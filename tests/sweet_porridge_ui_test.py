"""Walk both bookshelf compositions through every translated story page privately."""
from pathlib import Path
import os
import json
import subprocess
import tempfile
import time
import re
import unicodedata
from PIL import Image, ImageChops, ImageStat
from runtime_test import Desktop, ROOT, title_keys, title_unit
work = ROOT/'work/porridge-portrait-integration/ui'
work.mkdir(parents=True,exist_ok=True)
data=json.loads((ROOT/'tools/title_hotspots.json').read_text())
book=next(s for s in data['scenes'] if s['name']=='bookshelf')
story=json.loads((ROOT/'tools/sweet_porridge.json').read_text())
def tokens(text):
    text=unicodedata.normalize('NFKD',text.casefold())
    return re.findall(r'[a-z]+', ''.join(c for c in text if not unicodedata.combining(c)))
with tempfile.TemporaryDirectory(prefix='reader-',dir=work) as temp:
    binary = Path(os.environ.get('JUNGLE_TEST_BINARY', ROOT/'build/app/jungle'))
    with Desktop(binary,Path(temp),screen_size='1280x1100') as desktop:
        for width,height in ((960,600),(420,900)):
            desktop.resize(width,height)
            for language,first,last in ((0,'Sweet','Everyone'),(1,'Der','Alle'),(2,'La','Todos')):
                desktop.key('Home')
                unit=title_unit(width,height)
                desktop.click_actual(round((22+34*language)*unit),round(17*unit))
                for key in title_keys('Sweet Porridge')[1:-1]: desktop.key(key)
                variant=book['portrait'] if height>width else dict(book,width=data['width'],height=data['height'])
                h=next(h for h in variant['hotspots'] if h['id']=='fairy-tale')
                x=sum(p[0] for p in h['polygon'])/len(h['polygon']);y=sum(p[1] for p in h['polygon'])/len(h['polygon'])
                scale=max(width/variant['width'],height/variant['height'])
                # The actual book is visible before any pan, with no hint covering it.
                left=(width-variant['width']*scale)/2; top=(height-variant['height']*scale)/2
                xs=[point[0] for point in h['polygon']]; ys=[point[1] for point in h['polygon']]
                full=(left+min(xs)*scale,top+min(ys)*scale,left+max(xs)*scale,top+max(ys)*scale)
                # Narrow phones may clip a sliver of the painted spine at the
                # edge; at least 95% of the book must be on screen.
                box=tuple(round(value) for value in (max(0,full[0]),max(0,full[1]),min(width,full[2]),min(height,full[3])))
                visible=(box[2]-box[0])*(box[3]-box[1])/((full[2]-full[0])*(full[3]-full[1]))
                assert visible>=.95, f'Story book mostly off screen: {full} {visible:.3f}'
                source_box=tuple((value-offset)/scale for value,offset in zip(box,(left,top,left,top)))
                expected=Image.open(ROOT/variant['image']).convert('RGB').crop(tuple(round(v) for v in source_box))
                expected=expected.resize((box[2]-box[0],box[3]-box[1]),Image.Resampling.BILINEAR)
                deadline=time.monotonic()+10
                while True:
                    shelf_before=desktop.capture_actual(f'shelf-entry-{width}-{language}')
                    shelf_before.save(work/f'shelf-entry-{width}-{language}.png')
                    error=ImageStat.Stat(ImageChops.difference(shelf_before.crop(box),expected)).mean
                    if max(error)<18: break
                    assert time.monotonic()<deadline, f'Story entry obscured: {error}'
                    time.sleep(.2)
                desktop.click_actual(round(left+x*scale),round(top+y*scale))
                def capture(page):
                    name=f'story-{width}-{language}-{page}'
                    picture=desktop.capture_actual(name)
                    picture.save(work/(name+'.png'))
                    return picture
                def paper_box(page):
                    # Real reader coordinates below the shared 56px title bar.
                    bh=height-56
                    caption=120 if width>=bh else 140
                    portrait=bh>width
                    source_top=1536 if portrait else story['pages'][page]['paper_top']
                    source_width=1024 if portrait else 1536
                    span=min(width,(bh-caption-52)*source_width//source_top)
                    art=span*source_top//source_width
                    xx=(width-span)//2
                    return (xx,56+art,xx+span,height)
                def words(picture,page):
                    path=work/'caption.png'
                    index=10 if page=='last-again' else page
                    box=paper_box(index)
                    art_box=(box[0],56,box[2],box[1])
                    assert art_box[1]==56
                    assert 56<=box[1]<box[3]==height
                    # The outside margins must be the original painted paper,
                    # proving captions sit on the artwork rather than a UI card.
                    source=Image.open(ROOT/f"assets/jungle-book/pages/{story['pages'][index]['asset']}.webp").convert('RGB')
                    expected=source.crop((0,story['pages'][index]['paper_top'],1536,1024)).resize((box[2]-box[0],box[3]-box[1]),Image.Resampling.BILINEAR)
                    art_source=Image.open(ROOT/f"assets/jungle-book/portraits/{story['pages'][index]['portrait_asset']}.webp").convert('RGB') if height-56>width else source.crop((0,0,1536,story['pages'][index]['paper_top']))
                    artwork=art_source.resize((art_box[2]-art_box[0],art_box[3]-art_box[1]),Image.Resampling.BILINEAR)
                    assert max(ImageStat.Stat(ImageChops.difference(picture.crop(art_box),artwork)).mean)<12, 'Illustration cropped or not at page top'
                    actual=picture.crop(box)
                    for margin in ((0,0,12,100),(actual.width-12,0,actual.width,100)):
                        error=ImageStat.Stat(ImageChops.difference(actual.crop(margin),expected.crop(margin))).mean
                        assert max(error)<12, f'Caption paper not inside accepted painting: {box} {error}'
                    caption=120 if width>=height-56 else 140
                    text_area=actual.crop((16,8,actual.width-16,caption-8))
                    text_area.resize((text_area.width*2,text_area.height*2)).save(path)
                    result=subprocess.run(['tesseract',str(path),'stdout','--psm','6'],text=True,capture_output=True,check=True).stdout
                    (work/f'ocr-{width}-{language}-{page}.txt').write_text(result)
                    return result
                deadline=time.monotonic()+25
                while True:
                    cover=capture(0)
                    if first.casefold() in words(cover,0).casefold(): break
                    assert time.monotonic()<deadline,'Story cover did not load in selected language'
                    time.sleep(.25)
                desktop.key('space')
                previous=cover
                for page in range(1,11):
                    desktop.key('Right')
                    picture=capture(page)
                    area=(20,80,width-20,height-280 if height>width else height-220)
                    error=ImageStat.Stat(ImageChops.difference(previous.crop(area),picture.crop(area))).mean
                    assert max(error)>2,f'No scene change on page {page}'
                    text=words(picture,page)
                    expected=tokens(story['pages'][page][('en','de','es')[language]])
                    actual=tokens(text)
                    assert expected[-1] in ''.join(actual[-3:]) or (expected[-1]=='kuche' and any(word in actual for word in ('ktiche','kiiche'))), f'Caption ending clipped on page {page}: {text}'
                    assert len(set(expected)&set(actual))/len(set(expected))>.72, f'Missing full caption on page {page}: {text}'
                    previous=picture
                assert last.casefold() in text.casefold(),f'Ending missing: {text}'
                # The icon resumes/pauses without changing the page. Paused
                # page turns must keep narration paused as well as autoplay.
                icon_y=paper_box(10)[1]+(120 if width>=height-56 else 140)+4
                icon=(width//2,icon_y+22)
                icon_box=(width//2-22,icon_y,width//2+22,icon_y+44)
                paused_icon=previous.crop(icon_box)
                desktop.click_actual(*icon)
                resumed=capture('resumed')
                assert ImageStat.Stat(ImageChops.difference(resumed.crop(icon_box),paused_icon)).mean[0]>2
                desktop.click_actual(*icon)
                paused=capture('paused')
                assert ImageStat.Stat(ImageChops.difference(paused.crop(icon_box),paused_icon)).mean[0]<1
                assert ImageStat.Stat(ImageChops.difference(paused.crop(area),previous.crop(area))).mean[0]<1
                desktop.key('Right')
                finished=capture('finished')
                assert ImageStat.Stat(ImageChops.difference(finished,previous)).mean[0]>10
                desktop.key('Left')
                assert last.casefold() in words(capture('last-again'),'last-again').casefold()
                desktop.key('Escape')
                shelf=desktop.capture_actual(f'back-{width}-{language}')
                shelf.save(work/f'back-{width}-{language}.png')
                # Direct Back returns to the painted shelf, not a word-book chooser.
                assert ImageStat.Stat(ImageChops.difference(shelf,previous)).mean[0]>10
print('local story UI test passed: both bookshelf targets, EN/DE/ES, cover and all 10 pages, complete ending, Back')

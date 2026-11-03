"""Verify visible cover priority and shelf return on an owned private display."""
import json,tempfile,time
from pathlib import Path
from PIL import Image,ImageChops,ImageStat
import runtime_test as rt


def main():
    scratch=rt.ROOT/'backup/title-smoke'
    rt.OUTPUT=scratch/'shelf-captures'
    data=json.loads((rt.ROOT/'tools/title_hotspots.json').read_text())
    home=data['scenes'][0]
    shelf=next(s for s in data['scenes'] if s['name']=='bookshelf')
    for w,h in ((960,600),(420,900)):
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            state=Path(folder);(state/'guide.txt').write_text('seen\n');(state/'sound.txt').write_text('off\n')
            with rt.Desktop(rt.ROOT/'build/app/jungle',state,screen_size='1280x1100') as d:
                d.resize(w,h)
                def enter():
                    d.key('Home');d.key(str(next(i+1 for i,x in enumerate(home['hotspots']) if x['target']=='scene:bookshelf')));time.sleep(.6)
                def point(x,y,click=False):
                    rt.run(['xdotool','mousemove','--window',d.window,str(round(x)),str(round(y))],d.env)
                    time.sleep(.2)
                    if click:
                        rt.run(['xdotool','mousedown','1'],d.env);time.sleep(.1);rt.run(['xdotool','mouseup','1'],d.env);time.sleep(.6)
                enter()
                view=shelf['portrait'] if h>w else shelf
                aw,ah=(1024,1536) if h>w else (1672,941)
                scale=max(w/aw,h/ah);ox=(w-aw*scale)/2;oy=(h-ah*scale)/2
                for ident in ('book-cover-tiger','book-cover-rabbit','picture-books','fairy-tale'):
                    enter();point(w*.95,h*.5)
                    before=d.capture_actual(f'{w}-{ident}-rest')
                    if ident=='book-cover-tiger':
                        # The retired paper/stencil must not cover the tiger at rest.
                        full=Image.open(rt.ROOT/view['image']).convert('RGB')
                        expected=full.resize((round(aw*scale),round(ah*scale)),Image.Resampling.BILINEAR)
                        sx,sy,edge,_=view['paper']
                        left,top=round(ox+(sx-edge*.3)*scale),round(oy+(sy-edge*.3)*scale)
                        right,bottom=round(left+edge*.6*scale),round(top+edge*.6*scale)
                        region=(left,top,right,bottom)
                        reference=expected.crop((left-round(ox),top-round(oy),right-round(ox),bottom-round(oy)))
                        assert max(ImageStat.Stat(ImageChops.difference(before.crop(region).convert('RGB'),reference)).mean)<12,'extra paper overlay covers tiger'
                    x,y,bw,bh=next(x for x in view['hotspots'] if x['id']==ident)['glow_rect']
                    px,py=(x+bw/2,y+bh/2) if ident!='picture-books' else ((380,420) if h>w else (620,220))
                    point(ox+px*scale,oy+py*scale)
                    hover=d.capture_actual(f'{w}-{ident}-hover')
                    assert max(ImageStat.Stat(ImageChops.difference(before,hover)).mean)>.05,ident+' did not highlight'
                    point(ox+px*scale,oy+py*scale,True)
                    opened=d.capture_actual(f'{w}-{ident}-open')
                    assert max(ImageStat.Stat(ImageChops.difference(hover,opened)).mean)>8,ident+' did not open'
                    # Return through the shared title Back, regardless of reader state.
                    for _ in range(3):d.key('Escape')
                enter()
                point(27*rt.title_unit(w,h),21*rt.title_unit(w,h),True)
                returned=d.capture_actual(f'{w}-shelf-back')
                d.key('Home');time.sleep(.3)
                expected=d.capture_actual(f'{w}-home')
                assert max(ImageStat.Stat(ImageChops.difference(expected,returned)).mean)<1,'Shelf Back did not return'
                d.alive()
            print(f'local shelf smoke: {w}x{h}, tiger/rabbit/row/stories hover+click and top-left Back passed',flush=True)

if __name__=='__main__':main()

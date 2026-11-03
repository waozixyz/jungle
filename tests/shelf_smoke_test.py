"""Verify the whole first-row shelf glow, every book, its stencil and Back on an owned private display."""
import json,tempfile,time
from pathlib import Path
from PIL import Image,ImageChops,ImageStat
import runtime_test as rt

# Painted first-row covers (tiger, frogs, rabbit) in source pixels.
COVERS={False:([330,88,610,344],[630,110,865,358],[888,127,1128,372]),
        True:([133,248,348,515],[411,264,605,529],[656,279,854,540])}
# A spot on no hotspot, for resting captures.
REST={False:(250,500),True:(300,1420)}


def main():
    scratch=rt.ROOT/'backup/title-smoke'
    rt.OUTPUT=scratch/'shelf-captures'
    data=json.loads((rt.ROOT/'tools/title_hotspots.json').read_text())
    home=data['scenes'][0]
    shelf=next(s for s in data['scenes'] if s['name']=='bookshelf')
    for w,h in ((960,600),(420,900)):
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            state=Path(folder);(state/'guide.txt').write_text('seen\n');(state/'sound.txt').write_text('off\n')
            with rt.Desktop(rt.ROOT/'build/app/jungle',state,extra_env={'TMPDIR':str(state)},screen_size='1280x1100') as d:
                d.resize(w,h)
                portrait=h>w
                view=shelf['portrait'] if portrait else shelf
                aw,ah=(1024,1536) if portrait else (1672,941)
                scale=max(w/aw,h/ah);ox=(w-aw*scale)/2;oy=(h-ah*scale)/2
                expected=Image.open(rt.ROOT/view['image']).convert('RGB').resize((round(aw*scale),round(ah*scale)),Image.Resampling.BILINEAR)
                def enter():
                    d.key('Home');d.key(str(next(i+1 for i,x in enumerate(home['hotspots']) if x['target']=='scene:bookshelf')));time.sleep(.6)
                def point(x,y,click=False):
                    rt.run(['xdotool','mousemove','--window',d.window,str(round(ox+x*scale)),str(round(oy+y*scale))],d.env)
                    time.sleep(.3)
                    if click:
                        rt.run(['xdotool','mousedown','1'],d.env);time.sleep(.1);rt.run(['xdotool','mouseup','1'],d.env);time.sleep(.6)
                def box(rect):
                    x0,y0,x1,y1=rect
                    return (max(0,round(ox+x0*scale)),max(0,round(oy+y0*scale)),min(w,round(ox+x1*scale)),min(h,round(oy+y1*scale)))
                def differ(a,b,rect):
                    region=box(rect)
                    return max(ImageStat.Stat(ImageChops.difference(a.crop(region),b.crop(region))).mean)
                def painted(frame,rect):
                    region=box(rect)
                    ref=expected.crop((region[0]-round(ox),region[1]-round(oy),region[2]-round(ox),region[3]-round(oy)))
                    return max(ImageStat.Stat(ImageChops.difference(frame.crop(region),ref)).mean)
                row=next(x for x in view['hotspots'] if x['id']=='picture-books')
                story=next(x for x in view['hotspots'] if x['id']=='fairy-tale')
                books=list(COVERS[portrait])+[[x,y,x+bw,y+bh] for x,y,bw,bh in (next(x for x in view['hotspots'] if x['id']==i)['glow_rect'] for i in ('book-abc','book-123'))]
                sx,sy,edge,reveal=view['paper']
                stencil=[COVERS[portrait][0][2]+2,sy-edge*.3,COVERS[portrait][0][2]+edge*.12,sy+edge*.3]
                enter();point(*REST[portrait])
                rest=d.capture_actual(f'{w}-rest')
                # Every painted book is visible; the stencil peeks out beside the tiger.
                x,y,bw,bh=story['glow_rect']
                for rect in books+[[x+bw*.02,y+bh*.05,x+bw*.98,y+bh*.95]]:
                    assert painted(rest,rect)<12,f'shelf book missing or covered at {rect}'
                assert painted(rest,stencil)>12,'shelf stencil is not peeking out beside the tiger'
                for index,cover in enumerate(COVERS[portrait]):
                    enter();point(*REST[portrait]);rest=d.capture_actual(f'{w}-row-{index}-rest')
                    point((cover[0]+cover[2])/2,(cover[1]+cover[3])/2)
                    hover=d.capture_actual(f'{w}-row-{index}-hover')
                    # Pointing at any one book glows the whole row, tiger included.
                    for other in COVERS[portrait]:
                        assert differ(rest,hover,other)>.5,f'first row did not glow as one row from book {index}'
                    if index!=1:continue
                    point((cover[0]+cover[2])/2,(cover[1]+cover[3])/2,True)
                    opened=d.capture_actual(f'{w}-row-open')
                    assert max(ImageStat.Stat(ImageChops.difference(hover,opened)).mean)>8,'first row did not open'
                    for _ in range(3):d.key('Escape')
                enter();point(*REST[portrait]);rest=d.capture_actual(f'{w}-stories-rest')
                point(x+bw*.85,y+bh/2)
                hover=d.capture_actual(f'{w}-stories-hover')
                assert differ(rest,hover,[x+bw*.05,y+bh*.1,x+bw*.3,y+bh*.9])>.5,'Stories row did not glow as one row'
                point(x+bw*.85,y+bh/2,True)
                opened=d.capture_actual(f'{w}-stories-open')
                assert max(ImageStat.Stat(ImageChops.difference(hover,opened)).mean)>8,'Stories row did not open'
                for _ in range(3):d.key('Escape')
                # Only the stencil's visible edge reveals it, without the row glow; a tap collects it.
                enter();point(*REST[portrait]);rest=d.capture_actual(f'{w}-stencil-rest')
                point(stencil[0]+(stencil[2]-stencil[0])/2,sy)
                time.sleep(.4)
                hover=d.capture_actual(f'{w}-stencil-hover')
                assert differ(rest,hover,[stencil[2],sy-edge*.3,stencil[2]+reveal,sy+edge*.3])>8,'stencil did not slide out'
                assert differ(rest,hover,COVERS[portrait][2])<.5,'stencil hover also glowed the row'
                point(stencil[0]+(stencil[2]-stencil[0])/2,sy,True)
                time.sleep(1.5)
                assert 'bookshelf-scene' in (state/'collection.txt').read_text(),'shelf stencil was not collected'
                enter()
                point((27*rt.title_unit(w,h)-ox)/scale,(21*rt.title_unit(w,h)-oy)/scale,True)
                returned=d.capture_actual(f'{w}-shelf-back')
                d.key('Home');time.sleep(.3)
                home_frame=d.capture_actual(f'{w}-home')
                assert max(ImageStat.Stat(ImageChops.difference(home_frame,returned)).mean)<1,'Shelf Back did not return'
                d.alive()
            print(f'local shelf smoke: {w}x{h}, every book, whole first row, Stories row, stencil and top-left Back passed',flush=True)

if __name__=='__main__':main()

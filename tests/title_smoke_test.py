"""One local smoke run, both orientations, using only an owned private Xvfb."""
import json
import os
from pathlib import Path
import tempfile
import time
from PIL import Image, ImageChops, ImageStat
import runtime_test as rt


def main():
    root = rt.ROOT
    scratch = root/'backup/title-smoke'
    scratch.mkdir(parents=True, exist_ok=True)
    rt.OUTPUT = scratch/'captures'
    data = json.loads((root/'tools/title_hotspots.json').read_text())
    home = data['scenes'][0]
    campus = next(s for s in data['scenes'] if s['name']=='campus')
    binary = Path(os.environ.get('JUNGLE_TEST_BINARY', root/'build/app/jungle'))
    for w,h in ((960,600),(420,900),(1080,2340),(700,1100)):
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            state = Path(folder)
            (state/'sound.txt').write_text('off\n')
            (state/'guide.txt').write_text('seen\n')
            old = state/'games/jungle.garden/garden.txt'
            old.parent.mkdir(parents=True)
            old.write_text('garden 2 6\n1 100 100 3700 3600 0\n'+'0 0 0 0 0 0\n'*4+'2 100 100 3700 3600 0\n')
            with rt.Desktop(binary,state,extra_env={'TMPDIR':str(state)},screen_size='1400x2500') as d:
                def tap(x,y):
                    rt.run(['xdotool','mousemove','--window',d.window,str(x),str(y)],d.env)
                    time.sleep(.08)
                    rt.run(['xdotool','mousedown','1'],d.env)
                    time.sleep(.12)
                    rt.run(['xdotool','mouseup','1'],d.env)
                    time.sleep(.3)
                def wait_for(reference, name, opened=True):
                    deadline = time.monotonic()+10
                    while True:
                        picture = d.capture_actual(name)
                        area = (10,85,w-10,h-10)
                        difference = max(ImageStat.Stat(ImageChops.difference(
                            reference.crop(area),picture.crop(area))).mean)
                        if (difference > 8 if opened else difference < 8):
                            return picture
                        assert time.monotonic()<deadline,(w,locale,name,difference)
                        time.sleep(.15)
                def scene_return(name):
                    farm=next(s for s in data['scenes'] if s['name']==name)
                    farm=farm['portrait'] if h>w else farm
                    # The scene's own sign back to Campus.
                    sign=next(t for t in farm['hotspots'] if t['target']=='scene:campus')
                    assert sign['sign']['direction']==('right' if name in ('farm','jungle-path') else 'left')
                    x,y,_,_=sign['glow_rect'];bx,by,bw,bh=sign['sign']['label_rect']
                    fs=max(w/(1024 if h>w else 1672),h/(1536 if h>w else 941))
                    fx=(w-(1024 if h>w else 1672)*fs)/2;fy=(h-(1536 if h>w else 941)*fs)/2
                    tap(round(fx+(x+bx+bw/2)*fs),round(fy+(y+by+bh/2)*fs))
                d.resize(w,h)
                for locale in range(3):
                    d.key('Home')
                    tap(round((21+34*locale)*rt.title_unit(w,h)),round(17*rt.title_unit(w,h)))
                    d.key(str(next(i+1 for i,h in enumerate(home['hotspots']) if h['target']=='scene:campus')))
                    time.sleep(.6)
                    view = campus['portrait'] if h>w else campus
                    scale=(min if h>w else max)(w/(1024 if h>w else 1672),h/(1536 if h>w else 941))
                    ox=(w-(1024 if h>w else 1672)*scale)/2
                    oy=(h-(1536 if h>w else 941)*scale)/2
                    if h>w:
                        assert ox>=0 and oy>=0 and ox+1024*scale<=w+.01 and oy+1536*scale<=h+.01
                        actual=d.capture_actual(f'{w}-{locale}-portrait-composition').convert('RGB')
                        full=Image.open(root/view['image']).convert('RGB')
                        # Sample untouched paint at the treehouse, left route, pond and
                        # right-hand desert. These detect cropping or a stale plate.
                        for box in ((300,50,500,200),(350,950,500,1050),(100,1350,250,1450),(900,300,1010,400)):
                            region=tuple(round((ox if i%2==0 else oy)+v*scale) for i,v in enumerate(box))
                            scaled=full.resize((round(1024*scale),round(1536*scale)),Image.Resampling.BILINEAR)
                            local=tuple(v-round(ox if i%2==0 else oy) for i,v in enumerate(region))
                            ref=scaled.crop(local).resize((32,32),Image.Resampling.BILINEAR)
                            got=actual.crop(region).resize((32,32),Image.Resampling.BILINEAR)
                            assert max(ImageStat.Stat(ImageChops.difference(ref,got)).mean)<10,('portrait plate or transform',w,box)
                    # The complete Farm board, including its left arrow, stays onscreen.
                    farm_sign=next(t for t in view['hotspots'] if t['id']=='farm-path')
                    x,y,_,_=farm_sign['glow_rect'];bx,by,bw,bh=farm_sign['sign']['label_rect']
                    assert ox+(x+bx)*scale>=0 and ox+(x+bx+bw)*scale<=w
                    assert farm_sign['sign']['direction']=='left'
                    for ident in ('farm-path','jungle-path','desert-path'):
                        target=next(t for t in view['hotspots'] if t['id']==ident)
                        x,y,_,_=target['glow_rect'];bx,by,bw,bh=target['sign']['label_rect']
                        before=d.capture_actual('campus')
                        tap(round(ox+(x+bx+bw/2)*scale),round(oy+(y+by+bh/2)*scale))
                        wait_for(before,f'{w}-{locale}-{ident}')
                        if ident=='farm-path':
                            time.sleep(.7)
                            actual=d.capture_actual(f'{w}-{locale}-farm-painting').convert('RGB')
                            full=Image.open(root/('assets/jungle/title/farm-portrait.webp' if h>w else 'assets/jungle/title/farm.webp')).convert('RGB')
                            fs=max(w/full.width,h/full.height)
                            fx=(w-full.width*fs)/2;fy=(h-full.height*fs)/2
                            fw,fh=round(full.width*fs),round(full.height*fs)
                            expected=full.resize((fw,fh),Image.Resampling.BILINEAR)
                            # Central/lower painting must be the full artwork, without UI or placeholder.
                            region=(round(w*.2),round(h*.48),round(w*.8),round(h*.9))
                            ref=expected.crop((region[0]-round(fx),region[1]-round(fy),region[2]-round(fx),region[3]-round(fy)))
                            assert max(ImageStat.Stat(ImageChops.difference(actual.crop(region).resize((64,64)),ref.resize((64,64)))).mean)<4,'Farm full painting missing or covered'
                            scene_return('farm')
                        elif ident=='jungle-path':scene_return('jungle-path')
                        else:d.key('Escape')
                        wait_for(before,'returned',opened=False)
                    assert old.read_text().startswith('garden 2 6\n1 100 100 3700 3600 0\n'), 'existing garden save changed'
                    assert not (state/'games/jungle.farm').exists(),'duplicate Farm save identity'

                    # Keyboard uses the same actual Farm hotspot and return path.
                    d.key('Home')
                    d.key(str(next(i+1 for i,h in enumerate(home['hotspots']) if h['target']=='scene:campus')))
                    time.sleep(.6)
                    centered=d.capture_actual('centered-campus')
                    for _ in range(next(i+1 for i,t in enumerate(view['hotspots']) if t['id']=='farm-path')):
                        d.key('Right')
                    before=d.capture_actual('keyboard-campus')
                    d.key('Return')
                    time.sleep(.5)
                    wait_for(before,f'{w}-{locale}-keyboard-farm')
                    d.key('Escape')
                    wait_for(centered,'keyboard-returned',opened=False)
                d.alive()
            print(f'local smoke: {w}x{h}, EN/DE/ES, Farm/Jungle Path/Desert, pointer and keyboard, Campus return and garden save passed',flush=True)


if __name__=='__main__':main()

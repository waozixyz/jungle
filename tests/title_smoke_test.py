"""One local smoke run, both orientations, using only an owned private Xvfb."""
import json
import os
from pathlib import Path
import tempfile
import time
from PIL import ImageChops, ImageStat
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
    for w,h in ((960,600),(420,900)):
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            state = Path(folder)
            (state/'sound.txt').write_text('off\n')
            (state/'guide.txt').write_text('seen\n')
            old = state/'games/jungle.garden/garden.txt'
            old.parent.mkdir(parents=True)
            old.write_text('garden 2 6\n1 100 100 3700 3600 0\n'+'0 0 0 0 0 0\n'*4+'2 100 100 3700 3600 0\n')
            with rt.Desktop(binary,state,extra_env={'TMPDIR':str(state)},screen_size='1280x1100') as d:
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
                def farm_return():
                    # The painted Campus sign uses Farm's contained scene layout.
                    bh=h-56
                    scale=min(w/400,bh/640) if h>w else min(bh/430,w/760)
                    scale=min(scale,1.8)
                    width,height=int(w/scale),int(bh/scale)
                    tray=180 if width<600 else 94
                    aw,ah=(1024,1536) if h>w else (1671,941)
                    sw,sh=width,width*ah//aw
                    if sh>height-tray:sh=height-tray;sw=sh*aw//ah
                    sx,sy=(width-sw)//2,tray+(height-tray-sh)//2
                    rect=(680,320,180,180) if h>w else (1400,80,210,210)
                    x,y,edge,_=rect
                    tap(round((sx+(x+edge*625/1254)*sw/aw)*scale),
                        round(56+(sy+(y+edge*460/1254)*sh/ah)*scale))
                d.resize(w,h)
                for locale in range(3):
                    d.key('Home')
                    tap(round((21+34*locale)*rt.title_unit(w,h)),round(17*rt.title_unit(w,h)))
                    d.key(str(next(i+1 for i,h in enumerate(home['hotspots']) if h['target']=='scene:campus')))
                    time.sleep(.6)
                    view = campus['portrait'] if h>w else campus
                    scale=max(w/(1024 if h>w else 1672),h/(1536 if h>w else 941))
                    ox=(w-(1024 if h>w else 1672)*scale)/2
                    oy=(h-(1536 if h>w else 941)*scale)/2
                    for ident in ('farm-path','beach-path','desert-path'):
                        target=next(t for t in view['hotspots'] if t['id']==ident)
                        x,y,_,_=target['glow_rect'];bx,by,bw,bh=target['sign']['label_rect']
                        before=d.capture_actual('campus')
                        tap(round(ox+(x+bx+bw/2)*scale),round(oy+(y+by+bh/2)*scale))
                        wait_for(before,f'{w}-{locale}-{ident}')
                        if ident=='farm-path':farm_return()
                        else:d.key('Escape')
                        wait_for(before,'returned',opened=False)
                    saved=old.read_text().splitlines()
                    assert saved[0]=='garden 3 6' and saved[1].split()[0]=='1' and saved[-1].split()[0]=='2','existing garden plants lost'
                    assert not (state/'games/jungle.farm').exists(),'duplicate Farm save identity'

                    # Keyboard uses the same actual Farm hotspot and return path.
                    d.key('Home')
                    d.key(str(next(i+1 for i,h in enumerate(home['hotspots']) if h['target']=='scene:campus')))
                    for _ in range(next(i+1 for i,t in enumerate(view['hotspots']) if t['id']=='farm-path')):
                        d.key('Right')
                    before=d.capture_actual('keyboard-campus')
                    d.key('Return')
                    wait_for(before,f'{w}-{locale}-keyboard-farm')
                    d.key('Escape')
                    wait_for(before,'keyboard-returned',opened=False)
                d.alive()
            print(f'local smoke: {w}x{h}, EN/DE/ES, Farm/Beach/Desert, pointer and keyboard, Campus return and garden save passed',flush=True)


if __name__=='__main__':main()

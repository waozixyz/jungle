#!/usr/bin/env python3
"""Real host dispatch, interaction and isolated saves on owned private Xvfb."""
from pathlib import Path
import tempfile
import time
from PIL import ImageChops
import runtime_test as rt

rt.OUTPUT = rt.ROOT / 'backup/new-activities-ui'
TITLES = {'shapes':'Shapes & Sorting','matching':'Matching Pairs','hide_seek':'Hide & Seek','drums':'Music Room','garden':'Grow a Garden'}


def geometry(name, width, height):
    height -= 56
    if name == 'shapes':
        s = min(width/360, height/640) if width <= height else min(height/420, width/720)
        s = min(s, 1.6)
    elif name == 'garden':
        s = min(width/400, height/640) if width <= height else min(height/430, width/760)
        s = min(s, 1.8)
    else:
        s = min(width/400, height/700) if width <= height else min(height/520, width/780)
        s = max(.5, min(s, 1.6))
    return s, int(width/s), int(height/s)


def main():
    with tempfile.TemporaryDirectory(prefix='jungle-activities-') as temporary:
        for lang in ('en','de','es'):
            data = Path(temporary)/lang
            data.mkdir(); (data/'language.txt').write_text(lang)
            with rt.Desktop(rt.ROOT/'build/app/jungle', data, screen_size='1280x1100') as d:
                for name,title in TITLES.items():
                    if name=='garden' and title not in (rt.ROOT/'games/catalog.txt').read_text(): continue
                    d.game(title)
                    for size in ((400,756),(960,600),(1200,900)):
                        d.resize(*size)
                        picture=d.capture_actual(f'{name}-{lang}-{size[0]}')
                        assert len(picture.getcolors(1000000)) > 30, (name,'empty screen')
                    d.resize(400,756)
                    s,w,h=geometry(name,400,756)
                    def click(x,y): d.click_actual(round(x*s),round(56+y*s))
                    def save():
                        path=data/f'games/jungle.{name}/{name}.txt'
                        assert path.exists(), f'{name} did not write its isolated save'
                        return path.read_text().split()
                    if name=='shapes':
                        # Switch all three sorting modes and retain the size mode.
                        button=min(84,(w-28-48)//5); left=(w-(button*5+48))//2
                        for mode in (1,2): click(left+mode*(button+12)+button/2,44)
                        assert save()[2]=='2', save()
                        # Sort both visible sizes into their actual matching homes.
                        round_no=int(save()[8]); random=(round_no*7919+2*104729)%2147483646+1
                        random=random*48271%2147483647; random=random*48271%2147483647
                        targets=[1,0] if random%2==0 else [0,1]
                        area_y=118; area_h=h-area_y-14; area_w=w-28
                        tray_h=area_h*42//100; edge=min((area_w-12)//2,tray_h,150)
                        grid_left=14+(area_w-(edge*2+12))//2
                        grid_y=area_y+(tray_h-edge)//2
                        target_w=min((area_w-12)//2,240)
                        target_h=min(area_h-tray_h-24,target_w*3//2)
                        target_y=area_y+tray_h+24+(area_h-tray_h-24-target_h)//2
                        target_left=14+(area_w-(target_w*2+12))//2
                        for item,target in enumerate(targets):
                            click(grid_left+item*(edge+12)+edge/2,grid_y+edge/2)
                            click(target_left+target*(target_w+12)+target_w/2,target_y+target_h/2)
                        time.sleep(3)
                        assert save()[6]=='1', ('sorting did not finish a clean round',save())

                    elif name=='matching':
                        # Save the generated easy board, reopen, and find one real pair.
                        d.key('Escape'); saved=save(); animals=saved[5:9]
                        d.game(title)
                        top,bottom=70,h-66-12-14
                        best=(0,0,0)
                        for cols in (1,2,4):
                            rows=4//cols; edge=min((w-32-14*(cols-1))//cols,(bottom-top-14*(rows-1))//rows)
                            if edge>best[0]: best=(edge,cols,rows)
                        edge,cols,rows=best;edge=min(edge,220)
                        left=16+(w-32-(cols*edge+(cols-1)*14))//2
                        above=top+(bottom-top-(rows*edge+(rows-1)*14))//2
                        pair=[i for i,a in enumerate(animals) if a==animals[0]]
                        for i in pair: click(left+i%cols*(edge+14)+edge/2,above+i//cols*(edge+14)+edge/2)
                        assert save()[9:13].count('1')==2,save()
                    elif name=='hide_seek':
                        # Friends start fully hidden; only one place is empty,
                        # so looking at the first two places finds a friend.
                        # An empty look changes nothing in the scene.
                        stage=(round(12*s),round(56+84*s),round((w-12)*s),round(56+(h-90)*s))
                        path=data/f'games/jungle.{name}/{name}.txt'
                        counted=lambda: int(path.read_text().split()[3]) if path.exists() else 0
                        found=0
                        for place in range(2):
                            if place: d.key('Right')
                            before=d.capture_actual(f'{name}-{lang}-look{place}-before').crop(stage)
                            count=counted(); d.key('Return'); time.sleep(.75)
                            after=d.capture_actual(f'{name}-{lang}-look{place}').crop(stage)
                            assert counted()-count in (0,1), ('one look counted twice',save())
                            if counted()>count:
                                found+=1
                                assert ImageChops.difference(before,after).getbbox(), 'Found friend did not appear'
                            elif not found:
                                assert not ImageChops.difference(before,after).getbbox(), 'Empty place revealed something'
                        assert found>=1 and save()[2]=='1' and save()[4]=='0', save()
                        # The one action, Hide again, keeps the counts.
                        kept=save(); click(w/2,h-45)
                        assert save()==kept, save()
                    elif name=='drums':
                        click(w/4,h/2); click(w*3/4,36)
                        time.sleep(.2)
                        assert save()[:2]==['drums','1'],save()
                    else:
                        # Choose seed, plant, water, sun and grow; assert every stage.
                        y=h-174+46
                        click(w/4,y)
                        assert save()[2]=='1',save()
                        for stage in range(2,6):
                            click(w/2,y)
                            assert save()[2]==str(stage),save()
                        click(w*3/4,h-40)
                        assert save()[4:6]==['1','1'],save()
                    d.capture_actual(f'{name}-{lang}-played')
                    # Shared mute is reversible; Back saves and returns to the menu.
                    d.click_actual(372,28)
                    assert (data/'sound.txt').read_text().strip()=='off'
                    d.click_actual(372,28)
                    assert (data/'sound.txt').read_text().strip()=='quiet'
                    d.click_actual(28,28)
                    original=save()
                    d.game(title); d.capture_actual(f'{name}-{lang}-resumed');d.key('Escape')
                    assert save()==original,(name,'resume changed persisted state',original,save())
                # Last menu row is reachable by End, with no punctuation shortcut.
                d.key('End'); d.capture_actual(f'menu-{lang}-end');d.key('Return');d.alive();d.key('Escape')
            print(f'local new activities UI: {lang} catalog activities dispatch, play, saves/resume and three sizes passed',flush=True)

def catalog_narration():
    from book_ui_test import select_book, different, SCENE
    import sys
    sys.path.insert(0, str(rt.ROOT/'tools'))
    from book_catalog import BOOKS
    with tempfile.TemporaryDirectory(prefix='catalog-narration-') as temporary:
        data=Path(temporary); (data/'language.txt').write_text('es')
        audio=data/'narration.raw'
        with rt.Desktop(rt.ROOT/'build/app/jungle',data,extra_env={'SDL_AUDIODRIVER':'disk','SDL_DISKAUDIOFILE':str(audio)}) as d:
            d.game('Picture Book');d.key('s')
            for category, indices in [('actions',range(8)),('sports',[6]),('birds',[2])]:
                select_book(d,[name for name,_ in BOOKS].index(category))
                d.key('space')
                previous=None
                for page in range(max(indices)+1):
                    if page: d.key('Right')
                    if page not in indices: continue
                    audio.write_bytes(b''); d.click_actual(620,563); time.sleep(.8)
                    # The actual Hear word button must send decoded PCM to SDL.
                    signal=0
                    with audio.open('rb') as pcm:
                        while chunk:=pcm.read(65536): signal+=sum(b not in (0,255) for b in chunk)
                    assert signal>1000, (category,page,'missing decoded narration')
                    picture=d.capture(f'catalog-{category}-{page}')
                    if previous is not None: assert different(previous,picture,SCENE), (category,page,'unchanged scene')
                    previous=picture
                d.key('Escape')
        print('local native catalog: Actions eight pages, Badminton and Spanish Pingüino narration passed',flush=True)

if __name__=='__main__':
    main()
    catalog_narration()

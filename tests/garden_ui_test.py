#!/usr/bin/env python3
"""Garden planting, dragging, offline care and persistence on owned Xvfb."""
from pathlib import Path
import tempfile
import time
from PIL import ImageChops
import runtime_test as rt
from new_activities_ui_test import geometry

SCRATCH = rt.ROOT/'work/garden-redesign/ui'
SCRATCH.mkdir(parents=True, exist_ok=True)
rt.OUTPUT = SCRATCH/'captures'

def main():
    for language in ('en','de','es'):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temporary:
            data=Path(temporary)
            (data/'language.txt').write_text(language)
            (data/'sound.txt').write_text('off\n')
            path=data/'games/jungle.garden/garden.txt'
            path.parent.mkdir(parents=True)
            now=int(time.time())
            # A thirsty cabbage and a dead tomato, plus four empty plots.
            path.write_text(f'garden 2 0\n6 {now-120000} {now-100000} {now-100000} 20000 0\n2 {now-400000} {now-300000} {now-300000} 100000 0\n'+'0 0 0 0 0 0\n'*4)
            with rt.Desktop(rt.ROOT/'build/app/jungle',data,screen_size='1280x1100') as d:
                d.game('Grow a Garden')
                def move(x,y):
                    rt.run(['xdotool','mousemove','--window',d.window,str(x),str(y)],d.env)
                    time.sleep(.15)
                def tap(x,y):
                    move(x,y)
                    rt.run(['xdotool','mousedown','1'],d.env)
                    time.sleep(.12)
                    rt.run(['xdotool','mouseup','1'],d.env)
                    time.sleep(.15)
                    d.alive()
                for size in ((400,756),(960,600),(1200,900)):
                    d.resize(*size)
                    s,w,h=geometry('garden',*size)
                    tray=180 if w<600 else 94
                    columns=4 if w<600 else 7
                    rows=2 if columns==4 else 1
                    cw,ch=(w-16)//columns,(tray-16)//rows
                    def tool(index):
                        return (round((8+(index%columns+.5)*cw)*s),round(56+(8+(index//columns+.5)*ch)*s))
                    def plot(index):
                        return (round(w*(26+index%3*24)/100*s),round(56+(tray+(h-tray)*(57 if index<3 else 78)/100)*s))
                    def saved():
                        return [list(map(int,line.split())) for line in path.read_text().splitlines()[1:]]
                    # Selection persists between sizes. Explicitly choose Water
                    # so the baseline and Pumpkin preview are different items.
                    tap(*tool(6))
                    before=d.capture_actual(f'{language}-{size[0]}-before')
                    assert before.getcolors(1000000) and len(before.getcolors(1000000))>1000, 'Painted scene did not render'
                    seed_plot={400:3,960:4,1200:5}[size[0]]
                    cursor_x,cursor_y=plot(seed_plot)
                    move(cursor_x,cursor_y)
                    unselected=d.capture_actual(f'{language}-{size[0]}-cursor-unselected')
                    tap(*tool(4))
                    assert path.read_text().splitlines()[0]=='garden 2 5', path.read_text()
                    move(cursor_x,cursor_y)
                    selected=d.capture_actual(f'{language}-{size[0]}-cursor-selected')
                    cursor_box=(max(0,cursor_x-70),max(0,cursor_y-110),min(before.width,cursor_x+70),min(before.height,cursor_y+50))
                    assert ImageChops.difference(unselected.crop(cursor_box),selected.crop(cursor_box)).getbbox(), 'Selected item did not attach to the cursor'
                    move(round(cursor_x+100*s),cursor_y)
                    moved=d.capture_actual(f'{language}-{size[0]}-cursor-moved')
                    assert ImageChops.difference(selected.crop(cursor_box),moved.crop(cursor_box)).getbbox(), 'Selected item did not follow hover movement'
                    planted_at=int(time.time())
                    tap(cursor_x,cursor_y)
                    move(8,8)
                    seed=d.capture_actual(f'{language}-{size[0]}-seed-dropped')
                    time.sleep(.4)
                    dropped=d.capture_actual(f'{language}-{size[0]}-seed-in-soil')
                    assert saved()[seed_plot][0]==5 and 0<=saved()[seed_plot][1]-planted_at<=2, 'Seed click did not plant the selected item'
                    assert saved()[seed_plot][4]<3600, 'New seed skipped the seed stage'
                    soil_box=(round(cursor_x-25*s),round(cursor_y-30*s),round(cursor_x+25*s),round(cursor_y+5*s))
                    seed_change=ImageChops.difference(before.crop(soil_box),dropped.crop(soil_box)).getbbox()
                    assert seed_change, 'Soil click did not visibly drop a seed'
                    # The planted object is a small seed, not a packet or leaves.
                    assert seed_change[2]-seed_change[0]<=24*s and seed_change[3]-seed_change[1]<=24*s, 'New planting rendered a packet or sprout'
                    falling_change=ImageChops.difference(before.crop(soil_box),seed.crop(soil_box)).getbbox()
                    assert falling_change and falling_change[1]<seed_change[1], 'Seed did not visibly fall toward the soil'
                    if size[0]==400:
                        assert saved()[1][-1]==1, 'Offline death not reconciled'
                        tap(*tool(6)); tap(*plot(0))
                        watering=d.capture_actual(f'{language}-watering')
                        time.sleep(1.3)
                        settled=d.capture_actual(f'{language}-water-settled')
                        def blue(picture):
                            return sum(b>r*1.3 and b>g*1.08 for r,g,b in picture.crop((0,round(56+tray*s),size[0],size[1])).getdata())
                        assert blue(watering)>blue(settled)+5, 'Painted water drops did not animate and settle'
                        wet=saved()[0]
                        assert int(time.time())-wet[2]<15 and wet[4]<=85000, wet
                        tap(*plot(1))
                        assert saved()[1]==[0]*6, 'Withered plant did not clear'
                        tap(*tool(5)); tap(*plot(1))
                        assert saved()[1][0]==6, 'Cabbage packet did not plant'
                        # Drag a tomato packet to a different empty plot.
                        x,y=tool(1); tx,ty=plot(2)
                        env=d.env
                        rt.run(['xdotool','mousemove','--window',d.window,str(x),str(y)],env)
                        rt.run(['xdotool','mousedown','1'],env); time.sleep(.15)
                        rt.run(['xdotool','mousemove','--window',d.window,str(tx),str(ty)],env); time.sleep(.2)
                        rt.run(['xdotool','mouseup','1'],env); time.sleep(.4)
                        assert saved()[2][0]==2, 'Dragged seed did not plant'
                        # A healthy plant cannot be overwritten by another seed.
                        tap(*tool(4)); tap(*plot(2))
                        assert saved()[2][0]==2, 'Seed replaced a living plant'
                    after=d.capture_actual(f'{language}-{size[0]}-after')
                    if size[0]==400:
                        assert ImageChops.difference(before,after).getbbox(), 'Water/plant actions did not change painted scene'
                checkpoint=saved()
                d.key('Escape'); d.game('Grow a Garden')
                d.capture_actual(f'{language}-resumed')
                for before,after in zip(checkpoint,saved()):
                    assert [after[i] for i in (0,1,2,5)]==[before[i] for i in (0,1,2,5)], 'Resume lost plant/care timestamps'
                    assert before[4]<=after[4]<=before[4]+60, 'Resume reset or rushed growth'
                d.key('Escape')
        print(f'local garden UI: {language}, portrait/landscape, tap/drag, care and resume passed',flush=True)

if __name__=='__main__': main()

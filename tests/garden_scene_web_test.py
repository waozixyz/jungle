"""Actual Garden touch/care/save/return in private Chromium, Canvas and DOM."""
import argparse
import base64
import json
import io
from PIL import Image, ImageStat, ImageChops
from pathlib import Path
import time
from book_media_start_web_test import browser, serve
from garden_scene_layout import soil_point
from new_activities_ui_test import geometry
from runtime_test import title_keys, title_unit

OUT=Path('work/garden-redesign/web-proof')
SAVE='/kryon-apps/jungle/jungle.garden/garden.txt'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--web-root',type=Path,required=True)
    args=parser.parse_args(); OUT.mkdir(parents=True,exist_ok=True)
    with serve(args.web_root.resolve()) as url:
        for renderer in ('canvas','dom'):
            for language in ('en','de','es'):
                with browser() as c:
                    c.call('Emulation.setDeviceMetricsOverride',width=400,height=756,deviceScaleFactor=1,mobile=False)
                    c.call('Page.navigate',url=f'{url}/{renderer}.html')
                    c.until('typeof Module!=="undefined"&&Module.FS&&document.getElementById("loading").style.display==="none"','startup')
                    time.sleep(.8)
                    original_click=c.click
                    def click(x,y):
                        c.call('Input.dispatchMouseEvent',type='mouseMoved',x=x,y=y)
                        time.sleep(.1);original_click(x,y)
                    c.click=click
                    unit=title_unit(400,756)
                    c.click((21+34*('en','de','es').index(language))*unit,17*unit)
                    c.until('document.documentElement.lang==='+json.dumps(language),'locale')
                    def open_game():
                        for key in title_keys('Grow a Garden'): c.key(key)
                        time.sleep(.6)
                    def painted(size):
                        name='scene-portrait' if size[0]<size[1] else 'scene-landscape'
                        paths=[f'assets/garden/art/{name}.png','assets/garden/art/campus-sign.png','assets/garden/art/watering-can.png']
                        paths += [f'assets/garden/art/{kind}-packet.png' for kind in ('sunflower','tomato','carrot','strawberry','pumpkin','cabbage')]
                        # Full bytes in FS alone are insufficient: both renderers must
                        # have decoded and drawn the scene and independent objects.
                        c.until('('+json.dumps(paths)+').every(p=>Module.FS.analyzePath("/"+p).exists)','automatically requested full Garden image bytes')
                        if renderer=='dom':
                            c.until('(()=>{const imgs=[...document.querySelectorAll("#kryon-dom-paint img")];return imgs.length>=9&&imgs.every(i=>i.complete&&i.naturalWidth>0)})()','decoded Garden DOM images')
                        time.sleep(.4)
                        picture=Image.open(io.BytesIO(base64.b64decode(c.call('Page.captureScreenshot',format='png')['data']))).convert('RGB')
                        s,w,h=geometry('garden',*size);tray=180 if w<600 else 94
                        aw,ah=(1024,1536) if w<h else (1671,941)
                        sw,sh=w,w*ah//aw
                        if sh>h-tray:sh=h-tray;sw=sh*aw//ah
                        ox,oy=(w-sw)//2,tray+(h-tray-sh)//2
                        # Sample the hut roof, away from plants/sign/tool cursors.
                        box=(round((ox+sw*.36)*s),round(56+(oy+sh*.12)*s),round((ox+sw*.58)*s),round(56+(oy+sh*.19)*s))
                        actual=picture.crop(box)
                        assert min(ImageStat.Stat(actual).stddev)>15, 'Garden painting absent (flat fallback pixels)'
                        expected=Image.open(Path('assets/garden/art')/(name+'.png')).convert('RGB').resize((round(sw*s),round(sh*s)))
                        exbox=(round(sw*.36*s),round(sh*.12*s),round(sw*.58*s),round(sh*.19*s))
                        reference=expected.crop(exbox).resize(actual.size)
                        assert sum(ImageStat.Stat(ImageChops.difference(actual,reference)).mean)/3<30, 'Rendered scene differs from approved painting'
                        return picture
                    def saved():
                        text=c.evaluate(f'Module.FS.readFile({json.dumps(SAVE)},{{encoding:"utf8"}})')
                        assert text.startswith('garden 3 '),text
                        return [list(map(int,line.split())) for line in text.splitlines()[1:]]
                    def touch(point):
                        c.call('Input.dispatchTouchEvent',type='touchStart',touchPoints=[dict(x=point[0],y=point[1],id=1)])
                        time.sleep(.1)
                        c.call('Input.dispatchTouchEvent',type='touchEnd',touchPoints=[]);time.sleep(.2)
                    for size in ((400,756),(960,600)):
                        c.call('Emulation.setDeviceMetricsOverride',width=size[0],height=size[1],deviceScaleFactor=1,mobile=False);time.sleep(.3)
                        open_game()
                        # Initialize an empty fixture through actual packet selection first.
                        s,w,h=geometry('garden',*size);tray=180 if w<600 else 94
                        columns=4 if w<600 else 7;rows=2 if columns==4 else 1
                        cw,ch=(w-16)//columns,(tray-16)//rows
                        def tool(i):return (8+(i%columns+.5)*cw)*s,56+(8+(i//columns+.5)*ch)*s
                        def soil(x,y):
                            px,py=soil_point(w,h,x,y);return px*s,56+py*s
                        c.click(*tool(6));painted(size);c.key('Escape')
                        empty='garden 3 0\n'+'0 0 0 0 0 0 0 0\n'*6
                        c.evaluate(f'Module.FS.writeFile({json.dumps(SAVE)},{json.dumps(empty)})')
                        open_game()
                        for i,position in enumerate(((260,490),(440,490),(700,490),(260,650),(440,710),(800,670))):
                            c.click(*tool(i));touch(soil(*position))
                            ps=saved();assert sum(p[0]>0 for p in ps)==i+1,ps
                            p=ps[i];assert p[0]==i+1 and abs(p[6]-position[0])<=30 and abs(p[7]-position[1])<=30,p
                            # Three physical screen pixels bounds delivered input
                            # against the rendered root, across differently sized beds.
                            assert max(abs(a-b) for a,b in zip(soil(p[6],p[7]),soil(*position)))<=3, (p,position)
                            touch(soil(680,710));assert sum(p[0]>0 for p in saved())==i+1,'packet planted twice'
                        ps=saved();time.sleep(1.1);c.click(*tool(6));touch(soil(ps[0][6],ps[0][7]))
                        wet=saved();assert wet[0][2]>ps[0][2] and wet[0][4]<60,(ps,wet)
                        portrait=w<h;aw,ah=(1024,1536) if portrait else (1671,941)
                        sw,sh=w,w*ah//aw
                        if sh>h-tray:sh=h-tray;sw=sh*aw//ah
                        ox,oy=(w-sw)//2,tray+(h-tray-sh)//2
                        x,y,e=(680,320,180) if portrait else (1400,80,210)
                        sign=((ox+(x+e*.5)*sw/aw)*s,56+(oy+(y+e*.4)*sh/ah)*s)
                        if renderer=='dom':assert 'Campus' in c.evaluate('[...document.querySelectorAll("#kryon-dom-root button")].map(e=>e.getAttribute("aria-label"))')
                        label=f'{renderer}-{language}-{size[0]}'
                        painted(size).save(OUT/f'{label}.png')
                        touch(sign);time.sleep(.4)
                        if renderer=='dom':assert 'Campus' not in c.evaluate('[...document.querySelectorAll("#kryon-dom-root button")].map(e=>e.getAttribute("aria-label"))'),'Sign did not leave Garden'
                        open_game();again=saved()
                        for old,new in zip(wet,again):
                            assert all(old[k]==new[k] for k in (0,1,2,5,6,7)),(old,new)
                            assert old[4]<=new[4]<=old[4]+60
                        c.key('Escape')
                        print(f'local Garden web: {label} six plants/four beds/one seed/touch/water/save/reopen/independent Campus return passed',flush=True)
if __name__=='__main__':main()

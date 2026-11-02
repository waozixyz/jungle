"""Actual mouse/touch/keyboard/DOM semantic sign policy, in private Chromium."""
import argparse
import base64
import io
import json
from pathlib import Path
import time
from PIL import Image, ImageChops, ImageStat
from book_media_start_web_test import browser, serve
from sign_policy_fixture import fixture
from sign_policy_ui_test import NOTICE, PREVIEW, text, WORK
from runtime_test import title_unit
from title_waterfront_ui_test import mapping

DATA = fixture()
LABELS = (('Beach','Farm','Desert'),('Strand','Bauernhof','Wüste'),('Playa','Granja','Desierto'))


def key(c, value):
    code,vk = (('Digit'+value,ord(value)) if len(value)==1 and value.isdigit() else
               ('Key'+value.upper(),ord(value.upper())) if len(value)==1 and value.isalpha() else
               {'Home':('Home',36),'Enter':('Enter',13),'ArrowRight':('ArrowRight',39),'Escape':('Escape',27)}[value])
    for kind in ('keyDown','keyUp'):
        c.call('Input.dispatchKeyEvent',type=kind,key=value,code=code,windowsVirtualKeyCode=vk)
        time.sleep(.04)


def shot(c):
    return Image.open(io.BytesIO(base64.b64decode(c.call('Page.captureScreenshot',format='png')['data']))).convert('RGB')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--web-root',type=Path,required=True)
    p.add_argument('--testing',action='store_true')
    args=p.parse_args();WORK.mkdir(parents=True,exist_ok=True)
    assert json.loads((args.web_root/'version.json').read_text())['testingRooms'] == args.testing
    with serve(args.web_root.resolve()) as url:
        for renderer in ('canvas','dom'):
            with browser() as c:
                c.key=lambda value:key(c,value)
                c.call('Page.navigate',url=url+'/'+renderer+'.html')
                c.until('document.getElementById("loading").style.display==="none"','startup')
                time.sleep(1)
                def move(x,y):
                    c.call('Input.dispatchMouseEvent',type='mouseMoved',x=x,y=y);time.sleep(.1)
                def click(x,y):
                    move(x,y);c.click(x,y)
                def touch(x,y):
                    c.call('Input.dispatchTouchEvent',type='touchStart',touchPoints=[dict(x=x,y=y,id=1)])
                    time.sleep(.1)
                    c.call('Input.dispatchTouchEvent',type='touchEnd',touchPoints=[])
                for w,h in ((960,600),(420,900)):
                    c.call('Emulation.setDeviceMetricsOverride',width=w,height=h,deviceScaleFactor=1,mobile=h>w)
                    c.call('Emulation.setTouchEmulationEnabled',enabled=True,maxTouchPoints=1)
                    time.sleep(.4)
                    for lang,code in enumerate(('en','de','es')):
                        c.key('Home');unit=title_unit(w,h)
                        click((21+34*lang)*unit,17*unit)
                        c.until('document.documentElement.lang==='+json.dumps(code),'locale')
                        home=DATA['scenes'][0]
                        c.key(str(next(i+1 for i,t in enumerate(home['hotspots']) if t['target']=='scene:campus')))
                        time.sleep(.8)
                        base=next(s for s in DATA['scenes'] if s['name']=='campus')
                        campus=base['portrait'] if h>w else base
                        scale,ox,oy=mapping(campus,w,h)
                        for room,sign in enumerate(campus['hotspots'][-3:]):
                            x,y,_,_=sign['glow_rect'];point=(ox+(x+90)*scale,oy+(y+50)*scale)
                            inputs=['mouse','touch','keyboard']+(['semantic'] if renderer=='dom' else [])
                            for kind in inputs:
                                c.key('Home')
                                c.key(str(next(i+1 for i,t in enumerate(home['hotspots']) if t['target']=='scene:campus')))
                                time.sleep(.3)
                                move(w-8,h-8);time.sleep(.2);before=shot(c);centered=before
                                saved=c.evaluate('JSON.stringify([...Object.keys(localStorage)].sort().map(k=>[k,localStorage[k]]))')
                                if kind=='mouse':click(*point)
                                elif kind=='touch':touch(*point)
                                elif kind=='keyboard':
                                    for _ in range(len(campus['hotspots'])-3+room+1):c.key('ArrowRight')
                                    before=shot(c)
                                    c.key('Enter')
                                else:
                                    label=json.dumps(LABELS[lang][room])
                                    c.evaluate('window.policyButton=[...document.querySelectorAll("#kryon-dom-root button")].find(e=>e.getAttribute("aria-label")==='+label+');policyButton.click();policyButton.click()')
                                time.sleep(.5)
                                current=shot(c)
                                words=text(current,f'web-{args.testing}-{renderer}-{w}-{lang}-{room}-{kind}')
                                if args.testing:
                                    if room:assert PREVIEW[lang].casefold() in words.casefold(),words
                                    else:assert max(ImageStat.Stat(ImageChops.difference(before,current)).mean)>15,'Beach did not open'
                                else:
                                    assert NOTICE[lang] in words.casefold(),words
                                    c.key('Home');c.key('1')
                                    if kind=='semantic':c.evaluate('policyButton.click();policyButton.click()')
                                if kind in ('mouse','touch') and (not args.testing or room):
                                    at=(24,26) if args.testing else (w/2,h/2+40)
                                    (touch if kind=='touch' else click)(*at)
                                else:c.key('Escape')
                                time.sleep(.3)
                                if args.testing and room==0:before=centered
                                move(w-8,h-8);time.sleep(.2);after=shot(c)
                                area=(12,80,w-12,h-12)
                                error=max(ImageStat.Stat(ImageChops.difference(before.crop(area),after.crop(area))).mean)
                                assert error<3,('same Campus not restored',renderer,args.testing,w,code,room,kind,error)
                                assert c.evaluate('JSON.stringify([...Object.keys(localStorage)].sort().map(k=>[k,localStorage[k]]))')==saved,'sign wrote saved state'
                        print(f'local sign browser: {renderer} testing={args.testing} {w}x{h} {code}: all3 mouse/touch/keyboard{"/semantic" if renderer=="dom" else ""}/dismiss/Back/save passed',flush=True)


if __name__=='__main__':main()

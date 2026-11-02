"""Normal-metadata testing build: visible rooms and all browser input paths."""
import argparse
import json
from pathlib import Path
import time
from PIL import ImageChops, ImageStat
from book_media_start_web_test import browser, serve
from sign_policy_web_test import key, shot
from sign_policy_ui_test import text, WORK


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--web-root',type=Path,required=True)
    args=p.parse_args()
    assert json.loads((args.web_root/'version.json').read_text())['testingRooms']
    data=json.loads((args.web_root/'benchmark-catalog.json').read_text())['titleScenes']
    assert not any(h['id'].endswith('-policy-sign') for s in data['scenes'] for h in s['hotspots'])
    campus=str(next(i+1 for i,h in enumerate(data['scenes'][0]['hotspots']) if h['target']=='scene:campus'))
    with serve(args.web_root.resolve()) as url:
        for renderer in ('canvas','dom'):
            with browser() as c:
                c.key=lambda value:key(c,value)
                c.call('Page.navigate',url=url+'/'+renderer+'.html')
                c.until('document.getElementById("loading").style.display==="none"','startup');time.sleep(1)
                for w,h in ((960,600),(420,900)):
                    c.call('Emulation.setDeviceMetricsOverride',width=w,height=h,deviceScaleFactor=1,mobile=h>w)
                    c.call('Emulation.setTouchEmulationEnabled',enabled=True,maxTouchPoints=1)
                    def move():c.call('Input.dispatchMouseEvent',type='mouseMoved',x=w-8,y=100)
                    def touch(x,y):
                        c.call('Input.dispatchTouchEvent',type='touchStart',touchPoints=[dict(x=x,y=y,id=1)])
                        time.sleep(.1);c.call('Input.dispatchTouchEvent',type='touchEnd',touchPoints=[]);time.sleep(.12)
                    for room,letter in enumerate(('b','f','d')):
                        for kind in ['mouse','touch','keyboard']+(['semantic'] if renderer=='dom' else []):
                            c.key('Home');c.key(campus);move();time.sleep(.5);before=shot(c)
                            words=text(before.crop((8,h-94,w-8,h-62)).resize((2*(w-16),64)),f'web-normal-strip-{renderer}-{w}')
                            assert 'Testing rooms' in words,words
                            if kind=='keyboard':c.key(letter)
                            elif kind=='semantic':
                                label=json.dumps(('Beach','Farm','Desert')[room])
                                c.evaluate('window.normalRoom=[...document.querySelectorAll("#kryon-dom-root button")].find(e=>e.getAttribute("aria-label")==='+label+');normalRoom.click();normalRoom.click()')
                            else:
                                x,y=12+(room+.5)*(w-24)/3,h-38
                                if kind=='touch':touch(x,y)
                                else:
                                    c.call('Input.dispatchMouseEvent',type='mouseMoved',x=x,y=y);c.click(x,y)
                            time.sleep(.4);opened=shot(c)
                            if room:assert 'testing preview' in text(opened,f'web-normal-{renderer}-{w}-{room}-{kind}').casefold()
                            else:assert max(ImageStat.Stat(ImageChops.difference(before,opened)).mean)>15
                            if room and kind in ('mouse','touch'):(touch if kind=='touch' else c.click)(24,26)
                            else:c.key('Escape')
                            move();time.sleep(.35);after=shot(c);area=(12,80,w-12,h-100)
                            error=max(ImageStat.Stat(ImageChops.difference(before.crop(area),after.crop(area))).mean)
                            if error>=3:
                                before.save(WORK/'normal-web-before.png');after.save(WORK/'normal-web-after.png')
                            assert error<3,(renderer,w,room,kind,error)
                    print(f'local normal-metadata browser rooms: {renderer} {w}x{h}, all3 mouse/touch/keyboard{"/semantic" if renderer=="dom" else ""}/Back passed',flush=True)


if __name__=='__main__':main()

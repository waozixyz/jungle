"""Actual development-room controls with unchanged production metadata."""
import argparse
import json
from pathlib import Path
import tempfile
import time
import unicodedata
from PIL import ImageChops, ImageStat
import runtime_test
from runtime_test import Desktop, ROOT, title_unit, run
from sign_policy_ui_test import WORK, text, saves, PREVIEW


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--testing',action='store_true')
    parser.add_argument('--bar-smoke',action='store_true')
    args=parser.parse_args();WORK.mkdir(parents=True,exist_ok=True)
    if args.bar_smoke and not args.testing:parser.error('--bar-smoke requires --testing')
    runtime_test.OUTPUT=WORK/'normal-native-proof'
    data=json.loads((ROOT/'tools/title_hotspots.json').read_text())
    home=data['scenes'][0]
    campus_key=str(next(i+1 for i,h in enumerate(home['hotspots']) if h['target']=='scene:campus'))
    with tempfile.TemporaryDirectory(prefix='normal-',dir=WORK) as temporary:
        saved=Path(temporary);(saved/'preserved-save.txt').write_text('normal-metadata-save')
        with Desktop(ROOT/'build/tests/title-host/jungle',saved,screen_size='1280x1100') as d:
            for w,h in ((960,600),(420,900)):
                d.resize(w,h)
                for lang in range(1 if args.bar_smoke else 3):
                    d.key('Home');unit=title_unit(w,h)
                    d.click_actual(round((21+34*lang)*unit),round(17*unit))
                    for room,letter in enumerate(('b','f','d')):
                        if args.bar_smoke and room==0:continue
                        for kind in ('pointer','keyboard') if args.testing else ('keyboard',):
                            d.key('Home');d.key(campus_key)
                            run(['xdotool','mousemove','--window',d.window,str(w-8),'100'],d.env)
                            time.sleep(.3);before=d.capture_actual('normal-campus');state=saves(saved)
                            if room==0:
                                words=text(before.crop((8,h-94,w-8,h-62)).resize((2*(w-16),64)),f'normal-controls-{args.testing}-{w}-{lang}')
                                label=('Testing rooms','Testräume','Salas de prueba')[lang]
                                plain=lambda value:''.join(c for c in unicodedata.normalize('NFKD',value.casefold()) if not unicodedata.combining(c))
                                assert (plain(label) in plain(words)) == args.testing,words
                            if kind=='pointer':d.click_actual(round(12+(room+.5)*(w-24)/3),h-38)
                            else:d.key(letter)
                            time.sleep(.3);current=d.capture_actual('normal-room')
                            if args.testing:
                                words=text(current,f'normal-native-{w}-{lang}-{room}-{kind}')
                                if room:assert PREVIEW[lang].casefold() in words.casefold(),words
                                else:assert max(ImageStat.Stat(ImageChops.difference(before,current)).mean)>15
                                if args.bar_smoke:
                                    if kind=='pointer':d.click_actual(w-34,28)
                                    else:d.key('F10')
                                    muted=saves(saved)
                                    sound=next(k for k in muted if Path(k).name=='sound.txt')
                                    assert muted[sound]==b'off\n'
                                    if kind=='pointer':d.click_actual(w-34,28)
                                    else:d.key('F10')
                                    assert saves(saved)[sound]==b'quiet\n'
                                    state[sound]=b'quiet\n'
                                if room and kind=='pointer':d.click_actual(24,26)
                                else:d.key('Escape')
                                run(['xdotool','mousemove','--window',d.window,str(w-8),'100'],d.env)
                                time.sleep(.3);current=d.capture_actual('normal-campus-return')
                            area=(12,80,w-12,h-100)
                            assert max(ImageStat.Stat(ImageChops.difference(before.crop(area),current.crop(area))).mean)<3,(args.testing,w,lang,room,kind)
                            assert saves(saved)==state
                    print(f'local normal-metadata rooms: testing={args.testing} {w}x{h} locale={lang}: all3 {"buttons/shortcuts/Back/save" if args.testing else "shortcuts ignored/controls absent/save"} passed',flush=True)


if __name__=='__main__':main()

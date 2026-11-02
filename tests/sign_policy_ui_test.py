"""Release/testing sign routes on an owned, scrubbed private Xvfb."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from PIL import ImageChops, ImageStat
import runtime_test
from runtime_test import Desktop, ROOT, run, title_unit
from sign_policy_fixture import fixture
from title_waterfront_ui_test import mapping

WORK = ROOT/'work/sign-policy'
DATA = fixture()
NOTICE = ('implemented', 'implementiert', 'implementado')
PREVIEW = ('testing preview', 'Testvorschau', 'prueba')


def text(picture, name):
    path = WORK/(name+'.png')
    picture.save(path)
    return subprocess.check_output(['tesseract', str(path), 'stdout', '--psm', '11'],
                                   stderr=subprocess.DEVNULL, text=True)


def saves(directory):
    return {str(p.relative_to(directory)):p.read_bytes() for p in directory.rglob('*') if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--testing', action='store_true')
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    runtime_test.OUTPUT = WORK/'native-proof'
    with tempfile.TemporaryDirectory(prefix='native-', dir=WORK) as temporary:
        data = Path(temporary)
        # Unrelated working/saved pictures and game state must survive notices.
        (data/'preserved-save.txt').write_text('owner-save-sentinel')
        with Desktop(ROOT/'build/tests/title-host/jungle', data, screen_size='1280x1100') as d:
            for w,h in ((960,600),(420,900)):
                d.resize(w,h)
                for lang in range(3):
                    d.key('Home')
                    unit = title_unit(w,h)
                    d.click_actual(round((21+34*lang)*unit), round(17*unit))
                    home = DATA['scenes'][0]
                    d.key(str(next(i+1 for i,t in enumerate(home['hotspots']) if t['target']=='scene:campus')))
                    base = next(s for s in DATA['scenes'] if s['name']=='campus')
                    campus = base['portrait'] if h>w else base
                    scale, ox, oy = mapping(campus,w,h)
                    for room,sign in enumerate(campus['hotspots'][-3:]):
                        x,y,_,_ = sign['glow_rect']
                        point = round(ox+(x+90)*scale), round(oy+(y+50)*scale)
                        # Move to the same neutral location for comparable pixels.
                        run(['xdotool','mousemove','--window',d.window,str(w-8),str(h-8)],d.env)
                        time.sleep(.2)
                        before = d.capture_actual('campus-before')
                        saved = saves(data)
                        for input_kind in ('pointer','keyboard'):
                            d.key('Home')
                            d.key(str(next(i+1 for i,t in enumerate(home['hotspots']) if t['target']=='scene:campus')))
                            run(['xdotool','mousemove','--window',d.window,str(w-8),str(h-8)],d.env)
                            time.sleep(.3)
                            before = d.capture_actual('campus-before')
                            centered = before
                            saved = saves(data)
                            if input_kind == 'pointer':
                                d.click_actual(*point);time.sleep(.4)
                            else:
                                # All three signs are reachable through reading order,
                                # including entries beyond the numeric shortcuts.
                                for _ in range(len(campus['hotspots'])-3+room+1):d.key('Right')
                                before = d.capture_actual('campus-before-activation')
                                d.key('Return');time.sleep(.35)
                            current = d.capture_actual(f'{args.testing}-{w}-{lang}-{room}-{input_kind}')
                            words = text(current, f'native-{args.testing}-{w}-{lang}-{room}-{input_kind}')
                            if args.testing:
                                if room:
                                    assert PREVIEW[lang].casefold() in words.casefold(), words
                                else:
                                    assert max(ImageStat.Stat(ImageChops.difference(before,current)).mean)>15,'Beach did not open'
                                if room and input_kind == 'pointer': d.click_actual(24,26)
                                else: d.key('Escape')
                                if room == 0: before = centered
                            else:
                                assert NOTICE[lang] in words.casefold(), words
                                # These shortcuts must not navigate behind the shared modal.
                                d.key('Home');d.key('1');d.key('F10')
                                if input_kind == 'pointer': d.click_actual(w//2,h//2+40)
                                else: d.key('Escape')
                            run(['xdotool','mousemove','--window',d.window,str(w-8),str(h-8)],d.env)
                            time.sleep(.35)
                            after = d.capture_actual('campus-after')
                            area = (12,80,w-12,h-12)
                            error = max(ImageStat.Stat(ImageChops.difference(before.crop(area),after.crop(area))).mean)
                            assert error<3, ('did not return same Campus',args.testing,w,lang,room,input_kind,error)
                            assert saves(data)==saved, 'sign navigation changed saved state'
                    print(f'local sign native: testing={args.testing} {w}x{h} locale={lang}: all3 pointer/keyboard/dismiss/Back/save passed',flush=True)


if __name__=='__main__':main()

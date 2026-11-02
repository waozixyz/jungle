"""Focused private-Xvfb proof of flight landing and the former paper's route.
Uses the same stable test host and fully staged game bundles as the title suite.
"""
import json
import os
from pathlib import Path
import tempfile
import time
import numpy as np
from PIL import Image
import runtime_test
from runtime_test import ROOT, Desktop, run, title_unit
from title_paper_ui_test import enter, paper, background, error, collected


def capture(d, path):
    d.verify_server()
    d.alive()
    run(['import', '-display', d.env['DISPLAY'], '-window', d.window, str(path)], d.env)
    return Image.open(path).convert('RGB')


def main():
    work = ROOT/'work/title-layer-routes'
    work.mkdir(parents=True, exist_ok=True)
    runtime_test.OUTPUT = work/'captures'
    runtime_test.OUTPUT.mkdir(exist_ok=True)
    binary = Path(os.environ.get('JUNGLE_TEST_BINARY', ROOT/'build/app/jungle'))
    evidence = []
    for w, h in ((960, 600), (420, 900)):
        with tempfile.TemporaryDirectory(prefix='ui-', dir=work) as temporary:
            data = Path(temporary)
            (data/'guide-seen.txt').write_text('yes')
            with Desktop(binary, data, screen_size='1280x1100') as d:
                d.resize(w, h)
                enter(d, 'bookshelf')
                slug, x, y, edge = paper('bookshelf', w, h)
                run(['xdotool', 'mousemove', '--window', d.window, str(round(x+edge*.32)), str(y)], d.env)
                run(['xdotool', 'mousedown', '1'], d.env)
                start = time.monotonic()
                run(['xdotool', 'mouseup', '1'], d.env)
                # Observe an actual late flight, rather than inferring its
                # target from source code or a successful collection write.
                frames = []
                for at in (.62, .70, .78, .84, .89, .95, 1.01):
                    remaining = at-(time.monotonic()-start)
                    if remaining > 0:
                        time.sleep(remaining)
                    path = runtime_test.OUTPUT/f'flight-{w}-{round(at*100)}.png'
                    frames.append((time.monotonic()-start, capture(d,path), path))
                time.sleep(.2)
                done = capture(d, runtime_test.OUTPUT/f'flight-complete-{w}.png')
                assert collected(data) == [slug]
                unit = title_unit(w, h)
                cx, cy = w-51*unit, 17*unit
                candidates=[]
                b=np.asarray(done).astype(int)
                for elapsed, frame, path in frames:
                    a=np.asarray(frame).astype(int)
                    white=(a.min(axis=2)>235) & (np.abs(a-b).max(axis=2)>20)
                    yy,xx=np.indices(white.shape)
                    white &= (abs(xx-cx)<75) & (abs(yy-cy)<80)
                    py,px=np.where(white)
                    if len(px)>12:
                        center=[float(px.mean()),float(py.mean())]
                        candidates.append((abs(center[0]-cx)+abs(center[1]-cy),elapsed,center,path))
                assert candidates, ('late flight not visible near collection button',w)
                distance,elapsed,center,path=min(candidates)
                assert distance<25, ('flight missed compact collection button',w,center,(cx,cy))
                evidence.append(dict(size=[w,h],elapsed=elapsed,flight_center=center,button_center=[cx,cy],capture=str(path.relative_to(ROOT))))
                # The former hidden paper center lies behind the tiger book,
                # whose Picture Book hotspot receives taps after collection.
                d.click_actual(x, y)
                time.sleep(1.3)
                opened = d.capture_actual(f'underlying-picture-book-{w}')
                expected = background('bookshelf', w, h)
                assert error(opened, expected, (20,80,w-20,h-30))>20, ('underlying game did not open',w)
                # Native shared TitleBar returns from the hosted game.
                d.key('Escape')
                time.sleep(.6)
                returned = d.capture_actual(f'underlying-route-return-{w}')
                assert error(returned, expected, (20,80,w-20,h-30))<12, ('Back did not restore scene',w)
                assert collected(data)==[slug]
                print(f'local layered title route: {w}x{h} actual flight lands at compact button; collected paper exposes Picture Book route and Back',flush=True)
    (work/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')


if __name__=='__main__':
    main()

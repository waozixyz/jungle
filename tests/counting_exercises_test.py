#!/usr/bin/env python3
"""Focused model + real private host tests; no reimplementation of exercise RNG."""
from pathlib import Path
import subprocess
import tempfile
import time
import runtime_test as rt
from drums_playground_test import PROBE

rt.OUTPUT = rt.ROOT / 'backup/counting-exercises-ui'


def main():
    subprocess.run(['make', '-j1', 'build/tests/counting_exercises', 'build/tests/counting',
                    'build/app/jungle', 'build/app/games/animal-count.zx'], cwd=rt.ROOT, check=True)
    for name in ('counting_exercises', 'counting'):
        subprocess.run([str(rt.ROOT/'build/tests'/name)], check=True, env=rt.environment())
    scratch = rt.ROOT/'work/counting-exercises'
    scratch.mkdir(parents=True, exist_ok=True)
    source=scratch/'audio_probe.c'; library=scratch/'audio_probe.so'
    source.write_text(PROBE)
    subprocess.run(['cc','-shared','-fPIC','-O2',str(source),'-ldl','-o',str(library)],check=True)
    with tempfile.TemporaryDirectory(dir=scratch) as temporary:
        for lang in ('en', 'de', 'es'):
            data = Path(temporary)/lang
            savedir = data/'games/jungle.animals'
            savedir.mkdir(parents=True)
            (data/'language.txt').write_text(lang)
            progress = savedir/'progress.txt'
            settings = savedir/'counting-options.txt'
            original = 'animal 7 123 4 2\n'
            progress.write_text(original)
            settings.write_text('counting1 99 999\n')
            queued=data/'queued-audio.txt';queued.touch()
            audio_env={'LD_PRELOAD':str(library),'JUNGLE_TEST_AUDIO_QUEUE':str(queued)}
            def audio_lines(): return queued.read_text().splitlines()
            with rt.Desktop(rt.ROOT/'build/app/jungle', data, extra_env=audio_env, screen_size='1100x1000') as d:
                d.game('Animal Counting')
                d.resize(960,656)
                d.capture('lessons-'+lang, header=56)
                before_audio=len(audio_lines());d.key('1')
                d.capture('auto-'+lang,header=56)
                assert len(audio_lines())==before_audio,'lesson start repeated the generic question'
                assert progress.read_text() == original, 'opening changed legacy progress'
                def lesson(number):
                    d.key('Escape');d.capture('lessons-'+lang,header=56)
                    before_audio=len(audio_lines());d.key(str(number));d.capture('lesson-start-'+lang,header=56)
                    assert len(audio_lines())==before_audio,'lesson picker spoke a generic question'
                def options(mode,limit):
                    assert settings.read_text() == f'counting1 {mode} {limit}\n'
                def solve(limit, touch=False):
                    before = int(progress.read_text().split()[2])
                    before_picture = d.capture_actual(f'{lang}-before-answer')
                    assert len(before_picture.getcolors(1000000)) > 100, 'missing watercolor picture rendering'
                    for value in range(limit+1):
                        if touch:
                            # Portrait keypad, actual touch events including zero.
                            for digit in str(value):
                                index = int(digit)-1 if digit!='0' else 10
                                d.click_actual(round((24+(index%3)*92+44)*d.ps), round(d.pt+(350+(index//3)*40+17)*d.ps))
                            d.click_actual(round(24+2*92+44)*d.ps, round(d.pt+(350+3*40+17)*d.ps))
                        else:
                            for digit in str(value): d.key(digit)
                            before_audio=len(audio_lines())
                            d.key('Return')
                        if int(progress.read_text().split()[2]) == before+1:
                            if not touch:
                                expected=1+int((before+1)%8==0)+int(value==0)
                                assert len(audio_lines())-before_audio==expected,('unexpected narration after answer',lang,value,audio_lines()[before_audio:])
                            assert progress.read_text().split()[1::2] == ['7','4'], 'fixed mode changed Auto ladder'
                            assert progress.read_text().split()[4] == '2'
                            time.sleep(1.6)  # allow the existing reward page to finish
                            return value
                    raise AssertionError('no answer in selected bound accepted')
                for r,limit in enumerate((5,10,20),1):
                    lesson(r+1)
                    options(0,limit)
                    d.capture(f'{lang}-range-{limit}', header=56)
                    d.key('2');d.key('1');d.key('Return')
                    assert int(progress.read_text().split()[2]) == 123+r-1, 'out-of-range answer accepted'
                    solve(limit)
                lesson(2); options(0,5)
                for extra in range(6): solve(5)
                lesson(4); options(0,20)
                for mode in (1,2):
                    lesson(4+mode)
                    options(mode,20)
                    d.capture(f'{lang}-math-{mode}', header=56)
                    result = solve(5)
                    if mode == 2:
                        for attempt in range(20):
                            if result == 0: break
                            result = solve(5)
                        assert result == 0, 'subtraction never presented a zero answer'
                # Reopen the activity and app, retaining both math and remembered range.
                d.key('Escape');d.key('Escape');d.game('Animal Counting')
                d.capture('reopened-lessons-'+lang,header=56);d.key('Return')
                options(2,20)
                d.resize(320,596)
                d.ps = 1.0; d.pt = 56
                d.capture_actual(f'{lang}-portrait')
                result = solve(5, touch=True)
                for attempt in range(20):
                    if result == 0: break
                    result = solve(5, touch=True)
                assert result == 0, 'zero touch answer was not accepted'
                # Shared sound control continues to save in the owner's normal format.
                d.click_actual(292,28)
                assert (data/'sound.txt').read_text().strip() == 'off'
                d.click_actual(292,28)
                d.key('Escape');d.key('Escape')
            with rt.Desktop(rt.ROOT/'build/app/jungle',data,screen_size='1100x1000') as d:
                d.game('Animal Counting'); options(2,20)
                d.resize(960,656)
                d.capture(f'{lang}-reopen',header=56)
                d.key('4');options(0,20)
                d.capture(f'{lang}-count-restored',header=56)
                # Select Auto; old saved level/streaks survived every fixed exercise.
                d.key('Escape');d.key('1');options(0,0)
                d.key('Escape');d.key('Escape')
                fields=progress.read_text().split()
                assert fields[1]=='7' and fields[3:]==['4','2']
            print(f'local counting UI: {lang} six lesson cards, no repeated prompt audio, math, keyboard/touch, legacy ladder and reopen passed',flush=True)
    print('local counting exercises tests passed',flush=True)

if __name__ == '__main__': main()

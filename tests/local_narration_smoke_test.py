"""Play translated narration through SDL on owned private Xvfb displays."""
from array import array
from pathlib import Path
import tempfile
import time

import runtime_test as rt


def main():
    scratch = rt.run_folder('work/qwen-narration/smoke')
    rt.OUTPUT = scratch / 'captures'
    for language in ('de', 'es'):
        for width, height in ((960, 640), (540, 900)):
            with tempfile.TemporaryDirectory(dir=scratch) as folder:
                state = Path(folder)
                (state / 'language.txt').write_text(language)
                (state / 'guide-seen.txt').write_text('yes\n')
                audio = state / 'sdl.pcm'
                native = state / 'native'
                native.mkdir()
                with rt.Desktop(rt.ROOT / 'build/app/jungle', state,
                                extra_env={'SDL_AUDIODRIVER': 'disk',
                                           'SDL_DISKAUDIOFILE': str(audio),
                                           'TMPDIR': str(state), 'ZIRAN_NATIVE_DIR': str(native)},
                                screen_size='1280x1000') as desktop:
                    desktop.resize(width, height)

                    def heard(label, key='Right'):
                        time.sleep(.6)
                        with (rt.OUTPUT / 'jungle.log').open('rb') as stream:
                            stream.seek(max(0, (rt.OUTPUT / 'jungle.log').stat().st_size - 8192))
                            log = stream.read(8192).decode(errors='replace')
                        assert 'cannot run natively' not in log, log[-2000:]
                        # Read only the new bounded span of the private SDL sink.
                        start = audio.stat().st_size if audio.exists() else 0
                        desktop.key(key)
                        deadline = time.monotonic() + 15
                        while time.monotonic() < deadline:
                            time.sleep(.25)
                            if audio.exists():
                                with audio.open('rb') as stream:
                                    stream.seek(start)
                                    samples = array('h', stream.read(22050 * 2 * 8))
                                if sum(abs(sample) > 180 for sample in samples) > 220:
                                    print(f'local SDL playback: {language} {width}x{height} {label}', flush=True)
                                    desktop.capture_actual(f'{language}-{width}-{label}')
                                    return
                            desktop.alive()
                        desktop.capture_actual(f'failed-{language}-{label}')
                        raise AssertionError(f'No audible SDL output: {language} {label}')

                    for game in ('ABC Book', '123 Book'):
                        desktop.game(game)
                        heard(game)
                        desktop.key('Escape')
                        desktop.key('Escape')
                    desktop.game('Picture Book')
                    desktop.key('2')
                    heard('Picture Book')
                    desktop.key('Escape')
                    desktop.key('Escape')
                    desktop.game('Sweet Porridge')
                    desktop.key('1')
                    heard('Sweet Porridge')
                    desktop.key('Escape')
                    desktop.key('2')
                    heard('Town Musicians of Bremen')
    print('local Qwen app smoke passed: DE/ES, five activities, both orientations, audible SDL output')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Animal Counting's full viewport, approved assets and keypad on owned Xvfb."""
from pathlib import Path
import tempfile
import time

from PIL import Image
import runtime_test as rt

WORK = rt.ROOT / 'work/counting-portrait'
PAPER = (227, 236, 228)


def background(picture):
    width, height = picture.size
    # These include the middle side strips left by the old 320x200 canvas,
    # plus top/bottom letterboxing on taller phones and landscape windows.
    for x in (0, width - 1):
        assert all(picture.getpixel((x, y)) == PAPER for y in range(57, height)), 'activity margin is not gentle paper'
    assert not any(max(pixel) < 8 for pixel in picture.crop((0, 56, width, height)).getdata()), 'black canvas remains'


def assets():
    manifest = rt.ROOT / 'build/app/assets/shared-assets.txt'
    aliases = dict(line.split('|')[1:] for line in manifest.read_text().splitlines() if line.startswith('alias|'))
    names = ('tiger frog butterfly ladybug snail elephant giraffe monkey panda '
             'lion zebra crocodile parrot toucan rabbit cat dog sheep').split()
    for name in names:
        logical = f'assets/animal-count/pictures/{name}.png'
        target = rt.ROOT / 'build/app' / aliases.get(logical, logical)
        with Image.open(target) as picture:
            assert picture.size == (128, 128) and picture.mode == 'RGBA', target
            assert picture.getchannel('A').getextrema() == (0, 255), target
    print('local counting assets: all 18 shipped aliases resolve to transparent 128px pictures', flush=True)


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    rt.OUTPUT = WORK / 'after'
    assets()
    for lang in ('en', 'de', 'es'):
        with tempfile.TemporaryDirectory(dir=WORK) as temporary:
            data = Path(temporary)
            (data / 'language.txt').write_text(lang)
            (data / 'sound.txt').write_text('off\n')
            saved = data / 'games/jungle.animals/progress.txt'
            saved.parent.mkdir(parents=True)
            saved.write_text('animal 1 7 0 0\n')
            with rt.Desktop(rt.ROOT / 'build/app/jungle', data, screen_size='1100x1100') as desktop:
                desktop.game('Animal Counting')
                for width, height in ((400, 656), (400, 956), (960, 656)):
                    desktop.resize(width, height)
                    background(desktop.capture_actual(f'{lang}-lessons-{width}x{height}'))
                desktop.resize(400, 656)
                desktop.key('1')
                for width, height in ((400, 656), (400, 956), (960, 656)):
                    desktop.resize(width, height)
                    picture = desktop.capture_actual(f'{lang}-count-{width}x{height}')
                    background(picture)
                    portrait = height - 56 > width
                    scale = min(width / 320, (height - 56) / (540 if portrait else 200))
                    left = (width - 320 * scale) / 2
                    top = 56 + (height - 56 - (540 if portrait else 200) * scale) / 2
                    area = (20, 64, 300, 300) if portrait else (20, 55, 210, 155)
                    animals = picture.crop(tuple(round(v) for v in (left + area[0]*scale, top + area[1]*scale, left + area[2]*scale, top + area[3]*scale)))
                    # Frame/text sit outside this crop; group cards are pale.
                    assert sum(max(p) < 160 or max(p)-min(p) > 35 for p in animals.getdata()) > 50, 'animal pictures are missing'
                # Actual portrait taps solve the four-animal Auto range and
                # trigger its eighth-answer reward, using disposable saves.
                desktop.resize(400, 656)
                scale = 600 / 540
                left = (400 - 320 * scale) / 2
                def tap(index):
                    desktop.click_actual(round(left + (24 + index%3*92 + 44)*scale), round(56 + (350 + index//3*40 + 17)*scale))
                for value in range(1, 5):
                    tap(value - 1)
                    tap(11)
                    if int(saved.read_text().split()[2]) == 8:
                        break
                else:
                    raise AssertionError('portrait touch keypad did not accept the count')
                background(desktop.capture_actual(f'{lang}-reward-portrait'))
                time.sleep(1.6)
                desktop.resize(960, 656)
                background(desktop.capture_actual(f'{lang}-after-reward-landscape'))
            print(f'local counting portrait: {lang} picker/count/reward background, visible animals and touch answer passed', flush=True)


if __name__ == '__main__':
    main()

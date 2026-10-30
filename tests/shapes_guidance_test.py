#!/usr/bin/env python3
"""Guided sorting through the real host, owned Xvfb and disposable progress."""
from pathlib import Path
import subprocess
import tempfile
import time

from PIL import ImageChops
import runtime_test as rt


rt.OUTPUT = rt.ROOT / 'backup/shapes-guidance-ui'
ORIGINAL = 'shapes 1 0 0 0 0 0 0 0\n'
LEAF = (111, 159, 124)


def pixels(picture):
    return picture.get_flattened_data() if hasattr(picture, 'get_flattened_data') else picture.getdata()


def layout(width, height):
    """Two-piece first lesson; touch coordinates, independent of game rules."""
    height -= 56
    scale = min(width / 360, height / 640) if width <= height else min(height / 420, width / 720)
    scale = min(scale, 1.6)
    w, h = int(width / scale), int(height / scale)
    area_y, gap, margin = 118, 12, 14
    aw, ah = w - 28, h - area_y - margin
    if h >= w:
        tray = (margin, area_y, aw, ah * 42 // 100)
        region = (margin, area_y + tray[3] + gap * 2, aw, ah - tray[3] - gap * 2)
        tw = min((region[2] - gap) // 2, 240)
        th = min(region[3], tw * 3 // 2)
        homes = [(region[0] + (region[2] - tw * 2 - gap) // 2 + t * (tw + gap),
                  region[1] + (region[3] - th) // 2, tw, th) for t in range(2)]
    else:
        tray = (margin, area_y, (aw - gap * 2) * 52 // 100, ah)
        region = (tray[0] + tray[2] + gap * 2, area_y, aw - tray[2] - gap * 2, ah)
        tw, th = min(region[2], 420), min((region[3] - gap) // 2, 220)
        homes = [(region[0] + (region[2] - tw) // 2,
                  region[1] + (region[3] - th * 2 - gap) // 2 + t * (th + gap), tw, th) for t in range(2)]
    best, columns = 0, 1
    for cols in (1, 2):
        rows = (2 + cols - 1) // cols
        edge = min((tray[2] - gap * (cols - 1)) // cols, (tray[3] - gap * (rows - 1)) // rows)
        if edge > best:
            best, columns = edge, cols
    best = min(best, 150)
    rows = (2 + columns - 1) // columns
    cards = [(tray[0] + (tray[2] - best * columns - gap * (columns - 1)) // 2 + i % columns * (best + gap),
              tray[1] + (tray[3] - best * rows - gap * (rows - 1)) // 2 + i // columns * (best + gap), best, best) for i in range(2)]
    return scale, w, h, cards, homes


def shape(picture, colors):
    # Recognize what is actually drawn, without duplicating shuffle/target rules.
    from PIL import Image
    mask = Image.new('L', picture.size)
    mask.putdata([255 if color in colors else 0 for color in pixels(picture)])
    bounds = mask.getbbox()
    assert bounds, 'expected a visible sorting piece or hole'
    fitted = mask.crop(bounds)
    coverage = sum(pixels(fitted)) / (255 * fitted.width * fitted.height)
    return 'square' if coverage > .88 else 'circle' if coverage > .67 else 'triangle'


def exercise(language, size):
    with tempfile.TemporaryDirectory(prefix='jungle-shapes-guide-') as temporary:
        data = Path(temporary)
        (data / 'language.txt').write_text(language)
        (data / 'sound.txt').write_text('off\n')
        save = data / 'games/jungle.shapes/shapes.txt'
        save.parent.mkdir(parents=True)
        save.write_text(ORIGINAL)
        with rt.Desktop(rt.ROOT / 'build/app/jungle', data, screen_size='1280x1000') as d:
            d.resize(*size)
            d.game('Shapes & Sorting')
            scale, w, h, cards, homes = layout(*size)

            def crop(picture, box):
                x, y, width, height = box
                return picture.crop((round(x * scale), round(56 + y * scale),
                                     round((x + width) * scale), round(56 + (y + height) * scale)))

            def point(box):
                x, y, width, height = box
                return round((x + width / 2) * scale), round(56 + (y + height / 2) * scale)

            def tap(box):
                d.click_actual(*point(box))

            def screenshot(label):
                return d.capture_actual(f'{language}-{size[0]}-{label}')

            # Tap a piece to silence the demo, then identify both real shapes.
            tap(cards[0])
            still = screenshot('ready')
            kinds = [shape(crop(still, card), {LEAF}) for card in cards]
            targets = [shape(crop(still, home), {(181, 159, 124), (228, 216, 193)}) for home in homes]
            routes = [targets.index(kind) for kind in kinds]
            assert len(set(routes)) == 2, (kinds, targets)

            # Inactivity visibly moves a ghost. It cannot place even one piece.
            time.sleep(3.4)
            moving = screenshot('demo-source')
            time.sleep(.8)
            moved = screenshot('demo-route')
            difference = ImageChops.difference(moving, moved)
            assert difference.getbbox(), 'the idle demonstration did not animate'
            # The path must cross the empty space between the tray and homes.
            if h >= w:
                corridor = (14, 118 + (h - 132) * 42 // 100, w - 28, 24)
            else:
                corridor = (14 + (w - 52) * 52 // 100, 118, 24, h - 132)
            assert ImageChops.difference(crop(still, corridor), crop(moved, corridor)).getbbox(), 'no source-to-home trajectory'
            assert save.read_text() == ORIGINAL, 'watching changed persisted progress'

            button = min(84, (w - 76) // 5)
            left = (w - button * 5 - 48) // 2
            tap((left + 4 * (button + 12), 14, button, 60))
            screenshot('replay')
            d.key('Escape')
            assert save.read_text() == ORIGINAL, 'help or inactivity played the round'
            d.game('Shapes & Sorting')

            # Choose the other piece first. Tap then tap must work, including
            # after a harmless wrong-home try. No drag or reading is required.
            tap(cards[1])
            tap(homes[1 - routes[1]])
            # A miss replays the translucent ghost over this very piece.
            # Touch it to look underneath before testing its real silhouette.
            tap(cards[1])
            wrong = screenshot('gentle-hint')
            assert shape(crop(wrong, cards[1]), {LEAF}) == kinds[1], 'a miss removed the piece'
            tap(homes[routes[1]])
            placed = screenshot('tap-placed')
            assert LEAF not in set(pixels(crop(placed, cards[1]))), 'tap-then-home did not place the chosen piece'
            assert LEAF in set(pixels(crop(placed, homes[routes[1]]))), 'piece did not arrive in its matching home'

            # Drag the remaining piece using this test's private display only.
            start, end = point(cards[0]), point(homes[routes[0]])
            rt.run(['xdotool', 'mousemove', '--window', d.window, *map(str, start)], d.env)
            rt.run(['xdotool', 'mousedown', '1'], d.env)
            try:
                time.sleep(.15)
                rt.run(['xdotool', 'mousemove', '--sync', '--window', d.window, *map(str, end)], d.env)
                time.sleep(.2)
            finally:
                rt.run(['xdotool', 'mouseup', '1'], d.env)
            time.sleep(.3)
            screenshot('completed')
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and save.read_text().split()[8] == '0':
                d.alive()
                time.sleep(.15)
            assert save.read_text().split()[8] == '1', 'tap and drag did not finish exactly one round'
            assert save.read_text().split()[6] == '0', 'the demonstrated round hid the real wrong-home attempt'
            print(f'local shapes UI: {language} {size[0]}x{size[1]} demo, replay, tap, miss, drag, progress passed', flush=True)


def main():
    env = rt.environment()
    subprocess.run(['make', '-j1', 'build/tests/shapes', 'build/app/jungle',
                    'build/app/games/jungle-shapes.zx', 'build/app/games/catalog.txt'],
                   cwd=rt.ROOT, env=env, check=True)
    subprocess.run([str(rt.ROOT / 'build/tests/shapes')], env=env, check=True)
    print('local shapes model: guidance, progress, all modes/levels and route bounds passed', flush=True)
    for language in ('en', 'de', 'es'):
        for size in ((360, 696), (960, 600)):
            exercise(language, size)


if __name__ == '__main__':
    main()

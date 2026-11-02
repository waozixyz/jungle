"""Hidden title papers on an owned private Xvfb, never the desktop: each original
scene shows one glowing paper in landscape and portrait, hovering it lights no
item, a tap collects its empty scene once without opening anything, and the
paper stays gone, also after a restart."""
import json
import os
from pathlib import Path
import tempfile
import time
from PIL import Image, ImageChops, ImageStat
import runtime_test
from runtime_test import Desktop, ROOT, run

DATA = json.loads((ROOT/'tools/title_hotspots.json').read_text())
REGISTRY = json.loads((ROOT/'tools/collectibles.json').read_text())['collectibles']
SCENES = ('treehouse', 'bookshelf', 'campus')


def scene(name, w, h):
    base = next(s for s in DATA['scenes'] if s['name'] == name)
    return base.get('portrait', base) if h > w else base


def mapping(s, w, h):
    with Image.open(ROOT/s['image']) as source:
        sw, sh = source.size
    scale = max(w/sw, h/sh)
    return scale, (w-sw*scale)/2, (h-sh*scale)/2, sw, sh


def paper(name, w, h):
    """The paper's middle and edge in window pixels, as TitlePaperSpot places it."""
    entry = next(e for e in REGISTRY if e['source'] == {'kind': 'title', 'scene': name})
    spot = entry['how']['portrait'] if h > w else entry['how']
    scale, ox, oy, sw, sh = mapping(scene(name, w, h), w, h)
    edge = min(64, max(28, min(w, h)*0.07))
    return entry['slug'], round(ox+spot['x']*sw*scale), round(oy+spot['y']*sh*scale), edge


def background(name, w, h):
    s = scene(name, w, h)
    scale, ox, oy, _, _ = mapping(s, w, h)
    source = Image.open(ROOT/s['image']).convert('RGB')
    expected = source.resize((round(source.width*scale), round(source.height*scale)), Image.Resampling.BILINEAR)
    return expected.crop((-round(ox), -round(oy), w-round(ox), h-round(oy)))


def error(a, b, area):
    return max(ImageStat.Stat(ImageChops.difference(a.crop(area), b.crop(area))).mean)


def box(x, y, edge):
    reach = round(edge*1.2)
    return (x-reach, y-reach, x+reach, y+reach)


def move(d, x, y):
    run(['xdotool', 'mousemove', '--window', d.window, str(x), str(y)], d.env)
    time.sleep(.6)


def away(d, w, h):
    move(d, w//2, h-6)


def enter(d, name):
    d.key('Home')
    if name != 'treehouse':
        home = DATA['scenes'][0]
        d.key(str(next(i+1 for i, t in enumerate(home['hotspots']) if t['target'] == 'scene:'+name)))
    time.sleep(.8)


def collected(data):
    path = data/'collection.txt'
    return path.read_text().splitlines()[1:] if path.exists() else []


def check_scene(d, name, w, h, label):
    """The scene shown is NAME's painting (no item opened, no other scene)."""
    actual = d.capture_actual(f'paper-{label}-{name}-{w}')
    expected = background(name, w, h)
    assert error(actual, expected, (20, 80, w-20, h-30)) < 12, (name, w, h, label, 'wrong scene')
    return actual, expected


def main():
    work = ROOT/'work/title-paper-ui'
    work.mkdir(parents=True, exist_ok=True)
    captures = work/'captures'
    captures.mkdir(exist_ok=True)
    runtime_test.OUTPUT = captures
    binary = Path(os.environ.get('JUNGLE_TEST_BINARY', ROOT/'build/app/jungle'))
    try:
        for w, h in ((960, 600), (420, 900)):
            with tempfile.TemporaryDirectory(prefix='ui-', dir=work) as temporary:
                data = Path(temporary)
                (data/'guide-seen.txt').write_text('yes')
                with Desktop(binary, data, screen_size='1280x1100') as d:
                    d.resize(w, h)
                    earned = []
                    for name in SCENES:
                        enter(d, name)
                        slug, x, y, edge = paper(name, w, h)
                        area = box(x, y, edge)
                        away(d, w, h)
                        rest, expected = check_scene(d, name, w, h, 'rest')
                        shown = error(rest, expected, area)
                        assert shown > 8, (name, w, h, 'paper not visible', shown)
                        # Hovering the paper lights no painted item: outside the
                        # paper, the frame is unchanged.
                        move(d, x, y)
                        hovered = d.capture_actual(f'paper-hover-{name}-{w}')
                        masked_rest, masked_hover = rest.copy(), hovered.copy()
                        for image in (masked_rest, masked_hover):
                            image.paste((0, 0, 0), area)
                        changed = ImageChops.difference(masked_rest, masked_hover).getbbox()
                        assert changed is None, (name, w, h, 'hovering the paper changed the scene', changed)
                        # A tap collects it once; nothing opens and the scene stays.
                        d.click_actual(x, y)
                        earned.append(slug)
                        assert collected(data) == earned, (name, w, h, collected(data))
                        time.sleep(1.5)
                        away(d, w, h)
                        after, expected = check_scene(d, name, w, h, 'collected')
                        gone = error(after, expected, area)
                        assert gone < shown/2 and gone < 10, (name, w, h, 'paper still shown', shown, gone)
                        # Tapping the empty spot again collects nothing more.
                        d.click_actual(x, y)
                        assert collected(data) == earned, (name, w, h, 'collected twice')
                        check_scene(d, name, w, h, 'again')
                # The collection survives a restart and no paper comes back.
                with Desktop(binary, data, screen_size='1280x1100') as d:
                    d.resize(w, h)
                    for name in SCENES:
                        enter(d, name)
                        _, x, y, edge = paper(name, w, h)
                        away(d, w, h)
                        actual, expected = check_scene(d, name, w, h, 'restart')
                        assert error(actual, expected, box(x, y, edge)) < 10, (name, w, h, 'paper came back')
                assert collected(data) == [paper(n, w, h)[0] for n in SCENES]
            print(f'local title paper UI: {w}x{h} treehouse/bookshelf/campus shown, hover inert, '
                  'tap collects once without navigating, gone after restart', flush=True)
    finally:
        # The owner judges visuals. Remove owned verification pixels.
        for capture in captures.glob('*.png'):
            capture.unlink()


if __name__ == '__main__':
    main()

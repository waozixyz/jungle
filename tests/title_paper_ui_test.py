"""Actual title layers on an owned private Xvfb: a small paper peek smoothly
reveals on hover, stays under the foreground, collects once and persists.
Full-scene idle/hover evidence stays under the ignored project work folder.
"""
import json
import os
from pathlib import Path
import tempfile
import time
from PIL import Image, ImageChops, ImageStat
import numpy as np
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
    s = scene(name, w, h)
    scale, ox, oy, sw, sh = mapping(s, w, h)
    x, y, edge, travel = s['paper']
    return entry['slug'], round(ox+x*scale), round(oy+y*scale), edge*scale


def background(name, w, h):
    s = scene(name, w, h)
    scale, ox, oy, _, _ = mapping(s, w, h)
    source = Image.open(ROOT/s['background']).convert('RGBA')
    for hotspot in s['hotspots']:
        if hotspot.get('rest'):
            source.alpha_composite(Image.open(ROOT/hotspot['rest']).convert('RGBA'),
                                   tuple(hotspot['glow_rect'][:2]))
    source.alpha_composite(Image.open(ROOT/s['foreground']).convert('RGBA'))
    source = source.convert('RGB')
    expected = source.resize((round(source.width*scale), round(source.height*scale)), Image.Resampling.BILINEAR)
    return expected.crop((-round(ox), -round(oy), w-round(ox), h-round(oy)))


def error(a, b, area):
    return max(ImageStat.Stat(ImageChops.difference(a.crop(area), b.crop(area))).mean)


def box(x, y, edge):
    reach = round(edge*1.6)
    return (x-reach, y-reach, x+reach, y+reach)


def white_paper(actual, expected, area):
    shown = np.asarray(actual.crop(area)).astype(int)
    plain = np.asarray(expected.crop(area)).astype(int)
    return int(((shown.min(axis=2) > 230) &
                (np.abs(shown-plain).max(axis=2) > 22)).sum())


def foreground_mask(name, w, h):
    s = scene(name, w, h)
    scale, ox, oy, _, _ = mapping(s, w, h)
    alpha = Image.open(ROOT/s['foreground']).getchannel('A')
    alpha = alpha.resize((round(alpha.width*scale), round(alpha.height*scale)), Image.Resampling.BILINEAR)
    alpha = alpha.crop((-round(ox), -round(oy), w-round(ox), h-round(oy)))
    from PIL import ImageFilter
    return alpha.point(lambda a: 255 if a > 250 else 0).filter(ImageFilter.MinFilter(5))


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
                    shown = white_paper(rest, expected, area)
                    assert shown > 3, (name, w, h, 'paper peek not visible', shown)
                    assert shown < edge*edge*.4, (name, w, h, 'idle paper too exposed', shown)
                    # Hovering the paper lights no painted item: outside the
                    # paper, the frame is unchanged.
                    move(d, round(x+edge*.32), y)
                    hovered = d.capture_actual(f'paper-hover-{name}-{w}')
                    revealed = white_paper(hovered, expected, area)
                    assert revealed > shown*1.35, (name, w, h, 'hover did not reveal paper', shown, revealed)
                    print(f'local paper pixels {name} {w}x{h}: idle={shown}, hover={revealed}', flush=True)
                    # Every opaque foreground pixel remains the same as
                    # paper moves beneath it. Test the actual native frame.
                    mask = foreground_mask(name, w, h)
                    difference = ImageChops.difference(rest, hovered)
                    occluded = Image.composite(difference, Image.new('RGB', rest.size), mask)
                    assert max(v[1] for v in ImageStat.Stat(occluded.crop(area)).extrema) < 4, (name, w, h, 'paper painted over foreground')
                    masked_rest, masked_hover = rest.copy(), hovered.copy()
                    for image in (masked_rest, masked_hover):
                        image.paste((0, 0, 0), area)
                    changed = ImageChops.difference(masked_rest, masked_hover).getbbox()
                    assert changed is None, (name, w, h, 'hovering the paper changed the scene', changed)
                    # A tap collects it once; nothing opens and the scene stays.
                    d.click_actual(round(x+edge*.32), y)
                    earned.append(slug)
                    assert collected(data) == earned, (name, w, h, collected(data))
                    time.sleep(1.5)
                    away(d, w, h)
                    after, expected = check_scene(d, name, w, h, 'collected')
                    gone = white_paper(after, expected, area)
                    assert gone < max(3, shown/2), (name, w, h, 'paper still shown', shown, gone)
                    # Once gone, the scene's underlying objects receive taps.
                    # Repeated collection itself is covered by title_test.zi;
                    # a second click here may legitimately open Picture Book.
            # The collection survives a restart and no paper comes back.
            with Desktop(binary, data, screen_size='1280x1100') as d:
                d.resize(w, h)
                for name in SCENES:
                    enter(d, name)
                    _, x, y, edge = paper(name, w, h)
                    away(d, w, h)
                    actual, expected = check_scene(d, name, w, h, 'restart')
                    assert white_paper(actual, expected, box(x, y, edge)) < 3, (name, w, h, 'paper came back')
            assert collected(data) == [paper(n, w, h)[0] for n in SCENES]
        print(f'local title paper UI: {w}x{h} treehouse/bookshelf/campus idle peek, hover reveal, foreground occlusion, '
              'tap collects once without navigating, gone after restart', flush=True)


if __name__ == '__main__':
    main()

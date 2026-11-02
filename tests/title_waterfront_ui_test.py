"""Waterfront hover and round trips on an owned private Xvfb, never the desktop."""
import json
import os
from pathlib import Path
import tempfile
import time
from PIL import Image, ImageChops, ImageStat
import runtime_test
from runtime_test import Desktop, ROOT, run
from title_scenes_test import hit
from title_paper_ui_test import foreground_mask


DATA = json.loads((ROOT/'tools/title_hotspots.json').read_text())


def scene(name, w, h):
    base = next(s for s in DATA['scenes'] if s['name']==name)
    return base.get('portrait', base) if h>w else base


def mapping(s, w, h):
    with Image.open(ROOT/s['image']) as source:
        sw, sh = source.size
    scale = max(w/sw, h/sh)
    return scale, (w-sw*scale)/2, (h-sh*scale)/2


def point(s, target, w, h):
    scale, ox, oy = mapping(s, w, h)
    candidates = [(x, y) for y in range(65, h-10, 3) for x in range(10, w-10, 3)
                  if hit(s, (x-ox)/scale, (y-oy)/scale)==target]
    assert candidates, (s['image'], target, 'no visible tappable point')
    return candidates[len(candidates)//2]


def move(d, x, y):
    run(['xdotool', 'mousemove', '--window', d.window, str(x), str(y)], d.env)
    time.sleep(.5)


def assert_scene(d, name, w, h):
    s = scene(name, w, h)
    scale, ox, oy = mapping(s, w, h)
    away = next((x,y) for y in range(65,h-10,7) for x in range(10,w-10,7)
                if hit(s,(x-ox)/scale,(y-oy)/scale) is None)
    move(d,*away)
    actual = d.capture_actual(f'waterfront-{name}-{w}')
    source = Image.open(ROOT/s['image']).convert('RGB')
    expected = source.resize((round(source.width*scale),round(source.height*scale)),Image.Resampling.BILINEAR)
    expected = expected.crop((-round(ox),-round(oy),w-round(ox),h-round(oy)))
    area = (20,80,w-20,h-30)
    error = max(ImageStat.Stat(ImageChops.difference(actual.crop(area),expected.crop(area))).mean)
    assert error < 12, (name,w,h,'wrong scene',error)
    return s, actual


def main():
    work = ROOT/'work/title-waterfront'
    work.mkdir(parents=True,exist_ok=True)
    captures = work/'ui-captures'
    captures.mkdir(exist_ok=True)
    # Never use another UI task's capture directory, even under make test-ui.
    runtime_test.OUTPUT = captures
    try:
        with tempfile.TemporaryDirectory(prefix='ui-',dir=work) as temporary:
            with Desktop(Path(os.environ.get('JUNGLE_TEST_BINARY',ROOT/'build/app/jungle')),
                         Path(temporary),screen_size='1280x1100') as d:
                for w,h in ((960,600),(420,900)):
                    d.resize(w,h)
                    d.key('Home')
                    home = DATA['scenes'][0]
                    d.key(str(next(i+1 for i,t in enumerate(home['hotspots']) if t['target']=='scene:campus')))
                    campus,rest = assert_scene(d,'campus',w,h)
                    arrow = next(t for t in campus['hotspots'] if t['id']=='beach-path')
                    scale,ox,oy = mapping(campus,w,h)
                    rx,ry,rw,rh = arrow['glow_rect']
                    area = (max(0,round(ox+rx*scale)),max(65,round(oy+ry*scale)),
                            min(w,round(ox+(rx+rw)*scale)),min(h,round(oy+(ry+rh)*scale)))
                    with Image.open(ROOT/campus['image']) as source:
                        background = source.convert('RGB').resize(
                            (round(source.width*scale),round(source.height*scale)),Image.Resampling.BILINEAR)
                    background = background.crop((-round(ox),-round(oy),w-round(ox),h-round(oy)))
                    resting_signal = max(ImageStat.Stat(ImageChops.difference(rest.crop(area),background.crop(area))).mean)
                    assert resting_signal > 1, ('resting arrow missing',w,h,resting_signal)
                    x,y = point(campus,'beach-path',w,h)
                    move(d,x,y)
                    hovered = d.capture_actual(f'waterfront-hover-{w}')
                    signal = max(ImageStat.Stat(ImageChops.difference(rest.crop(area),hovered.crop(area))).mean)
                    assert signal > .5, ('arrow hover missing',w,h,signal)
                    mask = foreground_mask('campus', w, h)
                    delta = ImageChops.difference(rest, hovered)
                    occluded = Image.composite(delta, Image.new('RGB', rest.size), mask)
                    assert max(v[1] for v in ImageStat.Stat(occluded.crop(area)).extrema) < 4, ('arrow painted over tiger',w,h)
                    d.click_actual(x,y)
                    beach,beach_rest = assert_scene(d,'beach',w,h)
                    # Actual painted game entries, using the production catalog and routes.
                    for ident, title in [('fishing-boat', 'Little Fishing Boat'),
                                         ('crab-family', 'Crab Family Counting')]:
                        beach, resting = assert_scene(d, 'beach', w, h)
                        target = next(t for t in beach['hotspots'] if t['id'] == ident)
                        scale, ox, oy = mapping(beach, w, h)
                        rx, ry, rw, rh = target['glow_rect']
                        area = (max(0, round(ox+rx*scale)), max(65, round(oy+ry*scale)),
                                min(w, round(ox+(rx+rw)*scale)), min(h, round(oy+(ry+rh)*scale)))
                        # The complete physical entry remains visible after cover-cropping.
                        assert 0 <= ox+rx*scale and ox+(rx+rw)*scale <= w, (ident, w, 'sprite cropped horizontally')
                        assert 65 <= oy+ry*scale and oy+(ry+rh)*scale <= h, (ident, w, 'sprite cropped vertically')
                        # Visible object interiors must really differ from the clean water/sand plate.
                        with Image.open(ROOT/target['rest']) as layer:
                            assert layer.mode == 'RGBA' and layer.getchannel('A').getextrema()[1] > 240
                        with Image.open(ROOT/beach['image']) as plate:
                            plate = plate.convert('RGB').resize((round(plate.width*scale), round(plate.height*scale)),
                                                               Image.Resampling.BILINEAR)
                        plate = plate.crop((-round(ox), -round(oy), w-round(ox), h-round(oy)))
                        visible = max(ImageStat.Stat(ImageChops.difference(resting.crop(area), plate.crop(area))).mean)
                        assert visible > 1, (ident, w, 'painted entry not visible', visible)
                        # Click opaque sprite pixels, proving the visible object and
                        # the production hit shape agree (rather than empty bounds).
                        with Image.open(ROOT/target['rest']) as layer:
                            painted = [(round(ox+(rx+px)*scale), round(oy+(ry+py)*scale))
                                       for py in range(0, rh, 3) for px in range(0, rw, 3)
                                       if layer.getpixel((px, py))[3] > 220
                                       and hit(beach, rx+px, ry+py) == ident
                                       and 10 < ox+(rx+px)*scale < w-10
                                       and 65 < oy+(ry+py)*scale < h-10]
                        assert painted, (ident, w, 'no visible opaque hit point')
                        x, y = painted[len(painted)//2]
                        move(d, x, y)
                        hovered = d.capture_actual(f'port-{ident}-hover-{w}')
                        signal = max(ImageStat.Stat(ImageChops.difference(resting.crop(area), hovered.crop(area))).mean)
                        assert signal > .5, (ident, w, 'painted object did not glow', signal)
                        d.click_actual(x, y)
                        time.sleep(1)
                        opened = d.capture_actual(f'port-{ident}-opened-{w}')
                        assert max(ImageStat.Stat(ImageChops.difference(resting, opened)).mean) > 15, (title, 'did not open')
                        # Shared title bar Back must return to this beach, in the current orientation.
                        d.click_actual(24, 26)
                        assert_scene(d, 'beach', w, h)
                        game = 'fishing' if ident == 'fishing-boat' else 'beach_families'
                        saved = Path(temporary)/f'games/jungle.{game}/{game}.txt'
                        assert saved.is_file(), (title, 'expected game did not save on Back')
                    # Open water next to the boat is not a game target and cannot glow it.
                    scale, ox, oy = mapping(beach, w, h)
                    water = (450, 430) if w > h else (330, 440)
                    assert hit(beach, *water) is None
                    move(d, round(ox+water[0]*scale), round(oy+water[1]*scale))
                    d.click_actual(round(ox+water[0]*scale), round(oy+water[1]*scale))
                    beach, beach_rest = assert_scene(d, 'beach', w, h)
                    return_arrow = next(t for t in beach['hotspots'] if t['id']=='campus-path')
                    scale,ox,oy = mapping(beach,w,h)
                    rx,ry,rw,rh = return_arrow['glow_rect']
                    area = (max(0,round(ox+rx*scale)),max(65,round(oy+ry*scale)),
                            min(w,round(ox+(rx+rw)*scale)),min(h,round(oy+(ry+rh)*scale)))
                    with Image.open(ROOT/beach['image']) as source:
                        background = source.convert('RGB').resize(
                            (round(source.width*scale),round(source.height*scale)),Image.Resampling.BILINEAR)
                    background = background.crop((-round(ox),-round(oy),w-round(ox),h-round(oy)))
                    resting_signal = max(ImageStat.Stat(ImageChops.difference(
                        beach_rest.crop(area),background.crop(area))).mean)
                    assert resting_signal > 1, ('beach resting arrow missing',w,h,resting_signal)
                    x,y = point(beach,'campus-path',w,h)
                    move(d,x,y)
                    hovered = d.capture_actual(f'waterfront-beach-return-hover-{w}')
                    signal = max(ImageStat.Stat(ImageChops.difference(
                        beach_rest.crop(area),hovered.crop(area))).mean)
                    assert signal > .5, ('beach return hover missing',w,h,signal)
                    d.click_actual(x,y)
                    assert_scene(d,'campus',w,h)
                    d.click_actual(*point(campus,'beach-path',w,h))
                    assert_scene(d,'beach',w,h)
                    for origin,target,destination in [('beach','bunker-door','aquarium'),
                                                       ('aquarium','beach-stairs','beach'),
                                                       ('beach','campus-path','campus')]:
                        origin_scene = scene(origin, w, h)
                        click = point(origin_scene, target, w, h)
                        if origin == 'beach' and target == 'bunker-door':
                            _, before = assert_scene(d, 'beach', w, h)
                            move(d, *click)
                            hovered = d.capture_actual(f'beach-aquarium-hover-{w}')
                            scale, ox, oy = mapping(origin_scene, w, h)
                            door = next(t for t in origin_scene['hotspots'] if t['id'] == target)
                            rx, ry, rw, rh = door['glow_rect']
                            area = (max(0, round(ox+rx*scale)), max(65, round(oy+ry*scale)),
                                    min(w, round(ox+(rx+rw)*scale)), min(h, round(oy+(ry+rh)*scale)))
                            assert max(ImageStat.Stat(ImageChops.difference(before.crop(area), hovered.crop(area))).mean) > .3, ('new Aquarium arch did not glow', w)
                        d.click_actual(*click)
                        assert_scene(d,destination,w,h)
                    # Return stairs and Escape share the same parent graph.
                    for name,target in [('campus','beach-path'),('beach','bunker-door')]:
                        d.click_actual(*point(scene(name,w,h),target,w,h))
                    d.key('Escape')
                    assert_scene(d,'beach',w,h)
                    d.key('Escape')
                    assert_scene(d,'campus',w,h)
                    print(f'local waterfront UI: {w}x{h} hover, campus/beach/aquarium round trip and Back passed',flush=True)
    finally:
        # Retain owned private-display evidence requested for layer review.
        pass


if __name__=='__main__':
    main()

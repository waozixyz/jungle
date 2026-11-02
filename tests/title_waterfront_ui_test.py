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
                    d.click_actual(x,y)
                    assert_scene(d,'beach',w,h)
                    for origin,target,destination in [('beach','bunker-door','aquarium'),
                                                       ('aquarium','beach-stairs','beach'),
                                                       ('beach','campus-path','campus')]:
                        d.click_actual(*point(scene(origin,w,h),target,w,h))
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
        # The owner judges visuals. Retain logs, remove owned verification pixels.
        for capture in captures.glob('*.png'):
            capture.unlink()


if __name__=='__main__':
    main()

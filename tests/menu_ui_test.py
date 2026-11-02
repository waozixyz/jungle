"""Painted title navigation on owned private Xvfb in both orientations."""
from pathlib import Path
import os
import tempfile
import json
import time
from title_scenes_test import hit
from PIL import Image, ImageChops, ImageStat
from runtime_test import Desktop, ROOT, title_keys, run

data = json.loads((ROOT/'tools/title_hotspots.json').read_text())

def select_painted(desktop, name, target, width, height):
    base = next(scene for scene in data['scenes'] if scene['name'] == name)
    scene = base.get('portrait', base) if height > width else base
    index = next(i for i, h in enumerate(scene['hotspots']) if h['id'] == target)
    for _ in range(index + 1): desktop.key('Right')
    hotspot = scene['hotspots'][index]
    source = Image.open(ROOT/scene['image']).convert('RGB')
    scale = max(width/source.width, height/source.height)
    x, y = (width-source.width*scale)/2, (height-source.height*scale)/2
    rx, ry, rw, rh = hotspot['glow_rect']
    pan_x = max(x, min(-x, width/2-x-(rx+rw/2)*scale))
    pan_y = max(y, min(-y, height/2-y-(ry+rh/2)*scale))
    x, y = x + pan_x, y + pan_y
    expected = source.resize((round(source.width*scale), round(source.height*scale)), Image.Resampling.BILINEAR)
    expected = expected.crop((-round(x), -round(y), width-round(x), height-round(y)))
    return scene, hotspot, expected, lambda px, py: (round(x+px*scale), round(y+py*scale))


def wait_painted_transition(desktop, name, expected, area, opened, timeout=20):
    """Wait for one input's rendered result without sending it again.

    A packaged frame can arrive after the first window capture. Keep the
    original scene-difference limits and fail if the destination never draws.
    """
    deadline = time.monotonic() + timeout
    while True:
        actual = desktop.capture_actual(name)
        error = ImageStat.Stat(ImageChops.difference(actual.crop(area), expected.crop(area))).mean
        ready = max(error) > 20 if opened else max(error) < 12
        if ready or time.monotonic() >= deadline:
            return actual, error
        time.sleep(.1)


def hover_ladder_gaps(desktop, scene, ladder, screen, width, height, points):
    """Every rung gap must show the same accepted glow as keyboard selection."""
    reference = desktop.capture_actual(f'{scene["image"].split("/")[-1]}-selected')
    rx, ry, rw, rh = ladder['glow_rect']
    left, top = screen(rx, ry)
    right, bottom = screen(rx+rw, ry+rh)
    area = (max(2, left), max(60, top), min(width-2, right), min(height-2, bottom))
    # The accepted glow pulses. Measure its presence against the same view
    # with the pointer away, rather than comparing two different pulse phases.
    run(['xdotool', 'mousemove', '--window', desktop.window, '5', str(height-5)], desktop.env)
    background = desktop.capture_actual(f'{scene["image"].split("/")[-1]}-away')
    signal = max(ImageStat.Stat(ImageChops.difference(reference.crop(area), background.crop(area))).mean)
    assert signal > .5, f'Keyboard ladder selection has no visible glow: {scene["image"]}'
    for index, point in enumerate(points):
        x, y = screen(*point)
        assert 0 <= x < width and 50 <= y < height, (scene['image'], point, x, y)
        run(['xdotool', 'mousemove', '--window', desktop.window, str(x), str(y)], desktop.env)
        actual = desktop.capture_actual(f'{scene["image"].split("/")[-1]}-gap-{index}')
        glow = max(ImageStat.Stat(ImageChops.difference(actual.crop(area), background.crop(area))).mean)
        assert glow > signal*.25, f'Ladder gap lost selection in {scene["image"]} at {point}: {glow}, expected {signal}'


def move(d,x,y):
    run(['xdotool','mousemove','--window',d.window,str(round(x)),str(round(y))],d.env)
    time.sleep(.65)

def fit(scene,w,h,pan):
    scale=max(w/scene['width'],h/scene['height'])
    cx,cy=(w-scene['width']*scale)/2,(h-scene['height']*scale)/2
    pan[:]=[max(cx,min(-cx,pan[0])),max(cy,min(-cy,pan[1]))]
    return scale,cx+pan[0],cy+pan[1]

def pan_alignment(d):
    """Rendered positions, hover and routes after focus and repeated drags.

    The bookshelf centre crosses the dismissed guide bubble: that invisible
    region used to swallow a drag and leave the image at its old position.
    """
    scenes = [scene for scene in data["scenes"]
              if scene["name"] in ("treehouse", "bookshelf", "campus")]
    for w,h in ((960,600),(420,900),(1100,300)):
        d.resize(w,h)
        for base in scenes:
            d.key('Home')
            if base['name']=='bookshelf': d.key(str(next(i+1 for i,t in enumerate(scenes[0]['hotspots']) if t['target']=='scene:bookshelf')))
            if base['name']=='campus': d.key(str(next(i+1 for i,t in enumerate(scenes[0]['hotspots']) if t['target']=='scene:campus')))
            scene=base.get('portrait',base) if h>w else base
            scene=dict(scene)
            scene['width'],scene['height']=Image.open(ROOT/scene['image']).size
            idx=next(i for i,t in enumerate(scene['hotspots']) if t['id']=='ladder')
            ladder=scene['hotspots'][idx]
            for _ in range(idx+1): d.key('Right')
            scale=max(w/scene['width'],h/scene['height'])
            cx,cy=(w-scene['width']*scale)/2,(h-scene['height']*scale)/2
            rx,ry,rw,rh=ladder['glow_rect']
            pan=[w/2-cx-(rx+rw/2)*scale,h/2-cy-(ry+rh/2)*scale]
            fit(scene,w,h,pan)
            for n,(dx,dy) in enumerate(((35,28),(-70,-56),(45,40),(-20,-12))):
                move(d,w/2,h/2)
                run(['xdotool','mousedown','1'],d.env)
                time.sleep(.65)
                move(d,w/2+dx,h/2+dy)
                run(['xdotool','mouseup','1'],d.env)
                time.sleep(.65)
                pan[0] += dx
                pan[1] += dy
                scale,x,y=fit(scene,w,h,pan)
                move(d,3,h-3)
                actual=d.capture_actual(f'pan-{w}-{base["name"]}-{n}')
                source=Image.open(ROOT/scene['image']).convert('RGB')
                expected=source.resize((round(scene['width']*scale),round(scene['height']*scale)),Image.Resampling.BILINEAR).crop((-round(x),-round(y),w-round(x),h-round(y)))
                area=(110,80,w-110,h-60)
                err=max(ImageStat.Stat(ImageChops.difference(actual.crop(area),expected.crop(area))).mean)
                assert err<12,(w,h,base['name'],n,'render offset',err,pan)
                points=[(sx,sy) for sy in range(80,h-30,5) for sx in range(5,w-2,5) if hit(scene,(sx-x)/scale,(sy-y)/scale)=='ladder']
                assert points,(w,h,base['name'],'ladder not visible')
                sx,sy=points[len(points)//2]
                move(d,sx,sy)
                glow=d.capture_actual(f'pan-{w}-{base["name"]}-{n}-hover')
                area=(max(2,round(x+rx*scale)),max(60,round(y+ry*scale)),min(w-2,round(x+(rx+rw)*scale)),min(h-2,round(y+(ry+rh)*scale)))
                signal=max(ImageStat.Stat(ImageChops.difference(glow.crop(area),actual.crop(area))).mean)
                assert signal>.5,(w,h,base['name'],n,'hover missing',signal)
                print('pan hover aligned',w,h,base['name'],n,round(err,2),round(signal,2),flush=True)
            d.click_actual(sx,sy)
            # The same stationary mouse may now hover another painted item
            # in the destination. Clear that glow before comparing routes.
            destination_name = ladder['target'].split(':')[1]
            destination = next(s for s in scenes if s['name'] == destination_name)
            destination = dict(destination.get('portrait', destination) if h>w else destination)
            destination['width'],destination['height'] = Image.open(ROOT/destination['image']).size
            ds, ox, oy = fit(destination,w,h,[0,0])
            away = next((ax,ay) for ay in range(80,h-5,5) for ax in range(5,w-5,5)
                        if hit(destination,(ax-ox)/ds,(ay-oy)/ds) is None)
            move(d,*away)
            opened=d.capture_actual(f'pan-{w}-{base["name"]}-clicked')
            d.key('Home')
            if base['name']=='treehouse': d.key(str(idx+1))
            reference=d.capture_actual(f'pan-{w}-{base["name"]}-destination')
            area=(110,80,w-110,h-60)
            err=max(ImageStat.Stat(ImageChops.difference(opened.crop(area),reference.crop(area))).mean)
            assert err<2,(w,h,base['name'],'wrong click destination',err)
            print('pan click destination aligned',w,h,base['name'],flush=True)

work = ROOT / 'work/title-tests'
work.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='menu-', dir=work) as temporary:
    with Desktop(Path(os.environ.get('JUNGLE_TEST_BINARY', ROOT/'build/app/jungle')),
                 Path(temporary), screen_size='1280x1100') as desktop:
        pan_alignment(desktop)
        for width, height in ((960, 600), (420, 900)):
            desktop.resize(width, height)
            desktop.key('Home')
            actual = desktop.capture_actual(f'title-{width}-treehouse')
            scene = json.loads((ROOT/'tools/title_hotspots.json').read_text())['scenes'][0]
            variant = scene.get('portrait', scene) if height > width else scene
            source = Image.open(ROOT/variant['image']).convert('RGB')
            scale = max(width/source.width, height/source.height)
            expected = source.resize((round(source.width*scale), round(source.height*scale)), Image.Resampling.BILINEAR)
            left, top = (expected.width-width)//2, (expected.height-height)//2
            expected = expected.crop((left, top, left+width, top+height))
            treehouse_expected = expected
            area = (30, 120, width-30, height-100)
            error = ImageStat.Stat(ImageChops.difference(actual.crop(area), expected.crop(area))).mean
            assert max(error) < 12, f'Wrong scene composition at {width}x{height}: {error}'
            treehouse, ladder, expected, screen = select_painted(desktop, 'treehouse', 'ladder', width, height)
            gaps = ((1500, 550), (1550, 565)) if width > height else ((880, 1260), (900, 1360))
            hover_ladder_gaps(desktop, treehouse, ladder, screen, width, height, gaps)
            desktop.click_actual(*screen(*gaps[0]))
            # A gap opens the same campus as its painted rails.
            opened = desktop.capture_actual(f'title-{width}-ladder-campus')
            desktop.key('Home')
            key = next(i+1 for i,h in enumerate(treehouse['hotspots']) if h['target']=='scene:campus')
            desktop.key(str(key))
            reference = desktop.capture_actual(f'title-{width}-keyboard-campus')
            error = ImageStat.Stat(ImageChops.difference(opened, reference)).mean
            assert max(error) < 1, f'Treehouse ladder gap opened the wrong scene: {error}'
            desktop.key('Home')
            # Bookshelf remains a painted target. Keyboard paths come from
            # the same source as the UI and remain stable across variants.
            keys = title_keys('ABC Book')
            for key in keys[:-1]: desktop.key(key)
            shelf, ladder, expected, screen = select_painted(desktop, 'bookshelf', 'ladder', width, height)
            actual = desktop.capture_actual(f'title-{width}-bookshelf')
            # The former large Back rectangle is now only the actual painting.
            area = (12, 80, min(width-12, 180), 140)
            error = ImageStat.Stat(ImageChops.difference(actual.crop(area), expected.crop(area))).mean
            assert max(error) < 12, f'Back overlay remains: {error}'
            area = (12, height-55, width//3-12, height-16)
            error = ImageStat.Stat(ImageChops.difference(actual.crop(area), expected.crop(area))).mean
            assert max(error) < 12, f'Pan hint overlay remains: {error}'
            gaps = ((1655, 500), (1650, 610), (1648, 710), (1648, 820)) if width > height else ((1016, 720), (1010, 830), (1005, 970), (990, 1090), (985, 1210), (980, 1330))
            hover_ladder_gaps(desktop, shelf, ladder, screen, width, height, gaps)
            point = gaps[1]
            desktop.click_actual(*screen(*point))
            # The painted ladder must have returned to the treehouse: the treehouse's ABC
            # path now enters the shelf again and opens the actual book.
            for key in keys[1:]: desktop.key(key)
            desktop.wait_book(f'title-{width}-abc')
            desktop.key('Escape')
            desktop.game('Picture Book')
            desktop.wait_book(f'title-{width}-picture-book')
            desktop.key('Escape')
            desktop.key('Home')
            # The campus house and ladder share a full silhouette and route.
            campus = next(scene for scene in data['scenes'] if scene['name'] == 'treehouse')
            key = next(i+1 for i,h in enumerate(campus['hotspots']) if h['target']=='scene:campus')
            desktop.key(str(key))
            scene, ladder, expected, screen = select_painted(desktop, 'campus', 'ladder', width, height)
            gaps = ((965, 150), (978, 210), (993, 265), (1007, 323), (1019, 380), (1030, 432)) if width > height else ((550, 310), (565, 390), (580, 460), (600, 530))
            hover_ladder_gaps(desktop, scene, ladder, screen, width, height, gaps)
            actual = desktop.capture_actual(f'title-{width}-combined-treehouse-glow')
            points = ((800, 50), (980, 350)) if width > height else ((500, 140), (570, 430))
            for point in points:
                x, y = screen(*point)
                area = (x-2, y-2, x+3, y+3)
                error = ImageStat.Stat(ImageChops.difference(actual.crop(area), expected.crop(area))).mean
                assert max(error) > 4, f'Combined house/ladder glow missing at {point}: {error}'
            desktop.click_actual(*screen(*gaps[2]))
            returned = desktop.capture_actual(f'title-{width}-house-return')
            area = (30, 120, width-30, height-100)
            error = ImageStat.Stat(ImageChops.difference(returned.crop(area), treehouse_expected.crop(area))).mean
            assert max(error) < 12, f'Painted house did not return to treehouse: {error}'
            # Clicking the house returns to treehouse, so this path still works.
            music_keys = title_keys('Music Room')
            for music_key in music_keys[:-1]: desktop.key(music_key)
            music_campus = desktop.capture_actual(f'title-{width}-music-campus')
            desktop.key(music_keys[-1])
            area = (30, 120, width-30, height-100)
            _, error = wait_painted_transition(desktop, f'title-{width}-music-game', music_campus, area, opened=True)
            assert max(error) > 20, f'Music Room did not open its game: {error}'
            desktop.key('Escape')
            # Returning from drums keeps this campus. Select the painted
            # piano and click its real keyboard at the orientation's own point.
            desktop.key('Home')
            desktop.key(str(key))
            scene, piano, expected, screen = select_painted(desktop, 'campus', 'piano', width, height)
            point = (1430, 340) if width > height else (900, 530)
            x, y = screen(*point)
            run(['xdotool', 'mousemove', '--window', desktop.window, str(x), str(y)], desktop.env)
            desktop.capture_actual(f'title-{width}-separate-piano-glow')
            desktop.click_actual(*screen(*point))
            area = (30, 120, width-30, height-100)
            actual, error = wait_painted_transition(desktop, f'title-{width}-piano-game', expected, area, opened=True)
            assert max(error) > 20, f'Painted piano did not open its game: {error}'
            desktop.key('1')
            desktop.key('Escape')
            returned, error = wait_painted_transition(desktop, f'title-{width}-piano-back', expected, area, opened=False)
            assert max(error) < 12, f'Piano Back did not return to the same campus: {error}'
print('local title UI test: repeated pan/focus at wide/portrait/short sizes; landscape/portrait ladder gap hover/click, navigation, combined house/ladder glow and direct book/music/piano routes passed')

"""Painted title navigation on owned private Xvfb in both orientations."""
from pathlib import Path
import os
import tempfile
import json
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


work = ROOT / 'work/title-tests'
work.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='menu-', dir=work) as temporary:
    with Desktop(Path(os.environ.get('JUNGLE_TEST_BINARY', ROOT/'build/app/jungle')),
                 Path(temporary), screen_size='1280x1100') as desktop:
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
            desktop.game('Music Room')
            desktop.capture(f'title-{width}-music-game')
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
            actual = desktop.capture_actual(f'title-{width}-piano-game')
            area = (30, 120, width-30, height-100)
            error = ImageStat.Stat(ImageChops.difference(actual.crop(area), expected.crop(area))).mean
            assert max(error) > 20, f'Painted piano did not open its game: {error}'
            desktop.key('1')
            desktop.key('Escape')
            returned = desktop.capture_actual(f'title-{width}-piano-back')
            error = ImageStat.Stat(ImageChops.difference(returned.crop(area), expected.crop(area))).mean
            assert max(error) < 12, f'Piano Back did not return to the same campus: {error}'
print('local title UI test: landscape/portrait ladder gap hover/click, navigation, combined house/ladder glow and direct book/music/piano routes passed')

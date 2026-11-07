"""The world map in the real app on an owned private Xvfb, both orientations.

Every painted scene shows the map button -> it opens the painted map -> hovering
a landmark lights it -> a click travels to that landmark's scene (the Farm
landmark opens the Farm) -> a locked landmark stays on the map -> Back returns
where the map was opened, including into the Farm. Captures stay in ignored
backup/.
"""
import json
from functools import lru_cache
import os
from pathlib import Path
import tempfile
import time
import numpy as np
from PIL import Image, ImageChops, ImageStat
import runtime_test as rt
from world_map_geometry import fog_alpha, selectable_point

SIZES = ((960, 600), (420, 900), (1080, 2340), (1366, 768), (768, 1024))
ICON = (0x2e, 0x69, 0x56)
PAPER = (0xfd, 0xe9, 0xca)


@lru_cache(maxsize=8)
def painted_map(image, areas, metadata=None):
    """Reference terrain, persistent clouds and selectable landmark layers."""
    data = json.loads(metadata if metadata is not None else (rt.ROOT/'tools/title_hotspots.json').read_text())
    world = next(s for s in data['scenes'] if s['name'] == 'map')
    view = world if world['image'] == image else world['portrait']
    plate = Image.open(rt.ROOT/image).convert('RGBA')
    # The map ships at 75%; its layout, clouds and landmarks use painting pixels.
    from design_size import design_size
    plate = plate.resize(design_size(image, plate), Image.Resampling.LANCZOS)
    # Every landmark layer lies under one smooth cover, rebuilt on
    # exploration changes. Independent image composition verifies the
    # native render rather than accepting puff gaps or landmarks over fog.
    for spot in view['hotspots']:
        if spot['rest']:
            x, y, w, h = spot['glow_rect']
            with Image.open(rt.ROOT/spot['rest']) as mark:
                plate.alpha_composite(mark.convert('RGBA').resize((w, h), Image.Resampling.BILINEAR), (x, y))
    yy, xx = np.mgrid[:256, :384].astype(np.float32)
    xx = (xx + .5) * plate.width / 384
    yy = (yy + .5) * plate.height / 256
    fog = np.empty((256, 384, 4), dtype=np.uint8)
    fog[:, :, :3] = (242, 246, 242)
    fog[:, :, 3] = fog_alpha(world, areas, xx, yy)
    plate.alpha_composite(Image.fromarray(fog).resize(plate.size, Image.Resampling.BILINEAR))
    return plate.convert('RGB')


def difference(a, b, box):
    return max(ImageStat.Stat(ImageChops.difference(a.crop(box), b.crop(box))).mean)


def map_fit(view, size, w, h):
    """host/jungle_title.zi TitleFit for the complete shared map painting."""
    width, height = view.get('width', size[0]), view.get('height', size[1])
    scale = min(w / width,h / height)
    ox, oy = (w - width * scale) / 2, (h - height * scale) / 2
    return scale, ox, oy


def scene_keys(data, name):
    """Home, then 1-9 along the shortest scene path to the scene NAME."""
    names = [scene['name'] for scene in data['scenes']]
    paths, queue = {0: []}, [0]
    while queue:
        scene = queue.pop(0)
        if names[scene] == name:
            return ['Home'] + [str(step + 1) for step in paths[scene]]
        for index, hotspot in enumerate(data['scenes'][scene]['hotspots']):
            kind, _, target = hotspot['target'].partition(':')
            if kind == 'scene' and names.index(target) not in paths:
                paths[names.index(target)] = paths[scene] + [index]
                queue.append(names.index(target))
    raise AssertionError(f'no keys reach {name}')


def own_point(spot):
    """A scene point on the landmark's painting (its box centre may be bare ground)."""
    if not spot['rest']:
        x, y, w, h = spot['glow_rect']
        return x + w / 2, y + h / 2
    with Image.open(rt.ROOT/spot['rest']) as layer:
        alpha = np.asarray(layer.convert('RGBA').getchannel('A'), dtype=np.float32)
    ys, xs = np.nonzero(alpha >= 200)
    cy, cx = ys.mean(), xs.mean()
    nearest = np.argmin((xs - cx) ** 2 + (ys - cy) ** 2)
    x, y, w, h = spot['glow_rect']
    return x + (xs[nearest] + .5) * w / alpha.shape[1], y + (ys[nearest] + .5) * h / alpha.shape[0]


def has_button(picture, box):
    """The map button's green icon is drawn inside BOX."""
    crop = np.asarray(picture.crop(box).convert('RGB'), dtype=np.int16)
    near = (np.abs(crop - np.array(ICON, dtype=np.int16)).max(axis=2) < 40).sum()
    return near >= 6


def main():
    root = rt.ROOT
    scratch = rt.run_folder('backup/world-map-smoke')
    rt.OUTPUT = scratch/'captures'
    data = json.loads((root/'tools/title_hotspots.json').read_text())
    world = next(s for s in data['scenes'] if s['name'] == 'map')
    binary = Path(os.environ.get('JUNGLE_TEST_BINARY', root/'build/app/jungle'))
    # Every painted scene the title reaches (the Farm's own scene is its game's
    # entrance art, checked in title_test.zi).
    painted = []
    for scene in data['scenes']:
        try:
            if scene['name'] != 'map':
                scene_keys(data, scene['name'])
                painted.append(scene['name'])
        except AssertionError:
            pass
    for w, h in SIZES:
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            state = Path(folder)
            (state/'sound.txt').write_text('on\n' if (w, h) == (960, 600) else 'off\n')
            (state/'guide.txt').write_text('seen\n')
            # The Farm opens as a game, not a scene the keys walk through, so
            # its earlier visit is saved: every landmark is out of the fog.
            (state/'explored.txt').write_text('JUNGLE EXPLORED 1\nfarm\n')
            with rt.Desktop(binary, state, extra_env={'TMPDIR': str(state)}, screen_size='1400x2500') as d:
                def tap(x, y):
                    rt.run(['xdotool', 'mousemove', '--window', d.window, str(round(x)), str(round(y))], d.env)
                    time.sleep(.08)
                    rt.run(['xdotool', 'mousedown', '1'], d.env)
                    time.sleep(.12)
                    rt.run(['xdotool', 'mouseup', '1'], d.env)
                    time.sleep(.45)

                def hover(x, y):
                    rt.run(['xdotool', 'mousemove', '--window', d.window, str(round(x)), str(round(y))], d.env)
                    time.sleep(.35)

                def until(name, test, seconds=10):
                    deadline = time.monotonic() + seconds
                    while True:
                        picture = d.capture_actual(name)
                        if test(picture):
                            return picture
                        assert time.monotonic() < deadline, (w, h, name)
                        time.sleep(.15)

                d.resize(w, h)
                unit = rt.title_unit(w, h)
                w_units = int(w / unit)
                button = (round((w_units - 96) * unit), round(6 * unit), round((w_units - 70) * unit), round(28 * unit))
                press_map = lambda: tap((w_units - 83) * unit, 17 * unit)
                rest = lambda: hover(w / 2, h - 3)
                area = (10, round(40 * unit), w - 10, h - 10)
                view = world['portrait'] if h > w else world
                scale, ox, oy = map_fit(view, (data['width'], data['height']), w, h)
                to_screen = lambda x, y: (ox + x * scale, oy + y * scale)
                # The map's own paper surrounds the plate, behind every landmark.
                def painted_like_plate(picture, box, small=(48, 48), limit=22):
                    path = state/'explored.txt'
                    areas = tuple(path.read_text().splitlines()[1:]) if path.exists() else ()
                    plate = painted_map(view['image'], areas)
                    plate = plate.resize((round(plate.width * scale), round(plate.height * scale)), Image.Resampling.BILINEAR)
                    inside = (max(box[0], round(ox)), max(box[1], round(oy)),
                              min(box[2], round(ox) + plate.width), min(box[3], round(oy) + plate.height))
                    if inside[2] - inside[0] < small[0] or inside[3] - inside[1] < small[1]:
                        # Outside the plate the window shows the map's flat paper.
                        paper = Image.new('RGB', (box[2] - box[0], box[3] - box[1]), PAPER)
                        return max(ImageStat.Stat(ImageChops.difference(picture.crop(box).convert('RGB'), paper)).mean) < limit
                    box = inside
                    expected = plate.crop((box[0] - round(ox), box[1] - round(oy), box[2] - round(ox), box[3] - round(oy)))
                    return max(ImageStat.Stat(ImageChops.difference(picture.crop(box).convert('RGB').resize(small),
                                                                   expected.resize(small))).mean) < limit

                def on_map(picture):
                    return painted_like_plate(picture, (0, round(40 * unit), w, h))

                # Each painted scene, reached by keys: its reference picture and its map button.
                references = {}
                for name in painted:
                    # Each key changes scene; let that scene's pictures
                    # decode before the next key, as a person would.
                    for key in scene_keys(data, name):
                        d.key(key)
                        time.sleep(.6)
                    rest()
                    picture = d.capture_actual(f'{w}-{name}')
                    assert has_button(picture, button), (w, h, name, 'no map button')
                    references[name] = picture
                # The map opens from the treehouse; Back returns there.
                d.key('Home')
                rest()
                press_map()
                rest()
                shown = until(f'{w}-map', on_map)
                # Where the other scenes have the map button, the map shows its own painting.
                assert painted_like_plate(shown, button, (6, 6), 30), 'the map shows its own button'
                tap(28 * unit, 21 * unit)
                rest()
                until(f'{w}-map-back', lambda p: difference(p, references[painted[0]], area) < 8)
                for spot in view['hotspots']:
                    kind, _, target = spot['target'].partition(':')
                    origin = 'desert' if kind == 'locked' else 'campus'
                    for key in scene_keys(data, origin):
                        d.key(key)
                        time.sleep(.6)
                    time.sleep(.5)
                    press_map()
                    rest()
                    still = until(f'{w}-map-{spot["id"]}', on_map)
                    x, y, gw, gh = spot['glow_rect']
                    px,py,_ = selectable_point(view,spot,(w,h))
                    centre = to_screen(px,py)
                    inside = tuple(round(v) for v in (*to_screen(x + gw * .2, y + gh * .2), *to_screen(x + gw * .8, y + gh * .8)))
                    hover(*centre)
                    hover(centre[0] + 1, centre[1])
                    until(f'{w}-hover-{spot["id"]}', lambda p: difference(p, still, inside) > 3)
                    tap(*centre)
                    rest()
                    if kind == 'locked':
                        time.sleep(.8)
                        picture = d.capture_actual(f'{w}-locked-{spot["id"]}')
                        assert on_map(picture), (w, h, spot['id'], 'a locked landmark left the map')
                        tap(28 * unit, 21 * unit)
                        rest()
                        until(f'{w}-locked-back', lambda p: difference(p, references['desert'], area) < 8)
                    elif kind == 'scene':
                        until(f'{w}-at-{target}', lambda p: difference(p, references[target], area) < 8)
                    else:
                        # Farm has only floating Back; it returns to Campus,
                        # whose map button opens the map again.
                        assert target == 'Farm', spot
                        entrance = until(f'{w}-farm', lambda p: not on_map(p) and difference(p, references['campus'], area) > 8)
                        # The first opening's award badge flies away before the entrance is compared.
                        deadline = time.monotonic() + 10
                        while True:
                            time.sleep(1)
                            settled = d.capture_actual(f'{w}-farm-settled')
                            if difference(settled, entrance, area) < 1.5 or time.monotonic() > deadline:
                                entrance = settled
                                break
                            entrance = settled
                        tap(28,21)
                        rest()
                        until(f'{w}-farm-back-campus', lambda p: difference(p, references['campus'], area) < 8)
                        press_map()
                        rest()
                        until(f'{w}-farm-map', on_map)
                        tap(28 * unit, 21 * unit)
                        rest()
                        until(f'{w}-farm-map-back-campus', lambda p: difference(p, references['campus'], area) < 8)
                d.alive()
            print(f'local world map smoke: {w}x{h}, map button on {len(painted)} scenes, '
                  f'{len(view["hotspots"])} landmarks hover/travel, locked stays, Back and Farm return passed', flush=True)


if __name__ == '__main__':
    main()

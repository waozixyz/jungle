"""Real native visits clear clouds and survive restart on an owned private Xvfb."""
import json
from pathlib import Path
import tempfile
import time
from PIL import ImageStat

import runtime_test as rt
from world_map_smoke_test import difference, map_fit, scene_keys


def opaque_mist(picture, box):
    """No painted sand/water or repeated puff gaps in untouched interiors."""
    crop = picture.crop(box)
    expected = (242, 246, 242)
    for channel, (low, high) in enumerate(crop.getextrema()):
        assert abs(low-expected[channel]) <= 1 and abs(high-expected[channel]) <= 1, ('unseen terrain leaks through fog', channel, low, high)
    assert max(ImageStat.Stat(crop).stddev) < .1, 'unexplored interior has repeated cloud texture/gaps'


def main():
    scratch = rt.run_folder('backup/world-map-exploration')
    rt.OUTPUT = scratch / 'captures'
    data = json.loads((rt.ROOT / 'tools/title_hotspots.json').read_text())
    world = next(s for s in data['scenes'] if s['name'] == 'map')
    binary = rt.ROOT / 'build/app/jungle'
    for w, h in ((960, 600), (420, 900)):
        view = world['portrait'] if h > w else world
        scale, ox, oy = map_fit(view, (data['width'], data['height']), w, h)
        box = tuple(round(v) for v in (ox + 40 * scale, oy + 190 * scale,
                                      ox + 620 * scale, oy + 380 * scale))
        far = tuple(round(v) for v in (ox + 2400 * scale, oy + 1450 * scale,
                                      ox + 2900 * scale, oy + 1800 * scale))
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            state = Path(folder)
            (state / 'guide-seen.txt').write_text('yes\n')
            (state / 'sound.txt').write_text('off\n')
            (state / 'language.txt').write_text('en')
            # A genuine old game save migrates its known Farm visit and stays intact.
            old = state / 'games/jungle.garden/garden.txt'
            old.parent.mkdir(parents=True)
            old.write_text('existing-owner-garden-preserved\n')

            def enter_map(d):
                unit = rt.title_unit(w, h)
                x = round((int(w / unit) - 83) * unit)
                y = round(17 * unit)
                rt.run(['xdotool', 'mousemove', '--window', d.window, str(x), str(y)], d.env)
                # Let retained hover observe the new pointer position before
                # pressing; a teleport and down may otherwise share a frame.
                time.sleep(.2)
                rt.run(['xdotool', 'mousedown', '1'], d.env)
                time.sleep(.15)
                rt.run(['xdotool', 'mouseup', '1'], d.env)
                time.sleep(.15)
                rt.run(['xdotool', 'mousemove', '--window', d.window, str(w // 2), str(h - 3)], d.env)
                time.sleep(1)

            def saved():
                path = state / 'explored.txt'
                return path.read_text() if path.exists() else ''

            with rt.Desktop(binary, state, extra_env={'TMPDIR': str(state)}) as d:
                d.resize(w, h)
                enter_map(d)
                before = d.capture_actual(f'{w}-unvisited-port-clouds')
                opaque_mist(before, far)
                assert 'treehouse\n' in saved() and 'farm\n' in saved() and 'port\n' not in saved(), saved()
                # Hovering and opening the map have not visited Port, so its
                # fogged landmark ignores its key. Walk there through the scenes.
                d.key('1')
                time.sleep(.8)
                assert 'port\n' not in saved(), saved()
                for key in scene_keys(data, 'port'):
                    d.key(key)
                    time.sleep(.6)
                assert 'port\n' in saved(), saved()
                enter_map(d)
                after = d.capture_actual(f'{w}-visited-port-clear')
                opaque_mist(after, far)
                assert difference(before, after, box) > 4, (w, h, 'Port clouds did not clear')
                assert difference(before, after, far) < 1, (w, h, 'unvisited terrain changed')
                snapshot = saved()
            with rt.Desktop(binary, state, extra_env={'TMPDIR': str(state)}) as d:
                d.resize(w, h)
                enter_map(d)
                reopened = d.capture_actual(f'{w}-reopened-port-clear')
                opaque_mist(reopened, far)
                assert difference(after, reopened, box) < 1, (w, h, 'clouds returned after restart')
                assert saved() == snapshot
                assert old.read_text() == 'existing-owner-garden-preserved\n'
                assert (state / 'sound.txt').read_text() == 'off\n'
                assert (state / 'language.txt').read_text() == 'en'
            print(f'local native exploration {w}x{h}: old Farm visit seeded; genuine Port visit clears clouds; restart keeps clearing and owner saves/settings', flush=True)


if __name__ == '__main__':
    main()

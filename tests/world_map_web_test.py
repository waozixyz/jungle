"""Web: the world map opens from the map button, lights and travels, and Back returns.

  build-queue -- python3 tests/world_map_web_test.py --web-root build/web

In both renderers, in private headless Chromium, landscape and portrait: the
treehouse shows the map button; it opens the painted map; hovering Campus lights
it and a click travels there; the darkness beyond the Desert stays on the map;
Back returns to Campus, where the map was opened. Python stdlib + PIL; no
desktop pixels and no Node.
"""
import argparse
import base64
import io
import json
import time
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

import book_media_start_web_test as web
import runtime_test
from world_map_smoke_test import difference, has_button, map_fit, own_point, scene_keys

ROOT = Path(__file__).resolve().parents[1]
web.WORK = ROOT / 'local/world-map-web/browser'
SIZES = ((1280, 675), (412, 915))
STARTED = 'typeof Module!=="undefined"&&!!Module.FS&&document.getElementById("loading").style.display==="none"'


def shot(client):
    data = client.call('Page.captureScreenshot', format='png')['data']
    with Image.open(io.BytesIO(base64.b64decode(data))) as picture:
        return picture.convert('RGB')


def run(base_url, renderer, w, h):
    data = json.loads((ROOT / 'tools/title_hotspots.json').read_text())
    world = next(s for s in data['scenes'] if s['name'] == 'map')
    view = world['portrait'] if h > w else world
    spots = {s['id']: s for s in view['hotspots']}
    scale, ox, oy = map_fit(view, (data['width'], data['height']), w, h)
    plate = Image.open(ROOT / view['image']).convert('RGB')
    plate = plate.resize((round(plate.width * scale), round(plate.height * scale)), Image.Resampling.BILINEAR)
    unit = runtime_test.title_unit(w, h)
    w_units = int(w / unit)
    button = (round((w_units - 96) * unit), round(6 * unit), round((w_units - 70) * unit), round(28 * unit))
    area = (10, round(40 * unit), w - 10, h - 10)

    def on_map(picture):
        box = (max(0, round(ox)), max(round(40 * unit), round(oy)), min(w, round(ox) + plate.width), min(h, round(oy) + plate.height))
        expected = plate.crop((box[0] - round(ox), box[1] - round(oy), box[2] - round(ox), box[3] - round(oy)))
        return max(ImageStat.Stat(ImageChops.difference(picture.crop(box).resize((48, 48)), expected.resize((48, 48)))).mean) < 22

    def centre(spot):
        x, y = own_point(spots[spot])
        return ox + x * scale, oy + y * scale

    def until(client, test, what, seconds=10):
        end = time.monotonic() + seconds
        while True:
            picture = shot(client)
            if test(picture):
                return picture
            assert time.monotonic() < end, (renderer, w, h, what)
            time.sleep(.2)

    with web.browser() as client:
        client.call('Emulation.setDeviceMetricsOverride', width=w, height=h, deviceScaleFactor=1, mobile=False)
        client.call('Page.navigate', url=base_url.rstrip('/') + '/' + renderer + '.html')
        client.until(STARTED, 'wasm startup', 90)
        time.sleep(1.5)
        rest = lambda: client.call('Input.dispatchMouseEvent', type='mouseMoved', x=w // 2, y=h - 3)
        for key in scene_keys(data, 'campus'):
            client.key(key)
            time.sleep(.6)
        rest()
        time.sleep(.6)
        campus = shot(client)
        assert has_button(campus, button), (renderer, w, h, 'no map button on Campus')
        client.click((w_units - 83) * unit, 17 * unit)
        shown = until(client, on_map, 'the map')
        # Hover lights Campus; a click travels there.
        x, y = centre('campus')
        client.call('Input.dispatchMouseEvent', type='mouseMoved', x=x, y=y)
        time.sleep(.5)
        gx, gy, gw, gh = spots['campus']['glow_rect']
        box = tuple(round(v) for v in (ox + (gx + gw * .2) * scale, oy + (gy + gh * .2) * scale,
                                        ox + (gx + gw * .8) * scale, oy + (gy + gh * .8) * scale))
        until(client, lambda p: difference(p, shown, box) > 3, 'Campus lights up')
        client.click(x, y)
        rest()
        until(client, lambda p: difference(p, campus, area) < 8, 'travel to Campus')
        # The darkness beyond the Desert stays on the map; Back returns to Campus.
        client.click((w_units - 83) * unit, 17 * unit)
        until(client, on_map, 'the map again')
        client.click(*centre('darkness'))
        rest()
        time.sleep(1)
        assert on_map(shot(client)), (renderer, w, h, 'the darkness left the map')
        client.click(28 * unit, 21 * unit)
        rest()
        until(client, lambda p: difference(p, campus, area) < 8, 'Back to Campus')
    print(f'local world map web {renderer} {w}x{h}: button, map, hover, travel, locked darkness and Back passed', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--web-root', type=Path, default=ROOT / 'build/web')
    args = parser.parse_args()
    with web.serve(args.web_root.resolve()) as url:
        for renderer in ('canvas', 'dom'):
            for w, h in SIZES:
                run(url, renderer, w, h)


if __name__ == '__main__':
    main()

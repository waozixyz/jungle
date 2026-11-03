"""Web: Farm seeds drag and plant in the real browser runtime, in private headless Chromium.

  build-queue -- python3 tests/farm_web_test.py --web-root build/web

In both renderers: open Farm from the title scenes and the first garden with
the keyboard, drag a seed from the bag onto the soil, pick it up and drag it
again, then leave it alone until it sinks in and its sapling rises. Each step
must change the painted soil exactly where the seed is. Python stdlib + PIL;
no desktop pixels and no Node.
"""
import argparse
import base64
import io
import time
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

import book_media_start_web_test as web
import runtime_test

ROOT = Path(__file__).resolve().parents[1]
web.WORK = ROOT / 'local/farm-web/browser'
WIDTH, HEIGHT, HEADER = 1280, 675, 56


def contain(width, height, image_width, image_height):
    scale = min(width / image_width, height / image_height)
    return scale, int(image_width * scale), int(image_height * scale)


class Farm:
    """Logical Farm geometry (games/garden/jungle_garden.zi) in page pixels."""
    def __init__(self):
        self.scale = min(min(WIDTH, HEIGHT - HEADER) / 400, 1.8)
        self.lw, self.lh = int(WIDTH / self.scale), int((HEIGHT - HEADER) / self.scale)

    def page(self, x, y):
        return round(x * self.scale), round(HEADER + y * self.scale)

    def bag(self):
        cell = (self.lw - 24) // 4
        return self.page(12 + (cell - 4) / 2, self.lh - 45)

    def soil(self, u, v):
        scale, w, h = contain(self.lw, self.lh, 1536, 1024)
        sx, sw = (self.lw - w) // 2 + w * 15 // 100, w * 70 // 100
        sy, sh = (self.lh - h) // 2 + h * 43 // 100, h * 32 // 100
        return self.page(sx + u * sw / 10000, sy + v * sh / 10000)


def shot(client, name):
    data = client.call('Page.captureScreenshot', format='png')['data']
    with Image.open(io.BytesIO(base64.b64decode(data))) as picture:
        picture = picture.convert('RGB')
    # Private headless pictures for review, never the desktop.
    web.WORK.mkdir(parents=True, exist_ok=True)
    picture.save(web.WORK / f'{name}.png')
    return picture


def change(before, after, point, radius=34):
    x, y = point
    box = (x - radius, y - radius * 2, x + radius, y + radius // 2)
    return max(ImageStat.Stat(ImageChops.difference(before.crop(box), after.crop(box))).mean)


def drag(client, start, end, steps=14):
    client.call('Input.dispatchMouseEvent', type='mouseMoved', x=start[0], y=start[1])
    time.sleep(.1)
    client.call('Input.dispatchMouseEvent', type='mousePressed', x=start[0], y=start[1], button='left', buttons=1, clickCount=1)
    time.sleep(.12)
    for step in range(1, steps + 1):
        x = start[0] + (end[0] - start[0]) * step / steps
        y = start[1] + (end[1] - start[1]) * step / steps
        client.call('Input.dispatchMouseEvent', type='mouseMoved', x=x, y=y, button='left', buttons=1)
        time.sleep(.03)
    client.call('Input.dispatchMouseEvent', type='mouseReleased', x=end[0], y=end[1], button='left', buttons=0, clickCount=1)
    time.sleep(.25)


def run(base_url, renderer):
    farm = Farm()
    with web.browser() as client:
        client.call('Emulation.setDeviceMetricsOverride', width=WIDTH, height=HEIGHT, deviceScaleFactor=1, mobile=False)
        client.call('Page.navigate', url=base_url.rstrip('/') + '/' + renderer + '.html')
        client.until('typeof Module!=="undefined"&&!!Module.FS&&document.getElementById("loading").style.display==="none"',
                     'wasm startup', 90)
        for key in runtime_test.title_keys('Farm'):
            client.key(key)
            time.sleep(.8)
        client.until('(() => { const o = document.getElementById("activity-loading"); return !o || o.hidden })()',
                     'Farm download', 60)
        time.sleep(2)
        client.key('1')
        time.sleep(1.5)
        # Park the pointer away from the soil before the empty-garden picture.
        client.call('Input.dispatchMouseEvent', type='mouseMoved', x=WIDTH - 20, y=HEADER + 70)
        time.sleep(.4)
        empty = shot(client, f'{renderer}-empty')
        first, second = farm.soil(3000, 5000), farm.soil(7000, 5000)
        drag(client, farm.bag(), first)
        client.call('Input.dispatchMouseEvent', type='mouseMoved', x=WIDTH - 20, y=HEADER + 70)
        time.sleep(.3)
        dropped = shot(client, f'{renderer}-dropped')
        assert change(empty, dropped, first) > 6, (renderer, 'no seed where it was dropped', change(empty, dropped, first))
        # Pick the resting seed up and move it across the soil.
        drag(client, (first[0], first[1] - round(farm.scale * 8)), second)
        client.call('Input.dispatchMouseEvent', type='mouseMoved', x=WIDTH - 20, y=HEADER + 70)
        time.sleep(.3)
        moved = shot(client, f'{renderer}-moved')
        assert change(empty, moved, first) < 3, (renderer, 'seed stayed behind after it was moved', change(empty, moved, first))
        assert change(empty, moved, second) > 6, (renderer, 'moved seed missing', change(empty, moved, second))
        # Left alone, it sinks into a mound and a sapling rises.
        time.sleep(5.5)
        planted = shot(client, f'{renderer}-planted')
        assert change(moved, planted, second) > 6, (renderer, 'resting seed never planted', change(moved, planted, second))
    print(f'local Farm web {renderer}: bag drag, pick up and move, rest timer and sapling rise passed', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--web-root', type=Path, default=ROOT / 'build/web')
    args = parser.parse_args()
    with web.serve(args.web_root.resolve()) as url:
        for renderer in ('canvas', 'dom'):
            run(url, renderer)


if __name__ == '__main__':
    main()

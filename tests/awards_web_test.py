"""Web: a game's first opening gives its award, celebrates it once and keeps it.

  build-queue -- python3 tests/awards_web_test.py --web-root build/web

In both renderers, in private headless Chromium: a fresh page has no awards.
Opening Shapes & Sorting from the title scenes saves award-shapes in the app's
IndexedDB documents and pops the gold badge over the game, which is gone a few
seconds later. Opening it again gives nothing new and shows no badge, and a
reloaded page still has the award. Python stdlib + PIL; no desktop pixels and
no Node.
"""
import argparse
import base64
import io
import time
from pathlib import Path

from PIL import Image

import book_media_start_web_test as web
import runtime_test
from awards_smoke_test import gold

ROOT = Path(__file__).resolve().parents[1]
web.WORK = runtime_test.run_folder('local/awards-web', create=False) / 'browser'
WIDTH, HEIGHT, HEADER = 1280, 675, 56
STARTED = 'typeof Module!=="undefined"&&!!Module.FS&&document.getElementById("loading").style.display==="none"'
LOADED = '(() => { const o = document.getElementById("activity-loading"); return !o || o.hidden })()'
AWARDS = web.AWARDS
SHAPES = 'JUNGLE AWARDS 1\naward-shapes\n'


def shot(client):
    data = client.call('Page.captureScreenshot', format='png')['data']
    with Image.open(io.BytesIO(base64.b64decode(data))) as picture:
        return picture.convert('RGB')


def badge_box():
    """The badge resting in the middle of the game area (host/jungle_awards.zi)."""
    area = HEIGHT - HEADER
    size = max(96, min(320, min(WIDTH, area) * 2 // 5))
    x, y = WIDTH // 2, HEADER + area // 2
    return (x - size // 2, y - size // 2, x + size // 2, y + size // 2)


def open_shapes(client):
    for key in runtime_test.title_keys('Shapes & Sorting'):
        client.key(key)
        time.sleep(.6)


def run(base_url, renderer):
    box = badge_box()
    with web.browser() as client:
        client.call('Emulation.setDeviceMetricsOverride', width=WIDTH, height=HEIGHT, deviceScaleFactor=1, mobile=False)
        client.call('Page.navigate', url=base_url.rstrip('/') + '/' + renderer + '.html')
        client.until(STARTED, 'wasm startup', 90)
        time.sleep(1)
        assert client.evaluate(AWARDS) in ('', 'JUNGLE AWARDS 1\n'), (renderer, client.evaluate(AWARDS))
        open_shapes(client)
        client.until(f'{AWARDS}.includes("award-shapes")', 'Shapes & Sorting award', 30)
        assert client.evaluate(AWARDS) == SHAPES, (renderer, client.evaluate(AWARDS))
        client.until(LOADED, 'Shapes & Sorting download', 60)
        # The badge pops once its picture is here: the brightest moment of the show.
        shown, end = 0, time.monotonic() + 4
        while time.monotonic() < end and shown < 1500:
            shown = max(shown, gold(shot(client), box))
            time.sleep(.15)
        time.sleep(4)
        after = gold(shot(client), box)
        assert shown > 1500 and shown > 4 * after + 500, (renderer, 'no award celebration', shown, after)
        # Home and in again: kept, never given or celebrated twice.
        client.key('Escape')
        time.sleep(.6)
        open_shapes(client)
        client.until(LOADED, 'Shapes & Sorting again', 60)
        again = 0
        for _ in range(8):
            again = max(again, gold(shot(client), box))
            time.sleep(.15)
        assert again < shown / 4, (renderer, 'the award was celebrated twice', shown, again)
        assert client.evaluate(AWARDS) == SHAPES, (renderer, client.evaluate(AWARDS))
        # Saved to IndexedDB within a second; a fresh page reads it back.
        time.sleep(1.6)
        client.call('Page.reload', ignoreCache=False)
        time.sleep(.5)
        client.until(STARTED, 'wasm restart', 90)
        client.until(f'{AWARDS} === {SHAPES!r}', 'the award after a reload', 10)
    print(f'local awards web {renderer}: award saved, badge gold {shown} -> {after}, reopened {again}, kept after reload', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--web-root', type=Path, default=ROOT / 'build/web')
    args = parser.parse_args()
    with web.serve(args.web_root.resolve()) as url:
        for renderer in ('canvas', 'dom'):
            run(url, renderer)


if __name__ == '__main__':
    main()

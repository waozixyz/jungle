"""Web: Jungle's one hand cursor in Canvas and DOM, in private headless Chromium.

  build-queue -- python3 tests/cursor_web_test.py --web-root PATH

At device pixel ratio 2, the element under the pointer must show the hand's CSS
cursor (a 64 px image-set density image shown at 32 CSS pixels, hotspot 8 1) on the title
scenes, the bookshelf and in games, and no element's cursor may change while
the pointer moves. Each image's soft edge must be dark outline, never light.
"""
import argparse
import base64
import io
import json
import re
import time
from pathlib import Path

from PIL import Image

import book_media_start_web_test as web
import runtime_test

HOTSPOT = '8 1'
POINTS = ((640, 340), (200, 160), (1100, 560), (90, 620), (1180, 80), (640, 90), (420, 500), (860, 250))
WATCH = '''(() => {
  window.cursorProbe = {changes: [], last: new WeakMap()};
  const watch = element => {
    const value = element.style ? element.style.cursor : '';
    const before = cursorProbe.last.get(element);
    if (before !== undefined && before !== value) cursorProbe.changes.push([element.id || element.tagName, before.slice(0, 60), value.slice(0, 60)]);
    cursorProbe.last.set(element, value);
  };
  document.querySelectorAll('*').forEach(watch);
  new MutationObserver(list => list.forEach(change => watch(change.target)))
    .observe(document.documentElement, {subtree: true, attributes: true, attributeFilter: ['style']});
})()'''


def under(client, x, y):
    return client.evaluate(f'(() => {{ const e = document.elementFromPoint({x}, {y}); '
                           f'return e ? getComputedStyle(e).cursor : "" }})()')


def images(css):
    found = re.findall(r'url\("?data:image/png;base64,([A-Za-z0-9+/=]+)"?\)', css)
    assert found, 'cursor has no image: ' + css[:120]
    result = []
    for data in found:
        with Image.open(io.BytesIO(base64.b64decode(data))) as picture:
            result.append(picture.convert('RGBA'))
    return result


def clean(picture):
    soft = 0
    pixels = picture.tobytes()
    for red, green, blue, alpha in zip(*[iter(pixels)] * 4):
        if 0 < alpha < 200:
            soft += 1
            assert .299 * red + .587 * green + .114 * blue <= 150, 'light fringe on the web cursor edge'
    assert soft > 10, 'web cursor has no antialiased edge'


def expect_hand(client, phase, seen):
    client.call('Input.dispatchMouseEvent', type='mouseMoved', x=POINTS[0][0], y=POINTS[0][1])
    css = client.until(f'(() => {{ const c = getComputedStyle(document.elementFromPoint({POINTS[0][0]}, {POINTS[0][1]})).cursor; '
                       f'return c.includes("url(") && c.includes("{HOTSPOT}") ? c : "" }})()', f'hand cursor: {phase}', 30)
    if 'css' not in seen:
        pictures = images(css)
        sizes = sorted(picture.size for picture in pictures)
        # At 2x the browser shows the 64 px density image at 32 CSS pixels.
        assert 'image-set(' in css and re.search(r'" ?\) 2(x|dppx)\)', css) and sizes == [(64, 64)], ('no 2x density cursor', sizes, css[-60:])
        for picture in pictures:
            clean(picture)
        seen['css'] = css
    assert css == seen['css'], ('hand cursor changed', phase)
    client.evaluate('cursorProbe.changes.length = 0')
    for x, y in POINTS[1:] * 2:
        client.call('Input.dispatchMouseEvent', type='mouseMoved', x=x, y=y)
        time.sleep(.06)
        assert under(client, x, y) == css, ('a different cursor under the pointer', phase, x, y)
    changes = client.evaluate('cursorProbe.changes')
    assert not changes, ('cursor style changed while moving', phase, changes)
    seen.setdefault('phases', []).append(phase)


def run(base_url, renderer):
    seen = {}
    with web.browser() as client:
        client.call('Emulation.setDeviceMetricsOverride', width=1280, height=675, deviceScaleFactor=2, mobile=False)
        client.call('Page.navigate', url=base_url.rstrip('/') + '/' + renderer + '.html')
        client.until('typeof Module!=="undefined"&&!!Module.FS&&document.getElementById("loading").style.display==="none"',
                     'wasm startup', 90)
        client.evaluate(WATCH)
        client.key('Home')
        time.sleep(1)
        expect_hand(client, 'treehouse', seen)
        for title in ('Picture Book', 'Jigsaw Puzzles'):
            keys = runtime_test.title_keys(title)
            for step, key in enumerate(keys):
                client.key(key)
                time.sleep(.8)
                expect_hand(client, f'{title}: title step {step + 1}', seen)
            time.sleep(3)
            expect_hand(client, title, seen)
            client.key('Escape')
            time.sleep(1.5)
            expect_hand(client, f'back from {title}', seen)
    print(f'{renderer}: one hand cursor (64 px at 2x, hotspot {HOTSPOT}, dark edge) and no cursor change while moving, '
          f'across {len(seen["phases"])} views', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--web-root', type=Path)
    parser.add_argument('--base-url')
    args = parser.parse_args()
    assert bool(args.web_root) != bool(args.base_url), 'choose --web-root or --base-url'
    if args.web_root:
        with web.serve(args.web_root.resolve()) as url:
            for renderer in ('canvas', 'dom'):
                run(url, renderer)
    else:
        for renderer in ('canvas', 'dom'):
            run(args.base_url, renderer)


if __name__ == '__main__':
    main()

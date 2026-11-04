"""Web: Jungle's calm arrow and pointing hand in Canvas and DOM, in private headless Chromium.

  build-queue -- python3 tests/cursor_web_test.py --web-root PATH

At device pixel ratio 2, the element under the pointer shows the painted
arrow's CSS cursor over bare picture and the hand's only over something a click
does: the treehouse's items and its sound button. Each is a 64 px image-set
density image shown at 32 CSS pixels with its own hotspot, the same every
time, and nothing's cursor changes while the pointer moves within one kind of
target. In the bookshelf and games every point shows one of the two. Each
image's soft edge must be dark outline, never light.
"""
import argparse
import base64
import io
import re
import time
from pathlib import Path

from PIL import Image

import book_media_start_web_test as web
import cursor_desktop_test as desktop
import runtime_test

VIEW = (1280, 675)
HOTSPOTS = {'arrow': '%d %d' % desktop.ARROW[2:], 'hand': '%d %d' % desktop.HAND[2:]}
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


def kind(css):
    """'arrow' or 'hand' by the CSS cursor's hotspot, after its image."""
    match = re.search(r'\)\s+(\d+)\s+(\d+)\s*,', css) if 'url(' in css else None
    found = match and f'{match[1]} {match[2]}'
    return next((name for name, hotspot in HOTSPOTS.items() if hotspot == found), '')


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


def check(css, name, seen, phase):
    """The first time NAME shows, its density images are clean; it never changes."""
    if name not in seen:
        pictures = images(css)
        sizes = sorted(picture.size for picture in pictures)
        # At 2x the browser shows the 64 px density image at 32 CSS pixels.
        assert 'image-set(' in css and re.search(r'" ?\) 2(x|dppx)\)', css) and sizes == [(64, 64)], \
            ('no 2x density cursor', name, sizes, css[-60:])
        for picture in pictures:
            clean(picture)
        seen[name] = css
    assert css == seen[name], (name + ' cursor changed', phase)


def expect_at(client, name, phase, points, seen):
    """Every point shows NAME's cursor, settled once and unchanged while moving."""
    x, y = points[0]
    client.call('Input.dispatchMouseEvent', type='mouseMoved', x=x, y=y)
    deadline = time.monotonic() + 30
    while True:
        css = under(client, x, y)
        if kind(css) == name:
            break
        assert time.monotonic() < deadline, ('wrong cursor', phase, name, kind(css) or css[:80])
        time.sleep(.1)
    check(css, name, seen, phase)
    client.evaluate('cursorProbe.changes.length = 0')
    for x, y in list(points[1:]) * 2 + [points[0]]:
        for dx in (0, 2, -2):
            client.call('Input.dispatchMouseEvent', type='mouseMoved', x=x + dx, y=y + dx)
            time.sleep(.06)
            now = under(client, x + dx, y + dx)
            assert now == css, ('a different cursor under the pointer', phase, x + dx, y + dx, kind(now) or now[:80])
    changes = client.evaluate('cursorProbe.changes')
    assert not changes, ('cursor style changed while moving', phase, changes)
    seen.setdefault('phases', []).append(phase)


def application(client, phase, seen):
    """Every point shows one of the two application cursors, steady at rest."""
    for x, y in POINTS:
        client.call('Input.dispatchMouseEvent', type='mouseMoved', x=x, y=y)
        time.sleep(.35)
        css = under(client, x, y)
        name = kind(css)
        assert name, ('not an application cursor', phase, x, y, css[:80])
        check(css, name, seen, phase)
        for _ in range(3):
            time.sleep(.06)
            assert under(client, x, y) == css, ('cursor flickered at rest', phase, x, y)
    seen.setdefault('phases', []).append(phase)


def run(base_url, renderer):
    seen = {}
    pointing, calm, sound = desktop.treehouse_targets(*VIEW)
    with web.browser() as client:
        client.call('Emulation.setDeviceMetricsOverride', width=VIEW[0], height=VIEW[1], deviceScaleFactor=2, mobile=False)
        client.call('Page.navigate', url=base_url.rstrip('/') + '/' + renderer + '.html')
        client.until('typeof Module!=="undefined"&&!!Module.FS&&document.getElementById("loading").style.display==="none"',
                     'wasm startup', 90)
        client.evaluate(WATCH)
        time.sleep(1.5)
        # Alternate so every switch is a change of the pointed target.
        expect_at(client, 'arrow', 'treehouse: bare picture', calm, seen)
        expect_at(client, 'hand', 'treehouse: items', pointing, seen)
        expect_at(client, 'arrow', 'treehouse: bare picture again', calm[::-1], seen)
        expect_at(client, 'hand', 'treehouse: sound button', [sound], seen)
        expect_at(client, 'arrow', 'treehouse: bare picture after the button', calm[:2], seen)
        for title in ('Picture Book', 'Jigsaw Puzzles'):
            for key in runtime_test.title_keys(title):
                client.key(key)
                time.sleep(.8)
            time.sleep(3)
            application(client, title, seen)
            client.key('Escape')
            time.sleep(1.5)
            application(client, f'back from {title}', seen)
    assert seen['arrow'] != seen['hand']
    print(f'{renderer}: the arrow (hotspot {HOTSPOTS["arrow"]}) over bare picture and the hand (hotspot '
          f'{HOTSPOTS["hand"]}) only over clickable targets, 64 px at 2x with a dark edge, no cursor change '
          f'while moving, across {len(seen["phases"])} views', flush=True)


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

"""Web: the world map opens from the map button, lights and travels, and Back returns.

  build-queue -- python3 tests/world_map_web_test.py --web-root build/web
  # When Chromium cannot start in the private environment:
  build-queue -- python3 tests/world_map_web_test.py --web-root build/web --browser firefox
  # --hotspots PATH supplies the geometry matching an older prebuilt artifact.

In both renderers, in a private headless browser, landscape and portrait: the
treehouse shows the map button; it opens the painted map; hovering Campus lights
it and a click travels there; the darkness beyond the Desert stays on the map;
Back returns to Campus, where the map was opened. Python stdlib + PIL; no
desktop pixels and no Node.
"""
import argparse
import base64
import hashlib
import io
import json
import time
import traceback
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

import book_media_start_web_test as web
import runtime_test
from world_map_smoke_test import difference, has_button, map_fit, own_point, scene_keys, painted_map

ROOT = Path(__file__).resolve().parents[1]
web.WORK = runtime_test.run_folder('backup/world-map-web', create=False) / 'browser'
SIZES = ((1280, 675), (412, 915))
STARTED = 'typeof Module!=="undefined"&&!!Module.FS&&document.getElementById("loading").style.display==="none"'
EXPLORED = """(() => {
  for (const name of Module.FS.readdir('/kryon-apps')) {
    if (name === '.' || name === '..') continue;
    try { return Module.FS.readFile('/kryon-apps/' + name + '/settings/explored.txt', {encoding:'utf8'}) } catch (e) {}
  }
  return '';
})()"""


def shot(client):
    data = client.call('Page.captureScreenshot', format='png')['data']
    with Image.open(io.BytesIO(base64.b64decode(data))) as picture:
        return picture.convert('RGB')


def run(base_url, renderer, w, h, browser='chromium', metadata=None):
    output = web.WORK.parent / f'{browser}-{renderer}-{w}x{h}'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'receipt.json').unlink(missing_ok=True)
    print(f'local world map web {browser} {renderer} {w}x{h}: starting private browser', flush=True)
    metadata = metadata if metadata is not None else (ROOT / 'tools/title_hotspots.json').read_text()
    data = json.loads(metadata)
    world = next(s for s in data['scenes'] if s['name'] == 'map')
    view = world['portrait'] if h > w else world
    spots = {s['id']: s for s in view['hotspots']}
    scale, ox, oy = map_fit(view, (data['width'], data['height']), w, h)
    unit = runtime_test.title_unit(w, h)
    w_units = int(w / unit)
    button = (round((w_units - 96) * unit), round(6 * unit), round((w_units - 70) * unit), round(28 * unit))
    area = (10, round(40 * unit), w - 10, h - 10)

    def on_map(picture):
        areas = tuple(client.evaluate(EXPLORED).splitlines()[1:])
        plate = painted_map(view['image'], areas, metadata)
        plate = plate.resize((round(plate.width * scale), round(plate.height * scale)), Image.Resampling.BILINEAR)
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
            if time.monotonic() >= end:
                picture.save(output / 'failure.png')
                (output / 'input-failure.json').write_text(json.dumps(client.evaluate('''({
                    events: window.mapTestEvents,
                    viewport: [innerWidth, innerHeight, devicePixelRatio],
                    active: document.activeElement.id || document.activeElement.tagName,
                    canvas: document.getElementById('canvas').getBoundingClientRect().toJSON()
                })'''), indent=2) + '\n')
                if what.startswith('Back to Campus'):
                    # Diagnose whether the normal keyboard route is also
                    # blocked; the original failed pointer assertion remains.
                    client.key('Escape')
                    time.sleep(.5)
                    shot(client).save(output / 'escape-after-failure.png')
            assert time.monotonic() < end, (renderer, w, h, what)
            time.sleep(.2)

    def settled(client, what, seconds=10):
        """The map once its smooth images are ready: Kryon draws each with the
        browser's filter until its Lanczos copy is made, a slice a frame."""
        end = time.monotonic() + seconds
        picture = until(client, on_map, what)
        while True:
            time.sleep(.3)
            later = shot(client)
            if difference(picture, later, (0, 0, later.width, later.height)) < .05:
                return later
            assert time.monotonic() < end, (renderer, w, h, what, 'never settled')
            picture = later

    if browser == 'firefox':
        from private_firefox import browser as firefox_browser
        session = firefox_browser(web.WORK)
    else:
        session = web.browser()
    with session as client:
        client.call('Emulation.setDeviceMetricsOverride', width=w, height=h, deviceScaleFactor=1, mobile=False)
        client.call('Page.navigate', url=base_url.rstrip('/') + '/' + renderer + '.html')
        client.until(STARTED, 'wasm startup', 90)
        client.evaluate('''(() => {
            window.mapTestEvents = [];
            window.mapTestFrames = 0;
            const frame = () => { mapTestFrames++; requestAnimationFrame(frame); };
            requestAnimationFrame(frame);
            for (const type of ['pointermove', 'pointerdown', 'pointerup', 'mousedown', 'mouseup', 'click']) {
                document.addEventListener(type, e => {
                    if (mapTestEvents.length >= 200) mapTestEvents.shift();
                    mapTestEvents.push({type, x:e.clientX, y:e.clientY, button:e.button,
                        buttons:e.buttons, target:e.target.id || e.target.tagName, trusted:e.isTrusted,
                        time:performance.now(), frame:mapTestFrames});
                }, true);
            }
            return true;
        })()''')
        time.sleep(1.5)
        rest = lambda: client.call('Input.dispatchMouseEvent', type='mouseMoved', x=w // 2, y=h - 3)
        for key in scene_keys(data, 'campus'):
            client.key(key)
            time.sleep(.6)
        rest()
        time.sleep(.6)
        campus = shot(client)
        campus.save(output / 'campus.png')
        assert has_button(campus, button), (renderer, w, h, 'no map button on Campus')
        client.click((w_units - 83) * unit, 17 * unit)
        shown = until(client, on_map, 'the map')
        shown.save(output / 'map.png')
        client.click(28 * unit, 21 * unit)
        rest()
        until(client, lambda p: difference(p, campus, area) < 8, 'Back to Campus before locked landmark')
        client.click((w_units - 83) * unit, 17 * unit)
        shown = until(client, on_map, 'map reopened after Back')
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
        # A new visit clears its terrain, and IndexedDB keeps it after reload.
        initial = client.evaluate(EXPLORED)
        assert 'port\n' not in initial
        client.click((w_units - 83) * unit, 17 * unit)
        cloudy = until(client, on_map, 'map before Port visit')
        cloudy.save(output / 'before-visit.png')
        client.click(*centre('port'))
        client.until(f'{EXPLORED}.includes("port\\n")', 'genuine Port visit saved', 15)
        time.sleep(1)
        client.click((w_units - 83) * unit, 17 * unit)
        clear = settled(client, 'map after Port visit')
        clear.save(output / 'after-visit.png')
        box = tuple(round(v) for v in (ox + 40 * scale, oy + 190 * scale, ox + 620 * scale, oy + 380 * scale))
        cloud_difference = difference(cloudy, clear, box)
        assert cloud_difference > 4, (renderer, w, h, 'Port clouds did not clear', cloud_difference)
        saved = client.evaluate(EXPLORED)
        (output / 'input.json').write_text(json.dumps(client.evaluate('window.mapTestEvents'), indent=2) + '\n')
        client.call('Page.reload', ignoreCache=False)
        client.until(STARTED, 'reload startup', 90)
        client.until(f'{EXPLORED} === {json.dumps(saved)}', 'visited areas after reload', 15)
        time.sleep(1)
        client.click((w_units - 83) * unit, 17 * unit)
        reopened = settled(client, 'map after reload')
        reopened.save(output / 'after-reload.png')
        reload_difference = difference(clear, reopened, box)
        assert reload_difference < 2, (renderer, w, h, 'clouds returned after reload', reload_difference)
        (output / 'receipt.json').write_text(json.dumps(dict(browser=browser, renderer=renderer, width=w, height=h,
            geometry_sha256=hashlib.sha256(metadata.encode()).hexdigest(),
            cloud_difference=cloud_difference, reload_difference=reload_difference, explored=saved), indent=2) + '\n')
    print(f'local world map web {browser} {renderer} {w}x{h}: button, map, hover, travel, locked darkness, Back, cloud clearing and reload persistence passed', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--web-root', type=Path, default=ROOT / 'build/web')
    parser.add_argument('--browser', choices=('chromium', 'firefox'), default='chromium')
    parser.add_argument('--hotspots', type=Path, default=ROOT / 'tools/title_hotspots.json',
                        help='Geometry matching the tested web artifact')
    args = parser.parse_args()
    metadata = args.hotspots.read_text()
    runtime_test.run_folder(web.WORK.parent.parent)
    print(f'local world map web captures: {web.WORK.parent}', flush=True)
    (web.WORK.parent / 'geometry-used.json').write_text(metadata)
    artifacts = {}
    for name in ('canvas.html', 'dom.html', 'jungle.js', 'jungle-dom.js', 'jungle.wasm', 'jungle-dom.wasm'):
        path = args.web_root / name
        digest = hashlib.sha256()
        with path.open('rb') as artifact:
            for chunk in iter(lambda: artifact.read(1024 * 1024), b''):
                digest.update(chunk)
        artifacts[name] = digest.hexdigest()
    (web.WORK.parent / 'run-input.json').write_text(json.dumps(dict(browser=args.browser,
        web_root=str(args.web_root.resolve()), hotspots=str(args.hotspots.resolve()),
        geometry_sha256=hashlib.sha256(metadata.encode()).hexdigest(), artifacts=artifacts), indent=2) + '\n')
    failures = []
    results = []
    with web.serve(args.web_root.resolve()) as url:
        for renderer in ('canvas', 'dom'):
            for w, h in SIZES:
                try:
                    run(url, renderer, w, h, args.browser, metadata)
                    results.append(dict(renderer=renderer, width=w, height=h, status='passed'))
                except Exception as error:
                    failures.append(f'{args.browser} {renderer} {w}x{h}: {type(error).__name__}: {error}')
                    output = web.WORK.parent / f'{args.browser}-{renderer}-{w}x{h}'
                    (output / 'failure.txt').write_text(traceback.format_exc())
                    results.append(dict(renderer=renderer, width=w, height=h, status='failed', error=str(error)))
                    print(f'LOCAL TEST FAILED: {failures[-1]} (captures in {output})', flush=True)
    (web.WORK.parent / 'summary.json').write_text(json.dumps(dict(browser=args.browser,
        completed_at=time.time(), results=results), indent=2) + '\n')
    assert not failures, '\n'.join(failures)


if __name__ == '__main__':
    main()

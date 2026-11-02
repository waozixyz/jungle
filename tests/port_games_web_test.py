"""Actual Fishing/Crab painting in fresh, private Canvas and DOM browsers.

The application must request the images itself. This test never preloads or
fetches them, so an Image widget showing only its fallback label fails.
"""
import argparse
import base64
import io
import json
import os
from pathlib import Path
import time

from PIL import Image, ImageStat
import book_media_start_web_test as driver

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'work/port-games-web'
CAPTURES = Path(os.environ.get('JUNGLE_TEST_OUTPUT', WORK/'captures'))
GAMES = (
    ('Little Fishing Boat', ('fishing/background.webp', 'fishing/boat.webp')),
    ('Crab Family Counting', ('beach_families/background.webp', 'beach_families/crab-adult.webp')),
)


def route(data, wanted):
    names = [scene['name'] for scene in data['scenes']]
    paths, queue = {0: []}, [0]
    while queue:
        at = queue.pop(0)
        for index, item in enumerate(data['scenes'][at]['hotspots']):
            kind, _, target = item['target'].partition(':')
            path = paths[at] + [str(index + 1)]
            if kind == 'game' and target == wanted:
                return ['Home'] + path
            if kind == 'scene' and names.index(target) not in paths:
                destination = names.index(target)
                paths[destination] = path
                queue.append(destination)
    raise AssertionError('No painted route to ' + wanted)


def screenshot(client):
    payload = client.call('Page.captureScreenshot', format='png')['data']
    return Image.open(io.BytesIO(base64.b64decode(payload))).convert('RGB')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--web-root', type=Path, default=Path(os.environ.get('JUNGLE_WEB_ROOT', ROOT/'build/web')))
    args = parser.parse_args()
    root = args.web_root.resolve()
    metadata = root/'benchmark-catalog.json'
    data = (json.loads(metadata.read_text())['titleScenes'] if metadata.is_file()
            else json.loads((ROOT/'tools/title_hotspots.json').read_text()))
    WORK.mkdir(parents=True, exist_ok=True)
    CAPTURES.mkdir(parents=True, exist_ok=True)
    driver.WORK = WORK/'profiles'
    results = []
    with driver.serve(root) as base:
        for renderer in ('canvas', 'dom'):
            for width, height in ((960, 600), (420, 900)):
                # Each game starts cold at the title. Home navigates title
                # scenes; it does not leave an active activity.
                for title, paths in GAMES:
                    with driver.browser() as client:
                        client.call('Emulation.setDeviceMetricsOverride', width=width, height=height,
                                    deviceScaleFactor=1, mobile=False)
                        client.call('Page.navigate', url=base+'/'+renderer+'.html')
                        client.until('typeof Module!=="undefined"&&Module.FS&&document.getElementById("loading").style.display==="none"',
                                     'WASM startup', seconds=60)
                        for key in route(data, title):
                            client.key(key)
                        name = f'{renderer}-{width}-{title.lower().replace(" ", "-")}.png'
                        target = CAPTURES/name
                        screenshot(client).save(target)
                        try:
                            files = ['assets/'+path for path in paths]
                            client.until('('+json.dumps(files)+').every(p=>Module.FS.analyzePath("/"+p).exists)',
                                         title+' automatically requested its actual pictures', seconds=30)
                            if renderer == 'dom':
                                client.until('''(()=>{const images=[...document.querySelectorAll('#kryon-dom-paint img')]
                                    .filter(i=>{const r=i.getBoundingClientRect();return r.width>100&&r.height>80});
                                    return images.length>=2&&images.every(i=>i.complete&&i.naturalWidth>0)})()''',
                                             title+' painted DOM images decoded')
                            time.sleep(.4)
                            image = screenshot(client)
                            image.save(target)
                            area = image.crop((width//8, height//3, width*7//8, height*3//4)).resize((240, 160))
                            colors = len(area.getcolors(38401) or [])
                            deviation = max(ImageStat.Stat(area).stddev)
                            assert colors > 2000 and deviation > 15, (title, renderer, 'painting absent', colors, deviation)
                            results.append(dict(title=title, renderer=renderer, size=[width, height],
                                                automatically_loaded=files, colors=colors, screenshot=name))
                            print(f'local port painting: {title}, {renderer}, {width}x{height} passed', flush=True)
                        except Exception:
                            screenshot(client).save(target)
                            raise
    (WORK/'receipt.json').write_text(json.dumps(dict(version=json.loads((root/'version.json').read_text()),
                                                   cases=results), indent=2)+'\n')


if __name__ == '__main__':
    main()

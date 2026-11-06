"""Tap the actual Farm's two labelled routes through the portable app bridge."""
import json
from pathlib import Path
import tempfile
import time

from PIL import Image, ImageChops, ImageStat
import runtime_test as rt
from farm_smoke_test import FarmUI, cover, centered
from world_map_smoke_test import scene_keys


def main():
    scratch = rt.run_folder('backup/farm-navigation')
    rt.OUTPUT = scratch / 'captures'
    data = json.loads((rt.ROOT / 'tools/title_hotspots.json').read_text())
    scenes = {s['name']: s for s in data['scenes']}
    receipt = []
    for w, h in ((960, 600), (420, 900)):
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            state = Path(folder)
            (state / 'guide-seen.txt').write_text('yes\n')
            (state / 'sound.txt').write_text('off\n')
            old = state / 'games/jungle.garden/garden.txt'
            old.parent.mkdir(parents=True)
            legacy = 'owner garden remains unchanged\n'
            old.write_text(legacy)
            with rt.Desktop(rt.ROOT / 'build/app/jungle', state, screen_size='1280x1100') as d:
                d.resize(w, h)
                ui = FarmUI(d, w, h)
                def enter_scene(name, tag):
                    # A cold AVIF scene can still display the previous plate
                    # while loading. Confirm the intended canonical backdrop
                    # before recording a reference or claiming an origin.
                    scene = scenes[name]['portrait'] if h > w else scenes[name]
                    with Image.open(rt.ROOT / scene['image']) as source:
                        plate = source.convert('RGB')
                    scale = (min if name == 'campus' and h > w else max)(w / plate.width, h / plate.height)
                    pw, ph = round(plate.width * scale), round(plate.height * scale)
                    ox, oy = (w - pw) // 2, (h - ph) // 2
                    expected = Image.new('RGB', (w, h))
                    expected.paste(plate.resize((pw, ph), Image.Resampling.BILINEAR), (ox, oy))
                    box = (max(5, ox+5), max(80, oy+5), min(w-5, ox+pw-5), min(h-5, oy+ph-5))
                    for attempt in range(2):
                        for key in scene_keys(data, name):
                            d.key(key)
                            time.sleep(.35)
                        end = time.monotonic() + 5
                        while time.monotonic() < end:
                            picture = d.capture_actual(tag)
                            error = max(ImageStat.Stat(ImageChops.difference(expected, picture).crop(box)).mean)
                            if error < 25:
                                return picture
                            time.sleep(.15)
                    raise AssertionError((name, 'canonical scene did not load', error))
                references = {}
                for name in ('campus', 'market'):
                    references[name] = enter_scene(name, f'{w}-{name}-reference')
                distinct = max(ImageStat.Stat(ImageChops.difference(references['campus'], references['market'])).mean)
                assert distinct > 25, ('Campus and Market references are not distinct', distinct)
                # Enter from either origin: returning must follow the sign,
                # rather than the scene remembered when the game was opened.
                for origin in ('market', 'campus'):
                    for target in ('campus', 'market'):
                        enter_scene(origin, f'{w}-{origin}-origin-before-{target}')
                        entry = next(i for i, s in enumerate(scenes[origin]['hotspots']) if s['target'] == 'game:Farm')
                        d.key(str(entry + 1))
                        time.sleep(.4)
                        d.capture_actual(f'{w}-{origin}-farm-before-{target}')
                        ui.layout(True)
                        if target == 'campus':
                            scene = scenes['farm']['portrait'] if h > w else scenes['farm']
                            sign = next(s for s in scene['hotspots'] if s['id'] == 'campus-path')
                            assert sign['target'] == 'scene:campus' and sign['sign']['label'] == 'Campus'
                            x, y, bw, bh = sign['glow_rect']
                            lx, ly, lw, lh = sign['sign']['label_rect']
                            # Current sign polygon/label are generated from the
                            # same editable board. Transform its label centre.
                            import math
                            angle = math.radians(sign.get('rotation', 0))
                            px, py = lx + lw / 2 - bw / 2, ly + lh / 2 - bh / 2
                            px, py = x + bw / 2 + px * math.cos(angle) - py * math.sin(angle), y + bh / 2 + px * math.sin(angle) + py * math.cos(angle)
                            iw, ih = scene.get('width', data['width']), scene.get('height', data['height'])
                            scale, pw, ph = cover(ui.lw, ui.lh, iw, ih)
                            ui.logical_move(centered(ui.lw, pw) + px * scale, centered(ui.lh, ph) + py * scale)
                            ui.logical(centered(ui.lw, pw) + px * scale, centered(ui.lh, ph) + py * scale)
                        else:
                            ui.market_path()
                        time.sleep(.7)
                        rt.run(['xdotool', 'mousemove', '--window', d.window, str(w // 2), str(h - 2)], d.env)
                        box = (5, 80, w - 5, h - 5)
                        end = time.monotonic() + 8
                        while True:
                            actual = d.capture_actual(f'{w}-{origin}-farm-to-{target}')
                            error = max(ImageStat.Stat(ImageChops.difference(references[target], actual).crop(box)).mean)
                            if error < 1 or time.monotonic() >= end:
                                break
                            time.sleep(.15)
                        assert error < 1, (w, h, origin, target, 'wrong destination', error)
                        receipt.append(dict(size=[w, h], origin=origin, sign=target, destination=target, mean_error=error))
                assert old.read_text() == legacy
                assert (state / 'sound.txt').read_text() == 'off\n'
            print(f'local native Farm {w}x{h}: actual Campus and Market sign taps from both origins reach their labelled scenes; legacy save preserved', flush=True)
    (scratch / 'verification.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()

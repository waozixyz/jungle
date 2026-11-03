"""Render migrated artwork at full window size on an owned private Xvfb."""
import json
import os
from pathlib import Path
import tempfile
import subprocess
import time

from PIL import Image, ImageStat, ImageChops
import runtime_test as rt

ROOT = rt.ROOT
OUTPUT = Path(os.environ.get('JUNGLE_WEBP_SMOKE_OUTPUT', ROOT / 'local/art-development/webp-standard/smoke'))
GAMES = ('Animal Counting', '123 Book', 'ABC Book', 'Coloring Book',
         'Shapes & Sorting', 'Hide & Seek', 'Matching Pairs', 'Music Room', 'Farm')


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rt.OUTPUT = OUTPUT
    captures = []
    with tempfile.TemporaryDirectory(dir=OUTPUT) as folder:
        data = Path(folder)
        (data/'sound.txt').write_text('off\n')
        (data/'guide-seen.txt').write_text('yes\n')
        slugs = [row['slug'] for row in json.loads((ROOT/'tools/collectibles.json').read_text())['collectibles']]
        (data/'collection.txt').write_text('JUNGLE COLLECTION 1\n'+'\n'.join(slugs)+'\n')
        native = OUTPUT/'native'
        native.mkdir(exist_ok=True)
        extra = {'TMPDIR': str(data), 'ZIRAN_NATIVE_DIR': str(native)}
        env = rt.environment() | extra | {'JUNGLE_DATA': str(data)}
        result = subprocess.run([str(ROOT/'build/app/jungle'), '--check'], env=env,
                                capture_output=True, text=True, check=True)
        output = result.stdout + result.stderr
        (OUTPUT/'native-validation.log').write_text(output)
        assert 'cannot run' not in output, output[-2000:]
        assert output.count('runs here') >= 13, output[-2000:]
        with rt.Desktop(ROOT/'build/app/jungle', data, extra_env=extra, screen_size='1800x1800') as desktop:
            for width, height in ((1536, 1024), (900, 1600)):
                desktop.resize(width, height)
                for title in GAMES:
                    for _ in range(3):
                        desktop.key('Escape')
                    desktop.key('Home')
                    home = desktop.capture_actual('home-before-game')
                    if title == 'Farm' and not any(
                        h['target']=='game:Farm' for scene in json.loads((ROOT/'tools/title_hotspots.json').read_text())['scenes']
                        for h in scene['hotspots']):
                        scenes = json.loads((ROOT/'tools/title_hotspots.json').read_text())['scenes']
                        desktop.key('Home')
                        for scene, target in ((scenes[0], 'scene:campus'),
                                              (next(s for s in scenes if s['name']=='campus'), 'scene:farm')):
                            desktop.key(str(next(i+1 for i,h in enumerate(scene['hotspots']) if h['target']==target)))
                    else:
                        desktop.game(title)
                    if title == 'Animal Counting':
                        desktop.key('1')
                    if title == '123 Book':
                        desktop.key('4')
                    if title == 'Coloring Book':
                        from paint_geometry import scene_click
                        desktop.wait_scene_picker(f'{width}-scene-picker')
                        scene_click(desktop)
                    time.sleep(1)
                    name = f'{width}-{title.lower().replace(" ", "-").replace("&", "and")}'
                    picture = desktop.capture_actual(name)
                    assert picture.size == (width, height), (title, picture.size)
                    assert max(ImageStat.Stat(picture).stddev) > 25, (title, 'missing artwork')
                    region = (0, height//6, width, height*2//3)
                    assert max(ImageStat.Stat(ImageChops.difference(
                        home.crop(region), picture.crop(region))).mean) > 8, (title, 'game did not open')
                    captures.append(name)
                    print(f'local WebP smoke: {title}, {width}x{height}, rendered and alive', flush=True)
                for _ in range(3):
                    desktop.key('Escape')
                desktop.key('Home')
                unit = rt.title_unit(width, height)
                desktop.click_actual(round(width - 51*unit), round(17*unit))
                time.sleep(1)
                captures.append(f'{width}-collectibles')
                desktop.capture_actual(captures[-1])
                # Open each collectible cutout full size from the grid.
                columns = min(5, max(2, width // 150))
                rows = max(1, (height - 188) // 130)
                cell_width = (width - 24) // columns
                cell_height = min(190, (height - 180) // rows)
                for index in (6, 9, 10):
                    desktop.click_actual(12 + (index % columns)*cell_width + cell_width//2,
                                         130 + (index // columns)*cell_height + cell_height//2)
                    time.sleep(.5)
                    captures.append(f'{width}-collectible-{index}')
                    desktop.capture_actual(captures[-1])
                    desktop.key('Escape')
                desktop.key('Escape')
            desktop.alive()
        assert 'cannot run natively' not in (OUTPUT/'jungle.log').read_text()
    (OUTPUT/'captures.json').write_text(json.dumps(captures, indent=2)+'\n')
    # Contact sheets aid navigation; full-resolution captures are retained above.
    for width in (1536, 900):
        selected = [name for name in captures if name.startswith(str(width))]
        sheet = Image.new('RGB', (4*384, ((len(selected)+3)//4)*384), '#f5eddc')
        for index, name in enumerate(selected):
            picture = Image.open(OUTPUT/(name+'.png')).convert('RGB')
            picture.thumbnail((384, 360))
            sheet.paste(picture, ((index%4)*384, (index//4)*384))
        sheet.save(OUTPUT/f'{width}-overview.webp', lossless=True)
    print(f'local WebP smoke: {len(captures)} full-resolution captures retained in {OUTPUT}', flush=True)


if __name__ == '__main__':
    main()

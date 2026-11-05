"""Render migrated artwork at full window size on an owned private Xvfb."""
import json
import argparse
import os
from pathlib import Path
import tempfile
import re
import subprocess
import sys
import time

from PIL import Image, ImageStat, ImageChops
import runtime_test as rt

ROOT = rt.ROOT
sys.path.insert(0, str(ROOT/'tools'))
from avif_codec import save_avif
from book_catalog import WORDS
OUTPUT = Path(os.environ.get('JUNGLE_AVIF_SMOKE_OUTPUT', ROOT / 'local/art-development/avif-standard/smoke'))
GAMES = ('Animal Counting', 'Picture Book', '123 Book', 'ABC Book', 'Coloring Book',
         'Jigsaw Puzzles', 'Little Piano', 'Shapes & Sorting', 'Hide & Seek',
         'Matching Pairs', 'Music Room', 'Farm', 'Little Fishing Boat', 'Crab Family Counting')


def wait_title(desktop, title):
    deadline = time.monotonic() + 45
    words = ''
    while time.monotonic() < deadline:
        picture = desktop.capture_actual('opening-game')
        header = OUTPUT/'opening-header.png'
        # Read the centered title alone; corner icons confuse OCR's digits.
        picture.crop((picture.width//4, 0, picture.width*3//4, 56)).resize(
            (picture.width, 112), Image.Resampling.LANCZOS).save(header)
        words = subprocess.run(['tesseract', str(header), 'stdout', '--psm', '7'],
                               capture_output=True, text=True, check=True).stdout
        if title.casefold() in words.casefold():
            return
        time.sleep(.3)
    raise AssertionError((title, 'game did not reach its own title bar', words))


def wait_book_art(desktop):
    """Identify the visible word, then compare its painting with approved pixels."""
    deadline = time.monotonic() + 25
    words, error = '', None
    while time.monotonic() < deadline:
        picture = desktop.capture_actual('opening-book-page')
        # Read the caption strip from the page's lower quarter to the window's
        # bottom (landscape draws it on the page, portrait below it); the whole
        # frame's painting detail hides the word from OCR.
        width, height = picture.size
        edge = min(width, height - 56)
        left, top = (width-edge)//2, 56+(height-56-edge)//2
        caption = OUTPUT/'opening-book-caption.png'
        picture.crop((left, top+edge*3//4, left+edge, height)).save(caption)
        words = subprocess.run(['tesseract', str(caption), 'stdout', '--psm', '6'],
                               capture_output=True, text=True, check=True).stdout
        found = set(re.findall(r"[^\W\d_]+", words.casefold()))
        for name, translations in WORDS.items():
            path = ROOT/f'assets/jungle-book/pages/{name}.avif'
            if not set(translations[0].casefold().split()) <= found or not path.exists():
                continue
            width, height = picture.size
            edge = min(width, height - 56)
            left, top = (width-edge)//2, 56+(height-56-edge)//2
            region = (edge//10, edge//10, edge*9//10, edge*11//20)
            with Image.open(path) as source:
                expected = source.convert('RGB').resize((edge, edge), Image.Resampling.BILINEAR).crop(region)
            actual = picture.crop((left+region[0], top+region[1], left+region[2], top+region[3]))
            error = max(ImageStat.Stat(ImageChops.difference(actual, expected)).mean)
            if error < 12:
                desktop.key('space')
                print(f'local AVIF book: approved {name} pixels rendered, mean channel error {error:.2f}', flush=True)
                return
        time.sleep(.3)
    raise AssertionError(('AVIF picture-book painting did not match its source', words, error))


def farm_picture(desktop, ui, entrance):
    from farm_smoke_test import cover, centered
    portrait = ui.h > ui.w
    path = ('assets/garden/art/scene-' if entrance else 'assets/garden/play/garden-')
    path += ('portrait' if portrait else 'landscape')+'.avif'
    with Image.open(ROOT/path) as painting:
        source = painting.convert('RGB')
    scale, w, h = cover(ui.lw, ui.lh, *source.size)
    ox, oy = centered(ui.lw, w), centered(ui.lh, h)
    boxes = (((350,220,430,300),(410,1300,500,1400)) if portrait else
             ((450,600,550,720),(1450,300,1530,380))) if entrance else (
             ((580,180,680,250),(410,800,500,850)) if portrait else
             ((1300,280,1380,350),(700,560,820,640)))
    actual = desktop.capture_actual(f'{ui.w}-avif-farm-'+('chooser' if entrance else 'garden'))
    for box in boxes:
        region = tuple(round(((ox if i%2==0 else oy)+value*scale)*ui.scale)
                       for i,value in enumerate(box))
        expected = source.crop(box).resize((16,16), Image.Resampling.BILINEAR)
        shown = actual.crop(region).resize((16,16), Image.Resampling.BILINEAR)
        error = max(ImageStat.Stat(ImageChops.difference(expected, shown)).mean)
        assert error < 10, ('AVIF Farm painting differs from its source', path, box, error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=ROOT/'build/app/jungle')
    args = parser.parse_args()
    binary = args.binary.resolve()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rt.OUTPUT = OUTPUT
    captures = []
    with tempfile.TemporaryDirectory(dir=OUTPUT) as folder:
        data = Path(folder)
        (data/'sound.txt').write_text('off\n')
        (data/'guide-seen.txt').write_text('yes\n')
        slugs = [row['slug'] for row in json.loads((ROOT/'tools/collectibles.json').read_text())['collectibles']]
        (data/'collection.txt').write_text('JUNGLE COLLECTION 1\n'+'\n'.join(slugs)+'\n')
        awards = json.loads((ROOT/'tools/art_provenance/game-awards.json').read_text())['awards']
        (data/'awards.txt').write_text('JUNGLE AWARDS 1\n' + '\n'.join(row['award'] for row in awards) + '\n')
        native = OUTPUT/'native'
        native.mkdir(exist_ok=True)
        extra = {'TMPDIR': str(data), 'ZIRAN_NATIVE_DIR': str(native)}
        env = rt.environment() | extra | {'JUNGLE_DATA': str(data)}
        result = subprocess.run([str(binary), '--check'], env=env,
                                capture_output=True, text=True, check=True)
        output = result.stdout + result.stderr
        (OUTPUT/'native-validation.log').write_text(output)
        assert 'cannot run' not in output, output[-2000:]
        assert output.count('runs here') >= 13, output[-2000:]
        with rt.Desktop(binary, data, extra_env=extra, screen_size='1800x1800') as desktop:
            for width, height in ((1536, 1024), (900, 1600)):
                desktop.resize(width, height)
                for title in GAMES:
                    for _ in range(3):
                        desktop.key('Escape')
                    desktop.key('Home')
                    home = desktop.capture_actual('home-before-game')
                    desktop.game(title)
                    if title == 'Farm':
                        # Farm draws edge-to-edge without a title bar. Verify
                        # its approved chooser and garden paint independently.
                        from farm_smoke_test import FarmUI
                        ui = FarmUI(desktop, width, height)
                        deadline = time.monotonic()+30
                        while True:
                            try:
                                farm_picture(desktop, ui, True)
                                break
                            except AssertionError:
                                if time.monotonic() > deadline:
                                    raise
                                time.sleep(.3)
                        ui.garden(0)
                        time.sleep(.6)
                        farm_picture(desktop, ui, False)
                    else:
                        wait_title(desktop, title)
                    if title == 'Animal Counting':
                        desktop.key('1')
                    if title == 'Picture Book':
                        desktop.key('Return')
                        wait_book_art(desktop)
                    if title == '123 Book':
                        desktop.key('4')
                    if title == 'Jigsaw Puzzles':
                        desktop.wait_jigsaw_setup(f'{width}-jigsaw-pictures')
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
                    print(f'local AVIF smoke: {title}, {width}x{height}, rendered and alive', flush=True)
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
        save_avif(sheet, OUTPUT/f'{width}-overview.avif', lossless=True)
    print(f'local AVIF smoke: {len(captures)} full-resolution captures retained in {OUTPUT}', flush=True)


if __name__ == '__main__':
    main()

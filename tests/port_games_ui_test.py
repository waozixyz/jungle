"""Real port activities, isolated saves and owned Xvfb input.

Run after compiling both packed fixtures and the explicit title-host/jungle.
The fixture borrows two existing painted doors; production port navigation
remains subject to the owner's separate title-art choice.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unicodedata

import numpy as np
from PIL import Image
import runtime_test as rt

ROOT = rt.ROOT
WORK = ROOT / 'work/port-games-ui'
CAPTURES = Path(os.environ.get('JUNGLE_TEST_OUTPUT', WORK/'captures')).resolve()
HOST = ROOT / 'build/tests/title-host'
FISH = ('clownfish', 'blue-tang', 'butterflyfish', 'angelfish', 'parrotfish', 'pufferfish')


@contextmanager
def fixture():
    """Restore every changed test-host file, including on failed assertions."""
    assert (HOST / 'jungle').is_file(), 'compile the explicit title-host first'
    replacements = {
        HOST / 'games/catalog.txt': (
            'jungle-fishing.zx|Picture Book|Private fishing test|assets/jungle/covers/book.webp|2\n'
            'jungle-beach-families.zx|ABC Book|Private crab test|assets/jungle/covers/abc.webp|2\n').encode(),
        HOST / 'assets/shared-assets.txt': (
            '#jungle-shared-assets-1\nshared|assets/jungle/|\n'
            'shared|assets/collectibles/|\nshared|assets/previews/|\n').encode(),
        HOST / 'assets/speech.txt': b'#jungle-speech-1\n',
    }
    # All pictures are copied as binary files. No installed output is used.
    for folder in ('jungle', 'collectibles'):
        for source in (ROOT / 'assets' / folder).rglob('*'):
            if source.is_file():
                replacements[HOST / source.relative_to(ROOT)] = source
    for folder in ('fishing', 'beach_families'):
        for source in (ROOT / f'assets/{folder}/previews').glob('*.webp'):
            replacements[HOST / f'assets/previews/{folder}/{source.name}'] = source
    for bundle in ('jungle-fishing', 'jungle-beach-families'):
        source = ROOT / f'build/tests/{bundle}.zx'
        assert source.is_file(), f'compile packed fixture {source}'
        replacements[HOST / f'games/{bundle}.zx'] = source
    with tempfile.TemporaryDirectory(prefix='fixture-', dir=WORK) as directory:
        backup = Path(directory)
        saved = {}
        try:
            for index, (target, source) in enumerate(replacements.items()):
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    saved[target] = backup / str(index)
                    shutil.copy2(target, saved[target])
                else:
                    saved[target] = None
                if isinstance(source, bytes):
                    target.write_bytes(source)
                else:
                    shutil.copy2(source, target)
            yield
        finally:
            for target, original in saved.items():
                if original is None:
                    target.unlink(missing_ok=True)
                else:
                    shutil.copy2(original, target)


def layout(size):
    width, height = size
    height -= 56  # Actual shared host title bar.
    scale = min(width / 400, height / 640)
    if width > height:
        scale = min(height / 430, width / 760)
    scale = min(scale, 1.8)
    return scale, int(width / scale), int(height / scale)


def box(scale, x, y, width, height):
    return tuple(round(v) for v in (x * scale, 56 + y * scale,
                                   (x + width) * scale, 56 + (y + height) * scale))


def tap(d, scale, x, y):
    d.click_actual(round(x * scale), round(56 + y * scale))


def drag(d, scale, start, end):
    def move(point):
        rt.run(['xdotool', 'mousemove', '--window', d.window,
                str(round(point[0] * scale)), str(round(56 + point[1] * scale))], d.env)
        time.sleep(.15)
    move(start)
    rt.run(['xdotool', 'mousedown', '1'], d.env)
    try:
        time.sleep(.15)
        move(end)
    finally:
        rt.run(['xdotool', 'mouseup', '1'], d.env)
    time.sleep(.3)
    d.alive()


def art(picture, name, bounds, stretch=False):
    """Opaque picture interiors must match the shipped art, not a placeholder."""
    source = Image.open(ROOT / name).convert('RGBA')
    left, top, right, bottom = bounds
    width, height = right - left, bottom - top
    if not stretch:
        ratio = min(width / source.width, height / source.height)
        width, height = round(source.width * ratio), round(source.height * ratio)
        left += (right - left - width) // 2
        top += (bottom - top - height) // 2
    expected = np.asarray(source.resize((width, height), Image.Resampling.BILINEAR))
    actual = np.asarray(picture.crop((left, top, left + width, top + height)))
    mask = expected[:, :, 3] > 250
    # Keep away from interpolation/contain rounding at the subject boundary.
    mask[:3] = False; mask[-3:] = False; mask[:, :3] = False; mask[:, -3:] = False
    assert mask.sum() > 25, (name, 'no opaque art interior')
    error = np.abs(actual.astype(float) - expected[:, :, :3].astype(float))[mask].mean()
    assert error < 22, (name, bounds, 'art not loaded or wrong geometry', float(error))
    return float(error)


def words(picture, bounds, expected, label):
    path = CAPTURES / f'{label}-text.png'
    crop = picture.crop(bounds)
    crop.resize((crop.width * 2, crop.height * 2)).save(path)
    result = subprocess.run(['tesseract', str(path), 'stdout', '--psm', '6'],
                            check=True, text=True, capture_output=True, timeout=15).stdout
    (CAPTURES / f'{label}-ocr.txt').write_text(result)
    def normalize(text):
        return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold())
                       if not unicodedata.combining(c))
    assert normalize(expected) in normalize(result), (label, expected, result)


def saved(data, game):
    path = data / f'games/jungle.{game}/{game}.txt'
    assert path.is_file(), (game, 'host did not save')
    return path.read_text().split()


def wait_mask(d, data, mask):
    deadline = time.monotonic() + 16
    while time.monotonic() < deadline:
        d.alive()
        path = data / 'games/jungle.fishing/fishing.txt'
        if path.is_file() and path.read_text().split() == ['fishing1', str(mask)]:
            return
        time.sleep(.2)
    raise AssertionError(('catch did not save expected discovery', mask))


def fishing(d, data, size, language):
    scale, width, height = layout(size)
    scene_top, footer = 40, height - 112
    field = footer - scene_top
    d.game('Picture Book')
    time.sleep(.8)
    label = f'fishing-{language}-{size[0]}'
    idle = d.capture_actual(label + '-ready')
    # Background comparison excludes the boat and rod in the left third.
    source = Image.open(ROOT / 'assets/fishing/background.webp').convert('RGB')
    area = box(scale, 0, scene_top, width, field)
    expected = source.resize((area[2]-area[0], area[3]-area[1]), Image.Resampling.BILINEAR)
    actual = idle.crop(area)
    a, b = np.asarray(actual), np.asarray(expected)
    assert np.abs(a.astype(float)[:, int(a.shape[1]*.4):] - b.astype(float)[:, int(b.shape[1]*.4):]).mean() < 15
    edge = min(width, field)
    boat = min(edge * 42 // 100, width * 34 // 100)
    art(idle, 'assets/fishing/boat.webp', box(scale, width*180//1000-boat//2,
        scene_top+field//2-boat//2, boat, boat))
    words(idle, box(scale, 0, 0, width, scene_top),
          {'en': 'Tap the water', 'de': 'Tippe ins Wasser', 'es': 'Toca el agua'}[language], label+'-prompt')
    for index, species in enumerate(FISH):
        x = width * (220 + (index + .5) * 680 / 6) / 1000
        y = scene_top + field * .55
        tap(d, scale, x, y)
        if index == 0:
            cast = d.capture_actual(label+'-cast')
            drag(d, scale, (x, y), (x+width*.06, y+field*.06))
            moved = d.capture_actual(label+'-bobber-moved')
            assert np.abs(np.asarray(cast).astype(float)-np.asarray(moved).astype(float)).sum() > 2000
            tap(d, scale, x, y)
        elif index == 1:
            drag(d, scale, (x, y), (width*.24, scene_top+field*.5))
        elif index == 5:
            d.key('Right'); d.key('Left'); d.key('Return')
        else:
            tap(d, scale, x, y)
        wait_mask(d, data, (1 << (index+1))-1)
        card = d.capture_actual(label+'-catch-'+species)
        cw, ch = min(width-32, 440), min(field-20, 320)
        cx, cy = (width-cw)//2, scene_top+(field-ch)//2
        art(card, f'assets/fishing/{species}.webp', box(scale, cx+20, cy+40, cw-40, ch-90))
        if index == 0:
            words(card, box(scale, cx+12, cy+ch-46, cw-24, 36),
                  {'en':'Clownfish', 'de':'Clownfisch', 'es':'Pez payaso'}[language], label+'-species')
        if index == 5:
            d.key('Return')
        else:
            tap(d, scale, width*.7, scene_top+field*.7)
    assert saved(data, 'fishing') == ['fishing1', '63']
    # Test the actual shared Back control rather than only Escape handling.
    d.click_actual(24, 26)
    d.wait_menu(label+'-back')


def crab_point(width, height, count, index):
    spacing = (0, 300, 260, 210)[count-1]
    edge = min(width*(270,245,220,200)[count-1]//1000, (height-252)*65//100)
    x = width * (500 + (index*2-count+1)*spacing//2)//1000
    y = 128 + (height-252)*(560+count*15)//1000
    return x, y, edge


def crabs(d, data, size, language):
    scale, width, height = layout(size)
    label = f'crab-{language}-{size[0]}'
    d.game('ABC Book')
    time.sleep(.8)
    first = d.capture_actual(label+'-ready')
    words(first, box(scale, 24, 13, width-48, 58),
          {'en':'Crab Family', 'de':'Krabbenfamilie', 'es':'Familia de cangrejos'}[language], label+'-prompt')
    for count in range(1, 5):
        picture = d.capture_actual(label+f'-family-{count}')
        for index in range(count):
            x, y, edge = crab_point(width, height, count, index)
            small = edge*55//100 if index >= 2 else edge
            art(picture, 'assets/beach_families/crab-'+('baby' if index >= 2 else 'adult')+'.webp',
                box(scale, x-small//2, y-edge//2+edge-small, small, small))
        for index in range(count):
            x, y, _ = crab_point(width, height, count, index)
            if count == 4 and index == 1:
                # A process restart begins focus at the first crab. Move
                # once to select the second crab before counting it.
                d.key('Right'); d.key('Return')
            else:
                tap(d, scale, x, y)
            current = saved(data, 'beach_families')
            assert current[2] == str(count-1) and current[4:8].count('1') == index+1, current
            tap(d, scale, x, y)
            assert saved(data, 'beach_families') == current, 'duplicate crab tap counted twice'
            if count == 4 and index == 0:
                d.key('Escape'); d.wait_menu(label+'-partial-back')
                # Recreate only our owned process and display, with the same
                # isolated data. This proves a process restart, not just reentry.
                d.__exit__(None, None, None)
                d.__init__(HOST/'jungle', data, screen_size='1280x1100')
                d.__enter__()
                d.resize(*size)
                d.game('ABC Book')
                assert saved(data, 'beach_families') == current, 'partial round did not resume'
        done = saved(data, 'beach_families')
        time.sleep(.5)
        assert saved(data, 'beach_families') == done, 'family advanced without Next'
        d.capture_actual(label+f'-complete-{count}')
        if count < 4:
            if count == 2:
                d.key('Right'); d.key('Return')
            else:
                tap(d, scale, width/2, height-41)
            assert saved(data, 'beach_families')[2:4] == [str(count), str(count)], 'Next did not advance'
    d.click_actual(24, 26)
    d.wait_menu(label+'-back')


def reopen(data, size, label, language):
    with rt.Desktop(HOST/'jungle', data, screen_size='1280x1100') as d:
        d.resize(*size)
        d.game('Picture Book')
        time.sleep(.8)
        assert saved(data, 'fishing') == ['fishing1', '63']
        album = d.capture_actual(label+'-fishing-restarted')
        scale, width, height = layout(size)
        row = height-112+58
        cell, edge = (width-24)//6, min(height-row-3, 45)
        for index, species in enumerate(FISH):
            cx = 12+index*cell+cell//2
            art(album, f'assets/fishing/{species}.webp', box(scale, cx-edge//2, row, edge, edge))
        d.key('Escape'); d.wait_menu(label+'-restart-back')
        d.game('ABC Book')
        time.sleep(.8)
        assert saved(data, 'beach_families')[2:8] == ['3', '4', '1', '1', '1', '1']
        complete = d.capture_actual(label+'-crab-restarted')
        words(complete, box(scale, width/2-106, height-66, 212, 50),
              {'en':'New family', 'de':'Neue Familie', 'es':'Nueva familia'}[language], label+'-crab-resumed')


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    rt.OUTPUT = CAPTURES
    rt.OUTPUT.mkdir(exist_ok=True)
    with fixture():
        for language in ('en', 'de', 'es'):
            for size in ((420, 900), (960, 600)):
                with tempfile.TemporaryDirectory(prefix='save-', dir=WORK) as directory:
                    data = Path(directory)
                    (data/'language.txt').write_text(language)
                    (data/'sound.txt').write_text('off\n')
                    (data/'guide-seen.txt').write_text('yes\n')
                    with rt.Desktop(HOST/'jungle', data, screen_size='1280x1100') as d:
                        d.resize(*size)
                        fishing(d, data, size, language)
                        crabs(d, data, size, language)
                    reopen(data, size, f'{language}-{size[0]}', language)
                    print(f'local port gameplay: {language} {size[0]}x{size[1]} passed', flush=True)
    (WORK/'verification.json').write_text(json.dumps({
        'status':'local gameplay passed', 'host':str(HOST/'jungle'),
        'host_sha256':hashlib.file_digest((HOST/'jungle').open('rb'), 'sha256').hexdigest(),
        'sizes':[[420,900],[960,600]], 'languages':['en','de','es'],
        'entry':'test-fixture catalog aliases; production painted port entries not tested',
        'input':'owned private Xvfb mouse drag/tap and keyboard; no native touch injection',
    }, indent=2)+'\n')


if __name__ == '__main__':
    main()

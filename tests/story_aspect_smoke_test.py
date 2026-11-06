"""Measure story pages in the real app on a private display: every Bremen page
and some Sweet Porridge pages, in phone and desktop windows of both shapes.
Each painting must be drawn at its exact source shape, at the place the
reader's layout reserves for it, with the caption on the paper below it."""
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

from runtime_test import Desktop, ROOT
import runtime_test

SIZES = ((420, 900), (900, 420), (1280, 800), (1920, 1080))
BOOKS = (('2', 'town_musicians', range(11)), ('1', 'sweet_porridge', (0, 4, 9)))
RATIO_TOLERANCE = 0.005
BAR = 56  # host/jungle_menu.zi GAME_BAR_HEIGHT above every game


def layout(width, height, art_width, art_height):
    """games/book/story_layout.zi StoryPageLayout."""
    caption = 120 if width >= height else 140
    available = height - caption - 52
    span = width
    art = (span * art_height + art_width // 2) // art_width
    if art > available:
        art = available
        span = (available * art_width + art_height // 2) // art_height
    return (width - span) // 2, 0, span, art, caption


def gray(picture, half=True):
    data = np.asarray(picture.convert('L'), dtype=np.float32)
    if half:
        data = data[:data.shape[0] // 2 * 2, :data.shape[1] // 2 * 2]
        data = data.reshape(data.shape[0] // 2, 2, data.shape[1] // 2, 2).mean(axis=(1, 3))
    return data


def residual(shot, art, rect, shifts=3):
    """Lowest mean difference between the frame and ART drawn at RECT (in
    full window pixels), over small offsets, comparing the scene's inside."""
    x, y, w, h = rect
    drawn = gray(art.resize((max(2, round(w / 2)), max(2, round(h / 2))), Image.Resampling.BILINEAR), False)
    dh, dw = drawn.shape
    # The inside of the scene, clear of the Back control and its very edges.
    top, bottom, left, right = int(dh * .12), int(dh * .94), int(dw * .06), int(dw * .94)
    best = (1e9, 0, 0)
    for dy in range(-shifts, shifts + 1):
        for dx in range(-shifts, shifts + 1):
            oy, ox = round(y / 2) + dy + top, round(x / 2) + dx + left
            if oy < 0 or ox < 0 or oy + bottom - top > shot.shape[0] or ox + right - left > shot.shape[1]:
                continue
            error = float(np.abs(shot[oy:oy + bottom - top, ox:ox + right - left] - drawn[top:bottom, left:right]).mean())
            best = min(best, (error, dx * 2, dy * 2))
    return best


def measure(shot, art, guess):
    """The drawn width and height that best explain the frame, searched
    separately, so a stretched or squashed picture shows as a ratio change."""
    x, y, w, h = guess
    error = residual(shot, art, (x, y, w, h))[0]
    for step in (.01, .0025, .001):
        for _ in range(2):
            for axis in (0, 1):
                options = []
                for k in range(-4, 5):
                    nw = w * (1 + k * step) if axis == 0 else w
                    nh = h * (1 + k * step) if axis == 1 else h
                    found, dx, dy = residual(shot, art, (x, y, nw, nh))
                    options.append((found, nw, nh, dx, dy))
                error, w, h, dx, dy = min(options)
                x, y = x + dx, y + dy
    return (x, y, w, h), error


def main():
    output = ROOT / 'local/story-aspect-tests'
    output.mkdir(parents=True, exist_ok=True)
    results = []
    work = runtime_test.run_folder('work/bremen-aspect')
    captures = work / 'captures'
    shutil.rmtree(captures, ignore_errors=True)
    captures.mkdir(parents=True)
    with tempfile.TemporaryDirectory(dir=output) as folder:
        runtime_test.OUTPUT = captures
        with Desktop(ROOT / 'build/app/jungle', Path(folder), screen_size='2000x1300') as desktop:
            desktop.game('Sweet Porridge')
            # The Stories collection opens behind its loading screen.
            deadline = time.monotonic() + 30
            while True:
                desktop.capture('stories')
                words = subprocess.run(['tesseract', str(runtime_test.OUTPUT / 'stories.png'), 'stdout'],
                                       capture_output=True, text=True, check=True).stdout
                if 'Brem' in words and 'Stories' in words:
                    break
                if time.monotonic() > deadline:
                    shutil.copyfile(runtime_test.OUTPUT / 'stories.png', work / 'failed-stories.png')
                    raise AssertionError(('Stories collection did not open', words))
                time.sleep(.5)
            for key, name, pages in BOOKS:
                story = json.loads((ROOT / f'tools/{name}.json').read_text())['pages']
                desktop.key(key)
                time.sleep(1)
                desktop.key('space')  # Pause the story; walk the pages by hand.
                at = 0
                for width, height in SIZES:
                    desktop.resize(width, height)
                    assert desktop.actual_size == (width, height), (desktop.actual_size, width, height)
                    for page in pages:
                        while at < page:
                            desktop.key('Right'); at += 1
                        while at > page:
                            desktop.key('Left'); at -= 1
                        row = story[page]
                        portrait = height > width
                        if portrait:
                            painting = Image.open(ROOT / f"assets/jungle-book/portraits/{row['portrait_asset']}.avif").convert('RGB')
                            art = painting
                        else:
                            painting = Image.open(ROOT / f"assets/jungle-book/pages/{row['asset']}.avif").convert('RGB')
                            # paper_top is in painting pixels; the AVIF ships at 75%.
                            line = round(row['paper_top'] * painting.height / 1024)
                            art = painting.crop((0, 0, painting.width, line))
                        # The book is the window below the game bar.
                        lx, ly, lw, lh, caption = layout(width, height - BAR, art.width, art.height)
                        ly += BAR
                        # Wait for the full picture (its preview is blurrier).
                        deadline = time.monotonic() + 12
                        while True:
                            frame = desktop.capture_actual(f'{name}-{width}x{height}-{page}')
                            shot = gray(frame)
                            rect, error = measure(shot, art, (lx, ly, lw, lh))
                            if error < 9 or time.monotonic() > deadline:
                                break
                            time.sleep(.5)
                        drawn = rect[2] / rect[3]
                        source = art.width / art.height
                        pixels = np.asarray(frame, dtype=np.int16)
                        # Caption text sits on the paper below the scene.
                        top = round(rect[1] + rect[3])
                        band = pixels[top + 10:ly + lh + caption - 10, lx + 20:lx + lw - 20]
                        ink = int((band.mean(axis=2) < 110).sum())
                        # Margins beside the scene are the page's own paper.
                        paper = tuple(int(row['paper_color'][i:i + 2], 16) for i in (1, 3, 5))
                        margin = pixels[ly + lh + 4:height - 4, :max(lx - 2, 0)].reshape(-1, 3)
                        margin_error = float(np.abs(margin - paper).max()) if margin.size else 0.0
                        result = dict(book=name, page=page, window=[width, height], source_ratio=round(source, 4),
                                      drawn_ratio=round(drawn, 4), drawn=[round(v, 1) for v in rect],
                                      expected=[lx, ly, lw, lh], mean_error=round(error, 2), caption_ink=ink,
                                      margin_error=margin_error)
                        results.append(result)
                        print(json.dumps(result), flush=True)
                        if error >= 12 or abs(drawn / source - 1) > RATIO_TOLERANCE:
                            frame.save(work / f'failed-{name}-{width}x{height}-{page}.png')
                        assert abs(drawn / source - 1) <= RATIO_TOLERANCE, result
                        assert error < 12, ('Frame does not show the painting at its place', result)
                        assert abs(rect[0] - lx) <= 4 and abs(rect[1] - ly) <= 4, result
                        assert abs(rect[2] - lw) <= lw * .006 + 2 and abs(rect[3] - lh) <= lh * .006 + 2, result
                        assert ink > 150, ('No caption text on the paper below the scene', result)
                        assert margin_error <= 12, ('Margin paper does not match the page paper', result)
                for _ in range(at):
                    desktop.key('Left')
                desktop.key('Escape')
                time.sleep(1)
        if not os.environ.get('STORY_KEEP_CAPTURES'):
            shutil.rmtree(captures, ignore_errors=True)
    receipt = work / 'story-aspect-results.json'
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(results, indent=1) + '\n')
    worst = max(abs(r['drawn_ratio'] / r['source_ratio'] - 1) for r in results)
    print(f'local real-app aspect test passed: {len(results)} page views, worst drawn/source ratio difference {worst:.4%}, receipt {receipt}')


if __name__ == '__main__':
    main()

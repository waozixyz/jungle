#!/usr/bin/env python3
"""Independent layer fixtures and real portable UI, only private Xvfb/data."""
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from runtime_test import (ROOT, OUTPUT, Desktop, environment, DIGITS,
                          dinosaur_masks, picture_pixels, assert_dinosaur)
from paint_history_test import changed, history, open_paint, scenery

WORK = ROOT / 'work/paint-layers'
HEADER = b'JUNGLE PICTURE 3\n0e\n' + (b' ' * 38 + b'\n') * 8


def runs(pixels):
    flat = pixels.ravel()
    edges = np.r_[0, np.flatnonzero(flat[1:] != flat[:-1]) + 1, len(flat)]
    text = bytearray()
    for start, end in zip(edges[:-1], edges[1:]):
        value = int(flat[start])
        text.extend(b'~' if value == 255 else DIGITS[value].encode())
        length = int(end - start)
        while length >= 32:
            text.extend(DIGITS[32 + (length & 31)].encode())
            length >>= 5
        text.extend(DIGITS[length].encode())
    return bytes(text)


def fixture(objects):
    base = np.full((720, 960), 22, np.uint8)
    base[350:355] = 0
    canvas = base.copy()
    encoded, intervals = [], []
    for dino, size, x, y, color in objects:
        ink, body = dinosaur_masks(dino, size)
        pixels = np.where(ink, 0, np.where(body, color, 255)).astype(np.uint8)
        h, w = pixels.shape
        # First-fit intervals in the same bounded two-bank arena.
        storage = None
        for bank in range(2):
            candidate = bank * 960 * 720
            for left, right in sorted(intervals):
                if candidate < right and candidate + w * h > left:
                    candidate = right
            if candidate + w * h <= (bank + 1) * 960 * 720:
                storage = candidate
                break
        assert storage is not None, 'fixture exceeds supported pixel cap'
        intervals.append((storage, storage + w * h))
        encoded.append(f'{x} {y} {w} {h} {storage}\n'.encode() + runs(pixels) + b'\n')
        target = canvas[y:y+h, x:x+w]
        target[pixels != 255] = pixels[pixels != 255]
    return (HEADER + runs(canvas) + b'\n' + runs(base) + b'\n' +
            str(len(objects)).encode() + b'\n' + b''.join(encoded)), canvas, base


def pixel_click(desktop, x, y):
    # MainView's actual picture rectangle, scaled to Desktop's 320x200 view.
    width, height = desktop.actual_size
    height -= 56
    pad = max(6, min(20, min(width, height) // 40))
    gap = max(4, min(10, min(width, height) // 80))
    tool_h = (height - pad * 2 - gap * 7) // 8
    tool_w = max(64, min(tool_h * 5 // 2, width // 5))
    cw = width - pad * 3 - tool_w
    ch = cw * 3 // 4
    if ch > height - pad * 2:
        ch = height - pad * 2
        cw = ch * 4 // 3
    left = (width - tool_w - pad - cw) // 2 + tool_w + pad
    top = pad + (height - pad * 2 - ch) // 2
    desktop.click_actual(left + (x + .5) * cw / 960, 56 + top + (y + .5) * ch / 720)


def open_main(desktop, name):
    open_paint(desktop, name)
    # Read dimensions from this owned window's saved capture only.
    with Image.open(OUTPUT / (name + '.png')) as image:
        desktop.actual_size = image.size


def assert_pixels(path, expected):
    assert np.array_equal(picture_pixels(path.read_bytes()), expected), 'layer pixels changed'


def ui(language):
    objects = [(24, 2, 220, 170, 30), (24, 2, 235, 185, 40)]
    initial, both, base = fixture(objects)
    _, first, _ = fixture(objects[:1])
    # A hit safely inside the upper object's real painted body.
    ink, body = dinosaur_masks(24, 2)
    ys, xs = np.where(body & ~ink)
    pick = len(xs) // 2
    x, y = int(xs[pick]) + 235, int(ys[pick]) + 185
    with tempfile.TemporaryDirectory(prefix=f'{language}-', dir=WORK) as temporary:
        data = Path(temporary)
        (data / 'language.txt').write_text(language)
        folder = data / 'games/jungle.paint'
        folder.mkdir(parents=True)
        working = folder / 'working.txt'
        working.write_bytes(initial)
        (folder / 'slot-0.txt').write_bytes(initial)
        with Desktop(ROOT / 'build/app/jungle', data) as desktop:
            open_main(desktop, f'layers-{language}-open')
            assert_pixels(working, both)
            desktop.click(30, 87)  # selected Erase, with localized cue
            desktop.capture(f'layers-{language}-erase-cue', header=56)
            pixel_click(desktop, 20, 20)
            assert working.read_bytes() == initial and not (folder / 'working-undo.txt').exists(), 'empty erase changed history'
            pixel_click(desktop, x, y)
            changed(working, initial)
            assert_pixels(working, first)
            assert len(history(folder)) == 1
            desktop.key('Escape')
            desktop.wait_menu(f'layers-{language}-leave')
        with Desktop(ROOT / 'build/app/jungle', data) as desktop:
            open_main(desktop, f'layers-{language}-restart')
            desktop.click(30, 160)
            assert_pixels(working, both)
            # Slot loading and export/preview must keep all object pixels.
            desktop.click(30, 110)
            desktop.capture(f'layers-{language}-slot', header=56)
            previews = list(folder.glob('canvas-*.png'))
            palette = [int(v, 16) for v in __import__('re').findall(r'0x([0-9a-f]{8})', (ROOT / 'games/paint/paint_palette.zi').read_text())]
            rgb = np.array([[(v >> 24) & 255, (v >> 16) & 255, (v >> 8) & 255] for v in palette], np.uint8)[both]
            assert any(np.array_equal(np.asarray(Image.open(path).convert('RGB')), rgb) for path in previews), 'slot preview lost layers'
            desktop.click(210, 38)
            desktop.click(50, 80)
            assert_pixels(working, both)
            assert history(folder) == []
            desktop.click(30, 135)
            desktop.capture(f'layers-{language}-print', header=56)
            desktop.click(120, 104)
            desktop.capture(f'layers-{language}-export', header=56)
            exports = list((folder / 'exports').glob('*.png'))
            assert len(exports) == 1 and np.array_equal(np.asarray(Image.open(exports[0]).convert('RGB')), rgb), 'export lost layers'
            desktop.key('Escape')
            desktop.click(30, 87)
            pixel_click(desktop, x, y)
            assert_pixels(working, first)
            pixel_click(desktop, x, y)
            assert_pixels(working, base)
            # New picture retains its separate confirmation and Cancel flow.
            before = working.read_bytes()
            desktop.click(30, 185)
            desktop.capture(f'layers-{language}-new-confirm', header=56)
            desktop.click(240, 90)
            assert working.read_bytes() == before, 'cancelled new picture changed paint'
        print(f'local portable UI layers ({language}): erase, restart/undo, slots, preview/export and confirmed New picture passed', flush=True)


def budget_ui():
    cases = [('32-small', [(24, 1, 100, 100, 30)] * 32),
             ('large-overlap', [(0, 4, 0, 0, color) for color in (30, 50)] + [(24, 1, 300, 200, 35)] * 8),
             ('full-pixel-cap', [(14, 4, 0, 0, color) for color in (30, 50)])]
    for name, objects in cases:
        initial, pixels, _ = fixture(objects)
        _, after, _ = fixture(objects[:-1])
        ink, body = dinosaur_masks(objects[-1][0], objects[-1][1])
        ys, xs = np.where(body & ~ink)
        pick = len(xs) // 2
        x = int(xs[pick]) + objects[-1][2]
        y = int(ys[pick]) + objects[-1][3]
        with tempfile.TemporaryDirectory(prefix=name, dir=WORK) as temporary:
            data = Path(temporary)
            folder = data / 'games/jungle.paint'
            folder.mkdir(parents=True)
            working = folder / 'working.txt'
            working.write_bytes(initial)
            from paint_history_test import fnv
            sidecar = (b'JUNGLE UNDO 1\n' + f'{len(initial)} {fnv(initial):016x}\n8\n'.encode() +
                       (str(len(initial)).encode() + b'\n' + initial) * 8)
            (folder / 'working-undo.txt').write_bytes(sidecar)
            with Desktop(ROOT / 'build/app/jungle', data) as desktop:
                desktop.game('Coloring Book')
                desktop.key('Escape')
                desktop.wait_menu('layers-budget-immediate-exit-' + name)
                assert (folder / 'working-undo.txt').read_bytes() == sidecar, 'early exit replaced restoring history'
                open_main(desktop, 'layers-budget-' + name)
                if name == 'full-pixel-cap':
                    before_history = (folder / 'working-undo.txt').read_bytes()
                    desktop.click(30, 15)
                    desktop.click(52, 58)
                    desktop.click(52, 90)
                    desktop.capture('layers-over-cap-placement', header=56)
                    desktop.drag(72, 14, 102, 14)
                    assert working.read_bytes() == initial
                    assert (folder / 'working-undo.txt').read_bytes() == before_history, 'refused placement pushed history'
                desktop.click(30, 87)
                pixel_click(desktop, x, y)
                changed(working, initial)
                assert_pixels(working, after)
                desktop.click(30, 160)
                assert_pixels(working, pixels)
                # Choose Color to exit erase and fill the visible top object.
                desktop.click(30, 40)
                desktop.capture('layers-budget-colors', header=56)
                desktop.click(38, 40)
                pixel_click(desktop, x, y)
                filled = working.read_bytes()
                assert filled != initial, 'large visible fill did not change paint'
            with Desktop(ROOT / 'build/app/jungle', data) as desktop:
                open_main(desktop, 'layers-budget-restart-' + name)
                assert working.read_bytes() == filled
                desktop.click(30, 160)
                assert_pixels(working, pixels)
                desktop.click(30, 87)
                pixel_click(desktop, x, y)
                assert_pixels(working, after)
                for index in range(6):
                    (folder / f'slot-{index}.txt').write_bytes(initial)
                desktop.click(30, 110)
                desktop.capture('layers-heavy-six-previews-' + name, header=56)
                assert len(list(folder.glob('canvas-*.png'))) >= 6
            with (OUTPUT / 'jungle.log').open() as stream:
                stream.seek(0, 2)
                stream.seek(max(0, stream.tell() - 8000))
                log = stream.read(8000)
            assert 'stopped after' not in log.lower() and 'budget' not in log.lower(), log[-2000:]
            print('local portable VM budget: ' + name + ' load/erase/undo/fill/restart passed', flush=True)


def placement_ui():
    # A real Huge stencil is created by the UI on a legacy flattened base.
    base = np.full((720, 960), 22, np.uint8)
    original = HEADER.replace(b'PICTURE 3', b'PICTURE 2') + runs(base) + b'\n'
    with tempfile.TemporaryDirectory(prefix='placement-', dir=WORK) as temporary:
        data = Path(temporary)
        folder = data / 'games/jungle.paint'
        folder.mkdir(parents=True)
        working = folder / 'working.txt'
        working.write_bytes(original)
        with Desktop(ROOT / 'build/app/jungle', data) as desktop:
            open_main(desktop, 'layers-legacy-placement')
            desktop.click(30, 15)
            desktop.click(52, 58)
            desktop.click(280, 90)
            desktop.capture('layers-huge-placement', header=56)
            desktop.drag(72, 14, 102, 14)
            placed = changed(working, original)
            x, y = assert_dinosaur(original, placed)
            assert placed.startswith(b'JUNGLE PICTURE 3\n')
            desktop.key('Escape')
            desktop.wait_menu('layers-placement-menu')
        with Desktop(ROOT / 'build/app/jungle', data) as desktop:
            open_main(desktop, 'layers-placement-restored')
            ink, body = dinosaur_masks(0, 4)
            ys, xs = np.where(body & ~ink)
            pick = len(xs) // 2
            desktop.click(30, 87)
            pixel_click(desktop, int(xs[pick]) + x, int(ys[pick]) + y)
            changed(working, placed)
            assert_pixels(working, base)
            desktop.click(30, 160)
            assert_pixels(working, picture_pixels(placed))
        print('local portable UI placement: Huge stencil on legacy base, reopen, erase and Undo passed', flush=True)


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    subprocess.run(['make', '-s', '-j1', 'build/tests/paint_layers'], cwd=ROOT, env=environment(), check=True)
    subprocess.run([str(ROOT / 'build/tests/paint_layers')], env=environment(), check=True)
    placement_ui()
    budget_ui()
    for language in ('en', 'de', 'es'):
        ui(language)


if __name__ == '__main__':
    main()

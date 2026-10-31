#!/usr/bin/env python3
"""Native paint library regression tests using only disposable private Xvfb/data.

Run after building build/app/jungle. Pixel expectations are independent fixtures,
not screenshots or a copy of the application's rotation implementation.
"""
import math
import tempfile
import time
from pathlib import Path

import numpy as np

from runtime_test import ROOT, DIGITS, picture_pixels, run_number, dinosaur_masks, run
from paint_history_test import (Desktop, WORK, changed, history, open_paint,
                                open_slots, paint_layout, pixel_click, scenery, tool, stencil_click, stencil_layout)
from paint_layers_test import HEADER, runs



def scene_layout(desktop):
    """Scene rectangles in window pixels; six stable slots at every width."""
    width, total = desktop.actual_size
    height = max(300, total - 56)
    if total - 56 < 300:
        height = 500
    pad, gap = (8, 6) if height < 440 else (16, 10)
    cols = 2 if width < 600 else 3
    rows = 6 // cols
    tab_y = pad + 30 + gap
    tab_w = (width - 2 * pad - 2 * gap) // 3
    grid_y = tab_y + 44 + gap
    footer_y = height - pad - 44
    cw = (width - 2 * pad - gap * (cols - 1)) // cols
    ch = max(80, (footer_y - gap - grid_y - gap * (rows - 1)) // rows)
    fw = (width - 2 * pad - 2 * gap) // 3
    return {
        'category': [(pad + i * (tab_w + gap), 56 + tab_y, tab_w, 44) for i in range(3)],
        'tile': [(pad + i % cols * (cw + gap), 56 + grid_y + i // cols * (ch + gap), cw, ch) for i in range(6)],
        'previous': [(pad, 56 + footer_y, fw, 44)],
        'next': [(width - pad - fw, 56 + footer_y, fw, 44)],
    }


def scene_click(desktop, kind='tile', index=0):
    x, y, w, h = scene_layout(desktop)[kind][index]
    desktop.click_actual(x + w // 2, y + h // 2)



def placement_click(desktop, place=True):
    x, y, w, h = paint_layout(desktop)[0]
    bw = max(44, min(140, (w - 18) // 2))
    left = x + (w - bw * 2 - 6) // 2
    desktop.click_actual(left + (bw + 6 if place else 0) + bw // 2, 56 + y + h - 26)


def composite(base, objects):
    pixels = base.copy()
    for x, y, paint in objects:
        h, w = paint.shape
        area = pixels[y:y+h, x:x+w]
        area[paint != 255] = paint[paint != 255]
    return pixels


def document(base, objects):
    records, start = [], 0
    for x, y, paint in objects:
        h, w = paint.shape
        records.append(f'{x} {y} {w} {h} {start}\n'.encode() + runs(paint) + b'\n')
        start += paint.size
    header = HEADER.replace(b' ' * 38, b'Painted story'.ljust(38), 1)
    if not objects:
        return header.replace(b'PICTURE 3', b'PICTURE 2') + runs(base) + b'\n'
    return (header + runs(composite(base, objects)) + b'\n' + runs(base) + b'\n' +
            f'{len(objects)}\n'.encode() + b''.join(records))


def decode_runs(text, shape):
    text, values, at = text.decode('ascii'), [], 0
    while at < len(text):
        color = 255 if text[at] == '~' else DIGITS.index(text[at])
        length, at = run_number(text, at + 1)
        values.append(np.full(length, color, np.uint8))
    return np.concatenate(values).reshape(shape)


def assert_document(saved, base, objects):
    assert np.array_equal(picture_pixels(saved), composite(base, objects)), 'flattened rotation pixels differ'
    lines = saved.splitlines()
    assert lines[1] == b'0e' and lines[2] == b'Painted story'.ljust(38), 'rotation changed scene/crayon/story'
    assert np.array_equal(decode_runs(lines[11], (720, 960)), base), 'rotation altered background paint'
    assert int(lines[12]) == len(objects), 'rotation changed object count'
    for i, (x, y, paint) in enumerate(objects):
        left, top, w, h, _ = map(int, lines[13 + i*2].split())
        assert (left, top, w, h) == (x, y, paint.shape[1], paint.shape[0]), 'object bounds differ'
        assert np.array_equal(decode_runs(lines[14 + i*2], (h, w)), paint), 'rotation lost hidden paint/transparency'


def gallery(folder):
    lines = (folder / 'gallery.txt').read_text().splitlines()
    assert lines[0] == 'JUNGLE GALLERY1'
    count, _, selected = map(int, lines[1].split())
    names = []
    for line in lines[2:]:
        length, name = line.split(' ', 1)
        assert len(name) == int(length)
        names.append(name)
    assert len(names) == count and len(set(names)) == count
    return names, selected - 1


def open_gallery_page(desktop, folder, target):
    tool(desktop, 4)
    desktop.capture('library-gallery-page', header=56)
    _, selected = gallery(folder)
    page = max(0, selected // 6)
    while page > target:
        desktop.click(60, 180)
        page -= 1
    while page < target:
        desktop.click(145, 180)
        page += 1


def choices(folder):
    saved = (folder / 'choices.txt').read_bytes()
    prefix = b'JUNGLE PAINT CHOICES 1\n'
    assert saved.startswith(prefix) and len(saved) == len(prefix) + 8
    return [DIGITS.index(chr(byte)) for byte in saved[len(prefix):]]


def setup(data, language, initial):
    (data / 'language.txt').write_text(language)
    folder = data / 'games/jungle.paint'
    folder.mkdir(parents=True)
    (folder / 'working.txt').write_bytes(initial)
    return folder, folder / 'working.txt'


def object_records(saved):
    lines = saved.splitlines()
    result = []
    for i in range(int(lines[12])):
        x, y, w, h, _ = map(int, lines[13 + i * 2].split())
        result.append((x, y, decode_runs(lines[14 + i * 2], (h, w))))
    return result


def rotation_handle(desktop, obj):
    x, y, paint = obj
    yy, xx = np.nonzero(paint != 255)
    x0, y0, x1, y1 = x + xx.min(), y + yy.min(), x + xx.max() + 1, y + yy.max() + 1
    left, top, width, height = paint_layout(desktop)[0]
    cx = left + (x0 + (x1 - x0) / 2) * width / 960
    cy = 56 + top + (y0 + (y1 - y0) / 2) * height / 720
    hy = max(56 + 12, 56 + top + y0 * height / 720 - 24)
    return (cx, cy), (cx, hy)


def rotate_drag(desktop, working, obj, degrees, *, held=None):
    center, handle = rotation_handle(desktop, obj)
    radians = math.radians(degrees)
    dx, dy = handle[0] - center[0], handle[1] - center[1]
    target = (center[0] + dx * math.cos(radians) - dy * math.sin(radians),
              center[1] + dx * math.sin(radians) + dy * math.cos(radians))
    def move(point):
        run(['xdotool', 'mousemove', '--window', desktop.window,
             str(round(point[0])), str(round(point[1]))], desktop.env)
        time.sleep(.25)
    move(handle)
    run(['xdotool', 'mousedown', '1'], desktop.env)
    try:
        time.sleep(.25)
        move(target)
        time.sleep(.3)
        if held:
            held()
    finally:
        run(['xdotool', 'mouseup', '1'], desktop.env)
    time.sleep(.4)
    desktop.alive()


def rotation(language, data):
    base = np.full((720, 960), 22, np.uint8)
    base[350:355] = 0
    bottom = np.full((80, 120), 30, np.uint8)
    paint = np.full((50, 90), 40, np.uint8)
    paint[:12, :20] = 255
    paint[15:25, 30:60] = 0
    paint[30:, 70:] = 50
    edge = np.full((30, 50), 35, np.uint8)
    edge[:10, :20] = 0
    objects = [(270, 180, bottom), (280, 190, paint), (910, 690, edge)]
    initial = document(base, objects)
    folder, working = setup(data, language, initial)
    expected = [objects[0], (300, 170, np.rot90(paint, -1)), objects[2]]
    with Desktop(ROOT / 'build/app/jungle', data) as desktop:
        open_paint(desktop, 'library-rotation')
        tool(desktop, 8)
        pixel_click(desktop, 20, 20)
        assert working.read_bytes() == initial, 'bare-paper Select changed artwork'
        assert not (folder / 'working-undo.txt').exists(), 'Select pushed history'
        pixel_click(desktop, 330, 220)
        assert working.read_bytes() == initial, 'selecting an object changed pixels'
        rotate_drag(desktop, working, objects[1], 0)
        assert working.read_bytes() == initial, 'stationary handle changed pixels'
        assert not (folder / 'working-undo.txt').exists(), 'stationary handle pushed history'
        expected_history = None
        def held():
            assert working.read_bytes() == initial, 'rotation committed while held'
            path = folder / 'working-undo.txt'
            assert (path.read_bytes() if path.exists() else None) == expected_history, 'held rotation pushed Undo'
            if language == 'en':
                preview = desktop.capture_actual('free-rotation-held')
                artifact = ROOT / 'work/paint-rotation/preview.png'
                artifact.parent.mkdir(parents=True, exist_ok=True)
                preview.save(artifact)
        rotate_drag(desktop, working, objects[1], 90, held=held)
        rotated = changed(working, initial)
        selected = object_records(rotated)[1]
        assert abs(selected[2].shape[0] - 90) <= 2 and abs(selected[2].shape[1] - 50) <= 2
        expected = [objects[0], selected, objects[2]]
        assert_document(rotated, base, expected)
        assert len(history(folder)) == 1, 'completed gesture did not push exactly one Undo'
    with Desktop(ROOT / 'build/app/jungle', data) as desktop:
        open_paint(desktop, 'library-rotated-reopen')
        assert_document(working.read_bytes(), base, expected)
        tool(desktop, 6)
        restored = changed(working, rotated)
        assert_document(restored, base, objects)
        tool(desktop, 8)
        pixel_click(desktop, 330, 220)
        history_file = folder / 'working-undo.txt'
        expected_history = history_file.read_bytes() if history_file.exists() else None
        rotate_drag(desktop, working, objects[1], 37, held=held)
        arbitrary = changed(working, initial)
        actual = object_records(arbitrary)
        h, w = actual[1][2].shape
        assert 95 <= w <= 109 and 88 <= h <= 101 and w != 50 and h != 90, 'handle snapped to a right angle'
        assert actual[1][2][0, 0] == 255, 'rotation lost transparent corners'
        assert set(np.unique(actual[1][2])) <= {0, 40, 50, 255}, 'rotation invented paint colors'
        assert {0, 40, 50} <= set(np.unique(actual[1][2])), 'rotation lost painted regions'
        assert_document(arbitrary, base, [objects[0], actual[1], objects[2]])
        tool(desktop, 6)
        assert_document(changed(working, arbitrary), base, objects)
        # A transparent upper corner selects the visible lower object.
        tool(desktop, 8)
        pixel_click(desktop, 285, 195)
        rotate_drag(desktop, working, objects[0], 90)
        lower = changed(working, initial)
        selected = object_records(lower)[0]
        assert abs(selected[2].shape[0] - 120) <= 3 and abs(selected[2].shape[1] - 80) <= 3
        assert_document(lower, base, [selected, objects[1], objects[2]])
        tool(desktop, 6)
        assert_document(changed(working, lower), base, objects)
        # Both page boundaries and responsive toolbar layouts keep the handle usable.
        for dimensions, index in (((1120, 700), 2), ((420, 700), 1), ((700, 420), 1)):
            desktop.resize(*dimensions)
            desktop.capture('library-responsive-rotation', header=56)
            assert desktop.actual_size == dimensions, (desktop.actual_size, dimensions)
            tool(desktop, 8)
            pixel_click(desktop, 940 if index == 2 else 330, 710 if index == 2 else 220)
            rotate_drag(desktop, working, objects[index], 90)
            turned = changed(working, initial)
            selected = object_records(turned)[index]
            wanted = list(objects)
            wanted[index] = selected
            assert abs(selected[2].shape[0] - objects[index][2].shape[1]) <= 3
            assert abs(selected[2].shape[1] - objects[index][2].shape[0]) <= 3
            assert selected[0] >= 0 and selected[1] >= 0 and selected[0] + selected[2].shape[1] <= 960 and selected[1] + selected[2].shape[0] <= 720
            assert_document(turned, base, wanted)
            tool(desktop, 6)
            assert_document(changed(working, turned), base, objects)
        # Four successive gestures reuse the original raster without drift.
        tool(desktop, 8)
        pixel_click(desktop, 330, 220)
        current = objects[1]
        for turn in range(1, 5):
            before = working.read_bytes()
            rotate_drag(desktop, working, current, 90)
            turned = changed(working, before)
            current = object_records(turned)[1]
            assert_document(turned, base, [objects[0], current, objects[2]])
        assert abs(current[2].shape[0] - 50) <= 5 and abs(current[2].shape[1] - 90) <= 5, 'successive gestures degraded source bounds'
        assert np.count_nonzero(current[2] == 50) >= np.count_nonzero(paint == 50) * .90, 'successive gestures lost painted detail'
        # Leaving with Escape cancels an active gesture before its release.
        center, handle = rotation_handle(desktop, current)
        run(['xdotool', 'mousemove', '--window', desktop.window, str(round(handle[0])), str(round(handle[1])),
             'mousedown', '1'], desktop.env)
        time.sleep(.3)
        run(['xdotool', 'mousemove', '--window', desktop.window, str(round(center[0] + 30)), str(round(center[1]))], desktop.env)
        time.sleep(.3)
        before = working.read_bytes()
        try:
            desktop.key('Escape')
        finally:
            run(['xdotool', 'mouseup', '1'], desktop.env)
        assert working.read_bytes() == before, 'leaving committed a canceled drag'
    print(f'local native library ({language}): Select, free handle rotation, preview/release, no-op, alpha hit, Undo/reopen, edges and responsive layouts passed', flush=True)


def library(language, data):
    base = np.full((720, 960), 22, np.uint8)
    initial = document(base, [])
    folder, working = setup(data, language, initial)
    legacy = []
    for index in range(6):
        pixels = base.copy()
        pixels[100:150, 100:180] = 30 + index
        legacy.append(document(pixels, []))
        (folder / f'slot-{index}.txt').write_bytes(legacy[-1])
    with Desktop(ROOT / 'build/app/jungle', data) as desktop:
        open_paint(desktop, 'library-gallery')
        names, _ = gallery(folder)
        assert names == [f'slot-{i}.txt' for i in range(6)], 'six legacy slots were not imported by reference'
        tool(desktop, 4)
        desktop.capture('library-six-legacy', header=56)
        # Open every legacy thumbnail and compare its own original bytes/pixels.
        for i, saved in enumerate(legacy):
            if i:
                open_gallery_page(desktop, folder, 0)
            desktop.click(65 + i % 3 * 94, 78 + i // 3 * 60)
            assert np.array_equal(picture_pixels(working.read_bytes()), picture_pixels(saved)), f'legacy thumbnail {i} opened another picture'
        # Legacy Slots Save and Load remain reachable through Gallery.
        open_slots(desktop)
        desktop.click(210, 38)
        desktop.click(50, 80)
        assert np.array_equal(picture_pixels(working.read_bytes()), picture_pixels(legacy[0]))
        open_slots(desktop)
        desktop.click(50, 80)  # old Save route, including overwrite confirmation
        desktop.capture('library-slot-overwrite', header=56)
        desktop.click(80, 134)
        assert scenery((folder / 'slot-0.txt').read_bytes()) == scenery(legacy[0])
        original_names, _ = gallery(folder)
        tool(desktop, 4)
        desktop.click(90, 38)  # explicit Save a copy
        names, selected = gallery(folder)
        assert len(names) == len(original_names) + 1 and names[-1].startswith('picture-')
        copy_name = names[selected]
        copy_bytes = (folder / copy_name).read_bytes()
        # Save a copy switches to its page; open it, then edit in place.
        desktop.click(65 + selected % 6 % 3 * 94, 78 + selected % 6 // 3 * 60)
        tool(desktop, 1)
        desktop.capture('library-colors', header=56)
        desktop.click(38, 40)
        pixel_click(desktop, 20, 20)
        edited = changed(working, copy_bytes)
        assert gallery(folder)[0] == names, 'editing a positive gallery picture appended another entry'
        assert (folder / copy_name).read_bytes() == edited, 'gallery did not autosave the active entry'
        # New picture chooses its scene and must detach from the edited entry.
        tool(desktop, 7)
        desktop.capture('library-new', header=56)
        desktop.click(80, 90)
        desktop.wait_scene_picker('library-new-scenes')
        scene_click(desktop)
        desktop.key('Escape')  # leave stencil picker
        desktop.capture('library-new-main', header=56)
        new_picture = changed(working, edited)
        assert (folder / copy_name).read_bytes() == edited, 'New overwrote the prior gallery entry'
        assert len(gallery(folder)[0]) == len(names) + 1, 'new scene did not get its own gallery entry'
        # Open the earlier copy across pages and verify its edits survived New.
        open_gallery_page(desktop, folder, selected // 6)
        desktop.capture('library-open-copy', header=56)
        desktop.click(65 + selected % 6 % 3 * 94, 78 + selected % 6 // 3 * 60)
        assert scenery(working.read_bytes()) == scenery(edited), 'Gallery reopened another picture'
        assert history(folder) == [], 'Gallery open kept the other picture history'
        assert working.read_bytes() != new_picture
    with Desktop(ROOT / 'build/app/jungle', data) as desktop:
        open_paint(desktop, 'library-gallery-reopen')
        assert scenery(working.read_bytes()) == scenery(edited), 'hard reopen lost selected gallery edits'
        assert copy_name in gallery(folder)[0], 'hard reopen lost gallery index entry'
    for i, saved in enumerate(legacy):
        assert (folder / f'slot-{i}.txt').read_bytes() == saved, 'gallery import/edit wrote a legacy slot'
    print(f'local native library ({language}): six legacy imports/open, Slots Save/Load, copy, autosave, New, gallery open and restart passed', flush=True)


def remembered(language, data):
    base = np.full((720, 960), 22, np.uint8)
    folder, working = setup(data, language, document(base, []))
    (folder / 'choices.txt').write_bytes(b'JUNGLE PAINT CHOICES 1\n00030000')
    with Desktop(ROOT / 'build/app/jungle', data) as desktop:
        open_paint(desktop, 'library-choices')
        tool(desktop, 0)
        desktop.capture('library-stencils', header=56)
        # Page 2 dinosaur is an existing asset (stable ID 6).
        stencil_click(desktop, 'next')
        stencil_click(desktop)
        desktop.capture('library-placement', header=56)
        tool(desktop, 6)  # mirror while placing
        before = working.read_bytes()
        tool(desktop, 8)  # Place first: cannot silently rotate/lose pending stencil.
        assert working.read_bytes() == before and choices(folder)[:5] == [7, 0, 1, 3, 1]
        tool(desktop, 6)
        assert choices(folder)[4] == 0, 'Rotate discarded the pending stencil instead of showing Place first'
        tool(desktop, 6)
        assert choices(folder)[4] == 1
    with Desktop(ROOT / 'build/app/jungle', data) as desktop:
        open_paint(desktop, 'library-remembered-dinosaur')
        assert choices(folder)[:5] == [7, 0, 1, 3, 1]
        tool(desktop, 0)
        desktop.capture('library-remembered-page', header=56)
        stencil_click(desktop)
        assert choices(folder)[:3] == [7, 0, 1], 'dinosaur page did not reopen'
        desktop.capture('library-remembered-preview', header=56)
        assert choices(folder)[3] == 3, 'remembered size was lost'
        desktop.key('Escape')  # discard pending stencil
        tool(desktop, 0)
        # Switch category and choose existing Crate/Small.
        desktop.capture('library-stencils-again', header=56)
        stencil_click(desktop, 'category', 3)
        stencil_click(desktop)
        desktop.key('Escape')
        desktop.capture('library-small', header=56)
        tool(desktop, 0)
        desktop.capture('library-object-picker', header=56)
        assert choices(folder)[:5] == [25, 3, 0, 3, 1]
        desktop.key('Escape')
        # Remember Nature page 2 using old scene asset 7, then browse Adventures.
        tool(desktop, 7)
        desktop.capture('library-choice-new', header=56)
        desktop.click(80, 90)
        desktop.wait_scene_picker('library-choice-scenes')
        scene_click(desktop, 'next')
        scene_click(desktop)
        desktop.key('Escape')
        desktop.capture('library-choice-scene-selected', header=56)
        assert choices(folder)[5:] == [0, 1, 8]
        tool(desktop, 7)
        desktop.capture('library-choice-new-again', header=56)
        desktop.click(80, 90)
        desktop.wait_scene_picker('library-choice-scenes-again')
        scene_click(desktop, 'category', 2)
        assert choices(folder)[5:] == [2, 0, 8]
    expected = choices(folder)
    with Desktop(ROOT / 'build/app/jungle', data) as desktop:
        desktop.game('Coloring Book')
        desktop.wait_scene_picker('library-restored-scenes')
        assert choices(folder) == expected, 'hard reopen reset remembered choices'
        # Adventures first tile is stable Volcano valley, not Nature first tile.
        scene_click(desktop)
        assert choices(folder)[5:] == [2, 0, 2], ('restored Adventure scene selection', choices(folder))
        desktop.capture('library-restored-stencils', header=56)
        assert working.read_bytes().splitlines()[1][:1] == b'1', 'scene category reopened to another scene'
        assert choices(folder)[:5] == expected[:5], 'scene selection reset stencil choices'
        # Restored Objects category opens the existing Crate.
        stencil_click(desktop)
        assert choices(folder)[:4] == [25, 3, 0, 3], 'stencil category/page did not reopen'
        desktop.capture('library-restored-placement', header=56)
        assert choices(folder)[3] == 3, 'restored in-scene size differs'
        tool(desktop, 6)
        assert choices(folder)[4] == 0, 'mirror choice was not restored'
    print(f'local native library ({language}): stencil, category/page, size, flip, scene/category/page remembered across hard reopen passed', flush=True)


def responsive_stencils(data):
    """Real private-window input: resizing, partial pages and Escape preserve art."""
    base = np.full((720, 960), 22, np.uint8)
    folder, working = setup(data, 'en', document(base, []))
    with Desktop(ROOT / 'build/app/jungle', data, screen_size='1280x1000') as desktop:
        open_paint(desktop, 'responsive-main')
        before = working.read_bytes()
        tool(desktop, 0)
        for n, size in enumerate(((390, 844), (400, 756), (420, 700), (844, 390), (960, 600))):
            desktop.resize(*size)
            actual = desktop.capture_actual('responsive-picker')
            assert actual.size == size, 'private picker capture was clipped'
            rects = stencil_layout(desktop)
            boxes = sum(rects.values(), [])
            for x, y, w, h in boxes:
                assert w >= 44 and h >= 44, ('small touch target', size, (x, y, w, h))
                assert 0 <= x < x + w <= size[0] and 56 <= y < y + h <= size[1]
            for i, (x, y, w, h) in enumerate(boxes):
                for a, b, c, d in boxes[i+1:]:
                    assert x + w <= a or a + c <= x or y + h <= b or b + d <= y, 'picker controls overlap'
            # Check rendered control backgrounds at the predicted hit rectangles.
            for kind in ('category', 'tile'):
                for x, y, w, h in rects[kind]:
                    color = actual.getpixel((x + 4, y + h // 2))
                    assert color in ((243, 236, 220), (247, 241, 227), (220, 235, 220)), ('missing picker control', kind, size, color)
            # Each category ends with four actual tiles and two empty positions.
            category = n % 4
            stencil_click(desktop, 'category', category)
            for _ in range(2 if category == 0 else 1):
                stencil_click(desktop, 'next')
            assert choices(folder)[1:3] == [category, 2 if category == 0 else 1]
            saved_choices = choices(folder)
            stencil_click(desktop, 'next')  # No destination on the final page.
            stencil_click(desktop, 'tile', 5)  # No phantom sixth item.
            assert choices(folder) == saved_choices
            stencil_click(desktop, 'tile', 3)
            expected = (34, 38, 42, 46)[category]
            assert choices(folder)[0] == expected, ('partial page chose another stencil', category)
            desktop.key('Escape')  # Cancel pending stencil, then reopen its page.
            tool(desktop, 0)
            actual = desktop.capture_actual('responsive-selected')
            x, y, w, h = stencil_layout(desktop)['tile'][3]
            assert actual.getpixel((x + 4, y + h // 2)) == (220, 235, 220), 'selected stencil is not highlighted'
            selected = choices(folder)
            desktop.resize(960 if size[0] < 600 else 390, 600 if size[0] < 600 else 844)
            desktop.capture('responsive-resized-selection', header=56)
            assert choices(folder) == selected, 'resize changed persisted page or selection'
            stencil_click(desktop, 'tile', 3)
            assert choices(folder) == selected, 'resized page selected a different stencil'
            desktop.key('Escape')
            tool(desktop, 0)
            stencil_click(desktop, 'category', 0)  # Full page for the next geometry capture.
        desktop.key('Escape')  # Picker -> picture; cancellation preserves pixels.
        assert working.read_bytes() == before
    print('local native responsive picker: five mobile/landscape sizes, all categories, partial pages, selection, resize and keyboard cancellation passed', flush=True)



def responsive_scenes(data):
    """Real scene input at phone, landscape and short scrolling sizes."""
    import json
    catalog = json.loads((ROOT / 'tools/coloring_catalog.json').read_text())
    with Desktop(ROOT / 'build/app/jungle', data, screen_size='1280x1000') as desktop:
        desktop.game('Coloring Book')
        desktop.wait_scene_picker('responsive-scenes-entry')
        folder = data / 'games/jungle.paint'
        scene_click(desktop, 'category', 1)
        scene_click(desktop, 'category', 0)
        for size in ((320, 700), (390, 844), (420, 700), (844, 390), (960, 600)):
            desktop.resize(*size)
            actual = desktop.capture_actual('responsive-scenes')
            assert actual.size == size
            rects = scene_layout(desktop)
            boxes = sum(rects.values(), [])
            for i, (x, y, w, h) in enumerate(boxes):
                assert w >= 44 and h >= 44, ('small scene target', size)
                assert 0 <= x < x + w <= size[0] and 56 <= y < y + h <= size[1]
                for a, b, c, d in boxes[i+1:]:
                    assert x + w <= a or a + c <= x or y + h <= b or b + d <= y
            for category, name in enumerate(('nature', 'places', 'adventures')):
                scene_click(desktop, 'category', category)
                scene_click(desktop, 'previous')  # first page or inactive
                assert choices(folder)[5:7] == [category, 0]
                saved = choices(folder)
                scene_click(desktop, 'previous')
                assert choices(folder) == saved, 'Previous active on first scene page'
                count = sum(row['category'] == name for row in catalog['scenes'])
                pages = (count + 5) // 6
                for _ in range(pages - 1):
                    scene_click(desktop, 'next')
                saved = choices(folder)
                assert saved[6] == pages - 1
                scene_click(desktop, 'category', category)
                assert choices(folder) == saved, 'active category lost remembered page'
                scene_click(desktop, 'next')
                assert choices(folder) == saved, 'Next active on final scene page'
                if count % 6:
                    scene_click(desktop, 'tile', 5)
                    assert choices(folder) == saved, 'phantom scene tile selected'
            scene_click(desktop, 'category', 0)
        # Even a very short landscape retains full-size targets via page scroll.
        desktop.resize(844, 280)
        desktop.capture_actual('responsive-scenes-short')
        run(['xdotool', 'mousemove', '--window', desktop.window, '400', '180',
             'click', '--repeat', '35', '--delay', '15', '5'], desktop.env)
        time.sleep(.3)
        # Content bottom is 500, viewport is 224: footer center is 242.
        desktop.click_actual(700, 242)
        assert choices(folder)[6] == 1, 'short landscape footer not reachable'
        desktop.resize(390, 844)
        desktop.capture_actual('responsive-scenes-resize')
        assert choices(folder)[5:7] == [0, 1], 'resize lost scene page'
        desktop.resize(960, 600)
        desktop.capture('responsive-scenes-before-back', header=56)
        desktop.click_actual(28, 28)
        desktop.wait_menu('responsive-scenes-title-back')
    with Desktop(ROOT / 'build/app/jungle', data) as desktop:
        desktop.game('Coloring Book')
        desktop.wait_scene_picker('responsive-scenes-reopened')
        assert choices(folder)[5:7] == [0, 1]
        scene_click(desktop)
        desktop.key('Escape')
        desktop.capture('responsive-scene-selected', header=56)
        assert choices(folder)[5:7] == [0, 1]
    print('local responsive scenes: 2/3 columns, five sizes, all tabs/pages, invalid controls, short scroll, resize, Back and hard reopen passed', flush=True)


def placement_editor(data):
    """Only Place edits art; real drag/resize/free rotation survive releases."""
    base = np.full((720, 960), 22, np.uint8)
    initial = document(base, [])
    folder, working = setup(data, 'en', initial)
    with Desktop(ROOT / 'build/app/jungle', data, screen_size='1280x1000') as desktop:
        open_paint(desktop, 'editor-main')
        before = working.read_bytes()
        def undo():
            return history(folder) if (folder / "working-undo.txt").exists() else []
        def drag_actual(start, end):
            run(['xdotool', 'mousemove', '--window', desktop.window, str(round(start[0])), str(round(start[1]))], desktop.env)
            run(['xdotool', 'mousedown', '1'], desktop.env)
            try:
                for step in range(1, 9):
                    x = start[0] + (end[0]-start[0])*step/8
                    y = start[1] + (end[1]-start[1])*step/8
                    run(['xdotool', 'mousemove', '--window', desktop.window, str(round(x)), str(round(y))], desktop.env)
                    time.sleep(.04)
                held = desktop.capture_actual('editor-held')
                assert working.read_bytes() == before and not undo()
            finally:
                run(['xdotool', 'mouseup', '1'], desktop.env)
            time.sleep(.2)
            assert working.read_bytes() == before and not undo(), 'release placed the preview'
            return held
        def begin():
            tool(desktop, 0)
            desktop.capture('editor-picker', header=56)
            stencil_click(desktop, 'category', 3)
            stencil_click(desktop)
            return desktop.capture_actual('editor-preview')
        preview = begin()
        x,y,w,h = paint_layout(desktop)[0]
        cx,cy=x+w/2,56+y+h/2
        crop = np.asarray(preview)[int(cy-30):int(cy+30),int(cx-30):int(cx+30)]
        assert np.any(crop.sum(axis=2)<150), 'pending stencil art is missing'
        drag_actual((cx,cy), (cx+35,cy-25))
        placement_click(desktop, False)
        assert working.read_bytes() == before and not undo(), 'Cancel changed art or Undo'
        begin()
        ink,_ = dinosaur_masks(24, choices(folder)[3]); sw=ink.shape[1]
        full,_=dinosaur_masks(24,4);sh=full.shape[0]*sw/full.shape[1]
        corner=(min(x+w-22,cx+sw*w/960/2),min(56+y+h-74,cy+sh*h/720/2))
        drag_actual(corner,(cx+(corner[0]-cx)*.55,cy+(corner[1]-cy)*.55))
        assert choices(folder)[3] < 2, 'in-scene resize did not persist its nearest size'
        desktop.key('Escape')
        assert working.read_bytes() == before and not undo()
        begin()
        ink,_=dinosaur_masks(24,choices(folder)[3]);sw=ink.shape[1]
        sh=full.shape[0]*sw/full.shape[1]
        handle=(cx,max(56+y+22,cy-sh*h/720/2-30))
        radius=cy-handle[1]; angle=math.radians(37)
        drag_actual(handle,(cx+radius*math.sin(angle),cy-radius*math.cos(angle)))
        placement_click(desktop)
        saved=changed(working,before)
        assert len(object_records(saved))==1 and len(undo())==1
        assert np.array_equal(decode_runs(saved.splitlines()[11], (720,960)),base)
        tool(desktop,6)
        assert changed(working,saved)==before, 'placement Undo did not restore the exact picture'
        desktop.capture('editor-undo-settled',header=56)
        assert not undo(), ('Undo history', len(undo()))
        # Phone retains explicit controls and drawing; cancel is still atomic.
        desktop.resize(390,844)
        desktop.capture('editor-phone-main',header=56)
        begin()
        placement_click(desktop,False)
        assert working.read_bytes()==before and not undo(), ('phone Cancel',len(before),len(working.read_bytes()),len(undo()), choices(folder),working.read_bytes().splitlines()[1])
    print('local placement editor: visible art, drag/resize/37-degree rotation preview, release no-op, Place one Undo, Cancel/Escape and phone controls passed',flush=True)


def catalog_ui(data):
    """Exercise each added asset through its real categorized native picker."""
    base = np.full((720, 960), 22, np.uint8)
    initial = document(base, [])
    folder, working = setup(data, 'en', initial)
    (folder / 'choices.txt').write_bytes(b'JUNGLE PAINT CHOICES 1\n00040000')
    with Desktop(ROOT / 'build/app/jungle', data) as desktop:
        open_paint(desktop, 'library-new-catalog')
        for category in range(4):
            for offset in range(4):
                index = 30 + category * 4 + offset
                tool(desktop, 0)
                desktop.capture('library-catalog-stencils', header=56)
                stencil_click(desktop, 'category', category)
                for _ in range(2 if category == 0 else 1):
                    stencil_click(desktop, 'next')
                stencil_click(desktop, 'tile', offset)
                desktop.capture('library-catalog-placement', header=56)
                assert choices(folder)[0] == index + 1, f'new stencil {index} picker selected another asset'
                placement_click(desktop)
                placed = changed(working, initial)
                ink, body = dinosaur_masks(index, 4)
                source = np.where(ink, 0, np.where(body, 15, 255)).astype(np.uint8)
                x, y, w, h, *_ = map(int, placed.splitlines()[13].split())
                # Independent Pillow nearest-neighbour sampling of the full mask.
                from PIL import Image
                paint = np.asarray(Image.fromarray(source).resize((w, h), Image.Resampling.NEAREST))
                assert_document(placed, base, [(x, y, paint)])
                tool(desktop, 6)
                assert np.array_equal(picture_pixels(changed(working, placed)), base), f'new stencil {index} Undo failed'
        for index in range(12, 24):
            category = 0 if index < 16 else 1 if index < 20 else 2
            position = index - 2 if category == 0 else index - 15 if category == 1 else index - 19
            tool(desktop, 7)
            desktop.capture('library-catalog-new', header=56)
            desktop.click(80, 90)
            desktop.wait_scene_picker('library-catalog-scenes')
            scene_click(desktop, 'category', category)
            scene_click(desktop, 'previous')
            for _ in range(position // 6):
                scene_click(desktop, 'next')
            scene_click(desktop, 'tile', position % 6)
            desktop.key('Escape')
            desktop.capture('library-catalog-scene-main', header=56)
            saved = working.read_bytes()
            assert saved.splitlines()[1][0] == ord(DIGITS[index]), f'new scene {index} opened another asset'
            pixels = picture_pixels(saved)
            assert np.count_nonzero(pixels == 0) > 100 and np.count_nonzero(pixels != 0) > 10000, f'new scene {index} has no usable line art'
    print('local native catalog: all16 new stencils placed/compared/undone; all12 new scenes opened with line art', flush=True)


def run_paint_library_test():
    WORK.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='library-', dir=WORK) as temporary:
        for language in ('en', 'de', 'es'):
            for name, test in (('rotate', rotation), ('gallery', library), ('choices', remembered)):
                data = Path(temporary) / f'{language}-{name}'
                data.mkdir()
                test(language, data)
        data = Path(temporary) / 'responsive'
        data.mkdir()
        responsive_stencils(data)
        data = Path(temporary) / 'responsive-scenes'
        data.mkdir()
        responsive_scenes(data)
        data = Path(temporary) / 'placement-editor'
        data.mkdir()
        placement_editor(data)
        data = Path(temporary) / 'new-catalog'
        data.mkdir()
        catalog_ui(data)
    print('local native paint library test passed', flush=True)


if __name__ == '__main__':
    run_paint_library_test()

#!/usr/bin/env python3
"""Test the illustrated Drums playground on an owned private Xvfb display."""
from pathlib import Path
import tempfile
import time

from PIL import ImageChops
import runtime_test as rt


rt.OUTPUT = rt.ROOT / 'backup/drums-keyboard'
TITLE = 'Little Drums'
PICTURE_SIZES = (1.00, .56, .50, .48)
BODY_FRACTIONS = ((.50, .52), (.50, .52), (.32, .52), (.50, .52))


def geometry(width, height):
    height -= 56
    scale = min(width / 400, height / 700) if width <= height else min(height / 520, width / 780)
    scale = max(.5, min(scale, 1.6))
    virtual_width, virtual_height = int(width / scale), int(height / scale)
    columns = 4 if virtual_width > virtual_height * 2 else 2
    rows = 4 // columns
    edge = min((virtual_width - 32 - (columns - 1) * 14) // columns,
               (virtual_height - 216 - (rows - 1) * 14) // rows, 250)
    edge = max(edge, 0)
    left = (virtual_width - columns * edge - (columns - 1) * 14) // 2
    top = (virtual_height - 216 - rows * edge - (rows - 1) * 14) // 2
    return scale, virtual_width, virtual_height, columns, edge, left, top


def instruments(size):
    width, height = size
    _, virtual_width, virtual_height, columns, edge, left, top = geometry(width, height)
    placed = []
    for pad in range(4):
        slot = pad + 2 if columns == 2 and pad < 2 else pad - 2 if columns == 2 else pad
        cell_x = left + slot % columns * (edge + 14)
        cell_y = 142 + top + slot // columns * (edge + 14)
        picture_size = int(edge * PICTURE_SIZES[pad])
        picture_x = cell_x + (edge - picture_size) // 2
        picture_y = cell_y + edge * 79 // 100 - picture_size
        placed.append((pad, cell_x, cell_y, edge, picture_x, picture_y, picture_size))
    return placed


def actual_point(width, height, x, y):
    scale = geometry(width, height)[0]
    return round(x * scale), round(56 + y * scale)


def body_point(width, height, pad):
    item = instruments((width, height))[pad]
    _, _, _, _, picture_x, picture_y, picture_size = item
    fraction_x, fraction_y = BODY_FRACTIONS[pad]
    return actual_point(width, height, picture_x + picture_size * fraction_x,
                        picture_y + picture_size * fraction_y)


def changed(before, after):
    return ImageChops.difference(before.convert('RGB'), after.convert('RGB')).getbbox()


def ink_count(picture, box):
    crop = picture.crop(box).convert('RGB')
    pixels = crop.get_flattened_data() if hasattr(crop, 'get_flattened_data') else crop.getdata()
    return sum(max(color) < 190 for color in pixels)


def landscape_label_clusters(picture):
    crop_top = int(picture.height * .72)
    crop_bottom = int(picture.height * .78)
    occupied = [False] * picture.width
    for y in range(crop_top, crop_bottom):
        for x in range(0, picture.width):
            if max(picture.getpixel((x, y))) < 190:
                occupied[x] = True
    clusters = []
    start = None
    for x, marked in enumerate(occupied + [False]):
        if marked and start is None:
            start = x
        if not marked and start is not None:
            if not clusters or start > clusters[-1][2] + 25:
                clusters.append([start, crop_top, x - 1, crop_top])
            else:
                clusters[-1][2] = x - 1
            start = None
    for cluster in clusters:
        for y in range(crop_top, crop_bottom):
            if any(max(picture.getpixel((x, y))) < 190 for x in range(cluster[0], cluster[2] + 1)):
                cluster[1] = min(cluster[1], y); cluster[3] = max(cluster[3], y)
    # Keep text-sized clusters, not single antialiased specks.
    merged = []
    for cluster in clusters:
        if merged and cluster[0] <= merged[-1][2] + 25:
            merged[-1][0] = min(merged[-1][0], cluster[0]); merged[-1][1] = min(merged[-1][1], cluster[1])
            merged[-1][2] = max(merged[-1][2], cluster[2]); merged[-1][3] = max(merged[-1][3], cluster[3])
        else:
            merged.append(cluster)
    return [cluster for cluster in merged if cluster[2] - cluster[0] > 15]


def visible_art_box(picture, label):
    center_x = (label[0] + label[2]) // 2
    left = max(0, center_x - 88); right = min(picture.width, center_x + 89)
    top = int(picture.height * .18); bottom = label[1] - 8
    found = None
    for y in range(top, bottom):
        for x in range(left, right):
            color = picture.getpixel((x, y))
            if max(color) - min(color) > 28 or max(color) < 185:
                if found is None: found = [x, y, x, y]
                else:
                    found[0] = min(found[0], x); found[1] = min(found[1], y)
                    found[2] = max(found[2], x); found[3] = max(found[3], y)
    assert found is not None, 'illustrated instrument body was not visible above its label'
    return tuple(found)


def assert_illustrated(picture, size, name):
    assert len(picture.getcolors(1_000_000)) > 500, (name, 'playground has too little artwork')
    if size[0] > size[1]:
        labels = landscape_label_clusters(picture)
        assert len(labels) == 4, (name, 'four readable landscape labels were not found', labels)
        for label in labels:
            assert ink_count(picture, label) > 20, (name, 'instrument label is unreadable')
            assert len(picture.crop(visible_art_box(picture, label)).getcolors(200_000)) > 300, (
                name, 'instrument artwork is missing')
    else:
        for pad in (0, 1):
            item = instruments(size)[pad]
            _, cell_x, cell_y, edge, picture_x, picture_y, picture_size = item
            scale = geometry(*size)[0]
            artwork = (round(picture_x * scale), round(56 + picture_y * scale),
                       round((picture_x + picture_size) * scale), round(56 + (picture_y + picture_size) * scale))
            assert len(picture.crop(artwork).getcolors(200_000)) > 300, (name, 'instrument artwork is missing')
            label = (round((cell_x + 4) * scale), round(56 + (cell_y + edge * .81) * scale),
                     round((cell_x + edge - 4) * scale), round(56 + (cell_y + edge * .81 + 22) * scale))
            assert ink_count(picture, label) > 20, (name, 'instrument label is unreadable')


def assert_instrument_changed(before, after, size, pad, action):
    scale = geometry(*size)[0]
    item = instruments(size)[pad]
    _, cell_x, cell_y, edge = item[:4]
    box = (max(0, round((cell_x - 2) * scale)),
           max(0, round(56 + (cell_y - 2) * scale)),
           round((cell_x + edge + 2) * scale),
           round(56 + (cell_y + edge + 2) * scale))
    assert changed(before.crop(box), after.crop(box)), (pad, action, 'focused keyboard press gave no feedback')


def landscape_body_points(picture):
    labels = landscape_label_clusters(picture)
    points = []
    for pad, label in enumerate(labels):
        box = visible_art_box(picture, label)
        x = box[0] + int((box[2] - box[0]) * (.30 if pad == 2 else .50))
        y = box[1] + int((box[3] - box[1]) * .52)
        points.append((x, y))
    return points


def exercise_scene(desktop, language, size, prefix):
    width, height = size
    desktop.resize(*size)
    picture = desktop.capture_actual(f'{prefix}-{language}-{"portrait" if width < height else "landscape"}')
    assert_illustrated(picture, size, prefix)

    time.sleep(.8)
    quiet = desktop.capture_actual(f'{prefix}-{language}-quiet')
    points = landscape_body_points(quiet) if width > height else [
        body_point(width, height, pad) for pad in range(4)
    ]
    for pad in range(4):
        before = desktop.capture_actual(f'{prefix}-{language}-body-{pad}-before')
        desktop.click_actual(*points[pad])
        feedback = desktop.capture_actual(f'{prefix}-{language}-body-{pad}-feedback')
        assert changed(before, feedback), (language, pad, 'instrument body gave no visual feedback')

    if language == 'en':
        for pad in range(4):
            desktop.click_actual(*points[pad])
            time.sleep(.8)
            desktop.key('Tab'); desktop.key('Shift+Tab'); time.sleep(.3)
            for action in ('space', 'Return'):
                before = desktop.capture_actual(f'drums-keyboard-{pad}-{action}-before')
                desktop.key(action)
                feedback = desktop.capture_actual(f'drums-keyboard-{pad}-{action}-feedback')
                assert_instrument_changed(before, feedback, size, pad, action)
                time.sleep(.8)



    if width > height:
        first_art = visible_art_box(quiet, landscape_label_clusters(quiet)[0])
        art_width = first_art[2] - first_art[0]
        corner = (max(0, round(first_art[0] - art_width * .26) + 5),
                  max(0, round(first_art[1] - art_width * .04) + 5))
    else:
        item = instruments((width, height))[0]
        _, _, _, _, picture_x, picture_y, _ = item
        corner = actual_point(width, height, picture_x + 4, picture_y + 4)
    desktop.click_actual(*corner)
    empty = desktop.capture_actual(f'{prefix}-{language}-transparent-corner')
    time.sleep(.8)
    harmless = desktop.capture_actual(f'{prefix}-{language}-empty-mat-before')
    if width > height:
        desktop.click_actual(width // 2, int(height * .30))
    else:
        desktop.click_actual(*actual_point(width, height, width // 2 / geometry(width, height)[0], 136))
    background = desktop.capture_actual(f'{prefix}-{language}-empty-mat-after')
    assert changed(harmless, background) is None, (language, 'empty mat or transparent corner played')
    return picture


def main():
    orientations = {}
    captures = {}
    with tempfile.TemporaryDirectory(prefix='jungle-drums-playground-') as temporary:
        for language in ('en', 'de', 'es'):
            data = Path(temporary) / language
            data.mkdir()
            (data / 'language.txt').write_text(language)
            save = data / 'games/jungle.drums/drums.txt'
            save.parent.mkdir(parents=True)
            save.write_text('drums 1 5 1\n')
            with rt.Desktop(rt.ROOT / 'build/app/jungle', data, screen_size='1280x1100') as desktop:
                desktop.game(TITLE)
                captures[language] = exercise_scene(desktop, language, (400, 756), 'drums')
                desktop.resize(960, 600)
                captures[language, 'landscape'] = desktop.capture_actual(f'drums-{language}-landscape-main')
                assert_illustrated(captures[language, 'landscape'], (960, 600), 'landscape')

                if language == 'en':
                    virtual_width = geometry(960, 600)[1]
                    listen = actual_point(960, 600, virtual_width * 3 // 4, 30)
                    desktop.click_actual(*listen)
                    copying = desktop.capture_actual('drums-en-copy-mode')
                    assert changed(captures[language, 'landscape'], copying), 'Listen & Copy did not change the scene'
                    assert save.read_text() == 'drums 1 5 1\n', 'entering copy changed old progress'
                    replay = actual_point(960, 600, 60, 480)
                    desktop.click_actual(*replay)
                    replaying = desktop.capture_actual('drums-en-replay')
                    assert desktop.app.poll() is None, 'replay exited Little Drums'
                    assert changed(copying, replaying), 'replay control gave no scene response'
                    free = actual_point(960, 600, virtual_width // 4, 30)
                    desktop.click_actual(*free)
                    desktop.capture_actual('drums-en-free-returned')
                    assert save.read_text() == 'drums 1 5 1\n', 'returning to free play changed old progress'

                    desktop.click_actual(913, 28)
                    assert (data / 'sound.txt').read_text().strip() == 'off', 'mute control did not persist'
                    desktop.click_actual(913, 28)
                    assert (data / 'sound.txt').read_text().strip() == 'quiet', 'mute control did not restore sound'
                    desktop.click_actual(28, 28)
                    reopened_save = save.read_text()
                    desktop.game(TITLE)
                    resumed = desktop.capture_actual('drums-en-reopened')
                    assert changed(captures['en'], resumed), 'Little Drums did not reopen to its playground'
                    assert save.read_text() == reopened_save == 'drums 1 5 1\n', 'reopen changed persisted progress'
                    desktop.key('Escape')
                    orientations['portrait'] = captures['en']
                    orientations['landscape'] = captures[language, 'landscape']

    for orientation, english in orientations.items():
        german = captures['de', 'landscape'] if orientation == 'landscape' else captures['de']
        spanish = captures['es', 'landscape'] if orientation == 'landscape' else captures['es']
        assert changed(english, german), (
            orientation, 'German UI did not render its own readable text')
        assert changed(english, spanish), (
            orientation, 'Spanish UI did not render its own readable text')

    print('local drums playground test: four illustrated bodies, focused Space/Enter feedback, transparent misses, modes, mute, saves and EN/DE/ES layouts passed', flush=True)


if __name__ == '__main__':
    main()

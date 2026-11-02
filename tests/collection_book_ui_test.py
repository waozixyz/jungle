"""Shared collection titlebar, earned album, and unchanged activity return on private Xvfb."""
import tempfile
import time
import os
from pathlib import Path
from PIL import ImageChops
from runtime_test import ROOT, run
from paint_history_test import paint_layout, tool
from runtime_test import Desktop
import runtime_test
from paint_geometry import scene_click


def move_away(d):
    run(['xdotool', 'mousemove', '--window', d.window, str(d.actual_size[0] // 2), '2'], d.env)
    time.sleep(.4)


def shot(d, name):
    move_away(d)
    return d.capture_actual(name)


def album(d, width, abc=False, title=False):
    if title:
        unit = runtime_test.title_unit(*d.actual_size)
        d.click_actual(round(width - 51 * unit), round(17 * unit))
    else:
        d.click_actual(width - (178 if abc else 84), 28)
    image = shot(d, 'album')
    assert image.getpixel((3, 100)) == (255, 252, 243), 'Album did not open'
    return image


def same(a, b, area, message):
    delta = ImageChops.difference(a.crop(area), b.crop(area))
    assert delta.getbbox() is None, (message, delta.getbbox())


work = ROOT / 'work/collection-book-tests'
work.mkdir(parents=True, exist_ok=True)
runtime_test.OUTPUT = Path(os.environ.get('JUNGLE_TEST_OUTPUT', work / 'captures'))
BINARY = Path(os.environ.get('JUNGLE_TEST_BINARY', ROOT / 'build/app/jungle'))


def web_layout():
    import base64
    import io
    import sys
    import time

    sys.path.insert(0, str(ROOT / 'tests'))
    from PIL import Image
    from book_media_start_web_test import browser, serve
    captures = work / 'web-captures'
    captures.mkdir(parents=True, exist_ok=True)
    languages = (
        ('English', 'Collection Book', 'Back'),
        ('Deutsch', 'Sammelbuch', '< Zurück'),
        ('Español', 'Libro de colección', '< Atrás'),
    )
    sizes = ((320, 568), (960, 600), (1280, 300), (320, 240))

    def near(actual, expected, tolerance=.2):
        return abs(actual - expected) <= tolerance

    def controls(client, collection_label):
        rows = client.evaluate(
            "[...document.querySelectorAll('#kryon-dom-root button')].map(button=>({"
            "label:button.getAttribute('aria-label'),"
            "rect:button.getBoundingClientRect().toJSON()}))")
        collection = next((row for row in rows if row['label'] == collection_label), None)
        volume = max((row for row in rows if row['label'].startswith(
            ('Sound ', 'Ton ', 'Sonido '))), key=lambda row: row['rect']['left'])
        assert collection and volume['label'] != collection_label, (collection_label, rows)
        return collection, volume

    def button(client, label):
        rows = client.evaluate(
            "[...document.querySelectorAll('#kryon-dom-root button')].map(button=>({"
            "label:button.getAttribute('aria-label'),"
            "rect:button.getBoundingClientRect().toJSON()}))")
        result = next((row for row in rows if row['label'] == label), None)
        assert result, (label, rows)
        return result

    with serve(ROOT / 'build/web') as base_url, browser() as client:
        client.call('Page.navigate', url=base_url + '/dom.html')
        client.until("document.readyState === 'complete'", 'private Chromium page load')
        client.until("document.getElementById('loading').style.display === 'none'", 'title frame startup')
        client.until("[...document.querySelectorAll('#kryon-dom-root button')]"
                     ".some(button=>button.getAttribute('aria-label')==='Skip guide')",
                     'title guide controls')
        skip_guide = button(client, 'Skip guide')
        client.click(skip_guide['rect']['x'] + skip_guide['rect']['width'] / 2,
                     skip_guide['rect']['y'] + skip_guide['rect']['height'] / 2)
        for language, collection_label, back_label in languages:
            client.until(f"[...document.querySelectorAll('#kryon-dom-root button')]"
                         f".some(button=>button.getAttribute('aria-label')==={language!r})",
                         language + ' controls')
            language_button = button(client, language)
            client.click(language_button['rect']['x'] + language_button['rect']['width'] / 2,
                         language_button['rect']['y'] + language_button['rect']['height'] / 2)
            client.until(f"[...document.querySelectorAll('#kryon-dom-root button')]"
                         f".some(button=>button.getAttribute('aria-label')==={collection_label!r})",
                         collection_label + ' accessible label')
            for width, height in sizes:
                client.call('Emulation.setDeviceMetricsOverride', width=width, height=height,
                            deviceScaleFactor=1, mobile=False)
                time.sleep(.3)
                collection, volume = controls(client, collection_label)
                collection_rect = collection['rect']
                volume_rect = volume['rect']
                assert near(collection_rect['width'], volume_rect['width'], 1.1), (
                    width, height, collection_rect, volume_rect)
                assert near(collection_rect['height'], volume_rect['height'], 1.1), (
                    width, height, collection_rect, volume_rect)
                scale = volume_rect['width'] / 26
                assert near(collection_rect['height'], 22 * scale, .4)
                assert near(collection_rect['y'], volume_rect['y'], .4)
                assert near(volume_rect['x'] - collection_rect['right'], 6 * scale, .6)
                frame = client.call('Page.captureScreenshot', format='png')
                with Image.open(io.BytesIO(base64.b64decode(frame['data']))) as image:
                    assert image.size == (width, height)
                    image.save(captures / f'{language}-{width}x{height}.png')
                if language == 'English' and width == 320:
                    client.click(collection_rect['x'] + collection_rect['width'] / 2,
                                 collection_rect['y'] + collection_rect['height'] / 2)
                    client.until(f"[...document.querySelectorAll('#kryon-dom-root button')]"
                                 f".some(button=>button.getAttribute('aria-label')==={back_label!r})",
                                 'Collection Book opened')
                    client.key('Escape')
                    client.until(f"[...document.querySelectorAll('#kryon-dom-root button')]"
                                 f".some(button=>button.getAttribute('aria-label')==={collection_label!r})",
                                 'Collection Book closed')
        client.call('Emulation.setDeviceMetricsOverride', width=1280, height=675,
                    deviceScaleFactor=1, mobile=False)
        client.key('1')
        client.until("[...document.querySelectorAll('#kryon-dom-root button')]"
                     ".some(button=>button.getAttribute('aria-label')==='Sammelbuch'||"
                     "button.getAttribute('aria-label')==='Libro de colección'||"
                     "button.getAttribute('aria-label')==='Collection Book')",
                     'activity title bar')
        collection, volume = controls(client, 'Libro de colección')
        assert collection['rect']['width'] == volume['rect']['width'] == 44
        assert collection['rect']['height'] == volume['rect']['height'] == 44
        assert collection['rect']['y'] == volume['rect']['y'] == 6


if '--web-layout' in __import__('sys').argv:
    web_layout()
    print('local collection-book web layout test passed: compact button matches volume at portrait, landscape, short and wide sizes; EN/DE/ES labels and portrait tap')
    raise SystemExit(0)


for locale in ('en', 'de', 'es'):
    with tempfile.TemporaryDirectory(dir=work) as directory:
        data = Path(directory)
        (data / 'language.txt').write_text(locale)
        (data / 'guide-seen.txt').write_text('yes')
        # The title papers are already earned, so no pulsing paper glow changes
        # the exact title comparison below.
        (data / 'collection.txt').write_text(
            'JUNGLE COLLECTION 1\nmonkey\ntreehouse-scene\nbookshelf-scene\ncampus-scene\n')
        with Desktop(BINARY, data) as d:
            for width, height in ((960, 600), (320, 568)):
                d.resize(width, height)
                time.sleep(2)
                before = shot(d, 'title-before')
                collected = album(d, width, title=True)
                # First earned card contains colored artwork; next unearned card stays quiet.
                cell = (width - 24) // min(5, max(2, width // 150))
                earned = collected.crop((20, 138, cell - 4, 230))
                assert sum(1 for r, g, b in earned.getdata() if r > g + 15 and g > b + 10) > 200, 'Earned monkey artwork missing'
                d.click_actual(12 + cell // 2, 180)
                enlarged = shot(d, 'album-enlarged')
                assert ImageChops.difference(collected, enlarged).getbbox(), 'Earned card did not enlarge'
                art = enlarged.crop((16, 72, width - 16, height - 16))
                assert sum(1 for r, g, b in art.getdata() if r > g + 15 and g > b + 10) > 500, 'Enlarged monkey artwork missing'
                d.click_actual(28, 28)  # enlarged -> grid
                same(collected, shot(d, 'album-grid-return'), (0, 60, width, height), 'Back did not return to grid')
                d.click_actual(28, 28)  # grid -> title
                same(before, shot(d, 'title-return'), (0, 58, width, height), 'Title scene changed')

            d.game('Coloring Book')
            d.wait_scene_picker('album-paint-scenes')
            scene_click(d)
            d.key('Escape')  # dismiss stencil chooser, keep the selected background
            time.sleep(.7)
            for width, height in ((960, 600), (320, 568)):
                d.resize(width, height)
                shot(d, 'paint-layout')
                # Draw an unsaved line in the real working picture.
                tool(d, 1)
                d.capture('paint-colors', header=56)
                d.click(38 + 3 * 41, 40)
                time.sleep(.6)
                canvas = paint_layout(d)[0]
                x, y, w, h = canvas
                working = data / 'games/jungle.paint/working.txt'
                old_drawing = working.read_bytes()
                tool(d, 9)  # Pencil: a real unsaved stroke, not only a selected background.
                for command in (
                    ['mousemove', '--window', d.window, str(x + w // 3), str(56 + y + h // 2)],
                    ['mousedown', '1'],
                    ['mousemove', '--window', d.window, str(x + w // 2), str(56 + y + h // 2)],
                    ['mouseup', '1'],
                ):
                    run(['xdotool', *command], d.env)
                    time.sleep(.2)
                time.sleep(.7)
                drawing = working.read_bytes()
                assert drawing != old_drawing, 'Test did not create a working pencil stroke'
                before = shot(d, 'paint-before')
                album(d, width)
                d.click_actual(28, 28)
                after = shot(d, 'paint-return')
                assert working.read_bytes() == drawing, 'Album changed working drawing bytes'
                same(before, after, (x, 56 + y, x + w, 56 + y + h), 'Unsaved drawing changed on return')
            d.key('Escape')
            d.game('123 Book')
            # Pause autoplay before comparing the selected number page.
            d.key('space')
            for width, height in ((960, 600), (320, 568)):
                d.resize(width, height)
                before = shot(d, 'numbers-before')
                album(d, width, abc=True)
                d.key('Escape')
                same(before, shot(d, 'numbers-return'), (0, 58, width, height), 'Number activity changed')

# The entry also exists before any item is earned; opening it never grants an item.
with tempfile.TemporaryDirectory(dir=work) as directory:
    data = Path(directory)
    (data / 'guide-seen.txt').write_text('yes')
    with Desktop(BINARY, data) as d:
        d.resize(320, 568)
        album(d, 320, title=True)
        d.key('Escape')
        assert not (data / 'collection.txt').exists(), 'Viewing an empty album collected something'
print('local collection-book UI tests passed: title, earned enlargement/back, unsaved Coloring Book, paused 123 Book, empty album; EN/DE/ES at desktop + narrow phone sizes')

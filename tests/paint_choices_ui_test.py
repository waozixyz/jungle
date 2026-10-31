"""Exercise categorized scenes and all crayons through the real private UI."""
import json
import re
import tempfile
from pathlib import Path

from runtime_test import DIGITS, PICTURE_HEADER, ROOT, picture_runs, picture_pixels
from paint_library_test import scene_click, scene_layout
from paint_history_test import Desktop, WORK, changed, open_paint, pixel_click, tool


WORK.mkdir(parents=True, exist_ok=True)
catalog = json.loads((ROOT / 'tools/coloring_catalog.json').read_text())
with tempfile.TemporaryDirectory(prefix='paint-choices-', dir=WORK) as temporary:
    data = Path(temporary)
    working = data / 'games/jungle.paint/working.txt'
    with Desktop(ROOT / 'build/app/jungle', data) as desktop:
        desktop.game('Coloring Book')
        first = desktop.wait_scene_picker('paint-scenes-page-1')
        desktop.click_actual(28, 28)
        desktop.wait_menu('paint-title-back-to-menu')
        desktop.game('Coloring Book')
        first = desktop.wait_scene_picker('paint-scenes-title-back-reopened')
        scene_click(desktop, 'next')
        second = desktop.capture('paint-scenes-page-2', header=56)
        assert first.crop((20, 51, 299, 162)).tobytes() != second.crop((20, 51, 299, 162)).tobytes()
        scene_click(desktop, 'previous')
        back = desktop.capture('paint-scenes-previous', header=56)
        assert first.crop((20, 51, 299, 162)).tobytes() == back.crop((20, 51, 299, 162)).tobytes(), 'Previous did not return to the original scenes'
        seen = set()
        for category, name in enumerate(('nature', 'places', 'adventures')):
            scenes = [row for row in catalog['scenes'] if row['category'] == name]
            for position, scene in enumerate(scenes):
                if seen:
                    tool(desktop, 7)
                    desktop.capture('paint-new-picture-confirm', header=56)
                    desktop.click(80, 90)
                    desktop.wait_scene_picker('paint-next-background')
                scene_click(desktop, 'category', category)
                scene_click(desktop, 'previous')
                for _ in range(position // 6):
                    scene_click(desktop, 'next')
                offset = position % 6
                scene_click(desktop, 'tile', offset)
                desktop.key('Escape')
                desktop.capture('paint-selected-scene', header=56)
                index = scene['asset_id'] - 1
                assert working.read_bytes()[len(PICTURE_HEADER)] == ord(DIGITS[index]), 'Scene page selected a different background'
                seen.add(index)
        assert seen == set(range(24)), 'A categorized scene was unreachable'
        selected_scene = working.read_bytes()[len(PICTURE_HEADER)]
        tool(desktop, 1)
        desktop.capture('paint-expanded-colors', header=56)
        desktop.click_actual(28, 28)
        desktop.capture('paint-colors-title-back', header=56)
        assert working.read_bytes()[len(PICTURE_HEADER)] == selected_scene, 'Title-bar Back changed the working picture'
        tool(desktop, 1)
        colors = desktop.capture('paint-expanded-colors', header=56)
        source = (ROOT / 'games/paint/paint_palette.zi').read_text()
        palette = [int(value, 16) for value in re.findall(r'0x([0-9a-f]{8})', source)]
        order_text = re.search(r'crayon_order:.*?= \.\[(.*?)\];', source, re.S)[1]
        order = [int(value.strip().replace('CHARCOAL_PAINT', '63')) for value in order_text.split(',')]
        assert len(order) == len(set(palette[i] for i in order)) == 42
        for index, color in enumerate(order):
            rgb = tuple((palette[color] >> shift) & 255 for shift in (24, 16, 8))
            assert colors.getpixel((38 + index % 7 * 41, 40 + index // 7 * 23)) == rgb, f'Crayon {index} is missing or obscured'
        desktop.click(284, 155)
        desktop.capture('paint-charcoal-selected', header=56)
        before = working.read_bytes()
        pixels = picture_pixels(before)
        paper = next((x, y) for y in range(20, 700, 20) for x in range(20, 940, 20)
                     if (pixels[y-3:y+4, x-3:x+4] == 15).all())
        pixel_click(desktop, *paper)
        saved = changed(working, before)
        assert saved[len(PICTURE_HEADER) + 1] == ord(DIGITS[47]), 'Charcoal selection was not saved'
        painted_colors = {color for color, length in picture_runs(saved)}
        assert 63 in painted_colors, 'The bucket did not use charcoal'
        assert 0 in painted_colors, 'Painting removed the outline ink'
    with Desktop(ROOT / 'build/app/jungle', data) as desktop:
        open_paint(desktop, 'paint-new-scene-resumed')
        assert working.read_bytes() == saved, 'The background or paint changed on reopening'
print('local UI test: categorized pagination, all24 scenes, 42 crayons and charcoal save/resume passed')

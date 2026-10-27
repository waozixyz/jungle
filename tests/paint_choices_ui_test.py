"""Exercise scene pagination and all crayons through the real private UI."""
import re
import tempfile
from pathlib import Path

from runtime_test import Desktop, DIGITS, PICTURE_HEADER, ROOT, picture_pixels


with tempfile.TemporaryDirectory(prefix="jungle-paint-choices-") as temporary:
    data = Path(temporary)
    working = data / 'games/jungle.paint/working.txt'
    with Desktop(ROOT / 'build/app/jungle', data) as desktop:
        desktop.game('Coloring Book')
        first = desktop.capture('paint-scenes-page-1')
        desktop.click(180, 180)
        second = desktop.capture('paint-scenes-page-2')
        assert first.crop((20, 30, 299, 162)).tobytes() != second.crop((20, 30, 299, 162)).tobytes()
        desktop.click(50, 180)
        back = desktop.capture('paint-scenes-previous')
        assert first.crop((20, 30, 299, 162)).tobytes() == back.crop((20, 30, 299, 162)).tobytes(), 'Previous did not return to the original scenes'
        desktop.click(180, 180)
        for index in range(6, 12):
            offset = index - 6
            desktop.click(65 + offset % 3 * 94, 60 + offset // 3 * 68)
            desktop.capture(f'paint-new-scene-{index + 1}')
            assert working.read_bytes()[len(PICTURE_HEADER)] == ord(DIGITS[index]), 'The scene page selected a different background'
            desktop.key('Escape')
            if index < 11:
                # Reopen the gallery through New picture, using Erase.
                desktop.click(30, 87)
                desktop.capture('paint-new-picture-confirm')
                desktop.click(104, 130)
                desktop.capture('paint-next-background')
        desktop.click(30, 40)
        colors = desktop.capture('paint-expanded-colors')
        source = (ROOT / 'games/paint/paint_palette.zi').read_text()
        palette = [int(value, 16) for value in re.findall(r'0x([0-9a-f]{8})', source)]
        order_text = re.search(r'crayon_order:.*?= \.\[(.*?)\];', source, re.S)[1]
        order = [int(value.strip().replace('CHARCOAL_PAINT', '63')) for value in order_text.split(',')]
        assert len(order) == len(set(palette[i] for i in order)) == 42
        for index, color in enumerate(order):
            rgb = tuple((palette[color] >> shift) & 255 for shift in (24, 16, 8))
            assert colors.getpixel((38 + index % 7 * 41, 40 + index // 7 * 23)) == rgb, f'Crayon {index} is missing or obscured'
        desktop.click(284, 155)
        desktop.click(180, 140)
        desktop.capture('paint-charcoal-fill')
        saved = working.read_bytes()
        assert saved[len(PICTURE_HEADER) + 1] == ord(DIGITS[47]), 'Charcoal selection was not saved'
        assert (picture_pixels(saved) == 63).any(), 'The bucket did not use charcoal'
        assert (picture_pixels(saved) == 0).any(), 'Painting removed the outline ink'
    with Desktop(ROOT / 'build/app/jungle', data) as desktop:
        desktop.game('Coloring Book')
        desktop.capture('paint-new-scene-resumed')
        assert working.read_bytes() == saved, 'The new background or paint changed on reopening'
print('local UI test: two scene pages, six new backgrounds, 42 crayons and charcoal save/resume passed')

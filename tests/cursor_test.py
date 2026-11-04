"""Fast: Jungle's one hand cursor and every game cursor are clean, crisp images.

Each host sets the hand once with CursorSetDefault. Every cursor image is an
exact lossless WebP drawn at a whole 2x or 4x of its logical size (Jungle's own
at 4x: 128 px for 32 units), whose soft edge is dark outline, never a light
matte, and whose hotspot lies on the picture.
"""
from pathlib import Path
import re
import unittest

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PROPS = re.compile(r'asset_path\s*=\s*(?:"([^"]+)"|(JUNGLE_CURSOR_ASSET))\s*,\s*\.width\s*=\s*(\d+)\s*,\s*'
                   r'\.height\s*=\s*(\d+)\s*,\s*\.hotspot_x\s*=\s*(\d+)\s*,\s*\.hotspot_y\s*=\s*(\d+)')


def cursors():
    """(source file, asset, width, height, hotspot x, hotspot y) for every bitmap cursor."""
    hand = re.search(r'JUNGLE_CURSOR_ASSET\s*::\s*"([^"]+)"', (ROOT / 'host/jungle_cursor.zi').read_text())[1]
    found = []
    for source in sorted([*ROOT.glob('host/*.zi'), *ROOT.glob('web/*.zi'), *ROOT.glob('games/*/*.zi')]):
        text = source.read_text()
        for match in PROPS.finditer(text):
            asset = match[1] or hand
            found.append((source.relative_to(ROOT), asset, *map(int, match.groups()[2:])))
    return found


class CursorTest(unittest.TestCase):
    def test_every_host_sets_the_hand_once(self):
        for host in ('host/desktop.zi', 'web/jungle_web.zi'):
            self.assertEqual((ROOT / host).read_text().count('CursorSetDefault(JungleHandCursor())'), 1, host)
        # The Farm no longer draws its own hand over the application cursor.
        self.assertNotIn('hand-pointer', (ROOT / 'host/jungle_host.zi').read_text())

    def test_cursor_images_are_clean(self):
        seen = cursors()
        self.assertIn(Path('host/jungle_cursor.zi'), {row[0] for row in seen})
        for source, asset, width, height, hx, hy in seen:
            with self.subTest(source=str(source), asset=asset):
                path = ROOT / asset
                self.assertTrue(path.is_file())
                self.assertEqual(path.read_bytes()[12:16], b'VP8L', 'cursor WebP must be lossless')
                self.assertTrue(0 < width <= 32 and 0 < height <= 32)
                with Image.open(path) as image:
                    size = image.size
                    rgba = np.asarray(image.convert('RGBA')).astype(np.int32)
                # A whole density of the logical size, the same on both axes.
                scale = size[0] // width
                self.assertIn(scale, (2, 4))
                self.assertEqual(size, (width * scale, height * scale))
                if asset.startswith('assets/jungle/'):
                    self.assertEqual((size, width, height), ((128, 128), 32, 32))
                alpha = rgba[..., 3]
                light = 0.299 * rgba[..., 0] + 0.587 * rgba[..., 1] + 0.114 * rgba[..., 2]
                # A faint light pixel is the white fringe this replaced.
                self.assertEqual(int(((alpha > 0) & (alpha < 200) & (light > 140)).sum()), 0)
                self.assertEqual(int(((alpha == 0) & (rgba[..., :3].sum(axis=2) > 0)).sum()), 0)
                # Hidden edges stay inside the image with room for the outline.
                self.assertTrue((alpha[[0, -1], :] == 0).all() and (alpha[:, [0, -1]] == 0).all())
                cell = alpha[hy * scale:hy * scale + scale, hx * scale:hx * scale + scale]
                self.assertGreater(int(cell.max()), 0, 'hotspot must lie on the picture')

    def test_hand_hotspot_is_the_fingertip(self):
        text = (ROOT / 'host/jungle_cursor.zi').read_text()
        _, _, _, _, hx, hy = next(row for row in cursors() if row[0] == Path('host/jungle_cursor.zi'))
        with Image.open(ROOT / re.search(r'"(assets/[^"]+)"', text)[1]) as image:
            alpha = np.asarray(image.getchannel('A'))
        top = int(np.where((alpha >= 128).any(axis=1))[0][0])
        self.assertLessEqual(abs(hy * 4 - top), 4)
        tip = np.where(alpha[top] >= 128)[0]
        self.assertLessEqual(abs(hx * 4 + 2 - tip.mean()), 4)


if __name__ == '__main__':
    unittest.main()

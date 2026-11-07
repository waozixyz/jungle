import json
import unittest
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from paint_pages import dinosaur, render, fit, CANVAS, TALL

NEW_STENCILS = {
    53: 8,
    54: 8,
    55: 12,
    **{asset_id: 3 for asset_id in range(56, 67)},
}


class PaintStencilRegionsTest(unittest.TestCase):
    def test_new_stencils_have_closed_fill_regions(self):
        for asset_id, minimum_regions in NEW_STENCILS.items():
            with self.subTest(asset_id=asset_id):
                svg, width, height, _, _ = dinosaur(asset_id)
                with render(svg, *fit(width, height, *CANVAS)) as image:
                    pixels = np.asarray(image.convert("RGBA"))
                    image_size = image.size

                ink = (pixels[:, :, 3] > 16) & (pixels[:, :, :3].max(axis=2) < 160)
                paper = ((pixels[:, :, 3] > 240) &
                         (pixels[:, :, :3].min(axis=2) >= 160))
                self.assertEqual(pixels[0, 0, 3], 0, "top-left corner is not transparent")
                self.assertEqual(pixels[0, -1, 3], 0, "top-right corner is not transparent")
                self.assertEqual(pixels[-1, 0, 3], 0, "bottom-left corner is not transparent")
                self.assertEqual(pixels[-1, -1, 3], 0, "bottom-right corner is not transparent")

                outside = np.zeros(pixels.shape[:2], dtype=bool)
                outside[0] |= ~ink[0]
                outside[-1] |= ~ink[-1]
                outside[:, 0] |= ~ink[:, 0]
                outside[:, -1] |= ~ink[:, -1]
                while True:
                    expanded = ndimage.binary_dilation(outside) & ~ink
                    if np.array_equal(expanded, outside):
                        break
                    outside = expanded
                self.assertEqual(np.count_nonzero(outside & paper), 0,
                                 "an interior region leaks to the image border")

                labels, count = ndimage.label(paper & ~outside)
                sizes = ndimage.sum_labels(paper & ~outside, labels,
                                           range(1, count + 1))
                regions = np.count_nonzero(sizes >= 100)
                self.assertGreaterEqual(regions, minimum_regions)
                # Tall/narrow silhouettes keep their aspect ratio; their long
                # edge still reaches full page resolution.
                self.assertGreaterEqual(max(image_size), 720)


class PaintSceneAreasTest(unittest.TestCase):
    def test_named_areas_stay_apart(self):
        """A fill started in one named area never reaches another, on the
        page's mask as tools/paint_pages.py makes it."""
        pages = json.loads((ROOT / "tools/coloring_areas.json").read_text())["pages"]
        four = ndimage.generate_binary_structure(2, 1)
        for name, areas in pages.items():
            with self.subTest(page=name):
                size = TALL if name.startswith("portrait") else CANVAS
                page = render((ROOT / f"art/paint/{name}.svg").read_text(), *size)
                labels, _ = ndimage.label(np.asarray(page.convert("L")) >= 128, four)
                found = {area: labels[y, x] for area, (x, y) in areas.items()}
                self.assertNotIn(0, found.values(), f"a point is on a line: {found}")
                self.assertEqual(len(set(found.values())), len(found), f"areas share a fill: {found}")


if __name__ == "__main__":
    unittest.main()

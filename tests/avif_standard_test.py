"""Fast shipping policy: exact technical exceptions, no PNG/JPEG artwork, and
export roles: 'exact' keeps every RGBA value; 'cutout' keeps exact alpha with
q70 4:4:4 color."""
from pathlib import Path
import sys
import tempfile
import unittest
from PIL import Image
from canonical_avif_test import enforce_standard, noncanonical_rasters

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import image_exports


class AVIFStandardTest(unittest.TestCase):
    def test_assets_follow_standard(self):
        enforce_standard()

    def test_unknown_paths_and_case_variants_are_rejected(self):
        allowed = {'assets/font.png': 'Technical font atlas'}
        self.assertEqual(noncanonical_rasters([
            'assets/font.png', 'assets/art.avif', 'assets/art.webp', 'assets/art.PNG',
            'assets/font/new.png', 'assets/art.jpg', 'assets/art.JPEG'], allowed),
            ['assets/art.JPEG', 'assets/art.PNG', 'assets/art.jpg', 'assets/art.webp', 'assets/font/new.png'])

    def test_transparent_exact_role_keeps_every_rgba_value(self):
        # Regression: role 'exact' once took the cut-out path and changed RGB.
        picture = Image.new('RGBA', (48, 32))
        picture.putdata([((x * 37) % 256, (y * 53) % 256, (x * y * 11) % 256,
                          0 if x < 8 else (x * 9 + y) % 256)
                         for y in range(32) for x in range(48)])
        (ROOT / 'work').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'work', prefix='avif-roles-') as folder:
            source = Path(folder) / 'stencil.png'
            picture.save(source)
            cache = Path(folder) / 'cache'
            exact = image_exports.optimize_new_image_exports(source, 'exact', cache)
            self.assertTrue(exact.lossless)
            self.assertIsNone(exact.quality)
            with Image.open(exact.source) as decoded:
                # Hidden RGB under alpha 0 is kept as well.
                self.assertEqual(decoded.convert('RGBA').tobytes(), picture.tobytes())
            cutout = image_exports.optimize_new_image_exports(source, 'cutout', cache)
            self.assertNotEqual(cutout.source, exact.source)
            self.assertFalse(cutout.lossless)
            self.assertEqual(cutout.quality, image_exports.CUTOUT_QUALITY)
            with Image.open(cutout.source) as decoded:
                self.assertEqual(decoded.convert('RGBA').getchannel('A').tobytes(),
                                 picture.getchannel('A').tobytes())


if __name__ == '__main__':
    unittest.main()

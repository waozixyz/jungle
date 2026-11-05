"""Fast shipping policy: exact technical exceptions, no PNG/JPEG artwork."""
import unittest
from canonical_avif_test import enforce_standard, noncanonical_rasters


class AVIFStandardTest(unittest.TestCase):
    def test_assets_follow_standard(self):
        enforce_standard()

    def test_unknown_paths_and_case_variants_are_rejected(self):
        allowed = {'assets/font.png': 'Technical font atlas'}
        self.assertEqual(noncanonical_rasters([
            'assets/font.png', 'assets/art.avif', 'assets/art.webp', 'assets/art.PNG',
            'assets/font/new.png', 'assets/art.jpg', 'assets/art.JPEG'], allowed),
            ['assets/art.JPEG', 'assets/art.PNG', 'assets/art.jpg', 'assets/art.webp', 'assets/font/new.png'])


if __name__ == '__main__':
    unittest.main()

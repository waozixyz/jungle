"""Every unlockable game has exactly one shipped award, in catalog order."""
import hashlib
import json
from pathlib import Path
import re
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def table(name):
    source = (ROOT / 'host/jungle_awards.zi').read_text()
    match = re.search(rf'^{name}: \[(\d+)\]string = \.\[(.*?)\];', source, re.M | re.S)
    values = re.findall(r'"([^"]*)"', match.group(2))
    assert int(match.group(1)) == len(values), name
    return values


def catalog():
    return [line.split('|') for line in (ROOT / 'games/catalog.txt').read_text().splitlines() if line.strip()]


class AwardAssetsTest(unittest.TestCase):
    def test_one_award_per_catalog_game(self):
        bundles = table('award_bundles')
        self.assertEqual(bundles, [fields[0] for fields in catalog()])
        count = int(re.search(r'^AWARD_COUNT :: (\d+)$', (ROOT / 'host/jungle_awards.zi').read_text(), re.M).group(1))
        self.assertEqual(count, len(bundles))
        for name in ('award_apps', 'award_slugs', 'award_pictures'):
            values = table(name)
            self.assertEqual(len(values), count, name)
            self.assertEqual(len(set(values)), count, name)

    def test_web_games_share_the_catalog_index(self):
        web = (ROOT / 'web/jungle_web.zi').read_text()
        titles = re.findall(r'MenuGame\.\{\.title = "([^"]+)"\}', web)
        self.assertEqual(titles, [fields[1] for fields in catalog()])

    def test_award_folders_are_the_games_identities(self):
        makefile = (ROOT / 'Makefile').read_text()
        for bundle, app in zip(table('award_bundles'), table('award_apps')):
            rule = re.search(rf'^\$\(APP\)/games/{re.escape(bundle)}:.*?-o \$@ (games/\S+\.zi)$', makefile, re.M | re.S)
            self.assertIsNotNone(rule, bundle)
            self.assertIn(f'AppIdentity("{app}")', (ROOT / rule.group(1)).read_text(), bundle)

    def test_pictures_are_clean_lossless_cutouts(self):
        provenance = json.loads((ROOT / 'tools/art_provenance/game-awards.json').read_text())
        recorded = {entry['runtime']: entry for entry in provenance['awards']}
        self.assertEqual([entry['game'] for entry in provenance['awards']], table('award_bundles'))
        for path in table('award_pictures'):
            self.assertTrue(path.startswith('assets/jungle/awards/') and path.endswith('.webp'), path)
            data = (ROOT / path).read_bytes()
            self.assertEqual(data[12:16], b'VP8L', path)
            self.assertEqual(hashlib.sha256(data).hexdigest(), recorded[path]['sha256'], path)
            with Image.open(ROOT / path) as picture:
                self.assertEqual(picture.size, (384, 384), path)
                alpha = picture.convert('RGBA').getchannel('A')
                for corner in ((0, 0), (383, 0), (0, 383), (383, 383)):
                    self.assertEqual(alpha.getpixel(corner), 0, path)
                opaque = alpha.point(lambda value: 255 if value == 255 else 0).histogram()[255]
                self.assertGreater(opaque, 384 * 384 // 3, path)


if __name__ == '__main__':
    unittest.main()

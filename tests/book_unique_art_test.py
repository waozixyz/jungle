#!/usr/bin/env python3
"""Validate new page art and preserve baseline canonical source assets."""
import hashlib
import json
from pathlib import Path
import re
import unittest
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
def digest(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
def baseline_entries():
    # The pre-expansion inventory is streamed one entry at a time.
    inventory = ROOT / 'work/source-asset-fingerprints.json'
    if not inventory.exists():
        return
    with inventory.open() as stream:
        key = None
        for line in stream:
            match = re.match(r'  "([^"]+)": \{', line)
            if match:
                key = match.group(1)
            match = re.search(r'"sha256": "([0-9a-f]{64})"', line)
            if match and key:
                yield key, match.group(1)
                key = None
class UniqueBookArtTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ids = set(json.loads((ROOT/'tools/book_unique_expansion.json').read_text())['words'])
        cls.meta = {i: json.loads((ROOT/f'art/generated/book-unique-expansion/{i}.json').read_text()) for i in cls.ids}
    def test_exact_inventory_and_pages(self):
        self.assertEqual(len(self.ids), 36)
        self.assertEqual({p.stem for p in (ROOT/'art/generated/book-unique-expansion').glob('*.json')}, self.ids)
        for i, m in self.meta.items():
            with self.subTest(subject=i), Image.open(ROOT/m['page']) as im:
                self.assertEqual(m['page'], f'assets/jungle-book/pages/{i}.jpg')
                self.assertEqual((im.format, im.mode, im.size), ('JPEG', 'RGB', (1254,1254)))
                im.load()
    def test_sources_and_fingerprints(self):
        for i,m in self.meta.items():
            with self.subTest(subject=i):
                self.assertEqual(m['tool'], 'built-in image_gen')
                self.assertRegex(m['source_sha256'], r'^[0-9a-f]{64}$')
                self.assertEqual(m['dimensions'], [1254,1254])
                if (ROOT/m['original']).exists():
                    with Image.open(ROOT/m['original']) as im:
                        self.assertEqual(im.format, 'PNG')
                        self.assertEqual(im.width, im.height)
                        self.assertGreaterEqual(im.width,1254)
                        im.verify()
                    self.assertEqual(digest(ROOT/m['original']),m['source_sha256'])
                self.assertEqual(digest(ROOT/m['page']),m['page_sha256'])
                self.assertTrue(m['reference_images'])
                self.assertTrue(m['source'].endswith('.png'))
    def test_uniqueness_and_prompt_inventory(self):
        prompts=json.loads((ROOT/'tools/book_prompts.json').read_text())['pages']
        for field in ('source_sha256','page_sha256'):
            self.assertEqual(len({m[field] for m in self.meta.values()}),36)
        for i,m in self.meta.items():
            self.assertEqual(prompts[i],m['prompt'])
    def test_no_old_canonical_asset_overwrites(self):
        # Existing tracked aggregate guard also runs in clean CI checkouts.
        from book_expansion_test import LearningBookTest
        LearningBookTest("test_original_assets_unchanged").test_original_assets_unchanged()
        count=0
        for path,expected in baseline_entries():
            # Derived covers are rebuilt by the catalog owner. New additions
            # are deliberately never promoted to baseline originals here.
            canonical = path.startswith(('assets/jungle-book/pages/','assets/jungle-book/items/','assets/animal-counting/'))
            canonical |= '/sounds/' in path
            if not canonical or Path(path).stem in self.ids:
                continue
            with self.subTest(path=path):
                self.assertTrue((ROOT/path).is_file(),path)
                self.assertEqual(digest(ROOT/path),expected,path)
            count+=1
        if (ROOT/"work/source-asset-fingerprints.json").exists():
            self.assertGreater(count,248)
if __name__=='__main__': unittest.main()

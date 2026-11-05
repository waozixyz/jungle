"""A format-migration replay must never replace newer approved artwork."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import migrate_asset_avif as migration


class ReplaySafety(unittest.TestCase):
    def setUp(self):
        scratch = ROOT/'local/art-development/avif-migration/tests'
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.archive = self.root/'backup/avif-migration'
        self.cache = self.root/'local/art-development/avif-migration'
        self.receipt = self.root/'tools/canonical_avif.json'
        self.receipt.parent.mkdir(parents=True)
        self.asset = self.root/'assets/map.avif'
        self.asset.parent.mkdir()
        shutil.copyfile(ROOT/'assets/beach_families/background.avif', self.asset)
        self.pixels = self.asset.read_bytes()
        for name, value in (('ROOT', self.root), ('ARCHIVE', self.archive),
                            ('CACHE', self.cache), ('RECEIPT', self.receipt)):
            mocking = patch.object(migration, name, value)
            mocking.start()
            self.addCleanup(mocking.stop)
        # These fixture folders are disposable; production still requires
        # git check-ignore before every private backup/cache write.
        mocking = patch.object(migration.subprocess, 'run')
        mocking.start()
        self.addCleanup(mocking.stop)

    def write_receipt(self, source='local/approved-map.png', quality=35):
        self.receipt.write_text(json.dumps({'files': {'assets/map.avif': {
            'source': source, 'sha256': hashlib.sha256(self.pixels).hexdigest(),
            'quality': quality}}, 'migration_baseline': {'bytes': 324218932}}, indent=3)+'\n')
        return self.receipt.read_bytes()

    def run_apply(self):
        with patch.object(sys, 'argv', ['migrate_asset_avif.py', '--apply']):
            migration.main()

    def test_replay_preserves_new_map_q50_and_original_rows_without_encoding(self):
        for source, quality in (('local/approved-map.png', 35),
                                ('assets/map.webp', 50), ('assets/map.webp', None)):
            before = self.write_receipt(source, quality)
            with patch.object(migration, 'migrate', side_effect=AssertionError('archive replay')):
                self.run_apply()
            self.assertEqual(self.asset.read_bytes(), self.pixels)
            self.assertEqual(self.receipt.read_bytes(), before)

    def test_changed_destination_refuses_without_replacing_art_or_metadata(self):
        before = self.write_receipt()
        changed = self.pixels+b'new approved payload'
        self.asset.write_bytes(changed)
        with self.assertRaisesRegex(AssertionError, 'changed approved AVIF'):
            self.run_apply()
        self.assertEqual(self.asset.read_bytes(), changed)
        self.assertEqual(self.receipt.read_bytes(), before)

    def test_backup_alone_does_not_authorize_replay(self):
        old = self.archive/'assets/map.webp'
        old.parent.mkdir(parents=True)
        old.write_bytes(b'old source')
        with self.assertRaisesRegex(AssertionError, 'backup alone'):
            self.run_apply()
        self.assertEqual(self.asset.read_bytes(), self.pixels)
        self.assertFalse(self.receipt.exists())

    def test_live_webp_cannot_replace_divergent_existing_avif(self):
        live = self.root/'assets/map.webp'
        live.write_bytes(b'live WebP input')
        with patch.object(migration, 'migrate', return_value=('assets/map.avif', {'sha256': 'different'})):
            with self.assertRaisesRegex(AssertionError, 'existing AVIF'):
                self.run_apply()
        self.assertEqual(self.asset.read_bytes(), self.pixels)
        self.assertEqual(live.read_bytes(), b'live WebP input')
        self.assertFalse(self.receipt.exists())

    def test_completed_migration_refuses_reintroduced_webp(self):
        before = self.write_receipt()
        live = self.root/'assets/map.webp'
        live.write_bytes(b'old input reintroduced')
        with self.assertRaisesRegex(AssertionError, 'Migration already completed'):
            self.run_apply()
        self.assertEqual(self.asset.read_bytes(), self.pixels)
        self.assertEqual(self.receipt.read_bytes(), before)
        self.assertTrue(live.exists())


if __name__ == '__main__':
    unittest.main()

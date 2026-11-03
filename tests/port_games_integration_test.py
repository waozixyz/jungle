"""Port games keep their routes, saves and reviewed pictures on every host."""
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_web
import shared_assets
from web_images import preview_path

FISH = ('clownfish', 'blue-tang', 'butterflyfish', 'angelfish', 'parrotfish', 'pufferfish')
GAMES = (
    ('jungle-fishing', 'fishing', 'jungle_fishing', 'Fishing', 'Little Fishing Boat',
     'Cast, meet and release', 'fishing', 12),
    ('jungle-beach-families', 'beach_families', 'jungle_beach_families', 'BeachFamilies',
     'Crab Family Counting', 'Count the crab family', 'beach-families', 13),
)
OLD_TITLES = ('Picture Book', 'ABC Book', '123 Book', 'Animal Counting', 'Coloring Book',
              'Jigsaw Puzzles', 'Little Piano', 'Shapes & Sorting', 'Matching Pairs',
              'Hide & Seek', 'Music Room', 'Farm')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def expected_art():
    pictures = {f'assets/fishing/{name}.webp': name != 'background'
                for name in ('background', 'boat', *FISH)}
    pictures.update({f'assets/beach_families/{name}.webp': name != 'background'
                     for name in ('background', 'crab-adult', 'crab-baby')})
    pictures.update({f'assets/jungle/covers/{cover}.webp': None
                     for cover in ('fishing', 'beach-families')})
    return pictures


class Registration(unittest.TestCase):
    def test_reviewed_preview_mapping_and_browser_pack_bytes(self):
        # A tiny isolated tree exercises staging without installing candidate
        # artwork or touching the running app's output.
        with tempfile.TemporaryDirectory(prefix='port-registration-', dir=ROOT / 'work') as directory:
            root = Path(directory)
            files = {}
            for folder in shared_assets.PORT_FOLDERS:
                path = root / folder / 'friend.webp'
                path.parent.mkdir(parents=True)
                image = Image.new('RGBA', (256, 192), (140, 80, 60, 255))
                image.paste((0, 0, 0, 0), (0, 0, 80, 192))
                image.save(path, 'WEBP', lossless=True)
                preview = path.parent / 'previews' / path.name
                preview.parent.mkdir()
                image.thumbnail((128, 128))
                image.save(preview, 'WEBP', lossless=True)
                files[path.relative_to(root).as_posix()] = path
            out = root / 'web'
            out.mkdir()
            with patch.object(shared_assets, 'ROOT', root), patch.object(build_web, 'ROOT', root):
                native = shared_assets.Previews()
                self.assertEqual(set(native), {preview_path(name) for name in files})
                for bundle, folder, *_ in GAMES:
                    self.assertEqual(set(shared_assets.GameFiles(bundle)), {f'assets/{folder}/friend.webp'})
                build_web.write_previews(files, out, groups={})
                manifest = json.loads((out / 'preview-images.json').read_text())
                self.assertEqual(set(manifest['files']), set(files))
                for name, entry in manifest['files'].items():
                    with zipfile.ZipFile(out / entry['pack']) as archive:
                        item = next(item for item in archive.infolist()
                                    if item.header_offset + 30 + len(item.filename.encode()) + len(item.extra) == entry['offset'])
                        payload = archive.read(item)
                    self.assertEqual(hashlib.sha256(payload).hexdigest(), digest(native[preview_path(name)]))
                    with Image.open(io.BytesIO(payload)) as picture:
                        self.assertEqual(picture.size, (128, 96))
                        self.assertEqual(picture.getchannel('A').getextrema(), (0, 255))

    def test_catalog_web_routes_and_save_namespaces_agree(self):
        rows = [line.split('|') for line in (ROOT / 'games/catalog.txt').read_text().splitlines()]
        web = (ROOT / 'web/jungle_web.zi').read_text()
        menu = re.search(r'web_games: \[(\d+)\]MenuGame = \.\[(.*?)\n\];', web, re.S)
        titles = re.findall(r'\.title = "([^"]+)"', menu[2])
        self.assertEqual(int(menu[1]), len(titles))
        self.assertEqual(tuple(titles[:12]), OLD_TITLES)
        self.assertEqual([row[1] for row in rows], titles)
        self.assertEqual(len({row[0] for row in rows}), len(rows))
        for bundle, folder, module, alias, title, about, cover, index in GAMES:
            with self.subTest(game=bundle):
                self.assertEqual(rows[index], [bundle + '.zx', title, about,
                                               f'assets/jungle/covers/{cover}.webp', '2'])
                self.assertIn(f'{alias} :: #import, file "../games/{folder}/{module}.zi";', web)
                self.assertIn(f'if active_game == {index} {{ return {alias}.GameMain() }}', web)
                self.assertIn(f'if active_game == {index} {{ return "jungle.{folder}/" }}', web)
                source = (ROOT / f'games/{folder}/{module}.zi').read_text()
                self.assertIn(f'AppIdentity("jungle.{folder}")', source)
                self.assertRegex(source, r'GameMain :: \(\) -> s32')
        self.assertIn('Runner.DocumentReadHost(Cat(GamePrefix(), name))', web)
        self.assertIn('Runner.DocumentWriteHost(Cat(GamePrefix(), name), value)', web)

    def test_stable_bundle_and_model_test_recipes(self):
        make = (ROOT / 'Makefile').read_text()
        staged = re.search(r'^STAGED_GAMES := (.*)$', make, re.M)[1].split()
        self.assertEqual(staged, list(shared_assets.GAMES))
        sources = re.search(r'^SHARED_SOURCES := (.*)$', make, re.M)[1]
        games = re.search(r'^GAMES := (.*)$', make, re.M)[1]
        prerequisites = re.search(r'^test: (.*)$', make, re.M)[1]
        for bundle, folder, module, *_ in GAMES:
            self.assertRegex(sources, rf'\b{folder}\b')
            self.assertIn(f'$(APP)/games/{bundle}.zx', games.split())
            self.assertIn(f'$(STAGE)/{bundle}.files', make, 'port bundle must use the selected app staging')
            self.assertIn(f'--asset-dir assets=$(STAGE)/{bundle}/assets --entry {module}:main', make,
                          'port bundle must embed its selected app staging')
            self.assertIn(f'build/tests/{folder}', prerequisites.split())
            self.assertIn(f'\tbuild/tests/{folder}\n', make)
        self.assertIn('\tpython3 tests/port_games_integration_test.py\n', make)

    def test_catalog_wording_has_all_three_languages(self):
        locales = json.loads((ROOT / 'locales/ui.json').read_text())
        generated = (ROOT / 'retro/language.zi').read_text()
        for _, _, _, _, title, about, *_ in GAMES:
            for key in (title, about):
                self.assertIn(key, locales)
                self.assertEqual(len(locales[key]), 2)
                for value in (key, *locales[key]):
                    self.assertTrue(value.strip())
                    self.assertIn(json.dumps(value, ensure_ascii=False), generated)

    def test_fish_order_and_crab_picture_bindings(self):
        fishing = (ROOT / 'games/fishing/jungle_fishing.zi').read_text()
        # The saved discovery bit for a species must keep its model index.
        fish_assets = re.search(r'FishAsset ::.*?\n\}', fishing, re.S)[0]
        for index, species in enumerate(FISH[:-1]):
            self.assertIn(f'if fish == {index} {{ return "{species}" }}', fish_assets)
        self.assertIn('return "pufferfish"', fish_assets)
        crab = (ROOT / 'games/beach_families/jungle_beach_families.zi').read_text()
        for name in ('background', 'crab-adult', 'crab-baby'):
            self.assertIn(f'assets/beach_families/{name}.webp', crab)
        self.assertIn('RetroImagePreview(path)', crab)


class ReviewedAssets(unittest.TestCase):
    def test_complete_art_provenance_webp_and_alpha(self):
        manifest = json.loads((ROOT / 'tools/art_provenance/port-games/manifest.json').read_text())
        rows = {row['path']: row for row in manifest['assets']}
        self.assertEqual(len(rows), len(manifest['assets']), 'duplicate provenance paths')
        self.assertTrue(set(expected_art()) <= rows.keys(),
                        'missing reviewed art: ' + ', '.join(sorted(set(expected_art()) - rows.keys())))
        hashes = []
        for name, alpha in expected_art().items():
            row = rows[name]
            with self.subTest(asset=name):
                source = ROOT / row['master']
                if source.is_file():
                    self.assertEqual(digest(source), row['master_sha256'])
                self.assertEqual(digest(ROOT / name), row['sha256'])
                hashes.append(row['sha256'])
                with Image.open(ROOT / name) as full:
                    full.load()
                    self.assertEqual(full.format, 'WEBP')
                    self.assertEqual(list(full.size), row['size'])
                    self.assertGreaterEqual(max(full.size), 700)
                    if alpha is not None:
                        if source.is_file():
                            with Image.open(source) as master: self.assertEqual(full.size, master.size)
                        self.assertEqual('A' in full.getbands(), alpha)
                    if alpha:
                        low, high = full.getchannel('A').getextrema()
                        self.assertEqual(low, 0)
                        self.assertGreaterEqual(high, 240)
                        if source.is_file():
                            with Image.open(source) as master:
                                self.assertEqual(full.getchannel('A').tobytes(), master.getchannel('A').tobytes())
                    if name.startswith('assets/jungle/covers/'):
                        continue
                    preview = ROOT / row['preview']
                    self.assertEqual(digest(preview), row['preview_sha256'])
                    with Image.open(preview) as small:
                        small.load()
                        self.assertEqual(small.format, 'WEBP')
                        self.assertEqual(max(small.size), 128)
                        self.assertLess(abs(full.width / full.height - small.width / small.height), .03)
                        self.assertEqual('A' in small.getbands(), alpha)
                        if alpha:
                            self.assertEqual(small.getchannel('A').getextrema()[0], 0)
        self.assertEqual(len(set(hashes)), len(hashes), 'reused artwork or cover')

    def test_native_bundle_assets_and_canonical_previews(self):
        wanted = {name for name in expected_art() if not name.startswith('assets/jungle/')}
        previews = shared_assets.PortGamePreviews()
        self.assertTrue(wanted <= previews.keys(), 'missing port previews')
        canonical = {preview_path(name): source for name, source in previews.items()}
        installed, aliases, bundles = shared_assets.Plan(previews=canonical)
        for name in wanted:
            bundle = 'jungle-fishing' if name.startswith('assets/fishing/') else 'jungle-beach-families'
            self.assertIn(name, bundles[bundle])
            self.assertEqual(bundles[bundle][name], ROOT / name)
            self.assertEqual(installed[preview_path(name)], previews[name])
            self.assertNotIn(name, aliases)
        for bundle, *_ in GAMES:
            self.assertFalse(any('/previews/' in path for path in bundles[bundle]))

    def test_browser_preview_packs_use_reviewed_exports(self):
        wanted = {name: ROOT / name for name in expected_art() if not name.startswith('assets/jungle/')}
        self.assertTrue(all(path.is_file() for path in wanted.values()), 'missing full art')
        previews = shared_assets.PortGamePreviews()
        self.assertTrue(wanted.keys() <= previews.keys(), 'missing reviewed previews')
        with tempfile.TemporaryDirectory(prefix='port-previews-', dir=ROOT / 'work') as directory:
            out = Path(directory)
            build_web.write_previews(wanted, out)
            manifest = json.loads((out / 'preview-images.json').read_text())
            self.assertEqual(set(manifest['files']), set(wanted))
            for name, entry in manifest['files'].items():
                with zipfile.ZipFile(out / entry['pack']) as archive:
                    item = next(item for item in archive.infolist()
                                if item.header_offset + 30 + len(item.filename.encode()) + len(item.extra) == entry['offset'])
                    payload = archive.read(item)
                self.assertEqual(hashlib.sha256(payload).hexdigest(), digest(previews[name]))
                with Image.open(io.BytesIO(payload)) as picture:
                    self.assertEqual(picture.format, 'WEBP')
                    self.assertEqual(max(picture.size), 128)


if __name__ == '__main__':
    unittest.main()

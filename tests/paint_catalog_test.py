"""Stable multilingual coloring catalog and append-only art integration tests.

Runs without the new source PNGs. Image fixtures stay in memory; SVG fixtures
and compiler intermediates are isolated under ignored work/ and removed.
"""
import copy
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import dino_art
import paint_catalog as catalog
from PIL import Image, ImageDraw

OLD_STENCILS = (
    'TYRANNOSAURUS', 'STEGOSAURUS', 'TRICERATOPS', 'ANATOSAURUS',
    'BRACHIOSAURUS', 'DIPLODOCUS', 'PARASAUROLOPHUS', 'DEINONYCHUS',
    'PROTOCERATOPS', 'PTERANODON', 'STRACOSAURUS', 'CORYTHOSAURUS',
    'Cat', 'Dog', 'Butterfly', 'Child', 'Astronaut', 'Farmer', 'Rabbit',
    'Elephant', 'Lion', 'Doctor', 'Firefighter', 'Cook', 'Crate',
    'Campfire', 'Tent', 'Tree', 'Rock', 'Barrel',
)
OLD_SHORT = ('T-REX', 'STEGO', 'TRIKE', 'Duckbill', 'BRACHIO', 'DIPLO',
             'PARA', 'RAPTOR', 'PROTO', 'PTERANODON', 'STRACO', 'CORY') + OLD_STENCILS[12:]
OLD_SCENES = ('Jungle clearing', 'Volcano valley', 'Waterfall', 'Jungle river',
              'Island beach', 'Mountain lake', 'Meadow', 'Forest', 'Desert',
              'Snowy hills', 'Pond', 'Farmyard')
OLD_ORDER = list(range(12)) + [12, 13, 14, 18, 19, 20, 15, 16, 17, 21, 22, 23] + list(range(24, 30))


class PaintCatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metadata = json.loads(catalog.METADATA.read_text())
        cls.library = catalog.BuildPaintCatalog()
        # Never place test scratch among release/build outputs or outside project.
        ignored = subprocess.run(['git', 'check-ignore', '-q', 'work/paint-catalog-test'],
                                 cwd=ROOT)
        if ignored.returncode:
            raise RuntimeError('Catalog test scratch must be ignored')
        (ROOT / 'work').mkdir(exist_ok=True)

    def test_original_ids_labels_and_category_order(self):
        data = self.library
        self.assertEqual([e['asset_id'] for e in data['stencils']], list(range(1, 47)))
        self.assertEqual([e['asset_id'] for e in data['scenes']], list(range(1, 25)))
        self.assertEqual(tuple(e['labels']['en'] for e in data['stencils'][:30]), OLD_STENCILS)
        self.assertEqual(tuple(e['short_labels']['en'] for e in data['stencils'][:30]), OLD_SHORT)
        self.assertEqual(tuple(e['labels']['en'] for e in data['scenes'][:12]), OLD_SCENES)
        self.assertEqual([i for i in data['stencil_order'] if i < 30], OLD_ORDER)
        self.assertEqual(data['stencil_category_counts'], [16, 10, 10, 10])
        self.assertEqual(data['scene_category_counts'], [14, 5, 5])
        self.assertEqual([e['labels']['en'] for e in data['scene_categories']],
                         ['Nature', 'Places', 'Adventures'])
        self.assertEqual(data['scene_order'],
                         [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15,
                          11, 16, 17, 18, 19, 1, 20, 21, 22, 23])

    def test_every_entry_has_one_category_and_safe_pages(self):
        for kind in ('stencil', 'scene'):
            data = self.library
            count = len(data[kind + 's'])
            self.assertEqual(sorted(data[kind + '_order']), list(range(count)))
            visited = []
            for category, size in enumerate(data[kind + '_category_counts']):
                start = data[kind + '_category_starts'][category]
                group = data[kind + '_order'][start:start + size]
                self.assertEqual(len(group), size)
                for index in group:
                    self.assertEqual(data[kind + '_category_for_index'][index], category)
                pages = [group[page:page + 6] for page in range(0, size, 6)]
                self.assertTrue(all(1 <= len(page) <= 6 for page in pages))
                visited.extend(i for page in pages for i in page)
            self.assertEqual(len(set(visited)), count)

    def test_complete_locales_and_existing_translations(self):
        ui = json.loads((ROOT / 'locales/ui.json').read_text())
        for kind in ('stencil', 'scene'):
            for row in self.library[kind + 's'] + self.library[kind + '_categories']:
                for field in ('labels', 'short_labels') if kind == 'stencil' and 'asset_id' in row else ('labels',):
                    names = row[field]
                    self.assertEqual(set(names), {'en', 'de', 'es'})
                    self.assertTrue(all(names.values()))
                    self.assertTrue(all(ord(c) < 256 for name in names.values() for c in name))
                    if row.get('asset_id', 0) <= catalog.ORIGINAL_COUNTS[kind] and names['en'] in ui:
                        self.assertEqual([names['de'], names['es']], ui[names['en']])

    def test_invalid_metadata_is_rejected(self):
        mutations = (
            lambda d: d['stencils'][0].update(asset_id=2),
            lambda d: d['scenes'][0].update(category='missing'),
            lambda d: d['stencils'][30]['labels'].pop('de'),
            lambda d: d['stencils'][30]['short_labels'].update(es=''),
            lambda d: d['scenes'][12].update(source='../wrong.png'),
            lambda d: d['stencil_categories'].append(d['stencil_categories'][0]),
        )
        for mutate in mutations:
            metadata = copy.deepcopy(self.metadata)
            mutate(metadata)
            with self.assertRaises(ValueError):
                catalog.BuildPaintCatalog(metadata)

    def test_manifest_matches_new_sources_and_preserves_old_entries(self):
        manifest = json.loads((ROOT / 'tools/coloring_stencils.json').read_text())
        original = subprocess.check_output(
            ['git', 'show', 'HEAD:tools/coloring_stencils.json'], cwd=ROOT, text=True)
        baseline = json.loads(original)
        self.assertEqual(manifest['stencils'][:len(baseline['stencils'])], baseline['stencils'])
        # Appending source metadata must not change original prompts or formatting.
        prefix = original[:original.rfind('\n    }\n  ]') + len('\n    }')]
        self.assertTrue((ROOT / 'tools/coloring_stencils.json').read_text().startswith(prefix))
        mapping = {row['index']: row for row in manifest['stencils']}
        self.assertEqual(set(mapping), set(range(13, 47)))
        for row in self.library['stencils'][30:]:
            self.assertEqual(mapping[row['asset_id']]['name'], row['slug'])
            self.assertIn(row['subject'], mapping[row['asset_id']]['prompt'])

    def test_generated_file_is_reproducible_without_ignored_inputs(self):
        generated = catalog.GENERATED.read_text()
        self.assertEqual(catalog.render_catalog(), generated)
        self.assertEqual(catalog.render_catalog(catalog.BuildPaintCatalog(copy.deepcopy(self.metadata))), generated)
        self.assertNotIn('work/', (ROOT / 'tools/paint_catalog.py').read_text())
        subprocess.run([sys.executable, 'tools/paint_catalog.py', '--check'], cwd=ROOT, check=True)

    def test_missing_art_reports_every_source_before_writes(self):
        with patch.object(Path, 'is_file', return_value=False), patch.object(Path, 'write_text') as write:
            with self.assertRaises(FileNotFoundError) as error:
                catalog.compile_new_art(self.library)
            expected = [row['source'] for kind in ('stencils', 'scenes')
                        for row in self.library[kind] if 'source' in row]
            self.assertEqual(str(error.exception).splitlines()[1:], expected)
            self.assertEqual(len(expected), 28)
            write.assert_not_called()
        with patch.object(Path, 'write_text') as write:
            with self.assertRaisesRegex(ValueError, 'Unknown stencil asset IDs'):
                dino_art.standalone_stencils([999])
            write.assert_not_called()

    def test_art_writes_only_new_ids_and_composites_on_white(self):
        # Mock source loading and the external tracer, exercising the actual
        # filtering, thresholding, silhouette construction and SVG writers.
        with tempfile.TemporaryDirectory(prefix='paint-catalog-', dir=ROOT / 'work') as directory:
            root = Path(directory)
            (root / 'tools').mkdir()
            (root / 'tools/coloring_stencils.json').write_text((ROOT / 'tools/coloring_stencils.json').read_text())
            output = root / 'art/paint'
            output.mkdir(parents=True)
            protected = [output / f'{kind}{i}.svg'
                         for kind, total in (('dino', 30), ('scene', 12))
                         for i in range(1, total + 1)]
            for path in protected:
                path.write_text('original ' + path.name)
            before = {path: hashlib.sha256(path.read_bytes()).digest() for path in protected}
            opened, traced = [], []

            def image_open(path):
                opened.append(str(path.relative_to(root)))
                image = Image.new('RGBA', (80, 60), (0, 0, 0, 0))
                ImageDraw.Draw(image).rectangle((20, 15, 60, 45), outline='black', width=3)
                return image

            def trace(image):
                self.assertEqual(image.mode, '1')
                self.assertTrue(image.getbbox())
                self.assertEqual(image.getpixel((0, 0)), 0, 'transparent pixels became ink')
                traced.append(image.size)
                return 'M1 1H10V10H1Z'

            with patch.object(catalog, 'ROOT', root), patch.object(dino_art, 'ROOT', root), \
                    patch.object(dino_art, 'OUT', output), patch.object(Path, 'is_file', return_value=True), \
                    patch.object(Image, 'open', side_effect=image_open), \
                    patch.object(dino_art, 'trace', side_effect=trace), redirect_stdout(io.StringIO()):
                catalog.compile_new_art(self.library)
            self.assertEqual({path: hashlib.sha256(path.read_bytes()).digest() for path in protected}, before)
            expected_sources = [row['source'] for kind in ('stencils', 'scenes')
                                for row in self.library[kind] if 'source' in row]
            self.assertEqual(opened, expected_sources)
            expected_files = {f'dino{i}.svg' for i in range(1, 47)} | {f'scene{i}.svg' for i in range(1, 25)}
            self.assertEqual({path.name for path in output.iterdir()}, expected_files)
            self.assertEqual(len(traced), 16 * 2 + 12)
            self.assertTrue(all(size == (960, 720) for size in traced[-12:]))

    def test_generated_ziran_helpers_execute_in_every_language(self):
        # Compile a private Python target to exercise Ziran imports, bounds and
        # LanguageCode dispatch without building or launching the application.
        toolchain = Path(subprocess.check_output(['ziran', 'pkg', 'path', 'ziran'],
                                                 cwd=ROOT, text=True).strip())
        environment = os.environ.copy()
        for name in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS'):
            environment.pop(name, None)
        with tempfile.TemporaryDirectory(prefix='paint-catalog-', dir=ROOT / 'work') as directory:
            directory = Path(directory)
            lines = [f'#import, file {json.dumps(os.path.relpath(catalog.GENERATED, directory))};',
                     f'#import, file {json.dumps(os.path.relpath(ROOT / "retro/language.zi", directory))};',
                     'main :: () -> s32 {']
            for language in ('en', 'de', 'es', 'unknown'):
                lines.append(f'    LanguageSet("{language}")')
                locale = language if language != 'unknown' else 'en'
                for kind, title in (('stencil', 'Stencil'), ('scene', 'Scene')):
                    for index, row in enumerate(self.library[kind + 's']):
                        name = json.dumps(row['labels'][locale], ensure_ascii=False)
                        lines.append(f'    if Paint{title}Label({index}) != {name} {{ return 1 }}')
                        group = self.library[kind + '_category_for_index'][index]
                        lines.append(f'    if Paint{title}Category({index}) != {group} {{ return 2 }}')
                        if kind == 'stencil':
                            short = json.dumps(row['short_labels'][locale], ensure_ascii=False)
                            lines.append(f'    if PaintStencilShortLabel({index}) != {short} {{ return 3 }}')
                    for category, row in enumerate(self.library[kind + '_categories']):
                        name = json.dumps(row['labels'][locale], ensure_ascii=False)
                        lines.append(f'    if Paint{title}CategoryLabel({category}) != {name} {{ return 4 }}')
                        start = self.library[kind + '_category_starts'][category]
                        size = self.library[kind + '_category_counts'][category]
                        for offset, index in enumerate(self.library[kind + '_order'][start:start + size]):
                            lines.append(f'    if Paint{title}At({category}, {offset}) != {index} {{ return 5 }}')
                        lines.append(f'    if Paint{title}At({category}, {size}) != -1 {{ return 6 }}')
                    count, groups = len(self.library[kind + 's']), len(self.library[kind + '_categories'])
                    for invalid in (-1, count, 2147483647):
                        lines.append(f'    if Paint{title}Label({invalid}) != "" || Paint{title}Category({invalid}) != -1 {{ return 7 }}')
                        if kind == 'stencil':
                            lines.append(f'    if PaintStencilShortLabel({invalid}) != "" {{ return 8 }}')
                    for invalid in (-1, groups, 2147483647):
                        lines.append(f'    if Paint{title}CategoryLabel({invalid}) != "" || Paint{title}At({invalid}, 0) != -1 {{ return 9 }}')
                    lines.append(f'    if Paint{title}At(0, -1) != -1 || Paint{title}At(0, 2147483647) != -1 {{ return 10 }}')
            lines.extend(['    return 0', '}'])
            entry = directory / 'catalog_probe.zi'
            entry.write_text('\n'.join(lines))
            subprocess.run([str(toolchain / 'build/bin/ziran'), 'build', '--target=py', '--exe',
                            '--root', str(directory), '--module-path', f'std={toolchain / "std"}',
                            '--module-path', str(toolchain / 'std'), '--entry', 'catalog_probe:main',
                            '-o', str(directory / 'out'), str(entry)],
                           cwd=ROOT, env=environment, check=True)
            subprocess.run([sys.executable, str(directory / 'out')],
                           cwd=ROOT, env=environment, check=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)

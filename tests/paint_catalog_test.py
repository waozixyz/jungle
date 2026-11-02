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
    def test_catalog_without_native_tracing_library(self):
        script = f'''
import ctypes, sys
sys.path.insert(0, {str(ROOT / 'tools')!r})
original = ctypes.CDLL
def load(name, *args, **kwargs):
    if name == 'libpotrace.so.0':
        raise OSError('native tracer unavailable in this build-only environment')
    return original(name, *args, **kwargs)
ctypes.CDLL = load
import dino_art
from paint_catalog import BuildPaintCatalog
library = BuildPaintCatalog()
assert len(library['stencils']) == 66 and len(library['scenes']) == 30
'''
        subprocess.run([sys.executable, '-c', script], cwd=ROOT, check=True,
                       capture_output=True, text=True)

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
        self.assertEqual([e['asset_id'] for e in data['stencils']], list(range(1, 67)))
        self.assertEqual([e['asset_id'] for e in data['scenes']], list(range(1, 31)))
        self.assertEqual(tuple(e['labels']['en'] for e in data['stencils'][:30]), OLD_STENCILS)
        self.assertEqual(tuple(e['short_labels']['en'] for e in data['stencils'][:30]), OLD_SHORT)
        self.assertEqual(tuple(e['labels']['en'] for e in data['scenes'][:12]), OLD_SCENES)
        self.assertEqual([i for i in data['stencil_order'] if i < 30], OLD_ORDER)
        self.assertEqual(data['stencil_category_counts'], [16, 19, 11, 20])
        self.assertEqual(data['scene_category_counts'], [14, 10, 6])
        self.assertEqual([e['labels']['en'] for e in data['scene_categories']],
                         ['Nature', 'Places', 'Adventures'])
        self.assertEqual([index for index in data['scene_order'] if index < 26],
                         [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15,
                          11, 16, 17, 18, 19, 24, 1, 20, 21, 22, 23, 25])

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

    def test_collectible_ids_match_the_registry(self):
        registry = json.loads(catalog.REGISTRY.read_text())
        slugs = {row['id']: row['slug'] for row in registry['collectibles']}
        for kind, first in (('stencil', 56), ('scene', 27)):
            for row, identifier in zip(self.library[kind + 's'], self.library[kind + '_collectibles']):
                if row['asset_id'] < first:
                    self.assertEqual(identifier, -1)
                else:
                    self.assertEqual(slugs[identifier], row['collectible'])
        self.assertEqual(sorted(i for k in ('stencil', 'scene')
                                for i in self.library[k + '_collectibles'] if i >= 0), sorted(slugs))
        self.assertIn('paint_stencil_collectibles: [66]s32', catalog.GENERATED.read_text())
        self.assertIn('paint_scene_collectibles: [30]s32', catalog.GENERATED.read_text())

    def test_collectibles_follow_defaults_in_each_section(self):
        # A saved picker position among defaults stays right whatever is earned.
        for kind in ('stencil', 'scene'):
            hidden = [self.library[kind + '_collectibles'][i] >= 0 for i in self.library[kind + '_order']]
            for start, size in zip(self.library[kind + '_category_starts'], self.library[kind + '_category_counts']):
                group = hidden[start:start + size]
                self.assertEqual(group, sorted(group))
                self.assertFalse(all(group), 'every section keeps a default')

    def test_bad_collectible_links_are_rejected(self):
        registry = json.loads(catalog.REGISTRY.read_text())
        monkey = next(row for row in registry['collectibles'] if row['slug'] == 'monkey')
        def art(value):
            monkey['paint']['art'] = value
        restore = monkey['paint']['art']
        for change in (lambda d: d['stencils'][55].update(collectible='no-such-slug'),
                       lambda d: d['stencils'][55].update(collectible='panda'),
                       lambda d: d['scenes'][26].update(collectible='monkey'),
                       lambda d: d['stencils'][55].update(category='objects'),
                       lambda d: d['stencils'][55].pop('collectible')):
            metadata = copy.deepcopy(self.metadata)
            change(metadata)
            with self.assertRaises(ValueError):
                catalog.BuildPaintCatalog(metadata, registry)
        for wrong in (None, 55):
            art(wrong)
            with self.assertRaises(ValueError):
                catalog.BuildPaintCatalog(copy.deepcopy(self.metadata), registry)
        art(restore)
        catalog.BuildPaintCatalog(copy.deepcopy(self.metadata), registry)

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
        self.assertEqual(set(mapping), set(range(13, 67)))
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
                        for row in self.library[kind]]
            self.assertEqual(str(error.exception).splitlines()[1:], expected)
            self.assertEqual(len(expected), 96)
            write.assert_not_called()

    def test_production_art_needs_only_committed_vectors(self):
        # No source PNG, ignored archive, or native tracing library is opened.
        import paint_vectors
        with patch.object(Image, 'open', side_effect=AssertionError('raster source read')), \
                patch.object(dino_art, 'trace', side_effect=AssertionError('retrace')), \
                patch.object(Path, 'write_text') as write, redirect_stdout(io.StringIO()):
            catalog.compile_new_art(self.library)
            write.assert_not_called()
        for kind, prefix in (('stencils', 'dino'), ('scenes', 'scene')):
            for row in self.library[kind]:
                self.assertEqual(row['source'], f'art/paint/{prefix}{row["asset_id"]}.svg')
                paint_vectors.validate_source(ROOT / row['source'])

    def test_explicit_stencil_import_preserves_approved_ink_weight(self):
        source = Image.new('RGBA', (80, 60), (0, 0, 0, 0))
        ImageDraw.Draw(source).rectangle((20, 15, 60, 45), outline='black', width=3)
        with patch.object(Image, 'open', return_value=source):
            svg = dino_art.stencil_svg('chosen-reference.png', reinforce=False)
        self.assertIn('id="body"', svg)
        self.assertIn('id="ink"', svg)
        self.assertNotIn('stroke-width', svg)
        self.assertNotIn('<image', svg)

    def test_generated_ziran_helpers_execute_in_every_language(self):
        # Compile a private C target to exercise Ziran imports, bounds and
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
                        identifier = self.library[kind + '_collectibles'][index]
                        lines.append(f'    if Paint{title}Collectible({index}) != {identifier} {{ return 11 }}')
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
                        lines.append(f'    if Paint{title}Collectible({invalid}) != -1 {{ return 12 }}')
                        if kind == 'stencil':
                            lines.append(f'    if PaintStencilShortLabel({invalid}) != "" {{ return 8 }}')
                    for invalid in (-1, groups, 2147483647):
                        lines.append(f'    if Paint{title}CategoryLabel({invalid}) != "" || Paint{title}At({invalid}, 0) != -1 {{ return 9 }}')
                    lines.append(f'    if Paint{title}At(0, -1) != -1 || Paint{title}At(0, 2147483647) != -1 {{ return 10 }}')
            lines.extend(['    return 0', '}'])
            entry = directory / 'catalog_probe.zi'
            entry.write_text('\n'.join(lines))
            subprocess.run([str(toolchain / 'build/bin/ziran'), 'build', '--target=c', '--exe',
                            '--root', str(directory), '--module-path', f'std={toolchain / "std"}',
                            '--module-path', str(toolchain / 'std'), '--entry', 'catalog_probe:main',
                            '-o', str(directory / 'out'), str(entry)],
                           cwd=ROOT, env=environment, check=True)
            subprocess.run([str(directory / 'out/catalog_probe')],
                           cwd=ROOT, env=environment, check=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)

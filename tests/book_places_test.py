#!/usr/bin/env python3
"""The Places book (2026-11-05): catalog slot, AVIF art and EN/DE/ES narration."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
import wave

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
from book_catalog import BOOKS, BOOK_GROUPS, LANGUAGES, NAMES, PLACES, TITLES, WORDS, narration, voice_path
from book_speech import read_clip
from design_size import design_size
from places_book import BLEND, EN_LETTERS, assemble, spelled

PAGES = ('plaza', 'park', 'zoo', 'aquarium', 'city', 'street', 'traffic', 'traffic_light',
         'crosswalk', 'bus_stop', 'market', 'playground', 'train_station', 'library', 'fire_station')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class PlacesBookTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = json.loads((ROOT / 'tools/canonical_avif.json').read_text())['files']
        cls.provenance = json.loads((ROOT / 'tools/art_provenance/places-book.json').read_text())
        cls.settings = json.loads((ROOT / 'speech.json').read_text())['narration']

    def test_catalog_appends_one_book(self):
        self.assertEqual(BOOKS[-1], ('places', PAGES))
        self.assertEqual(len(BOOKS), 42)
        self.assertEqual(NAMES[-len(PAGES):], PAGES)
        self.assertEqual(TITLES['places'], ['Places', 'Orte', 'Lugares'])
        self.assertEqual(dict(BOOK_GROUPS)['Home'][-1], 'places')
        self.assertEqual(json.loads((ROOT / 'locales/ui.json').read_text())['Places'], ['Orte', 'Lugares'])
        self.assertEqual(WORDS['traffic_light'], ('Traffic light', 'Ampel', 'Semáforo'))
        self.assertEqual(WORDS['crosswalk'], ('Crosswalk', 'Zebrastreifen', 'Paso de peatones'))
        pages = (ROOT / 'games/book/book_pages.zi').read_text()
        self.assertIn('CATEGORY_COUNT :: 42\n', pages)
        for name in PAGES:
            self.assertEqual(pages.count(f'"assets/jungle-book/pages/{name}.avif"'), 1)

    def test_art_is_owner_standard_avif(self):
        prompts = json.loads((ROOT / 'tools/book_prompts.json').read_text())['pages']
        self.assertEqual(set(self.provenance['files']), {f'assets/jungle-book/pages/{n}.avif' for n in PAGES})
        self.assertEqual(len({entry['source_png_sha256'] for entry in self.provenance['files'].values()}), len(PAGES))
        for name in PAGES:
            path = f'assets/jungle-book/pages/{name}.avif'
            with self.subTest(name=name):
                entry, row = self.provenance['files'][path], self.canonical[path]
                self.assertEqual(entry['prompt'], prompts[name])
                self.assertEqual(entry['prompt_sha256'], hashlib.sha256(prompts[name].encode()).hexdigest())
                self.assertEqual(entry['generator'], 'built-in imagegen')
                self.assertTrue(all((ROOT / ref).is_file() or ref.startswith('local/') for ref in entry['reference_images']))
                self.assertEqual(digest(ROOT / path), entry['sha256'])
                self.assertEqual((row['sha256'], row['scale'], row['quality'], row['subsampling']),
                                 (entry['sha256'], 0.75, 35, '420'))
                self.assertEqual((row['dimensions'], row['design_dimensions']), ([940, 940], [1254, 1254]))
                self.assertFalse((ROOT / f'assets/jungle-book/items/{name}.avif').exists())
                with Image.open(ROOT / path) as image:
                    self.assertEqual((image.format, image.mode, design_size(ROOT / path, image)), ('AVIF', 'RGB', (1254, 1254)))
        cover = ROOT / 'assets/jungle-book/previews/places.avif'
        self.assertEqual(self.canonical['assets/jungle-book/previews/places.avif']['design_dimensions'], [768, 768])
        with Image.open(ROOT / 'assets/jungle-book/pages/plaza.avif') as scene, Image.open(cover) as preview:
            expected = scene.convert('RGB').resize(preview.size, Image.Resampling.LANCZOS)
            self.assertLess(max(ImageStat.Stat(ImageChops.difference(expected, preview.convert('RGB'))).mean), 12)

    def check_clip(self, path, text, voice):
        receipt = json.loads((ROOT / path).with_suffix('.speech.json').read_text())
        self.assertEqual((receipt['text'], receipt['voice']), (text, voice))
        self.assertEqual(receipt['sha256'], digest(ROOT / path))
        with wave.open(str(ROOT / path)) as clip:
            self.assertEqual((clip.getnchannels(), clip.getsampwidth(), clip.getframerate()), (1, 2, 22050))
            frames = clip.readframes(clip.getnframes())
            self.assertAlmostEqual(receipt['duration'], clip.getnframes() / 22050)
        self.assertTrue(any(memoryview(frames).cast('h')))
        return receipt

    def test_narration_voices(self):
        retakes = self.settings['es']['retakes']
        self.assertEqual(self.settings['en']['books'], {'places': BLEND})
        self.assertEqual(self.settings['en']['blends'][BLEND], {'af_bella': .5, 'af_heart': .5})
        for name in PAGES:
            with self.subTest(name=name):
                english = self.check_clip(voice_path(name, 'en', True), narration(name, 'en', True), BLEND)
                self.assertEqual((english['speed'], english['blend']), (.8, {'af_bella': .5, 'af_heart': .5}))
                for profile in ('slow', 'fast'):
                    slow = 'assets/speech-profiles/' + profile + '/' + voice_path(name, 'en', True).removeprefix('assets/')
                    self.check_clip(slow, narration(name, 'en', True), BLEND)
                german = self.check_clip(voice_path(name, 'de', True), narration(name, 'de', True), 'df_victoria')
                self.assertEqual(german['model'], self.settings['de']['model'])
                spanish = self.check_clip(voice_path(name, 'es', True), narration(name, 'es', True), 'Serena')
                self.assertEqual(spanish['model'], self.settings['es']['model'])
                # Every Spanish clip was chosen by ear-check and pinned.
                self.assertEqual(spanish['seeds'], retakes[voice_path(name, 'es', True)]['seeds'])

    def test_spelling_is_exact_pcm(self):
        for language in LANGUAGES:
            for name in PAGES:
                with self.subTest(name=name, language=language):
                    letters = spelled(name, language)
                    if language == 'en':
                        self.assertTrue(all(letter is None or letter.startswith(EN_LETTERS + '/') for letter in letters))
                    data, _ = assemble(voice_path(name, language, True), letters)
                    receipt = self.check_clip(voice_path(name, language), narration(name, language),
                                              {'en': BLEND, 'de': 'df_victoria', 'es': 'Serena'}[language])
                    self.assertEqual(pcm(ROOT / voice_path(name, language)), data)
                    self.assertEqual([source['path'] for source in receipt['sources']],
                                     [voice_path(name, language, True)] + [l for l in letters if l])
                    for source in receipt['sources']:
                        self.assertEqual(read_clip(ROOT / source['path'])[1], source['sha256'])


def pcm(path):
    with wave.open(str(path)) as clip:
        return clip.readframes(clip.getnframes())


if __name__ == '__main__':
    unittest.main()

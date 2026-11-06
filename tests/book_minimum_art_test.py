import sys
#!/usr/bin/env python3
"""Public provenance and speech coverage for the 109 minimum-book additions."""
import hashlib
import json
from pathlib import Path
import unittest
import wave

from PIL import Image

import book_expansion_test as expansion
from book_catalog import LANGUAGES, MINIMUM, NAMES, WORDS, narration, voice_path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from design_size import design_size

ROOT = Path(__file__).resolve().parents[1]
digest = expansion.digest


class MinimumBookArtTest(unittest.TestCase):
    check_spelling = expansion.LearningBookTest.check_spelling

    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / 'tools/book_minimum_art.json').read_text())
        cls.files = cls.manifest['files']

    def test_exact_inventory_and_provenance(self):
        names = set(MINIMUM['words'])
        self.assertEqual(len(names), 109)
        self.assertEqual(names, set(NAMES[326:435]))
        self.assertEqual(self.manifest['count'], 109)
        self.assertEqual(set(self.files), {f'assets/jungle-book/pages/{name}.avif' for name in names})
        prompts = json.loads((ROOT / 'tools/book_prompts.json').read_text())['pages']
        refresh = json.loads((ROOT / 'tools/book_art_refresh.json').read_text())['files']
        for field in ('sha256', 'source_png_sha256'):
            self.assertEqual(len({entry[field] for entry in self.files.values()}), 109)
        for path, entry in self.files.items():
            with self.subTest(path=path):
                name = Path(path).stem
                self.assertEqual(entry['generator'], 'built-in imagegen')
                self.assertEqual(entry['format'], 'AVIF')
                self.assertEqual(list(design_size(ROOT / path)), [1254, 1254])
                self.assertEqual(digest(ROOT / path), entry['sha256'])
                with Image.open(ROOT / path) as image:
                    self.assertEqual((image.format, image.mode, design_size(ROOT / path, image)), ('AVIF', 'RGB', (1254, 1254)))
                    image.load()
                self.assertEqual(entry['prompt_sha256'], hashlib.sha256(prompts[name].encode()).hexdigest())
                self.assertTrue(entry['reference_images'])
                self.assertTrue(entry['reference_usage'])
                for reference in entry['reference_images']:
                    self.assertTrue((ROOT / reference).is_file(), reference)
                self.assertEqual(entry['source_png_format'], 'PNG')
                self.assertEqual(len(entry['source_png_dimensions']), 2)
                self.assertTrue(all(size >= 1254 for size in entry['source_png_dimensions']))
                self.assertRegex(entry['source_png_sha256'], r'^[0-9a-f]{64}$')
                self.assertEqual(refresh[path], {'previous_sha256': None, 'sha256': entry['sha256']})
                # Public CI needs only tracked exports. Check retained full sources
                # as well when this checkout has the optional ignored backups.
                source = ROOT / f'backup/picture-book-scenes/minimum-books/{name}.png'
                if source.exists():
                    self.assertEqual(digest(source), entry['source_png_sha256'])
                    with Image.open(source) as image:
                        self.assertEqual(image.format, 'PNG')
                        self.assertEqual(list(image.size), entry['source_png_dimensions'])
                        image.verify()
                self.assertFalse((ROOT / f'assets/jungle-book/items/{name}.avif').exists())

    def test_all_327_normal_word_recordings(self):
        self.assertEqual(LANGUAGES, ('en', 'de', 'es'))
        paths = set()
        for name, labels in MINIMUM['words'].items():
            self.assertEqual(WORDS[name], tuple(labels))
            self.assertEqual(len(labels), 3)
            for language in LANGUAGES:
                path = ROOT / voice_path(name, language, True)
                with self.subTest(name=name, language=language):
                    paths.add(path)
                    receipt = json.loads(path.with_suffix('.speech.json').read_text())
                    self.assertEqual(receipt['text'], narration(name, language, True))
                    if language == 'en':
                        self.assertEqual(receipt['voice'], 'af_bella')
                        self.assertEqual(receipt['speed'], 0.8)
                        self.assertEqual(receipt['model'], 'kokoro-82m-uint8')
                        self.assertEqual(receipt['profile'], 'normal')
                        self.assertEqual(receipt['language'], 'en')
                    else:
                        voice = json.loads((ROOT / 'speech.json').read_text())['narration'][language]
                        self.assertEqual((receipt['voice'], receipt['model']), (voice['voice'], voice['model']))
                        self.assertEqual(receipt['speed'], 1.0)
                    self.assertEqual(receipt['sha256'], digest(path))
                    with wave.open(str(path)) as clip:
                        self.assertEqual((clip.getnchannels(), clip.getsampwidth(), clip.getframerate()), (1, 2, 22050))
                        self.assertGreater(clip.getnframes(), 0)
                        self.assertLess(clip.getnframes(), 22050 * 60)
                        self.assertAlmostEqual(receipt['duration'], clip.getnframes() / 22050)
                        self.assertTrue(any(memoryview(clip.readframes(clip.getnframes())).cast('h')))
        self.assertEqual(len(paths), 327)

    def test_all_327_spelling_recordings_exact_pcm(self):
        self.assertEqual(self.check_spelling(MINIMUM['words']), 327)
        paths = {voice_path(name, language, simple) for name in MINIMUM['words']
                 for language in LANGUAGES for simple in (True, False)}
        self.assertEqual(len(paths), 654)


if __name__ == '__main__':
    unittest.main()

"""Regression coverage for the illustrated multilingual learning expansion."""
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from book_catalog import (BOOKS, BOOK_GROUPS, LANGUAGES, LEARNING, NAMES,
                          PAGE_NAMES, TITLES, UNIQUE, WORDS, BuildUniqueBookCatalog,
                          narration, voice_path)
from book_speech import read_clip

OLD_IDS = ('jungle', 'garden', 'fruits', 'farm', 'kitchen', 'bathroom',
           'bedroom', 'living-room', 'nature', 'vegetables', 'family',
           'breakfast', 'lunch', 'dinner', 'body', 'clothing', 'seasons',
           'birds', 'toys', 'vehicles', 'bedtime', 'vacation', 'sports',
           'beach', 'weather', 'feelings')
NEW_IDS = ('tropical-fruits', 'gardening', 'school', 'water-animals', 'drinks')
ADDED_IDS = ('actions',)
REUSED = {'mango', 'banana', 'coconut', 'pineapple', 'flower', 'book',
          'backpack', 'duck', 'frog', 'water', 'milk'}
# Aggregate of the parent's pre-expansion source fingerprints, streamed below.
# Four covers follow their book's new first page and are checked below instead;
# with them this baseline is 3313 files, b4f61c9dc0cdf9e3ea37742b1552ff10df70a777a944392c9dedc6c36a5b58df.
ORIGINAL_DIGEST = 'b77f0935d88e63bc7d1fda900b48ad43bd5cfe298416754d02f82c4ed69c3565'
ORIGINAL_COUNT = 3309
NEW_COVERS = {'birds': 'owl', 'fruits': 'apricot', 'bedtime': 'toothpaste', 'nature': 'waterfall'}
NEW_LETTER = 'assets/jungle-book/sounds/es/letters/00fc'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def protected(name):
    return (name.startswith(('assets/jungle-book/', 'assets/abc/'))
            and name not in {f'assets/jungle-book/previews/{book}.jpg' for book in NEW_COVERS})


def fingerprint_rows(path):
    """Read the saved large fingerprint inventory one entry at a time."""
    name = None
    with path.open() as source:
        for line in source:
            if line.startswith('  "'):
                name = json.loads(line.strip().removesuffix(': {'))
            elif name and '"sha256":' in line:
                yield name, json.loads(line.split(':', 1)[1].strip().rstrip(','))
                name = None


class LearningBookTest(unittest.TestCase):
    def test_catalog_and_stable_slots(self):
        catalog = BuildUniqueBookCatalog()
        self.assertEqual(catalog['books'], BOOKS)
        self.assertEqual(tuple(c for c, _ in BOOKS), OLD_IDS + NEW_IDS + ADDED_IDS)
        self.assertEqual((len(NAMES), len(set(NAMES)), len(PAGE_NAMES)), (284, 284, 284))
        self.assertEqual(len(LEARNING['words']), 37)
        groups = dict(BOOK_GROUPS)
        self.assertEqual(groups['Family'], ('family', 'body', 'clothing', 'sports', 'feelings', 'actions'))
        self.assertTrue({'gardening', 'water-animals'} <= set(groups['Nature']))
        self.assertTrue({'tropical-fruits', 'drinks'} <= set(groups['Food']))
        self.assertIn('school', groups['Home'])
        self.assertEqual(set(c for _, members in BOOK_GROUPS for c in members), set(dict(BOOKS)))
        for category, extra in LEARNING['extra'].items():
            self.assertEqual(dict(BOOKS)[category][-len(extra):], tuple(extra))
        shared = {n for names in LEARNING['books'].values() for n in names} - set(LEARNING['words'])
        self.assertEqual(shared, REUSED)
        pages = (ROOT / 'games/book/book_pages.zi').read_text()
        voices = (ROOT / 'games/book/book_voice.zi').read_text()
        self.assertIn('CATEGORY_COUNT :: 32', pages)
        # The learning books once reused these words; each now has one home page.
        for name in REUSED:
            self.assertEqual(PAGE_NAMES.count(name), 1)
            self.assertEqual(pages.count(f'"assets/jungle-book/pages/{name}.jpg"'), PAGE_NAMES.count(name))
            for language in LANGUAGES:
                for simple in (True, False):
                    self.assertEqual(voices.count('"' + voice_path(name, language, simple) + '"'), PAGE_NAMES.count(name))
        # The shelf uses catalog-sized storage and group counts, with scrolling.
        shelf = (ROOT / 'games/book/jungle_book.zi').read_text()
        self.assertIn('visible: [CATEGORY_COUNT]s32', shelf)
        self.assertIn('group_counts[book_tab]', shelf)
        self.assertIn('content_height := rows *', shelf)

    def test_art_and_translations(self):
        manifest = json.loads((ROOT / 'art/generated/book-learning-expansion/prompts.json').read_text())
        prompts = json.loads((ROOT / 'tools/book_prompts.json').read_text())
        rows = json.loads((ROOT / 'locales/ui.json').read_text())
        self.assertEqual(set(manifest), set(LEARNING['words']))
        for name, labels in LEARNING['words'].items():
            self.assertEqual(WORDS[name], tuple(labels))
            self.assertEqual(len(labels), 3)
            scene = ROOT / f'assets/jungle-book/pages/{name}.jpg'
            self.assertEqual(digest(scene), manifest[name]['sha256'])
            self.assertEqual(prompts['pages'][name], manifest[name]['prompt'])
            self.assertFalse((ROOT / f'assets/jungle-book/items/{name}.png').exists())
            with Image.open(scene) as im:
                self.assertEqual((im.size, im.mode, im.format), ((1254, 1254), 'RGB', 'JPEG'))
        for category, names in LEARNING['books'].items():
            title = TITLES[category]
            self.assertEqual(rows[title[0]], title[1:])
            with Image.open(ROOT / f'assets/jungle-book/pages/{names[0]}.jpg') as scene:
                expected = io.BytesIO()
                scene.convert('RGB').resize((768, 768), Image.Resampling.LANCZOS).save(expected, format='JPEG', quality=86)
            self.assertEqual((ROOT / f'assets/jungle-book/previews/{category}.jpg').read_bytes(), expected.getvalue())
        self.assertEqual(dict(BOOKS)['water-animals'][0], 'goldfish')

    def test_new_spelling_exact_pcm(self):
        self.assertEqual(self.check_spelling(LEARNING['words']), 111)

    def test_unique_expansion_media(self):
        # Runs once the new art and speech exist; every original check also applies.
        prompts = json.loads((ROOT / 'tools/book_prompts.json').read_text())
        for name in UNIQUE['words']:
            scene = ROOT / f'assets/jungle-book/pages/{name}.jpg'
            self.assertIn(name, prompts['pages'])
            self.assertFalse((ROOT / f'assets/jungle-book/items/{name}.png').exists())
            with Image.open(scene) as im:
                self.assertEqual((im.size, im.mode, im.format), ((1254, 1254), 'RGB', 'JPEG'))
        for category, first in {**NEW_COVERS, 'actions': 'cooking'}.items():
            self.assertEqual(dict(BOOKS)[category][0], first)
            with Image.open(ROOT / f'assets/jungle-book/pages/{first}.jpg') as scene:
                expected = io.BytesIO()
                scene.convert('RGB').resize((768, 768), Image.Resampling.LANCZOS).save(expected, format='JPEG', quality=86)
            self.assertEqual((ROOT / f'assets/jungle-book/previews/{category}.jpg').read_bytes(), expected.getvalue())
        letter = json.loads((ROOT / (NEW_LETTER + '.speech.json')).read_text())
        self.assertEqual(letter['text'], 'u con diéresis.')
        self.assertEqual(self.check_spelling(UNIQUE['words']), 108)
        self.assertEqual(self.check_spelling(UNIQUE['voice_stems'], ('de',)), 1)

    def check_spelling(self, names, languages=LANGUAGES):
        import wave
        count = 0
        for language in languages:
            for name in names:
                word_path = ROOT / voice_path(name, language, True)
                word, word_hash = read_clip(word_path)
                receipt = json.loads(word_path.with_suffix('.speech.json').read_text())
                self.assertEqual(receipt['text'], narration(name, language, True))
                parts = [word, bytes(22050 // 2 * 2)]
                sources = [{'path': word_path.relative_to(ROOT).as_posix(), 'sha256': word_hash}]
                for letter in WORDS[name][LANGUAGES.index(language)].lower():
                    if letter.isspace():
                        parts.append(bytes(22050 // 3 * 2))
                        continue
                    path = ROOT / f'assets/jungle-book/sounds/{language}/letters/{ord(letter):04x}.wav'
                    data, sha = read_clip(path)
                    parts.extend((data, bytes(22050 // 4 * 2)))
                    sources.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': sha})
                parts.extend((bytes(22050 // 4 * 2), word))
                path = ROOT / voice_path(name, language)
                receipt = json.loads(path.with_suffix('.speech.json').read_text())
                self.assertEqual(receipt['sources'], sources)
                self.assertEqual(receipt['text'], narration(name, language))
                self.assertEqual(receipt['sha256'], digest(path))
                with wave.open(str(path)) as voice:
                    self.assertEqual((voice.getnchannels(), voice.getsampwidth(), voice.getframerate()), (1, 2, 22050))
                    self.assertEqual(voice.readframes(voice.getnframes()), b''.join(parts))
                    self.assertLess(voice.getnframes(), 22050 * 60)
                    self.assertAlmostEqual(receipt['duration'], voice.getnframes() / 22050)
                count += 1
        return count

    def test_original_assets_unchanged(self):
        # Exclude only explicitly new filenames. Any changed/missing old file or
        # unexpected extra asset changes this durable aggregate, even after commit.
        new_stems = (set(LEARNING['words']) | set(UNIQUE['words']) | set(NEW_IDS) | set(ADDED_IDS)
                     | {stem for stems in UNIQUE['voice_stems'].values() for stem in stems.values()})
        current = []
        for folder in ('assets/jungle-book', 'assets/abc'):
            for path in (ROOT / folder).rglob('*'):
                name = path.relative_to(ROOT).as_posix()
                if (path.is_file() and path.name.split('.')[0] not in new_stems
                        and protected(name) and name.split('.')[0] != NEW_LETTER):
                    current.append(name)
        aggregate = hashlib.sha256()
        for name in sorted(current):
            aggregate.update((name + '\0' + digest(ROOT / name) + '\n').encode())
        self.assertEqual(len(current), ORIGINAL_COUNT)
        self.assertEqual(aggregate.hexdigest(), ORIGINAL_DIGEST)
        baseline = ROOT / 'work/source-asset-fingerprints.json'
        if baseline.exists():
            for name, sha in fingerprint_rows(baseline):
                if protected(name):
                    self.assertEqual(digest(ROOT / name), sha, name)


if __name__ == '__main__':
    unittest.main()

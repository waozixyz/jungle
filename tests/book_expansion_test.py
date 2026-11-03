"""Regression coverage for the illustrated multilingual learning expansion."""
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from book_catalog import (BOOKS, BOOK_GROUPS, LANGUAGES, LEARNING, NAMES,
                          MINIMUM, PAGE_NAMES, TITLES, UNIQUE, WORDS, BuildUniqueBookCatalog,
                          narration, voice_path)
from book_speech import read_clip

OLD_IDS = ('jungle', 'garden', 'fruits', 'farm', 'kitchen', 'bathroom',
           'bedroom', 'living-room', 'nature', 'vegetables', 'family',
           'breakfast', 'lunch', 'dinner', 'body', 'clothing', 'seasons',
           'birds', 'toys', 'vehicles', 'bedtime', 'vacation', 'sports',
           'beach', 'weather', 'feelings')
NEW_IDS = ('tropical-fruits', 'gardening', 'school', 'water-animals', 'drinks')
ADDED_IDS = ('actions',)
LATEST_IDS = ('desert-animals', 'insects', 'people-at-work')
NATURE_IDS = ('reptiles', 'trees', 'plants', 'forest')
REUSED = {'mango', 'banana', 'coconut', 'pineapple', 'flower', 'book',
          'backpack', 'duck', 'frog', 'water', 'milk'}
# Aggregate of established sources, including the approved Bella English refresh.
# Four covers follow their book's new first page and are checked below instead.
# The Bella refresh retains all 3309 protected names; english_speech_test.py
# independently verifies every profile's literal speech and PCM composition.
ORIGINAL_DIGEST = '48168148f19b2a5a5b514c2d50aa200e876ce0318d3fe6b6355745773097b5ef'
ORIGINAL_COUNT = 3309
NEW_COVERS = {'birds': 'owl', 'fruits': 'apricot', 'bedtime': 'toothpaste', 'nature': 'waterfall'}
NEW_LETTER = 'assets/jungle-book/sounds/es/letters/00fc'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


MIGRATED = json.loads((ROOT / 'tools/canonical_webp.json').read_text())['files']
CANONICAL_NAMES = {entry['source']: name for name, entry in MIGRATED.items()}


def canonical_name(name):
    return CANONICAL_NAMES.get(name, name)


def preserved_digest(name):
    """Compare the unchanged baseline through explicitly requested art refreshes.

    Each replacement must match its reviewed current hash; its exact prior hash
    still participates in the original aggregate. Other assets retain the same
    baseline, and the refresh inventory cannot exempt unrelated artwork.
    """
    name = canonical_name(name)
    manifest = ROOT / 'tools/book_art_refresh.json'
    refresh = json.loads(manifest.read_text())['files'] if manifest.exists() else {}
    wild = set(dict(BOOKS)['jungle'])
    farm_scenes = {'rabbit', 'cat', 'mouse', 'pig', 'cow', 'dog', 'horse',
                   'sheep', 'duck', 'hen', 'goat', 'donkey', 'goose', 'turkey',
                   'chick', 'rooster', 'llama', 'alpaca', 'calf', 'lamb'}
    farm_counting = {'rabbit', 'cat', 'pig', 'cow', 'dog', 'sheep', 'duck', 'hen'}
    scenes = wild | {'firefighter', 'doctor', 'teacher', 'farmer', 'builder', 'baker',
                     'drawing', 'brushing_teeth'}
    allowed = ({f'assets/jungle-book/pages/{name}.webp' for name in scenes | farm_scenes}
               | {f'assets/jungle-book/items/{name}.png' for name in wild}
               | {f'assets/jungle-book/items/{name}.png' for name in farm_scenes}
               | {f'assets/jungle-book/counting/{name}.png' for name in wild}
               | {f'assets/jungle-book/counting/{name}.png' for name in farm_counting}
               | {'assets/jungle-book/previews/jungle.webp',
                  'assets/jungle-book/previews/people-at-work.webp',
                  'assets/jungle-book/previews/farm.webp', 'assets/jungle/book.png'})
    minimum_pages = {f'assets/jungle-book/pages/{name}.webp' for name in MINIMUM['words']}
    assert set(refresh) <= allowed | minimum_pages, 'Unrequested original asset in art refresh'
    assert {path for path, entry in refresh.items() if entry['previous_sha256'] is None} == minimum_pages, \
        'Only the exact 109 new scenes may have no historical fingerprint'
    actual = digest(ROOT / name)
    if name in refresh:
        entry = refresh[name]
        assert actual == entry['sha256'], f'Reviewed artwork changed: {name}'
        return entry['previous_sha256']
    if name in MIGRATED:
        entry = MIGRATED[name]
        assert actual == entry['sha256'], f'Migrated artwork changed: {name}'
        return entry['original_sha256']
    return actual


def protected(name):
    name = canonical_name(name)
    return (name.startswith(('assets/jungle-book/', 'assets/abc/'))
            and name not in ({f'assets/jungle-book/previews/{book}.webp' for book in NEW_COVERS}
                             | {f'assets/jungle-book/previews/{book}.webp' for book in LATEST_IDS}))


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
        self.assertEqual(tuple(c for c, _ in BOOKS), OLD_IDS + NEW_IDS + ADDED_IDS + LATEST_IDS + NATURE_IDS + ('pets', 'on-the-farm'))
        self.assertEqual((len(NAMES), len(set(NAMES)), len(PAGE_NAMES)), (435, 435, 435))
        self.assertTrue(all(len(names) >= 10 for _, names in BOOKS))
        self.assertEqual(len(MINIMUM['words']), 109)
        self.assertEqual(NAMES[326:], tuple(MINIMUM['words']))
        self.assertEqual(hashlib.sha256('\n'.join(NAMES[:326]).encode()).hexdigest(),
                         '980519bf63805b0f5b63724f77eba1b52a90fa440cdfc8dbaccded7c540d578c')
        self.assertEqual(len(LEARNING['words']), 37)
        groups = dict(BOOK_GROUPS)
        self.assertEqual(groups['Family'], ('family', 'body', 'clothing', 'sports', 'feelings', 'actions', 'people-at-work'))
        self.assertIn('gardening', groups['Nature'])
        self.assertIn('water-animals', groups['Animals'])
        self.assertIn('desert-animals', groups['Animals'])
        self.assertIn('insects', groups['Nature'])
        self.assertFalse(set(groups['Nature']) & set(groups['Animals']))
        self.assertTrue({'tropical-fruits', 'drinks'} <= set(groups['Food']))
        self.assertIn('school', groups['Home'])
        self.assertEqual(set(c for _, members in BOOK_GROUPS for c in members), set(dict(BOOKS)))
        for category, extra in LEARNING['extra'].items():
            historical = tuple(name for name in dict(BOOKS)[category] if name not in MINIMUM['words'])
            self.assertEqual(historical[-len(extra):], tuple(extra))
        shared = {n for names in LEARNING['books'].values() for n in names} - set(LEARNING['words'])
        self.assertEqual(shared, REUSED)
        pages = (ROOT / 'games/book/book_pages.zi').read_text()
        voices = (ROOT / 'games/book/book_voice.zi').read_text()
        self.assertIn('CATEGORY_COUNT :: 41', pages)
        # The learning books once reused these words; each now has one home page.
        for name in REUSED:
            self.assertEqual(PAGE_NAMES.count(name), 1)
            self.assertEqual(pages.count(f'"assets/jungle-book/pages/{name}.webp"'), PAGE_NAMES.count(name))
            for language in LANGUAGES:
                for simple in (True, False):
                    self.assertEqual(voices.count('"' + voice_path(name, language, simple) + '"'), PAGE_NAMES.count(name))
        # The shelf uses catalog-sized storage and group counts, with scrolling.
        shelf = (ROOT / 'games/book/jungle_book.zi').read_text()
        self.assertIn('visible: [CATEGORY_COUNT]s32', shelf)
        self.assertIn('group_counts[book_tab]', shelf)
        self.assertIn('content_height := rows *', shelf)

    def test_art_and_translations(self):
        manifest = json.loads((ROOT / 'tools/art_provenance/book-learning-expansion/prompts.json').read_text())
        prompts = json.loads((ROOT / 'tools/book_prompts.json').read_text())
        rows = json.loads((ROOT / 'locales/ui.json').read_text())
        self.assertEqual(set(manifest), set(LEARNING['words']))
        for name, labels in LEARNING['words'].items():
            self.assertEqual(WORDS[name], tuple(labels))
            self.assertEqual(len(labels), 3)
            scene = ROOT / f'assets/jungle-book/pages/{name}.webp'
            self.assertEqual(digest(scene), manifest[name]['canonical_sha256'])
            self.assertEqual(prompts['pages'][name], manifest[name]['prompt'])
            self.assertFalse((ROOT / f'assets/jungle-book/items/{name}.png').exists())
            with Image.open(scene) as im:
                self.assertEqual((im.size, im.mode, im.format), ((1254, 1254), 'RGB', 'WEBP'))
        for category, names in LEARNING['books'].items():
            title = TITLES[category]
            self.assertEqual(rows[title[0]], title[1:])
            with Image.open(ROOT / f'assets/jungle-book/pages/{names[0]}.webp') as scene, Image.open(
                    ROOT / f'assets/jungle-book/previews/{category}.webp') as cover:
                expected = scene.convert('RGB').resize((768, 768), Image.Resampling.LANCZOS)
                self.assertLess(max(ImageStat.Stat(ImageChops.difference(expected, cover.convert('RGB'))).mean), 8)
        self.assertEqual(dict(BOOKS)['water-animals'][0], 'goldfish')

    def test_new_spelling_exact_pcm(self):
        self.assertEqual(self.check_spelling(LEARNING['words']), 111)

    def test_unique_expansion_media(self):
        # Runs once the new art and speech exist; every original check also applies.
        prompts = json.loads((ROOT / 'tools/book_prompts.json').read_text())
        for name in UNIQUE['words']:
            scene = ROOT / f'assets/jungle-book/pages/{name}.webp'
            self.assertIn(name, prompts['pages'])
            self.assertFalse((ROOT / f'assets/jungle-book/items/{name}.png').exists())
            with Image.open(scene) as im:
                self.assertEqual((im.size, im.mode, im.format), ((1254, 1254), 'RGB', 'WEBP'))
        for category, first in {**NEW_COVERS, 'actions': 'cooking', 'desert-animals': 'camel',
                                'insects': 'beetle', 'people-at-work': 'firefighter'}.items():
            self.assertEqual(dict(BOOKS)[category][0], first)
            with Image.open(ROOT / f'assets/jungle-book/pages/{first}.webp') as scene, Image.open(
                    ROOT / f'assets/jungle-book/previews/{category}.webp') as cover:
                expected = scene.convert('RGB').resize((768, 768), Image.Resampling.LANCZOS)
                self.assertLess(max(ImageStat.Stat(ImageChops.difference(expected, cover.convert('RGB'))).mean), 8)
        letter = json.loads((ROOT / (NEW_LETTER + '.speech.json')).read_text())
        self.assertEqual(letter['text'], 'u con diéresis.')
        self.assertEqual(self.check_spelling(UNIQUE['words']), 234)
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
        new_stems = (set(LEARNING['words']) | set(UNIQUE['words']) | set(NEW_IDS) | set(ADDED_IDS) | set(LATEST_IDS) | set(NATURE_IDS)
                     | set(MINIMUM['words']) | {'pets', 'on-the-farm'}
                     | {stem for stems in UNIQUE['voice_stems'].values() for stem in stems.values()})
        # The separately validated story adds these exact files; it cannot
        # exempt or change any preexisting word-book source in the aggregate.
        story = json.loads((ROOT / 'tools/sweet_porridge.json').read_text())
        story_assets = {f"assets/jungle-book/pages/{row['asset']}.webp" for row in story['pages']}
        story_assets |= {f"assets/jungle-book/story-sounds/{language}/{row['asset']}.{suffix}"
                         for row in story['pages'] for language in LANGUAGES
                         for suffix in ('wav', 'speech.json')}
        story_assets |= {f"assets/jungle-book/portraits/{row['portrait_asset']}.webp" for row in story['pages']}
        story_assets.add('assets/jungle-book/previews/sweet-porridge.webp')
        # The new collection feedback sound is not historical book artwork.
        # Exempt its exact path, preserving the original count and digest.
        added_sounds = {'assets/jungle-book/collect.wav'}
        current = []
        for folder in ('assets/jungle-book', 'assets/abc'):
            for path in (ROOT / folder).rglob('*'):
                name = path.relative_to(ROOT).as_posix()
                if (path.is_file() and path.name.split('.')[0] not in new_stems
                        and protected(name) and name.split('.')[0] != NEW_LETTER
                        and name not in story_assets | added_sounds):
                    current.append(name)
        aggregate = hashlib.sha256()
        for name in sorted(current):
            aggregate.update((MIGRATED.get(name, {}).get('source', name) + '\0' + preserved_digest(name) + '\n').encode())
        self.assertEqual(len(current), ORIGINAL_COUNT)
        self.assertEqual(aggregate.hexdigest(), ORIGINAL_DIGEST)
        baseline = ROOT / 'work/source-asset-fingerprints.json'
        if baseline.exists():
            for name, sha in fingerprint_rows(baseline):
                # The historical inventory still protects original artwork;
                # narration now has the refreshed tracked aggregate above.
                if protected(name) and not name.endswith(('.wav', '.speech.json')):
                    self.assertEqual(preserved_digest(name), sha, name)


if __name__ == '__main__':
    unittest.main()

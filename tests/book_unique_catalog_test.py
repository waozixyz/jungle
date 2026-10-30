#!/usr/bin/env python3
"""Every Picture Book subject appears once, in all languages and in a Play All pass."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import book_catalog
from book_catalog import (BOOKS, BOOK_GROUPS, LANGUAGES, LEGACY_IDS, LEGACY_NAMES, NAMES,
                          PAGE_NAMES, PENDING_MEDIA, TITLES, UNIQUE, WORDS,
                          ApplyUniqueExpansion, BuildUniqueBookCatalog, NormalizedLabel,
                          ValidateBookCatalog, narration, voice_path)

# Fingerprints of the word and page order before this catalog changed.
LEGACY_NAMES_SHA256 = '3c1a7f68ad746f230fa0907cda8e24d5614df26e68484e51b392eb92fdd2cefc'
LEGACY_PAGES = 275
REPLACED = {
    'birds': {'parrot': 'owl', 'toucan': 'kingfisher', 'duck': 'penguin', 'hen': 'eagle',
              'goose': 'swan', 'rooster': 'flamingo'},
    'water-animals': {'duck': 'stingray', 'frog': 'seal'},
    'gardening': {'flower': 'hose'},
    'fruits': {'banana': 'apricot', 'mango': 'plum', 'coconut': 'raspberry', 'pineapple': 'blackberry'},
    'bedroom': {'teddy': 'dresser', 'book': 'laundry_basket'},
    'bedtime': {'bed': 'toothpaste', 'pillow': 'slippers', 'blanket': 'bathrobe', 'teddy': 'pajamas',
                'book': 'sleeping', 'moon': 'stars'},
    'nature': {'sun': 'waterfall', 'cloud': 'forest', 'rain': 'rock'},
    'breakfast': {'milk': 'pancakes'},
    'lunch': {'water': 'hummus'},
    'vacation': {'backpack': 'binoculars'},
}
HOMES = {'jungle': ('parrot', 'toucan'), 'farm': ('duck', 'hen', 'goose', 'rooster'),
         'garden': ('frog', 'flower'),
         'tropical-fruits': ('banana', 'mango', 'coconut', 'pineapple'), 'toys': ('teddy',),
         'school': ('book', 'backpack'), 'bedroom': ('bed', 'pillow', 'blanket'), 'nature': ('moon',),
         'weather': ('sun', 'cloud', 'rain'), 'drinks': ('milk', 'water')}
ACTIONS = ('cooking', 'cleaning', 'reading', 'drawing', 'singing', 'washing_hands', 'brushing_teeth',
           'watering_plants')
LABELS = """
owl Owl|Eule|Búho
kingfisher Kingfisher|Eisvogel|Martín pescador
penguin Penguin|Pinguin|Pingüino
eagle Eagle|Adler|Águila
swan Swan|Schwan|Cisne
flamingo Flamingo|Flamingo|Flamenco
stingray Stingray|Rochen|Raya
seal Seal|Robbe|Foca
hose Hose|Gartenschlauch|Manguera
apricot Apricot|Aprikose|Albaricoque
plum Plum|Pflaume|Ciruela
raspberry Raspberry|Himbeere|Frambuesa
blackberry Blackberry|Brombeere|Mora
dresser Dresser|Kommode|Cómoda
laundry_basket Laundry basket|Wäschekorb|Cesto de ropa
toothpaste Toothpaste|Zahnpasta|Pasta de dientes
slippers Slippers|Hausschuhe|Pantuflas
bathrobe Bathrobe|Bademantel|Albornoz
pajamas Pajamas|Schlafanzug|Pijama
sleeping Sleeping|Schlafen|Dormir
stars Stars|Sterne|Estrellas
waterfall Waterfall|Wasserfall|Cascada
forest Forest|Wald|Bosque
rock Rock|Stein|Piedra
pancakes Pancakes|Pfannkuchen|Tortitas
hummus Hummus|Hummus|Hummus
binoculars Binoculars|Fernglas|Prismáticos
cooking Cooking|Kochen|Cocinar
cleaning Cleaning|Putzen|Limpiar
reading Reading|Lesen|Leer
drawing Drawing|Malen|Dibujar
singing Singing|Singen|Cantar
washing_hands Washing hands|Hände waschen|Lavarse las manos
brushing_teeth Brushing teeth|Zähne putzen|Cepillarse los dientes
watering_plants Watering plants|Pflanzen gießen|Regar las plantas
badminton Badminton|Badminton|Bádminton
"""


def expected_labels():
    return {row.split(' ', 1)[0]: tuple(row.split(' ', 1)[1].split('|')) for row in LABELS.strip().splitlines()}


def fixture():
    """A small valid catalog, changed one fact at a time by the rejection tests."""
    return dict(
        books=(('one', ('cat', 'dog')), ('two', ('sun', 'moon'))),
        groups=(('Group', ('one', 'two')),),
        words={'cat': ('Cat', 'Katze', 'Gato'), 'dog': ('Dog', 'Hund', 'Perro'),
               'sun': ('Sun', 'Sonne', 'Sol'), 'moon': ('Moon', 'Mond', 'Luna')},
        titles={'one': ('One', 'Eins', 'Uno'), 'two': ('Two', 'Zwei', 'Dos')},
        names=('cat', 'dog', 'sun', 'moon'),
        homes={'cat': 'one'}, legacy_ids=('one',), legacy_names=('cat', 'dog'),
    )


def table(source, name):
    """Read a generated string table back in runtime index order."""
    values = []
    for start, body in re.findall(rf'^{name}_(\d+): \[\d+\]string = \.\[\n(.*?)^\];', source, re.M | re.S):
        values.extend(json.loads(line.strip().rstrip(',')) for line in body.splitlines())
    return values


class CatalogTest(unittest.TestCase):
    def test_exact_shape_and_uniqueness(self):
        catalog = BuildUniqueBookCatalog()
        self.assertEqual(catalog['books'], BOOKS)
        self.assertEqual((len(BOOKS), len(PAGE_NAMES), len(set(PAGE_NAMES)), len(NAMES)), (32, 284, 284, 284))
        self.assertEqual(set(PAGE_NAMES), set(NAMES))
        self.assertEqual(set(NAMES), set(WORDS))
        for at, language in enumerate(LANGUAGES):
            labels = [NormalizedLabel(WORDS[name][at]) for name in NAMES]
            self.assertEqual(len(labels), len(set(labels)), language)

    def test_saved_ids_keep_their_positions(self):
        self.assertEqual(hashlib.sha256('\n'.join(LEGACY_NAMES).encode()).hexdigest(), LEGACY_NAMES_SHA256)
        self.assertEqual(NAMES[:248], LEGACY_NAMES)
        self.assertEqual(NAMES[248:], tuple(expected_labels()))
        self.assertEqual(tuple(category for category, _ in BOOKS)[:31], LEGACY_IDS)
        self.assertEqual((len(LEGACY_IDS), LEGACY_IDS[30], BOOKS[31][0]), (31, 'drinks', 'actions'))

    def test_exact_replacements_and_additions(self):
        self.assertEqual(UNIQUE['replacements'], REPLACED)
        self.assertEqual(sum(map(len, REPLACED.values())), 27)
        books = dict(BOOKS)
        self.assertEqual(books['actions'], ACTIONS)
        self.assertEqual(books['sports'][-1], 'badminton')
        self.assertEqual(dict(BOOK_GROUPS)['Family'][-1], 'actions')
        self.assertEqual(TITLES['actions'], ['Actions', 'Tätigkeiten', 'Acciones'])
        for category, members in book_catalog._legacy_books:
            swaps = REPLACED.get(category, {})
            kept = tuple(swaps.get(name, name) for name in members)
            self.assertEqual(books[category][:len(kept)], kept, category)
        for home, members in HOMES.items():
            for name in members:
                self.assertIn(name, books[home])
                self.assertEqual(PAGE_NAMES.count(name), 1, name)

    def test_exact_new_labels(self):
        for name, labels in expected_labels().items():
            self.assertEqual(WORDS[name], labels)

    def test_one_german_label_per_subject(self):
        # The two old German "Salat" pages stay apart without touching a recording.
        self.assertEqual(WORDS['salad'][1], 'Salat')
        self.assertEqual(WORDS['lettuce'], ('Lettuce', 'Kopfsalat', 'Lechuga'))
        self.assertEqual(voice_path('lettuce', 'de', True), 'assets/jungle-book/sounds/de/simple/lettuce_kopfsalat.wav')
        self.assertEqual(voice_path('lettuce', 'es', True), 'assets/jungle-book/sounds/es/simple/lettuce.wav')
        self.assertEqual(voice_path('lettuce', 'en'), 'assets/jungle-book/sounds/lettuce.wav')
        old = json.loads((ROOT / 'assets/jungle-book/sounds/de/simple/lettuce.speech.json').read_text())
        self.assertEqual(old['text'], 'Salat.')

    def test_every_word_has_literal_narration(self):
        for name in NAMES:
            for language in LANGUAGES:
                self.assertTrue(narration(name, language).startswith(WORDS[name][LANGUAGES.index(language)]))
        self.assertIn('. u con diéresis. ', narration('penguin', 'es'))
        self.assertEqual(narration('penguin', 'es', True), 'Pingüino.')

    def test_spanish_u_diaeresis_is_not_borrowed(self):
        german = ROOT / 'assets/jungle-book/sounds/de/letters/00fc.wav'
        spanish = ROOT / 'assets/jungle-book/sounds/es/letters/00fc.wav'
        self.assertTrue(german.exists())
        if spanish.exists():  # Generated separately; never a copy of the German letter.
            self.assertNotEqual(spanish.read_bytes(), german.read_bytes())
            receipt = json.loads(spanish.with_suffix('.speech.json').read_text())
            self.assertEqual(receipt['text'], 'u con diéresis.')
        originals = [path for path in (ROOT / 'assets/jungle-book/sounds').glob('*/letters/*.wav') if path != spanish]
        self.assertEqual(len(originals), 88)

    def test_pending_media_is_exact(self):
        self.assertEqual(set(PENDING_MEDIA), set(expected_labels()) | {'lettuce'})


class InvalidCatalogTest(unittest.TestCase):
    def rejects(self, change, message):
        catalog = copy.deepcopy(fixture())
        ValidateBookCatalog(**catalog)
        change(catalog)
        with self.assertRaisesRegex(ValueError, message):
            ValidateBookCatalog(**catalog)

    def test_subject_in_two_books(self):
        def change(catalog):
            catalog['books'] = (('one', ('cat', 'dog')), ('two', ('sun', 'cat')))
            catalog['words'].pop('moon')
            catalog['names'] = ('cat', 'dog', 'sun')
        self.rejects(change, 'cat appears in one and two')

    def test_subject_twice_in_one_book(self):
        def change(catalog):
            catalog['books'] = (('one', ('cat', 'dog', 'cat')), ('two', ('sun', 'moon')))
        self.rejects(change, 'cat appears in one and one')

    def test_label_collisions_ignore_case_spacing_and_form(self):
        for language, labels, message in (
                (0, ('CAT', 'Hund', 'Perro'), 'dog repeats the en label'),
                (1, ('Dog', 'KATZE', 'Perro'), 'dog repeats the de label'),
                (2, ('Dog', 'Hund', 'gato'), 'dog repeats the es label')):
            def change(catalog, labels=labels):
                catalog['words']['dog'] = labels
            self.rejects(change, message)
        def spaced(catalog):
            catalog['words']['cat'] = ('Sea lion', 'Katze', 'Gato')
            catalog['words']['dog'] = ('SEA  LION', 'Hund', 'Perro')
        self.rejects(spaced, 'dog repeats the en label')
        def composed(catalog):
            catalog['words']['cat'] = ('Cat', 'Katze', 'Plátano')
            catalog['words']['dog'] = ('Dog', 'Hund', 'Plátano')
        self.rejects(composed, 'dog repeats the es label')

    def test_title_collision(self):
        self.rejects(lambda catalog: catalog['titles'].update(two=('ONE', 'Zwei', 'Dos')), 'two repeats the en label')

    def test_missing_or_blank_label(self):
        self.rejects(lambda catalog: catalog['words'].update(cat=('Cat', 'Katze')), 'cat needs one clean label')
        self.rejects(lambda catalog: catalog['words'].update(cat=('Cat', '', 'Gato')), 'cat needs one clean label')

    def test_untranslated_or_unreachable_subject(self):
        self.rejects(lambda catalog: catalog['words'].pop('moon'), 'pages and translated words differ')
        self.rejects(lambda catalog: catalog['words'].update(owl=('Owl', 'Eule', 'Búho')), 'pages and translated words differ')

    def test_routes(self):
        self.rejects(lambda catalog: catalog.update(groups=(('Group', ('one',)),)), 'exactly one shelf group')
        self.rejects(lambda catalog: catalog.update(groups=(('A', ('one', 'two')), ('B', ('two',)))), 'exactly one shelf group')

    def test_saved_positions(self):
        self.rejects(lambda catalog: catalog.update(books=tuple(reversed(catalog['books']))), 'saved book slot moved')
        self.rejects(lambda catalog: catalog.update(names=('dog', 'cat', 'sun', 'moon')), 'saved word ID moved')
        self.rejects(lambda catalog: catalog.update(names=('cat', 'dog', 'sun')), 'list every page once')

    def test_wrong_home(self):
        self.rejects(lambda catalog: catalog.update(homes={'cat': 'two'}), 'cat belongs in two')

    def test_unsafe_asset_name(self):
        def change(catalog):
            catalog['books'] = (('one', ('cat', '../dog')), ('two', ('sun', 'moon')))
            catalog['words']['../dog'] = catalog['words'].pop('dog')
            catalog['names'] = ('cat', '../dog', 'sun', 'moon')
            catalog['legacy_names'] = ('cat',)
        self.rejects(change, 'not a safe asset name')

    def test_missing_replacement_source(self):
        unique = dict(replacements={'one': {'owl': 'hawk'}}, append={}, books={})
        with self.assertRaisesRegex(ValueError, 'one has no page owl'):
            ApplyUniqueExpansion((('one', ('cat',)),), unique)


class GeneratedRouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = (ROOT / 'games/book/book_pages.zi').read_text()
        cls.voices = (ROOT / 'games/book/book_voice.zi').read_text()

    def test_page_tables_follow_the_catalog(self):
        self.assertIn('CATEGORY_COUNT :: 32\n', self.pages)
        ids = json.loads('[' + re.search(r'^category_ids:.*?\.\[(.*)\];', self.pages, re.M)[1] + ']')
        self.assertEqual(ids, [category for category, _ in BOOKS])
        counts = re.search(r'^category_counts:.*?\.\{(.*)\};', self.pages, re.M)[1]
        self.assertEqual([int(count) for count in counts.split(',')], [len(names) for _, names in BOOKS])
        order = re.search(r'^shelf_order:.*?\.\[(.*)\];', self.pages, re.M)[1]
        self.assertEqual(sorted(int(at) for at in order.split(',')), list(range(32)))
        self.assertEqual(table(self.pages, 'page_paths'), [f'assets/jungle-book/pages/{name}.jpg' for name in PAGE_NAMES])
        for at, language in enumerate(LANGUAGES):
            self.assertEqual(table(self.pages, f'page_names_{language}'), [WORDS[name][at] for name in PAGE_NAMES])

    def test_voice_tables_follow_the_catalog(self):
        for language in LANGUAGES:
            for simple, mode in ((False, 'spelling'), (True, 'simple')):
                paths = table(self.voices, f'voice_paths_{language}_{mode}')
                self.assertEqual(paths, [voice_path(name, language, simple) for name in PAGE_NAMES])
                self.assertEqual(len(paths), len(set(paths)))

    def test_shelf_title_is_translated(self):
        rows = json.loads((ROOT / 'locales/ui.json').read_text())
        self.assertEqual(rows['Actions'], ['Tätigkeiten', 'Acciones'])
        language = (ROOT / 'retro/language.zi').read_text()
        for label in TITLES['actions']:
            self.assertIn(json.dumps(label, ensure_ascii=False), language)


class PlayAllModelTest(unittest.TestCase):
    def test_compiled_preferences_model(self):
        # Runs the real generated tables through the real NextBookCategory.
        library = ROOT / 'build/ziran/libziran.a'
        self.assertTrue(library.exists(), 'run the Ziran runtime build first')
        lock = [] if (ROOT / 'ziran.local.toml').exists() else ['--locked']
        locate = lambda package: subprocess.run(['ziran', 'pkg', 'path', package, *lock], cwd=ROOT, check=True,
                                                capture_output=True, text=True).stdout.strip()
        toolchain = Path(locate('ziran'))
        std = toolchain / 'std'
        (ROOT / 'work').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='book-unique-', dir=ROOT / 'work') as directory:
            sources = Path(directory) / 'c'
            program = Path(directory) / 'book_preferences'
            subprocess.run([toolchain / 'build/bin/ziran', 'build', '--target=c', '--root', 'tests',
                            '--module-path', f'std={std}', '--module-path', std,
                            '--entry', 'book_preferences_test:main', '-o', sources,
                            'tests/book_preferences_test.zi'], cwd=ROOT, check=True, capture_output=True, text=True)
            folders = [flag for folder in [sources, *(path for path in sources.rglob('*') if path.is_dir())]
                       for flag in ('-iquote', folder)]
            subprocess.run([*shlex.split(os.environ.get('CC', 'cc')), '-std=c11', '-O1', f'-I{toolchain / "include"}', *folders,
                            *sources.rglob('*.c'), library, '-lm', '-lpthread', '-o', program],
                           check=True, capture_output=True, text=True)
            result = subprocess.run([program], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, f'book_preferences_test failed at check {result.returncode}')


if __name__ == '__main__':
    unittest.main()

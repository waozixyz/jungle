"""Complete word, category and literal letter-name inventory for all book languages."""
LANGUAGES = ("en", "de", "es")
BOOKS = (
    ("jungle", ("tiger", "elephant", "giraffe", "monkey", "panda", "lion", "zebra", "crocodile", "parrot", "toucan")),
    ("garden", ("frog", "butterfly", "ladybug", "snail", "flower")),
    ("fruits", ("banana", "mango", "coconut", "apple", "pear", "orange", "strawberry", "grapes", "pineapple", "watermelon", "lemon", "peach", "cherry")),
    ("farm", ("rabbit", "cat", "mouse", "pig", "cow", "dog", "horse", "sheep", "duck", "hen", "goat", "donkey", "goose", "turkey")),
)
WORDS = {
    "tiger": ("Tiger", "Tiger", "Tigre"),
    "elephant": ("Elephant", "Elefant", "Elefante"),
    "giraffe": ("Giraffe", "Giraffe", "Jirafa"),
    "monkey": ("Monkey", "Affe", "Mono"),
    "panda": ("Panda", "Panda", "Panda"),
    "lion": ("Lion", "Löwe", "León"),
    "zebra": ("Zebra", "Zebra", "Cebra"),
    "crocodile": ("Crocodile", "Krokodil", "Cocodrilo"),
    "parrot": ("Parrot", "Papagei", "Loro"),
    "toucan": ("Toucan", "Tukan", "Tucán"),
    "frog": ("Frog", "Frosch", "Rana"),
    "butterfly": ("Butterfly", "Schmetterling", "Mariposa"),
    "ladybug": ("Ladybug", "Marienkäfer", "Mariquita"),
    "snail": ("Snail", "Schnecke", "Caracol"),
    "flower": ("Flower", "Blume", "Flor"),
    "banana": ("Banana", "Banane", "Plátano"),
    "mango": ("Mango", "Mango", "Mango"),
    "coconut": ("Coconut", "Kokosnuss", "Coco"),
    "apple": ("Apple", "Apfel", "Manzana"),
    "pear": ("Pear", "Birne", "Pera"),
    "orange": ("Orange", "Orange", "Naranja"),
    "strawberry": ("Strawberry", "Erdbeere", "Fresa"),
    "grapes": ("Grapes", "Trauben", "Uvas"),
    "pineapple": ("Pineapple", "Ananas", "Piña"),
    "watermelon": ("Watermelon", "Wassermelone", "Sandía"),
    "lemon": ("Lemon", "Zitrone", "Limón"),
    "peach": ("Peach", "Pfirsich", "Melocotón"),
    "cherry": ("Cherry", "Kirsche", "Cereza"),
    "rabbit": ("Rabbit", "Kaninchen", "Conejo"),
    "cat": ("Cat", "Katze", "Gato"),
    "mouse": ("Mouse", "Maus", "Ratón"),
    "pig": ("Pig", "Schwein", "Cerdo"),
    "cow": ("Cow", "Kuh", "Vaca"),
    "dog": ("Dog", "Hund", "Perro"),
    "horse": ("Horse", "Pferd", "Caballo"),
    "sheep": ("Sheep", "Schaf", "Oveja"),
    "duck": ("Duck", "Ente", "Pato"),
    "hen": ("Hen", "Huhn", "Gallina"),
    "goat": ("Goat", "Ziege", "Cabra"),
    "donkey": ("Donkey", "Esel", "Burro"),
    "goose": ("Goose", "Gans", "Ganso"),
    "turkey": ("Turkey", "Truthahn", "Pavo"),
}
ADDED = ("apple", "pear", "orange", "strawberry", "grapes", "pineapple", "watermelon", "lemon", "peach", "cherry", "duck", "hen", "goat", "donkey", "goose", "turkey")
# Keep new illustrations and all three translations in one reviewed manifest.
import json
from pathlib import Path
import re
import unicodedata
EXPANSION = json.loads(Path(__file__).with_name("book_expansion.json").read_text())
OUTDOOR = json.loads(Path(__file__).with_name("outdoor_books.json").read_text())
EXPANSION["extra"].update(OUTDOOR["books"])
EXPANSION["words"].update(OUTDOOR["words"])
EXPANSION["titles"].update(OUTDOOR["titles"])
LEARNING = json.loads(Path(__file__).with_name("book_learning_expansion.json").read_text())
# Extend existing categories in place; append books to preserve saved category slots.
for category, names in LEARNING["extra"].items():
    EXPANSION["extra"][category].extend(names)
EXPANSION["extra"].update(LEARNING["books"])
EXPANSION["words"].update(LEARNING["words"])
EXPANSION["titles"].update(LEARNING["titles"])
_original = dict(BOOKS)
_legacy_books = tuple((category, _original.get(category, ()) + tuple(extra)) for category, extra in EXPANSION["extra"].items())
# Saved word IDs keep their old order; subjects added later always go at the end.
LEGACY_IDS = tuple(category for category, _ in _legacy_books)
LEGACY_NAMES = tuple(dict.fromkeys(name for _, names in _legacy_books for name in names))
UNIQUE = json.loads(Path(__file__).with_name("book_unique_expansion.json").read_text())


def ApplyUniqueExpansion(books, unique):
    """Give duplicated pages new subjects in place, then append the new pages."""
    changed = []
    for category, names in books:
        names = list(names)
        for old, new in unique["replacements"].get(category, {}).items():
            if old not in names:
                raise ValueError(f"{category} has no page {old} to replace")
            names[names.index(old)] = new
        changed.append((category, tuple(names) + tuple(unique["append"].get(category, ()))))
    return tuple(changed) + tuple((category, tuple(names)) for category, names in unique["books"].items())


BOOKS = ApplyUniqueExpansion(_legacy_books, UNIQUE)
WORDS.update((name, tuple(words)) for name, words in EXPANSION["words"].items())
WORDS.update((name, tuple(words)) for name, words in UNIQUE["words"].items())
for _name, _changes in UNIQUE["label_changes"].items():
    _labels = list(WORDS[_name])
    for _language, _label in _changes.items():
        _labels[LANGUAGES.index(_language)] = _label
    WORDS[_name] = tuple(_labels)
# Narration tools read these: every book's final pages and every final word.
EXPANSION["extra"] = {category: list(names) for category, names in BOOKS}
EXPANSION["words"].update((name, WORDS[name]) for name in (*UNIQUE["words"], *UNIQUE["label_changes"]))
EXPANSION["titles"].update(UNIQUE["titles"])
TITLES = EXPANSION["titles"]
PAGE_NAMES = tuple(name for _, names in BOOKS for name in names)
NAMES = LEGACY_NAMES + tuple(UNIQUE["words"])
# A changed label records its speech under a new name; old recordings stay intact.
PENDING_MEDIA = tuple(UNIQUE["words"]) + tuple(UNIQUE["voice_stems"])
BOOK_GROUPS = (
    ("Nature", ("jungle", "garden", "farm", "nature", "seasons", "birds", "weather", "beach", "gardening", "water-animals")),
    ("Food", ("fruits", "vegetables", "breakfast", "lunch", "dinner", "tropical-fruits", "drinks")),
    ("Home", ("kitchen", "bathroom", "bedroom", "living-room", "toys", "vehicles", "bedtime", "vacation", "school")),
    ("Family", ("family", "body", "clothing", "sports", "feelings", "actions")),
)


def NormalizedLabel(label):
    """Labels that look or sound the same to a reader compare as equal."""
    return " ".join(unicodedata.normalize("NFKC", label).casefold().split())


def _require_unique_labels(kind, rows):
    for at, language in enumerate(LANGUAGES):
        seen = {}
        for key, labels in rows.items():
            label = NormalizedLabel(labels[at])
            if label in seen:
                raise ValueError(f"{kind} {key} repeats the {language} label of {seen[label]}: {labels[at]}")
            seen[label] = key


def ValidateBookCatalog(books, groups, words, titles, names, homes=(), legacy_ids=(), legacy_names=()):
    """Raise ValueError unless every subject belongs to exactly one book.

    BOOKS order is the persistent category slot order; groups control only
    presentation. Saved slots and word IDs stay in order ahead of new ones.
    """
    ids = tuple(category for category, _ in books)
    routes = tuple(category for _, members in groups for category in members)
    if len(ids) != len(set(ids)):
        raise ValueError("a book ID appears twice")
    if ids[:len(legacy_ids)] != tuple(legacy_ids):
        raise ValueError("a saved book slot moved")
    if len(routes) != len(set(routes)) or set(routes) != set(ids):
        raise ValueError("every book needs exactly one shelf group")
    if set(titles) != set(ids):
        raise ValueError("every book needs exactly one title")
    pages = {}
    for category, members in books:
        if not members:
            raise ValueError(f"{category} has no pages")
        for name in members:
            if name in pages:
                raise ValueError(f"{name} appears in {pages[name]} and {category}")
            pages[name] = category
    if set(pages) != set(words):
        raise ValueError("pages and translated words differ: " + ", ".join(sorted(set(pages) ^ set(words))))
    if tuple(names) != tuple(dict.fromkeys(names)) or set(names) != set(pages):
        raise ValueError("word IDs must list every page once")
    if tuple(names[:len(legacy_names)]) != tuple(legacy_names):
        raise ValueError("a saved word ID moved")
    for name in pages:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            raise ValueError(f"{name} is not a safe asset name")
    for key, labels in (*words.items(), *titles.items()):
        if len(labels) != len(LANGUAGES) or not all(label and label == label.strip() for label in labels):
            raise ValueError(f"{key} needs one clean label per language")
    _require_unique_labels("word", words)
    _require_unique_labels("book", titles)
    for name, home in dict(homes).items():
        if pages.get(name) != home:
            raise ValueError(f"{name} belongs in {home}, not {pages.get(name)}")


def BuildUniqueBookCatalog():
    """Return the validated catalog: every subject is on exactly one page."""
    ValidateBookCatalog(BOOKS, BOOK_GROUPS, WORDS, TITLES, NAMES, UNIQUE["canonical_homes"], LEGACY_IDS, LEGACY_NAMES)
    return dict(books=BOOKS, groups=BOOK_GROUPS, words=WORDS, titles=TITLES,
                names=NAMES, page_names=PAGE_NAMES)


BuildUniqueBookCatalog()
LETTERS = {
    "de": dict(zip("abcdefghijklmnopqrstuvwxyz", ("a", "be", "ze", "de", "e", "ef", "ge", "ha", "i", "jot", "ka", "el", "em", "en", "o", "pe", "ku", "er", "es", "te", "u", "fau", "we", "iks", "ypsilon", "zett")), ä="ä", ö="ö", ü="ü", ß="Eszett"),
    "es": dict(zip("abcdefghijklmnopqrstuvwxyz", ("a", "be", "ce", "de", "e", "efe", "ge", "hache", "i", "jota", "ka", "ele", "eme", "ene", "o", "pe", "cu", "erre", "ese", "te", "u", "uve", "uve doble", "equis", "ye", "zeta")), ñ="eñe", á="a con tilde", é="e con tilde", í="i con tilde", ó="o con tilde", ú="u con tilde", ü="u con diéresis"),
}


def narration(name, language, simple=False):
    word = WORDS[name][LANGUAGES.index(language)]
    if simple:
        return word + "."
    letters = [letter for letter in word.upper() if not letter.isspace()] if language == "en" else [LETTERS[language][letter] for letter in word.lower() if not letter.isspace()]
    return word + ". " + ". ".join(letters) + ". " + word + "."


def voice_path(name, language, simple=False):
    # Preserve the original verified English spelling recordings.
    folder = "" if language == "en" and not simple else language + ("/simple/" if simple else "/spelling/")
    stem = UNIQUE["voice_stems"].get(name, {}).get(language, name)
    return "assets/jungle-book/sounds/" + folder + stem + ".wav"

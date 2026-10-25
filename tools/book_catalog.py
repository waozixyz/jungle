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
EXPANSION = json.loads(Path(__file__).with_name("book_expansion.json").read_text())
_original = dict(BOOKS)
BOOKS = tuple((category, _original.get(category, ()) + tuple(extra)) for category, extra in EXPANSION["extra"].items())
WORDS.update((name, tuple(words)) for name, words in EXPANSION["words"].items())
TITLES = EXPANSION["titles"]
NAMES = tuple(name for _, names in BOOKS for name in names)
LETTERS = {
    "de": dict(zip("abcdefghijklmnopqrstuvwxyz", ("a", "be", "ze", "de", "e", "ef", "ge", "ha", "i", "jot", "ka", "el", "em", "en", "o", "pe", "ku", "er", "es", "te", "u", "fau", "we", "iks", "ypsilon", "zett")), ä="ä", ö="ö", ü="ü", ß="Eszett"),
    "es": dict(zip("abcdefghijklmnopqrstuvwxyz", ("a", "be", "ce", "de", "e", "efe", "ge", "hache", "i", "jota", "ka", "ele", "eme", "ene", "o", "pe", "cu", "erre", "ese", "te", "u", "uve", "uve doble", "equis", "ye", "zeta")), ñ="eñe", á="a con tilde", é="e con tilde", í="i con tilde", ó="o con tilde", ú="u con tilde"),
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
    return "assets/jungle-book/sounds/" + folder + name + ".wav"

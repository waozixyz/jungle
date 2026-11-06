"""Validate language coverage and the shipped teaching inventory without a display."""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from book_catalog import BOOKS, LANGUAGES, NAMES, WORDS, narration, voice_path


def source_literals(text):
    # Match strings before interpreting comment markers inside them. Quoted
    # protocol documentation in comments is not a displayed message.
    tokens = r'//[^\n]*|/\*.*?\*/|"((?:\\.|[^"\\])*)"'
    return [match[1] for match in re.finditer(tokens, text, re.S) if match[1] is not None]


def main():
    assert source_literals('// "protocol fields"\n"Visible message" /* "comment" */\n"https://waozi.xyz"') == [
        "Visible message", "https://waozi.xyz"]
    rows = json.loads((ROOT / "locales/ui.json").read_text())
    for english, translations in rows.items():
        assert len(translations) == 2 and all(translations), english
        for text in (english, *translations):
            assert all(ord(c) < 256 for c in text), "UI font cannot represent " + text
    # Every visible fixed message, including errors and legacy game dialogs,
    # must have both translations. Technical strings and scientific short
    # names are explicitly outside this message inventory.
    for source in ("games/paint/dino_paint.zi", "games/animal/animal_count.zi", "games/abc/jungle_abc.zi", "games/numbers/jungle_numbers.zi", "games/jigsaw/jungle_jigsaw.zi", "games/piano/jungle_piano.zi", "games/piano/song.zi", "games/piano/catalog.zi", "host/desktop.zi", "host/jungle_host.zi", "src/app.zi"):
        text = (ROOT / source).read_text()
        # Inline Words("en", "de", "es") wording must match its registered
        # row; its German and Spanish literals are translations, not keys.
        translated = set()
        for english, german, spanish in re.findall(r'Words\("([^"\n]*)",\s*"([^"\n]*)",\s*"([^"\n]*)"\)', text):
            assert rows.get(english) == [german, spanish], (source, "inline wording differs", english)
            translated.update((german, spanish))
        for value in source_literals(text):
            if value in translated and value not in rows:
                continue
            if " " not in value or not value.strip() or value.startswith(("assets/", "paint", "skill ", " runs here", ":", "jungle:")):
                continue
            # Numeric ink/touch protocol fields contain no wording to translate.
            if re.fullmatch(r'%(?: %)+', value):
                continue
            if value in ("FILE|TITLE|ABOUT|ICON|AGE", "Jungle Academy", "jungle --check", "COUNTING", " / ", "  ·  ", " : ") or "\\" in value:
                continue
            assert value in rows, (source, "untranslated message", value)
    assert len(BOOKS) == 42 and len(NAMES) == len(set(NAMES)) == 450
    assert dict((name, len(words)) for name, words in BOOKS) == dict(jungle=15, garden=10, fruits=16, farm=16, vegetables=16, clothing=12, places=15, **{name: 10 for name in ("kitchen", "bathroom", "bedroom", "living-room", "nature", "family", "breakfast", "lunch", "dinner", "body", "seasons", "birds", "toys", "vehicles", "bedtime", "vacation", "sports", "beach", "weather", "feelings", "tropical-fruits", "gardening", "school", "water-animals", "drinks", "actions", "desert-animals", "insects", "people-at-work", "reptiles", "trees", "plants", "forest", "pets", "on-the-farm")})
    assert set(NAMES) == set(WORDS)
    generated = (ROOT / "games/book/book_pages.zi").read_text()
    voices = (ROOT / "games/book/book_voice.zi").read_text()
    for language_index, language in enumerate(LANGUAGES):
        for name in NAMES:
            word = WORDS[name][language_index]
            assert f'"{word}"' in generated
            assert f'"{" ".join(word.upper())}"' in generated
            for simple in (True, False):
                path = ROOT / voice_path(name, language, simple)
                metadata = json.loads(path.with_suffix(".speech.json").read_text())
                assert metadata["text"] == narration(name, language, simple)
                assert metadata["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
                assert str(path.relative_to(ROOT)) in voices
                if simple:
                    assert metadata["text"] == word + ".", "Simple mode must say the word exactly once"
    print(f"local language test: complete UI coverage, {len(NAMES)} translated words, {len(NAMES)*6} book recordings passed")


if __name__ == "__main__":
    main()

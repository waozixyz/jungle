"""Validate language coverage and the shipped teaching inventory without a display."""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from book_catalog import BOOKS, LANGUAGES, NAMES, WORDS, narration, voice_path


def main():
    rows = json.loads((ROOT / "locales/ui.json").read_text())
    for english, translations in rows.items():
        assert len(translations) == 2 and all(translations), english
        for text in (english, *translations):
            assert all(ord(c) < 256 for c in text), "UI font cannot represent " + text
    # Every visible fixed message, including errors and legacy game dialogs,
    # must have both translations. Technical strings and scientific short
    # names are explicitly outside this message inventory.
    for source in ("games/paint/dino_paint.zi", "games/animal/animal_count.zi", "games/abc/jungle_abc.zi", "host/desktop.zi", "host/jungle_host.zi", "src/app.zi"):
        text = (ROOT / source).read_text()
        for value in re.findall(r'"([^"\n]*)"', text):
            if " " not in value or not value.strip() or value.startswith(("assets/", "paint", "skill ", " runs here", ":", "jungle:")):
                continue
            if value in ("FILE|TITLE|ABOUT|ICON|AGE", "Jungle Academy", "jungle --check", "COUNTING") or "\\" in value:
                continue
            assert value in rows, (source, "untranslated message", value)
    assert len(BOOKS) == 15 and len(NAMES) == len(set(NAMES)) == 153
    assert dict((name, len(words)) for name, words in BOOKS) == dict(jungle=15, garden=10, fruits=16, farm=20, kitchen=8, bathroom=8, bedroom=8, **{"living-room":8}, nature=8, vegetables=16, family=8, breakfast=6, lunch=6, dinner=6, body=10)
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

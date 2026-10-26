"""Exercise all languages, both reading modes and ten books on a private Xvfb."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time

from PIL import ImageChops
from runtime_test import Desktop, ROOT
sys.path.insert(0, str(ROOT / "tools"))
from book_catalog import BOOKS, LANGUAGES, voice_path


def different(a, b, box=None):
    if box:
        a, b = a.crop(box), b.crop(box)
    return ImageChops.difference(a, b).getbbox() is not None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/app/jungle")
    args = parser.parse_args()
    binary = args.binary.resolve()
    ink = (62, 51, 42)
    with tempfile.TemporaryDirectory(prefix="jungle-book-") as temporary:
        data = Path(temporary)
        for index, language in enumerate(LANGUAGES):
            with Desktop(binary, data) as desktop:
                desktop.capture(f"{language}-menu-before")
                desktop.click(55 + index * 100, 12)
                menu = desktop.capture(f"{language}-menu")
                assert (data / "language.txt").read_text() == language
                desktop.key("1")
                categories = desktop.wait_book(f"{language}-books")
                # The saved setting from the preceding language is reset explicitly.
                desktop.key("s")
                firsts, endings = {}, {}
                for category_index, (name, names) in enumerate(BOOKS):
                    desktop.key(str((category_index + 1) % 10))
                    first = desktop.capture(f"{language}-{name}-simple")
                    assert ink in [c for _, c in first.crop((168, 74, 298, 113)).getcolors(10000)]
                    assert ink not in [c for _, c in first.crop((168, 115, 298, 130)).getcolors(10000)], "Simple mode still shows spelling"
                    firsts[name] = first
                    assert ink not in [c for _, c in first.crop((24, 16, 298, 27)).getcolors(10000)], "Page still shows a category or counter"
                    desktop.key("Left")
                    assert not different(first, desktop.capture(f"{language}-{name}-first-back")), "Back from the first page wrapped"
                    for _ in range(len(names) - 1):
                        desktop.key("Right")
                    last = desktop.capture(f"{language}-{name}-last")
                    assert different(first, last, (24, 39, 152, 167))
                    desktop.key("Right")
                    ending = desktop.capture(f"{language}-{name}-finished")
                    endings[name] = ending
                    assert different(last, ending), "Last page did not finish the book"
                    desktop.key("Left")
                    assert not different(last, desktop.capture(f"{language}-{name}-finished-back")), "Back from the finish did not restore the last picture"
                    desktop.key("Right")
                    desktop.key("Escape")
                    desktop.key(str((category_index + 1) % 10))
                    assert not different(first, desktop.capture(f"{language}-{name}-restarted"))
                    desktop.key("Right")
                    next_page = desktop.capture(f"{language}-{name}-next")
                    assert different(first, next_page, (24, 39, 152, 167))
                    desktop.drag(40, 112, 280, 112)
                    assert not different(first, desktop.capture(f"{language}-{name}-swipe-back"))
                    desktop.drag(280, 112, 40, 112)
                    assert not different(next_page, desktop.capture(f"{language}-{name}-swipe-forward"))
                    desktop.key("Left")
                    desktop.key("Right")
                    desktop.drag(80, 100, 84, 100)
                    assert not different(next_page, desktop.capture(f"{language}-{name}-short-drag"))
                    desktop.key("Left")
                    desktop.key("Right")
                    desktop.drag(100, 60, 100, 145)
                    assert not different(next_page, desktop.capture(f"{language}-{name}-vertical-drag"))
                    desktop.key("Escape")
                desktop.key("d")
                assert (data / "games/jungle.book/mode.txt").read_text() == "spelling"
                desktop.key("2")  # Garden contains the long butterfly word.
                desktop.key("Right")
                started = time.monotonic()
                spelling = desktop.capture(f"{language}-butterfly-spelling")
                assert ink in [c for _, c in spelling.crop((168, 103, 298, 125)).getcolors(10000)], "Spelling line is missing"
                duration = json.loads((ROOT / voice_path("butterfly", language)).with_suffix(".speech.json").read_text())["duration"]
                hold = max(12, duration + 3)
                time.sleep(min(5, hold - 2))
                assert not different(spelling, desktop.capture(f"{language}-spelling-held")), "Narration was cut short"
                if language == "en":
                    time.sleep(max(0, hold + 1 - (time.monotonic() - started)))
                    assert different(spelling, desktop.capture("en-spelling-auto-turn")), "Automatic turning stopped"
                desktop.key("Escape")
                desktop.key("Escape")
                desktop.key("1")
                desktop.wait_book(f"{language}-mode-reopened")
                desktop.key("2")
                desktop.key("Right")
                assert not different(spelling, desktop.capture(f"{language}-spelling-persisted")), "Book mode did not persist"
                desktop.key("Escape")
                desktop.key("s")
                desktop.key("1")
                simple = desktop.capture(f"{language}-simple-timing")
                duration = json.loads((ROOT / voice_path("tiger", language, True)).with_suffix(".speech.json").read_text())["duration"]
                time.sleep(max(6, duration + 3) + 1)
                assert different(simple, desktop.capture(f"{language}-simple-auto-turn")), "Simple mode never advanced"
                desktop.key("Escape")
                desktop.key("2")
                for _ in range(len(dict(BOOKS)["garden"]) - 1):
                    desktop.key("Right")
                duration = json.loads((ROOT / voice_path(dict(BOOKS)["garden"][-1], language, True)).with_suffix(".speech.json").read_text())["duration"]
                time.sleep(max(6, duration + 3) + 1)
                assert not different(endings["garden"], desktop.capture(f"{language}-auto-finished")), "Automatic reading looped instead of finishing"
                time.sleep(3.2)
                assert not different(firsts["fruits"], desktop.capture(f"{language}-suggested-next-book")), "Suggested book did not open"
                desktop.key("Escape")
                desktop.key("Escape")
                desktop.key("2")
                desktop.capture(f"{language}-counting")
                desktop.key("Escape")
                desktop.key("3")
                desktop.capture(f"{language}-paint")
                desktop.click(32, 14)
                desktop.capture(f"{language}-scenes")
            # Verify the actual saved language after starting a fresh process.
            with Desktop(binary, data) as desktop:
                persisted = desktop.capture(f"{language}-menu-persisted")
                assert not different(menu, persisted), "Language did not survive reopening Jungle"
            print(f"local UI test: {language}, ten books, two modes, swipes, timing and persistence passed", flush=True)
    print("local Picture Book language and mode UI tests passed")


if __name__ == "__main__":
    main()

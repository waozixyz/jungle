"""Read the Clothing and Seasons books in every supported language."""
from pathlib import Path
import sys
import tempfile

from book_ui_test import different, select_book, LABEL, SCENE
from runtime_test import Desktop, ROOT

sys.path.insert(0, str(ROOT / "tools"))
from book_catalog import BOOKS, LANGUAGES


with tempfile.TemporaryDirectory(prefix="jungle-new-books-") as temporary:
    data = Path(temporary)
    for index, language in enumerate(LANGUAGES):
        with Desktop(ROOT / "build/app/jungle", data) as desktop:
            desktop.capture(f"new-books-{language}-menu")
            desktop.click(55 + index * 100, 51)
            desktop.key("1")
            desktop.wait_book(f"new-books-{language}-shelf")
            desktop.key("s")
            for category in ("clothing", "seasons"):
                category_index = [name for name, _ in BOOKS].index(category)
                select_book(desktop, category_index)
                first = desktop.capture(f"new-books-{language}-{category}-first")
                for page in range(1, len(dict(BOOKS)[category])):
                    desktop.key("Right")
                    if language == "de" and category == "clothing" and page == 4:
                        desktop.capture_actual("new-books-de-skirt")
                last = desktop.capture(f"new-books-{language}-{category}-last")
                assert different(first, last, SCENE), f"{category} did not turn through its pictures"
                desktop.key("Right")
                ending = desktop.capture(f"new-books-{language}-{category}-finished")
                assert different(last, ending), f"{category} did not reach its finish screen"
                desktop.key("Escape")
                desktop.key("d")
                select_book(desktop, category_index)
                spelling = desktop.capture(f"new-books-{language}-{category}-spelling")
                assert different(first, spelling, LABEL), f"{category} did not show its spelling"
                desktop.key("Escape")
                desktop.key("s")
        print(f"local UI test: {language} Clothing and Seasons, all pages, spelling and finish screens passed", flush=True)

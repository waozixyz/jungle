"""The combined entry opens both books without moving their saved progress."""
from pathlib import Path
import tempfile

from runtime_test import Desktop, ROOT


with tempfile.TemporaryDirectory(prefix="jungle-learning-menu-") as temporary:
    data = Path(temporary)
    saves = {
        "jungle.abc": "abc 3 22 2 1\n",
        "jungle.numbers": "numbers 2 12 1 0\n",
    }
    for name, content in saves.items():
        path = data / "games" / name / "progress.txt"
        path.parent.mkdir(parents=True)
        path.write_text(content)
    with Desktop(ROOT / "build/app/jungle", data) as desktop:
        desktop.capture("combined-main")
        desktop.key("2")
        desktop.capture("combined-books")
        desktop.key("1")
        desktop.capture("combined-letters")
        desktop.key("Return")
        desktop.capture("combined-letter-learn")
        desktop.key("Escape")
        desktop.key("Escape")
        desktop.capture("combined-return")
        desktop.key("2")
        desktop.capture("combined-numbers")
        desktop.key("Return")
        desktop.capture("combined-number-learn")
        desktop.key("Escape")
        desktop.key("Escape")
        desktop.key("Escape")
        desktop.capture("combined-back-home")
        desktop.key("4")
        desktop.capture("combined-coloring")
        desktop.click(52, 58)
        assert (data / "games/jungle.paint/working.txt").exists(), "Fourth card did not open Coloring Book"
    for name, content in saves.items():
        assert (data / "games" / name / "progress.txt").read_text() == content, name
print("local UI test: combined ABC/123 navigation, Back, four menu entries and unchanged progress passed")

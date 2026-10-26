"""Open real learning pages, their shared images and Back with old saves intact."""
from pathlib import Path
import tempfile
import os
from PIL import ImageChops
from runtime_test import Desktop, ROOT, OUTPUT

for language in ("en", "de", "es"):
    with tempfile.TemporaryDirectory(prefix="jungle-learning-menu-") as temporary:
        data = Path(temporary)
        (data / "language.txt").write_text(language)
        saves = {"jungle.abc": "abc 3 22 2 1\n", "jungle.numbers": "numbers 2 12 1 0\n"}
        for name, content in saves.items():
            path = data / "games" / name / "progress.txt"
            path.parent.mkdir(parents=True)
            path.write_text(content)
        with Desktop(Path(os.environ.get("JUNGLE_TEST_BINARY", ROOT / "build/app/jungle")), data) as desktop:
            desktop.capture("combined-main-" + language)
            desktop.key("2")
            hub = desktop.capture("combined-books-" + language)
            for choice, name in (("1", "letters"), ("2", "numbers")):
                desktop.key(choice)
                page = desktop.capture_actual("direct-" + name + "-" + language)
                # A real watercolor picture must render immediately. The old
                # activity cards and the stopped-game menu contain no such art.
                picture = page.crop((page.width // 2, 90, page.width - 40, page.height - 90))
                vivid = sum(1 for r,g,b in (picture.get_flattened_data() if hasattr(picture, "get_flattened_data") else picture.getdata()) if max(r,g,b)-min(r,g,b)>65 and min(r,g,b)<160)
                assert vivid > 300, (name, language, "shared illustration did not render")
                desktop.key("Right")
                changed = desktop.capture_actual("next-" + name + "-" + language)
                assert ImageChops.difference(page, changed).getbbox(), "Next did not change the learning page"
                desktop.click_actual(30, 28)
                if choice == "2": desktop.key("Up")
                returned = desktop.capture("returned-" + name + "-" + language)
                assert ImageChops.difference(hub, returned).getbbox() is None, "Back did not return directly to the book choice"
            desktop.key("Escape")
            desktop.key("4")
            desktop.capture("combined-coloring")
            desktop.click(52, 58)
            working = data / "games/jungle.paint/working.txt"
            assert working.exists(), "Fourth card did not open Coloring Book"
            saved = working.read_bytes()
            desktop.key("Escape")  # Close the stencil picker.
            desktop.key("Escape")  # Leave the picture directly.
            desktop.key("2")
            assert ImageChops.difference(hub, desktop.capture("after-coloring-exit")).getbbox() is None, "Coloring Back still asks Yes/No"
            assert working.read_bytes() == saved, "Back changed the saved picture"
            assert "portable execution failed" not in (OUTPUT / "jungle.log").read_text(), "A game stopped"
        for name, content in saves.items():
            assert (data / "games" / name / "progress.txt").read_text() == content, name
print("local UI test: direct learning, shared pictures, Back, saved coloring and preserved progress in all three languages passed")

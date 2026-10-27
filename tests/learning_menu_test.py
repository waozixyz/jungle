"""Open real learning pages, their shared images and Back with old saves intact."""
from pathlib import Path
import tempfile
import os
import time
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
                # Letters are taught alone by default. Pictures are optional;
                # the number pages still show their counted animals.
                picture = page.crop((page.width // 2, 90, page.width - 40, page.height - 90))
                vivid = sum(1 for r,g,b in (picture.get_flattened_data() if hasattr(picture, "get_flattened_data") else picture.getdata()) if max(r,g,b)-min(r,g,b)>65 and min(r,g,b)<160)
                if name == "letters":
                    assert vivid < 100, (language, "ABC default still shows word examples")
                    # Open the optional right-hand examples at the current size.
                    width, height = page.size
                    fit = min(width / 320, (height - 56) / 200)
                    padding = max(24, int(14 * fit) + 8)
                    desktop.click_actual(width // 2, 56 + padding + 16)
                    illustrated = desktop.capture_actual("examples-" + language)
                    colors = illustrated.crop((width // 2, 90, width - 40, height - 90))
                    pixels = colors.get_flattened_data() if hasattr(colors, "get_flattened_data") else colors.getdata()
                    assert sum(1 for r,g,b in pixels if max(r,g,b)-min(r,g,b)>65 and min(r,g,b)<160) > 300, "Optional shared illustration did not render"
                else:
                    # Cows and other pale/grey animals are valid watercolor
                    # pictures too. Check image detail rather than saturation.
                    colors = picture.getcolors(picture.width * picture.height)
                    assert len(colors or []) > 256, (language, "Counted animals did not render")
                desktop.key("Right")
                changed = desktop.capture_actual("next-" + name + "-" + language)
                assert ImageChops.difference(page, changed).getbbox(), "Next did not change the learning page"
                desktop.click_actual(30, 28)
                if choice == "2": desktop.key("Up")
                returned = desktop.capture("returned-" + name + "-" + language)
                assert ImageChops.difference(hub, returned).getbbox() is None, "Back did not return directly to the book choice"
            desktop.key("Escape")
            desktop.key("4")
            desktop.wait_scene_picker("combined-coloring")
            desktop.click(52, 58)
            working = data / "games/jungle.paint/working.txt"
            deadline = time.monotonic() + 20
            while not working.exists() and time.monotonic() < deadline:
                desktop.alive()
                time.sleep(.05)
            assert working.exists(), "Choosing the first background did not save the working picture"
            desktop.capture("combined-coloring-stencils", header=56)
            saved = working.read_bytes()
            desktop.key("Escape")  # Close the stencil picker.
            desktop.key("Escape")  # Leave the picture directly.
            desktop.wait_menu("after-coloring-home")
            desktop.key("2")
            deadline = time.monotonic() + 20
            while ImageChops.difference(hub, desktop.capture("after-coloring-exit")).getbbox() is not None:
                assert time.monotonic() < deadline, "Coloring Back did not return directly to the book choice"
            assert working.read_bytes() == saved, "Back changed the saved picture"
            assert "portable execution failed" not in (OUTPUT / "jungle.log").read_text(), "A game stopped"
        for name, content in saves.items():
            assert (data / "games" / name / "progress.txt").read_text() == content, name
print("local UI test: direct learning, shared pictures, Back, saved coloring and preserved progress in all three languages passed")

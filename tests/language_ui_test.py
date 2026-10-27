"""Verify localized game controls and accented stories using private displays."""
import argparse
from pathlib import Path
import tempfile
from runtime_test import Desktop, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/app/jungle")
    args = parser.parse_args()
    for index, language, words in ((1, "de", "Grüße, schön, süß"), (2, "es", "Niño, piña, ratón")):
        with tempfile.TemporaryDirectory(prefix="jungle-language-") as temporary:
            data = Path(temporary)
            with Desktop(args.binary.resolve(), data) as desktop:
                desktop.capture(f"language-{language}-initial")
                desktop.click(55 + index * 100, 51)
                desktop.capture(f"language-{language}-title")
                desktop.game("Animal Counting")
                desktop.capture(f"language-{language}-counting")
                desktop.key("Escape")
                desktop.game("Coloring Book")
                desktop.capture(f"language-{language}-paint")
                desktop.click(30, 15)
                desktop.capture(f"language-{language}-scenes")
                desktop.click(52, 58)
                desktop.capture(f"language-{language}-dinosaurs")
                desktop.click(52, 58)
                desktop.capture(f"language-{language}-sizes")
                desktop.click(280, 90)
                desktop.click(30, 40)
                desktop.capture(f"language-{language}-colors")
                desktop.key("Escape")
                desktop.click(30, 65)
                desktop.type(words)
                desktop.capture(f"language-{language}-story")
                desktop.key("Return")
                desktop.click(30, 110)
                desktop.capture(f"language-{language}-save")
                desktop.click(50, 80)
                saved = data / "games/jungle.paint/slot-0.txt"
                assert saved.exists()
                assert words.encode("latin-1") in saved.read_bytes(), "Accented keyboard input was lost"
                desktop.click(30, 65)
                desktop.key("Home")
                desktop.type("x")
                desktop.key("Return")
                desktop.click(30, 110)
                desktop.click(50, 80)
                desktop.capture(f"language-{language}-overwrite")
                desktop.click(210, 134)
                desktop.key("Escape")
                # Reload the accented original after cancelling the overwrite.
                desktop.click(30, 110)
                desktop.click(210, 38)
                desktop.click(50, 80)
                desktop.click(30, 135)
                desktop.capture(f"language-{language}-export")
                desktop.click(120, 104)
                exported = list((data / "games/jungle.paint/exports").glob("*.txt"))
                assert len(exported) == 1 and exported[0].read_text().startswith(words + "\n"), "UTF-8 export lost accents"
                desktop.key("Escape")
                desktop.click(30, 90)
                desktop.capture(f"language-{language}-erase")
                desktop.click(240, 85)
                desktop.key("Escape")
                desktop.capture(f"language-{language}-stop")
            print(f"local language UI test: {language} dialogs, accented input, save/load and UTF-8 export passed", flush=True)


if __name__ == "__main__":
    main()

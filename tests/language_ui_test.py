"""Verify localized game controls and accented stories using private displays."""
import argparse
from pathlib import Path
import tempfile
from runtime_test import ROOT
from paint_history_test import Desktop, WORK, open_slots, stencil_click, tool


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/app/jungle")
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    for index, language, words in ((1, "de", "Grüße, schön, süß"), (2, "es", "Niño, piña, ratón")):
        with tempfile.TemporaryDirectory(prefix="jungle-language-", dir=WORK) as temporary:
            data = Path(temporary)
            with Desktop(args.binary.resolve(), data) as desktop:
                desktop.capture(f"language-{language}-initial")
                desktop.click(55 + index * 100, 51)
                desktop.capture(f"language-{language}-title")
                desktop.game("Animal Counting")
                desktop.capture(f"language-{language}-counting")
                desktop.key("Escape")
                desktop.game("Coloring Book")
                desktop.wait_scene_picker(f"language-{language}-scenes")
                desktop.click(65, 78)
                desktop.capture(f"language-{language}-dinosaurs")
                stencil_click(desktop)
                desktop.capture(f"language-{language}-sizes")
                desktop.click(280, 90)
                tool(desktop, 1)
                desktop.capture(f"language-{language}-colors")
                desktop.key("Escape")
                tool(desktop, 2)
                desktop.type(words)
                desktop.capture(f"language-{language}-story")
                desktop.key("Return")
                open_slots(desktop)
                desktop.capture(f"language-{language}-save")
                desktop.click(50, 80)
                saved = data / "games/jungle.paint/slot-0.txt"
                assert saved.exists()
                assert words.encode("latin-1") in saved.read_bytes(), "Accented keyboard input was lost"
                tool(desktop, 2)
                desktop.key("Home")
                desktop.type("x")
                desktop.key("Return")
                open_slots(desktop)
                desktop.click(50, 80)
                desktop.capture(f"language-{language}-overwrite")
                desktop.click(210, 134)
                desktop.key("Escape")
                # Reload the accented original after cancelling the overwrite.
                open_slots(desktop)
                desktop.click(210, 38)
                desktop.click(50, 80)
                tool(desktop, 5)
                desktop.capture(f"language-{language}-export")
                desktop.click(120, 104)
                exported = list((data / "games/jungle.paint/exports").glob("*.txt"))
                assert len(exported) == 1 and exported[0].read_text().startswith(words + "\n"), "UTF-8 export lost accents"
                desktop.key("Escape")
                tool(desktop, 3)
                desktop.capture(f"language-{language}-erase")
                desktop.click(240, 85)
                desktop.key("Escape")
                desktop.capture(f"language-{language}-stop")
            print(f"local language UI test: {language} dialogs, accented input, save/load and UTF-8 export passed", flush=True)


if __name__ == "__main__":
    main()

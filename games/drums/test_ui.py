#!/usr/bin/env python3
"""Exercise only Little Drums in the real host on an owned private Xvfb.

The fixture copies the existing binary and our bundle, never source files or
the project's catalog. The owner's app and installed saves are untouched.
"""
from pathlib import Path
import shutil
import sys
import tempfile
import time
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
import runtime_test

runtime_test.OUTPUT = ROOT / "backup/drums-ui"


def geometry(width, height):
    height -= 56
    scale = min(width / 400, height / 700, 1.6)
    if width > height:
        scale = min(height / 520, width / 780, 1.6)
    scale = max(0.5, scale)
    w, h = int(width / scale), int(height / scale)
    board_h = h - 232
    columns = 4 if w > board_h * 2 else 2
    rows = 4 // columns
    edge = min((w - 32 - (columns - 1) * 14) // columns,
               (board_h - (rows - 1) * 14) // rows, 250)
    left = (w - columns * edge - (columns - 1) * 14) // 2
    top = 146 + (board_h - rows * edge - (rows - 1) * 14) // 2
    return scale, w, h, columns, edge, left, top


def main():
    with tempfile.TemporaryDirectory(prefix="jungle-drums-ui-") as temporary:
        fixture = Path(temporary)
        (fixture / "games").mkdir()
        (fixture / "assets/jungle-book").mkdir(parents=True)
        shutil.copy2(ROOT / "build/app/jungle", fixture / "jungle")
        shutil.copytree(ROOT / "assets/jungle", fixture / "assets/jungle")
        shutil.copy2(ROOT / "assets/jungle-book/font.png", fixture / "assets/jungle-book/font.png")
        manifest = ROOT / "build/app/assets/shared-assets.txt"
        if manifest.exists():
            shutil.copy2(manifest, fixture / "assets/shared-assets.txt")
        shutil.copy2(ROOT / "build/app/games/jungle-drums.zx", fixture / "games/jungle-drums.zx")
        (fixture / "games/catalog.txt").write_text("jungle-drums.zx|Little Drums|Tap and play|music|1\n")
        for language in ("en", "de", "es"):
            data = fixture / ("data-" + language)
            data.mkdir()
            (data / "language.txt").write_text(language)
            with runtime_test.Desktop(fixture / "jungle", data, screen_size="1280x1100") as desktop:
                desktop.key("1")
                for width, height in ((400, 756), (960, 600)):
                    desktop.resize(width, height)
                    scale, w, h, columns, edge, left, top = geometry(width, height)

                    def click(x, y):
                        desktop.click_actual(round(x * scale), round(56 + y * scale))

                    def capture(suffix):
                        return desktop.capture_actual(f"drums-{language}-{width}-{suffix}")

                    picture = capture("free")
                    # Every pad's upper inner corner retains its own soft fill.
                    fills = ((248, 231, 216), (233, 241, 227), (228, 240, 245), (249, 240, 213))
                    for pad, expected in enumerate(fills):
                        x = left + (pad % columns) * (edge + 14) + edge * 0.2
                        y = top + (pad // columns) * (edge + 14) + edge * 0.15
                        pixel = picture.getpixel((round(x * scale), round(56 + y * scale)))
                        assert max(abs(a-b) for a,b in zip(pixel, expected)) < 5, (language, width, pad, pixel)
                    # A real contact highlights immediately, even before release.
                    runtime_test.run(["xdotool", "mousemove", "--window", desktop.window,
                                      str(round((left + edge / 2) * scale)),
                                      str(round(56 + (top + edge / 2) * scale))], desktop.env)
                    runtime_test.run(["xdotool", "mousedown", "1"], desktop.env)
                    try:
                        time.sleep(0.12)
                        desktop.verify_server()
                        path = runtime_test.OUTPUT / f"drums-{language}-{width}-contact.png"
                        runtime_test.run(["import", "-display", desktop.env["DISPLAY"],
                                          "-window", desktop.window, str(path)], desktop.env)
                        pressed = Image.open(path).convert("RGB")
                        pixel = pressed.getpixel((round((left + edge * 0.2) * scale),
                                                  round(56 + (top + edge * 0.15) * scale)))
                        assert max(abs(a-b) for a,b in zip(pixel, (255,246,215))) < 5, ("contact highlight", pixel)
                    finally:
                        runtime_test.run(["xdotool", "mouseup", "1"], desktop.env)
                    # Finish narration before taking copy-mode captures.
                    click(w * 0.75, 36)
                    time.sleep(0.15)
                    capture("copy")
                    # Replay explicitly cancels narration and begins the demo.
                    click(w / 6, h - 42)
                    time.sleep(2.1)
                    capture("your-turn")
                    click(left + edge / 2, top + edge / 2)
                    capture("answer")
                    # The easy two-sound round and Free Play are always reachable.
                    click(w / 2, h - 42)
                    capture("easy")
                    click(w / 4, 36)
                    capture("free-again")
                    assert (data / "games/jungle.drums/drums.txt").read_text().startswith("drums 1 2 ")
                desktop.key("Escape")
    print("local drums UI test: four pads, touch contact, copy/replay/easy/free and saves in en/de/es, portrait and landscape")


if __name__ == "__main__":
    main()

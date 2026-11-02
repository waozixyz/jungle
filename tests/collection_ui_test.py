"""Collect the monkey by tapping it in Picture Book, then keep it across a restart, on a private Xvfb."""
import argparse
from pathlib import Path
import shutil
import sys
import time

from runtime_test import Desktop, ROOT
sys.path.insert(0, str(ROOT / "tools"))
from book_catalog import BOOKS

# retro/collectibles.zi: the monkey's ellipse centre on its square scene.
MONKEY = (0.48, 0.50)
TITLE_BAR = 56
SAVED = "JUNGLE COLLECTION 1\nmonkey\n"


def open_monkey(desktop):
    desktop.game("Picture Book")
    desktop.wait_book("collection-books")
    desktop.key("1")  # the Wild animals book opens on its first page
    names = dict(BOOKS)["jungle"]
    for _ in range(names.index("monkey")):
        desktop.key("Right")
    time.sleep(1.5)  # the page picture is presented before a tap can collect


def tap_monkey(desktop, name):
    width, height = desktop.capture_actual(name).size
    area = height - TITLE_BAR
    size = min(width, area)
    desktop.click_actual(round((width - size) / 2 + MONKEY[0] * size),
                         round(TITLE_BAR + (area - size) / 2 + MONKEY[1] * size))
    time.sleep(1.0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/app/jungle")
    parser.add_argument("--data", type=Path, default=ROOT / "work/collection-ui-data")
    args = parser.parse_args()
    data = args.data.resolve()
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    saved = data / "collection.txt"

    with Desktop(args.binary.resolve(), data) as desktop:
        open_monkey(desktop)
        assert not saved.exists(), "nothing is collected before the tap"
        tap_monkey(desktop, "collection-first-tap")
        assert saved.read_text() == SAVED, saved.read_text() if saved.exists() else "collection.txt missing"
        assert not (data / "collection.txt.new").exists()
    first = saved.stat().st_mtime_ns

    # After a restart the monkey is already collected: the same tap turns the page and
    # nothing is written again.
    with Desktop(args.binary.resolve(), data) as desktop:
        open_monkey(desktop)
        tap_monkey(desktop, "collection-restart-tap")
        assert saved.read_text() == SAVED
        assert saved.stat().st_mtime_ns == first, "a collected item was saved again"

    # An unreadable newer-format file is never overwritten.
    corrupt = "JUNGLE COLLECTION 2\nsomething-new\n"
    saved.write_text(corrupt)
    with Desktop(args.binary.resolve(), data) as desktop:
        open_monkey(desktop)
        tap_monkey(desktop, "collection-corrupt-tap")
        assert saved.read_text() == corrupt, "an invalid collection file was overwritten"
    print("collection UI test passed")


if __name__ == "__main__":
    main()

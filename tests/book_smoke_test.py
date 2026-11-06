"""Quick private-display startup verification for a freshly built or installed app."""
import argparse
from pathlib import Path
import tempfile
import time
from PIL import ImageChops
from runtime_test import Desktop, ROOT
import sys
sys.path.insert(0, str(ROOT / "tools"))
from book_catalog import BOOKS, BOOK_GROUPS


def settled(desktop, name):
    """A capture once the page has stopped changing (turns, awards)."""
    previous = desktop.capture(name)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        time.sleep(.4)
        current = desktop.capture(name)
        if not ImageChops.difference(previous, current).getbbox():
            return current
        previous = current
    raise AssertionError(f'{name} never stopped changing')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=ROOT / 'build/app/jungle')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='jungle-book-smoke-') as temporary:
        data = Path(temporary)
        with Desktop(args.binary.resolve(), data) as desktop:
            desktop.capture('new-version-menu')
            desktop.select_language(2)
            desktop.game("Picture Book")
            desktop.wait_book('new-version-spanish-books')
            desktop.key('3')
            simple = desktop.capture('new-version-spanish-simple')
            desktop.key('Escape')
            desktop.key("d")
            desktop.key('3')
            spelling = desktop.capture('new-version-spanish-spelling')
            assert ImageChops.difference(simple.crop((168, 103, 298, 125)), spelling.crop((168, 103, 298, 125))).getbbox(), 'Mode did not change the spelling line'
            desktop.key('Escape')
            desktop.key('4')
            desktop.capture('new-version-spanish-farm')
            desktop.key('Escape')
            desktop.key('Escape')
            # Leaving a game returns to the painted scene that opened it (the
            # bookshelf); Home walks back to the treehouse and its flags.
            desktop.key('Home')
            desktop.wait_menu('new-version-language-menu')
            desktop.select_language(1)
            desktop.game("Picture Book")
            desktop.wait_book('new-version-german-books')
            desktop.key('2')
            desktop.key('Right')
            desktop.capture('new-version-german-butterfly')
            for _ in range(len(dict(BOOKS)["garden"]) - 1):
                desktop.key('Right')
            finished = desktop.capture('new-version-book-finished')
            # The finished screen counts down FINISHED_SECONDS (8 s) and then
            # opens the next book in shelf order (games/book/jungle_book.zi).
            deadline = time.monotonic() + 14
            continued = finished
            while not ImageChops.difference(finished.crop((0, 40, 320, 200)), continued.crop((0, 40, 320, 200))).getbbox():
                assert time.monotonic() < deadline, 'The finished book never moved on'
                time.sleep(.5)
                continued = desktop.capture('new-version-next-book')
            continued = settled(desktop, 'new-version-next-book')
            desktop.key('Escape')
            # Number keys open books by catalog slot: 1-9, then 0 for the tenth.
            ids = [category for category, _ in BOOKS]
            order = [category for _, members in BOOK_GROUPS for category in members]
            following = ids.index(order[(order.index('garden') + 1) % len(order)])
            assert following < 10, 'The next book needs a number key'
            desktop.key(str((following + 1) % 10))
            expected = settled(desktop, 'new-version-expected-next-book')
            assert not ImageChops.difference(continued, expected).getbbox(), 'The next book did not open automatically'
            assert (data / 'language.txt').read_text() == 'de'
            assert (data / 'games/jungle.book/mode.txt').read_text() == 'spelling'
    print('local startup test: new language flags, ten books, Simple/Spelling modes and German/Spanish pages passed')


if __name__ == '__main__': main()

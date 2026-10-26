"""Quick private-display startup verification for a freshly built or installed app."""
import argparse
from pathlib import Path
import tempfile
import time
from PIL import ImageChops
from runtime_test import Desktop, ROOT
import sys
sys.path.insert(0, str(ROOT / "tools"))
from book_catalog import BOOKS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=ROOT / 'build/app/jungle')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='jungle-book-smoke-') as temporary:
        data = Path(temporary)
        with Desktop(args.binary.resolve(), data) as desktop:
            desktop.capture('new-version-menu')
            desktop.click(255, 51)
            desktop.key('1')
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
            desktop.wait_menu('new-version-language-menu')
            desktop.click(155, 51)
            desktop.key('1')
            desktop.wait_book('new-version-german-books')
            desktop.key('2')
            desktop.key('Right')
            desktop.capture('new-version-german-butterfly')
            for _ in range(len(dict(BOOKS)["garden"]) - 1):
                desktop.key('Right')
            desktop.capture('new-version-book-finished')
            time.sleep(3.3)
            continued = desktop.capture('new-version-next-book')
            desktop.key('Escape')
            desktop.key('3')
            expected = desktop.capture('new-version-expected-next-book')
            assert not ImageChops.difference(continued, expected).getbbox(), 'The next book did not open automatically'
            assert (data / 'language.txt').read_text() == 'de'
            assert (data / 'games/jungle.book/mode.txt').read_text() == 'spelling'
    print('local startup test: new language flags, ten books, Simple/Spelling modes and German/Spanish pages passed')


if __name__ == '__main__': main()

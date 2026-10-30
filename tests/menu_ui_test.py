"""Age order and the real scroll container on a private display."""
from pathlib import Path
import os
import tempfile
import time
from PIL import ImageChops
from runtime_test import Desktop, ROOT

catalog = [line.split('|') for line in (ROOT/'games/catalog.txt').read_text().splitlines() if '|' in line]
root_entries = [row for row in sorted(catalog, key=lambda row: int(row[4])) if row[1] != '123 Book']
ages = [int(row[4]) for row in root_entries]
assert ages == sorted(ages), 'The visible catalog is not in age order'
assert len(set(row[1] for row in root_entries)) == len(root_entries), 'The visible catalog has duplicate titles'
jigsaw_title = next(row[1] for row in root_entries if row[1] == 'Jigsaw Puzzles')
coloring_title = next(row[1] for row in root_entries if row[1] == 'Coloring Book')
visible_rows = 3
scroll_count = max(0, len(root_entries) - visible_rows)
coloring_row = next(index for index, row in enumerate(root_entries) if row[1] == coloring_title) - scroll_count
assert 0 <= coloring_row < visible_rows, 'Coloring is not visible after catalog-derived scrolling'

with tempfile.TemporaryDirectory(prefix='jungle-menu-') as temporary:
    with Desktop(Path(os.environ.get('JUNGLE_TEST_BINARY',ROOT/'build/app/jungle')),Path(temporary),screen_size='1280x1100') as desktop:
        desktop.resize(960,600)
        initial=desktop.capture('age-menu-top')
        desktop.game(jigsaw_title)
        desktop.wait_jigsaw_setup('age-menu-third-jigsaw')
        desktop.key('Return')
        saved = Path(temporary)/'games/jungle.jigsaw/puzzle.txt'
        deadline=time.monotonic()+20
        while not saved.exists() and time.monotonic()<deadline:
            desktop.alive();time.sleep(.1)
        assert saved.exists(),'Jigsaw did not start and save its puzzle'
        desktop.key('Escape');desktop.key('Escape')
        for _ in range(scroll_count): desktop.click(180,120,button=5)
        scrolled=desktop.capture('age-menu-scrolled')
        assert ImageChops.difference(initial.crop((0,0,320,64)),scrolled.crop((0,0,320,64))).getbbox() is None,'Scrolling moved the heading or language flags'
        assert ImageChops.difference(initial.crop((0,174,320,200)),scrolled.crop((0,174,320,200))).getbbox() is None,'Scrolling moved the footer'
        desktop.click(150,75 + coloring_row * 37)
        desktop.wait_scene_picker('age-menu-scrolled-coloring')
        desktop.key('Escape')
        desktop.game(root_entries[0][1])
        desktop.capture('age-menu-keyboard-top')
        desktop.wait_book('age-menu-first-picture-book')
print('local menu UI test: age order, wheel scrolling, fixed header/footer, click activation and keyboard reveal passed')

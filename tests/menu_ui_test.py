"""Age order and the real scroll container on a private display."""
from pathlib import Path
import os
import tempfile
import time
from PIL import ImageChops
from runtime_test import Desktop, ROOT

with tempfile.TemporaryDirectory(prefix='jungle-menu-') as temporary:
    with Desktop(Path(os.environ.get('JUNGLE_TEST_BINARY',ROOT/'build/app/jungle')),Path(temporary),screen_size='1280x1100') as desktop:
        desktop.resize(960,600)
        initial=desktop.capture('age-menu-top')
        # The third entry is the new 3+ puzzle, before counting (4+) and
        # coloring (5+). Number activation still reaches offscreen entries.
        desktop.key('3')
        desktop.wait_jigsaw_setup('age-menu-third-jigsaw')
        desktop.key('Return')
        saved = Path(temporary)/'games/jungle.jigsaw/puzzle.txt'
        deadline=time.monotonic()+20
        while not saved.exists() and time.monotonic()<deadline:
            desktop.alive();time.sleep(.1)
        assert saved.exists(),'Jigsaw did not start and save its puzzle'
        desktop.key('Escape');desktop.key('Escape')
        for _ in range(8): desktop.click(180,120,button=5)
        scrolled=desktop.capture('age-menu-scrolled')
        assert ImageChops.difference(initial.crop((0,0,320,64)),scrolled.crop((0,0,320,64))).getbbox() is None,'Scrolling moved the heading or language flags'
        assert ImageChops.difference(initial.crop((0,174,320,200)),scrolled.crop((0,174,320,200))).getbbox() is None,'Scrolling moved the footer'
        desktop.click(150,146)
        desktop.wait_scene_picker('age-menu-scrolled-coloring')
        desktop.key('Escape')
        # Arrow navigation reveals the first row again inside the container.
        desktop.key('Down')
        desktop.capture('age-menu-keyboard-top')
        desktop.key('Return')
        desktop.wait_book('age-menu-first-picture-book')
print('local menu UI test: age order, wheel scrolling, fixed header/footer, click activation and keyboard reveal passed')

"""Playback and saved book choices on a disposable, privately owned display."""
import tempfile
import time
import os
from pathlib import Path
from PIL import ImageChops
from runtime_test import Desktop, ROOT, run


def changed(a, b, box=None):
    if box:
        a, b = a.crop(box), b.crop(box)
    return ImageChops.difference(a, b).getbbox() is not None


with tempfile.TemporaryDirectory(prefix='jungle-playback-') as temporary:
    data = Path(temporary)
    binary = Path(os.environ.get('JUNGLE_TEST_BINARY', ROOT / 'build/app/jungle'))
    with Desktop(binary, data) as desktop:
        run(['xdotool', 'windowmove', desktop.window, '0', '0'], desktop.env)
        desktop.resize(960, 600)
        desktop.key('1')
        desktop.key('1')
        before = desktop.capture_actual('playback-book-before-pause')
        desktop.key('space')
        paused = desktop.capture_actual('playback-book-paused')
        assert not changed(before, paused, (240, 100, 720, 430)), 'Space turned the page instead of pausing'
        time.sleep(7)
        held = desktop.capture_actual('playback-book-held')
        assert not changed(paused, held), 'A paused picture book kept advancing'
        desktop.key('space')
        time.sleep(7)
        resumed = desktop.capture_actual('playback-book-resumed')
        assert changed(paused, resumed, (240, 100, 720, 430)), 'Resume did not continue the book'
        desktop.key('Escape')
        # Manage the first Nature book, then verify the actual saved choices.
        desktop.click_actual(773, 526)
        desktop.click_actual(156, 303)
        desktop.click_actual(359, 303)
        choices = data / 'games/jungle.book'
        assert (choices / 'hidden-jungle.txt').read_text() == 'yes'
        assert (choices / 'skip-jungle.txt').read_text() == 'yes'
        desktop.click_actual(773, 526)
        shelf = desktop.capture_actual('playback-hidden-book-shelf')
        desktop.key('1')
        assert not changed(shelf, desktop.capture_actual('playback-hidden-book-shortcut')), 'A hidden book opened from its shortcut'
        # Re-enable it through Manage, keeping its independent autoplay choice.
        desktop.click_actual(773, 526)
        desktop.click_actual(156, 303)
        assert (choices / 'hidden-jungle.txt').read_text() == 'no'
        assert (choices / 'skip-jungle.txt').read_text() == 'yes'
        desktop.click_actual(773, 526)
        desktop.key('Escape')
        desktop.key('2')
        desktop.key('2')
        number_one = desktop.capture_actual('playback-number-one')
        desktop.key('space')
        time.sleep(4.7)
        number_two = desktop.capture_actual('playback-number-two')
        assert changed(number_one, number_two, (90, 90, 430, 430)), 'Number autoplay did not advance'
        desktop.key('space')
        number_paused = desktop.capture_actual('playback-number-paused')
        time.sleep(4.7)
        assert not changed(number_paused, desktop.capture_actual('playback-number-held')), 'Paused number autoplay kept advancing'
        assert 'portable execution failed' not in (ROOT / 'build/tests/ui/jungle.log').read_text()
print('local playback UI test: Space pause/resume, hidden shortcuts, independent saved autoplay choices and number autoplay passed')

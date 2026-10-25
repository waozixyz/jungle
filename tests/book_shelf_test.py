"""Verify the larger native window and grouped scrolling on an owned display."""
from pathlib import Path
import tempfile
from PIL import ImageChops
from runtime_test import Desktop, ROOT


with tempfile.TemporaryDirectory(prefix='jungle-shelf-') as directory:
    with Desktop(ROOT / 'build/app/jungle', Path(directory), screen_size='1600x1000') as desktop:
        desktop.capture('larger-window-menu')
        assert desktop.scale == 4, 'Default window did not grow to 1280 by 800'
        desktop.key('1')
        top = desktop.wait_book('shelf-top')
        for _ in range(8):
            desktop.click(225, 120, button=5)
        bottom = desktop.capture('shelf-bottom')
        assert ImageChops.difference(top, bottom).getbbox(), 'Wheel did not scroll the book shelf'
        desktop.click(225, 123)
        selected = desktop.capture('shelf-room')
        desktop.key('Escape')
        desktop.key('8')
        direct = desktop.capture('shelf-room-direct')
        assert not ImageChops.difference(selected, direct).getbbox(), 'Clipped scroll input opened the wrong book'
print('local UI test: larger default window, grouped shelf, wheel scrolling and room selection passed')

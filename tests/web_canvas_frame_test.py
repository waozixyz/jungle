#!/usr/bin/env python3
"""The web page's canvas frame is exactly the canvas touches land on.

Kryon draws the page at the size of #canvas-frame. When the frame was padded
by safe-area insets (notched phones, home bars), the canvas inside it was
smaller, the picture was squeezed toward the top and a tap on a keypad button
pressed the one above. The insets pad the body instead, and this checks the
resulting geometry: a touch at a button's centre maps to that button.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
page = (ROOT / 'web/index.html').read_text()
style = page.split('<style>', 1)[1].split('</style>', 1)[0]
screen = style.split('@media print', 1)[0]
rules = {}
for selector, body in re.findall(r'([^{}]+)\{([^{}]*)\}', screen):
    for name in selector.split(','):
        rules.setdefault(name.strip(), []).append(body)

frame = ';'.join(rules.get('#canvas-frame', []))
assert 'padding' not in frame, '#canvas-frame must not be padded: ' + frame
body = ';'.join(rules.get('body', []))
for side in ('top', 'right', 'bottom', 'left'):
    assert 'env(safe-area-inset-' + side + ')' in body, 'body keeps the ' + side + ' safe-area inset'
assert 'width:100%' in frame and 'height:100%' in frame
assert re.search(r'(^|;)\s*width:100%;height:100%', ';'.join(rules.get('canvas', []))), 'canvas fills its frame'


def keypad_touch(frame_height, canvas_top, canvas_height, page_y):
    """Where a touch on page_y lands: Kryon draws frame_height units into the
    canvas box and reads touches as client offsets from the canvas top."""
    shown = canvas_top + page_y * canvas_height / frame_height
    return shown - canvas_top


# A 390 x 844 phone with 48 px and 34 px safe-area insets: the canvas is 762
# tall. Animal Counting's portrait keypad rows are about 44 px apart; the
# centre of the second-to-last row sits near y 624.
centre = 624.0
# Padded frame (the old page): the frame measured 844, the touch lands 61 px
# (more than a row) above the centre that was drawn under the finger.
assert keypad_touch(844.0, 48.0, 762.0, centre) < centre - 44.0
# Body padding (this page): the frame is the canvas, the touch hits the centre.
assert abs(keypad_touch(762.0, 0.0, 762.0, centre) - centre) < 0.001
print('web canvas frame: unpadded frame, safe-area insets on the body, keypad touches on target')

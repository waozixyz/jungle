
import json
import os
from pathlib import Path
import tempfile
import time

from runtime_test import Desktop, ROOT


def guide_controls(width, height):
    """Step 1 ("Drag to see more") is centred and the longest line, so the test
    can reach its controls before the guide moves on."""
    unit = max(1.0, min(3.0, min(width, height) / 300.0))
    view_width, view_height = int(width / unit), int(height / unit)
    anchor = (view_width // 2 - 34, view_height // 2 - 34, 68, 68)
    bubble_width = 228 if view_width >= 270 else 208 if view_width >= 190 else max(120, view_width - 12)
    bubble_x = max(6, min(view_width - 6 - bubble_width, anchor[0] + anchor[2] // 2 - bubble_width // 2))
    bubble_y = anchor[1] + anchor[3] + 8
    if bubble_y + 48 > view_height - 8:
        bubble_y = anchor[1] - 56
    if bubble_y < 38:
        bubble_y = view_height - 56
    box = tuple(int(value * unit) for value in (bubble_x, bubble_y, bubble_width, 48))
    mute_x, mute_y = box[0] + box[2] - 42, box[1] + 5
    skip_x, skip_y = box[0] + box[2] - 21, box[1] + 5
    return (mute_x + 8, mute_y + 8), (skip_x + 8, skip_y + 8), box


def cream_pixels(picture, x, y, width, height):
    region = picture.crop((x + 6, y + 6, x + width - 50, y + height - 6))
    return sum(1 for color in region.getdata()
               if abs(color[0] - 247) < 10 and abs(color[1] - 241) < 10 and abs(color[2] - 227) < 10)


def edge_pixels(picture, x, y, width, height):
    points = [(x + offset, y) for offset in range(2, width - 2, 4)]
    points += [(x + offset, y + height - 1) for offset in range(2, width - 2, 4)]
    points += [(x, y + offset) for offset in range(2, height - 2, 4)]
    points += [(x + width - 1, y + offset) for offset in range(2, height - 2, 4)]
    return sum(1 for point in points
               if abs(picture.getpixel(point)[0] - 218) < 8
               and abs(picture.getpixel(point)[1] - 205) < 8
               and abs(picture.getpixel(point)[2] - 181) < 8)


def wait_guide(desktop, width, height, name):
    mute, skip, box = guide_controls(width, height)
    x, y, width, height = box
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        picture = desktop.capture_actual(name)
        mute_box = (mute[0] - 8, mute[1] - 8, 16, 16)
        skip_box = (skip[0] - 8, skip[1] - 8, 16, 16)
        if (cream_pixels(picture, x, y, width, height) > 2500 and
                edge_pixels(picture, *mute_box) > 5 and
                edge_pixels(picture, *skip_box) > 5):
            return picture, mute, skip
        time.sleep(.05)
    raise AssertionError("Compact guide did not appear")


binary = Path(os.environ.get("JUNGLE_TEST_BINARY", ROOT / "build/app/jungle"))
work = ROOT / "work/title-guide-ui"
work.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="skip-", dir=work) as temporary:
    data = Path(temporary)
    with Desktop(binary, data, screen_size="320x200") as desktop:
        _, _, skip = wait_guide(desktop, 320, 200, "guide-before-skip")
        desktop.click_actual(*skip)
        immediate = desktop.capture_actual("guide-immediately-after-skip")
        _, _, box = guide_controls(320, 200)
        assert cream_pixels(immediate, *box) < 500, "Skipped guide stayed on screen"
    assert (data / "guide-seen.txt").read_text() == "yes\n", "Guide skip was not saved"
    with Desktop(binary, data, screen_size="320x200") as desktop:
        desktop.wait_menu("guide-disabled")
        picture = desktop.capture_actual("guide-disabled")
        _, _, box = guide_controls(320, 200)
        assert cream_pixels(picture, *box) < 500, "Skipped guide reappeared"

with tempfile.TemporaryDirectory(prefix="mute-", dir=work) as temporary:
    data = Path(temporary)
    with Desktop(binary, data, screen_size="320x200") as desktop:
        _, mute, _ = wait_guide(desktop, 320, 200, "guide-before-mute")
        desktop.click_actual(*mute)
    assert (data / "guide-sound.txt").read_text() == "off\n", "Guide mute was not saved"
    with Desktop(binary, data, screen_size="320x200") as desktop:
        wait_guide(desktop, 320, 200, "guide-after-mute")
    assert (data / "guide-sound.txt").read_text() == "off\n", "Guide mute did not survive restart"

with tempfile.TemporaryDirectory(prefix="portrait-", dir=work) as temporary:
    with Desktop(binary, Path(temporary)) as desktop:
        desktop.resize(600, 900)
        assert desktop.actual_size == (600, 900), desktop.actual_size
        _, _, box = guide_controls(600, 900)
        deadline = time.monotonic() + 8
        while cream_pixels(desktop.capture_actual("guide-portrait"), *box) <= 2500:
            assert time.monotonic() < deadline, "Compact guide did not fit portrait"
        assert box[2] < 600 and box[3] < 900 / 4, box

print("title guide UI test: mute persisted, skip stayed dismissed, portrait fits")

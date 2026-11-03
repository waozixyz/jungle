"""The real app on an owned private Xvfb: an earlier save gets its award
quietly, a game's first opening gives and celebrates its award once, and the
Collection Book shows it. Both orientations; captures stay in backup/."""
import os
from pathlib import Path
import shutil
import tempfile
import time
import runtime_test as rt

def gold(picture, box):
    """How many pixels of BOX in PICTURE have the badge rim's saturated gold,
    which the games' wooden tables (blue 90 and up) never reach."""
    count = 0
    for r, g, b in picture.crop(box).get_flattened_data():
        if r >= 200 and 130 <= g <= 215 and b <= 60 and r - b > 150:
            count += 1
    return count


def badge_box(width, height):
    """The rim of the badge resting in the game area (host/jungle_awards.zi)."""
    area = height - 56
    size = max(96, min(320, min(width, area) * 2 // 5))
    x, y = width // 2, 56 + area // 2
    return (x - size // 2, y - size // 2, x + size // 2, y + size // 2)


def main():
    root = rt.ROOT
    scratch = root / 'backup/awards-smoke'
    scratch.mkdir(parents=True, exist_ok=True)
    rt.OUTPUT = scratch / 'captures'
    binary = Path(os.environ.get('JUNGLE_TEST_BINARY', root / 'build/app/jungle'))
    for width, height in ((960, 600), (420, 900)):
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            state = Path(folder)
            (state / 'sound.txt').write_text('off\n')
            (state / 'guide-seen.txt').write_text('yes\n')
            # Picture Book was opened by an earlier version: only its folder is left.
            (state / 'games/jungle.book').mkdir(parents=True)
            awards = state / 'awards.txt'
            with rt.Desktop(binary, state, extra_env={'TMPDIR': str(state)}, screen_size='1400x2500') as d:
                assert awards.read_text() == 'JUNGLE AWARDS 1\naward-picture-book\n', awards.read_text()
                d.resize(width, height)
                d.key('Home')
                box = badge_box(width, height)
                # Treehouse item 1 is Shapes & Sorting: its first opening unlocks it.
                d.key('1')
                deadline = time.monotonic() + 3
                while 'award-shapes' not in awards.read_text():
                    assert time.monotonic() < deadline, 'opening Shapes & Sorting gave no award'
                    time.sleep(.05)
                assert awards.read_text() == 'JUNGLE AWARDS 1\naward-picture-book\naward-shapes\n', awards.read_text()
                time.sleep(.6)
                shown = gold(d.capture_actual(f'award-shown-{width}x{height}'), box)
                time.sleep(3.2)
                after = gold(d.capture_actual(f'award-after-{width}x{height}'), box)
                assert shown > 1500 and shown > 4 * after + 500, (width, height, shown, after)
                # Back to the treehouse and in again: the award is kept, never given twice.
                d.key('Escape')
                time.sleep(.6)
                d.key('Home')
                d.key('1')
                time.sleep(.9)
                again = gold(d.capture_actual(f'award-again-{width}x{height}'), box)
                assert again < shown / 4, (width, height, shown, again)
                assert awards.read_text() == 'JUNGLE AWARDS 1\naward-picture-book\naward-shapes\n', awards.read_text()
                # The game bar's Collection Book opens on the awards page.
                d.click_actual(width - 106 + 22, 28)
                time.sleep(.8)
                album = d.capture_actual(f'award-album-{width}x{height}')
                # Both earned badges in full color (about 900 rim pixels each); missing ones are faint.
                assert gold(album, (0, 56, width, height)) > 1200, 'the Collection Book lacks the earned awards'
            print(f'local awards smoke test passed at {width}x{height}: badge gold {shown} -> {after}, reopened {again}', flush=True)
    shutil.rmtree(rt.OUTPUT, ignore_errors=True)


if __name__ == '__main__':
    main()

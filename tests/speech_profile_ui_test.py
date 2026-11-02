"""Exercise the narration setting and persistence on an owned private display."""
import argparse
from pathlib import Path
import tempfile
from runtime_test import Desktop, ROOT


def manage(desktop):
    desktop.game('Picture Book')
    desktop.wait_book('speech-profile-books')
    picture = desktop.capture_actual('speech-profile-books-actual')
    width, height = picture.size
    content = height - 56
    padding = max(24, int(14 * min(width / 320, content / 200)) + 12)
    gap = 12 if width < 600 else 20
    footer = height - padding - 48
    button = (width - padding * 2 - gap * 2) / 3
    desktop.click_actual(padding + (button + gap) * 2 + button / 2, footer + 24)
    return padding, gap, button, footer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    binary = parser.parse_args().binary.resolve()
    assert binary != ROOT / 'build/app/jungle', 'use the explicit private test host'
    previous = None
    with tempfile.TemporaryDirectory(dir=ROOT / 'work', prefix='speech-profile-ui-') as folder:
        data = Path(folder)
        for profile, index in [('slow', 0), ('normal', 1), ('fast', 2)]:
            with Desktop(binary, data) as desktop:
                padding, gap, button, footer = manage(desktop)
                if previous is not None:
                    restored = desktop.capture_actual('speech-profile-restored')
                    box = (int(padding), int(footer - 54), restored.width - int(padding), int(footer - 10))
                    assert restored.crop(box).tobytes() == previous.crop(box).tobytes(), 'saved profile was not selected after restart'
                desktop.click_actual(padding + (button + gap) * index + button / 2, footer - 54 + 22)
                assert (data / 'speech-profile.txt').read_text() == profile, profile
                previous = desktop.capture_actual('speech-profile-' + profile)
            # Each fresh app session reads the preceding persistent selection.
            assert (data / 'speech-profile.txt').read_text() == profile
    print('local narration UI test: three choices save across private app sessions')


if __name__ == '__main__':
    main()

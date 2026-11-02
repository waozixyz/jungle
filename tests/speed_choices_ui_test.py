"""Book speed icons cycle on the real host, in each locale and phone/desktop layout."""
import os
import tempfile
from pathlib import Path
from PIL import ImageChops
from runtime_test import Desktop, ROOT, run


def different(a, b):
    return ImageChops.difference(a, b).getbbox() is not None


work = ROOT / 'work/speed-choices-tests'
work.mkdir(parents=True, exist_ok=True)
binary = Path(os.environ.get('JUNGLE_TEST_BINARY', ROOT / 'build/app/jungle'))
for language in ('en', 'de', 'es'):
    with tempfile.TemporaryDirectory(dir=work) as temporary:
        data = Path(temporary)
        (data / 'language.txt').write_text(language)
        with Desktop(binary, data) as desktop:
            for game in ('Picture Book', 'ABC Book', '123 Book'):
                desktop.game(game)
                if game == 'Picture Book':
                    desktop.key('1')
                for width, height in ((960, 600), (390, 844), (320, 568)):
                    desktop.resize(width, height)
                    # Normal -> Fast -> Slow -> Normal; only the current icon is visible.
                    icons = []
                    for at in range(4):
                        run(['xdotool', 'mousemove', '--window', desktop.window,
                             str(width // 2), str(height - 5)], desktop.env)
                        picture = desktop.capture_actual(f'speed-{language}-{game}-{width}-{at}')
                        icon = picture.crop((width - 123, 12, width - 91, 44))
                        ink = sum(1 for r, g, b in (icon.get_flattened_data() if hasattr(icon, 'get_flattened_data') else icon.getdata()) if g < 150 and r < 100)
                        assert ink > 70, ('Missing speed icon', language, game, width, at, ink)
                        icons.append(icon)
                        if at < 3:
                            desktop.click_actual(width - 106, 28)
                    assert all(different(icons[a], icons[b]) for a, b in ((0, 1), (1, 2), (0, 2))), 'Speed choices are indistinguishable'
                    assert not different(icons[0], icons[3]), 'Speed did not wrap back to Normal'
                    # A localized hover hint appears outside the icon-only button.
                    run(['xdotool', 'mousemove', '--window', desktop.window,
                         str(width - 106), '28'], desktop.env)
                    hint = desktop.capture_actual(f'speed-hint-{language}-{game}-{width}')
                    assert different(picture.crop((width - 214, 56, width - 62, 82)),
                                     hint.crop((width - 214, 56, width - 62, 82))), 'Speed tooltip missing'
                desktop.key('Escape')
                if game == 'Picture Book':
                    desktop.key('Escape')
print('local speed UI test: all 3 icons cycle and wrap in all 3 books, EN/DE/ES, desktop/phone/narrow-phone; hover hints passed')

"""An actively playing learning page survives a collection visit, then continues playing."""
import tempfile
import time
from pathlib import Path
from PIL import ImageChops
import runtime_test
from runtime_test import ROOT, Desktop, run

work = ROOT / 'work/collection-book-tests'
work.mkdir(parents=True, exist_ok=True)
runtime_test.OUTPUT = work / 'autoplay-captures'
for width, height in ((960, 600), (320, 568)):
    with tempfile.TemporaryDirectory(dir=work) as directory:
        data = Path(directory)
        (data / 'guide-seen.txt').write_text('yes')
        with Desktop(ROOT / 'build/app/jungle', data) as d:
            d.game('123 Book')
            d.resize(width, height)
            d.key('1')
            run(['xdotool', 'mousemove', '--window', d.window, str(width // 2), '2'], d.env)
            before = d.capture_actual('active-before')
            d.click_actual(width - 178, 28)
            time.sleep(4)
            d.click_actual(28, 28)
            run(['xdotool', 'mousemove', '--window', d.window, str(width // 2), '2'], d.env)
            after = d.capture_actual('active-return')
            assert ImageChops.difference(before.crop((0, 58, width, height)), after.crop((0, 58, width, height))).getbbox() is None, 'Active number page changed during collection visit'
            time.sleep(5)
            resumed = d.capture_actual('active-resumed')
            assert ImageChops.difference(after.crop((0, 58, width, height)), resumed.crop((0, 58, width, height))).getbbox(), 'Autoplay stopped after returning'
print('local collection autoplay UI test passed: same active number returns after four-second album visit, then autoplay continues; desktop + narrow phone')

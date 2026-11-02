"""Private landscape proof that the relocated Peekaboo entry opens Hide & Seek."""
import json
import os
from pathlib import Path
import tempfile
import time

from PIL import Image, ImageChops, ImageStat

import runtime_test
from runtime_test import Desktop, ROOT
from title_waterfront_ui_test import DATA, assert_scene, mapping, move, point


def difference(left, right):
    area = (20, 80, left.width-20, left.height-30)
    return max(ImageStat.Stat(ImageChops.difference(
        left.crop(area), right.crop(area))).mean)


def main():
    work = ROOT/'work/title-peekaboo'
    work.mkdir(parents=True, exist_ok=True)
    runtime_test.OUTPUT = Path(os.environ.get('JUNGLE_TEST_OUTPUT', work/'captures'))
    runtime_test.OUTPUT.mkdir(exist_ok=True)
    binary = Path(os.environ.get('JUNGLE_TEST_BINARY', ROOT/'build/app/jungle'))
    with tempfile.TemporaryDirectory(prefix='ui-', dir=work) as temporary:
        with Desktop(binary, Path(temporary), screen_size='1280x1100') as desktop:
            desktop.resize(960, 600)
            desktop.key('Home')
            home = DATA['scenes'][0]
            desktop.key(str(next(index + 1 for index, hotspot in enumerate(home['hotspots'])
                                       if hotspot['target'] == 'scene:campus')))
            campus, resting = assert_scene(desktop, 'campus', 960, 600)
            hotspot = next(h for h in campus['hotspots'] if h['id'] == 'hiding-bush')
            scale, offset_x, offset_y = mapping(campus, 960, 600)
            x, y, width, height = hotspot['glow_rect']
            area = (max(0, round(offset_x + x*scale)), max(65, round(offset_y + y*scale)),
                    min(960, round(offset_x + (x+width)*scale)),
                    min(600, round(offset_y + (y+height)*scale)))
            tap_x, tap_y = point(campus, 'hiding-bush', 960, 600)
            move(desktop, tap_x, tap_y)
            hovered = desktop.capture_actual('peekaboo-hover-960')
            signal = max(ImageStat.Stat(ImageChops.difference(
                resting.crop(area), hovered.crop(area))).mean)
            assert signal > .5, ('Peekaboo hover missing', signal, area)
            desktop.click_actual(tap_x, tap_y)
            time.sleep(1.0)
            opened = desktop.capture_actual('peekaboo-hide-seek-960')
            assert difference(resting, opened) > 20, 'Hide & Seek did not open'
            desktop.key('Escape')
            time.sleep(.7)
            returned = desktop.capture_actual('peekaboo-return-960')
            assert difference(resting, returned) < 12, 'Back did not restore campus'
            receipt = {
                'hotspot': hotspot['id'],
                'target': hotspot['target'],
                'source_glow_rect': hotspot['glow_rect'],
                'screen_tap': [tap_x, tap_y],
                'hover_signal': signal,
                'captures': [str((runtime_test.OUTPUT/name).relative_to(ROOT)) for name in (
                    'peekaboo-hover-960.png', 'peekaboo-hide-seek-960.png',
                    'peekaboo-return-960.png')],
            }
            (work/'evidence.json').write_text(json.dumps(receipt, indent=2)+'\n')
            print('local Peekaboo UI: 960x600 hover, Hide & Seek click and Back passed', flush=True)


if __name__ == '__main__':
    main()

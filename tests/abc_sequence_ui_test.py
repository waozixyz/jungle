"""The real ABC bundle speaks letters first, advances gently and opens optional examples."""
import tempfile
import time
from pathlib import Path
from PIL import ImageChops
from runtime_test import Desktop, ROOT, OUTPUT, run


def layout(width, height):
    height -= 56
    fit = min(width / 320, height / 200)
    pad = max(24, int(14 * fit) + 8)
    gap = 8 if width < 600 else 16
    control = 32 if height < 400 else 40
    return pad, gap, control


def vivid(picture):
    pixels = picture.get_flattened_data() if hasattr(picture, 'get_flattened_data') else picture.getdata()
    return sum(1 for r,g,b in pixels if max(r,g,b)-min(r,g,b)>65 and min(r,g,b)<160)


for language in ('en', 'de', 'es'):
    with tempfile.TemporaryDirectory(prefix='jungle-alphabet-') as temporary:
        data = Path(temporary)
        (data / 'language.txt').write_text(language)
        with Desktop(ROOT / 'build/app/jungle', data, screen_size='1800x1200') as desktop:
            run(['xdotool','windowmove',desktop.window,'0','0'],desktop.env)
            desktop.resize(960,600)
            desktop.key('2'); desktop.key('1')
            a = desktop.capture_actual('alphabet-sequence-a-' + language)
            region = (100,160,860,380)
            assert vivid(a.crop(region)) < 100, 'Alphabet default still shows a word example'
            time.sleep(4.8)
            automatic = desktop.capture_actual('alphabet-sequence-b-' + language)
            assert ImageChops.difference(a.crop(region), automatic.crop(region)).getbbox(), 'The spoken sequence did not advance'
            desktop.key('b')  # Manual selection pauses the sequence.
            selected = desktop.capture_actual('alphabet-selected-b-' + language)
            assert ImageChops.difference(selected.crop(region), automatic.crop(region)).getbbox() is None, 'The sequence skipped B'
            time.sleep(4.5)
            paused = desktop.capture_actual('alphabet-paused-' + language)
            assert ImageChops.difference(selected, paused).getbbox() is None, 'Manual exploration did not pause the sequence'
            desktop.key('a')
            for width,height in ((1284,834),(390,844),(844,390),(320,568)):
                desktop.resize(width,height)
                standalone = desktop.capture_actual(f'alphabet-letters-{language}-{width}')
                assert standalone.size == (width,height)
                pad,gap,control = layout(width,height)
                desktop.click_actual(width//2,56+pad+control//2)
                example = desktop.capture_actual(f'alphabet-example-{language}-{width}')
                assert vivid(example.crop((width//2,56+pad+control+gap,width-pad,height-pad))) > 100, 'Example did not render on the right'
                desktop.click_actual(width//4,56+pad+control//2)
                desktop.key('space')  # Pause after returning to standalone letters.
                plain = desktop.capture_actual(f'alphabet-return-{language}-{width}')
                assert vivid(plain.crop((pad,56+pad,width-pad,height-pad))) < 100, 'Letters mode retained an example'
                # The final language-specific letter must be present and
                # selectable in every layout, including short landscape.
                count = 30 if language == 'de' else 27 if language == 'es' else 26
                columns = min(15,max(5,(width-pad*2)//42))
                rows = (count+columns-1)//columns
                columns = (count+rows-1)//rows
                cell = (width-pad*2-(columns-1)*6)//columns
                cell_height = 24 if height-56<400 else 30 if width<360 else 42
                strip = height-56-pad-(rows*(cell_height+6)-6)
                last = count-1
                desktop.click_actual(pad+(last%columns)*(cell+6)+cell//2,56+strip+(last//columns)*(cell_height+6)+cell_height//2)
                final = desktop.capture_actual(f'alphabet-final-letter-{language}-{width}')
                area=(pad,56+pad+control+gap,width-pad,56+strip-gap-control-gap)
                assert ImageChops.difference(plain.crop(area),final.crop(area)).getbbox(), 'The last alphabet letter was hidden or unreachable'
                desktop.key('a')
            assert 'portable execution failed' not in (OUTPUT / 'jungle.log').read_text()
print('local alphabet UI test: default letters, A–B sequence, pause, optional examples and four responsive layouts passed')

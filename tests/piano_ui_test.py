"""Exercise the fixed piano and song chooser on an owned private Xvfb."""
from pathlib import Path
import tempfile
import time
from runtime_test import Desktop, ROOT, run

GREEN = (46, 105, 86)


def layout(width, height):
    height -= 56
    pad = max(8, min(28, width // 24, height // 24))
    body_width, body_height = min(width - pad * 2, 1000), min(height - pad * 2, 660)
    left, top = (width - body_width) // 2, (height - body_height) // 2
    rail = max(12, body_width // 30)
    keys_x, keys_width = left + rail, body_width - rail * 2
    keys_height = min(230, body_height * 36 // 100)
    if width < 500 and body_height < 560: keys_height = body_height * 29 // 100
    if body_height < 360: keys_height = body_height * 26 // 100
    keys_y = top + body_height - 22 - keys_height
    controls_height = 30 if body_height < 360 else 40
    controls_width = min(keys_width,620)
    if controls_width < 500: controls_height = controls_height * 2 + 6
    controls_y = keys_y - controls_height - 12
    player_x, player_width = keys_x + 8, keys_width - 16
    player_y = top + 8
    player_height = controls_y - player_y - 12
    lyrics_x, lyrics_width = player_x + 16, player_width - 32
    lyrics_height = 22 if player_height < 180 else 32
    lyrics_y = player_y + player_height - lyrics_height - 9
    guide_x, guide_width = player_x + 16, player_width - 32
    header = (34 if player_height < 180 else 42) + 26
    available = lyrics_y - player_y - header - 6
    gap = max(4, min(14, available // 10, guide_width // 20))
    guide_y = player_y + header + (available - gap * 10) // 2
    key_width = max(36, keys_width // 22)
    return locals()


def target(picture, step=0):
    p = layout(*picture.size)
    tick = step  # first two notes of the default melody are eighths
    unit = (p['guide_width'] - p['gap'] * 8) // 8
    x = p['guide_x'] + p['gap'] * 6 + (tick * 2 + 1) * unit // 2 - p['gap']
    return sum(picture.getpixel((x+dx,y)) == GREEN for dx in (-1,0,1)
               for y in range(56+p['guide_y']+p['gap'],56+p['guide_y']+p['gap']*9)) >= p['gap']*2


def staff_visible(picture):
    p = layout(*picture.size)
    for line in range(5):
        y = 56 + p['guide_y'] + p['gap'] * (2 + line)
        pixels = [picture.getpixel((x, y)) for x in range(p['guide_x'], p['guide_x'] + p['guide_width'])]
        assert pixels.count((168, 155, 129)) > p['guide_width'] * .6, ('Missing staff line', line, picture.size)
    # There is one caption band below the score, never a stack of verses.
    assert p['lyrics_y'] >= p['guide_y'] + p['gap'] * 10
    crop = picture.crop((p['lyrics_x'],56+p['lyrics_y'],p['lyrics_x']+p['lyrics_width'],56+p['lyrics_y']+p['lyrics_height']))
    assert sum(max(c)<155 for c in crop.getdata()) > 10


for language in ('en','de','es'):
    with tempfile.TemporaryDirectory(prefix='jungle-piano-') as temporary:
        data=Path(temporary); (data/'language.txt').write_text(language)
        with Desktop(ROOT/'build/app/jungle', data, screen_size='1280x1100') as desktop:
            desktop.resize(960,600); desktop.game('Little Piano')
            picture=desktop.capture_actual('piano-start-'+language)
            assert target(picture), 'Default practice target is missing'
            p=layout(960,600)
            # A black key above C4 cannot also advance the white C4 underneath.
            desktop.click_actual(p['keys_x']+p['key_width']*8,56+p['keys_y']+20)
            assert target(desktop.capture_actual('piano-black-'+language))
            desktop.key('1'); assert target(desktop.capture_actual('piano-d-'+language),1)
            for width,height in ((390,844),(320,568),(844,390),(960,600)):
                desktop.resize(width,height)
                picture=desktop.capture_actual(f'piano-{language}-{width}-{height}')
                assert target(picture,1), ('Target moved on resize',language,width,height)
                staff_visible(picture)
            p=layout(960,600)
            # Each selected song must leave the physical keyboard unchanged.
            baseline=desktop.capture_actual('piano-before-chooser-'+language)
            for song in range(5):
                desktop.click_actual(480,56+p['player_y']+18)
                chooser=desktop.capture_actual(f'piano-chooser-{language}-{song}')
                assert not target(chooser), 'Song chooser failed to open'
                row=min(64,(p['body_height']-118)//5)
                desktop.click_actual(480,56+p['top']+70+song*row+(row-6)//2)
                selected=desktop.capture_actual(f'piano-song-{language}-{song}')
                staff_visible(selected)
                # Rightmost two octaves are unhighlighted in every song.
                box=(p['keys_x']+p['key_width']*14,56+p['keys_y'],p['keys_x']+p['key_width']*22,56+p['keys_y']+p['keys_height'])
                assert baseline.crop(box).tobytes()==selected.crop(box).tobytes(), 'Song remapped the keyboard'
            desktop.key('Escape'); desktop.game('Little Piano')
            assert target(desktop.capture_actual('piano-reopen-'+language))
            if language == 'en':
                p=layout(960,600)
                desktop.click_actual(370,56+p['controls_y']+20)
                time.sleep(4.0)
                desktop.key('1');desktop.key('2')
                assert target(desktop.capture_actual('piano-lesson-early-release')), 'Early release passed a lesson note'
                run(['xdotool','keydown','1'],desktop.env)
                try:
                    time.sleep(.42)
                    held=desktop.capture_actual('piano-lesson-hold')
                    x=p['player_x']+p['player_width']-22;y=56+p['player_y']+40
                    assert held.getpixel((x,y)) == (181,214,170), 'Hold bar did not fill to the release cue'
                finally:
                    run(['xdotool','keyup','1'],desktop.env)
                assert target(desktop.capture_actual('piano-lesson-released'),1), 'A full keyboard hold/release did not advance'

print('local piano UI test: three languages, four sizes, single caption, five-song selector, fixed keyboard, black-key overlap and practice passed')

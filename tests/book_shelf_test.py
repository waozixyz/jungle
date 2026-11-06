"""Verify book covers and whole illustrations across actual native window sizes."""
from pathlib import Path
import tempfile
import time
import json
from PIL import Image, ImageChops, ImageStat
from runtime_test import Desktop, ROOT

SCENES = json.loads((ROOT / 'tools/title_hotspots.json').read_text())['scenes']
WORK = ROOT / 'work/book-shelf-tests'
WORK.mkdir(parents=True, exist_ok=True)

with tempfile.TemporaryDirectory(prefix='jungle-responsive-', dir=WORK) as directory:
    with Desktop(ROOT / 'build/app/jungle', Path(directory), screen_size='1600x1300') as desktop:
        desktop.capture('responsive-native-menu')
        for mw,mh in [(1280,800),(960,1024),(900,878),(838,878),(390,844),(844,390)]:
            desktop.resize(mw,mh)
            desktop.key('Home')
            menu=desktop.capture_actual(f'menu-painted-bounds-{mw}-{mh}')
            assert menu.size==(mw,mh), 'Window resize did not reach the title viewport'
            # The actual portrait/landscape painting fills the viewport with
            # cover-fit cropping, independently of book-page letterboxing.
            scene=SCENES[0].get('portrait',SCENES[0]) if mh>mw else SCENES[0]
            source=Image.open(ROOT/scene['image']).convert('RGB')
            scale=max(mw/source.width,mh/source.height)
            expected=source.resize((round(source.width*scale),round(source.height*scale)),Image.Resampling.BILINEAR)
            x,y=(expected.width-mw)//2,(expected.height-mh)//2
            expected=expected.crop((x,y,x+mw,y+mh))
            area=(30,120,mw-30,mh-100)
            error=ImageStat.Stat(ImageChops.difference(menu.crop(area),expected.crop(area))).mean
            assert max(error)<12, f'Painted title did not fill {mw}x{mh}: {error}'

        desktop.resize(1280,800)
        desktop.game('Picture Book')
        desktop.wait_book('responsive-native-books')
        # The first opening celebrates the Picture Book award over the game
        # (host/jungle_award_show.zi); let it fly away before comparing pages.
        deadline=time.monotonic()+12
        previous=desktop.capture_actual('responsive-native-books-award')
        while True:
            time.sleep(.5)
            current=desktop.capture_actual('responsive-native-books-award')
            if not ImageChops.difference(previous,current).getbbox(): break
            assert time.monotonic()<deadline, 'The Picture Book award never finished'
            previous=current
        for width,height in [(1280,800),(1000,700),(375,812),(844,390)]:
            desktop.resize(width,height)
            shelf=desktop.capture_actual(f'responsive-native-shelf-{width}')
            assert shelf.size==(width,height), 'Window resize did not reach the game viewport'
            assert shelf.getpixel((0,56))==(227,236,228), 'The responsive book has a black letterbox'
            desktop.key('0')
            first=desktop.capture_actual(f'responsive-native-vegetables-{width}')
            padding=max(24,int(14*min(width/320,(height-56)/200))+12)
            desktop.click_actual(width-padding-28,height-140)
            second=desktop.capture_actual(f'responsive-native-next-{width}')
            assert ImageChops.difference(first,second).getbbox(), 'Next page ignored a resized pointer'
            desktop.click_actual(padding+28,height-140)
            restored=desktop.capture_actual(f'responsive-native-back-{width}')
            assert not ImageChops.difference(first,restored).getbbox(), 'Back did not restore the full picture'
            desktop.key('Escape')
        desktop.resize(375,812)
        for _ in range(8):desktop.click_actual(180,350,button=5)
        bottom=desktop.capture_actual('responsive-native-scroll-bottom')
        assert bottom.size==(375,812)
print('local UI test: desktop and phone-shaped native resizing, whole vegetable pages, navigation and scrolling passed')

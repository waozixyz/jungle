"""Verify book covers and whole illustrations across actual native window sizes."""
from pathlib import Path
import tempfile
import time
from PIL import ImageChops
from runtime_test import Desktop, ROOT

with tempfile.TemporaryDirectory(prefix='jungle-responsive-') as directory:
    with Desktop(ROOT / 'build/app/jungle', Path(directory), screen_size='1600x1300') as desktop:
        desktop.capture('responsive-native-menu')
        for mw,mh in [(1280,800),(960,1024),(390,844),(844,390)]:
            desktop.resize(mw,mh)
            menu=desktop.capture_actual(f'menu-thumbnail-bounds-{mw}')
            fit=min(mw/320,mh/200); portrait=mh>mw
            rh=(int(mh/fit)-164)//3 if portrait else 35
            start=112 if portrait else 67
            left=(mw-320*fit)/2
            gap=menu.crop((round(left+26*fit),round((start+rh-1)*fit),round(left+90*fit),round((start+rh-1)*fit)+1))
            assert all(min(color)>180 and color[0]>=color[1]>=color[2] for _,color in gap.getcolors(100000)), 'Thumbnail overflowed its title-screen row'
        desktop.resize(1280,800)
        desktop.key('1')
        desktop.wait_book('responsive-native-books')
        for width,height in [(1280,800),(1000,700),(375,812),(844,390)]:
            desktop.resize(width,height)
            shelf=desktop.capture_actual(f'responsive-native-shelf-{width}')
            assert shelf.size==(width,height), 'Window resize did not reach the game viewport'
            assert shelf.getpixel((0,0))==(227,236,228), 'The responsive book has a black letterbox'
            desktop.key('0')
            first=desktop.capture_actual(f'responsive-native-vegetables-{width}')
            padding=max(24,int(14*min(width/320,(height-56)/200))+12)
            desktop.click_actual(width-padding-28,height-padding-24)
            second=desktop.capture_actual(f'responsive-native-next-{width}')
            assert ImageChops.difference(first,second).getbbox(), 'Next page ignored a resized pointer'
            desktop.click_actual(padding+28,height-padding-24)
            restored=desktop.capture_actual(f'responsive-native-back-{width}')
            assert not ImageChops.difference(first,restored).getbbox(), 'Back did not restore the full picture'
            desktop.key('Escape')
        desktop.resize(375,812)
        for _ in range(8):desktop.click_actual(180,350,button=5)
        bottom=desktop.capture_actual('responsive-native-scroll-bottom')
        assert bottom.size==(375,812)
print('local UI test: desktop and phone-shaped native resizing, whole vegetable pages, navigation and scrolling passed')

#!/usr/bin/env python3
"""Export the generated brand artwork into platform icon formats."""
from pathlib import Path
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]


def main():
    source = Image.open(ROOT / 'art/generated/branding/app-icon.png').convert('RGB')
    assert source.width == source.height
    icons = ROOT / 'assets/jungle/icons'
    icons.mkdir(parents=True, exist_ok=True)
    for size in (16, 32, 48, 64, 128, 180, 192, 256, 512, 1024):
        source.resize((size,size), Image.Resampling.LANCZOS).save(icons / f'icon-{size}.png', optimize=True)
    source.resize((64,64), Image.Resampling.LANCZOS).save(ROOT / 'assets/jungle/icon.png', optimize=True)
    source.resize((256,256), Image.Resampling.LANCZOS).save(icons / 'window.bmp')
    source.resize((256,256), Image.Resampling.LANCZOS).save(icons / 'favicon.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
    background = source.getpixel((0,0))
    maskable = Image.new('RGB',(512,512),background)
    maskable.paste(source.resize((400,400), Image.Resampling.LANCZOS),(56,56))
    maskable.save(icons / 'maskable-512.png', optimize=True)
    res = ROOT / 'droid/app/src/main/res'
    for density, size in (('mdpi',48),('hdpi',72),('xhdpi',96),('xxhdpi',144),('xxxhdpi',192)):
        folder = res / ('mipmap-' + density)
        folder.mkdir(parents=True, exist_ok=True)
        source.resize((size,size), Image.Resampling.LANCZOS).save(folder / 'ic_launcher.png', optimize=True)
    foreground = Image.new('RGBA',(432,432))
    foreground.paste(source.resize((260,260), Image.Resampling.LANCZOS),(86,86))
    folder = res / 'drawable-nodpi'
    folder.mkdir(parents=True, exist_ok=True)
    foreground.save(folder / 'ic_launcher_foreground.png', optimize=True)
    values = res / 'values'
    values.mkdir(parents=True, exist_ok=True)
    color = '#' + ''.join(f'{c:02x}' for c in background)
    (values / 'launcher_colors.xml').write_text(f'<?xml version="1.0" encoding="utf-8"?>\n<resources><color name="launcher_background">{color}</color></resources>\n')
    adaptive = res / 'mipmap-anydpi-v26'
    adaptive.mkdir(parents=True, exist_ok=True)
    (adaptive / 'ic_launcher.xml').write_text('''<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/launcher_background" />
    <foreground android:drawable="@drawable/ic_launcher_foreground" />
</adaptive-icon>
''')
    logo = ROOT / 'art/generated/branding/logo.png'
    if logo.exists():
        target = ROOT / 'assets/jungle/branding'
        target.mkdir(parents=True, exist_ok=True)
        with Image.open(logo) as image:
            image.thumbnail((1200,600), Image.Resampling.LANCZOS)
            image.save(target / 'logo.png', optimize=True)
    print('Exported website, desktop and Android brand icons')


if __name__ == '__main__': main()

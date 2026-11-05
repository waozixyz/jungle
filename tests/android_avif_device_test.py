"""Render the actual Android AVIF app on the USB Moto with disposable storage.

Build with tools/build_android.py --abi armeabi-v7a --device-test first.
The test never updates or clears the owner's xyz.waozi.jungle installation.
"""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
import zipfile

from PIL import Image, ImageChops, ImageStat
from runtime_test import ROOT, title_keys
sys.path.insert(0, str(ROOT/'tools'))
from book_catalog import WORDS
from web_images import PREVIEW_FOLDERS, PREVIEW_ROOT

SERIAL = 'ZE2223BQZT'
PACKAGE = 'xyz.waozi.jungle.aviftest'
OWNER_PACKAGE = 'xyz.waozi.jungle'
OUTPUT = ROOT/'local/art-development/avif-migration/moto'


def adb(*args, check=True, timeout=60):
    return subprocess.run(['adb', '-s', SERIAL, *args], check=check,
                          capture_output=True, text=True, timeout=timeout)


def shell(*args, **kwargs):
    return adb('shell', shlex.join(args), **kwargs)


def owner_install():
    paths = shell('pm', 'path', OWNER_PACKAGE).stdout.strip()
    package = shell('dumpsys', 'package', OWNER_PACKAGE).stdout
    identity = [row.strip() for row in package.splitlines()
                if re.match(r'\s*(versionCode=|versionName=|lastUpdateTime=)', row)]
    return {'paths': paths, 'identity': identity}


def focused():
    return any(PACKAGE+'/' in row for row in shell('dumpsys', 'window', 'windows').stdout.splitlines()
               if 'mCurrentFocus=' in row)


def awake():
    return 'mWakefulness=Awake' in shell('dumpsys', 'power').stdout


def capture(name):
    assert focused(), 'The test app is not focused; no phone pixels captured'
    path = OUTPUT/(name+'.png')
    with path.open('wb') as stream:
        subprocess.run(['adb', '-s', SERIAL, 'exec-out', 'screencap', '-p'],
                       stdout=stream, check=True, timeout=30)
    with Image.open(path) as image:
        return image.convert('RGB')


def key(name):
    # MOVE_HOME is the app's Home key, never Android's system HOME button.
    code = {'Home': 122, 'Escape': 111, 'Return': 66, 'space': 62}.get(name)
    if code is None:
        code = 7+int(name)
    shell('input', 'keyevent', str(code))
    time.sleep(.4)


def wait_words(name, expected):
    deadline = time.monotonic()+60
    text = ''
    while time.monotonic() < deadline:
        picture = capture(name)
        text = subprocess.run(['tesseract', str(OUTPUT/(name+'.png')), 'stdout'],
                              capture_output=True, text=True, check=True).stdout
        if any(word.casefold() in text.casefold() for word in expected):
            assert max(ImageStat.Stat(picture).stddev) > 25, 'Missing painted artwork'
            return picture
        time.sleep(.5)
    raise AssertionError((name, expected, text))


def app_body(picture):
    """Find Jungle's title bar below Android's status/navigation insets."""
    pixels = picture.load()
    for y in range(picture.height//2):
        xs = [x for x in range(picture.width) if pixels[x, y] == (227, 236, 228)]
        if len(xs) > picture.width//2:
            left, right = xs[0], xs[-1]+1
            bottom = y
            while bottom < picture.height and pixels[left+2, bottom] == (227, 236, 228):
                bottom += 1
            # TitleBar's bottom rule is a separate colour from its fill.
            rule = pixels[left+2, bottom]
            while bottom < picture.height and pixels[left+2, bottom] == rule:
                bottom += 1
            # The app reaches the bottom in portrait, and the navigation bar
            # is outside [left,right) in landscape on this USB Moto.
            return picture.crop((left, bottom, right, picture.height))
    raise AssertionError('Missing Jungle title bar in own focused phone capture')


def wait_book_painting():
    deadline = time.monotonic()+60
    error = None
    while time.monotonic() < deadline:
        picture = capture('book-page')
        # Read the caption alone; a painted background can hide its large
        # word from whole-screen OCR even while the page is fully rendered.
        label = OUTPUT/'book-label.png'
        picture.crop((picture.width//4, picture.height*2//3,
                      picture.width*3//4, picture.height*5//6)).save(label)
        text = subprocess.run(['tesseract', str(label), 'stdout', '--psm', '7'],
                              capture_output=True, text=True, check=True).stdout
        for name, translations in WORDS.items():
            path = ROOT/f'assets/jungle-book/pages/{name}.avif'
            if not path.exists() or not re.search(r'\b'+re.escape(translations[0])+r'\b', text, re.I):
                continue
            body = app_body(picture)
            edge = min(body.size)
            left, top = (body.width-edge)//2, (body.height-edge)//2
            region = (edge//10, edge//10, edge*9//10, edge//2)
            with Image.open(path) as source:
                expected = source.convert('RGB').resize((edge, edge), Image.Resampling.BILINEAR).crop(region)
            # Android's scaled logical viewport can round its center by one
            # physical pixel. Keep the pixel threshold and source unchanged.
            error = min(max(ImageStat.Stat(ImageChops.difference(expected, body.crop((
                left+region[0]+dx, top+region[1]+dy,
                left+region[2]+dx, top+region[3]+dy)))).mean)
                for dx in (-1, 0, 1) for dy in (-1, 0, 1))
            if error < 12:
                print(f'local Moto AVIF book: {name} source pixels rendered, mean channel error {error:.2f}', flush=True)
                return picture, error
        time.sleep(.5)
    raise AssertionError(('Book word appeared but its AVIF painting did not match', error))


def wait_counting_art():
    deadline = time.monotonic()+60
    while time.monotonic() < deadline:
        picture = capture('counting-art')
        body = app_body(picture)
        # CountingView's animal group alone, excluding its title/keypad.
        portrait = body.height > body.width
        height, y, width, group_height = (540, 64, 280, 236) if portrait else (200, 55, 190, 100)
        scale = min(body.width/320, body.height/height)
        left, top = (body.width-320*scale)/2, (body.height-height*scale)/2
        box = tuple(round(v) for v in (left+20*scale, top+y*scale,
                                      left+(20+width)*scale, top+(y+group_height)*scale))
        group = body.crop(box).resize((200, 120))
        vivid = sum(max(pixel)-min(pixel)>45 and min(pixel)<210 for pixel in group.get_flattened_data())
        if vivid > 100:
            return picture, vivid
        time.sleep(.5)
    raise AssertionError('Counting lesson appeared without painted AVIF animal cutouts')


def log_diagnostics(apk, path):
    """Distinguish a staged optional-preview miss from an AVIF failure."""
    failures, loaded, uploads = [], {}, []
    with path.open() as log:
        for index, line in enumerate(log):
            match = re.search(r'FILEIO: \[([^]]+\.avif)\] File loaded successfully', line)
            if match:
                loaded[match[1]] = index
            match = re.search(r'TEXTURE: .*Texture loaded successfully \((\d+)x(\d+) \| R8G8B8A8', line)
            if match:
                uploads.append((index, (int(match[1]), int(match[2]))))
            if re.search(r'FATAL EXCEPTION|Fatal signal|cannot run natively|\bANR\b|avif.*(?:failed|error)', line, re.I):
                failures.append((index, line.strip()))
    expected, unexpected = [], []
    with zipfile.ZipFile(apk) as package:
        aliases = {}
        with package.open('assets/assets/shared-assets.txt') as manifest:
            for raw in manifest:
                fields = raw.decode().strip().split('|')
                if len(fields) == 3 and fields[0] == 'alias':
                    aliases[fields[1]] = fields[2]
        for index, line in failures:
            match = re.search(r'FILEIO: \[(assets/previews/animal-count/pictures/[^/]+\.avif)\] Failed to open file$', line)
            if match:
                preview = match[1]
                logical = 'assets/'+preview[len(PREVIEW_ROOT):]
                target = aliases.get(logical, logical)
                try:
                    package.getinfo('assets/'+preview)
                    absent = False
                except KeyError:
                    absent = True
                if absent and str(Path(logical).parent) not in PREVIEW_FOLDERS:
                    with package.open('assets/'+target) as stream, Image.open(stream) as full:
                        size = full.size
                        small_avif = full.format == 'AVIF' and max(size) <= 128
                    if (small_avif and loaded.get(target, index+1) < index
                            and any(at > index and dimensions == size for at, dimensions in uploads)):
                        expected.append({'preview': preview, 'full_asset': target,
                                         'full_dimensions': list(size),
                                         'reason': 'No preview is staged for this already-small full AVIF; full load/upload and counting pixels passed'})
                        continue
            unexpected.append(line)
    return unexpected, expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path,
                        default=ROOT/'build/android/JungleAcademy-armeabi-v7a-aviftest-debug.apk')
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    assert adb('get-state').stdout.strip() == 'device'
    assert shell('getprop', 'ro.product.cpu.abi').stdout.strip() == 'armeabi-v7a'
    assert not shell('pm', 'path', PACKAGE, check=False).stdout.strip(), 'A different device test already owns this package'
    tools = Path.home()/'Android/Sdk/build-tools/36.0.0'
    badging = subprocess.check_output([str(tools/'aapt'), 'dump', 'badging', str(args.apk)], text=True)
    assert "package: name='"+PACKAGE+"'" in badging, 'Only the disposable test APK is accepted'
    before = owner_install()
    was_awake = awake()
    installed = False
    pid = None
    launch = {'started_at': time.time(), 'screen_was_awake': was_awake}
    (OUTPUT/'launch.json').write_text(json.dumps(launch, indent=2)+'\n')
    try:
        result = adb('install', str(args.apk), timeout=180)
        assert 'Success' in result.stdout, result.stdout
        installed = True
        state = {'sound.txt': 'off\n', 'guide-seen.txt': 'yes\n', 'language.txt': 'en\n'}
        awards = json.loads((ROOT/'tools/art_provenance/game-awards.json').read_text())['awards']
        state['awards.txt'] = 'JUNGLE AWARDS 1\n'+'\n'.join(row['award'] for row in awards)+'\n'
        shell('run-as', PACKAGE, 'mkdir', '-p', 'files/jungle')
        for name, text in state.items():
            script = 'cat > '+shlex.quote('files/jungle/'+name)
            subprocess.run(['adb', '-s', SERIAL, 'shell', shlex.join(['run-as', PACKAGE, 'sh', '-c', script])],
                           input=text, text=True, check=True, capture_output=True, timeout=30)
        # AM's -W waits for a drawn window indefinitely behind a sleeping
        # phone's keyguard. Wake first, then observe our PID and painting
        # independently so even a failed launch leaves the correct diagnostics.
        shell('input', 'keyevent', 'KEYCODE_WAKEUP')
        shell('wm', 'dismiss-keyguard')
        assert awake(), 'USB Moto did not wake for its disposable app test'
        result = shell('am', 'start', '-n', PACKAGE+'/xyz.waozi.jungle.MainActivity')
        launch['activity_start'] = result.stdout
        deadline = time.monotonic()+30
        while time.monotonic() < deadline:
            pid = shell('pidof', PACKAGE, check=False).stdout.strip()
            if pid:
                break
            time.sleep(.2)
        assert pid.isdigit(), 'Android process did not start'
        launch['pid'] = pid
        launch['pid_seen_at'] = time.time()
        (OUTPUT/'launch.json').write_text(json.dumps(launch, indent=2)+'\n')
        deadline = time.monotonic()+30
        while not focused() and time.monotonic() < deadline:
            time.sleep(.3)
        assert focused(), 'Disposable app could not gain focus (check phone keyguard)'
        deadline = time.monotonic()+60
        while True:
            menu = capture('title')
            content = menu.crop((0, menu.height//5, menu.width, menu.height*4//5))
            if max(ImageStat.Stat(content).stddev) > 25:
                break
            assert time.monotonic() < deadline, 'Android title painting never appeared'
            time.sleep(.5)
        for name in title_keys('Picture Book'):
            key(name)
        wait_words('picture-book', ('Picture Book',))
        key('Return')
        key('space')  # Stabilize the page while its asynchronous painting loads.
        page, book_error = wait_book_painting()
        assert sorted(page.size) == sorted(menu.size), 'Physical screen size changed beyond supported rotation'
        for _ in range(3):
            key('Escape')
        for name in title_keys('Animal Counting'):
            key(name)
        wait_words('counting', ('Animal Counting',))
        key('1')
        counting, cutout_pixels = wait_counting_art()
        pid = shell('pidof', PACKAGE).stdout.strip()
        assert pid.isdigit(), 'Android process exited'
        receipt = {'serial': SERIAL, 'abi': 'armeabi-v7a',
                   'android': shell('getprop', 'ro.build.version.release').stdout.strip(),
                   'package': PACKAGE, 'screen': list(menu.size),
                   'capture_sizes': {'title': list(menu.size), 'book-page': list(page.size),
                                     'counting-art': list(counting.size)},
                   'book_max_channel_mean_error': book_error,
                   'counting_cutout_vivid_pixels': cutout_pixels,
                   'captures': ['title', 'picture-book', 'book-page', 'counting', 'counting-art']}
    finally:
        try:
            pid = pid or shell('pidof', PACKAGE, check=False).stdout.strip()
            if pid:
                launch['pid'] = pid
                with (OUTPUT/'app.log').open('w') as log:
                    subprocess.run(['adb', '-s', SERIAL, 'logcat', '-d', '--pid='+pid,
                                    '-b', 'main', '-b', 'system', '-b', 'crash', '-v', 'threadtime'],
                                   stdout=log, check=True, timeout=30)
            launch['ended_at'] = time.time()
            launch['screen_awake_at_cleanup'] = awake()
            (OUTPUT/'launch.json').write_text(json.dumps(launch, indent=2)+'\n')
        finally:
            if installed:
                # Only the app installed by this invocation is stopped and removed.
                shell('am', 'force-stop', PACKAGE)
                assert 'Success' in adb('uninstall', PACKAGE).stdout
            assert owner_install() == before, 'The owner app installation changed'
            removed = not shell('pm', 'path', PACKAGE, check=False).stdout.strip()
            (OUTPUT/'cleanup-verification.json').write_text(json.dumps({
                'read_at': time.time(), 'serial': SERIAL, 'test_package_removed': removed,
                'normal_install_identity': before['identity'], 'owner_install_preserved': True,
            }, indent=2)+'\n')
            if not was_awake:
                shell('input', 'keyevent', 'KEYCODE_SLEEP')
            assert removed, 'Disposable app was not removed'
    assert not shell('pm', 'path', PACKAGE, check=False).stdout.strip()
    failures, optional_misses = log_diagnostics(args.apk, OUTPUT/'app.log')
    assert not failures, failures[-8:]
    receipt['expected_optional_preview_misses'] = optional_misses
    receipt['owner_install_preserved'] = True
    receipt['test_package_removed'] = True
    (OUTPUT/'result.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print('local Moto AVIF test: Android 9 ARMv7 title, book painting and counting cutouts rendered; owner install preserved; disposable app removed')


if __name__ == '__main__':
    main()

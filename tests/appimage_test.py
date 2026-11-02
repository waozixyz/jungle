#!/usr/bin/env python3
"""Verify the actual AppImage runtime, then exercise its extracted payload privately."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

from runtime_test import ROOT, Desktop, OUTPUT, environment, title_keys

version = (ROOT / 'VERSION').read_text().strip()
image = ROOT / 'build/downloads' / ('jungle-v' + version + '-x86_64.AppImage')
digest = hashlib.sha256()
with image.open('rb') as source:
    for chunk in iter(lambda: source.read(1024 * 1024), b''):
        digest.update(chunk)
assert image.with_suffix('.AppImage.sha256').read_text().split()[0] == digest.hexdigest()
work = ROOT / 'work/appimage-tests'
work.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='jungle-appimage-', dir=work) as temporary:
    folder = Path(temporary)
    data = folder / 'data'
    data.mkdir()
    env = environment()
    env.update(APPIMAGE_EXTRACT_AND_RUN='1', JUNGLE_DATA=str(data), TMPDIR=str(folder))
    subprocess.run([str(image), '--check'], env=env, check=True, timeout=90)
    subprocess.run([str(image), '--appimage-extract'], cwd=folder, env=env, check=True,
                   stdout=subprocess.DEVNULL, timeout=90)
    app = folder / 'squashfs-root/AppRun'
    libraries = folder / 'squashfs-root/usr/lib'
    for name in ('libwebpdemux.so.2', 'libwebp.so.7'):
        assert (libraries / name).is_file(), 'Packaged WebP library is missing: ' + name
    env['JUNGLE_TEST_BINARY'] = str(app)
    subprocess.run(['python3', str(ROOT / 'tests/learning_menu_test.py')], cwd=ROOT, env=env, check=True)
    subprocess.run(['python3', str(ROOT / 'tests/menu_ui_test.py')], cwd=ROOT, env=env, check=True)
    subprocess.run(['python3', str(ROOT / 'tests/jigsaw_ui_test.py')], cwd=ROOT, env=env, check=True)
    with Desktop(app, data, extra_env={'TMPDIR': str(folder)}) as desktop:
        for key in title_keys('Picture Book'):
            desktop.key(key)
        desktop.wait_book('appimage-books')
        desktop.key('Return')
        picture = desktop.capture_actual('appimage-webp-page')
        colors = picture.crop((80,120,picture.width-80,picture.height-100)).resize((250,200)).getcolors(50001)
        assert len(colors or []) > 3000, 'The packaged WebP decoder did not render the book scene'
        loaded_webp = set()
        with Path('/proc/' + str(desktop.app.pid) + '/maps').open() as maps:
            for line in maps:
                if '/libwebp' in line:
                    loaded_webp.add(Path(line.split()[-1]))
        assert any(path.name.startswith('libwebpdemux.so.') for path in loaded_webp)
        assert any(path.name.startswith('libwebp.so.') for path in loaded_webp)
        assert all(path.resolve().is_relative_to(libraries.resolve()) for path in loaded_webp), 'WebP decoding used a host library instead of the AppImage'
        assert 'portable execution failed' not in (OUTPUT / 'jungle.log').read_text()
print('local AppImage test: actual runtime, all bundles, shared learning art, WebP pages and saved pictures passed')

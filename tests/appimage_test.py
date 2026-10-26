#!/usr/bin/env python3
"""Verify the actual AppImage runtime, then exercise its extracted payload privately."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

from runtime_test import ROOT, Desktop, OUTPUT, environment

version = (ROOT / 'VERSION').read_text().strip()
image = ROOT / 'build/downloads' / ('jungle-v' + version + '-x86_64.AppImage')
assert image.with_suffix('.AppImage.sha256').read_text().split()[0] == hashlib.sha256(image.read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix='jungle-appimage-') as temporary:
    folder = Path(temporary)
    data = folder / 'data'
    data.mkdir()
    env = environment()
    env.update(APPIMAGE_EXTRACT_AND_RUN='1', JUNGLE_DATA=str(data))
    subprocess.run([str(image), '--check'], env=env, check=True, timeout=90)
    subprocess.run([str(image), '--appimage-extract'], cwd=folder, env=env, check=True,
                   stdout=subprocess.DEVNULL, timeout=90)
    app = folder / 'squashfs-root/AppRun'
    env['JUNGLE_TEST_BINARY'] = str(app)
    subprocess.run(['python3', str(ROOT / 'tests/learning_menu_test.py')], cwd=ROOT, env=env, check=True)
    with Desktop(app, data) as desktop:
        desktop.key('1')
        desktop.wait_book('appimage-books')
        desktop.key('Return')
        picture = desktop.capture_actual('appimage-jpeg-page')
        colors = picture.crop((80,120,picture.width-80,picture.height-100)).resize((250,200)).getcolors(50001)
        assert len(colors or []) > 3000, 'The packaged JPEG decoder did not render the book scene'
        assert 'portable execution failed' not in (OUTPUT / 'jungle.log').read_text()
print('local AppImage test: actual runtime, all bundles, shared learning art, JPEG pages and saved pictures passed')

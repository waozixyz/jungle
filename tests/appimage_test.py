#!/usr/bin/env python3
"""Verify the actual AppImage runtime, then exercise its extracted payload privately."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

from runtime_test import ROOT, Desktop, environment

version = (ROOT / 'VERSION').read_text().strip()
image = ROOT / 'build/downloads' / ('jungle-v' + version + '-x86_64.AppImage')
digest = hashlib.sha256()
with image.open('rb') as source:
    for chunk in iter(lambda: source.read(1024 * 1024), b''):
        digest.update(chunk)
assert image.with_suffix('.AppImage.sha256').read_text().split()[0] == digest.hexdigest()
work = ROOT / 'local/art-development/appimage-tests'
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
    for name in ('libwebpdemux.so.2', 'libwebp.so.7', 'libkryonavif.so'):
        assert (libraries / name).is_file(), 'Packaged AVIF library is missing: ' + name
    env['JUNGLE_AVIF_SMOKE_OUTPUT'] = str(work / 'smoke')
    subprocess.run(['python3', str(ROOT / 'tests/avif_smoke_test.py'), '--binary', str(app)],
                   cwd=ROOT, env=env, check=True)
    with Desktop(app, data, extra_env={'TMPDIR': str(folder)}) as desktop:
        loaded_avif = set()
        with Path('/proc/' + str(desktop.app.pid) + '/maps').open() as maps:
            for line in maps:
                if '/libkryonavif.so' in line:
                    loaded_avif.add(Path(line.split()[-1]))
        assert loaded_avif, 'The packaged AVIF decoder was not loaded'
        assert all(path.resolve().is_relative_to(libraries.resolve()) for path in loaded_avif), 'AVIF decoding used a host library instead of the AppImage'
print('local AppImage test: actual runtime, all bundles, AVIF pages/cutouts in both orientations and bundled decoder passed')

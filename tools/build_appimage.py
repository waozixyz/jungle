#!/usr/bin/env python3
"""Bundle the desktop app, its games, pictures, voices and runtime libraries."""
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TOOL_URL = 'https://github.com/linuxdeploy/linuxdeploy/releases/download/1-alpha-20251107-1/linuxdeploy-x86_64.AppImage'
TOOL_SHA256 = 'c20cd71e3a4e3b80c3483cef793cda3f4e990aca14014d23c544ca3ce1270b4d'
RUNTIME_URL = 'https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64'
RUNTIME_SHA256 = '2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d'


def main():
    if platform.machine() != 'x86_64':
        raise SystemExit('The Linux AppImage currently targets x86_64.')
    subprocess.run(['make', '-j2', 'all'], cwd=ROOT, check=True)
    tool = ROOT / 'build/tools/linuxdeploy-x86_64.AppImage'
    tool.parent.mkdir(parents=True, exist_ok=True)
    if not tool.exists():
        with urllib.request.urlopen(TOOL_URL, timeout=60) as response:
            tool.write_bytes(response.read())
    assert hashlib.sha256(tool.read_bytes()).hexdigest() == TOOL_SHA256, 'linuxdeploy checksum mismatch'
    tool.chmod(0o755)
    appdir = ROOT / 'build/AppDir'
    if appdir.exists(): shutil.rmtree(appdir)
    payload = appdir / 'usr/lib/jungle'
    shutil.copytree(ROOT / 'build/app', payload)
    bindir = appdir / 'usr/bin'
    bindir.mkdir(parents=True)
    (bindir / 'jungle').symlink_to('../lib/jungle/jungle')
    kryon = Path(subprocess.check_output(['ziran', 'pkg', 'path', 'kryon'], cwd=ROOT, text=True).strip())
    fonts = appdir / 'usr/share/fonts/truetype/jungle'
    fonts.mkdir(parents=True)
    shutil.copy2(kryon / 'assets/fonts/LiberationSans-Regular.ttf', fonts)
    docs = appdir / 'usr/share/doc/jungle'
    docs.mkdir(parents=True)
    shutil.copy2(ROOT / 'LICENSE', docs)
    for license in (kryon / 'assets/fonts').glob('*LICENSE*'):
        shutil.copy2(license, docs / ('font-' + license.name))
    apprun = ROOT / 'packaging/AppRun'
    libraries = subprocess.check_output(['ldconfig', '-p'], text=True)
    pixbuf = next(line.split(' => ')[1] for line in libraries.splitlines()
                  if 'libgdk_pixbuf-2.0.so.0 ' in line and 'x86-64' in line)
    env = os.environ.copy()
    env.update(APPIMAGE_EXTRACT_AND_RUN='1', ARCH='x86_64', VERSION=(ROOT / 'VERSION').read_text().strip(),
               OMP_NUM_THREADS='1')
    # GdkPixbuf is loaded at runtime for JPEG pages; it is not in ldd output.
    subprocess.run([str(tool), '--appdir', str(appdir), '--deploy-deps-only', str(payload / 'jungle'),
                    '--library', pixbuf, '--desktop-file', str(ROOT / 'packaging/xyz.waozi.jungle.desktop'),
                    '--icon-file', str(ROOT / 'assets/jungle/icon.png'), '--icon-filename', 'xyz.waozi.jungle',
                    '--custom-apprun', str(apprun)], env=env, check=True)
    # Keep the distribution copyright notices for each bundled library.
    notices = docs / 'bundled-licenses'
    notices.mkdir()
    for lib in (appdir / 'usr/lib').glob('*.so*'):
        match = subprocess.run(['dpkg-query', '-S', '*/' + lib.name], text=True, capture_output=True)
        for line in match.stdout.splitlines():
            package = line.split(': ')[0].split(':')[0]
            copyright = Path('/usr/share/doc') / package / 'copyright'
            if copyright.is_file(): shutil.copy2(copyright, notices / (package + '.txt'))
    output = ROOT / 'build/downloads' / ('jungle-v' + env['VERSION'] + '-x86_64.AppImage')
    output.parent.mkdir(parents=True, exist_ok=True)
    # Use the packager inside the checksum-pinned linuxdeploy archive so we
    # can bound compression to two workers and pin the runtime as well.
    unpacked = ROOT / 'build/tools/linuxdeploy-extracted'
    packager = unpacked / 'squashfs-root/plugins/linuxdeploy-plugin-appimage/usr/bin/appimagetool'
    if not packager.exists():
        unpacked.mkdir(parents=True, exist_ok=True)
        subprocess.run([str(tool), '--appimage-extract'], cwd=unpacked, env=env,
                       stdout=subprocess.DEVNULL, check=True)
    runtime = ROOT / 'build/tools/runtime-x86_64'
    if not runtime.exists():
        with urllib.request.urlopen(RUNTIME_URL, timeout=60) as response:
            runtime.write_bytes(response.read())
    assert hashlib.sha256(runtime.read_bytes()).hexdigest() == RUNTIME_SHA256, 'AppImage runtime checksum mismatch'
    subprocess.run([str(packager), '--runtime-file', str(runtime),
                    '--mksquashfs-opt=-processors', '--mksquashfs-opt=2',
                    '--mksquashfs-opt=-mem', '--mksquashfs-opt=256M',
                    str(appdir), str(output)], env=env, check=True)
    output.chmod(0o755)
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + '.sha256').write_text(checksum + '  ' + output.name + '\n')
    print('Built ' + str(output.relative_to(ROOT)))


if __name__ == '__main__': main()

#!/usr/bin/env python3
"""Build Jungle Academy's Android APK: the menu host with its games, pictures and sounds."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def package(name):
    flags = [] if (ROOT / 'ziran.local.toml').exists() else ['--locked']
    return Path(subprocess.check_output(['ziran', 'pkg', 'path', name, *flags],
                                        cwd=ROOT, text=True).strip())


def version():
    """VERSION and the matching versionCode, 0.1.3 -> 103."""
    text = (ROOT / 'VERSION').read_text().strip()
    parts = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)', text)
    assert parts, 'VERSION must be MAJOR.MINOR.PATCH'
    major, minor, patch = map(int, parts.groups())
    assert minor < 100 and patch < 100
    return text, major * 10000 + minor * 100 + patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--abi', choices=('arm64-v8a', 'armeabi-v7a', 'universal'), default='arm64-v8a')
    parser.add_argument('--release', action='store_true', help='build the unsigned production APK for signing')
    args = parser.parse_args()
    name, code = version()
    kryon = package('kryon')
    ziran = package('ziran')
    raylib = package('raylib')
    environment = os.environ.copy()
    for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS'):
        environment.pop(key, None)
    # The games and pictures as the desktop installs them, without its program.
    subprocess.run(['make', 'all'], cwd=ROOT, env=environment, check=True)
    staged = ROOT / 'build/android/assets'
    shutil.rmtree(staged, ignore_errors=True)
    staged.mkdir(parents=True)
    for folder in ('assets', 'games'):
        shutil.copytree(ROOT / 'build/app' / folder, staged / folder)
    (ROOT / 'droid/gradle.properties').write_text(
        'org.gradle.daemon=false\norg.gradle.parallel=false\norg.gradle.workers.max=1\n'
        'org.gradle.jvmargs=-Xmx1024m -Dfile.encoding=UTF-8\n')
    environment.update(CMAKE_BUILD_PARALLEL_LEVEL='1', ZIRAN_PAR_THREADS='1', MAKEFLAGS='-j1')
    sdk = Path(environment.get('ANDROID_SDK_ROOT', str(Path.home() / 'Android/Sdk')))
    environment.update(ANDROID_SDK_ROOT=str(sdk), ANDROID_HOME=str(sdk))
    aapt = sdk / 'build-tools/36.0.0/aapt2'
    assert aapt.exists(), 'Install Android build-tools 36.0.0'
    abis = 'arm64-v8a,armeabi-v7a' if args.abi == 'universal' else args.abi
    task = 'assembleRelease' if args.release else 'assembleDebug'
    subprocess.run(['sh', 'droid/gradlew', '-p', 'droid', '--no-daemon', '--max-workers=1', task,
                    '-Pkryon.dir=' + str(kryon), '-Pziran.dir=' + str(ziran), '-Praylib.dir=' + str(raylib / 'src'),
                    '-Papp.abis=' + abis, '-Papp.minSdk=21', '-Papp.codegen=c99',
                    '-Papp.versionCode=' + str(code), '-Papp.versionName=' + name,
                    '-Pandroid.aapt2FromMavenOverride=' + str(aapt)],
                   cwd=ROOT, env=environment, check=True)
    variant = 'release' if args.release else 'debug'
    source = 'app-release-unsigned.apk' if args.release else 'app-debug.apk'
    target = ROOT / 'build/android' / ('JungleAcademy-' + args.abi + ('-release-unsigned.apk' if args.release else '-debug.apk'))
    shutil.copy2(ROOT / 'droid/app/build/outputs/apk' / variant / source, target)
    print('Built ' + str(target))


if __name__ == '__main__':
    main()

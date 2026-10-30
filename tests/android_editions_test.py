#!/usr/bin/env python3
"""Release paths build all three Android editions without shipping stale games."""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import android_release
import build_android
import shared_assets


def stale_package_test():
    with tempfile.TemporaryDirectory(prefix='android-package-') as directory:
        root = Path(directory)
        app = root / 'app'
        (app / 'assets').mkdir(parents=True)
        (app / 'games').mkdir()
        (app / 'jungle').write_bytes(b'executable')
        (app / 'assets/speech.txt').write_text('speech\n')
        (app / 'games/catalog.txt').write_text('one.zx|One|Description|cover|1\ntwo.zx|Two|Description|cover|2\n')
        for name, data in {'one.zx': b'one', 'two.zx': b'two', 'stale.zx': b'stale'}.items():
            (app / 'games' / name).write_bytes(data)
        package = root / 'package'
        assert shared_assets.StageReleaseApp(app, package) == ['one.zx', 'two.zx']
        assert sorted(path.relative_to(package).as_posix() for path in package.rglob('*')) == [
            'assets', 'assets/speech.txt', 'games', 'games/catalog.txt', 'games/one.zx', 'games/two.zx', 'jungle']
        assert (package / 'jungle').read_bytes() == b'executable'
        (package / 'games/stale.zx').write_bytes(b'leaked')
        shared_assets.StageReleaseApp(app, package)
        assert not (package / 'games/stale.zx').exists(), 'fresh staging retained an unregistered game'
        assert (app / 'games/stale.zx').exists(), 'staging deleted another session’s build output'
        shared_assets.StageReleaseApp(app, package, program=False)
        assert not (package / 'jungle').exists(), 'Android staging does not ship the desktop executable'


def build_api_test():
    with tempfile.TemporaryDirectory(prefix='android-build-') as directory:
        root = Path(directory)
        original_root = build_android.ROOT
        original_package = build_android.package
        original_version = build_android.version
        original_run = build_android.subprocess.run
        build_android.ROOT = root
        (root / 'VERSION').write_text('0.1.3\n')
        (root / 'droid').mkdir()
        (root / 'build-tools/36.0.0/aapt2').parent.mkdir(parents=True)
        (root / 'build-tools/36.0.0/aapt2').write_text('')
        app = root / 'build/app'
        (app / 'assets').mkdir(parents=True)
        (app / 'games').mkdir()
        (app / 'jungle').write_bytes(b'host')
        (app / 'games/catalog.txt').write_text('one.zx|One|Description|cover|1\n')
        (app / 'games/one.zx').write_bytes(b'one')
        commands = []

        def package(name):
            return root / (name + '-package')

        def run(command, **_):
            commands.append(command)
            if not any('gradlew' in part for part in command):
                return subprocess.CompletedProcess(command, 0)
            source = root / 'droid/app/build/outputs/apk/release/app-release-unsigned.apk'
            source.parent.mkdir(parents=True, exist_ok=True)
            edition = next(part.removeprefix('-Papp.edition=') for part in command
                           if part.startswith('-Papp.edition='))
            source.write_bytes(('apk-' + edition).encode())
            return subprocess.CompletedProcess(command, 0)

        try:
            build_android.package = package
            build_android.version = lambda: ('0.1.3', 103)
            build_android.subprocess.run = run
            outputs = {edition: build_android.BuildAndroidEdition(edition, 'universal', True)
                       for edition in ('direct', 'fdroid', 'gplay')}
        finally:
            build_android.ROOT = original_root
            build_android.package = original_package
            build_android.version = original_version
            build_android.subprocess.run = original_run

        assert outputs['direct'].name == 'JungleAcademy-universal-release-unsigned.apk'
        assert outputs['fdroid'].name == 'JungleAcademy-universal-fdroid-release-unsigned.apk'
        assert outputs['gplay'].name == 'JungleAcademy-universal-gplay-release-unsigned.apk'
        gradles = {next(part.removeprefix('-Papp.edition=') for part in command
                        if part.startswith('-Papp.edition=')): command
                   for command in commands if any('gradlew' in part for part in command)}
        assert set(gradles) == {'direct', 'fdroid', 'gplay'}
        assert '-Papp.minSdk=21' in gradles['direct']
        assert '-Papp.minSdk=21' in gradles['fdroid']
        assert '-Papp.minSdk=23' in gradles['gplay']
        assert '-Pandroid.useAndroidX=true' in gradles['gplay']
        assert all('-Pandroid.useAndroidX=true' not in gradles[name]
                   for name in ('direct', 'fdroid'))
        assert all('-Papp.abis=arm64-v8a,armeabi-v7a' in command for command in gradles.values())


def release_gate_test():
    assert android_release.OutputName('0.1.3', 'direct') == 'jungle-v0.1.3.apk'
    assert android_release.OutputName('0.1.3', 'fdroid') == 'jungle-v0.1.3-fdroid.apk'
    assert android_release.OutputName('0.1.3', 'gplay') == 'jungle-v0.1.3-gplay.apk'
    workflow = (ROOT / '.github/workflows/android.yml').read_text()
    assert 'libvorbisfile3 ffmpeg python3-pil' in workflow
    assert workflow.count('google-free@5427f011d20ad9a67abd734c6a7985650e9d5bf3') == 2
    assert "expect-google: 'true'" in workflow
    assert 'JungleAcademy-universal-release-unsigned.apk' in workflow
    assert 'JungleAcademy-universal-fdroid-release-unsigned.apk' in workflow
    assert 'JungleAcademy-universal-gplay-release-unsigned.apk' in workflow
    assert 'waozi/jungle:android' in workflow and workflow.count('waozi/jungle:android') == 1
    gradle = (ROOT / 'droid/app/build.gradle').read_text()
    assert "apply from: new File(kryonDir, 'templates/android-gplay.gradle')" in gradle
    assert 'implementation' not in gradle
    cmake = (ROOT / 'droid/app/src/main/cpp/CMakeLists.txt').read_text()
    assert '--define GOOGLE_PLAY' in cmake and '--define FDROID' in cmake
    assert "'--mute-audio'" in (ROOT / 'tests/speech_playback_web_test.mjs').read_text()


stale_package_test()
build_api_test()
release_gate_test()
print('local Android editions test: direct/fdroid/gplay outputs, Google-free gates, signing names and selective staging passed')

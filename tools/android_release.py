#!/usr/bin/env python3
"""Sign and verify Jungle Academy's Android download with the release key.

The key lives only in GitHub secrets; CI writes it to a temporary file, signs
here and publishes the verified APK with the release.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import zipfile

from shared_assets import CatalogGames

ROOT = Path(__file__).resolve().parents[1]


def build_tools():
    sdk = Path(os.environ.get('ANDROID_SDK_ROOT') or os.environ.get('ANDROID_HOME') or Path.home() / 'Android/Sdk')
    tools = sdk / 'build-tools/36.0.0'
    assert all((tools / name).is_file() for name in ('aapt', 'apksigner', 'zipalign'))
    return tools


def OutputName(version, edition):
    """The stable download name; the normal edition keeps its historic name."""
    suffix = '' if edition == 'direct' else '-' + edition
    return f'jungle-v{version}{suffix}.apk'


def verify(apk, edition='direct'):
    version = (ROOT / 'VERSION').read_text().strip()
    major, minor, patch = map(int, version.split('.'))
    tools = build_tools()
    badging = subprocess.check_output([str(tools / 'aapt'), 'dump', 'badging', str(apk)], text=True)
    package = re.search(r"^package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'", badging, re.M)
    assert package and package[1] == 'xyz.waozi.jungle' and package[3] == version
    assert int(package[2]) == major * 10000 + minor * 100 + patch
    assert 'application-debuggable' not in badging, 'A debug APK cannot be released'
    certificate = subprocess.check_output(['openssl', 'x509', '-in', str(ROOT / 'packaging/android/certificate.pem'), '-outform', 'DER'])
    expected = hashlib.sha256(certificate).hexdigest()
    signature = subprocess.check_output([str(tools / 'apksigner'), 'verify', '--verbose', '--print-certs', str(apk)], text=True)
    actual = re.findall(r'^(?:Signer #\d+|V[\d.]+ Signer:) certificate SHA-256 digest: ([0-9a-f]+)$', signature, re.M)
    assert 'Number of signers: 1' in signature and set(actual) == {expected}, 'Unexpected release certificate'
    subprocess.run([str(tools / 'zipalign'), '-c', '-P', '16', '4', str(apk)], check=True, capture_output=True)
    with zipfile.ZipFile(apk) as archive:
        names = archive.namelist()
        abis = sorted(p.split('/')[1] for p in names if re.fullmatch(r'lib/[^/]+/libmain\.so', p))
        assert abis == ['arm64-v8a', 'armeabi-v7a'], 'Both ARM architectures are required'
        assert archive.read('assets/games/catalog.txt') == (ROOT / 'build/app/games/catalog.txt').read_bytes()
        for game in CatalogGames(ROOT / 'build/app'):
            assert archive.read('assets/games/' + game) == (ROOT / 'build/app/games' / game).read_bytes(), game
    return hashlib.sha256(Path(apk).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('sign', 'verify'))
    parser.add_argument('apk', type=Path)
    parser.add_argument('--keystore', type=Path)
    parser.add_argument('--password-file', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/downloads')
    parser.add_argument('--edition', choices=('direct', 'fdroid', 'gplay'), default='direct')
    args = parser.parse_args()
    if args.action == 'verify':
        print(verify(args.apk, args.edition))
        return
    assert args.keystore and args.password_file, 'Signing needs the release keystore and its password file'
    args.output.mkdir(parents=True, exist_ok=True)
    version = (ROOT / 'VERSION').read_text().strip()
    tools = build_tools()
    aligned = args.output / 'aligned-unsigned.apk'
    temporary = args.output / 'jungle.new.apk'
    target = args.output / OutputName(version, args.edition)
    try:
        subprocess.run([str(tools / 'zipalign'), '-P', '16', '-f', '4', str(args.apk.resolve()), str(aligned)], check=True)
        subprocess.run([str(tools / 'apksigner'), 'sign', '--alignment-preserved', '--ks', str(args.keystore.resolve(strict=True)),
                        '--ks-key-alias', 'jungle', '--ks-pass', 'file:' + str(args.password_file.resolve(strict=True)),
                        '--out', str(temporary), str(aligned)], check=True)
        digest = verify(temporary, args.edition)
        temporary.replace(target)
    finally:
        aligned.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
    print(f'Jungle Academy {version} ({args.edition}): {target.name} signed and verified ({digest})')


if __name__ == '__main__':
    main()

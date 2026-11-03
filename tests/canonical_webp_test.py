"""Canonical image migration preserves dimensions, PNGs and recoverable sources."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def main():
    receipt = json.loads((ROOT / 'tools/canonical_webp.json').read_text())
    rows = receipt['files']
    assert len(rows) == 555
    assert sum(row['bytes'] for row in rows.values()) < sum(row['original_bytes'] for row in rows.values())
    approved={r['path']:r for r in json.loads((ROOT/'tests/approved_title_webp.json').read_text())['images']}
    layers=json.loads((ROOT/'tools/title_webp_layers.json').read_text())
    for name, row in rows.items():
        if name in approved:
            assert digest(ROOT/name)==approved[name]['sha256'],name
            continue
        path = ROOT / name
        assert path.suffix == '.webp' and digest(path) == row['sha256'], name
        assert path.stat().st_size == row['bytes'] and row['quality'] == 90, name
        with Image.open(path) as image:
            assert image.format == 'WEBP' and image.mode == 'RGB', name
            assert list(image.size) == row['dimensions'], name
            assert hashlib.sha256(image.tobytes()).hexdigest() == row['pixels_sha256'], name
        original = ROOT / 'backup/jpeg-webp-migration' / row['source']
        if original.exists():
            assert digest(original) == row['original_sha256'], name
    for name, expected in receipt['preserved_png_sha256'].items():
        if name in layers:
            layer=layers[name]
            assert layer['original_sha256']==expected,name
            assert not (ROOT/name).exists(),name
            if not layer.get('retired'):
                assert digest(ROOT/layer['path'])==layer['sha256'],name
                with Image.open(ROOT/layer['path']) as im:
                    assert hashlib.sha256(im.convert('RGBA').tobytes()).hexdigest()==layer['rgba_sha256'],name
        else:
            assert digest(ROOT / name) == expected, 'Canonical PNG changed: ' + name
    for path in (ROOT / 'assets').rglob('*'):
        if not path.is_file():
            continue
        assert path.suffix.lower() not in ('.jpg', '.jpeg'), path
        with path.open('rb') as source:
            assert source.read(3) != b'\xff\xd8\xff', 'JPEG payload under another suffix: ' + str(path)
    # Historical provenance stores the original names; active source and
    # generators must never recreate or request those paths.
    paths = subprocess.check_output(['git', 'ls-files', '-z', 'games', 'host', 'retro', 'web', 'tools']).decode().split('\0')
    for name in paths:
        path = ROOT / name
        if not path.is_file() or path.suffix not in ('.py', '.zi', '.json', '.txt', '.html', '.js'):
            continue
        if name == 'tools/canonical_webp.json' or name.startswith('tools/art_provenance/'):
            continue
        assert not re.search(r'assets/[^\s\"\'<>]*\.jpe?g\b', path.read_text(), re.I), name
    print(f'local canonical image test: {len(rows)} real WebP masters, dimensions/pixel receipts, '
          f"{len(receipt['preserved_png_sha256'])} unchanged PNGs and no active JPEG payloads/references passed")


if __name__ == '__main__':
    main()

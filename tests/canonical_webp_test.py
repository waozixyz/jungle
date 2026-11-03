"""Enforce WebP artwork and verify exact migrations without private masters."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def noncanonical_rasters(names, allowlist):
    return sorted(name for name in names
                  if Path(name).suffix.lower() in ('.png', '.jpg', '.jpeg')
                  and name not in allowlist)


def enforce_standard():
    allowed = json.loads((ROOT / 'tools/asset_png_allowlist.json').read_text())['files']
    assert all(name.startswith('assets/') and not any(c in name for c in '*?[')
               and len(reason.strip()) > 30 for name, reason in allowed.items())
    # Include tracked files and new candidates; omit tracked removals before commit.
    names = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others',
                                     '--exclude-standard', 'assets'], cwd=ROOT).decode().split('\0')
    names = {name for name in names if (ROOT / name).is_file()}
    bad = noncanonical_rasters(names, allowed)
    assert not bad, 'Export artwork via tools/image_exports.py; undocumented PNG/JPEG: ' + ', '.join(bad)
    assert set(allowed) <= names, 'Remove stale PNG allowlist entries'
    # The validator must reject new paths, JPEGs and case variants, including
    # a PNG beside an allowed font. No folder-wide exemptions.
    assert noncanonical_rasters(['assets/new.PNG', 'assets/new.JPEG',
                                 'assets/animal-count/new.png', *allowed], allowed) == [
        'assets/animal-count/new.png', 'assets/new.JPEG', 'assets/new.PNG']


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def main():
    receipt = json.loads((ROOT / 'tools/canonical_webp.json').read_text())
    enforce_standard()
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
    migrated = receipt.get('png_migration', {}).get('files', {})
    migrated_sources = {row['source']: name for name, row in migrated.items()}
    for name, row in migrated.items():
        path = ROOT / name
        # A repainted, re-approved export supersedes its migration receipt.
        if name in approved:
            assert digest(path) == approved[name]['sha256'], name
            continue
        assert path.suffix == '.webp' and digest(path) == row['sha256'], name
        assert not (ROOT / row['source']).exists(), row['source']
        with Image.open(path) as image:
            assert image.format == 'WEBP' and list(image.size) == row['dimensions'], name
            assert hashlib.sha256(image.convert('RGBA').tobytes()).hexdigest() == row['rgba_sha256'], name
        if row['lossless']:
            assert row['rgba_sha256'] == row['original_rgba_sha256'], name
        else:
            assert row['quality'] == 85 and row['role'] == 'scene', name
        assert row['method'] == 6
        original = ROOT / row['master']
        if original.exists():
            assert digest(original) == row['original_sha256'], name
    for name, expected in receipt['preserved_png_sha256'].items():
        if name in migrated_sources:
            assert migrated[migrated_sources[name]]['original_sha256'] == expected, name
            continue
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
    print(f'local canonical image test: {len(rows)} historical WebPs, {len(migrated)} PNG migrations; '
          'WebP standard, exact-path technical PNG allowlist and dimensions/pixel receipts passed')


if __name__ == '__main__':
    main()

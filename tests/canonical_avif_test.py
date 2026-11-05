"""Validate every runtime AVIF against the migration's independent pixel receipts."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def noncanonical_rasters(names, allowlist):
    return sorted(name for name in names
                  if Path(name).suffix.lower() in ('.webp', '.png', '.jpg', '.jpeg')
                  and name not in allowlist)


def enforce_standard():
    allowed = json.loads((ROOT / 'tools/asset_png_allowlist.json').read_text())['files']
    assert all(name.startswith('assets/') and not any(c in name for c in '*?[')
               and len(reason.strip()) > 30 for name, reason in allowed.items())
    names = {p.relative_to(ROOT).as_posix() for p in (ROOT/'assets').rglob('*') if p.is_file()}
    bad = noncanonical_rasters(names, allowed)
    assert not bad, 'Export artwork through tools/image_exports.py: ' + ', '.join(bad)
    assert set(allowed) <= names, 'Remove stale PNG allowlist entries'
    paths = subprocess.check_output(['git','ls-files','-z','games','host','retro','web','tools'],cwd=ROOT).decode().split('\0')
    for name in paths:
        path = ROOT/name
        if not path.is_file() or path.suffix not in ('.py','.zi','.json','.txt','.html','.js'):
            continue
        if name.startswith('tools/art_provenance/') or name in ('tools/canonical_avif.json','tools/migrate_asset_avif.py'):
            continue
        assert not re.search(r'(?<![/\w-])assets/[^\s\"\'<>]*\.webp\b',path.read_text(),re.I), name


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    enforce_standard()
    receipt = json.loads((ROOT/'tools/canonical_avif.json').read_text())
    rows = receipt['files']
    actual = {p.relative_to(ROOT).as_posix() for p in (ROOT/'assets').rglob('*.avif')}
    assert actual == set(rows), (actual-set(rows),set(rows)-actual)
    assert len(rows) == receipt['count']
    assert sum(row['bytes'] for row in rows.values()) == receipt['after_bytes']
    assert sum(row['source_bytes'] for row in rows.values()) == receipt['before_bytes']
    for name, row in rows.items():
        path = ROOT/name
        assert digest(path) == row['sha256'] and path.stat().st_size == row['bytes'], name
        with Image.open(path) as decoded:
            assert decoded.format == 'AVIF' and list(decoded.size) == row['dimensions'], name
            rgba = decoded.convert('RGBA')
            assert hashlib.sha256(rgba.tobytes()).hexdigest() == row['rgba_sha256'], name
            assert hashlib.sha256(rgba.getchannel('A').tobytes()).hexdigest() == row['alpha_sha256'], name
            # Every export is smaller than its source, except AVIF's fixed
            # container overhead on a few sub-kilobyte icons and glows.
            assert row['bytes'] < row['source_bytes'] or row['source_bytes'] < 10000, name
            if row.get('scale'):
                # Owner standard: 75% Lanczos of the design size, AVIF q35;
                # transparent art keeps 4:4:4 color and q90 alpha.
                design = row['design_dimensions']
                assert row['scale'] == 0.75 and row['quality'] == 35 and not row['lossless'], name
                assert row['dimensions'] == [max(1, round(v * .75)) for v in design], name
                assert row['subsampling'] == ('444' if row['alpha'] else '420'), name
                assert row['alpha_quality'] == (90 if row['alpha'] else 100), name
            elif row['lossless']:
                assert not row['alpha'] and row['rgba_sha256'] == row['source_rgba_sha256'], name
            elif row['alpha']:
                # Transparent art: 4:4:4 color, alpha exact unless a tiny soft
                # glow needed near-lossless alpha to beat its WebP.
                assert row['subsampling'] == '444' and 20 <= row['quality'] <= 70, name
                assert row['exact_alpha'] == (row['alpha_quality'] == 100), name
                if row['exact_alpha']:
                    assert row['alpha_sha256'] == row['source_alpha_sha256'], name
            elif name.startswith('assets/jigsaw/') or max(row['dimensions']) <= 64:
                # Jigsaw paintings and small menu icons (role `icon`).
                assert row['quality'] == 60 and row['subsampling'] == '444', name
            else:
                assert row['quality'] in (35, 50) and row['subsampling'] == '420', name
        original = (ROOT/row['source'] if row['source'].startswith('local/') else ROOT/'backup/avif-migration'/row['source'])
        if original.exists():
            assert digest(original) == row['source_sha256'], name
            with Image.open(original) as image:
                shipped = row.get('design_dimensions', row['dimensions'])
                if row['source'].startswith('assets/'):
                    assert list(image.size) == shipped, name
                if list(image.size) != shipped:
                    image = image.resize(shipped, Image.Resampling.LANCZOS)
                assert hashlib.sha256(image.convert('RGBA').getchannel('A').tobytes()).hexdigest() == row['source_alpha_sha256'], name
    allowed = json.loads((ROOT/'tools/asset_png_allowlist.json').read_text())
    assert {p.relative_to(ROOT).as_posix() for p in (ROOT/'droid/app/src/main/res').rglob('*.png')} == set(allowed['android_platform_files'])
    for name, row in receipt['technical_files'].items():
        path = ROOT/name
        assert digest(path) == row['sha256'] and path.stat().st_size == row['bytes'], name
        with Image.open(path) as image:
            assert image.format == row['format'] and list(image.size) == row['dimensions'], name
    print(f'local AVIF asset test: {len(rows)} decodes; dimensions, exact alpha, smaller-than-source, payload receipts and format policy passed')


if __name__ == '__main__':
    main()

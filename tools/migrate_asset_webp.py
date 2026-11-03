"""Migrate legacy painted PNGs once; archive masters and record verifiable exports.

Prepare caches without changing assets; --apply installs and removes old PNGs.
Title artwork belongs to its separate approval/export workflow.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image
from image_exports import ROOT, optimize_new_image_exports

ARCHIVE = ROOT / 'local/art-development/webp-standard'
ALLOWLIST = ROOT / 'tools/asset_png_allowlist.json'
RECEIPT = ROOT / 'tools/canonical_webp.json'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    allowed = json.loads(ALLOWLIST.read_text())['files']
    names = subprocess.check_output(['git', 'ls-files', '-z', 'assets']).decode().split('\0')
    rows = {}
    for name in names:
        source = ROOT / name
        if source.suffix.lower() not in ('.png', '.jpg', '.jpeg') or name in allowed:
            continue
        if name.startswith('assets/jungle/title/') or '/musicians_' in name:
            continue
        if not source.exists():
            continue
        master = ARCHIVE / name
        master.parent.mkdir(parents=True, exist_ok=True)
        if master.exists():
            assert digest(master) == digest(source), name
        else:
            shutil.copyfile(source, master)
        # Preserve all cutout, preview, palette and small icon pixels exactly.
        # Only opaque full-scene paintings use the scene preset (q85/method 6).
        with Image.open(master) as image:
            rgba = image.convert('RGBA')
            role = ('scene' if rgba.getchannel('A').getextrema()[0] == 255
                    and min(image.size) >= 700 else 'exact')
            original_pixels = hashlib.sha256(rgba.tobytes()).hexdigest()
            dimensions = list(image.size)
        export = optimize_new_image_exports(master, role, ARCHIVE / 'cache')
        with Image.open(export.source) as image:
            pixels = hashlib.sha256(image.convert('RGBA').tobytes()).hexdigest()
            assert list(image.size) == dimensions
            if export.lossless:
                assert pixels == original_pixels, name
        destination = source.with_suffix('.webp')
        assert not destination.exists(), destination
        rows[destination.relative_to(ROOT).as_posix()] = {
            'source': name, 'master': master.relative_to(ROOT).as_posix(),
            'original_sha256': digest(master), 'original_bytes': master.stat().st_size,
            'original_rgba_sha256': original_pixels,
            'sha256': digest(export.source), 'bytes': export.source.stat().st_size,
            'dimensions': dimensions, 'rgba_sha256': pixels,
            'role': role, 'quality': export.quality, 'lossless': export.lossless, 'method': 6,
        }
        if args.apply:
            shutil.copyfile(export.source, destination)
            source.unlink()
    if not rows:
        print('No legacy artwork remains to migrate', flush=True)
        return
    if args.apply:
        previous = json.loads(RECEIPT.read_text()).get('png_migration', {}).get('files', {})
        rows = previous | rows
    total = sum(row['original_bytes'] for row in rows.values())
    after = sum(row['bytes'] for row in rows.values())
    result = {'files': rows, 'before_bytes': total, 'after_bytes': after}
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    (ARCHIVE / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    if args.apply:
        receipt = json.loads(RECEIPT.read_text())
        receipt['png_migration'] = result
        receipt['policy'] = ('WebP for generated/painted rasters; q50 title backgrounds, q85 book pages/scenes, '
                             'exact lossless cutouts/layers/palettes. Masters stay in local/art-development/. '
                             'Historical JPEG and PNG names/hashes below are archival provenance, not runtime aliases.')
        RECEIPT.write_text(json.dumps(receipt, indent=2) + '\n')
    print(f'{"Installed" if args.apply else "Prepared"} {len(rows)} WebPs: {total:,} -> {after:,} bytes ({100*(1-after/total):.1f}% smaller)', flush=True)


if __name__ == '__main__':
    main()

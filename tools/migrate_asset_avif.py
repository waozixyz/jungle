"""One-time AVIF migration of approved runtime artwork, without regeneration.

Run --apply only to install prepared bitstreams. The ignored backup preserves
all source files; the public receipt validates every dimension, alpha and hash.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageChops, ImageStat
from avif_codec import save_avif, CUTOUT_QUALITY, QUALITY, SPEED, encoder_version

# Color qualities tried in order until a picture beats its WebP's size.
LADDER = (70, 60, 50, 42, 35, 28, 20)

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'backup/avif-migration'
CACHE = ROOT / 'local/art-development/avif-migration'
RECEIPT = ROOT / 'tools/canonical_avif.json'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def migrate(source):
    name = source.relative_to(ARCHIVE).as_posix()
    destination = ROOT / Path(name).with_suffix('.avif')
    candidate = CACHE / Path(name).with_suffix('.avif')
    with Image.open(source) as original:
        picture = original.convert('RGBA')
        dimensions = list(picture.size)
        alpha = picture.getchannel('A').getextrema()[0] < 255
        original_rgba = hashlib.sha256(picture.tobytes()).hexdigest()
        original_alpha = hashlib.sha256(picture.getchannel('A').tobytes()).hexdigest()
        with source.open('rb') as stream:
            stream.seek(12)
            webp_lossless = False
            while header := stream.read(8):
                if header[:4] in (b'VP8L', b'VP8 '):
                    webp_lossless = header[:4] == b'VP8L'
                    break
                size = int.from_bytes(header[4:], 'little')
                stream.seek(size + size % 2, 1)
        jigsaw = name.startswith('assets/jigsaw/')
        # Transparent art keeps exact alpha with q70 4:4:4 color; opaque lossless
        # WebP (palettes, icons) stays exact. Puzzle paintings are photos: q50.
        cutout = alpha
        lossless = not alpha and webp_lossless and not jigsaw
        quality = 50 if jigsaw or name.startswith('assets/jungle-book/previews/') or (Path(name).parent == Path('assets/jungle/title') and Path(name).stem.startswith('world-map')) else QUALITY
        if not alpha:
            picture = picture.convert('RGB')
        source_bytes = source.stat().st_size
        settings = dict(source_sha256=digest(source), cutout=cutout, lossless=lossless, quality=quality,
                        ladder=LADDER, speed=SPEED, encoder=encoder_version())
        stamp = candidate.with_suffix('.json')
        if not candidate.exists() or not stamp.exists() or json.loads(stamp.read_text()).get('settings') != settings:
            # Every shipped picture must be smaller than the WebP it replaces:
            # step the color quality down until it is (alpha always stays exact).
            steps = [q for q in LADDER if q <= (CUTOUT_QUALITY if cutout else quality)] or [quality]
            for used in steps:
                if cutout:
                    save_avif(picture, candidate, lossless=True, cutout_quality=used)
                else:
                    save_avif(picture, candidate, lossless=lossless, quality=used)
                if lossless or candidate.stat().st_size < source_bytes:
                    break
            stamp.write_text(json.dumps({'settings': settings, 'quality': None if lossless else used}))
        used = json.loads(stamp.read_text())['quality']
    with Image.open(candidate) as decoded:
        rgba = decoded.convert('RGBA')
        assert list(decoded.size) == dimensions, name
        rgba_hash = hashlib.sha256(rgba.tobytes()).hexdigest()
        alpha_hash = hashlib.sha256(rgba.getchannel('A').tobytes()).hexdigest()
        assert alpha_hash == original_alpha, name
        assert not lossless or rgba_hash == original_rgba, name
    return destination.relative_to(ROOT).as_posix(), {
        'source': name, 'source_sha256': digest(source), 'source_bytes': source.stat().st_size,
        'source_rgba_sha256': original_rgba, 'dimensions': dimensions,
        'alpha': alpha, 'source_alpha_sha256': original_alpha, 'alpha_sha256': alpha_hash, 'rgba_sha256': rgba_hash,
        'sha256': digest(candidate), 'bytes': candidate.stat().st_size,
        'quality': used, 'lossless': lossless, 'exact_alpha': True,
        'subsampling': '444' if lossless or cutout else '420', 'speed': SPEED,
    }


def reencode(item):
    """Re-encode a lossless export from its own exact pixels under the size rule:
    transparent art keeps exact alpha with 4:4:4 color, stepping quality down
    until it is smaller than the original source; puzzle paintings use q50."""
    name, row = item
    current = ROOT / name
    candidate = CACHE / 'reencode' / name
    with Image.open(current) as decoded:
        picture = decoded.convert('RGBA')
    assert hashlib.sha256(picture.tobytes()).hexdigest() == row['rgba_sha256'], name
    alpha = row['alpha']
    jigsaw = name.startswith('assets/jigsaw/')
    exact = not alpha and not jigsaw
    if not alpha:
        picture = picture.convert('RGB')
    limit = row['source_bytes']
    if exact:
        return name, row
    for used in [q for q in LADDER if q <= (CUTOUT_QUALITY if alpha else 50)]:
        if alpha:
            save_avif(picture, candidate, lossless=True, cutout_quality=used)
        else:
            save_avif(picture, candidate, quality=used)
        if candidate.stat().st_size < limit:
            break
    alpha_used = 100
    if alpha and candidate.stat().st_size >= limit:
        # Soft glows and tiny icons whose exact alpha alone outweighs the WebP:
        # keep q50 color and give the alpha plane near-lossless quality instead.
        for alpha_used in (90, 80, 70, 60, 50):
            save_avif(picture, candidate, lossless=True, cutout_quality=50, alpha_quality=alpha_used)
            if candidate.stat().st_size < limit:
                break
        used = 50
    with Image.open(candidate) as decoded:
        rgba = decoded.convert('RGBA')
        assert list(decoded.size) == row['dimensions'], name
        if alpha_used == 100:
            assert hashlib.sha256(rgba.getchannel('A').tobytes()).hexdigest() == row['alpha_sha256'], ('alpha changed', name)
        else:
            error = ImageStat.Stat(ImageChops.difference(rgba.getchannel('A'), picture.getchannel('A'))).mean[0]
            assert error < 2.0, ('alpha drifted', name, error)
        rgba_hash = hashlib.sha256(rgba.tobytes()).hexdigest()
    updated = dict(row, sha256=digest(candidate), bytes=candidate.stat().st_size, rgba_sha256=rgba_hash,
                   quality=used, lossless=False, exact_alpha=alpha_used == 100, alpha_quality=alpha_used, subsampling='444' if alpha else '420')
    return name, updated


def reencode_all(apply):
    receipt = json.loads(RECEIPT.read_text())
    rows = receipt['files']
    for name, row in rows.items():
        assert digest(ROOT/name) == row['sha256'], ('changed since its provenance', name)
    pending = [(name, row) for name, row in rows.items() if row['lossless']]
    changed = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        for index, (name, row) in enumerate(pool.map(reencode, pending), 1):
            if row is not rows[name]:
                changed[name] = row
            if index % 50 == 0:
                print(f'Re-encoded {index}/{len(pending)}', flush=True)
    grown = [name for name, row in {**rows, **changed}.items() if row['bytes'] >= row['source_bytes'] and not row['lossless']]
    print(f'AVIF re-encode: {len(changed)} of {len(pending)} lossless exports; '
          f'{sum(rows[n]["bytes"] for n in changed)} -> {sum(r["bytes"] for r in changed.values())} bytes; '
          f'not smaller than source: {len(grown)} {grown[:5]}', flush=True)
    if not apply:
        return
    for name in changed:
        shutil.copyfile(CACHE / 'reencode' / name, ROOT / name)
    rows.update(changed)
    receipt['encoding'] = ('AVIF q35 (q50 book previews, world map and puzzle paintings) 8-bit YUV420 full range speed6 jobs1; '
                           'transparent art keeps exact (lossless) alpha with q70 YUV444 color, stepped down until smaller '
                           'than its source; only tiny opaque exact art stays lossless')
    receipt['after_bytes'] = sum(r['bytes'] for r in rows.values())
    refresh_runtime_provenance(rows)
    RECEIPT.write_text(json.dumps(receipt, indent=2)+'\n')


MASTER_KEYS = ('master', 'source', 'canonical_source', 'original', 'source_png')


def provenance_masters():
    """Runtime path -> local/art-development masters named by provenance JSON."""
    found = {}
    def walk(value):
        if isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            runtimes = [v for k, v in value.items() if isinstance(v, str) and v.startswith('assets/')]
            masters = [v for k, v in value.items() if k in MASTER_KEYS and isinstance(v, str)
                       and v.startswith('local/') and (ROOT / v).is_file()]
            for runtime in runtimes:
                for master in masters:
                    found.setdefault(str(Path(runtime).with_suffix('.avif')), []).append(master)
            for item in value.values():
                walk(item)
    for base in ('tools', 'assets'):
        for path in (ROOT / base).rglob('*.json'):
            if path.name != 'canonical_avif.json':
                try:
                    walk(json.loads(path.read_text()))
                except ValueError:
                    pass
    return found


def best_master(name, row, masters):
    """The art-development master when it is the same picture, else the
    archived pre-AVIF original, else the current file."""
    archived = ARCHIVE / Path(row.get('source', name)) if row.get('source') else None
    fallback = archived if archived and archived.is_file() else ROOT / name
    with Image.open(fallback) as im:
        reference = im.convert('RGBA')
    for master in masters.get(name, []):
        with Image.open(ROOT / master) as im:
            candidate = im.convert('RGBA')
        if abs(candidate.width / candidate.height - reference.width / reference.height) > .01:
            continue
        if candidate.width < reference.width:
            continue
        a = candidate.resize((256, 256), Image.Resampling.LANCZOS)
        b = reference.resize((256, 256), Image.Resampling.LANCZOS)
        if max(ImageStat.Stat(ImageChops.difference(a, b)).mean) < 6:
            return master, candidate.resize(reference.size, Image.Resampling.LANCZOS) if candidate.size != reference.size else candidate
    return str(fallback.relative_to(ROOT)), reference


def scale(item, masters):
    """Re-export one shipped picture under the 75% Lanczos q35 standard."""
    from image_exports import save_scaled, scaled_role, runtime_size
    name, row = item
    exact = row['lossless'] and not row['alpha']
    if not scaled_role(name, row['dimensions'], exact):
        return name, row
    master, picture = best_master(name, row, masters)
    candidate = CACHE / 'scale75' / name
    alpha = save_scaled(picture, candidate)
    if candidate.stat().st_size >= row['bytes']:
        return name, row
    with Image.open(candidate) as decoded:
        rgba = decoded.convert('RGBA')
    expected = picture.convert('RGBA').resize(runtime_size(picture.size), Image.Resampling.LANCZOS)
    assert rgba.size == expected.size, name
    if alpha:
        drift = ImageChops.difference(rgba.getchannel('A'), expected.getchannel('A'))
        assert ImageStat.Stat(drift).mean[0] < 1 and drift.getextrema()[1] <= 24, ('alpha drifted', name)
    updated = dict(row, sha256=digest(candidate), bytes=candidate.stat().st_size,
                   rgba_sha256=hashlib.sha256(rgba.tobytes()).hexdigest(),
                   alpha_sha256=hashlib.sha256(rgba.getchannel('A').tobytes()).hexdigest(),
                   dimensions=list(rgba.size), design_dimensions=list(picture.size), quality=35, lossless=False, scale=0.75,
                   master=master, master_sha256=digest(ROOT / master),
                   exact_alpha=False if alpha else row.get('exact_alpha', False),
                   alpha_quality=90 if alpha else 100, subsampling='444' if alpha else '420')
    return name, updated


def scale_all(apply):
    receipt = json.loads(RECEIPT.read_text())
    rows = receipt['files']
    for name, row in rows.items():
        assert digest(ROOT/name) == row['sha256'], ('changed since its provenance', name)
    masters = provenance_masters()
    changed = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        for index, (name, row) in enumerate(pool.map(lambda item: scale(item, masters), rows.items()), 1):
            if row is not rows[name]:
                changed[name] = row
            if index % 100 == 0:
                print(f'Scaled {index}/{len(rows)}', flush=True)
    from_masters = sum(1 for row in changed.values() if row['master'].startswith('local/'))
    print(f'AVIF 75% standard: {len(changed)} of {len(rows)} pictures; '
          f'{sum(rows[n]["bytes"] for n in changed)} -> {sum(r["bytes"] for r in changed.values())} bytes; '
          f'{from_masters} from art-development masters', flush=True)
    if not apply:
        return
    for name in changed:
        shutil.copyfile(CACHE / 'scale75' / name, ROOT / name)
    rows.update(changed)
    receipt['encoding'] = ('Owner standard 2026-11-05: masters Lanczos-downscaled to 75%, AVIF q35 8-bit full range speed6 '
                           'jobs1; opaque YUV420, transparent art YUV444 with q90 alpha. Pictures under 512 px, '
                           'source-rectangle sheets, jigsaw (q60 YUV444), paint art and cursors keep their pixels.')
    receipt['after_bytes'] = sum(r['bytes'] for r in rows.values())
    refresh_runtime_provenance(rows)
    RECEIPT.write_text(json.dumps(receipt, indent=2)+'\n')


def refresh_runtime_provenance(rows):
    """Refresh active byte/pixel fingerprints while preserving original hashes."""
    def refresh(value):
        if isinstance(value, list):
            for item in value:
                refresh(item)
        elif isinstance(value, dict):
            for key, item in list(value.items()):
                if key in rows:
                    if isinstance(item, str) and len(item) == 64:
                        value[key] = rows[key]['sha256']
                    elif isinstance(item, dict):
                        for field in ('sha256', 'bytes', 'dimensions', 'rgba_sha256'):
                            if field in item:
                                item[field] = rows[key][field]
                if isinstance(item, str) and item in rows:
                    row = rows[item]
                    if key in ('path', 'runtime'):
                        for field in ('sha256', 'bytes', 'dimensions', 'rgba_sha256', 'lossless', 'quality'):
                            if field in value:
                                value[field] = row[field]
                        if 'decoded_rgba_sha256' in value:
                            value['decoded_rgba_sha256'] = row['rgba_sha256']
                    if key + '_sha256' in value:
                        value[key + '_sha256'] = row['sha256']
                refresh(item)
    for base in ('tools', 'tests', 'assets'):
        for path in (ROOT/base).rglob('*.json'):
            if path.name in ('canonical_avif.json', 'legacy-webp.json'):
                continue
            before = path.read_text()
            data = json.loads(before)
            refresh(data)
            if path.name == 'approved_title_avif.json':
                data['total_bytes'] = sum(row['bytes'] for row in data['images'])
            if path.name == 'farm_images.json':
                for name, row in data['cutouts'].items():
                    actual = rows[f'assets/garden/play/{name}.avif']
                    row.update(sha256=actual['sha256'], bytes=actual['bytes'])
            if data != json.loads(before):
                path.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--scale', action='store_true',
                        help='re-export every eligible picture at 75%% (Lanczos) and q35')
    parser.add_argument('--reencode-lossless', action='store_true',
                        help='shrink lossless exports: exact alpha with lossy 4:4:4 color')
    args = parser.parse_args()
    if args.scale:
        return scale_all(args.apply)
    if args.reencode_lossless:
        return reencode_all(args.apply)
    for path in (ARCHIVE, CACHE):
        subprocess.run(['git', 'check-ignore', '-q', str(path.relative_to(ROOT))], cwd=ROOT, check=True)
    receipt_before = RECEIPT.read_bytes() if RECEIPT.exists() else None
    existing = json.loads(receipt_before) if receipt_before else {}
    for name, row in existing.get('files', {}).items():
        destination = ROOT/name
        assert destination.is_file() and digest(destination) == row['sha256'], (
            'Refusing to overwrite a changed approved AVIF; update its provenance through its authoring tool', name)
    active_sources = sorted((ROOT / 'assets').rglob('*.webp'))
    if not active_sources:
        assert existing, 'No runtime WebP inputs; an old backup alone never authorizes replacing current AVIF art'
        print(f'AVIF: validated {len(existing["files"])} existing exports; no WebP inputs, no assets or metadata rewritten')
        return
    assert not existing, 'Migration already completed; export new artwork through image_exports.py instead of introducing runtime WebP'
    for source in active_sources:
        archived = ARCHIVE / source.relative_to(ROOT)
        archived.parent.mkdir(parents=True, exist_ok=True)
        if not archived.exists():
            shutil.copyfile(source, archived)
        assert digest(archived) == digest(source), source
    # Only live WebP inputs authorize conversion. Archived files never become
    # replay inputs after migration, including after separately approved art.
    sources = [ARCHIVE/source.relative_to(ROOT) for source in active_sources]
    rows = dict(existing.get('files', {}))
    prepared = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        for index, (name, row) in enumerate(pool.map(migrate, sources), 1):
            destination = ROOT/name
            assert not destination.exists() or digest(destination) == row['sha256'], (
                'Refusing to replace an existing AVIF with an archived WebP conversion', name)
            prepared[name] = row
            rows[name] = row
            if index % 50 == 0:
                print(f'Validated AVIF {index}/{len(sources)}', flush=True)
    receipt = {
        'version': 1, 'count': len(rows), 'encoder': encoder_version(),
        'encoding': 'AVIF q35 (q50 book previews) 8-bit YUV420 full range speed6 jobs1; jigsaw puzzle pictures and exact RGBA use lossless identity YUV444',
        'dimensions': 'Full original dimensions; no downsampling, no regeneration',
        'reference': 'local/image-format-research/previews/full-1x-book-page.png (label: 75% AVIF q35 + Lanczos); full dimensions retained for shipping',
        'migration_baseline': existing.get('migration_baseline', {'format': 'WEBP', 'count': len(sources), 'bytes': sum(p.stat().st_size for p in sources)}),
        'before_bytes': sum(r['source_bytes'] for r in rows.values()),
        'before_bytes_note': 'Per-export source byte sum, including the same approved new map PNG for four exports. migration_baseline.bytes is the immutable original WebP total.',
        'after_bytes': sum(r['bytes'] for r in rows.values()), 'files': rows,
    }
    allowed = json.loads((ROOT/'tools/asset_png_allowlist.json').read_text())
    receipt['technical_files'] = {}
    for section in ('files', 'other_platform_formats', 'android_platform_files'):
        for name in allowed[section]:
            path = ROOT/name
            with Image.open(path) as image:
                receipt['technical_files'][name] = {'sha256': digest(path), 'bytes': path.stat().st_size,
                                                   'dimensions': list(image.size), 'format': image.format}
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / 'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    if args.apply:
        assert (RECEIPT.read_bytes() if RECEIPT.exists() else None) == receipt_before, 'Provenance changed while preparing; nothing installed'
        # Validate every pending write before changing any destination/source.
        for name, row in prepared.items():
            destination = ROOT/name
            assert not destination.exists() or digest(destination) == row['sha256'], ('AVIF changed while preparing; nothing installed', name)
            assert digest(ROOT/row['source']) == row['source_sha256'], ('WebP changed while preparing; nothing installed', name)
        for name, row in prepared.items():
            destination = ROOT / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                shutil.copyfile(CACHE / name, destination)
            (ROOT / row['source']).unlink()
        refresh_runtime_provenance(rows)
        RECEIPT.write_text(json.dumps(receipt, indent=2)+'\n')
    print(f'AVIF: {len(rows)} images, {receipt["before_bytes"]} -> {receipt["after_bytes"]} bytes; apply={args.apply}', flush=True)


if __name__ == '__main__':
    main()

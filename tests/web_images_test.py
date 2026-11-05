"""Verify shipped runtime AVIF payloads, provenance, dimensions and alpha."""
import hashlib
import io
import json
import os
from pathlib import Path
import zipfile

from PIL import Image, ImageChops, ImageStat
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from web_images import APP_READY_FARM_AVIF
from farm_images import RUNTIME as FARM_RUNTIME

ROOT = Path(__file__).resolve().parents[1]
WEB = Path(os.environ.get('JUNGLE_WEB_ROOT', ROOT/'build/web'))
manifest = json.loads((WEB/'asset-packs.json').read_text())
converted = 0
categories = set()
for name, entry in manifest['files'].items():
    if entry.get('encoding') != 'avif':
        if name.startswith('assets/dino-paint/'):
            assert entry['sha256'] == hashlib.sha256((ROOT/name).read_bytes()).hexdigest(), name
        continue
    original_path = ROOT/name
    original_bytes = original_path.read_bytes()
    assert entry['source_sha256'] == hashlib.sha256(original_bytes).hexdigest(), name
    assert (entry['quality'] is None if entry.get('reused_source') or entry.get('alpha') else entry['quality'] == 35), entry
    assert entry.get('alpha_quality') == 100, entry
    if entry.get('reused_source'):
        assert entry['runtime_bytes'] == entry['source_bytes'] and entry['sha256'] == entry['source_sha256'], name
    else:
        assert entry['runtime_bytes'] < entry['source_bytes'], name
    with zipfile.ZipFile(WEB/entry['pack']) as archive:
        stored = next(item for item in archive.infolist()
                      if item.header_offset + 30 + len(item.filename.encode('utf-8'))
                      + len(item.extra) == entry['offset'])
        assert stored.filename.endswith('.avif'), name
        payload = archive.read(stored)
    assert b'ftyp' == payload[4:8], name
    assert hashlib.sha256(payload).hexdigest() == entry['sha256'], name
    assert len(payload) == entry['runtime_bytes'] == entry['size'], name
    with Image.open(io.BytesIO(payload)) as decoded, Image.open(original_path) as original:
        assert decoded.format == 'AVIF', name
        assert (original.width, original.height) == (entry['width'], entry['height']), name
        assert (decoded.width, decoded.height) == (entry['runtime_width'], entry['runtime_height']), name
        assert max(decoded.size) <= entry['long_edge'], name
        assert (original.mode in ('RGBA', 'LA', 'PA') or
                (original.mode == 'P' and 'transparency' in original.info)) == entry['alpha'], name
        if entry['alpha']:
            assert hashlib.sha256(decoded.getchannel('A').tobytes()).hexdigest() == entry['alpha_sha256'], name
        else:
            assert 'A' not in decoded.getbands(), name
    converted += 1
    categories.add(str(Path(name).parent))

representatives = (
    'assets/jungle-book/pages/tiger.avif',
    'assets/hide_seek/props/basket.avif', 'assets/shapes/wooden/backdrop.avif',
    'assets/drums/pictures/room.avif')
for name in representatives:
    entry = manifest['files'][name]
    with zipfile.ZipFile(WEB/entry['pack']) as archive, Image.open(ROOT/name) as original:
        stored = next(item for item in archive.infolist()
                      if item.header_offset + 30 + len(item.filename.encode('utf-8'))
                      + len(item.extra) == entry['offset'])
        with Image.open(archive.open(stored)) as decoded:
            decoded.load()
            comparison = original.convert('RGBA').resize(decoded.size, Image.Resampling.LANCZOS)
            rgb = ImageStat.Stat(ImageChops.difference(decoded.convert('RGB'), comparison.convert('RGB')))
            assert max(rgb.mean) < 8 and max(rgb.rms) < 24, (name, rgb.mean, rgb.rms)
            if entry['alpha']:
                assert ImageChops.difference(decoded.getchannel('A'),
                                             comparison.getchannel('A')).getbbox() is None, name

assert converted > 700, converted
assert {'assets/jungle-book/pages', 'assets/jungle-book/items',
        'assets/shapes/wooden', 'assets/drums/pictures', 'assets/hide_seek/props'} <= categories, categories
farm_files={name for name in manifest['files'] if name.startswith('assets/garden/')}
assert farm_files==FARM_RUNTIME, ('Unreferenced/missing Farm payload',farm_files ^ FARM_RUNTIME)
for name in APP_READY_FARM_AVIF | farm_files:
    entry=manifest['files'][name]
    assert entry['sha256']==hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),name

title_sources = sorted((ROOT/'assets/jungle/title').glob('*.avif'))
assert title_sources
for source in title_sources:
    shipped = WEB/'assets/jungle/title'/(source.stem + '.avif')
    assert shipped.is_file(), source
    with Image.open(shipped) as decoded, Image.open(source) as original:
        assert decoded.format == 'AVIF' and decoded.size == original.size, source
        assert decoded.size == original.size, source
print(f'local web image test: {converted} full-dimension runtime AVIF payloads with provenance, magic, dimensions, representative pixels/alpha and unchanged Dino Paint passed')

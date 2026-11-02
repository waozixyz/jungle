"""Verify shipped runtime WebP payloads, provenance, dimensions and alpha."""
import hashlib
import io
import json
import os
from pathlib import Path
import zipfile

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]
WEB = Path(os.environ.get('JUNGLE_WEB_ROOT', ROOT/'build/web'))
manifest = json.loads((WEB/'asset-packs.json').read_text())
converted = 0
categories = set()
for name, entry in manifest['files'].items():
    if entry.get('encoding') != 'webp':
        if name.startswith('assets/dino-paint/'):
            assert entry['sha256'] == hashlib.sha256((ROOT/name).read_bytes()).hexdigest(), name
        continue
    original_path = ROOT/name
    original_bytes = original_path.read_bytes()
    assert entry['source_sha256'] == hashlib.sha256(original_bytes).hexdigest(), name
    assert (entry['quality'] is None if entry.get('reused_source') else entry['quality'] == 85), entry
    assert entry.get('alpha_quality') == 100, entry
    if entry.get('reused_source'):
        assert entry['runtime_bytes'] == entry['source_bytes'] and entry['sha256'] == entry['source_sha256'], name
    else:
        assert entry['runtime_bytes'] < entry['source_bytes'], name
    with zipfile.ZipFile(WEB/entry['pack']) as archive:
        stored = next(item for item in archive.infolist()
                      if item.header_offset + 30 + len(item.filename.encode('utf-8'))
                      + len(item.extra) == entry['offset'])
        assert stored.filename.endswith('.webp'), name
        payload = archive.read(stored)
    assert payload[:4] == b'RIFF' and payload[8:12] == b'WEBP', name
    assert hashlib.sha256(payload).hexdigest() == entry['sha256'], name
    assert len(payload) == entry['runtime_bytes'] == entry['size'], name
    with Image.open(io.BytesIO(payload)) as decoded, Image.open(original_path) as original:
        assert decoded.format == 'WEBP', name
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
    'assets/jungle-book/pages/tiger.webp', 'assets/garden/art/bed.png',
    'assets/hide_seek/props/basket.png', 'assets/shapes/wooden/backdrop.png',
    'assets/drums/pictures/room.png')
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
assert {'assets/jungle-book/pages', 'assets/jungle-book/items', 'assets/garden/art',
        'assets/shapes/wooden', 'assets/drums/pictures', 'assets/hide_seek/props'} <= categories, categories
title_sources = sorted((ROOT/'assets/jungle/title').glob('*.webp'))
assert title_sources
for source in title_sources:
    shipped = WEB/'assets/jungle/title'/(source.stem + '.webp')
    assert shipped.is_file(), source
    with Image.open(shipped) as decoded, Image.open(source) as original:
        assert decoded.format == 'WEBP' and max(decoded.size) <= 2048, source
        assert decoded.size == original.size, source
print(f'local web image test: {converted} capped runtime WebP payloads with provenance, magic, dimensions, representative pixels/alpha and unchanged Dino Paint passed')

"""Verify shipped WebP pixels, source provenance and the protected PNG artwork."""
import hashlib
import io
import json
from pathlib import Path
import zipfile

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT/'build/web'
manifest = json.loads((WEB/'asset-packs.json').read_text())
converted = 0
for name, entry in manifest['files'].items():
    if entry.get('encoding') != 'webp':
        if name.startswith('assets/dino-paint/'):
            assert entry['sha256'] == hashlib.sha256((ROOT/name).read_bytes()).hexdigest(), name
        continue
    assert str(Path(name).parent) in {'assets/jungle-book/pages', 'assets/jungle-book/previews', 'assets/jigsaw'}, name
    assert name.endswith('.jpg') and entry['quality'] == 90, name
    original_bytes = (ROOT/name).read_bytes()
    assert entry['source_sha256'] == hashlib.sha256(original_bytes).hexdigest(), name
    with zipfile.ZipFile(WEB/entry['pack']) as archive:
        # Identical previews share one stored entry; use the shipped seek index
        # rather than assuming every logical alias has its own ZIP filename.
        stored = next(item for item in archive.infolist()
                      if item.header_offset + 30 + len(item.filename.encode('utf-8'))
                      + len(item.extra) == entry['offset'])
        assert stored.filename.endswith('.webp'), name
        payload = archive.read(stored)
    assert hashlib.sha256(payload).hexdigest() == entry['sha256'], name
    with Image.open(io.BytesIO(payload)) as decoded, Image.open(io.BytesIO(original_bytes)) as original:
        assert decoded.format == 'WEBP' and decoded.size == original.size, name
        difference = ImageStat.Stat(ImageChops.difference(decoded.convert('RGB'), original.convert('RGB')))
        assert max(difference.mean) < 7 and max(difference.rms) < 20, (name, difference.mean, difference.rms)
    assert len(payload) < len(original_bytes), name
    converted += 1
assert converted > 200, converted
print(f'local web image test: {converted} smaller full-resolution WebP photos, source fingerprints and unchanged Dino Paint SVG/PNG encoding passed')

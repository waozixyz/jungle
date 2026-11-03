import hashlib
import json
import subprocess
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parents[1]
records = json.loads((root / 'tools/art_provenance/activity-covers/sources.json').read_text())
names = {'shapes': 'Shapes & Sorting', 'matching': 'Matching Pairs', 'hide-seek': 'Hide & Seek', 'drums': 'Music Room'}
assert set(records) == set(names)
hash_file = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
for name, title in names.items():
    rec = records[name]
    path = root / rec['webp']
    assert rec['webp'] == f'assets/jungle/covers/{name}.webp'
    with Image.open(path) as im:
        assert im.format == 'WEBP' and im.mode == 'RGB' and im.size == (420, 420)
    assert hash_file(path) == rec['webp_sha256'] and rec['prompt'] and rec['references']
    for ref, digest in rec['references'].items():
        if (root/ref).exists(): assert hash_file(root/ref) == digest
    raw = Path(rec['source_png'])
    if raw.exists(): assert hash_file(raw) == rec['source_sha256']
    lines = (root / 'games/catalog.txt').read_text().splitlines()
    assert sum(title in line and rec['webp'] in line for line in lines) == 1
    # The web host's painted navigation registers titles only; covers stay in the catalog.
    web = (root / 'web/jungle_web.zi').read_text()
    assert web.count(f'MenuGame.{{.title = "{title}"}}') == 1, title
assert len({r['webp_sha256'] for r in records.values()}) == 4
for name in ['abc-123', 'abc', 'book', 'counting', 'jigsaw', 'numbers', 'paint', 'piano']:
    path = f'assets/jungle/covers/{name}.webp'
    migration = json.loads((root / 'tools/canonical_webp.json').read_text())['files'][path]
    assert migration['sha256'] == hash_file(root / path), path
print('activity cover tests passed')

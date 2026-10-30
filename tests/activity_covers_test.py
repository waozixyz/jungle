import hashlib
import json
import subprocess
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parents[1]
records = json.loads((root / 'art/generated/activity-covers/sources.json').read_text())
names = {'shapes': 'Shapes & Sorting', 'matching': 'Matching Pairs', 'hide-seek': 'Hide & Seek', 'drums': 'Little Drums'}
assert set(records) == set(names)
hash_file = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
for name, title in names.items():
    rec = records[name]
    path = root / rec['jpeg']
    assert rec['jpeg'] == f'assets/jungle/covers/{name}.jpg'
    with Image.open(path) as im:
        assert im.format == 'JPEG' and im.mode == 'RGB' and im.size == (420, 420)
    assert hash_file(path) == rec['jpeg_sha256'] and rec['prompt'] and rec['references']
    for ref, digest in rec['references'].items(): assert hash_file(root / ref) == digest
    raw = Path(rec['source_png'])
    if raw.exists(): assert hash_file(raw) == rec['source_sha256']
    for registry in ['games/catalog.txt', 'web/jungle_web.zi']:
        lines = (root / registry).read_text().splitlines()
        assert sum(title in line and rec['jpeg'] in line for line in lines) == 1
assert len({r['jpeg_sha256'] for r in records.values()}) == 4
for name in ['abc-123', 'abc', 'book', 'counting', 'jigsaw', 'numbers', 'paint', 'piano']:
    path = f'assets/jungle/covers/{name}.jpg'
    original = subprocess.check_output(['git', 'show', f'HEAD:{path}'], cwd=root)
    assert hashlib.sha256(original).hexdigest() == hash_file(root / path), path
print('activity cover tests passed')

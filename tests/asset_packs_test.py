"""Portable ZIP round trips, deduplication, reproducibility and upload gates."""
import hashlib
from pathlib import Path
import sys
import tempfile
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from asset_packs import pack_assets, validate_distribution

with tempfile.TemporaryDirectory(prefix='asset-pack-test-',dir=ROOT/'build') as temporary:
    root = Path(temporary)
    inputs = {}
    for name, data in {'images/a.png': b'\x89PNG'+bytes(range(256))*8,
                       'sounds/en/a.wav': b'RIFF'+b'hello world'*2048,
                       'sounds/es/a.wav': b'RIFF'+b'hola mundo'*2048,
                       'images/alias.png': b'\x89PNG'+bytes(range(256))*8,
                       'words/niño.txt': 'niño'.encode(),
                       'words/empty.txt': b''}.items():
        path=root/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        inputs[name]=path
    first=pack_assets(inputs, root/'one', max_bytes=24000)
    second=pack_assets(dict(reversed(list(inputs.items()))), root/'two', max_bytes=24000)
    assert first==second, 'Pack layout depends on source enumeration order'
    assert first['files']['images/a.png']==first['files']['images/alias.png']
    methods=set()
    for name, entry in first['files'].items():
        payload=(root/'one'/entry['pack']).read_bytes()
        assert payload==(root/'two'/entry['pack']).read_bytes()
        compressed=payload[entry['offset']:entry['offset']+entry['length']]
        data=zlib.decompress(compressed,-15) if entry['method']==8 else compressed
        assert data==inputs[name].read_bytes(), name
        assert hashlib.sha256(data).hexdigest()==entry['sha256']
        methods.add(entry['method'])
        with zipfile.ZipFile(root/'one'/entry['pack']) as archive:
            assert archive.testzip() is None
    assert methods=={0,8}
    validate_distribution(root/'one')
    try:
        pack_assets({'../outside': inputs['images/a.png']}, root/'bad')
        raise AssertionError('Unsafe path was accepted')
    except ValueError:
        pass
    for index in range(1001):
        (root/'one'/str(index)).touch()
    try:
        validate_distribution(root/'one')
        raise AssertionError('Excess files passed the upload gate')
    except ValueError:
        pass

print('local asset pack test: lossless ZIP/seek round trips, aliases, Unicode, empty files, stable output and upload gates passed')

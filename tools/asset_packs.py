"""Jungle's portable, lossless asset packs: ordinary ZIPs plus a seek index.

No image/audio conversion. Entries retain their paths and exact bytes; any ZIP
reader can extract them. The browser uses the index to decode just one entry.
"""
import hashlib
import io
import json
from pathlib import Path
import struct
import zipfile

PACK_BYTES = 4 * 1024 * 1024


def pack_assets(files, output, max_bytes=PACK_BYTES):
    """Pack {relative path: source Path}, grouping by directory and size.

    Each payload is stored once, even when multiple game paths use it. Packs
    have stable timestamps and content-addressed names for browser/CDN caches.
    """
    output = Path(output)
    directory = output / 'packs'
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {'format': 1, 'packs': {}, 'files': {}}
    pending, aliases, seen = [], {}, {}
    size, group = 0, None

    def flush():
        if not pending:
            return
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6) as archive:
            for name, data in pending:
                entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                # PNG/JPEG already have compression; WAV compresses losslessly.
                entry.compress_type = (zipfile.ZIP_STORED if Path(name).suffix
                                       in ('.png', '.jpg', '.ico') else zipfile.ZIP_DEFLATED)
                archive.writestr(entry, data)
        payload = buffer.getvalue()
        digest = hashlib.sha256(payload).hexdigest()
        name = 'packs/' + digest + '.zip'
        (output / name).write_bytes(payload)
        manifest['packs'][name] = {'size': len(payload), 'sha256': digest}
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for entry in archive.infolist():
                offset = entry.header_offset
                name_size, extra_size = struct.unpack_from('<HH', payload, offset + 26)
                manifest['files'][entry.filename] = {
                    'pack': name, 'offset': offset + 30 + name_size + extra_size,
                    'length': entry.compress_size, 'size': entry.file_size,
                    'method': entry.compress_type,
                    'sha256': hashlib.sha256(archive.read(entry)).hexdigest(),
                }
        pending.clear()

    for name, source in sorted(files.items()):
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or str(path) != name:
            raise ValueError('Unsafe asset path: ' + name)
        data = Path(source).read_bytes()
        digest = hashlib.sha256(data).digest()
        if digest in seen:
            aliases[name] = seen[digest]
            continue
        # Keep languages and activity directories separate, then split large
        # directories. No pack exceeds max_bytes except one oversized asset.
        next_group = str(path.parent)
        if next_group != group or size + len(data) > max_bytes:
            flush()
            size = 0
        seen[digest] = name
        pending.append((name, data))
        size += len(data)
        group = next_group
    flush()
    for alias, original in aliases.items():
        manifest['files'][alias] = manifest['files'][original]
    (output / 'asset-packs.json').write_text(json.dumps(manifest, separators=(',', ':')) + '\n')
    return manifest


def validate_distribution(root):
    """Fail before publication on the strictest supported hosting limits."""
    root = Path(root)
    files = [p for p in root.rglob('*') if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    if len(files) > 1000:
        raise ValueError(f'Too many distribution files: {len(files)} > 1000')
    if total > 500_000_000:
        raise ValueError(f'Distribution exceeds 500 MB: {total} bytes')
    for path in files:
        if path.stat().st_size > 25 * 1024 * 1024:
            raise ValueError('Distribution file exceeds 25 MiB: ' + str(path.relative_to(root)))
        if len(path.relative_to(root).as_posix()) > 240:
            raise ValueError('Distribution path exceeds 240 characters: ' + str(path))
    return len(files), total

#!/usr/bin/env python3
"""Encode Jungle's canonical speech clips as Ogg Vorbis, once, at build time.

Each clip of a speech manifest (tools/speech_manifest.py) is encoded at one
setting, Vorbis quality 4, mono, 22050 Hz, by ffmpeg's libvorbis. Recordings
with identical bytes in one language share one file; languages never share.
The source WAVs are only read.

Encodings are cached in work/speech-codec/LANGUAGE/SOURCE_SHA256.ogg beside a
.json record of the source hash, settings, encoder and the encoded file's own
hash. A record that differs in any of them, or a cached file whose bytes no
longer match it, is encoded again. Every new encoding is checked to be one
complete mono 22050 Hz Ogg Vorbis stream ending at exactly the source's last
frame. ffmpeg is a build tool only; the app decodes with libvorbisfile on
Linux and raylib on Android (host/sound.zi DecodeSpeech).
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import wave

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = 'assets/speech'
FORMAT = 'jungle-speech-encoded-1'
SETTINGS = {'codec': 'vorbis', 'container': 'ogg', 'quality': 4, 'channels': 1,
            'sample_rate': 22050, 'page_duration_us': 20000}
MAX_FRAMES = 22050 * 60
WORKERS = 2
_ENCODER = {}


def Encoder():
    """The ffmpeg that encodes, by its version line; refuses one without libvorbis."""
    if 'identity' not in _ENCODER:
        program = shutil.which('ffmpeg')
        if not program:
            raise RuntimeError('speech encoding needs ffmpeg with libvorbis')
        version = subprocess.run([program, '-hide_banner', '-version'], check=True, capture_output=True,
                                 text=True).stdout.splitlines()[0]
        encoders = subprocess.run([program, '-hide_banner', '-encoders'], check=True, capture_output=True,
                                  text=True).stdout
        if not re.search(r'^\s*A\S*\s+libvorbis\s', encoders, re.M):
            raise RuntimeError('ffmpeg has no libvorbis encoder: ' + version)
        _ENCODER.update(program=program, identity=version)
    return _ENCODER['identity']


def ShippedPath(language, source_sha256):
    return f'{SHIPPED}/{language}/{source_sha256}.ogg'


def OggVorbisFrames(data):
    """Frames of one complete mono 22050 Hz Ogg Vorbis stream, or ValueError.

    The pages must tile DATA exactly, belong to one stream, begin with its
    first page and end with its last; the identification header gives the
    channels and rate, and the last page's granule position the length.
    """
    at, serial, granule, first_packet = 0, None, None, None
    while at < len(data):
        if len(data) - at < 27 or data[at:at + 4] != b'OggS' or data[at + 4] != 0:
            raise ValueError('not an Ogg page')
        flags = data[at + 5]
        page_serial = int.from_bytes(data[at + 14:at + 18], 'little')
        if serial is None:
            serial = page_serial
        elif page_serial != serial:
            raise ValueError('more than one Ogg stream')
        if bool(flags & 2) != (at == 0):
            raise ValueError('Ogg stream does not begin at its first page')
        segments = data[at + 26]
        table = data[at + 27:at + 27 + segments]
        if len(table) != segments:
            raise ValueError('truncated Ogg page')
        body = at + 27 + segments
        if first_packet is None:
            first_packet = data[body:body + table[0]] if segments else b''
        granule = int.from_bytes(data[at + 6:at + 14], 'little', signed=True)
        at = body + sum(table)
        if at > len(data):
            raise ValueError('truncated Ogg page')
        if bool(flags & 4) != (at == len(data)):
            raise ValueError('Ogg stream does not end at its last page')
    if not first_packet or len(first_packet) < 30 or first_packet[:7] != b'\x01vorbis':
        raise ValueError('not a Vorbis stream')
    channels = first_packet[11]
    rate = int.from_bytes(first_packet[12:16], 'little')
    if (channels, rate) != (SETTINGS['channels'], SETTINGS['sample_rate']):
        raise ValueError(f'expected mono {SETTINGS["sample_rate"]} Hz Vorbis, found {channels} x {rate} Hz')
    if not 0 < granule <= MAX_FRAMES:
        raise ValueError('Vorbis stream length outside the speech bound')
    return granule


def _source_frames(path, clip):
    """Checks the source recording against its manifest clip; its frame count."""
    if hashlib.sha256(path.read_bytes()).hexdigest() != clip['sha256']:
        raise ValueError('speech source changed since its manifest: ' + clip['source'])
    with wave.open(str(path)) as source:
        shape = source.getnchannels(), source.getsampwidth(), source.getframerate()
        frames = source.getnframes()
    if shape != (1, 2, SETTINGS['sample_rate']) or frames != clip['frame_count'] or not 0 < frames <= MAX_FRAMES:
        raise ValueError('speech source is not its manifest clip: ' + clip['source'])
    return frames


def _check_cache(cache, root):
    """The cache must be a real folder under the owning repo's ignored work/."""
    work = root / 'work'
    resolved = cache.resolve()
    if not resolved.is_relative_to(work.resolve()) or resolved == work.resolve():
        raise ValueError(f'speech cache must be inside {work}: {cache}')
    probe = cache
    while probe != probe.parent and probe.resolve() != work.resolve():
        if probe.is_symlink():
            raise ValueError('speech cache may not pass through a symlink: ' + str(probe))
        probe = probe.parent
    if work.is_symlink():
        raise ValueError('work/ may not be a symlink')


def _record(clip, frames):
    return {'format': FORMAT, 'source_sha256': clip['sha256'], 'language': clip['language'],
            'frames': frames, 'settings': SETTINGS, 'encoder': Encoder()}


def _cached(ogg, receipt, expected):
    """The cached record when it and its file are exactly what EXPECTED needs."""
    try:
        record = json.loads(receipt.read_text())
        data = ogg.read_bytes()
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict) or {key: record.get(key) for key in expected} != expected:
        return None
    if record.get('bytes') != len(data) or record.get('sha256') != hashlib.sha256(data).hexdigest():
        return None
    return record


def _encode(source, clip, cache):
    frames = _source_frames(source, clip)
    expected = _record(clip, frames)
    folder = cache / clip['language']
    ogg = folder / (clip['sha256'] + '.ogg')
    receipt = folder / (clip['sha256'] + '.json')
    record = _cached(ogg, receipt, expected)
    if record is None:
        folder.mkdir(parents=True, exist_ok=True)
        temporary = ogg.with_name(ogg.name + '.new')
        subprocess.run([_ENCODER['program'], '-nostdin', '-v', 'error', '-y', '-i', str(source),
                        '-map', '0:a:0', '-c:a', 'libvorbis', '-q:a', str(SETTINGS['quality']),
                        '-fflags', '+bitexact', '-flags:a', '+bitexact', '-map_metadata', '-1',
                        # A short recording must have a non-final audio page.
                        # Otherwise FFmpeg-based browser decoders can trim a
                        # priming block again at EOF and lose its final samples.
                        '-page_duration', str(SETTINGS['page_duration_us']),
                        '-f', 'ogg', str(temporary)], check=True)
        data = temporary.read_bytes()
        encoded_frames = OggVorbisFrames(data)
        if encoded_frames != frames:
            temporary.unlink()
            raise ValueError(f'encoded {clip["source"]} holds {encoded_frames} frames, not {frames}')
        # A source read before encoding could have changed underneath it.
        _source_frames(source, clip)
        record = dict(expected, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
        os.replace(temporary, ogg)
        receipt_temporary = receipt.with_name(receipt.name + '.new')
        receipt_temporary.write_text(json.dumps(record, indent=1, sort_keys=True) + '\n')
        os.replace(receipt_temporary, receipt)
    return {'path': ShippedPath(clip['language'], clip['sha256']), 'sha256': record['sha256'],
            'bytes': record['bytes']}, ogg


def EncodeSpeech(manifest, root=ROOT, cache=None):
    """Encode every clip of MANIFEST; {'encoding', 'encoded', 'files'}.

    'encoding' names the settings and encoder, 'encoded' maps each clip key to
    its shipped path and encoded hash, and 'files' maps each shipped path to
    its cached file. Raises ValueError for a source that is not its clip.
    """
    root = Path(root).resolve()
    cache = Path(cache) if cache is not None else root / 'work/speech-codec'
    _check_cache(cache, root)
    Encoder()
    units = {}
    for name, clip in sorted(manifest['clips'].items()):
        if clip['source'] != name or clip['language'] not in ('en', 'de', 'es'):
            raise ValueError('unexpected speech clip: ' + name)
        units.setdefault((clip['language'], clip['sha256']), (root / name, clip))
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = dict(zip(units, pool.map(lambda unit: _encode(unit[0], unit[1], cache), units.values())))
    encoded = {name: results[(clip['language'], clip['sha256'])][0]
               for name, clip in sorted(manifest['clips'].items())}
    files = {entry['path']: file for entry, file in results.values()}
    return {'encoding': dict(SETTINGS, encoder=Encoder()), 'encoded': encoded, 'files': files}


def ValidateEncodedSpeech(manifest, files):
    """Every clip has one shipped encoding of its own language and source."""
    encoded = manifest.get('encoded')
    if manifest.get('encoding', {}).get('codec') != SETTINGS['codec'] or not isinstance(encoded, dict):
        raise ValueError('speech manifest has no encoding')
    if {key: manifest['encoding'].get(key) for key in SETTINGS} != SETTINGS:
        raise ValueError('speech encoding settings differ')
    if set(encoded) != set(manifest['clips']):
        raise ValueError('encoded speech must cover exactly the clips')
    owners = {}
    for name, entry in encoded.items():
        clip = manifest['clips'][name]
        path = ShippedPath(clip['language'], clip['sha256'])
        if set(entry) != {'path', 'sha256', 'bytes'} or entry['path'] != path:
            raise ValueError('unexpected encoded speech path: ' + name)
        if owners.setdefault(path, (entry['sha256'], entry['bytes'])) != (entry['sha256'], entry['bytes']):
            raise ValueError('one shipped speech file with two encodings: ' + path)
    if set(files) != set(owners):
        raise ValueError('encoded speech files differ from the manifest')
    for path, (digest, size) in owners.items():
        data = Path(files[path]).read_bytes()
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('encoded speech file changed: ' + path)

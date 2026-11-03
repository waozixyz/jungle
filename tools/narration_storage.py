#!/usr/bin/env python3
"""Measure verified Jungle narration storage against its multilingual model."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import wave

if __package__:
    from . import speech_codec
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import speech_codec


LANGUAGES = ('en', 'de', 'es')
PARTIAL_SUFFIXES = ('.part', '.partial', '.tmp', '.download', '.crdownload',
                    '.incomplete')
HEX256 = re.compile(r'[0-9a-f]{64}')
DEFAULT_AUDIO_ROOT = Path('build/app')
MODEL_NOTE = ('one multilingual model copy; all en/de/es voice presets share it')


def _relative_path(name, what):
    if not isinstance(name, str) or not name or '\\' in name or '\x00' in name:
        raise ValueError(f'invalid {what} path: {name!r}')
    path = Path(name)
    if path.is_absolute() or any(part in ('', '.', '..') for part in path.parts):
        raise ValueError(f'invalid {what} path: {name!r}')
    return path


def _file_under(root, relative, what):
    relative = _relative_path(relative, what)
    probe = root
    if probe.is_symlink():
        raise ValueError(f'{what} path passes through a symlink: {probe}')
    for part in relative.parts[:-1]:
        probe = probe / part
        try:
            mode = probe.lstat().st_mode
        except FileNotFoundError as error:
            raise ValueError(f'{what} does not exist: {probe}') from error
        if stat.S_ISLNK(mode):
            raise ValueError(f'{what} path passes through a symlink: {probe}')
        if not stat.S_ISDIR(mode):
            raise ValueError(f'{what} path is not inside directories: {probe}')
    path = probe / relative.parts[-1]
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as error:
        raise ValueError(f'{what} does not exist: {path}') from error
    if stat.S_ISLNK(mode):
        raise ValueError(f'{what} is a symlink: {path}')
    if not stat.S_ISREG(mode):
        raise ValueError(f'{what} is not a regular file: {path}')
    return path


def _sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _model_snapshot(model_directory):
    model = Path(model_directory)
    mode = model.lstat().st_mode
    if stat.S_ISLNK(mode):
        raise ValueError('model directory is a symlink: ' + str(model))
    if not stat.S_ISDIR(mode):
        raise ValueError('model directory is not a directory: ' + str(model))

    identities = {}
    aliases = 0

    def visit(directory):
        nonlocal aliases
        with os.scandir(directory) as entries:
            for entry in entries:
                entry_mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISLNK(entry_mode):
                    raise ValueError('model snapshot contains a symlink: ' + entry.path)
                if stat.S_ISDIR(entry_mode):
                    visit(Path(entry.path))
                elif stat.S_ISREG(entry_mode):
                    if entry.name.lower().endswith(PARTIAL_SUFFIXES):
                        raise ValueError('model snapshot contains a partial file: ' + entry.path)
                    stats = entry.stat(follow_symlinks=False)
                    identity = (stats.st_dev, stats.st_ino)
                    if identity in identities:
                        aliases += 1
                    else:
                        identities[identity] = stats.st_size
                else:
                    raise ValueError('model snapshot contains a non-regular file: ' + entry.path)

    visit(model)
    if not identities:
        raise ValueError('model snapshot is empty: ' + str(model))
    return {'files': len(identities), 'bytes': sum(identities.values()),
            'hardlink_aliases_not_counted': aliases}


def _validated_manifest(manifest, root, audio_root):
    if not isinstance(manifest, dict):
        raise ValueError('encoded manifest must be a JSON object')
    clips = manifest.get('clips')
    encoded = manifest.get('encoded')
    if not isinstance(clips, dict) or not clips:
        raise ValueError('encoded manifest has no clips')
    if not isinstance(encoded, dict):
        raise ValueError('encoded manifest has no encoded assets')

    languages = {clip.get('language') for clip in clips.values() if isinstance(clip, dict)}
    missing = [language for language in LANGUAGES if language not in languages]
    if missing:
        raise ValueError('encoded manifest is missing complete languages: ' + ', '.join(missing))

    encoding = manifest.get('encoding')
    if not isinstance(encoding, dict):
        raise ValueError('encoded manifest has no encoding settings')
    if {key: encoding.get(key) for key in speech_codec.SETTINGS} != speech_codec.SETTINGS:
        raise ValueError('encoded manifest does not use mono 22050 Hz Ogg Vorbis q4 settings')
    if not isinstance(encoding.get('encoder'), str) or not encoding['encoder']:
        raise ValueError('encoded manifest has no encoder identity')

    raw_logical = 0
    unique_sources = {}
    owners = {}
    for name, clip in clips.items():
        if not isinstance(name, str) or not isinstance(clip, dict):
            raise ValueError('invalid speech clip entry')
        language = clip.get('language')
        source = clip.get('source')
        digest = clip.get('sha256')
        frames = clip.get('frame_count')
        if language not in LANGUAGES:
            raise ValueError('unexpected speech clip language: ' + str(name))
        if source != name:
            raise ValueError('speech clip source differs from its key: ' + str(name))
        if not isinstance(digest, str) or not HEX256.fullmatch(digest):
            raise ValueError('invalid source hash: ' + str(name))
        if isinstance(frames, bool) or not isinstance(frames, int) or not 0 < frames <= speech_codec.MAX_FRAMES:
            raise ValueError('invalid source frame count: ' + str(name))

        path = _file_under(root, source, 'speech source')
        actual_digest = _sha256(path)
        if actual_digest != digest:
            raise ValueError('speech source changed since its manifest: ' + source)
        with wave.open(str(path)) as recording:
            shape = recording.getnchannels(), recording.getsampwidth(), recording.getframerate()
            actual_frames = recording.getnframes()
        if shape != (speech_codec.SETTINGS['channels'], 2,
                     speech_codec.SETTINGS['sample_rate']) or actual_frames != frames:
            raise ValueError('speech source is not its manifest clip: ' + source)
        size = path.stat().st_size
        raw_logical += size
        unique_sources.setdefault(digest, size)

        entry = encoded.get(name)
        if not isinstance(entry, dict) or set(entry) != {'path', 'sha256', 'bytes'}:
            raise ValueError('invalid encoded speech entry: ' + name)
        expected_path = speech_codec.ShippedPath(language, digest)
        if entry.get('path') != expected_path:
            raise ValueError('unexpected encoded speech path: ' + name)
        encoded_digest = entry.get('sha256')
        encoded_bytes = entry.get('bytes')
        if not isinstance(encoded_digest, str) or not HEX256.fullmatch(encoded_digest):
            raise ValueError('invalid encoded speech hash: ' + name)
        if isinstance(encoded_bytes, bool) or not isinstance(encoded_bytes, int) or encoded_bytes <= 0:
            raise ValueError('invalid encoded speech byte count: ' + name)
        previous = owners.setdefault(expected_path, (encoded_digest, encoded_bytes))
        if previous != (encoded_digest, encoded_bytes):
            raise ValueError('one shipped speech file has two encodings: ' + expected_path)

    if set(encoded) != set(clips):
        raise ValueError('encoded speech must map exactly every clip')

    by_language = {language: {'files': 0, 'bytes': 0} for language in LANGUAGES}
    for shipped, (digest, size) in owners.items():
        path = _file_under(audio_root, shipped, 'encoded speech')
        if _sha256(path) != digest:
            raise ValueError('encoded speech file does not match its manifest: ' + shipped)
        data = path.read_bytes()
        if len(data) != size:
            raise ValueError('encoded speech file does not match its manifest: ' + shipped)
        encoded_frames = speech_codec.OggVorbisFrames(data)
        sources = [clip for clip in clips.values() if encoded[clip['source']]['path'] == shipped]
        if any(encoded_frames != clip['frame_count'] for clip in sources):
            raise ValueError('encoded speech length differs from its source: ' + shipped)
        language = shipped.split('/')[2]
        by_language[language]['files'] += 1
        by_language[language]['bytes'] += size

    raw_unique = sum(unique_sources.values())
    encoded_files = sum(item['files'] for item in by_language.values())
    encoded_bytes = sum(item['bytes'] for item in by_language.values())
    return {
        'raw_source_wav': {'logical_bytes': raw_logical, 'unique_bytes': raw_unique},
        'encoded_ogg': {'files': encoded_files, 'bytes': encoded_bytes,
                        'by_language': by_language},
    }


def measure_storage(root, model_directory, encoded_manifest):
    """Return verified actual source, encoded-audio and model storage totals.

    ROOT owns manifest source paths and, by default, encoded paths are read
    from ROOT/build/app. MODEL_DIRECTORY is measured as one complete snapshot;
    symlinks, partial files, non-regular files and hard-linked duplicate model
    aliases are rejected or deduplicated. ENCODED_MANIFEST must contain clips
    and exact encodings for all three languages.
    """
    return _measure_storage(root, model_directory, encoded_manifest, None)


def _measure_storage(root, model_directory, encoded_manifest, audio_root=None):
    root = Path(root).resolve()
    resolved_audio_root = root / DEFAULT_AUDIO_ROOT if audio_root is None else Path(audio_root).resolve()
    model_directory = Path(model_directory)
    if not model_directory.is_absolute():
        model_directory = root / model_directory

    audio = _validated_manifest(encoded_manifest, root, resolved_audio_root)
    snapshot = _model_snapshot(model_directory)
    model_bytes = snapshot['bytes']
    encoded_bytes = audio['encoded_ogg']['bytes']
    total_bytes = model_bytes + encoded_bytes
    ratios = {
        'encoded_audio_to_model': encoded_bytes / model_bytes,
        'model_to_encoded_audio': model_bytes / encoded_bytes,
        'model_plus_encoded_audio_to_model': total_bytes / model_bytes,
    }
    if any(not math.isfinite(value) for value in ratios.values()):
        raise ValueError('storage ratio is not finite')
    model = dict(snapshot, copies=1, languages=list(LANGUAGES), note=MODEL_NOTE)
    return {
        'raw_source_wav': audio['raw_source_wav'],
        'encoded_ogg': audio['encoded_ogg'],
        'model': model,
        'total_bytes': total_bytes,
        'ratios': ratios,
    }


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def _arguments(argv):
    parser = _JsonArgumentParser(prog='narration_storage.py', add_help=False)
    parser.add_argument('--help', action='store_true')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--audio-root', type=Path)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    return parser.parse_args(argv)


def main(argv=None):
    try:
        arguments = _arguments(argv)
        if arguments.help:
            return {'help': 'requires --manifest and --model; --audio-root defaults to ROOT/build/app'}
        manifest = json.loads(arguments.manifest.read_text())
        return _measure_storage(arguments.root, arguments.model, manifest,
                                arguments.audio_root)
    except (OSError, ValueError, wave.Error, json.JSONDecodeError) as error:
        return {'error': str(error)}


if __name__ == '__main__':
    try:
        result = main()
    except Exception as error:
        result = {'error': str(error)}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    raise SystemExit(0 if 'error' not in result else 2)

#!/usr/bin/env python3
"""Measure narration storage from complete, byte-verified synthetic fixtures."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import wave


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import narration_storage


RATE = 22050


def write_wave(path, frames=3, samples=(400, -400, 0)):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(RATE)
        values = list(samples[:frames]) + [0] * (frames - len(samples))
        recording.writeframes(b''.join(struct.pack('<h', value) for value in values))
    return path.stat().st_size


def ogg_page(serial, sequence, flags, granule, body, lacing=(30,)):
    table = bytes(lacing)
    return (b'OggS' + bytes([0, flags]) + struct.pack('<qIII', granule, serial,
                                                       sequence, 0) + bytes([len(table)])
            + table + body)


def synthetic_ogg(frames=3):
    identification = (b'\x01vorbis' + struct.pack('<IBIiiiB', 0, 1, RATE, 0, 0, 0, 0xb8)
                      + b'\x01')
    assert len(identification) == 30
    return ogg_page(7, 0, 2, 0, identification) + ogg_page(7, 1, 4, frames, b'x', (1,))


def fixture(root, *, include_es=True, duplicate_english=True):
    root.mkdir(parents=True, exist_ok=True)
    model = root / 'model'
    model.mkdir()
    weights = b'0123456789' * 10
    (model / 'model.safetensors').write_bytes(weights)
    (model / 'tokenizer.json').write_bytes(b'tokenizer')
    (model / 'config.json').write_bytes(b'config')
    alias = model / 'model-alias.safetensors'
    alias.hardlink_to(model / 'model.safetensors')

    languages = ['en', 'de'] + (['es'] if include_es else [])
    clips = {}
    encoded = {}
    audio_sizes = {}
    raw_logical = 0
    source_sizes = {}
    for language in languages:
        source = f'assets/speech-sources/{language}/{language}.wav'
        path = root / source
        size = write_wave(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        clips[source] = {'source': source, 'language': language, 'sha256': digest,
                         'frame_count': 3, 'start_frame': 0}
        raw_logical += size
        source_sizes[digest] = size
        _add_encoded(root, clips, encoded, audio_sizes, source, language, digest)

    if duplicate_english:
        source = 'assets/speech-sources/en/repeated.wav'
        path = root / source
        path.write_bytes((root / 'assets/speech-sources/en/en.wav').read_bytes())
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        clips[source] = {'source': source, 'language': 'en', 'sha256': digest,
                         'frame_count': 3, 'start_frame': 0}
        raw_logical += path.stat().st_size
        _add_encoded(root, clips, encoded, audio_sizes, source, 'en', digest)

    manifest = {'format': 'synthetic', 'clips': clips, 'encoded': encoded,
                'encoding': dict(narration_storage.speech_codec.SETTINGS,
                                 encoder='synthetic fixture encoder'),
                'voices': {}}
    manifest_path = root / 'speech-manifest.json'
    manifest_path.write_text(json.dumps(manifest))
    return model, manifest_path, manifest, raw_logical, sum(source_sizes.values()), audio_sizes


def _add_encoded(root, clips, encoded, audio_sizes, source, language, source_digest):
    data = synthetic_ogg(clips[source]['frame_count'])
    shipped = f'assets/speech/{language}/{source_digest}.ogg'
    path = root / 'build/app' / shipped
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    path.write_bytes(data)
    encoded[source] = {'path': shipped, 'sha256': hashlib.sha256(data).hexdigest(),
                       'bytes': len(data)}
    if not existed:
        audio_sizes[language] = audio_sizes.get(language, 0) + len(data)


class NarrationStorageTest(unittest.TestCase):
    def test_measures_verified_deduplicated_storage(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'work') as name:
            root = Path(name)
            model, _, manifest, logical, unique, audio_sizes = fixture(root)
            result = narration_storage.measure_storage(root, model, manifest)
            self.assertEqual(result['raw_source_wav'],
                             {'logical_bytes': logical, 'unique_bytes': unique})
            self.assertEqual(result['encoded_ogg']['files'], 3)
            self.assertEqual(result['encoded_ogg']['bytes'], sum(audio_sizes.values()))
            for language in ('en', 'de', 'es'):
                self.assertEqual(result['encoded_ogg']['by_language'][language],
                                 {'files': 1, 'bytes': audio_sizes[language]})
            self.assertEqual(result['model']['files'], 3)
            self.assertEqual(result['model']['bytes'], 115)
            self.assertEqual(result['model']['hardlink_aliases_not_counted'], 1)
            self.assertEqual(result['model']['copies'], 1)
            self.assertEqual(result['model']['languages'], ['en', 'de', 'es'])
            self.assertIn('one multilingual model', result['model']['note'])
            self.assertEqual(result['total_bytes'], 115 + sum(audio_sizes.values()))
            encoded_bytes = sum(audio_sizes.values())
            self.assertEqual(result['ratios']['encoded_audio_to_model'], encoded_bytes / 115)
            self.assertEqual(result['ratios']['model_plus_encoded_audio_to_model'],
                             (115 + encoded_bytes) / 115)

    def test_refuses_hash_tamper_missing_and_incomplete_generation(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'work') as name:
            root = Path(name)
            model, manifest_path, manifest, *_ = fixture(root)
            first = next(iter(manifest['encoded']))
            audio = root / 'build/app' / manifest['encoded'][first]['path']
            original = audio.read_bytes()
            audio.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
            with self.assertRaisesRegex(ValueError, 'does not match its manifest'):
                narration_storage.measure_storage(root, model, manifest)
            audio.write_bytes(original)

            audio.unlink()
            with self.assertRaisesRegex(ValueError, 'encoded speech'):
                narration_storage.measure_storage(root, model, manifest)

            incomplete, _, incomplete_manifest, *_ = fixture(root / 'incomplete', include_es=False)
            with self.assertRaisesRegex(ValueError, 'missing complete languages: es'):
                narration_storage.measure_storage(root / 'incomplete', incomplete, incomplete_manifest)

            source = next(iter(manifest['clips']))
            source_path = root / source
            source_path.write_bytes(source_path.read_bytes()[:-1] + b'x')
            with self.assertRaisesRegex(ValueError, 'speech source changed'):
                narration_storage.measure_storage(root, model, manifest)

    def test_refuses_wrong_codec_settings_and_model_snapshot_aliases(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'work') as name:
            root = Path(name)
            model, _, manifest, *_ = fixture(root, duplicate_english=False)
            wrong = json.loads(json.dumps(manifest))
            wrong['encoding']['sample_rate'] = 44100
            with self.assertRaisesRegex(ValueError, 'mono 22050 Hz'):
                narration_storage.measure_storage(root, model, wrong)

            wrong = json.loads(json.dumps(manifest))
            name_key = next(key for key, clip in wrong['clips'].items() if clip['language'] == 'en')
            shipped = wrong['encoded'][name_key]['path']
            path = root / 'build/app' / shipped
            original = path.read_bytes()
            data = bytearray(path.read_bytes())
            data[39] = 2
            digest = hashlib.sha256(data).hexdigest()
            for entry in wrong['encoded'].values():
                if entry['path'] == shipped:
                    entry['sha256'] = digest
                    entry['bytes'] = len(data)
            path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'expected mono'):
                narration_storage.measure_storage(root, model, wrong)
            path.write_bytes(original)

            (model / 'unfinished.safetensors.part').write_bytes(b'partial')
            with self.assertRaisesRegex(ValueError, 'partial file'):
                narration_storage.measure_storage(root, model, manifest)
            (model / 'unfinished.safetensors.part').unlink()
            (model / 'symlink').symlink_to(model / 'model.safetensors')
            with self.assertRaisesRegex(ValueError, 'symlink'):
                narration_storage.measure_storage(root, model, manifest)

    def test_cli_uses_explicit_inputs_and_audio_root(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'work') as name:
            root = Path(name)
            model, manifest_path, manifest, *_ = fixture(root)
            audio_root = root / 'build/app'
            completed = subprocess.run(
                [sys.executable, str(ROOT / 'tools/narration_storage.py'),
                 '--manifest', str(manifest_path), '--model', str(model),
                 '--root', str(root), '--audio-root', str(audio_root)],
                check=True, capture_output=True, text=True)
            result = json.loads(completed.stdout)
            self.assertEqual(result['encoded_ogg']['files'], 3)
            self.assertEqual(completed.stderr, '')

            missing_arguments = subprocess.run(
                [sys.executable, str(ROOT / 'tools/narration_storage.py')],
                capture_output=True, text=True)
            self.assertEqual(missing_arguments.returncode, 2)
            self.assertEqual(missing_arguments.stderr, '')
            self.assertIn('--manifest', json.loads(missing_arguments.stdout)['error'])

            (audio_root / next(path for path in manifest['encoded'].values()
                               if path['path'].startswith('assets/speech/es/'))['path']).unlink()
            failed = subprocess.run(
                [sys.executable, str(ROOT / 'tools/narration_storage.py'),
                 '--manifest', str(manifest_path), '--model', str(model),
                 '--root', str(root), '--audio-root', str(audio_root)],
                capture_output=True, text=True)
            self.assertEqual(failed.returncode, 2)
            self.assertEqual(failed.stderr, '')
            self.assertIn('error', json.loads(failed.stdout))


if __name__ == '__main__':
    unittest.main()

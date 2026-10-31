#!/usr/bin/env python3
"""Shipped speech is Ogg Vorbis that the app's own decoder plays exactly.

Every canonical clip is encoded once per language and content, cached by its
source, settings and encoder, and decoded by host/sound.zi DecodeSpeech
(build/tests/speech_codec) to exactly its source's frames; damaged, wrong-shape
and over-long streams are refused before any decoder runs. The source WAVs
are never changed.
"""
import array
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import shared_assets
import speech_codec
from speech_manifest import BuildSpeechManifest

DRIVER = ROOT / 'build/tests/speech_codec'
RATE = 22050
# Waveform SNR of q4 Vorbis against the original recording. Hissing words
# such as "sink" measure about 10 dB, as the codec renders their noise as
# noise; the median is about 22 dB. Misaligned or misdecoded samples fall
# near 0 dB.
MIN_SNR_DB = 8
MEDIAN_SNR_DB = 18


def decode(path, frames, valid=True):
    """DecodeSpeech's samples for PATH, or None when it must refuse."""
    with tempfile.TemporaryDirectory(dir=ROOT / 'work') as directory:
        out = Path(directory) / 'out.pcm'
        result = subprocess.run([str(DRIVER), str(path), str(frames), str(out)])
        assert result.returncode == (0 if valid else 2), (path, frames, result.returncode)
        return array.array('h', out.read_bytes()) if valid else None


def preflight(path, frames, valid):
    result = subprocess.run([str(DRIVER), str(path), str(frames)])
    assert result.returncode == (0 if valid else 2), (path, frames, result.returncode)


def snr(decoded, source):
    error = sum((a - b) ** 2 for a, b in zip(decoded, source))
    power = sum(a * a for a in source)
    return 10 * math.log10(power / max(error, 1))


def write_wave(path, samples, rate=RATE, channels=1):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(array.array('h', samples).tobytes())


def tone(frames, frequency=330.0, rate=RATE):
    return [int(9000 * math.sin(2 * math.pi * frequency * index / rate) * (0.5 + 0.5 * math.sin(index / 900)))
            for index in range(frames)]


def encode_raw(path, samples, rate, channels, quality=4):
    raw = path.with_suffix('.raw')
    raw.write_bytes(array.array('h', samples).tobytes())
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 's16le', '-ar', str(rate), '-ac', str(channels),
                    '-i', str(raw), '-c:a', 'libvorbis', '-q:a', str(quality), '-fflags', '+bitexact',
                    '-flags:a', '+bitexact', '-map_metadata', '-1', '-f', 'ogg', str(path)], check=True)
    raw.unlink()
    return path


def clip(root, name, language):
    data = (root / name).read_bytes()
    with wave.open(str(root / name)) as source:
        frames = source.getnframes()
    return {'source': name, 'sha256': hashlib.sha256(data).hexdigest(), 'language': language,
            'start_frame': 0, 'frame_count': frames}


def stamps(cache):
    return {path.relative_to(cache).as_posix(): path.stat().st_mtime_ns
            for path in sorted(cache.rglob('*')) if path.is_file()}


def real_clips_test():
    """Every real clip: one encoding per language and content, exact decode."""
    manifest = BuildSpeechManifest()
    sources = {name: (ROOT / name).read_bytes() for name in manifest['clips']}
    encoded = speech_codec.EncodeSpeech(manifest)
    cache = ROOT / 'work/speech-codec'
    before = stamps(cache)
    again = speech_codec.EncodeSpeech(manifest)
    assert again['encoded'] == encoded['encoded'] and stamps(cache) == before, 'cache hit rewrote files'
    shipped = dict(manifest, encoding=encoded['encoding'], encoded=encoded['encoded'])
    speech_codec.ValidateEncodedSpeech(shipped, encoded['files'])
    assert encoded['encoding'] == dict(speech_codec.SETTINGS, encoder=speech_codec.Encoder())
    assert speech_codec.SETTINGS == {'codec': 'vorbis', 'container': 'ogg', 'quality': 4,
                                     'channels': 1, 'sample_rate': RATE, 'page_duration_us': 20000}
    units = {(clip['language'], clip['sha256']) for clip in manifest['clips'].values()}
    assert len(encoded['files']) == len(units)
    languages = {}
    for name, entry in encoded['encoded'].items():
        language = manifest['clips'][name]['language']
        assert entry['path'] == f'assets/speech/{language}/{manifest["clips"][name]["sha256"]}.ogg', name
        assert languages.setdefault(entry['path'], language) == language, 'shared across languages'
    lowest = []
    for index, (name, clip_data) in enumerate(sorted(manifest['clips'].items())):
        path = encoded['files'][encoded['encoded'][name]['path']]
        frames = clip_data['frame_count']
        assert 0 < frames <= RATE * 60
        assert speech_codec.OggVorbisFrames(path.read_bytes()) == frames, name
        samples = decode(path, frames)
        assert len(samples) == frames, name
        if index % 9 == 0:
            with wave.open(str(ROOT / name)) as source:
                original = array.array('h', source.readframes(source.getnframes()))
            lowest.append((snr(samples, original), name))
    lowest.sort()
    assert lowest[0][0] >= MIN_SNR_DB, lowest[:3]
    assert lowest[len(lowest) // 2][0] >= MEDIAN_SNR_DB, lowest[len(lowest) // 2]
    # Shipping: every encoded file once, and no speech WAV beside it.
    installed, _, bundles = shared_assets.Plan(shipped, encoded['files'])
    represented = set(manifest['clips']) | set(manifest['voices'])
    assert set(encoded['files']) <= set(installed)
    assert not represented & set(installed)
    assert all(not represented & set(files) for files in bundles.values())
    assert not any(path.startswith('assets/speech/') and not path.endswith('.ogg') for path in installed)
    # The encoder only read its sources.
    assert all((ROOT / name).read_bytes() == data for name, data in sources.items())
    wav_bytes = sum(len(data) for data in sources.values())
    ogg_bytes = sum(path.stat().st_size for path in encoded['files'].values())
    return len(manifest['clips']), len(encoded['files']), wav_bytes, ogg_bytes, lowest[0][0]


def cache_test(work):
    """Sharing, cache hits, tampering, source, settings and encoder changes."""
    root = work / 'repo'
    words = tone(RATE // 3)
    for name in ('assets/en/a.wav', 'assets/en/b.wav', 'assets/de/a.wav'):
        write_wave(root / name, words)
    write_wave(root / 'assets/en/c.wav', tone(RATE // 2, 523.0))
    manifest = {'clips': {name: clip(root, name, name.split('/')[1])
                          for name in ('assets/en/a.wav', 'assets/en/b.wav', 'assets/de/a.wav', 'assets/en/c.wav')}}
    cache = root / 'work/speech-codec'
    result = speech_codec.EncodeSpeech(manifest, root)
    # Identical English recordings share one file; German keeps its own.
    paths = {name: entry['path'] for name, entry in result['encoded'].items()}
    assert paths['assets/en/a.wav'] == paths['assets/en/b.wav'] != paths['assets/de/a.wav']
    assert len(result['files']) == 3 and len(list(cache.rglob('*.ogg'))) == 3
    english = result['files'][paths['assets/en/a.wav']]
    good = english.read_bytes()
    receipt = english.with_suffix('.json')
    record = json.loads(receipt.read_text())
    assert record['sha256'] == hashlib.sha256(good).hexdigest() and record['settings'] == speech_codec.SETTINGS
    assert record['source_sha256'] == manifest['clips']['assets/en/a.wav']['sha256']
    samples = decode(english, len(words))
    assert snr(samples, words) >= 20
    before = stamps(cache)
    assert speech_codec.EncodeSpeech(manifest, root)['encoded'] == result['encoded']
    assert stamps(cache) == before, 'a cache hit wrote files'

    def reencoded(change):
        change()
        speech_codec.EncodeSpeech(manifest, root)
        assert english.read_bytes() == good and json.loads(receipt.read_text()) == record
        assert english.stat().st_mtime_ns != before['en/' + english.name], 'not encoded again'

    damaged = bytearray(good)
    damaged[len(good) // 2] ^= 0x20
    reencoded(lambda: english.write_bytes(bytes(damaged)))
    reencoded(lambda: receipt.write_text(json.dumps(dict(record, frames=record['frames'] + 1))))
    reencoded(lambda: receipt.write_text('{'))
    reencoded(receipt.unlink)
    reencoded(english.unlink)

    # Other settings or another encoder are other encodings.
    original_settings, original_encoder = speech_codec.SETTINGS, dict(speech_codec._ENCODER)
    try:
        speech_codec.SETTINGS = dict(original_settings, quality=2)
        lower = speech_codec.EncodeSpeech(manifest, root)
        assert lower['encoded']['assets/en/a.wav']['sha256'] != record['sha256']
        assert json.loads(receipt.read_text())['settings']['quality'] == 2
        speech_codec.SETTINGS = original_settings
        speech_codec._ENCODER['identity'] = original_encoder['identity'] + ' (other build)'
        speech_codec.EncodeSpeech(manifest, root)
        assert json.loads(receipt.read_text())['encoder'].endswith('(other build)')
    finally:
        speech_codec.SETTINGS = original_settings
        speech_codec._ENCODER.clear()
        speech_codec._ENCODER.update(original_encoder)
    speech_codec.EncodeSpeech(manifest, root)
    assert english.read_bytes() == good

    # A source that is not its manifest clip is refused and nothing is written.
    before = stamps(cache)
    source = root / 'assets/en/c.wav'
    kept = source.read_bytes()
    # Changed content under the old hash; then wrong shapes even with a new one.
    for change, shape in ((lambda: write_wave(source, tone(RATE // 2, 600.0)), False),
                          (lambda: write_wave(source, tone(RATE // 2, 523.0) * 2, channels=2), True),
                          (lambda: write_wave(source, tone(RATE // 2, 523.0), rate=44100), True)):
        change()
        stale = dict(manifest['clips']['assets/en/c.wav'])
        refreshed = dict(clip(root, 'assets/en/c.wav', 'en'), frame_count=stale['frame_count'])
        for refreshed in (stale, refreshed) if shape else (stale,):
            try:
                speech_codec.EncodeSpeech({'clips': dict(manifest['clips'], **{'assets/en/c.wav': refreshed})}, root)
            except ValueError:
                pass
            else:
                raise AssertionError('accepted a changed or wrong-shape source')
        source.write_bytes(kept)
    assert stamps(cache) == before
    # Over a minute is refused before encoding.
    long_name = 'assets/en/long.wav'
    write_wave(root / long_name, [0] * (RATE * 60 + 1))
    try:
        speech_codec.EncodeSpeech({'clips': {long_name: clip(root, long_name, 'en')}}, root)
    except ValueError:
        pass
    else:
        raise AssertionError('accepted more than a minute of speech')

    # The cache lives in the owning repo's ignored work/, never elsewhere.
    for bad in (root / 'assets/cache', root / 'work', work / 'elsewhere'):
        try:
            speech_codec.EncodeSpeech(manifest, root, bad)
        except ValueError:
            assert not bad.exists() or bad == root / 'work'
        else:
            raise AssertionError('accepted cache ' + str(bad))
    (root / 'work/linked').symlink_to(work / 'outside', target_is_directory=True)
    try:
        speech_codec.EncodeSpeech(manifest, root, root / 'work/linked/cache')
    except ValueError:
        assert not (work / 'outside').exists()
    else:
        raise AssertionError('accepted a cache through a symlink')

    # The shipped manifest must name exactly these files, unchanged.
    shipped = dict(manifest, encoding=result['encoding'], encoded=result['encoded'])
    speech_codec.ValidateEncodedSpeech(shipped, result['files'])
    german = paths['assets/de/a.wav']
    for broken, files in (
            (dict(shipped, encoded={k: v for k, v in result['encoded'].items() if k != 'assets/en/c.wav'}),
             result['files']),
            (dict(shipped, encoded=dict(result['encoded'], **{'assets/en/a.wav': dict(
                result['encoded']['assets/en/a.wav'], path=german)})), result['files']),
            (dict(shipped, encoding=dict(result['encoding'], quality=5)), result['files']),
            (shipped, dict(result['files'], **{german: result['files'][paths['assets/en/c.wav']]})),
            (shipped, {k: v for k, v in result['files'].items() if k != german})):
        try:
            speech_codec.ValidateEncodedSpeech(broken, files)
        except ValueError:
            continue
        raise AssertionError('accepted a broken encoded speech mapping')
    return english, len(words)


def decoder_test(work, good, frames):
    """DecodeSpeech decodes exactly; everything else is refused, before any
    platform decoder for anything its pages already rule out."""
    decode(good, frames)
    preflight(good, frames, True)
    data = good.read_bytes()
    for wrong in (frames - 1, frames + 1, 0, -1, RATE * 60 + 1):
        decode(good, wrong, False)
        preflight(good, wrong, False)
    bad = work / 'bad.ogg'
    flipped = bytearray(data)
    flipped[len(data) // 2] ^= 0xFF
    # Damaged pages pass the page check but not the decoder's CRC.
    for label, content, ruled_out in (
            ('empty', b'', True), ('wav', (ROOT / 'assets/jungle-book/sounds/en/simple/tiger.wav').read_bytes(), True),
            ('truncated', data[:len(data) // 2], True), ('trailing', data + b'\0' * 8, True),
            ('chained', data + data, True), ('flipped', bytes(flipped), False)):
        bad.write_bytes(content)
        decode(bad, frames, False)
        preflight(bad, frames, not ruled_out)
    shapes = (('stereo', tone(frames) * 2, RATE, 2, frames), ('44100 Hz', tone(frames * 2), 44100, 1, frames * 2),
              ('over a minute', tone(RATE * 61), RATE, 1, RATE * 61))
    for label, samples, rate, channels, length in shapes:
        encode_raw(bad, samples, rate, channels)
        assert len(samples) // channels == length
        for claimed in {length, min(length, RATE * 60), frames}:
            decode(bad, claimed, False)
            preflight(bad, claimed, False)
    # Within a minute and the right shape, but larger than any speech clip.
    noise = [(index * 7919 % 65521) - 32760 for index in range(RATE * 59)]
    encode_raw(bad, noise, RATE, 1, quality=10)
    assert bad.stat().st_size > shared_bytes_limit(), bad.stat().st_size
    assert speech_codec.OggVorbisFrames(bad.read_bytes()) == RATE * 59
    decode(bad, RATE * 59, False)
    preflight(bad, RATE * 59, False)


def shared_bytes_limit():
    text = (ROOT / 'host/sound.zi').read_text()
    return int(text.split('SPEECH_BYTES_LIMIT :: ', 1)[1].split()[0])


def main():
    if not shutil.which('ffmpeg'):
        raise SystemExit('speech codec test needs ffmpeg with libvorbis')
    subprocess.run(['make', '--no-print-directory', '-s', str(DRIVER.relative_to(ROOT))], cwd=ROOT, check=True)
    (ROOT / 'work').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='speech-codec-', dir=ROOT / 'work') as directory:
        work = Path(directory)
        good, frames = cache_test(work)
        decoder_test(work, good, frames)
    clips, files, wav_bytes, ogg_bytes, lowest = real_clips_test()
    print(f'local speech codec test: {clips} clips as {files} Ogg Vorbis files, '
          f'{wav_bytes / 1e6:.1f} MB WAV to {ogg_bytes / 1e6:.1f} MB, every decode exact, '
          f'lowest sampled SNR {lowest:.1f} dB; cache, tampering, sources and malformed streams passed')


if __name__ == '__main__':
    main()

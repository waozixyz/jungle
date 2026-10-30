#!/usr/bin/env python3
"""Build a lossless speech manifest for Jungle's narration paths.

The manifest is intentionally host-neutral. Clip entries name verified source
WAV files and exact signed-PCM frame ranges; voice entries keep every existing
runtime path and describe its playback as those ranges and integer silent
gaps. Nothing in this phase changes the source recordings or their receipts.
"""
import hashlib
import json
from pathlib import Path
import re
import sys
import wave

from book_catalog import LANGUAGES, NAMES, WORDS, voice_path
from book_speech import read_clip


ROOT = Path(__file__).resolve().parents[1]
# Hosts read assets/speech.txt; staging keeps this whole manifest for audits.
MANIFEST_PATH = 'build/stage/speech-manifest.json'
FORMAT = 'jungle-speech-manifest-1'
PCM_FORMAT = {
    'encoding': 'PCM signed 16-bit little-endian',
    'channels': 1,
    'sample_rate': 22050,
}


def _relative(path, root):
    return path.resolve().relative_to(root).as_posix()


def _receipt(path):
    receipt_path = path.with_suffix('.speech.json')
    assert receipt_path.is_file(), receipt_path
    receipt = json.loads(receipt_path.read_text())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == receipt['sha256'], path
    return receipt, digest


def _wave_pcm(path):
    receipt, digest = _receipt(path)
    with wave.open(str(path)) as source:
        channels, width, rate, frames = (source.getnchannels(), source.getsampwidth(),
                                         source.getframerate(), source.getnframes())
        if (channels, width, rate) != (1, 2, 22050):
            raise ValueError(f'expected mono signed PCM16 at 22050 Hz: {path}')
        if not 0 < frames <= rate * 60:
            raise ValueError(f'source outside the 60 second speech bound: {path}')
        pcm = source.readframes(frames)
        if len(pcm) != frames * 2:
            raise ValueError(f'truncated or padded speech WAV: {path}')
        return pcm, digest, receipt


def _trimmed_range(path, root):
    data, digest = read_clip(path)
    with wave.open(str(path)) as source:
        samples = source.getnframes()
        pcm = source.readframes(samples)
    values = memoryview(pcm).cast('h')
    audible = [index for index, value in enumerate(values) if abs(value) > 180]
    assert audible, path
    first = max(0, audible[0] - 1102)
    last = min(samples, audible[-1] + 2205)
    assert data == pcm[first * 2:last * 2], path
    return first, last - first, digest


def _whole_clip(path, language, root):
    pcm, digest, _ = _wave_pcm(path)
    return {
        'source': _relative(path, root),
        'sha256': digest,
        'language': language,
        'start_frame': 0,
        'frame_count': len(pcm) // 2,
    }, pcm


def _add_clip(clips, clip_data, pcm):
    source = clip_data['source']
    if source in clips:
        assert clips[source] == clip_data, source
    else:
        clips[source] = clip_data
    return source


def _segment(clip):
    return {'clip': clip['source'], 'start': clip['start_frame'], 'frames': clip['frame_count']}


def _range_segment(source, start, frames):
    return {'clip': source, 'start': start, 'frames': frames}


def _pcm_range(path, clip, start, frames, root):
    pcm, digest, _ = _wave_pcm(root / clip['source'])
    assert digest == clip['sha256'], path
    assert 0 <= start and 0 < frames and start + frames <= len(pcm) // 2, clip['source']
    return pcm[start * 2:(start + frames) * 2]


def _book_voices(clips, voices, root):
    assembled = 0
    recorded_spelling = 0
    for language_index, language in enumerate(LANGUAGES):
        for name in NAMES:
            simple = root / voice_path(name, language, True)
            simple_clip, _ = _whole_clip(simple, language, root)
            _add_clip(clips, simple_clip, None)
            voices[_relative(simple, root)] = [_segment(simple_clip)]
            simple_start, simple_frames, simple_digest = _trimmed_range(simple, root)
            assert simple_digest == simple_clip['sha256'], simple

            spelling = root / voice_path(name, language, False)
            receipt, digest = _receipt(spelling)
            if 'PCM assembly' not in receipt.get('method', ''):
                whole_clip, _ = _whole_clip(spelling, language, root)
                _add_clip(clips, whole_clip, None)
                voices[_relative(spelling, root)] = [_segment(whole_clip)]
                recorded_spelling += 1
                continue

            expected_sources = [entry['path'] for entry in receipt['sources']]
            expected_hashes = [entry['sha256'] for entry in receipt['sources']]
            assert expected_sources[0] == _relative(simple, root), spelling
            simple_name = _relative(simple, root)
            word = _range_segment(simple_name, simple_start, simple_frames)
            segments = [word, {'silence': 11025}]
            source_index = 1
            for letter in WORDS[name][language_index].lower():
                if letter.isspace():
                    segments.append({'silence': 7350})
                    continue
                source = root / expected_sources[source_index]
                source_start, source_frames, source_digest = _trimmed_range(source, root)
                source_clip = clips.get(expected_sources[source_index])
                if source_clip is None:
                    source_clip, _ = _whole_clip(source, language, root)
                    _add_clip(clips, source_clip, None)
                assert source_clip['source'] == expected_sources[source_index], spelling
                assert source_clip['sha256'] == expected_hashes[source_index] == source_digest, spelling
                segments.extend((_range_segment(source_clip['source'], source_start, source_frames),
                                 {'silence': 5512}))
                source_index += 1
            assert source_index == len(expected_sources), spelling
            segments.extend(({'silence': 5512}, word))

            reconstructed = b''.join(
                bytes(segment['silence'] * 2) if 'silence' in segment
                else _pcm_range(spelling, clips[segment['clip']], segment['start'], segment['frames'], root)
                for segment in segments
            )
            original, original_digest, original_receipt = _wave_pcm(spelling)
            assert original_digest == digest == original_receipt['sha256'], spelling
            assert original == reconstructed, (
                spelling,
                next((index for index, (left, right) in enumerate(zip(original, reconstructed)) if left != right), None),
                len(original), len(reconstructed),
            )
            voices[_relative(spelling, root)] = segments
            assembled += 1

    return assembled, recorded_spelling


def _book_letter_clips(clips, root):
    pattern = re.compile(r'^assets/jungle-book/sounds/(en|de|es)/letters/([0-9a-f]{4})\.wav$')
    paths = sorted((root / 'assets/jungle-book/sounds').glob('*/letters/*.wav'))
    for path in paths:
        name = _relative(path, root)
        match = pattern.match(name)
        assert match, name
        clip, _ = _whole_clip(path, match.group(1), root)
        _add_clip(clips, clip, None)


def _alphabet_voices(clips, voices, root):
    total = 0
    pattern = re.compile(r'^assets/abc/sounds/(en|de|es)/letters/([0-9a-f]{4})\.speech\.json$')
    for receipt_path in sorted((root / 'assets/abc/sounds').glob('*/letters/*.speech.json')):
        name = _relative(receipt_path, root)
        match = pattern.match(name)
        assert match, name
        language, code = match.groups()
        abc_path = root / (name[:-len('.speech.json')] + '.wav')
        _wave_pcm(abc_path)
        book_path = root / f'assets/jungle-book/sounds/{language}/letters/{code}.wav'
        clip, _ = _whole_clip(book_path, language, root)
        _add_clip(clips, clip, None)
        voices[_relative(abc_path, root)] = [_segment(clip)]
        total += 1
    return total


def _recorded_voices(clips, voices, root):
    paths = sorted((root / 'assets/numbers/sounds').glob('*/*.wav'))
    paths += sorted((root / 'assets/animal-count/sounds').glob('question-*.wav'))
    for path in paths:
        name = _relative(path, root)
        language = name.split('/')[-2] if '/numbers/' in name else name.rsplit('-', 1)[-1].removesuffix('.wav')
        assert language in LANGUAGES, name
        clip, _ = _whole_clip(path, language, root)
        _add_clip(clips, clip, None)
        voices[name] = [_segment(clip)]
    return len(paths)


def _safe_asset_path(name):
    path = Path(name)
    return (isinstance(name, str) and name.startswith('assets/') and not path.is_absolute()
            and all(part not in ('', '.', '..') for part in name.split('/'))
            and all(character not in name for character in ('|', '\n', '\\')))


def ValidateSpeechManifest(manifest, root=ROOT):
    """Reject unsafe paths, bad ranges, missing receipts, or changed sources."""
    root = Path(root).resolve()
    if manifest.get('format') != FORMAT or manifest.get('audio') != PCM_FORMAT:
        raise ValueError('unsupported speech manifest format')
    clips, voices = manifest.get('clips'), manifest.get('voices')
    if not isinstance(clips, dict) or not isinstance(voices, dict) or not clips or not voices:
        raise ValueError('speech manifest clips and voices must be nonempty objects')
    for name, clip in clips.items():
        if not _safe_asset_path(name) or clip.get('source') != name:
            raise ValueError('unsafe or mismatched speech clip path: ' + repr(name))
        if clip.get('language') not in LANGUAGES:
            raise ValueError('unknown speech language: ' + name)
        source = root / name
        pcm, digest, _ = _wave_pcm(source)
        frames = len(pcm) // 2
        start, count = clip.get('start_frame'), clip.get('frame_count')
        if type(start) is not int or type(count) is not int:
            raise ValueError('non-integer speech clip range: ' + name)
        if start != 0:
            raise ValueError('speech clips must describe their whole source: ' + name)
        if not 0 <= start or not 0 < count or start + count > frames:
            raise ValueError('speech clip range exceeds source: ' + name)
        if digest != clip.get('sha256'):
            raise ValueError('speech clip hash changed: ' + name)
    for name, segments in voices.items():
        if not _safe_asset_path(name) or not isinstance(segments, list) or not segments:
            raise ValueError('unsafe or empty speech voice: ' + repr(name))
        original, _, _ = _wave_pcm(root / name)
        reconstructed = []
        exact = len(segments) > 1
        total_frames = 0
        for segment in segments:
            if set(segment) == {'silence'}:
                silence = segment['silence']
                if type(silence) is not int or not 0 < silence <= 22050 * 60:
                    raise ValueError('invalid speech silence: ' + name)
                reconstructed.append(bytes(silence * 2))
                total_frames += silence
                exact = True
                continue
            if set(segment) != {'clip', 'start', 'frames'}:
                raise ValueError('unknown speech segment: ' + name)
            clip_name, start, frames = segment['clip'], segment['start'], segment['frames']
            if type(start) is not int or type(frames) is not int or not 0 <= start or not 0 < frames:
                raise ValueError('invalid speech segment range: ' + name)
            clip = clips[clip_name]
            if start < clip['start_frame'] or start + frames > clip['start_frame'] + clip['frame_count']:
                raise ValueError('speech segment exceeds clip: ' + name)
            reconstructed.append(_pcm_range(root / name, clip, start, frames, root))
            total_frames += frames
        if not 0 < total_frames <= 22050 * 60:
            raise ValueError('speech voice outside the 60 second bound: ' + name)
        if exact:
            if original != b''.join(reconstructed):
                raise ValueError('speech recipe does not reconstruct original PCM: ' + name)


def BuildSpeechManifest(root=ROOT, extra_voices=()):
    """Validate and describe all narrated paths used by the speech phase."""
    root = Path(root).resolve()
    clips, voices = {}, {}
    assembled, recorded_spelling = _book_voices(clips, voices, root)
    _book_letter_clips(clips, root)
    alphabet = _alphabet_voices(clips, voices, root)
    recorded = _recorded_voices(clips, voices, root)
    # Further whole recordings, as {path: language} or paths in a language folder.
    for name in extra_voices:
        path = root / name
        language = next((part for part in Path(name).parts if part in LANGUAGES), None)
        if isinstance(extra_voices, dict):
            assert extra_voices[name] == language, (name, extra_voices[name])
        assert language and _safe_asset_path(name), name
        clip, _ = _whole_clip(path, language, root)
        _add_clip(clips, clip, None)
        voices[name] = [_segment(clip)]
        recorded += 1
    return {
        'format': FORMAT,
        'audio': PCM_FORMAT,
        'shipping': {
            'manifest': MANIFEST_PATH,
            'clips': 'Ship each clips key at that exact source path.',
            'voices': 'Resolve voice keys from segments; a missing voice path is expected when it is not also a clip key.',
        },
        'clips': dict(sorted(clips.items())),
        'voices': dict(sorted(voices.items())),
        'counts': {
            'assembled_lessons': assembled,
            'recorded_spelling_lessons': recorded_spelling,
            'alphabet_letters': alphabet,
            'recorded_voices': recorded,
            'clips': len(clips),
            'voices': len(voices),
        },
    }


if __name__ == '__main__':
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'build/speech-manifest.json'
    manifest = BuildSpeechManifest()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + '.new')
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')) + '\n')
    temporary.replace(output)
    print('speech manifest: ' + ', '.join(f'{name} {count}' for name, count in manifest['counts'].items()))

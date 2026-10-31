"""Speech recipes reconstruct exactly without changing source recordings."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import shared_assets
from book_catalog import LANGUAGES, LETTERS, NAMES, LEARNING, UNIQUE, voice_path
from book_speech import read_clip
import speech_codec
import speech_manifest


def pcm(path):
    with wave.open(str(path)) as source:
        return source.readframes(source.getnframes())


def rebuild(manifest, segments):
    parts = []
    for segment in segments:
        if 'silence' in segment:
            parts.append(bytes(segment['silence'] * 2))
            continue
        clip = manifest['clips'][segment['clip']]
        data = pcm(ROOT / clip['source'])
        parts.append(data[segment['start'] * 2:(segment['start'] + segment['frames']) * 2])
    return b''.join(parts)


def language_for(name):
    parts = Path(name).parts
    if name.startswith('assets/jungle-book/sounds/') and parts[3] not in LANGUAGES:
        return 'en'
    if any(name.endswith(f'-{language}.wav') for language in LANGUAGES):
        return next(language for language in LANGUAGES if name.endswith(f'-{language}.wav'))
    return next(part for part in parts if part in LANGUAGES)


def verify_legacy_lettuce():
    path = ROOT / 'assets/jungle-book/sounds/de/spelling/lettuce.wav'
    receipt = json.loads(path.with_suffix('.speech.json').read_text())
    assert 'PCM assembly' in receipt['method'], path
    assert hashlib.sha256(path.read_bytes()).hexdigest() == receipt['sha256'], path
    phrases = receipt['text'].split('. ')
    word = phrases[0]
    assert phrases[-1] == word + '.', receipt['text']
    letters = [letter for letter in word.lower() if not letter.isspace()]
    expected_text = f'{word}. ' + '. '.join(LETTERS['de'][letter] for letter in letters) + f'. {word}.'
    assert receipt['text'] == expected_text, (receipt['text'], expected_text)

    sources = [f'assets/jungle-book/sounds/de/letters/{ord(letter):04x}.wav'
               for letter in letters]
    assert [entry['path'] for entry in receipt['sources']] == ['assets/jungle-book/sounds/de/simple/lettuce.wav', *sources], path
    parts = []
    for entry, letter in zip(receipt['sources'], (None, *letters)):
        source = ROOT / entry['path']
        data, source_hash = read_clip(source)
        assert source_hash == entry['sha256'], entry['path']
        parts.append(data)
        if letter is None:
            parts.append(bytes(22050 // 2 * 2))
        else:
            parts.append(bytes(22050 // 4 * 2))
    parts.extend((bytes(22050 // 4 * 2), parts[0]))
    with wave.open(str(path)) as voice:
        assert (voice.getnchannels(), voice.getsampwidth(), voice.getframerate()) == (1, 2, 22050), path
        assert voice.readframes(voice.getnframes()) == b''.join(parts), path


def real_catalog_test():
    manifest = speech_manifest.BuildSpeechManifest()
    assert manifest['counts'] == {
        'assembled_lessons': 726, 'recorded_spelling_lessons': 126,
        'alphabet_letters': 83, 'recorded_voices': 63,
        'clips': 1130, 'voices': 1850,
    }
    speech_manifest.ValidateSpeechManifest(manifest)
    book_voices = {voice_path(name, language, simple)
                   for language in LANGUAGES for simple in (False, True) for name in NAMES}
    spelling_voices = {voice_path(name, language, False) for language in LANGUAGES for name in NAMES}
    alphabet = {path.relative_to(ROOT).as_posix()
                for path in (ROOT / 'assets/abc/sounds').glob('*/letters/*.wav')}
    numbers = {path.relative_to(ROOT).as_posix() for path in (ROOT / 'assets/numbers/sounds').glob('*/*.wav')}
    questions = {path.relative_to(ROOT).as_posix()
                 for path in (ROOT / 'assets/animal-count/sounds').glob('question-*.wav')}
    assert set(manifest['voices']) == book_voices | alphabet | numbers | questions

    new_lessons = {voice_path(name, language, False)
                   for language in LANGUAGES
                   for name in (*LEARNING['words'], *UNIQUE['words'])}
    new_lessons.update(voice_path(name, language, False)
                       for name, languages in UNIQUE['voice_stems'].items()
                       for language in languages)
    assembled = recorded_spelling = original_assembled = new_assembled = 0
    for path in sorted((ROOT / 'assets/jungle-book/sounds').glob('**/*.speech.json')):
        voice = Path(str(path)[:-len('.speech.json')] + '.wav')
        name = voice.relative_to(ROOT).as_posix()
        if '/letters/' in name or name not in spelling_voices:
            continue
        receipt = json.loads(path.read_text())
        assert hashlib.sha256(voice.read_bytes()).hexdigest() == receipt['sha256'], name
        segments = manifest['voices'][name]
        if 'PCM assembly' not in receipt.get('method', ''):
            recorded_spelling += 1
            assert len(segments) == 1 and segments[0]['start'] == 0
            assert segments[0]['frames'] == len(pcm(voice)) // 2, name
            continue
        assembled += 1
        if name in new_lessons:
            new_assembled += 1
        else:
            original_assembled += 1
        assert any('silence' in segment for segment in segments), name
        assert pcm(voice) == rebuild(manifest, segments), name
    assert assembled == 726, assembled
    assert original_assembled == 506, original_assembled
    assert new_assembled == 220, new_assembled
    assert recorded_spelling == 126, recorded_spelling
    verify_legacy_lettuce()
    assert original_assembled + 1 == 507

    letters = {name for name in manifest['clips'] if '/letters/' in name}
    assert len(letters) == 89
    assert sum(name.startswith('assets/jungle-book/sounds/en/letters/') for name in letters) == 26
    assert sum(name.startswith('assets/jungle-book/sounds/de/letters/') for name in letters) == 30
    assert sum(name.startswith('assets/jungle-book/sounds/es/letters/') for name in letters) == 33
    for name in alphabet:
        segment = manifest['voices'][name][0]
        assert segment['start'] == 0
        assert segment['frames'] == len(pcm(ROOT / name)) // 2
        assert pcm(ROOT / name) == pcm(ROOT / segment['clip'])
    for name, segments in manifest['voices'].items():
        language = language_for(name)
        assert all(manifest['clips'][segment['clip']]['language'] == language
                   for segment in segments if 'clip' in segment), name
    return manifest


def rejection_test(manifest):
    name = next(iter(manifest['clips']))
    unsafe = copy.deepcopy(manifest)
    unsafe['clips']['/etc/passwd'] = unsafe['clips'].pop(name)
    out_of_bounds = copy.deepcopy(manifest)
    out_of_bounds['clips'][name]['frame_count'] += 1
    bad_segment = copy.deepcopy(manifest)
    voice = next(iter(bad_segment['voices']))
    bad_segment['voices'][voice][0]['frames'] += 1
    for broken in (unsafe, out_of_bounds, bad_segment):
        try:
            speech_manifest.ValidateSpeechManifest(broken)
        except ValueError:
            continue
        raise AssertionError('accepted malformed speech manifest')


def staging_test():
    original_root = shared_assets.ROOT
    with tempfile.TemporaryDirectory(prefix='speech-stage-', dir=ROOT / 'build') as directory:
        root = Path(directory)
        source, app, stage = root / 'source', root / 'app', root / 'stage'
        for name in shared_assets.COUNTING:
            path = source / f'assets/jungle-book/counting/{name}.png'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())
        for name, data in (('assets/jungle-book/items/tiger.png', b'item'),
                           ('assets/jungle-book/previews/jungle.jpg', b'preview')):
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        files = {
            'assets/jungle/font.png': b'font',
            'assets/jungle-book/font.png': b'font',
            'assets/jungle-book/pages/tiger.jpg': b'page',
            'assets/jungle-book/sounds/tiger.wav': b'assembled',
            'assets/jungle-book/sounds/en/letters/0061.wav': b'canonical letter',
            'assets/abc/sounds/en/letters/0061.wav': b'duplicate letter',
            'assets/numbers/sounds/one.wav': b'number',
            'assets/animal-count/font.png': b'counting font',
            'assets/hide_seek/scenes/cottage-yard.png': b'grounded shared scene',
        }
        for name, data in files.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        clip = {'source': 'assets/jungle-book/sounds/en/letters/0061.wav',
                'sha256': hashlib.sha256(b'canonical letter').hexdigest(), 'language': 'en',
                'start_frame': 0, 'frame_count': 1}
        number_clip = {'source': 'assets/numbers/sounds/one.wav',
                       'sha256': hashlib.sha256(b'number').hexdigest(), 'language': 'en',
                       'start_frame': 0, 'frame_count': 1}
        speech = {'format': speech_manifest.FORMAT, 'audio': speech_manifest.PCM_FORMAT,
                  'clips': {clip['source']: clip, number_clip['source']: number_clip},
                  'voices': {
                      'assets/jungle-book/sounds/tiger.wav': [{'clip': clip['source'], 'start': 0, 'frames': 1}],
                      'assets/abc/sounds/en/letters/0061.wav': [{'clip': clip['source'], 'start': 0, 'frames': 1}],
                      'assets/numbers/sounds/one.wav': [{'clip': number_clip['source'], 'start': 0, 'frames': 1}],
                  }}
        # Stand-in encodings: tests/speech_codec_test.py encodes real ones.
        encoded_files, encoded = {}, {}
        for name, entry in speech['clips'].items():
            shipped = f'assets/speech/en/{entry["sha256"]}.ogg'
            data = b'encoded ' + name.encode()
            encoded_files[shipped] = root / 'encoded' / (entry['sha256'] + '.ogg')
            encoded_files[shipped].parent.mkdir(parents=True, exist_ok=True)
            encoded_files[shipped].write_bytes(data)
            encoded[name] = {'path': shipped, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
        encoding = dict(speech_codec.SETTINGS, encoder='test')
        shipped = dict(speech, encoding=encoding, encoded=encoded)
        # A stale WAV and a removed clip from an earlier build.
        for name in ('assets/jungle-book/sounds/tiger.wav', 'assets/speech/en/old.ogg'):
            (app / name).parent.mkdir(parents=True, exist_ok=True)
            (app / name).write_bytes(b'old')
        shared_assets.ROOT = source
        try:
            installed, _, bundles = shared_assets.StageSharedAssets(app, stage, (shipped, encoded_files))
        finally:
            shared_assets.ROOT = original_root
        # Each clip ships once, encoded; no speech WAV ships beside it.
        assert set(encoded_files) <= set(installed)
        assert not {path for path in installed if path.endswith('.wav')}
        shipped_files = {path.relative_to(app).as_posix() for path in app.rglob('*') if path.is_file()}
        assert not {path for path in shipped_files if path.endswith('.wav')}, shipped_files
        assert 'assets/speech/en/old.ogg' not in shipped_files
        assert (app / next(iter(encoded_files))).read_bytes().startswith(b'encoded ')
        assert all('assets/abc/sounds/en/letters/0061.wav' not in files for files in bundles.values())
        assert all('assets/numbers/sounds/one.wav' not in files for files in bundles.values())
        staged = json.loads((stage / shared_assets.SPEECH_MANIFEST).read_text())
        assert staged['clips'] == speech['clips'] and staged['voices'] == speech['voices']
        assert staged['encoded'] == encoded and staged['encoding'] == encoding
        index = (app / shared_assets.SPEECH_INDEX).read_text()
        assert index == shared_assets.SpeechIndexText(shipped) and index.startswith(shared_assets.SPEECH_HEADER)
        letter = sorted(encoded_files).index(encoded[clip['source']]['path'])
        assert f'voice|assets/abc/sounds/en/letters/0061.wav|{letter}:0:1\n' in index, index
        assert not (stage / '.speech-assets').exists()


def main():
    rejection_test(real_catalog_test())
    staging_test()
    print('local speech manifest test: 726 exact active lessons (506 original + 220 new), one preserved original lesson, 126 whole recordings, 83 alphabet voices, 89 letter clips passed')


if __name__ == '__main__':
    main()

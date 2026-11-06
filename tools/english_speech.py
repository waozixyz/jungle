"""Reproduce Jungle's English Bella recordings with the local CPU Kokoro pack.

Run with speech/.venv/bin/python tools/book_speech.py --bella. No downloads,
network provider, global preferences or time stretching are involved.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import wave

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / 'tools/english_speech_corpus.json'
PROFILES = {'slow': 0.65, 'normal': 0.8, 'fast': 1.0}
RATE = 22050


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.new')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def profile_path(name, profile):
    return name if profile == 'normal' else f'assets/speech-profiles/{profile}/' + name.removeprefix('assets/')


def capture_corpus():
    """Freeze original texts/IDs and assembly dependencies before replacing audio."""
    if CORPUS.exists():
        return json.loads(CORPUS.read_text())
    corpus = {}
    for path in sorted((ROOT / 'assets').rglob('*.speech.json')):
        if 'speech-profiles' in path.parts:
            continue
        if not ('en' in path.parts or path.name.endswith('-en.speech.json')
                or path.parent == ROOT / 'assets/jungle-book/sounds'):
            continue
        receipt = json.loads(path.read_text())
        name = path.relative_to(ROOT).as_posix().removesuffix('.speech.json') + '.wav'
        entry = {'text': receipt['text']}
        if 'PCM assembly' in receipt.get('method', ''):
            entry['sources'] = [source['path'] for source in receipt['sources']]
        corpus[name] = entry
    write_json(CORPUS, corpus)
    return corpus


def pcm(path):
    with wave.open(str(path)) as clip:
        assert clip.getparams()[:3] == (1, 2, RATE), path
        return clip.readframes(clip.getnframes())


def save(path, data, metadata):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.new')
    with wave.open(str(temporary), 'wb') as clip:
        clip.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
        clip.writeframes(data)
    temporary.replace(path)
    write_json(path.with_suffix('.speech.json'), dict(metadata, duration=len(data) / (RATE * 2), sha256=digest(path)))


def voice_style(engine, voice):
    """A Kokoro voice name, or 'a+b': the equal blend (mean style vector) the
    owner chose on 2026-11-03 (Bella+Heart, harness/speech comparison R)."""
    import numpy as np
    if '+' not in voice:
        return voice
    return np.mean([engine.get_voice_style(name) for name in voice.split('+')], axis=0).astype(np.float32)


def generate(only=None):
    """Synthesize missing or stale profile clips; ONLY limits the corpus paths."""
    import numpy as np
    import onnxruntime as ort
    from kokoro_onnx import Kokoro
    from book_speech import read_clip

    preferences = json.loads((ROOT / 'speech.json').read_text())['narration']['en']
    assert preferences['voice'] == 'af_bella' and preferences['profiles'] == PROFILES
    assert preferences['default_profile'] == 'normal'
    corpus = capture_corpus()
    pack = ROOT.parents[2] / 'harness/speech/models/kokoro'
    model, voices = pack / 'model_uint8.onnx', pack / 'voices-v1.0.bin'
    identity = {'model_sha256': digest(model), 'voices_sha256': digest(voices)}
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(model), sess_options=options, providers=['CPUExecutionProvider'])
    engine = Kokoro.from_session(session, str(voices))
    cache = ROOT / 'work/bella-speech/cache'
    cache.mkdir(parents=True, exist_ok=True)
    for profile, speed in PROFILES.items():
        # Dependencies first, then spelling recipes using those exact recordings.
        entries = sorted(((name, entry) for name, entry in corpus.items() if only is None or name in only),
                         key=lambda pair: ('sources' in pair[1], pair[0]))
        for index, (name, entry) in enumerate(entries, 1):
            target = ROOT / profile_path(name, profile)
            voice = entry.get('voice', 'af_bella')
            metadata = dict(text=entry['text'], model='kokoro-82m-uint8', voice=voice,
                            language='en', speed=speed, profile=profile, **identity)
            if '+' in voice:
                metadata['blend'] = {name: 1 / len(voice.split('+')) for name in voice.split('+')}
            receipt_path = target.with_suffix('.speech.json')
            if target.exists() and receipt_path.exists():
                receipt = json.loads(receipt_path.read_text())
                if all(receipt.get(k) == v for k, v in metadata.items()) and receipt.get('sha256') == digest(target):
                    continue
            if 'sources' in entry:
                source_paths = [ROOT / profile_path(source, profile) for source in entry['sources']]
                word, _ = read_clip(source_paths[0])
                parts = [word, bytes(11025 * 2)]
                word_text = entry['text'].split('. ')[0]
                letter_sources = iter(source_paths[1:])
                for letter in word_text.lower():
                    if letter.isspace():
                        parts.append(bytes(7350 * 2))
                    else:
                        data, _ = read_clip(next(letter_sources))
                        parts.extend((data, bytes(5512 * 2)))
                assert next(letter_sources, None) is None, name
                parts.extend((bytes(5512 * 2), word))
                metadata.update(method='Verified word, literal letter names, word; PCM assembly',
                                sources=[{'path': path.relative_to(ROOT).as_posix(), 'sha256': digest(path)} for path in source_paths])
                data = b''.join(parts)
            else:
                key = hashlib.sha256(json.dumps(dict(metadata, profile=None), sort_keys=True).encode()).hexdigest()
                cached = cache / (key + '.wav')
                if not cached.exists():
                    audio, rate = engine.create(entry['text'], voice=voice_style(engine, voice), speed=speed, lang='en-us')
                    assert np.isfinite(audio).all() and len(audio) and np.max(np.abs(audio)) > .005, name
                    # Change sample format/rate only; speed is set in synthesis.
                    data = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-threads', '1',
                                           '-f', 'f32le', '-ar', str(rate), '-ac', '1', '-i', 'pipe:0',
                                           '-f', 's16le', '-ar', str(RATE), '-ac', '1', 'pipe:1'],
                                          input=np.asarray(audio, dtype='<f4').tobytes(),
                                          stdout=subprocess.PIPE, check=True).stdout
                    save(cached, data, metadata)
                data = pcm(cached)
            assert 0 < len(data) <= RATE * 2 * 60, (name, len(data))
            save(target, data, metadata)
            if index % 25 == 0 or index == len(entries):
                print(f'{profile}: {index}/{len(entries)}', flush=True)
    manifest = {'format': 'jungle-speech-profiles-1', 'language': 'en', 'voice': 'af_bella', 'default': 'normal',
                'profiles': {profile: {'speed': speed, 'voices': {name: profile_path(name, profile) for name in corpus}}
                             for profile, speed in PROFILES.items()}}
    write_json(ROOT / 'assets/speech-profiles.json', manifest)
    validate()
    if only is None:
        # The reader's offline fallback must describe these newly measured clips.
        # Regenerate it in the same operation as the narration inventory.
        from story_book import main as compile_story
        compile_story()


def validate():
    from array import array
    corpus = json.loads(CORPUS.read_text())
    manifest = json.loads((ROOT / 'assets/speech-profiles.json').read_text())
    assert manifest['format'] == 'jungle-speech-profiles-1'
    assert manifest['voice'] == 'af_bella' and manifest['default'] == 'normal'
    total = 0
    for profile, speed in PROFILES.items():
        mapping = manifest['profiles'][profile]
        assert mapping['speed'] == speed and set(mapping['voices']) == set(corpus)
        for name, entry in corpus.items():
            path = ROOT / mapping['voices'][name]
            assert mapping['voices'][name] == profile_path(name, profile)
            receipt = json.loads(path.with_suffix('.speech.json').read_text())
            assert (receipt['text'], receipt['voice'], receipt['speed'], receipt['model']) == (entry['text'], entry.get('voice', 'af_bella'), speed, 'kokoro-82m-uint8'), path
            assert receipt['sha256'] == digest(path), path
            data = pcm(path)
            values = array('h', data)
            assert 0 < len(values) <= RATE * 60 and max(abs(value) for value in values) > 180, path
            assert abs(receipt['duration'] - len(values) / RATE) < 1 / RATE, path
            if 'sources' in entry:
                assert [source['path'] for source in receipt['sources']] == [profile_path(source, profile) for source in entry['sources']], path
                assert all(source['sha256'] == digest(ROOT / source['path']) for source in receipt['sources']), path
            total += path.stat().st_size
    print(f'local Bella validation: {len(corpus)} English paths x 3 profiles = {len(corpus)*3} finite PCM16 clips, {total} audio bytes', flush=True)

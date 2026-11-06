"""Places picture book (owner, 2026-11-05): Plaza, Park, Zoo, Aquarium, City,
traffic and more town places.

    python3 tools/places_book.py export          # pages, cover, receipts (Pillow)
    <harness .venv>/python tools/places_book.py en       # Bella+Heart, 3 profiles
    <harness .venv>/python tools/places_book.py de       # Kokoro German Victoria
    <harness .venv-qwen>/python tools/places_book.py es-candidates SEED... [NAME...]
    <whisper venv>/python tools/places_book.py es-scan   # listen to candidates
    <harness .venv-qwen>/python tools/places_book.py es  # pinned speech.json seeds

Generated originals stay in ignored local/art-development/places-book/; only
AVIF and narration ship. English uses the owner's 50/50 Bella+Heart blend
(2026-11-03), German Victoria and Spanish Serena with a pinned seed per clip.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import wave

sys.path.insert(0, str(Path(__file__).resolve().parent))
from book_catalog import LANGUAGES, PLACES, WORDS, narration, voice_path

ROOT = Path(__file__).resolve().parents[1]
BOOK = 'places'
NAMES = tuple(PLACES['words'])
ART = ROOT / 'local/art-development/places-book'
PROVENANCE = ROOT / 'tools/art_provenance/places-book.json'
SPEECH = ROOT.parents[2] / 'harness/speech'
WORK = ROOT / 'work/places-speech'
RATE = 22050
BLEND = 'af_bella+af_heart'
EN_LETTERS = 'assets/jungle-book/sounds/en/letters-bella-heart'
METHOD = 'Verified word, literal letter names, word; PCM assembly'
REFERENCE = 'local/art-development/title-covers.png'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.new')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


# ---------------------------------------------------------------- pictures

def export():
    """Ship each generated original at the 75% q35 standard with its receipts."""
    from PIL import Image
    from image_exports import export_scaled_master, record_canonical_rows
    prompts = json.loads((ART / 'prompts.json').read_text())['prompts']
    sources = json.loads((ART / 'sources.json').read_text())
    masters = ART / 'masters'
    masters.mkdir(parents=True, exist_ok=True)
    rows, pages = {}, {}
    for name in NAMES:
        source = ART / 'sources' / (name + '.png')
        master = masters / (name + '.png')
        with Image.open(source) as original:
            assert original.format == 'PNG' and min(original.size) >= 1024, (name, original.size)
            size = list(original.size)
            picture = original.convert('RGB')
            if picture.size != (1254, 1254):
                picture = picture.resize((1254, 1254), Image.Resampling.LANCZOS)
            picture.save(master, 'PNG')
        page = f'assets/jungle-book/pages/{name}.avif'
        rows[page] = export_scaled_master(master, ROOT / page)
        pages[page] = dict(subject=name, prompt=prompts[name],
                           prompt_sha256=hashlib.sha256(prompts[name].encode()).hexdigest(),
                           generator='built-in imagegen', reference_images=[REFERENCE],
                           reference_usage='style only: title-screen tiger cover watercolor',
                           request_id=sources[name]['request_id'],
                           source_png_sha256=digest(source), source_png_dimensions=size,
                           master=master.relative_to(ROOT).as_posix(), master_sha256=digest(master),
                           design_dimensions=[1254, 1254], sha256=rows[page]['sha256'])
    # A book's cover is its first page, as tools/book_art.py derives it.
    cover = masters / f'preview-{BOOK}.png'
    with Image.open(masters / (NAMES[0] + '.png')) as first:
        first.convert('RGB').resize((768, 768), Image.Resampling.LANCZOS).save(cover, 'PNG')
    preview = f'assets/jungle-book/previews/{BOOK}.avif'
    rows[preview] = export_scaled_master(cover, ROOT / preview)
    record_canonical_rows(rows)
    write_json(PROVENANCE, dict(book=BOOK, count=len(pages), files=pages,
                                cover=dict(path=preview, page=f'assets/jungle-book/pages/{NAMES[0]}.avif',
                                           design_dimensions=[768, 768], sha256=rows[preview]['sha256'])))
    book_prompts = ROOT / 'tools/book_prompts.json'
    data = json.loads(book_prompts.read_text())
    data['pages'].update((name, prompts[name]) for name in NAMES)
    book_prompts.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    for path, row in rows.items():
        print(path, row['dimensions'], row['bytes'])


# ---------------------------------------------------------------- shared audio

def pcm(path):
    with wave.open(str(path)) as clip:
        assert clip.getparams()[:3] == (1, 2, RATE), path
        return clip.readframes(clip.getnframes())


def save_wave(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.new')
    with wave.open(str(temporary), 'wb') as clip:
        clip.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
        clip.writeframes(data)
    temporary.replace(path)


def spelled(name, language):
    """Letter clips of the word, None for a space between its words."""
    word = WORDS[name][LANGUAGES.index(language)]
    folder = EN_LETTERS if language == 'en' else f'assets/jungle-book/sounds/{language}/letters'
    return [None if letter.isspace() else f'{folder}/{ord(letter):04x}.wav' for letter in word.lower()]


def assemble(word_path, letters, read=None):
    """Word, letter names and word with the reader's established pauses."""
    from book_speech import read_clip
    read = read or (lambda path: read_clip(ROOT / path)[0])
    parts = [read(word_path), bytes(RATE // 2 * 2)]
    recipe = [{'source': word_path}, {'silence_frames': RATE // 2}]
    for letter in letters:
        if letter is None:
            parts.append(bytes(RATE // 3 * 2))
            recipe.append({'silence_frames': RATE // 3})
        else:
            parts.extend((read(letter), bytes(RATE // 4 * 2)))
            recipe.extend(({'source': letter}, {'silence_frames': RATE // 4}))
    parts.extend((bytes(RATE // 4 * 2), read(word_path)))
    recipe.extend(({'silence_frames': RATE // 4}, {'source': word_path}))
    return b''.join(parts), recipe


def check_audio(path, text):
    """Same bounds local_narration.py applies before it accepts a clip."""
    from array import array
    data = pcm(path)
    duration = len(data) / (RATE * 2)
    characters = sum(not char.isspace() for char in text)
    assert max(.08, characters / 150) <= duration <= min(60, max(5, characters * .8 + 2)), (path, duration)
    samples = array('h', data)
    assert sum(abs(value) > 180 for value in samples) >= min(220, max(1, len(samples) // 1000)), path
    assert not any(abs(value) >= 32767 for value in samples), path
    return duration


# ---------------------------------------------------------------- English

def english():
    """Bella+Heart word, letter and spelling clips in all three profiles."""
    import english_speech
    corpus = json.loads(english_speech.CORPUS.read_text())
    for name in NAMES:
        for letter in spelled(name, 'en'):
            if letter:
                original = ROOT / f'assets/jungle-book/sounds/en/letters/{Path(letter).name}'
                text = json.loads(original.with_suffix('.speech.json').read_text())['text']
                corpus[letter] = dict(text=text, voice=BLEND)
        corpus[voice_path(name, 'en', True)] = dict(text=narration(name, 'en', True), voice=BLEND)
    for name in NAMES:
        sources = [voice_path(name, 'en', True)] + [letter for letter in spelled(name, 'en') if letter]
        corpus[voice_path(name, 'en')] = dict(text=narration(name, 'en'), voice=BLEND, sources=sources)
    english_speech.write_json(english_speech.CORPUS, corpus)
    only = {path for path, entry in corpus.items() if entry.get('voice') == BLEND}
    english_speech.generate(only=only)


# ---------------------------------------------------------------- German and Spanish

def _provider():
    path = SPEECH / 'local_speech_qwen.py'
    sys.path.insert(0, str(SPEECH))
    import importlib.util
    spec = importlib.util.spec_from_file_location('jungle_local_speech_provider', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _identity(language, seeds=None):
    """Receipt identity: the exact pack of this language's established clips
    with the provider revision that spoke the new ones."""
    settings = json.loads((ROOT / 'speech.json').read_text())['narration'][language]
    sample = ROOT / f'assets/jungle-book/sounds/{language}/simple/tractor.speech.json'
    receipt = json.loads(sample.read_text())
    assert (receipt['model'], receipt['voice']) == (settings['model'], settings['voice'])
    pack = dict(receipt['pack'], provider_sha256=digest(SPEECH / 'local_speech_qwen.py'))
    identity = dict(provider='local_speech', model=settings['model'], pack=pack,
                    voice=settings['voice'], speed=1.0)
    if seeds:
        identity['seeds'] = list(seeds)
    return identity


def _engine(language):
    module = _provider()
    if language == 'de':
        model = SPEECH / 'models/kokoro-german-victoria'
        return module.Engine(dict(provider='kokoro-german', model=str(model / 'kokoro-e2e.onnx'),
                                  data=str(model / 'kokoro-e2e.onnx.data'),
                                  voices=str(model / 'voices/df_victoria.bin'),
                                  vocab=str(model / 'vocab_index.json'), voice='df_victoria'))
    return module.Engine(dict(provider='qwen3-tts', model=str(SPEECH / 'models/qwen/customvoice-0.6b')))


def _request(language, text, identity):
    sys.path.insert(0, str(ROOT / 'tools'))
    from local_narration import _request as request
    return request(dict(language=language, text=text), identity)


def _kind(text):
    return 'word' if len(re.findall(r'\w+', text)) <= 1 else 'sentence'


def synthesize(engine, language, text, target, seeds=None):
    """One provider clip converted to the reader's mono PCM16 at 22.05 kHz."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix='synthesis-') as folder:
        raw = Path(folder) / 'engine.wav'
        voice = json.loads((ROOT / 'speech.json').read_text())['narration'][language]['voice']
        engine.write(text, voice, language, raw, **({'seeds': list(seeds)} if seeds else {}))
        converted = Path(folder) / 'pcm.wav'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-threads', '1', '-i', str(raw),
                        '-t', '61', '-map_metadata', '-1', '-ac', '1', '-ar', str(RATE),
                        '-c:a', 'pcm_s16le', str(converted)], check=True, timeout=180)
        check_audio(converted, text)
        converted.replace(target)


def _receipt(path, text, language, identity, kind, extra=None):
    metadata = dict(identity, kind=kind, text=text, language=language,
                    request_sha256=_request(language, text, identity), **(extra or {}))
    metadata.update(sha256=digest(path), duration=len(pcm(path)) / (RATE * 2))
    write_json(Path(path).with_suffix('.speech.json'), metadata)


def _spell(language, word_identity):
    """Assemble every spelling lesson from the verified word and letter clips."""
    for name in NAMES:
        word = voice_path(name, language, True)
        letters = spelled(name, language)
        data, recipe = assemble(word, letters)
        target = ROOT / voice_path(name, language)
        save_wave(target, data)
        sources = [word] + [letter for letter in letters if letter]
        identity = {k: v for k, v in word_identity[name].items() if k != 'seeds'}
        recipe = dict(method=METHOD, trim='book_speech.read_clip', parts=recipe)
        _receipt(target, narration(name, language), language, identity, 'spelling',
                 dict(method=METHOD, recipe=recipe,
                      sources=[{'path': source, 'sha256': digest(ROOT / source)} for source in sources]))


def german():
    engine = _engine('de')
    identities = {}
    for name in NAMES:
        text = narration(name, 'de', True)
        target = ROOT / voice_path(name, 'de', True)
        synthesize(engine, 'de', text, target)
        identities[name] = _identity('de')
        _receipt(target, text, 'de', identities[name], _kind(text))
    _spell('de', identities)


def _retakes():
    return json.loads((ROOT / 'speech.json').read_text())['narration']['es']['retakes']


def spanish_candidates(seeds, only=()):
    engine = _engine('es')
    for name in only or NAMES:
        for seed in seeds:
            target = WORK / 'es' / f'{name}-{seed}.wav'
            if not target.exists():
                try:
                    synthesize(engine, 'es', narration(name, 'es', True), target, [seed])
                except (ValueError, AssertionError) as error:  # unsuitable audio: this seed is not a candidate
                    print('rejected', target.name, error, flush=True)
                    continue
                print('candidate', target.name, flush=True)


def _plain(text):
    text = unicodedata.normalize('NFKD', text.casefold())
    return ' '.join(re.sub(r'[^a-zñ ]', ' ', ''.join(c for c in text if not unicodedata.combining(c))).split())


def spanish_scan():
    """Whisper (faster-whisper medium, local) transcript of every candidate."""
    import numpy as np
    from faster_whisper import WhisperModel
    model = WhisperModel('medium', device='cpu', compute_type='int8', cpu_threads=4, local_files_only=True)
    scanned = WORK / 'es-scan.json'
    results = json.loads(scanned.read_text()) if scanned.exists() else {}
    for path in sorted((WORK / 'es').glob('*.wav')):
        if path.name in results:
            continue
        name, seed = path.stem.rsplit('-', 1)
        raw = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-ac', '1', '-ar', '16000',
                              '-f', 'f32le', '-'], check=True, capture_output=True).stdout
        segments, _ = model.transcribe(np.frombuffer(raw, np.float32).copy(), language='es', beam_size=5,
                                       vad_filter=False, condition_on_previous_text=False)
        segments = list(segments)
        heard = ''.join(segment.text for segment in segments).strip()
        expected = WORDS[name][2]
        results[path.name] = dict(name=name, seed=int(seed), expected=expected, heard=heard,
                                  match=_plain(heard) == _plain(expected),
                                  logprob=min((s.avg_logprob for s in segments), default=-9.0),
                                  duration=len(pcm(path)) / (RATE * 2))
        print(json.dumps(results[path.name], ensure_ascii=False), flush=True)
    write_json(WORK / 'es-scan.json', results)


def pin_spanish_seeds():
    """Choose the best transcribed candidate per word and pin it in speech.json."""
    scan = json.loads((WORK / 'es-scan.json').read_text())
    chosen = {}
    for name in NAMES:
        rows = [row for row in scan.values() if row['name'] == name and row['match']]
        assert rows, f'no candidate transcribed as {WORDS[name][2]}'
        chosen[name] = max(rows, key=lambda row: (row['logprob'], -row['seed']))['seed']
    settings_path = ROOT / 'speech.json'
    lines = settings_path.read_text().splitlines(keepends=True)
    # Rewrite only the Spanish retake rows, keeping their one-line format.
    first = lines.index('      "retakes": {\n') + 1
    last = lines.index('      }\n', first)
    rows = dict(next(iter(json.loads('{' + line.strip().rstrip(',') + '}').items())) for line in lines[first:last])
    for name, seed in chosen.items():
        rows[voice_path(name, 'es', True)] = {'seeds': [seed]}
    body = [f'        {json.dumps(key)}: {json.dumps(value)},\n' for key, value in sorted(rows.items())]
    body[-1] = body[-1].replace(',\n', '\n')
    lines[first:last] = body
    settings_path.write_text(''.join(lines))
    json.loads(settings_path.read_text())
    return chosen


def spanish():
    retakes = _retakes()
    identities = {}
    for name in NAMES:
        seeds = retakes[voice_path(name, 'es', True)]['seeds']
        text = narration(name, 'es', True)
        target = ROOT / voice_path(name, 'es', True)
        shutil.copyfile(WORK / 'es' / f'{name}-{seeds[0]}.wav', target)
        identities[name] = _identity('es', seeds)
        _receipt(target, text, 'es', identities[name], _kind(text))
    _spell('es', identities)


def main():
    command = sys.argv[1]
    if command == 'export':
        export()
    elif command == 'en':
        english()
    elif command == 'de':
        german()
    elif command == 'es-candidates':
        # Seeds, optionally followed by the word names to retake.
        spanish_candidates([int(arg) for arg in sys.argv[2:] if arg.isdigit()],
                           [arg for arg in sys.argv[2:] if not arg.isdigit()])
    elif command == 'es-scan':
        spanish_scan()
    elif command == 'es-pin':
        print(pin_spanish_seeds())
    elif command == 'es':
        spanish()
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()

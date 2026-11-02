"""Every English narration ID has independently synthesized Bella profiles."""
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from english_speech import CORPUS, PROFILES, pcm, profile_path, validate
from book_catalog import NAMES, voice_path
from book_speech import read_clip

validate()
corpus = json.loads(CORPUS.read_text())
# All canonical book words, spelling lessons, alphabet and number selections.
required = {voice_path(name, 'en', simple) for name in NAMES for simple in (False, True)}
required.update(f'assets/abc/sounds/en/letters/{ord(letter):04x}.wav' for letter in 'abcdefghijklmnopqrstuvwxyz')
required.update(f'assets/numbers/sounds/en/{number}.wav' for number in range(1, 21))
assert required <= corpus.keys(), required - corpus.keys()
receipted = set()
for path in (ROOT / 'assets').rglob('*.speech.json'):
    if 'speech-profiles' in path.parts:
        continue
    if ('en' in path.parts or path.name.endswith('-en.speech.json')
            or path.parent == ROOT / 'assets/jungle-book/sounds'):
        receipted.add(path.relative_to(ROOT).as_posix().removesuffix('.speech.json') + '.wav')
assert receipted == corpus.keys(), receipted ^ corpus.keys()
for profile in PROFILES:
    for name, entry in corpus.items():
        if 'sources' not in entry:
            continue
        sources = iter(ROOT / profile_path(source, profile) for source in entry['sources'])
        word, _ = read_clip(next(sources))
        parts = [word, bytes(11025 * 2)]
        for letter in entry['text'].split('. ')[0].lower():
            if letter.isspace():
                parts.append(bytes(7350 * 2))
            else:
                letter_pcm, _ = read_clip(next(sources))
                parts.extend((letter_pcm, bytes(5512 * 2)))
        parts.extend((bytes(5512 * 2), word))
        assert next(sources, None) is None
        assert pcm(ROOT / profile_path(name, profile)) == b''.join(parts), (name, profile)
# The three settings must affect synthesis, including complete story sentences.
stories = [name for name in corpus if '/story-sounds/' in name]
durations = {}
for profile in PROFILES:
    durations[profile] = statistics.median(
        json.loads((ROOT / profile_path(name, profile)).with_suffix('.speech.json').read_text())['duration']
        for name in stories)
assert durations['slow'] > durations['normal'] > durations['fast'], durations
print(f'local English speech test: full corpus coverage, exact profile spelling reconstruction, story median seconds {durations}')

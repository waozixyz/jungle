"""Compose new spelling lessons from verified word and letter-name recordings."""
import hashlib
import json
from pathlib import Path
import wave
import sys

from book_catalog import EXPANSION, LANGUAGES, WORDS, narration, voice_path

ROOT = Path(__file__).resolve().parents[1]


def read_clip(path):
    metadata = json.loads(path.with_suffix('.speech.json').read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == metadata['sha256'], path
    with wave.open(str(path)) as clip:
        assert (clip.getnchannels(), clip.getsampwidth(), clip.getframerate()) == (1, 2, 22050)
        data = clip.readframes(clip.getnframes())
    # Remove provider padding while retaining quiet consonants and natural edges.
    samples = memoryview(data).cast('h')
    audible = [i for i, value in enumerate(samples) if abs(value) > 180]
    assert audible, path
    first = max(0, audible[0] - 1102)
    last = min(len(samples), audible[-1] + 2205)
    return data[first * 2:last * 2], metadata['sha256']


def main():
    total = 0
    categories = [arg for arg in sys.argv[1:] if arg != '--missing-only']
    for language in LANGUAGES:
        for name in EXPANSION['words']:
            if categories and not any(name in EXPANSION['extra'][category] for category in categories):continue
            if '--missing-only' in sys.argv and (ROOT / voice_path(name, language, False)).exists():continue
            word = WORDS[name][LANGUAGES.index(language)]
            source = ROOT / voice_path(name, language, True)
            word_data, word_hash = read_clip(source)
            parts = [word_data, bytes(22050 // 2 * 2)]
            provenance = [{'path': str(source.relative_to(ROOT)), 'sha256': word_hash}]
            for letter in word.lower():
                if letter.isspace():
                    parts.append(bytes(22050 // 3 * 2))
                    continue
                path = ROOT / f'assets/jungle-book/sounds/{language}/letters/{ord(letter):04x}.wav'
                data, digest = read_clip(path)
                parts.extend((data, bytes(22050 // 4 * 2)))
                provenance.append({'path': str(path.relative_to(ROOT)), 'sha256': digest})
            parts.extend((bytes(22050 // 4 * 2), word_data))
            path = ROOT / voice_path(name, language, False)
            path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(path), 'wb') as output:
                output.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
                output.writeframes(b''.join(parts))
            with wave.open(str(path)) as output:
                duration = output.getnframes() / output.getframerate()
            assert duration < 60, (name, language, duration)
            path.with_suffix('.speech.json').write_text(json.dumps({
                'text': narration(name, language), 'duration': duration,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'method': 'Verified word, literal letter names, word; PCM assembly',
                'sources': provenance,
            }, ensure_ascii=False, indent=2) + '\n')
            total += 1
    print(f'Composed and measured {total} spelling lessons in three languages')


if __name__ == '__main__':
    main()

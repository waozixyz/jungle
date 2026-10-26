"""Every alphabet letter has its own verified spoken name in the shipped ABC assets."""
import hashlib
import json
from pathlib import Path
import sys
import wave
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from abc_catalog import alphabet, letter_names
ROOT = Path(__file__).resolve().parents[1]
total = 0
for language in ('en', 'de', 'es'):
    for letter, name in zip(alphabet(language), letter_names(language)):
        path = ROOT / f'assets/abc/sounds/{language}/letters/{ord(letter.lower()):04x}.wav'
        metadata = json.loads(path.with_suffix('.speech.json').read_text())
        assert metadata['text'] == name + '.', (language, letter, metadata['text'])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == metadata['sha256']
        with wave.open(str(path)) as voice:
            assert voice.getparams()[:3] == (1, 2, 22050)
            assert abs(voice.getnframes() / voice.getframerate() - metadata['duration']) < .001
            assert .2 < metadata['duration'] < 6
        total += 1
assert alphabet('es')[13:16] == ['N', 'Ñ', 'O']
print(f'local alphabet audio test: {total} standalone letter names, complete narration and Spanish alphabet order passed')

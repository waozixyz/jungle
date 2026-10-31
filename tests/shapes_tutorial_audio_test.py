#!/usr/bin/env python3
"""Tutorial recordings agree with their provenance and both entry points."""
from pathlib import Path
import hashlib
import json
import sys
import wave

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'tools'))
import shared_assets

old = {'en': '709879e30570f55540260cd071f26896da2efec38cddd441c03e2af96ce5684f', 'de': '9df5e6c88d32812aa2f3df487886b8bff6b565b8b4b3d9a1867e70af16842732', 'es': '163fee0758023af9e6eaf78c883f50b59ccfc39ef4542d0cc43b641af18aa692'}
texts = {'en': 'Hold, drag, let go.', 'de': 'Halten, ziehen, loslassen.', 'es': 'Presiona, arrastra y suelta.'}
fingerprints = {'en': '71d85e9e75caedf090982a9ea4be8291b85bb480ff43c1305091d67eacccbc9b', 'de': 'f8f7f2507b81485044b2bbd43af4e35a9fd900876bf5a552a74d9d835af8dcee', 'es': '15ff9c117f109384ac039c10c96fea258f1e6381b09e0f776e0e307caf357d18'}
voices = shared_assets.NarratedVoices(root)
for lang, expected in texts.items():
    folder = root / 'assets/shapes/sounds' / lang
    wav = folder / 'tutorial_drag.wav'
    receipt = json.loads(wav.with_suffix('.speech.json').read_text())
    digest = hashlib.sha256(wav.read_bytes()).hexdigest()
    assert receipt['sha256'] == digest == fingerprints[lang] and receipt['text'] == expected
    assert receipt['voice'] == 'Kore' and receipt['speed'] == 1.0
    assert receipt['model'] == 'google/gemini-3.8-flash-lite-tts'
    with wave.open(str(wav)) as audio:
        assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getcomptype()) == (1, 2, 22050, 'NONE')
        assert 0 < audio.getnframes() <= 5.2 * audio.getframerate()
        assert abs(receipt['duration'] - audio.getnframes() / 22050) < 0.001
    assert voices[wav.relative_to(root).as_posix()] == lang
    assert hashlib.sha256((folder / 'show_me.wav').read_bytes()).hexdigest() == old[lang]
source = (root / 'games/shapes/jungle_shapes.zi').read_text()
assert source.count('PlayDragTutorialNarration()') == 2
assert 'PlayDragTutorialNarration :: () { Voice("tutorial_drag") }' in source
assert 'Voice("show_me")' not in source
print('shapes tutorial audio: passed')

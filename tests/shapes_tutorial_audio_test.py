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

old = {'en': '1df1a3b14b6f9e25d803d3583a6cb97ad89f4c0b43e1f1a7e44dbb445990e77a', 'de': '9df5e6c88d32812aa2f3df487886b8bff6b565b8b4b3d9a1867e70af16842732', 'es': '163fee0758023af9e6eaf78c883f50b59ccfc39ef4542d0cc43b641af18aa692'}
texts = {'en': 'Hold, drag, let go.', 'de': 'Halten, ziehen, loslassen.', 'es': 'Presiona, arrastra y suelta.'}
fingerprints = {'en': 'fbbb6f27caf7b5403332eb39105a25deafbc294cbbb4d65f51b18152236ab35c', 'de': 'bc977737213ae2b2dd214a5c2909f66732842d2639270a8cd31458ee5767f51a', 'es': '7c671d2dd0fa1a184ccb90a3732505f146d8e5c57270c8e4557a5a3d969bc391'}
voices = shared_assets.NarratedVoices(root)
for lang, expected in texts.items():
    folder = root / 'assets/shapes/sounds' / lang
    wav = folder / 'tutorial_drag.wav'
    receipt = json.loads(wav.with_suffix('.speech.json').read_text())
    digest = hashlib.sha256(wav.read_bytes()).hexdigest()
    assert receipt['sha256'] == digest == fingerprints[lang] and receipt['text'] == expected
    if lang == 'en':
        assert receipt['voice'] == 'af_bella' and receipt['speed'] == 0.8
        assert receipt['model'] == 'kokoro-82m-uint8'
    else:
        narration = json.loads((root / 'speech.json').read_text())['narration'][lang]
        assert receipt['voice'] == narration['voice'] and receipt['speed'] == 1.0
        assert receipt['model'] == narration['model']
    with wave.open(str(wav)) as audio:
        assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getcomptype()) == (1, 2, 22050, 'NONE')
        assert 0 < audio.getnframes() <= 5.2 * audio.getframerate()
        assert abs(receipt['duration'] - audio.getnframes() / 22050) < 0.001
    assert voices[wav.relative_to(root).as_posix()] == lang
    show_me = folder / 'show_me.wav'
    show_receipt = json.loads(show_me.with_suffix('.speech.json').read_text())
    show_hash = hashlib.sha256(show_me.read_bytes()).hexdigest()
    assert show_hash == show_receipt['sha256']
    assert (show_hash == old[lang]) == (lang == 'en')
source = (root / 'games/shapes/jungle_shapes.zi').read_text()
assert source.count('PlayDragTutorialNarration()') == 2
assert 'PlayDragTutorialNarration :: () { Voice("tutorial_drag") }' in source
assert 'Voice("show_me")' not in source
print('shapes tutorial audio: passed')

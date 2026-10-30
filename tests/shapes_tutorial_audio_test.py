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

old = {'en': '01936ad6f93848eb4919620e07f9f21343dd63d1425ba6829cf773b8267d7123', 'de': '0381bc21bad7db3e9b3788ec2293ceed179b2e3853314180173737ade670ecbb', 'es': '7da9c3a4b61d04bad31bea6c7bbf1aa94f9e289de61f3de54712a2c572ca1000'}
texts = {'en': 'Hold, drag, let go.', 'de': 'Halten, ziehen, loslassen.', 'es': 'Presiona, arrastra y suelta.'}
fingerprints = {'en': '3cdae392d1884982c4c339e4592769107317f36914f5311c23eb7929b623bf20', 'de': 'baf8dd17da34bf3c118307adb264fa0734dc84f2f40817f18a07702aec235732', 'es': 'aed0a5bce135f3089fbfb8a59c4249dc30ba6a1cd70d71623ef802d1347f8647'}
voices = shared_assets.NarratedVoices(root)
for lang, expected in texts.items():
    folder = root / 'assets/shapes/sounds' / lang
    wav = folder / 'tutorial_drag.wav'
    receipt = json.loads(wav.with_suffix('.speech.json').read_text())
    digest = hashlib.sha256(wav.read_bytes()).hexdigest()
    assert receipt['sha256'] == digest == fingerprints[lang] and receipt['text'] == expected
    assert receipt['voice'] == 'Kore' and receipt['speed'] == 0.8
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

"""Fast profile staging, validation and exact-frame mapping tests."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from speech_manifest import AddSpeechProfiles, ValidateSpeechManifest, FORMAT, PCM_FORMAT
from shared_assets import SpeechIndexText


def staging_test():
    with tempfile.TemporaryDirectory(dir=ROOT / 'work', prefix='speech-profiles-') as folder:
        root = Path(folder)
        voices = {}
        clips = {}
        profiles = {}
        for profile, speed, frames in [('normal', .8, 4000), ('slow', .65, 6000), ('fast', 1., 2000)]:
            name = 'assets/en/demo.wav' if profile == 'normal' else f'assets/speech-profiles/{profile}/en/demo.wav'
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(path), 'wb') as wav:
                wav.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
                wav.writeframes(b'\x10\x10' * frames)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            path.with_suffix('.speech.json').write_text(json.dumps({'sha256': digest}))
            profiles[profile] = {'speed': speed, 'voices': {'assets/en/demo.wav': name}}
            if profile == 'normal':
                clips[name] = dict(source=name, language='en', start_frame=0, frame_count=frames, sha256=digest)
                voices[name] = [dict(clip=name, start=0, frames=frames)]
        inventory = dict(format='jungle-speech-profiles-1', language='en', voice='af_bella', default='normal', profiles=profiles)
        (root / 'assets/speech-profiles.json').write_text(json.dumps(inventory))
        manifest = dict(format=FORMAT, audio=PCM_FORMAT, clips=clips, voices=voices, counts={})
        AddSpeechProfiles(manifest, root)
        ValidateSpeechManifest(manifest, root)
        assert [manifest['voices'][profiles[p]['voices']['assets/en/demo.wav']][0]['frames'] for p in profiles] == [4000, 6000, 2000]
        manifest['encoded'] = {name: {'path': f'assets/speech/{index}.ogg'} for index, name in enumerate(clips)}
        text = SpeechIndexText(manifest)
        assert 'voice|assets/speech-profiles/slow/en/demo.wav|' in text
        inventory['profiles']['slow']['voices']['assets/en/demo.wav'] = 'assets/../escape.wav'
        (root / 'assets/speech-profiles.json').write_text(json.dumps(inventory))
        try:
            AddSpeechProfiles(manifest, root)
        except ValueError:
            pass
        else:
            raise AssertionError('unsafe profile accepted')



if __name__ == '__main__':
    staging_test()
    print('local speech profile unit tests: staging validation, exact frames and normal/slow/fast mappings passed')

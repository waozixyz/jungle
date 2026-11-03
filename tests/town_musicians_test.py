"""Bremen ships without development masters, in every reader language/profile."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import wave
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from shared_assets import NarratedVoices, GameFiles
story=json.loads((ROOT/'tools/town_musicians.json').read_text())
assert len(story['pages'])==11
before=(ROOT/'games/book/town_musicians.zi').read_bytes()
subprocess.run([sys.executable,str(ROOT/'tools/town_musicians_book.py')],check=True)
assert before==(ROOT/'games/book/town_musicians.zi').read_bytes()
mapping=json.loads((ROOT/'tools/art_provenance/town-musicians-portrait/mapping.json').read_text())
voices=NarratedVoices(ROOT)
for row,scene in zip(story['pages'],mapping['scenes']):
    name=f"assets/jungle-book/portraits/{row['asset']}.webp"
    assert GameFiles('jungle-book')[name]==ROOT/name
    with Image.open(ROOT/name) as image: assert image.size==(1024,1536) and image.format=='WEBP'
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==scene['runtime_sha256']
    for lang in ('en','de','es'):
        name=f"assets/jungle-book/story-sounds/{lang}/{row['asset']}.wav"
        assert name in voices
        for prefix in (['','assets/speech-profiles/slow/','assets/speech-profiles/fast/'] if lang=='en' else ['']):
            path=ROOT/(prefix+name.removeprefix('assets/') if prefix else name)
            receipt=json.loads(path.with_suffix('.speech.json').read_text())
            assert receipt['text']==row[lang]
            assert receipt['sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
            with wave.open(str(path)) as clip:
                assert clip.getparams()[:3]==(1,2,22050)
                assert .5<clip.getnframes()/22050<30
                assert abs(clip.getnframes()/22050-receipt['duration'])<1/22050
print('local Bremen test passed: 11 WebPs, 33 translated pages, 55 measured narration clips, shared catalog and reproducible reader data')

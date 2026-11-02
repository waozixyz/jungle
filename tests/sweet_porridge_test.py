"""The complete story, literal recordings, previews and both title routes."""
import hashlib
import json
from pathlib import Path
import sys
import wave
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from title_scenes import Load
from web_images import prepare_native_previews, preview_path
from shared_assets import NarratedVoices
story = json.loads((ROOT/'tools/sweet_porridge.json').read_text())
assert len(story['pages']) == 11
files = {}
for row in story['pages']:
    name = f"assets/jungle-book/pages/{row['asset']}.webp"
    files[name] = ROOT/name
    with Image.open(ROOT/name) as picture:
        assert picture.size == (1536,1024)
        assert 800 <= row['paper_top'] < 940
        # Every page's annotated text reserve is part of its accepted painting.
        paper=picture.convert('RGB').crop((0,row['paper_top'],1536,1024))
        from PIL import ImageStat
        assert min(ImageStat.Stat(paper).mean)>200
    for language in ('en','de','es'):
        path = ROOT/f"assets/jungle-book/story-sounds/{language}/{row['asset']}.wav"
        receipt = json.loads(path.with_suffix('.speech.json').read_text())
        assert receipt['text'] == row[language]
        assert receipt['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
        with wave.open(str(path)) as audio:
            assert (audio.getnchannels(),audio.getsampwidth(),audio.getframerate()) == (1,2,22050)
            assert 0.5 < audio.getnframes()/22050 < 30
voices = NarratedVoices(ROOT)
assert len([p for p in voices if '/story-sounds/' in p]) == 33
previews = prepare_native_previews(files, ROOT/'work/sweet-porridge-review-v2/preview-test')
for name in files:
    with Image.open(previews[preview_path(name)]) as image: assert max(image.size) == 128
*_,hotspots = Load()
assert len([h for h in hotspots if h['game']=='Sweet Porridge']) == 2
assert 'no one is hungry' in story['pages'][-1]['en']
assert 'niemand' in story['pages'][-1]['de'] and 'nadie' in story['pages'][-1]['es']
print('local story test passed: 11 scenes, 33 literal narration receipts, 128px previews, two routes, complete ending')

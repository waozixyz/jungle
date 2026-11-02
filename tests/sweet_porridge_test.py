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
from shared_assets import NarratedVoices, GameFiles, SHARED
from web_images import prepare_runtime_images
import subprocess
story = json.loads((ROOT/'tools/sweet_porridge.json').read_text())
assert len(story['pages']) == 11
files = {}
masters = ROOT/'art/generated/sweet-porridge-portrait'
mapping = json.loads((masters/'mapping.json').read_text())
assert len(mapping['scenes']) == 11
assert len({scene['portrait_sha256'] for scene in mapping['scenes']}) == 11
before = (ROOT/'games/book/sweet_porridge.zi').read_bytes()
subprocess.run([sys.executable, str(ROOT/'tools/story_book.py')], check=True)
assert before == (ROOT/'games/book/sweet_porridge.zi').read_bytes(), 'Generated story out of date'
for row, scene in zip(story['pages'], mapping['scenes']):
    assert row['asset'] == scene['asset'] == row['portrait_asset']
    assert hashlib.sha256((ROOT/scene['source']).read_bytes()).hexdigest() == scene['source_sha256']
    assert hashlib.sha256((masters/scene['portrait']).read_bytes()).hexdigest() == scene['portrait_sha256']
    name = scene['runtime']
    files[name] = ROOT/name
    with Image.open(ROOT/name) as picture: assert picture.size == (1024,1536)
    assert (ROOT/name).stat().st_size < (masters/scene['portrait']).stat().st_size
    assert GameFiles('jungle-book')[name] == ROOT/name
assert 'assets/jungle-book/portraits/' in SHARED
exports = prepare_runtime_images(files, ROOT/'work/porridge-portrait-integration/runtime-test')
assert len(exports) == 11
for name, export in exports.items():
    assert export.info['reused_source'] and export.source.read_bytes() == files[name].read_bytes()

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
previews = prepare_native_previews(files, ROOT/'work/porridge-portrait-integration/preview-test')
for name in files:
    with Image.open(previews[preview_path(name)]) as image: assert max(image.size) == 128
print('local portrait assets passed: 11 approved unique masters, runtime reuse, 22 previews, 33 narration receipts', flush=True)
*_,hotspots = Load()
assert len([h for h in hotspots if h['game']=='Sweet Porridge']) == 2
assert 'no one is hungry' in story['pages'][-1]['en']
assert 'niemand' in story['pages'][-1]['de'] and 'nadie' in story['pages'][-1]['es']
print('local story test passed: 11 scenes, 33 literal narration receipts, 128px previews, two routes, complete ending')

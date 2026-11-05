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
sys.path.insert(0,str(ROOT/'tests'))
from design_size import design_size
from shared_assets import NarratedVoices, GameFiles
story=json.loads((ROOT/'tools/town_musicians.json').read_text())
assert len(story['pages'])==11
before=(ROOT/'games/book/town_musicians.zi').read_bytes()
subprocess.run([sys.executable,str(ROOT/'tools/town_musicians_book.py')],check=True)
assert before==(ROOT/'games/book/town_musicians.zi').read_bytes()
mapping=json.loads((ROOT/'tools/art_provenance/town-musicians-portrait/mapping.json').read_text())
voices=NarratedVoices(ROOT)
for row,scene in zip(story['pages'],mapping['scenes']):
    name=f"assets/jungle-book/portraits/{row['asset']}.avif"
    assert GameFiles('jungle-book')[name]==ROOT/name
    with Image.open(ROOT/name) as image: assert design_size(name,image)==(1024,1536) and image.format=='AVIF'
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
print('local Bremen test passed: 11 AVIFs, 33 translated pages, 55 measured narration clips, shared catalog and reproducible reader data')

landscape=json.loads((ROOT/'tools/art_provenance/town-musicians-landscape/mapping.json').read_text())
assert len(landscape['scenes'])==11
from web_images import prepare_runtime_images
from PIL import ImageStat
for row,scene in zip(story['pages'],landscape['scenes']):
    name=f"assets/jungle-book/pages/{row['asset']}.avif"
    assert scene['runtime']==name
    assert GameFiles('jungle-book')[name]==ROOT/name
    with Image.open(ROOT/name) as picture:
        assert design_size(name,picture)==(1536,1024) and picture.format=='AVIF'
        # paper_top is in painting pixels; the AVIF ships at 75%.
        reserve=(0,round(row['paper_top']*picture.height/1024),picture.width,picture.height)
        paper=ImageStat.Stat(picture.convert('RGB').crop(reserve))
        assert paper.mean[0]>240 and paper.mean[1]>210 and paper.mean[2]>160
        assert max(paper.stddev)<15, 'Caption reserve must be quiet paper'
        # The reader fills the page around the scene with this paper colour.
        color=tuple(int(row['paper_color'][at:at+2],16) for at in (1,3,5))
        median=ImageStat.Stat(picture.convert('RGB').crop(reserve)).median
        assert all(abs(a-b)<=6 for a,b in zip(color,median)), (row['asset'],color,median)
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==scene['runtime_sha256']
    exports=prepare_runtime_images({name:ROOT/name},ROOT/'local/art-development/town-musicians-landscape/test-exports')
    assert exports[name].info['reused_source']
reader=(ROOT/'games/book/jungle_book.zi').read_text()
assert 'ifx portrait then bremen_portraits[at] else bremen_pictures[at]' in reader
assert 'portrait || selected_story == 1' not in reader
print('local Bremen landscape test passed: 11 native AVIFs, caption reserves, catalog, web exports and orientation selection')
# The real reader layout: every page of both stories keeps its painting's
# exact shape at phone, tablet and desktop sizes, and its caption stays on the
# paper below the scene.
subprocess.run(['make','--no-print-directory','-s','build/tests/story_layout'],cwd=ROOT,check=True)
layout=subprocess.run([str(ROOT/'build/tests/story_layout')],capture_output=True,text=True)
assert layout.returncode==0, layout.stdout+layout.stderr
print(layout.stdout.strip())

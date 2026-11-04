#!/usr/bin/env python3
"""Full painted garden assets, transparent cutouts and shipped previews."""
from pathlib import Path
from PIL import Image
import hashlib, json

ROOT=Path(__file__).resolve().parents[1]
def main():
    import sys
    sys.path.insert(0,str(ROOT/'tools'))
    from farm_images import check, SCENES, FIELDS
    check()
    for name in SCENES:
        with Image.open(ROOT/name) as picture:
            assert max(picture.size)>=1500, (name,'full scene too small')
            assert 'A' not in picture.getbands() or picture.getchannel('A').getextrema()==(255,255)
    for name in FIELDS:
        with Image.open(ROOT/name) as picture:
            assert picture.mode=='RGBA' and picture.getchannel('A').getextrema()[0]==0 and picture.getchannel('A').getextrema()[1]>0,name
    assert not list((ROOT/'assets/garden/previews').glob('*')), 'Unused Farm previews shipped'
    provenance = json.loads((ROOT/'assets/garden/scene-provenance.json').read_text())
    for asset in provenance['assets']:
        assert hashlib.sha256((ROOT/asset['runtime']).read_bytes()).hexdigest() == asset['sha256']
        if (ROOT/asset['source']).exists():
            assert hashlib.sha256((ROOT/asset['source']).read_bytes()).hexdigest() == asset['source_sha256']
    assert not list((ROOT/'assets/garden').rglob('stage-*.wav')),'Guided narration remains packaged'
    assert 'jungle.voice' not in (ROOT/'games/garden/jungle_garden.zi').read_text()
    print('local garden assets: only runtime scenes, field glows and trimmed cut-outs passed')
if __name__=='__main__': main()

#!/usr/bin/env python3
"""Full painted garden assets, transparent cutouts and shipped previews."""
from pathlib import Path
from PIL import Image
import hashlib, json

ROOT=Path(__file__).resolve().parents[1]
def main():
    names={'bed','watering-can','water-drop','scene-landscape','scene-portrait','campus-sign','campus-sign-glow'}
    for kind in ('sunflower','tomato','carrot','strawberry','pumpkin','cabbage'):
        for stage in ('sprout','small','mature','dry','withered','packet'):
            names.add(f'{kind}-{stage}')
    for name in sorted(names):
        with Image.open(ROOT/f'assets/garden/art/{name}.webp') as full, Image.open(ROOT/f'assets/garden/previews/{name}.webp') as preview:
            assert max(full.size)>=700,(name,'full art too small',full.size)
            assert max(preview.size)<=128,(name,'preview too large')
            assert full.width*preview.height==full.height*preview.width or abs(full.width/full.height-preview.width/preview.height)<.04,(name,'preview aspect')
            if name not in ('bed','scene-landscape','scene-portrait'):
                assert full.mode=='RGBA' and preview.mode=='RGBA',(name,'lost transparency')
                assert full.getchannel('A').getextrema()==(0,255) or full.getchannel('A').getextrema()==(0,254),(name,'opaque cutout')
                assert preview.getchannel('A').getextrema()[0]==0,(name,'opaque preview')
    provenance = json.loads((ROOT/'assets/garden/scene-provenance.json').read_text())
    for asset in provenance['assets']:
        assert hashlib.sha256((ROOT/asset['runtime']).read_bytes()).hexdigest() == asset['sha256']
        if (ROOT/asset['source']).exists():
            assert hashlib.sha256((ROOT/asset['source']).read_bytes()).hexdigest() == asset['source_sha256']
    assert not list((ROOT/'assets/garden').rglob('stage-*.wav')),'Guided narration remains packaged'
    assert 'jungle.voice' not in (ROOT/'games/garden/jungle_garden.zi').read_text()
    print(f'local garden assets: {len(names)} full paintings, transparent cutouts and 128px previews passed')
if __name__=='__main__': main()

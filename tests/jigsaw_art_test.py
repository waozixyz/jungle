"""Verify the shipped pieces reconstruct every picture without lost regions."""
from pathlib import Path
import sys
from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from jigsaw_art import SCENES, GRIDS, SIZE

for scene in SCENES:
    for n in GRIDS:
        cell = SIZE//n
        pad = cell//4
        tile = cell+pad*2
        with Image.open(ROOT/f'assets/jigsaw/{scene}-{n}.png') as atlas:
            assert atlas.mode == 'RGBA' and atlas.size == (tile*n,tile*n)
            assembled = Image.new('RGBA',(SIZE+pad*2,SIZE+pad*2))
            for row in range(n):
                for col in range(n):
                    piece = atlas.crop((col*tile,row*tile,(col+1)*tile,(row+1)*tile))
                    assert piece.getchannel('A').getextrema() == (0,255)
                    assembled.alpha_composite(piece,(col*cell,row*cell))
            assembled = assembled.crop((pad,pad,pad+SIZE,pad+SIZE))
            # Smooth boundary pixels are allowed; no region may be missing.
            assert assembled.getchannel('A').getextrema()[0] > 200,(scene,n,'gap')
            original = Image.open(ROOT/f'art/generated/jigsaw/{scene}.png').convert('RGB').resize((SIZE,SIZE),Image.Resampling.LANCZOS)
            diff = ImageStat.Stat(ImageChops.difference(assembled.convert('RGB'),original))
            assert max(diff.mean) < 5,(scene,n,diff.mean)
print('local jigsaw artwork test: all 462 complementary pieces reconstruct their high-resolution scenes')

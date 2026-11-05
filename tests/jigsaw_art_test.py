"""Verify only current full pictures ship; runtime geometry is tested in Ziran."""
from pathlib import Path
import sys
from PIL import Image,ImageChops,ImageStat
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from jigsaw_art import SCENES,SIZE
expected={name+'.avif' for name in SCENES}
actual={p.name for p in (ROOT/'assets/jigsaw').iterdir() if p.suffix in ('.avif','.png')}
assert actual==expected,'Jigsaw still ships derived atlases or stale pictures'
for name in SCENES:
    with Image.open(ROOT/'assets/jigsaw'/f'{name}.avif') as picture:
        assert picture.size==(SIZE,SIZE) and picture.format=='AVIF'
        source=ROOT/'local/art-development/jigsaw'/f'{name}.png'
        if source.exists():
            original=Image.open(ROOT/'local/art-development/jigsaw'/f'{name}.png').convert('RGB').resize((SIZE,SIZE),Image.Resampling.LANCZOS)
            assert max(ImageStat.Stat(ImageChops.difference(picture.convert('RGB'),original)).mean)<7,name

# q60 4:4:4 keeps the approved fine detail closer to the masters than the old
# WebP; three exports total about 1.1 MB.
assert sum(p.stat().st_size for p in (ROOT/'assets/jigsaw').glob('*.avif'))<1_500_000
print('local jigsaw artwork test: three current full pictures, original color fidelity and no pre-cut atlas/thumbnail files passed')

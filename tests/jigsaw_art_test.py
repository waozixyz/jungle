"""Verify only current full pictures ship; runtime geometry is tested in Ziran."""
from pathlib import Path
import sys
from PIL import Image,ImageChops,ImageStat
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from jigsaw_art import SCENES,SIZE
expected={name+'.jpg' for name in SCENES}
actual={p.name for p in (ROOT/'assets/jigsaw').iterdir() if p.suffix in ('.jpg','.png','.webp')}
assert actual==expected,'Jigsaw still ships derived atlases or stale pictures'
for name in SCENES:
    with Image.open(ROOT/'assets/jigsaw'/f'{name}.jpg') as picture:
        assert picture.size==(SIZE,SIZE) and picture.format=='JPEG'
        original=Image.open(ROOT/'art/generated/jigsaw'/f'{name}.png').convert('RGB').resize((SIZE,SIZE),Image.Resampling.LANCZOS)
        assert max(ImageStat.Stat(ImageChops.difference(picture.convert('RGB'),original)).mean)<7,name
assert sum(p.stat().st_size for p in (ROOT/'assets/jigsaw').glob('*.jpg'))<3_000_000
print('local jigsaw artwork test: three current full pictures, original color fidelity and no pre-cut atlas/thumbnail files passed')

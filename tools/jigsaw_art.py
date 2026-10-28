"""Prepare the full pictures; every host cuts Jigsaw pieces at runtime."""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCENES = ('tiger-stream', 'duck-pond', 'meadow-train')
GRIDS = (2, 3, 4, 5, 6, 8)
SIZE = 1200


def main():
    dest = ROOT/'assets/jigsaw'
    dest.mkdir(parents=True, exist_ok=True)
    for name in SCENES:
        source = Image.open(ROOT/'art/generated/jigsaw'/f'{name}.png').convert('RGB')
        source = source.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
        source.save(dest/f'{name}.jpg', quality=92)
        print('Prepared full runtime jigsaw picture:', name, flush=True)
    Image.open(dest/'tiger-stream.jpg').convert('RGB').resize((420,420),Image.Resampling.LANCZOS).save(ROOT/'assets/jungle/covers/jigsaw.jpg',quality=90,optimize=True,progressive=True)


if __name__ == '__main__':
    main()

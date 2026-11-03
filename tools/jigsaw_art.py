"""Prepare the full pictures; every host cuts Jigsaw pieces at runtime."""
from pathlib import Path
from image_exports import export_image

ROOT = Path(__file__).resolve().parents[1]
SCENES = ('tiger-stream', 'duck-pond', 'meadow-train')
GRIDS = (2, 3, 4, 5, 6, 8)
SIZE = 1200


def main():
    dest = ROOT/'assets/jigsaw'
    dest.mkdir(parents=True, exist_ok=True)
    for name in SCENES:
        source = ROOT/'local/art-development/jigsaw'/f'{name}.png'
        export_image(source, dest/f'{name}.webp', 'scene', size=(SIZE, SIZE))
        print('Prepared full runtime jigsaw picture:', name, flush=True)
    export_image(ROOT/'local/art-development/jigsaw/tiger-stream.png',
                 ROOT/'assets/jungle/covers/jigsaw.webp', 'scene', size=(420, 420))



if __name__ == '__main__':
    main()

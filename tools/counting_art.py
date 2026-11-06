"""Make small transparent counting pictures from the approved cut-outs."""
from pathlib import Path
from PIL import Image
from image_exports import export_painted_image

ROOT = Path(__file__).resolve().parents[1]
ANIMALS = ('tiger', 'frog', 'butterfly', 'ladybug', 'snail', 'elephant',
           'giraffe', 'monkey', 'panda', 'lion', 'zebra', 'crocodile', 'parrot',
           'toucan', 'rabbit', 'cat', 'dog', 'sheep', 'duck', 'hen', 'pig', 'cow')
SIZE = 128


def main():
    target = ROOT / 'assets/jungle-book/counting'
    target.mkdir(parents=True, exist_ok=True)
    for name in ANIMALS:
        with Image.open(ROOT / 'assets/jungle-book/items' / (name + '.avif')) as image:
            export_painted_image(image.convert('RGBA').resize((SIZE, SIZE), Image.Resampling.LANCZOS),
                                 target / (name + '.avif'), 'cutout')
    print(f'Prepared {len(ANIMALS)} transparent {SIZE} px counting pictures')


if __name__ == '__main__':
    main()

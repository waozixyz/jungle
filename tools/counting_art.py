"""Make small transparent counting pictures from the approved cut-outs."""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ANIMALS = ('tiger', 'frog', 'butterfly', 'ladybug', 'snail', 'elephant',
           'giraffe', 'monkey', 'panda', 'lion', 'zebra', 'crocodile', 'parrot',
           'toucan', 'rabbit', 'cat', 'dog', 'sheep', 'duck', 'hen', 'pig', 'cow')
SIZE = 128


def main():
    target = ROOT / 'assets/jungle-book/counting'
    target.mkdir(parents=True, exist_ok=True)
    for name in ANIMALS:
        with Image.open(ROOT / 'assets/jungle-book/items' / (name + '.png')) as image:
            image.convert('RGBA').resize((SIZE, SIZE), Image.Resampling.LANCZOS).save(
                target / (name + '.png'), optimize=True)
    print(f'Prepared {len(ANIMALS)} transparent {SIZE} px counting pictures')


if __name__ == '__main__':
    main()

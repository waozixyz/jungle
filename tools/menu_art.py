"""Cut the generated watercolor title atlas into the game's three covers."""
from pathlib import Path
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]

def main():
    source = Image.open(ROOT / 'art/generated/title-covers.png').convert('RGBA')
    assert source.width == source.height
    target = ROOT / 'assets/jungle/covers'
    target.mkdir(parents=True, exist_ok=True)
    for index, name in enumerate(('book', 'count', 'paint')):
        row, column = divmod(index, 2)
        cell = source.crop(tuple(round(v) for v in (column * source.width / 2, row * source.height / 2,
                          (column + 1) * source.width / 2, (row + 1) * source.height / 2)))
        cell.resize((420, 420), Image.Resampling.LANCZOS).save(target / (name + '.png'), optimize=True)
    with Image.open(ROOT / 'art/generated/abc-123-cover.png') as cover:
        cover.resize((420, 420), Image.Resampling.LANCZOS).save(target / 'abc-123.png', optimize=True)
    print('Prepared four watercolor title covers')
if __name__ == '__main__': main()

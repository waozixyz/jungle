"""Export the individually generated watercolor menu illustrations."""
from pathlib import Path
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]

def main():
    target = ROOT / 'assets/jungle/covers'
    target.mkdir(parents=True, exist_ok=True)
    for name in ('book', 'count', 'paint', 'abc-123'):
        with Image.open(ROOT / 'art/generated/menu-covers' / (name + '.png')) as cover:
            assert cover.width == cover.height
            cover.convert('RGBA').resize((420, 420), Image.Resampling.LANCZOS).save(
                target / (('counting' if name == 'count' else name) + '.png'), optimize=True)
    print('Prepared four watercolor title covers')
if __name__ == '__main__': main()

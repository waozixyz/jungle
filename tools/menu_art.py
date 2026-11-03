"""Export the individually generated watercolor menu illustrations."""
from pathlib import Path
from PIL import Image
from image_exports import export_image
ROOT = Path(__file__).resolve().parents[1]

def main():
    target = ROOT / 'assets/jungle/covers'
    target.mkdir(parents=True, exist_ok=True)
    for name in ('book', 'count', 'paint', 'abc-123'):
        with Image.open(ROOT / 'local/art-development/menu-covers' / (name + '.png')) as cover:
            assert cover.width == cover.height
            # Preserve canonical cover pixels; runtime exports control shipped size.
            export_image(ROOT / 'local/art-development/menu-covers' / (name + '.png'),
                         target / (('counting' if name == 'count' else name) + '.webp'),
                         'scene', size=(420, 420))
    print('Prepared four watercolor title covers')
if __name__ == '__main__': main()

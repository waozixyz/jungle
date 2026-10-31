"""Decode the real preview encoder output; no desktop or source emulation."""
from pathlib import Path
import subprocess
import tempfile
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    scratch = ROOT / 'work/paint-preview-tests'
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as folder:
        path = Path(folder) / 'alpha.png'
        subprocess.run([str(ROOT / 'build/tests/paint_preview'), str(path)], check=True)
        with Image.open(path) as image:
            assert image.size == (2, 2)
            rgba = image.convert('RGBA')
            assert rgba.getpixel((1, 0))[3] == 0
            assert all(rgba.getpixel(point)[3] == 255 for point in ((0, 0), (0, 1), (1, 1)))
            assert rgba.getpixel((0, 1))[:3] == (0, 0, 0)
    print('local paint preview: bounded requests, decoded colors and transparency passed')


if __name__ == '__main__':
    main()

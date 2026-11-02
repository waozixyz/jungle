"""Real stencil vector storage, geometry fidelity, and reproducible compilation.

The decoder is independent of the encoder and the native rasterizer. Native
paint_view tests cover tiled rendering, zoom, fills, and legacy documents.
"""
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import paint_vectors as vectors
from paint_pages import CANVAS, dinosaur, fit, render


def decode(data):
    assert data[:4] == b'KVP1'
    at = 4

    def number():
        nonlocal at
        value = shift = 0
        while True:
            assert at < len(data) and shift < 35
            byte = data[at]
            at += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value
            shift += 7

    width, height, count = number() / 16, number() / 16, number()
    paths = []
    for _ in range(count):
        assert data[at] == ord('E')
        at += 1
        length = number()
        end = at + length
        previous = [0, 0]
        commands = []
        opened = False
        while at < end:
            command = chr(data[at])
            at += 1
            assert command in 'MLCZ'
            if command == 'M':
                assert not opened
                opened = True
            elif command == 'Z':
                assert opened
                opened = False
            else:
                assert opened
            values = []
            for axis in range({'M': 2, 'L': 2, 'C': 6, 'Z': 0}[command]):
                value = number()
                previous[axis % 2] += -(value // 2) - 1 if value & 1 else value // 2
                values.append(previous[axis % 2] / 16)
            commands.append(command + ' '.join(f'{value:g}' for value in values))
        assert at == end and not opened
        paths.append(''.join(commands))
    assert at == len(data)
    return width, height, paths


def coverage(width, height, path, size, box=None, threshold=128):
    box = box or (0, 0, width, height)
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="' +
           ' '.join(map(str, box)) + '"><path fill-rule="evenodd" d="' + path + '"/></svg>')
    return np.asarray(render(svg, *size).getchannel('A')) >= threshold


class PaintVectorsTest(unittest.TestCase):
    def test_all_catalog_assets_are_compact_geometry(self):
        names = vectors.source_names()
        self.assertEqual({p.stem for p in vectors.OUT.glob('*.kvp')}, set(names))
        total = 0
        for name in names:
            with self.subTest(name=name):
                vectors.validate_source(vectors.ART / (name + '.svg'))
                data = (vectors.OUT / (name + '.kvp')).read_bytes()
                self.assertLessEqual(len(data), vectors.MAX_VECTOR_BYTES)
                width, height, paths = decode(data)
                self.assertEqual(len(paths), 1 if name.startswith('scene') else 2)
                self.assertTrue(all('C' in path for path in paths), 'Expected smooth Bezier outlines')
                if name.startswith('scene'):
                    self.assertEqual((width, height), CANVAS)
                else:
                    _, w, h, _, _ = dinosaur(int(name[4:]))
                    self.assertEqual((width, height), fit(w, h, *CANVAS))
                total += len(data)
        self.assertLess(total, len(names) * 24 * 1024)
        art = ROOT / 'assets/dino-paint/art'
        self.assertEqual({p.name for p in art.glob('dino*.png')},
                         {name + '-preview.png' for name in names if name.startswith('dino')})

    def test_vector_coverage_preserves_each_source(self):
        for name in vectors.source_names():
            with self.subTest(name=name):
                width, height, paths = decode((vectors.OUT / (name + '.kvp')).read_bytes())
                size = (int(width), int(height))
                if name.startswith('scene'):
                    source = (vectors.ART / (name + '.svg')).read_text()
                    sources = [source]
                else:
                    _, _, _, ink, body = dinosaur(int(name[4:]))
                    sources = [body, ink]
                for path, source in zip(paths, sources):
                    image = render(source, *size)
                    expected = (np.asarray(image.convert('L')) < 128 if name.startswith('scene')
                                else np.asarray(image.getchannel('A')) >= 128)
                    actual = coverage(width, height, path, size)
                    self.assertGreater(expected.sum(), 100)
                    # Thresholded antialiasing differs by up to 4.3% of narrow
                    # ink in detailed original scenes. Check geometry against
                    # nontrivial antialiased coverage as well: a thin line at
                    # 49% coverage must not count as missing beside a 51% one.
                    self.assertLess(np.count_nonzero(expected ^ actual) / expected.sum(), .05)
                    neighbors = np.ones((3, 3), dtype=bool)
                    expected_support = (np.asarray(image.convert('L')) < 239 if name.startswith('scene')
                                        else np.asarray(image.getchannel('A')) >= 16)
                    actual_support = coverage(width, height, path, size, threshold=16)
                    self.assertFalse(np.any(actual & ~ndimage.binary_dilation(expected_support, structure=neighbors)))
                    self.assertFalse(np.any(expected & ~ndimage.binary_dilation(actual_support, structure=neighbors)))

    def test_collectible_fill_regions_stay_closed_at_zoom(self):
        for index in range(56, 67):
            width, height, paths = decode((vectors.OUT / f'dino{index}.kvp').read_bytes())
            for scale in (1, 3):
                with self.subTest(index=index, scale=scale):
                    size = (int(width) * scale, int(height) * scale)
                    ink = coverage(width, height, paths[1], size)
                    body = coverage(width, height, paths[0], size)
                    seed = np.zeros(ink.shape, dtype=bool)
                    seed[0] = ~ink[0]; seed[-1] = ~ink[-1]
                    seed[:, 0] = ~ink[:, 0]; seed[:, -1] = ~ink[:, -1]
                    outside = ndimage.binary_propagation(seed, mask=~ink)
                    paper = body & ~ink
                    # Ignore a single antialiased boundary pixel, matching the
                    # host's bounded color bleed beneath the vector ink.
                    self.assertFalse(np.any(ndimage.binary_erosion(paper, structure=np.ones((3, 3))) & outside))
                    labels, count = ndimage.label(paper & ~outside)
                    areas = np.bincount(labels.ravel())[1:]
                    self.assertGreaterEqual(np.count_nonzero(areas >= 100 * scale * scale), 3)

    def test_zoomed_geometry_tracks_source(self):
        # A repaired palm scene, an older animal, and the newest default stencil.
        last = max(int(p.stem[4:]) for p in vectors.ART.glob('dino[0-9]*.svg'))
        for name in ('scene1', 'dino13', f'dino{last}'):
            width, height, paths = decode((vectors.OUT / (name + '.kvp')).read_bytes())
            if name.startswith('scene'):
                source = (vectors.ART / (name + '.svg')).read_text()
            else:
                source = dinosaur(int(name[4:]))[3]
            # Crop a central tile in page space, so 8x needs no giant image.
            import xml.etree.ElementTree as ET
            tree = ET.fromstring(source)
            # Stencil SVG units differ from their fitted page-space KVP units.
            _, _, source_width, source_height = map(float, tree.get('viewBox').split())
            group = ET.Element('{http://www.w3.org/2000/svg}g', {
                'transform': f'scale({width / source_width} {height / source_height})'})
            for child in list(tree):
                tree.remove(child)
                group.append(child)
            tree.append(group)
            box = (width / 2 - 40, height / 2 - 40, 80, 80)
            tree.set('viewBox', ' '.join(map(str, box)))
            for scale in (1, 3, 8):
                with self.subTest(name=name, scale=scale):
                    size = (80 * scale, 80 * scale)
                    image = render(ET.tostring(tree, encoding='unicode'), *size)
                    expected = (np.asarray(image.convert('L')) < 128 if name.startswith('scene')
                                else np.asarray(image.getchannel('A')) >= 128)
                    actual = coverage(width, height, paths[-1], size, box)
                    self.assertLess(np.count_nonzero(expected ^ actual) / max(1, expected.sum()), .08)

    def test_encoder_rejects_unsupported_or_incomplete_paths(self):
        for path in ('M0', 'L0 0 C1 1', 'M0 0 Q1 1 2 2 Z', 'M0 0 A2 2 0 0 0 1 1Z'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                vectors.encode_path(path)
        self.assertEqual(vectors.encode_path('M0 0 1 1Z'), vectors.encode_path('M0 0L1 1Z'))


if __name__ == '__main__':
    unittest.main()

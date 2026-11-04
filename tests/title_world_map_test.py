"""The world map's data and art: every area is a landmark on both plates.

tools/title_world_map.json lists the landmarks; tools/title_world_map.py writes
the "map" scene into tools/title_hotspots.json. Behavior (hover, travel, the
locked cue, Back, the map button on every scene, the fit) is in title_test.zi.
"""
import json
from pathlib import Path
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT/'tools/title_world_map.json').read_text())
DATA = json.loads((ROOT/'tools/title_hotspots.json').read_text())
SCENES = {s['name']: s for s in DATA['scenes']}
MAP = SCENES[SPEC['scene']]
VIEWS = {'landscape': MAP, 'portrait': MAP['portrait']}


def chunk(path):
    """The WebP image chunk: VP8L is lossless, VP8 lossy."""
    data = Path(path).read_bytes()
    assert data[:4] == b'RIFF' and data[8:12] == b'WEBP', path
    at = 12
    while at < len(data):
        name, size = data[at:at + 4], int.from_bytes(data[at + 4:at + 8], 'little')
        if name in (b'VP8L', b'VP8 '):
            return name
        at += 8 + size + size % 2
    raise AssertionError(f'{path} has no image chunk')


class WorldMapTest(unittest.TestCase):
    def test_every_scene_is_a_landmark(self):
        covered = set()
        for mark in SPEC['landmarks']:
            kind, _, target = mark['target'].partition(':')
            covered.update(mark.get('covers', []))
            if kind == 'scene':
                covered.add(target)
        others = set(SCENES) - {SPEC['scene']}
        self.assertEqual(others - covered, set(), 'scenes without a landmark on the world map')
        covers = {name for mark in SPEC['landmarks'] for name in mark.get('covers', [])}
        self.assertEqual(covers - others, set(), 'landmarks that cover a missing scene')

    def test_landmarks_match_the_data_in_both_orientations(self):
        for orientation, view in VIEWS.items():
            spots = {h['id']: h for h in view['hotspots']}
            self.assertEqual(list(spots), [m['id'] for m in SPEC['landmarks']], orientation)
            for mark in SPEC['landmarks']:
                spot = spots[mark['id']]
                kind, _, dest = mark['target'].partition(':')
                # A landmark stays locked only while its scene is missing.
                if kind == 'scene' and dest in SCENES or kind != 'scene':
                    self.assertEqual(spot['target'], mark['target'], mark['id'])
                else:
                    self.assertEqual(spot['target'], 'locked:' + mark['id'], mark['id'])
                self.assertEqual(spot['rest'], f'assets/jungle/title/world-map/{mark["id"]}.webp')
                self.assertEqual(spot['glow'], f'assets/jungle/title/world-map/{mark["id"]}-glow.webp')
                self.assertNotIn('sign', spot)
        self.assertTrue(any(m['target'].startswith('locked:') for m in SPEC['landmarks']), 'nothing beyond the desert')
        self.assertIs(MAP.get('back'), True)

    def test_landmarks_stay_apart_and_inside(self):
        for orientation, view in VIEWS.items():
            width, height = (view.get('width', DATA['width']), view.get('height', DATA['height']))
            boxes = []
            for spot in view['hotspots']:
                x, y, w, h = spot['glow_rect']
                self.assertTrue(0 <= x and 0 <= y and x + w <= width and y + h <= height, (orientation, spot['id']))
                # The corner controls (Back, sound, collection, map) stay clear.
                self.assertGreater(y + h * 0.25, height * 0.04, (orientation, spot['id']))
                boxes.append((spot['id'], x, y, x + w, y + h))
            for i, a in enumerate(boxes):
                for b in boxes[i + 1:]:
                    across = max(0, min(a[3], b[3]) - max(a[1], b[1])) * max(0, min(a[4], b[4]) - max(a[2], b[2]))
                    smaller = min((a[3] - a[1]) * (a[4] - a[2]), (b[3] - b[1]) * (b[4] - b[2]))
                    # Glow boxes may touch; the hit areas are the silhouettes.
                    self.assertLess(across, smaller * 0.35, (orientation, a[0], b[0]))

    def test_runtime_images(self):
        for orientation, view in VIEWS.items():
            size = (view.get('width', DATA['width']), view.get('height', DATA['height']))
            for key in ('image', 'low'):
                path = ROOT/view[key]
                self.assertEqual(path.suffix, '.webp')
                self.assertEqual(chunk(path), b'VP8 ', path)
                with Image.open(path) as picture:
                    self.assertEqual(picture.mode, 'RGB')
                    if key == 'image':
                        self.assertEqual(picture.size, size)
                    else:
                        self.assertEqual(picture.width, 240)
            for spot in view['hotspots']:
                for key in ('rest', 'glow'):
                    path = ROOT/spot[key]
                    self.assertEqual(chunk(path), b'VP8L', path)
                    with Image.open(path) as picture:
                        self.assertEqual(picture.mode, 'RGBA')
                        # Both share the glow rectangle.
                        x, y, w, h = spot['glow_rect']
                        self.assertAlmostEqual(picture.width / picture.height, w / h, delta=0.05)
                        self.assertEqual(picture.getchannel('A').getextrema()[0], 0)
        self.assertEqual(sorted(p.name for p in (ROOT/'assets/jungle/title/world-map').iterdir()),
                         sorted(n for m in SPEC['landmarks'] for n in (m['id'] + '.webp', m['id'] + '-glow.webp')))
        self.assertFalse(list((ROOT/'assets/jungle/title').glob('world-map*.png')))

    def test_paper_and_cue_match_the_app(self):
        title = (ROOT/'host/jungle_title.zi').read_text()
        self.assertIn(f'TITLE_MAP_PAPER :: 0x{SPEC["paper"]}ff', title)
        with Image.open(ROOT/MAP['image']) as plate:
            edge = plate.convert('RGB').getpixel((0, plate.height // 2))
        self.assertLess(max(abs(a - b) for a, b in zip(edge, bytes.fromhex(SPEC['paper']))), 6)
        self.assertTrue((ROOT/'assets/jungle/sounds/not-yet.wav').is_file())
        menu = (ROOT/'host/jungle_menu.zi').read_text()
        self.assertRegex(menu, r'TitleMapEntry\(scene\) && TitleMapButton\(')
        # Farm is a full-window game with floating Back. Its route into the
        # map is through the painted Campus, which retains the map button.
        self.assertIn('GameSceneBack(', (ROOT/'host/jungle_host.zi').read_text())
        labels = json.loads((ROOT/'locales/ui.json').read_text())
        self.assertEqual(len(labels['World map']), 2)


if __name__ == '__main__':
    unittest.main()

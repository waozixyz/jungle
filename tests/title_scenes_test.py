"""Validate title variants without selecting unapproved portrait artwork."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('title_scenes', ROOT/'tools/title_scenes.py')
title = importlib.util.module_from_spec(spec)
spec.loader.exec_module(title)


def inside(polygon, x, y):
    """Even-odd source geometry, including the existing overlap policy."""
    result = False
    for (xi, yi), (xj, yj) in zip(polygon, polygon[-1:] + polygon[:-1]):
        if (yi > y) != (yj > y) and x < xi + (y-yi)*(xj-xi)/(yj-yi):
            result = not result
    return result


def hit(scene, x, y):
    candidates = [h for h in scene['hotspots'] if inside(h['polygon'], x, y)]
    return min(candidates, key=lambda h: h['glow_rect'][2]*h['glow_rect'][3])['id'] if candidates else None


class TitleVariants(unittest.TestCase):
    def load(self, data):
        work = ROOT/'work/title-tests'
        work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as directory:
            source = Path(directory)/'scenes.json'
            source.write_text(json.dumps(data))
            return title.Load(source)

    def fixture(self):
        data = json.loads(title.SOURCE.read_text())
        # Existing assets stand in for files only. The synthetic geometry
        # deliberately has different dimensions to catch landscape assumptions.
        for scene in data['scenes']:
            portrait = copy.deepcopy(scene)
            portrait.pop('name')
            portrait.update(width=941, height=1672)
            for hotspot in portrait['hotspots']:
                hotspot['polygon'] = [[y, x] for x, y in hotspot['polygon']]
                x, y, w, h = hotspot['glow_rect']
                hotspot['glow_rect'] = [y, x, h, w]
            scene['portrait'] = portrait
        return data

    def test_production(self):
        data, scenes, parents, hotspots = title.Load()
        self.assertEqual(title.OUTPUT.read_text(), title.Render(data, scenes, parents, hotspots))
        shelf = next(s for s in scenes if s['name'] == 'bookshelf')
        self.assertEqual(sum(h['target'] == 'game:Picture Book' for h in shelf['hotspots']), 1)
        campus = next(s for s in scenes if s['name'] == 'campus')
        routes = {h['id']: h['target'] for h in campus['hotspots']}
        self.assertEqual(routes['music-hut'], 'game:Music Room')
        self.assertEqual(routes['piano'], 'game:Little Piano')

    def test_separate_music_and_piano_entrances(self):
        _, scenes, _, _ = title.Load()
        for name in ('campus', 'campus-portrait'):
            with self.subTest(scene=name):
                scene = next(s for s in scenes if s['name'] == name)
                hotspots = {h['id']: h for h in scene['hotspots']}
                hut, piano = hotspots['music-hut'], hotspots['piano']
                self.assertEqual(hut['target'], 'game:Music Room')
                self.assertEqual(piano['target'], 'game:Little Piano')
                # Portrait's two separate painted entrances must remain
                # separate in landscape too, rather than overlapping targets.
                self.assertLess(max(x for x, y in hut['polygon']),
                                min(x for x, y in piano['polygon']))
                self.assertEqual(hotspots['ladder']['target'], 'scene:treehouse')

    def test_ladder_interiors_are_continuous(self):
        _, scenes, _, _ = title.Load()
        # Sweep between the rails at every source-pixel row, across rungs
        # and their gaps. Portrait artwork has its own traced composition.
        bands = {
            'treehouse': (540, 580, lambda y: (1455, 1595)),
            'treehouse-portrait': (1240, 1420, lambda y: (850, 1005)),
            'bookshelf': (480, 850, lambda y: (1660-.28*(y-480), 1670)),
            'bookshelf-portrait': (630, 1370, lambda y: (1015-.13*(y-630), 1022)),
            'campus': (145, 445, lambda y: (942+.215*(y-137), 991+.205*(y-141))),
            'campus-portrait': (300, 540, lambda y: (520+.19*(y-300), 590+.17*(y-300))),
        }
        for scene in scenes:
            start, end, edges = bands[scene['name']]
            for y in range(start, end):
                left, right = edges(y)
                for x in range(round(left), round(right)):
                    self.assertEqual(hit(scene, x+.5, y+.5), 'ladder', (scene['name'], x, y))

    def test_nearby_targets_and_background_remain_separate(self):
        _, scenes, _, _ = title.Load()
        samples = {
            'treehouse': [(1400, 550, None), (1000, 400, 'easel')],
            'treehouse-portrait': [(780, 1300, None), (850, 500, 'easel')],
            'bookshelf': [(1500, 600, None), (900, 500, 'book-123')],
            'bookshelf-portrait': [(900, 1000, None), (700, 700, 'book-123')],
            'campus': [(900, 300, None), (200, 300, 'music-hut'), (1430, 340, 'piano'), (200, 700, 'garden')],
            'campus-portrait': [(480, 430, None), (200, 530, 'music-hut'), (900, 530, 'piano'), (200, 850, 'garden')],
        }
        for scene in scenes:
            for x, y, expected in samples[scene['name']]:
                self.assertEqual(hit(scene, x, y), expected, (scene['name'], x, y))

    def test_distinct_variant_dimensions_and_parents(self):
        data, scenes, parents, hotspots = self.load(self.fixture())
        base_count = len(data['scenes'])
        self.assertEqual(len(scenes), 2 * base_count)
        for index in range(base_count):
            self.assertEqual(scenes[index + base_count]['base'], index)
            self.assertEqual(scenes[index + base_count]['width'], 941)
            self.assertEqual(parents[index + base_count], parents[index])
            left = [h for h in hotspots if h['scene'] == index]
            right = [h for h in hotspots if h['scene'] == index + base_count]
            self.assertEqual([h['game'] for h in left], [h['game'] for h in right])
            self.assertEqual(right[0]['polygon'][0], tuple(reversed(left[0]['polygon'][0])))
        output = title.Render(data, scenes, parents, hotspots)
        self.assertIn('TITLE_SCENE_PORTRAIT', output)
        self.assertIn('941, 941, 941', output)

    def test_reject_changed_identity_or_destination(self):
        data = self.fixture()
        data['scenes'][0]['portrait']['hotspots'][0]['target'] = 'game:Picture Book'
        with self.assertRaisesRegex(SystemExit, 'IDs and targets'):
            self.load(data)

    def test_reject_invalid_portrait_dimensions(self):
        data = self.fixture()
        data['scenes'][0]['portrait']['height'] = 1
        with self.assertRaisesRegex(SystemExit, 'taller dimensions'):
            self.load(data)

    def test_reject_outside_geometry(self):
        data = self.fixture()
        data['scenes'][0]['portrait']['hotspots'][0]['polygon'][0] = [-1, 0]
        with self.assertRaisesRegex(SystemExit, 'outside scene'):
            self.load(data)


if __name__ == '__main__':
    unittest.main()

"""Validate title variants without selecting unapproved portrait artwork."""
import copy
import importlib.util
import json
import sys
from pathlib import Path
import tempfile
import unittest
import subprocess
from PIL import Image, ImageFilter
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('title_scenes', ROOT/'tools/title_scenes.py')
title = importlib.util.module_from_spec(spec)
spec.loader.exec_module(title)
sys.path.insert(0, str(ROOT/'tools'))
import web_images


def inside(polygon, x, y):
    """Even-odd source geometry, including the existing overlap policy."""
    result = False
    for (xi, yi), (xj, yj) in zip(polygon, polygon[-1:] + polygon[:-1]):
        if (yi > y) != (yj > y) and x < xi + (y-yi)*(xj-xi)/(yj-yi):
            result = not result
    return result


def hit(scene, x, y):
    candidates = [h for h in scene['hotspots'] if inside(h['polygon'], x, y)
                  and not (h.get('occlusion') and inside(h['occlusion'], x, y))]
    return min(candidates, key=lambda h: h['glow_rect'][2]*h['glow_rect'][3])['id'] if candidates else None


class TitleVariants(unittest.TestCase):
    def signs(self):
        data = json.loads(title.SOURCE.read_text())
        campus = next(s for s in data['scenes'] if s['name'] == 'campus')
        for scene in (campus, campus['portrait']):
            path = next(h for h in scene['hotspots'] if h['id'] == 'beach-path')
            # Existing separate sprite stands in for an approved wooden sign;
            # these fixtures never replace production art or routes.
            path['glow_rect'] = [100, 100, 200, 160]
            path['polygon'] = [[110, 110], [290, 110], [290, 250], [110, 250]]
            path['sign'] = {'label': 'Beach', 'label_rect': [20, 20, 160, 50], 'direction': 'left'}
        return data, campus

    def test_sign_board_metadata_and_locale_inventory(self):
        data, campus = self.signs()
        _, scenes, _, hotspots = self.load(data)
        signs = [h for h in hotspots if h['sign_label']]
        self.assertEqual(len(signs), 2)
        for sign in signs:
            self.assertEqual(sign['sign_label'], 'Beach')
            self.assertEqual(sign['sign_rect'], [20, 20, 160, 50])
            self.assertEqual(scenes[sign['scene_target']]['name'], 'beach')
        output = title.Render(*self.load(data))
        self.assertIn('TITLE_SIGN_LABEL', output)
        self.assertIn('TITLE_SIGN_RECT', output)
        self.assertIn('TITLE_SIGN_DIRECTION', output)
        self.assertTrue(all(sign['sign_direction'] == 1 for sign in signs))
        locales = json.loads((ROOT/'locales/ui.json').read_text())
        for label, translations in {'Beach': ['Strand', 'Playa'], 'Farm': ['Bauernhof', 'Granja'],
                                    'Desert': ['Wüste', 'Desierto']}.items():
            self.assertEqual(locales[label], translations)

    def test_sign_directions_are_data_driven(self):
        for direction, code in title.SIGN_DIRECTIONS.items():
            data, campus = self.signs()
            for scene in (campus, campus['portrait']):
                next(h for h in scene['hotspots'] if h['id'] == 'beach-path')['sign']['direction'] = direction
            signs = [h for h in self.load(data)[3] if h['sign_label']]
            self.assertEqual([h['sign_direction'] for h in signs], [code, code])

    def test_explicit_testing_destinations(self):
        for label, code in (('Farm', 1), ('Desert', 2)):
            data, campus = self.signs()
            for scene in (campus, campus['portrait']):
                path = next(h for h in scene['hotspots'] if h['id'] == 'beach-path')
                # Keep the old waterfront route for graph reachability.
                path = copy.deepcopy(path)
                path['id'] = label.lower() + '-sign'
                path['sign']['label'] = label
                path['target'] = 'preview:' + label
                scene['hotspots'].append(path)
            signs = [h for h in self.load(data)[3] if h['sign_label'] == label]
            self.assertEqual([h['preview_room'] for h in signs], [code, code])
            self.assertTrue(all(h['game'] == '' and h['scene_target'] < 0 for h in signs))

    def test_modal_and_preview_locales(self):
        rows = json.loads((ROOT/'locales/ui.json').read_text())
        self.assertEqual(rows['Not yet implemented'], ['Noch nicht implementiert', 'Aún no implementado'])
        for key in ('Close', 'Development preview', 'This room is a testing preview.'):
            self.assertEqual(len(rows[key]), 2)
            self.assertTrue(all(value and value != key for value in rows[key]))

    def test_testing_builds_reject_published_outputs(self):
        import build_web
        with self.assertRaisesRegex(SystemExit, 'private output'):
            build_web.build(ROOT/'build/web', test_rooms=True)
        for app in ('build/app', str(ROOT/'build/app')):
            result = subprocess.run(['make','-n','TEST_ROOMS=1','APP='+app], cwd=ROOT,
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('requires a private APP', result.stderr)

    def test_reject_invalid_sign_board_or_physical_sprite(self):
        for update, error in [
                ({'sign': {'label': 'Elsewhere', 'label_rect': [20, 20, 160, 50], 'direction': 'left'}}, 'invalid path sign label'),
                ({'sign': {'label': 'Beach', 'label_rect': [20, 20, 181, 50], 'direction': 'left'}}, 'label_rect'),
                ({'sign': {'label': 'Beach', 'label_rect': [20, 20, 160, 0], 'direction': 'left'}}, 'label_rect'),
                ({'sign': {'label': 'Beach', 'label_rect': [20, 20, 1.5, 50], 'direction': 'left'}}, 'label_rect'),
                ({'sign': {'label': 'Beach', 'label_rect': [0, 0, 160, 50], 'direction': 'left'}}, 'physical hit area'),
                ({'sign': {'label': 'Beach', 'label_rect': [20, 20, 160, 50], 'direction': 'sideways'}}, 'invalid path sign direction'),
                ({'rest': ''}, 'separate resting sprite'),
                ({'target': 'guide:tour'}, 'actual destination'),
                ({'polygon': [[90, 110], [290, 110], [290, 250]]}, 'hit polygon'),
                ({'target': 'scene:unconfirmed-farm'}, 'unknown scene')]:
            with self.subTest(update=update):
                data, campus = self.signs()
                for scene in (campus, campus['portrait']):
                    next(h for h in scene['hotspots'] if h['id'] == 'beach-path').update(update)
                with self.assertRaisesRegex(SystemExit, error):
                    self.load(data)

    def test_reject_different_sign_label_in_portrait(self):
        data, campus = self.signs()
        next(h for h in campus['portrait']['hotspots'] if h['id'] == 'beach-path')['sign']['label'] = 'Farm'
        with self.assertRaisesRegex(SystemExit, 'portrait path sign labels'):
            self.load(data)

    def test_port_entries_have_separate_painted_layers(self):
        _, scenes, _, _ = title.Load()
        for name in ('beach', 'beach-portrait'):
            scene = next(s for s in scenes if s['name'] == name)
            orientation = 'portrait' if name.endswith('-portrait') else 'landscape'
            approved = np.asarray(Image.open(ROOT/f'art/generated/world-scene-refresh/beach-{orientation}-clean.png').convert('RGB'))
            plate = np.asarray(Image.open(ROOT/scene['image']).convert('RGB'))
            self.assertTrue(np.array_equal(approved, plate), name)
            for ident in ('fishing-boat', 'crab-family'):
                target = next(h for h in scene['hotspots'] if h['id'] == ident)
                x, y, w, h = target['glow_rect']
                with Image.open(ROOT/target['rest']) as rest, Image.open(ROOT/target['glow']) as glow:
                    self.assertEqual(rest.size, (w, h))
                    self.assertEqual(rest.mode, 'RGBA')
                    self.assertEqual(rest.getchannel('A').tobytes(), glow.getchannel('A').tobytes())
                    painted = [(px, py) for py in range(0, h, 3) for px in range(0, w, 3)
                               if rest.getpixel((px, py))[3] > 200 and hit(scene, x+px, y+py) == ident]
                    self.assertGreater(len(painted), 30, (name, ident))
            water = (450, 430) if name == 'beach' else (330, 440)
            self.assertIsNone(hit(scene, *water))

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
                if 'occlusion' in hotspot:
                    hotspot['occlusion'] = [[y, x] for x, y in hotspot['occlusion']]
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

    def test_waterfront_routes_and_art(self):
        _, scenes, parents, _ = title.Load()
        for suffix in ('', '-portrait'):
            campus, beach, aquarium = [next(s for s in scenes if s['name'] == name+suffix)
                                       for name in ('campus', 'beach', 'aquarium')]
            routes = lambda scene: {h['id']: h['target'] for h in scene['hotspots']}
            self.assertEqual(routes(campus)['beach-path'], 'scene:beach')
            self.assertEqual(routes(beach), {'campus-path': 'scene:campus', 'bunker-door': 'scene:aquarium',
                                            'fishing-boat': 'game:Little Fishing Boat',
                                            'crab-family': 'game:Crab Family Counting'})
            self.assertEqual(routes(aquarium), {'beach-stairs': 'scene:beach'})
            for scene in (beach, aquarium):
                with Image.open(ROOT/scene['image']) as image:
                    self.assertEqual(image.size, (scene['width'], scene['height']))
                with Image.open(ROOT/scene['low']) as low:
                    self.assertEqual(low.width, 240)
                    self.assertAlmostEqual(low.height/low.width, scene['height']/scene['width'], delta=.005)
            self.assertEqual(parents[scenes.index(beach)], next(i for i, s in enumerate(scenes) if s['name']=='campus'))
            self.assertEqual(parents[scenes.index(aquarium)], next(i for i, s in enumerate(scenes) if s['name']=='beach'))

    def test_beach_return_arrow_follows_sandy_campus_path(self):
        _, scenes, _, _ = title.Load()
        for suffix in ('', '-portrait'):
            with self.subTest(orientation=suffix or 'landscape'):
                beach = next(s for s in scenes if s['name'] == 'beach'+suffix)
                arrow = next(h for h in beach['hotspots'] if h['id'] == 'campus-path')
                aquarium = next(h for h in beach['hotspots'] if h['id'] == 'bunker-door')
                self.assertEqual(arrow['target'], 'scene:campus')
                arrow_box = (min(x for x, y in arrow['polygon']), min(y for x, y in arrow['polygon']),
                             max(x for x, y in arrow['polygon']), max(y for x, y in arrow['polygon']))
                aquarium_box = (min(x for x, y in aquarium['polygon']), min(y for x, y in aquarium['polygon']),
                                max(x for x, y in aquarium['polygon']), max(y for x, y in aquarium['polygon']))
                # The new sandy return path is left of the Aquarium entrance.
                self.assertLess(arrow_box[2], aquarium_box[0])
                self.assertGreater(arrow_box[1], beach['height'] * .55)
                rx, ry, width, height = arrow['glow_rect']
                self.assertTrue(any(hit(beach, x, y) == 'campus-path'
                                    for x in range(rx, rx+width, 3)
                                    for y in range(ry, ry+height, 3)))
                with Image.open(ROOT/arrow['rest']) as rest:
                    high = rest.getchannel('A').getextrema()[1]
                    self.assertGreater(high, 50)
                    self.assertLess(high, 150)

    def test_arrow_foreground_and_visible_rest(self):
        _, scenes, _, _ = title.Load()
        for name, foreground in (('campus', (623, 495)), ('campus-portrait', (563, 683))):
            scene = next(s for s in scenes if s['name'] == name)
            arrow = next(h for h in scene['hotspots'] if h['id']=='beach-path')
            self.assertTrue(inside(arrow['polygon'], *foreground))
            self.assertTrue(inside(arrow['occlusion'], *foreground))
            self.assertIsNone(hit(scene, *foreground))
            rx, ry, w, h = arrow['glow_rect']
            for key in ('rest', 'glow'):
                with Image.open(ROOT/arrow[key]) as image:
                    self.assertEqual(image.size, (w, h))
                    self.assertEqual(image.mode, 'RGBA')
                    maximum = image.getchannel('A').getextrema()[1]
                    self.assertGreater(maximum, 50)
                    if key == 'rest':
                        self.assertLess(maximum, 150)
                        # The arrow really extends under the tiger. The separate
                        # foreground, rather than a polygon notch, hides it.
                        self.assertGreater(image.getpixel((foreground[0]-rx, foreground[1]-ry))[3], 0)
            with Image.open(ROOT/scene['foreground']) as image:
                self.assertGreater(image.getpixel(foreground)[3], 240)
            # At least one visible, tappable point remains outside the tiger.
            self.assertTrue(any(hit(scene, x, y)=='beach-path'
                                for x in range(rx, rx+w, 3) for y in range(ry, ry+h, 3)))

    def test_actual_separated_layers_preserve_approved_art(self):
        _, scenes, _, _ = title.Load()
        layered = [s for s in scenes if s.get('foreground')]
        self.assertEqual(len(layered), 6)
        for scene in layered:
            with self.subTest(scene=scene['name']):
                original = np.asarray(Image.open(ROOT/scene['image']).convert('RGB'))
                foreground = Image.open(ROOT/scene['foreground']).convert('RGBA')
                background = np.asarray(Image.open(ROOT/scene['background']).convert('RGB'))
                pixels = np.asarray(foreground)
                alpha = pixels[:, :, 3]
                self.assertEqual(foreground.size, (scene['width'], scene['height']))
                self.assertEqual((int(alpha.min()), int(alpha.max())), (0, 255))
                self.assertTrue(np.array_equal(pixels[alpha == 255, :3], original[alpha == 255]))
                # Reconstructed background is confined to the extracted object,
                # preserving every unrelated object and accepted scene pixel.
                outside = np.asarray(foreground.getchannel('A').filter(ImageFilter.MaxFilter(13))) == 0
                self.assertTrue(np.array_equal(background[outside], original[outside]))
                self.assertGreater(np.abs(background.astype(int)-original).sum(), 10000)
                self.assertGreater(float((alpha > 0).mean()), .01)
                self.assertLess(float((alpha > 0).mean()), .3)
                x, y, edge, travel = scene['paper']
                width = edge*.78
                visible = []
                for dx in (0, travel):
                    area = alpha[round(y-edge/2):round(y+edge/2),
                                 round(x+dx-width/2):round(x+dx+width/2)]
                    visible.append(float((255-area).mean()/255))
                self.assertGreater(visible[0], .04)
                self.assertLess(visible[0], .3)
                self.assertGreater(visible[1], visible[0]+.2)
                self.assertLess(visible[1], .75)

    def test_waterfront_browser_encodings(self):
        _, scenes, _, _ = title.Load()
        files = {s[key]: ROOT/s[key] for s in scenes if s['name'].startswith(('beach', 'aquarium'))
                 for key in ('image', 'low')}
        work = ROOT/'work/title-tests'
        work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as directory:
            result, names, metadata = web_images.prepare_web_images(files, Path(directory)/'cache')
            self.assertEqual(len(result), 8)
            for name, path in result.items():
                with Image.open(path) as decoded, Image.open(files[name]) as source:
                    self.assertEqual(decoded.size, source.size)
                    if name in metadata:
                        self.assertEqual(decoded.format, 'WEBP')
                        self.assertTrue(names[name].endswith('.webp'))
                    else:
                        # Tiny placeholders may already be smaller than WebP.
                        self.assertEqual(path, files[name])

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

    def test_landscape_peekaboo_moves_clear_of_piano(self):
        _, scenes, _, _ = title.Load()
        def box(hotspot):
            return (min(x for x, y in hotspot['polygon']), min(y for x, y in hotspot['polygon']),
                    max(x for x, y in hotspot['polygon']), max(y for x, y in hotspot['polygon']))
        for name, peek_point, piano_box in (
                ('campus', (660, 300), (1352, 284, 1521, 425)),
                ('campus-portrait', (914, 1287), (819, 462, 1005, 622))):
            with self.subTest(scene=name):
                scene = next(s for s in scenes if s['name'] == name)
                peek = next(h for h in scene['hotspots'] if h['id'] == 'hiding-bush')
                peek_box = box(peek)
                if name == 'campus':
                    self.assertLess(peek_box[2], piano_box[0])
                else:
                    self.assertGreater(peek_box[1], piano_box[3])
                self.assertEqual(hit(scene, *peek_point), 'hiding-bush')
                self.assertEqual(peek['target'], 'game:Hide & Seek')

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
            if scene['name'] not in bands:
                continue
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
            for x, y, expected in samples.get(scene['name'], []):
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

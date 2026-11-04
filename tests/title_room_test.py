"""The Treehouse room is a clean plate with separate object layers on top,
and its round window opens a look-only outside view with a Back button."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('title_scenes', ROOT / 'tools/title_scenes.py')
title = importlib.util.module_from_spec(spec)
spec.loader.exec_module(title)

# Each tappable piece of furniture is carried by its own layer.
CARRIED = {'shape-sorter', 'bookshelf', 'puzzle-table', 'easel', 'ladder'}


def lossless(path):
    """True when the WebP holds a lossless (VP8L) bitstream."""
    data = Path(path).read_bytes()
    return b'VP8L' in data[12:64]


class TreehouseRoom(unittest.TestCase):
    def test_animation_atlases_and_generated_runtime(self):
        spec = importlib.util.spec_from_file_location('title_animations', ROOT/'tools/title_animations.py')
        animation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(animation)
        self.assertEqual(animation.TARGET.read_text(), animation.generate())
        layers = json.loads(animation.SOURCE.read_text())['layers']
        for scene in ('window', 'window-portrait'):
            selected = [layer for layer in layers if layer['scene'] == scene]
            self.assertEqual(len(selected), 12)
            self.assertEqual(selected[-1]['mode'], 2)
            self.assertTrue(all(l['mode'] != 2 for l in selected[:-1]))
            base = next(s for s in json.loads(title.SOURCE.read_text())['scenes'] if s['name'] == 'window')
            preload = base if scene == 'window' else base['portrait']
            self.assertEqual(set(preload['animations']), {layer['path'] for layer in selected} | {f'assets/jungle/title/window-animation/{"portrait" if scene.endswith("portrait") else "landscape"}-frame.webp'})
            self.assertEqual(sum(layer['mode'] == 2 for layer in selected), 1)
            self.assertEqual(sum(layer['mode'] == 1 for layer in selected), 4)
            for layer in selected:
                self.assertTrue(lossless(ROOT/layer['path']))
                with Image.open(ROOT/layer['path']) as image:
                    columns, count, width, height = layer['sheet']
                    first = image.crop((0, 0, width, height))
                    last = image.crop(((count-1)*width, 0, count*width, height))
                    if count > 1: self.assertNotEqual(first.tobytes(), last.tobytes())

    def test_window_weather_depth_and_alpha(self):
        layers=json.loads((ROOT/'tools/title_animations.json').read_text())['layers']
        for scene in ('window','window-portrait'):
            chosen=[l for l in layers if l['scene']==scene]
            clouds=[l for l in chosen if l['mode']==-1]
            self.assertEqual(len(clouds),2)
            self.assertNotEqual(clouds[0]['timing'][1],clouds[1]['timing'][1])
            self.assertNotEqual(clouds[0]['rect'][1],clouds[1]['rect'][1])
            depth=next(i for i,l in enumerate(chosen) if l['mode']==-2)
            self.assertTrue(all(chosen.index(l)<depth for l in clouds))
            twig=next(l for l in chosen if l['mode']==-3)
            self.assertGreater(chosen.index(twig),depth)
            with Image.open(ROOT/twig['path']) as image:
                self.assertEqual(image.getchannel('A').getextrema(),(0,255))

    def test_painted_river_has_no_animation(self):
        layers = json.loads((ROOT/'tools/title_animations.json').read_text())['layers']
        for layer in layers:
            if layer['mode'] == 0:
                self.assertIn('-leaves-', layer['path'])
        for orientation in ('landscape', 'portrait'):
            self.assertFalse((ROOT/f'assets/jungle/title/window-animation/{orientation}-water.webp').exists())
        window = next(s for s in json.loads(title.SOURCE.read_text())['scenes'] if s['name'] == 'window')
        for scene in (window, window['portrait']):
            self.assertFalse(any('-water.' in path for path in scene['animations']))

    def test_window_frame_occludes_flyers(self):
        renderer = (ROOT/'host/jungle_menu.zi').read_text()
        draw = renderer.index('    TitleAnimations(session, scene, picture, view, now)')
        frame = renderer.index('TitleWindowFrame(session, scene, picture, view)', draw)
        self.assertGreater(frame, draw)
        for orientation in ('landscape', 'portrait'):
            path = ROOT/f'assets/jungle/title/window-animation/{orientation}-frame.webp'
            self.assertTrue(lossless(path))
            with Image.open(path) as image:
                alpha = image.getchannel('A')
                self.assertEqual(alpha.getpixel((0,0)), 255)
                self.assertEqual(alpha.getpixel((image.width//2,image.height//2)), 0)

    def setUp(self):
        self.data = json.loads(title.SOURCE.read_text())
        self.room = next(s for s in self.data['scenes'] if s['name'] == 'treehouse')

    def variants(self, data=None):
        room = self.room if data is None else next(s for s in data['scenes'] if s['name'] == 'treehouse')
        return [(room, self.data['width'], self.data['height']), (room['portrait'], 1024, 1536)]

    def test_plate_and_every_object_layer(self):
        for scene, width, height in self.variants():
            with Image.open(ROOT / scene['background']) as plate:
                self.assertEqual((plate.format, plate.size), ('WEBP', (width, height)))
                self.assertEqual(plate.convert('RGBA').getchannel('A').getextrema(), (255, 255))
            ids = [layer['id'] for layer in scene['objects']]
            self.assertGreaterEqual(len(ids), 10)
            self.assertEqual(len(ids), len(set(ids)))
            for layer in scene['objects']:
                with self.subTest(layer=layer['id'], width=width):
                    self.assertEqual(set(layer), {'id', 'image', 'rect'})
                    x, y, w, h = layer['rect']
                    self.assertTrue(0 <= x and 0 <= y and x + w <= width and y + h <= height)
                    self.assertTrue(layer['image'].startswith('assets/jungle/title/room/'))
                    self.assertTrue(lossless(ROOT / layer['image']))
                    with Image.open(ROOT / layer['image']) as picture:
                        self.assertEqual((picture.format, picture.mode, picture.size), ('WEBP', 'RGBA', (w, h)))
                        alpha = picture.getchannel('A')
                        # A real cut-out: an opaque body inside a clear margin,
                        # except where the scene's own border cuts the object.
                        self.assertEqual(alpha.getextrema(), (0, 255))
                        sides = {'left': (x > 0, [(0, v) for v in range(h)]),
                                 'right': (x + w < width, [(w - 1, v) for v in range(h)]),
                                 'top': (y > 0, [(u, 0) for u in range(w)]),
                                 'bottom': (y + h < height, [(u, h - 1) for u in range(w)])}
                        for side, (inside, pixels) in sides.items():
                            if inside:
                                self.assertEqual(max(alpha.getpixel(p) for p in pixels), 0, side)

    def test_hotspots_follow_their_objects(self):
        for scene, width, height in self.variants():
            layers = {layer['id']: layer for layer in scene['objects']}
            carried = {h['id']: h for h in scene['hotspots'] if 'object' in h}
            self.assertEqual(set(carried), CARRIED)
            for hotspot in carried.values():
                with self.subTest(hotspot=hotspot['id'], width=width):
                    layer = layers[hotspot['object']]
                    self.assertEqual(hotspot['glow_rect'], layer['rect'])
                    x, y, w, h = layer['rect']
                    self.assertTrue(all(x <= px < x + w and y <= py < y + h for px, py in hotspot['polygon']))
                    with Image.open(ROOT / hotspot['glow']) as glow:
                        self.assertEqual(glow.size, (w, h))
            # The old full-room glows are gone with the old painting.
            for hotspot in scene['hotspots']:
                self.assertFalse(Path(hotspot['glow']).name.startswith('treehouse-') and hotspot['id'] != 'window')

    def test_moving_or_resizing_a_layer_moves_its_hotspot(self):
        data = copy.deepcopy(self.data)
        scene = self.variants(data)[0][0]
        layer = next(layer for layer in scene['objects'] if layer['id'] == 'easel')
        hotspot = next(h for h in scene['hotspots'] if h['id'] == 'easel')
        before = [list(point) for point in hotspot['polygon']]
        x, y, w, h = layer['rect']
        layer['rect'] = [x - 100, y + 20, w, h]
        self.assertTrue(title.Follow(data))
        self.assertEqual(hotspot['glow_rect'], layer['rect'])
        self.assertEqual(hotspot['polygon'], [[px - 100, py + 20] for px, py in before])
        self.assertFalse(title.Follow(data))
        layer['rect'] = [x - 100, y + 20, w // 2, h // 2]
        self.assertTrue(title.Follow(data))
        self.assertTrue(all(x - 100 <= px <= x - 100 + w // 2 for px, _ in hotspot['polygon']))
        title.Objects(dict(scene, width=self.data['width'], height=self.data['height']))

    def test_broken_layers_are_rejected(self):
        scene = dict(self.room, width=self.data['width'], height=self.data['height'])
        title.Objects(scene)
        for change in ('outside', 'missing-picture', 'duplicate', 'stale-hotspot', 'unknown-object'):
            broken = copy.deepcopy(scene)
            if change == 'outside':
                broken['objects'][0]['rect'][0] = self.data['width'] - 1
            elif change == 'missing-picture':
                broken['objects'][0]['image'] = 'assets/jungle/title/room/missing.webp'
            elif change == 'duplicate':
                broken['objects'][1]['id'] = broken['objects'][0]['id']
            elif change == 'stale-hotspot':
                next(h for h in broken['hotspots'] if h['id'] == 'easel')['glow_rect'][0] += 5
            else:
                next(h for h in broken['hotspots'] if h['id'] == 'easel')['object'] = 'piano'
            with self.subTest(change=change), self.assertRaises(SystemExit):
                title.Objects(broken)

    def test_window_opens_a_look_only_view(self):
        view = next(s for s in self.data['scenes'] if s['name'] == 'window')
        self.assertIs(view['back'], True)
        self.assertEqual((view['hotspots'], view['portrait']['hotspots']), ([], []))
        for scene, width, height in ((view, self.data['width'], self.data['height']), (view['portrait'], 1024, 1536)):
            for key, size in (('image', (width, height)), ('low', (240, round(height * 240 / width)))):
                with Image.open(ROOT / scene[key]) as picture:
                    self.assertEqual((picture.format, picture.size), ('WEBP', size))
        for scene, width, height in self.variants():
            window = scene['hotspots'][-1]
            self.assertEqual((window['id'], window['target']), ('window', 'scene:window'))
            self.assertNotIn('object', window)
            # The tiger in front of the window keeps its own taps and glow.
            self.assertGreaterEqual(len(window['occlusion']), 3)
        data, scenes, parents, _ = title.Load()
        names = [scene['name'] for scene in scenes]
        self.assertEqual(scenes[parents[names.index('window')]]['name'], 'treehouse')
        rendered = title.Render(data, *title.Load()[1:])
        self.assertIn('TITLE_SCENE_BACK', rendered)
        self.assertIn('TITLE_OBJECT_PATH', rendered)

    def test_room_draws_its_layers_and_back(self):
        menu = (ROOT / 'host/jungle_menu.zi').read_text()
        self.assertIn('TitleObjects(session, scene, picture, view)', menu)
        self.assertIn('TITLE_SCENE_BACK[scene] != 0', menu)
        # title_glow must never repaint the layered room from the old painting.
        glow = (ROOT / 'tools/title_glow.py').read_text()
        self.assertIn('room_owned(scene)', glow)


if __name__ == '__main__':
    unittest.main()

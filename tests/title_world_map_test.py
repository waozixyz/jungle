"""The world map's data and art: every area is a landmark on both plates.

tools/title_world_map.json lists the landmarks; tools/title_world_map.py writes
the "map" scene into tools/title_hotspots.json. Behavior (hover, travel, the
locked cue, Back, the map button on every scene, the fit) is in title_test.zi.
"""
import json
from pathlib import Path
import unittest
from PIL import Image
from world_map_geometry import selectable_point
from design_size import design_size

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT/'tools/title_world_map.json').read_text())
DATA = json.loads((ROOT/'tools/title_hotspots.json').read_text())
SCENES = {s['name']: s for s in DATA['scenes']}
MAP = SCENES[SPEC['scene']]
VIEWS = {'landscape': MAP, 'portrait': MAP['portrait']}


def exact(path):
    row = json.loads((ROOT/'tools/canonical_avif.json').read_text())['files'][Path(path).relative_to(ROOT).as_posix()]
    with Image.open(path) as image:
        assert image.format == 'AVIF'
        if row['lossless']:
            import hashlib
            assert hashlib.sha256(image.convert('RGBA').tobytes()).hexdigest() == row['source_rgba_sha256']
    return row['lossless']


class WorldMapTest(unittest.TestCase):
    def test_generator_uses_one_rect_despite_legacy_portrait_geometry(self):
        import sys
        sys.path.insert(0,str(ROOT/'tools'))
        try:
            from title_world_map import SharedGeometry
            mark={'rects':{'landscape':[100,200,320,180],'portrait':[900,20,12,90]},'rotation':24}
            original=[10,20,160,90]
            polygon=[[10,20],[170,20],[170,110],[10,110]]
            landscape=SharedGeometry(mark,original,polygon)
            portrait=SharedGeometry(mark,original,polygon)
            self.assertEqual(landscape,portrait)
            self.assertEqual(landscape,([100,200,320,180],[[100,200],[420,200],[420,380],[100,380]]))
        finally: sys.path.pop(0)

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
                if mark.get('terrain_region'):
                    self.assertEqual((spot['rest'], spot['glow']), ('', ''))
                    self.assertEqual(spot['target'], 'scene:desert')
                else:
                    self.assertEqual(spot['rest'], f'assets/jungle/title/world-map/{mark["id"]}.avif')
                    self.assertEqual(spot['glow'], f'assets/jungle/title/world-map/{mark["id"]}-glow.avif')
                self.assertNotIn('sign', spot)
        self.assertTrue(any(m['target'].startswith('locked:') for m in SPEC['landmarks']), 'nothing beyond the desert')
        self.assertIs(MAP.get('back'), True)

    def test_landmarks_stay_apart_and_inside(self):
        for orientation, view in VIEWS.items():
            width, height = (view.get('width', DATA['width']), view.get('height', DATA['height']))
            for spot in view['hotspots']:
                x, y, w, h = spot['glow_rect']
                self.assertTrue(0 <= x and 0 <= y and x + w <= width and y + h <= height, (orientation, spot['id']))
                # The corner controls (Back, sound, collection, map) stay clear.
                self.assertGreater(y + h * 0.25, height * 0.04, (orientation, spot['id']))
                for size in ((360,800),(420,900),(960,600)):
                    _,_,radius = selectable_point(view,spot,size)
                    self.assertGreaterEqual(radius,1 if spot['target'].startswith('locked:') else 3,
                                            (orientation,spot['id'],size,'covered or impractical hit'))

    def test_full_painting_fit_keeps_terrain_edges_in_both_orientations(self):
        import sys
        sys.path.insert(0,str(ROOT/'tools'))
        try:
            from title_scenes import Load,MapSafe
            _,scenes,_,hotspots = Load()
            for index,scene in enumerate(scenes):
                expected = [0,0,3072,2048] if scene['name'] in ('map','map-portrait') else [0,0,0,0]
                # A scene's own safe rect (Campus portrait's original painting
                # between its widened strips) stays whole on screen.
                if scene.get('safe'): expected = list(scene['safe'])
                self.assertEqual(MapSafe(scene,[h for h in hotspots if h['scene']==index]),expected)
        finally:
            sys.path.pop(0)

    def test_runtime_images(self):
        for orientation, view in VIEWS.items():
            size = (view.get('width', DATA['width']), view.get('height', DATA['height']))
            for key in ('image', 'low'):
                path = ROOT/view[key]
                self.assertEqual(path.suffix, '.avif')
                self.assertFalse(exact(path), path)
                with Image.open(path) as picture:
                    self.assertEqual(picture.mode, 'RGB')
                    if key == 'image':
                        self.assertEqual(design_size(path, picture), size)
                    else:
                        self.assertEqual(picture.width, 240)
            for spot in view['hotspots']:
                for key in ('rest', 'glow'):
                    if not spot[key]:
                        continue
                    path = ROOT/spot[key]
                    exact(path)
                    # Cut-out standard: transparent art keeps full 4:4:4 color.
                    row = json.loads((ROOT/'tools/canonical_avif.json').read_text())['files'][spot[key]]
                    self.assertTrue(row['alpha'] and row['subsampling'] == '444', path)
                    with Image.open(path) as picture:
                        self.assertEqual(picture.mode, 'RGBA')
                        # Both share the glow rectangle.
                        x, y, w, h = spot['glow_rect']
                        self.assertAlmostEqual(picture.width / picture.height, w / h, delta=0.05)
                        self.assertEqual(picture.getchannel('A').getextrema()[0], 0)
        self.assertEqual(sorted(p.name for p in (ROOT/'assets/jungle/title/world-map').iterdir()),
                         sorted(n for m in SPEC['landmarks'] for n in (m['id'] + '.avif', m['id'] + '-glow.avif')))
        self.assertFalse(list((ROOT/'assets/jungle/title').glob('world-map*.png')))

    def test_paper_and_cue_match_the_app(self):
        title = (ROOT/'host/jungle_title.zi').read_text()
        self.assertIn(f'TITLE_MAP_PAPER :: 0x{SPEC["paper"]}ff', title)
        self.assertEqual(SPEC['canvas'], [3072, 2048])
        self.assertEqual((MAP['width'], MAP['height']), tuple(SPEC['canvas']))
        centers = {m['id']: m['center'] for m in SPEC['landmarks']}
        for mark in SPEC['landmarks']:
            x, y, width, height = next(h['glow_rect'] for h in MAP['hotspots'] if h['id'] == mark['id'])
            self.assertAlmostEqual(x + width/2, centers[mark['id']][0], delta=.5)
            self.assertAlmostEqual(y + height/2, centers[mark['id']][1], delta=.5)
        self.assertEqual(MAP['hotspots'], MAP['portrait']['hotspots'], 'one map must have identical hit shapes and placement')
        for field in ('width', 'height', 'image', 'low', 'exploration', 'exploration_routes'):
            self.assertEqual(MAP[field], MAP['portrait'][field], field)
        self.assertEqual(MAP['exploration'], [dict(area=m['id'], center=m['center'], region=m['region'])
                                            for m in SPEC['landmarks'] if not m['target'].startswith('locked:')])
        self.assertEqual(MAP['exploration_routes'], SPEC['routes'])
        self.assertTrue((ROOT/'assets/jungle/sounds/not-yet.wav').is_file())
        menu = (ROOT/'host/jungle_menu.zi').read_text()
        self.assertRegex(menu, r'TitleMapEntry\(scene\) && TitleMapButton\(')
        # Farm is a full-window game with floating Back. Its route into the
        # map is through the painted Campus, which retains the map button.
        self.assertIn('GameSceneBack(', (ROOT/'host/jungle_host.zi').read_text())
        labels = json.loads((ROOT/'locales/ui.json').read_text())
        self.assertEqual(len(labels['World map']), 2)

    def test_each_place_reveals_its_own_landmark(self):
        from world_map_geometry import fog_alpha
        import numpy as np
        areas = {place['area'] for place in MAP['exploration']}
        for route in MAP['exploration_routes']:
            self.assertLessEqual(set(route['areas']), areas, route)
        for spot in MAP['hotspots']:
            if spot['id'] not in areas:
                continue
            x, y, w, h = spot['glow_rect']
            middle = np.array([[x + w / 2]], dtype=np.float32), np.array([[y + h / 2]], dtype=np.float32)
            self.assertEqual(int(fog_alpha(MAP, {spot['id']}, *middle)[0, 0]), 0, spot['id'])
            self.assertEqual(int(fog_alpha(MAP, set(), *middle)[0, 0]), 255, spot['id'])

    def test_fog_lies_over_every_map_layer(self):
        # The title frame paints the map's fog once, after every scene layer
        # (picture, objects, landmarks, glow, signs, decorations), so nothing
        # undiscovered shows through; only the guide and controls follow it.
        menu = (ROOT/'host/jungle_menu.zi').read_text()
        frame = menu[menu.index('JungleMenu :: ('):]
        self.assertEqual(frame.count('TitleMapFog(session, scene, picture)'), 1)
        fog = frame.index('TitleMapFog(session, scene, picture)')
        for layer in ('TitleObjects(session, scene', 'TitleAnimations(session, scene', 'TitleWindowFrame(session',
                      'TitlePicture(session, TitleHotspotRest(hotspot)', 'TitlePicture(session, TitleHotspotGlow(glowing)',
                      'TitlePathSign(session, hotspot', 'TITLE_DECORATION_PATH[index]', 'TitlePaperUnder(session'):
            self.assertLess(frame.rindex(layer, 0, frame.index('if guiding && !title_state.not_implemented')), fog, layer)
        self.assertGreater(frame.index('if guiding && !title_state.not_implemented'), fog)
        # One rule hides a fogged landmark from the pointer, hand, glow, taps and keys.
        title = (ROOT/'host/jungle_title.zi').read_text()
        self.assertIn('pointed := TitleSpotHit(title_state, ', frame)
        self.assertEqual(title.count('TitleFogAlpha(state.map_visits'), 1)


if __name__ == '__main__':
    unittest.main()

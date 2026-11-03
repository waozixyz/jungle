"""The Desert edge title scene: painted plates, guide and camel layers, the
Campus return sign and the guide's tap-through dialogue in every language."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('title_scenes', ROOT/'tools/title_scenes.py')
title = importlib.util.module_from_spec(spec)
spec.loader.exec_module(title)

LINES = [
    ('Hello! This is the big desert.', 'Hallo! Das ist die große Wüste.', '¡Hola! Este es el gran desierto.'),
    ('It is very hot, and the other side is far away.', 'Es ist sehr heiß, und die andere Seite ist weit weg.',
     'Hace mucho calor y el otro lado está muy lejos.'),
    ('First we need water, a sun hat and a little more learning.',
     'Zuerst brauchen wir Wasser, einen Sonnenhut und müssen noch ein bisschen lernen.',
     'Primero necesitamos agua, un sombrero para el sol y aprender un poco más.'),
    ('Come back when you are ready. My camel will wait for you!',
     'Komm wieder, wenn du bereit bist. Mein Kamel wartet auf dich!',
     'Vuelve cuando tengas todo listo. ¡Mi camello te esperará!'),
]


def inside(polygon, x, y):
    result = False
    for (xi, yi), (xj, yj) in zip(polygon, polygon[-1:] + polygon[:-1]):
        if (yi > y) != (yj > y) and x < xi + (y-yi)*(xj-xi)/(yj-yi):
            result = not result
    return result


def hit(view, x, y):
    found = [h for h in view['hotspots'] if inside(h['polygon'], x, y)]
    return min(found, key=lambda h: h['glow_rect'][2]*h['glow_rect'][3])['id'] if found else None


def digest(path):
    return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()


class DesertScene(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT/'tools/title_hotspots.json').read_text())
        self.desert = next(s for s in self.data['scenes'] if s['name'] == 'desert')
        self.views = (('landscape', self.desert, (1672, 941)),
                      ('portrait', self.desert['portrait'], (1024, 1536)))

    def test_campus_desert_sign_opens_the_scene(self):
        _, scenes, parents, hotspots = title.Load()
        names = [s['name'] for s in scenes]
        campus = next(s for s in self.data['scenes'] if s['name'] == 'campus')
        for view in (campus, campus['portrait']):
            sign = next(h for h in view['hotspots'] if h['id'] == 'desert-path')
            self.assertEqual(sign['target'], 'scene:desert')
            self.assertEqual((sign['sign']['label'], sign['sign']['direction']), ('Desert', 'right'))
        self.assertEqual(parents[names.index('desert')], names.index('campus'))
        self.assertEqual(parents[names.index('desert-portrait')], names.index('campus'))
        self.assertFalse(any(h['notice'] for h in hotspots), 'the old Desert availability notice is gone')

    def test_plates_are_opaque_webp_at_scene_size(self):
        for orientation, view, size in self.views:
            for key, expected in (('image', size), ('low', (240, round(size[1]*240/size[0])))):
                with self.subTest(orientation=orientation, key=key), Image.open(ROOT/view[key]) as im:
                    self.assertEqual(im.format, 'WEBP')
                    self.assertEqual(im.mode, 'RGB')
                    self.assertEqual(im.size, expected)
            self.assertNotIn('background', view)
            self.assertNotIn('foreground', view)

    def test_guide_camel_and_sign_layers(self):
        for orientation, view, size in self.views:
            ids = [h['id'] for h in view['hotspots']]
            self.assertEqual(ids, ['campus-path', 'camel', 'desert-guide'], 'camel paints behind its guide')
            sign, camel, guide = view['hotspots']
            self.assertEqual(sign['target'], 'scene:campus')
            self.assertEqual(sign['sign'], dict(sign['sign'], label='Campus', direction='left'))
            self.assertEqual(sign['rest'], 'assets/jungle/title/objects/wood-arrow-left.webp')
            for layer, name in ((camel, 'camel'), (guide, 'guide')):
                with self.subTest(orientation=orientation, layer=name):
                    self.assertEqual(layer['target'], 'dialogue:desert-guide')
                    self.assertEqual(layer['rest'], f'assets/jungle/title/objects/desert-{name}.webp')
                    self.assertEqual(layer['glow'], f'assets/jungle/title/objects/desert-{name}-glow.webp')
                    x, y, w, h = layer['glow_rect']
                    self.assertTrue(0 <= x and x + w <= size[0] and 0 <= y and y + h <= size[1])
                    with Image.open(ROOT/layer['rest']) as rest, Image.open(ROOT/layer['glow']) as glow:
                        self.assertEqual((rest.format, rest.mode), ('WEBP', 'RGBA'))
                        self.assertEqual(rest.getchannel('A').tobytes(), glow.getchannel('A').tobytes())
                        lo, hi = rest.getchannel('A').getextrema()
                        self.assertEqual((lo, hi), (0, 255), 'a clean transparent cut-out')
                        corners = [rest.getpixel(p)[3] for p in ((0, 0), (rest.width-1, 0), (0, rest.height-1))]
                        self.assertEqual(corners, [0, 0, 0], 'no paper or ground patch around the figure')
                        self.assertAlmostEqual(w / h, rest.width / rest.height, delta=0.01)
                        # Shown sharp: never stretched beyond the painted master.
                        self.assertGreaterEqual(rest.height, h * 1.4)
            gx, gy, gw, gh = guide['glow_rect']
            self.assertEqual(hit(view, gx + gw*0.5, gy + gh*0.3), 'desert-guide')
            cx, cy, cw, ch = camel['glow_rect']
            self.assertEqual(hit(view, cx + cw*0.7, cy + ch*0.35), 'camel')
            x, y, _, _ = sign['glow_rect']
            bx, by, bw, bh = sign['sign']['label_rect']
            self.assertEqual(hit(view, x + bx + bw/2, y + by + bh/2), 'campus-path')
            # Empty sky above the pair and the open dunes never open the bubble.
            self.assertIsNone(hit(view, size[0]*0.9, size[1]*0.12))
            # Both stand on the sand: their feet share a ground line near each other.
            self.assertLess(abs((gy + gh) - (cy + ch)), size[1]*0.04)

    def test_guide_camel_and_sign_stay_whole_on_tablets_and_phones(self):
        # The host cover-fits and centers the scene (TitleFit); nothing may be cut.
        for orientation, view, (width, height) in self.views:
            shapes = ((9, 20), (9, 16), (3, 4)) if orientation == 'portrait' else ((4, 3), (16, 9), (20, 9))
            for across, down in shapes:
                scale = max(across / width, down / height)
                left, top = (width - across / scale) / 2, (height - down / scale) / 2
                for hotspot in view['hotspots']:
                    with self.subTest(orientation=orientation, shape=(across, down), hotspot=hotspot['id']):
                        xs = [p[0] for p in hotspot['polygon']]
                        ys = [p[1] for p in hotspot['polygon']]
                        self.assertGreaterEqual(min(xs), left + 4)
                        self.assertLessEqual(max(xs), width - left - 4)
                        self.assertGreaterEqual(min(ys), top + 4)
                        self.assertLessEqual(max(ys), height - top - 4)

    def test_dialogue_lines_in_every_language(self):
        dialogues = title.Dialogues()
        self.assertEqual([d['id'] for d in dialogues], ['desert-guide'])
        lines = dialogues[0]['lines']
        self.assertEqual([(l['en'], l['de'], l['es']) for l in lines], LINES)
        generated = (ROOT/'host/jungle_title_data.zi').read_text()
        self.assertIn('TITLE_DIALOGUE_COUNT :: 1', generated)
        self.assertIn(f'TITLE_DIALOGUE_LINES: [1]s32 = .[{len(LINES)}];', generated)
        for entry in (text for line in LINES for text in line):
            self.assertIn(json.dumps(entry, ensure_ascii=False), generated)
        self.assertIn('TITLE_HOTSPOT_DIALOGUE', generated)
        # Tapping the camel still lets the guide speak: his figure anchors the bubble.
        _, scenes, _, hotspots = title.Load()
        for name in ('desert', 'desert-portrait'):
            scene = [s['name'] for s in scenes].index(name)
            by_id = {h['id']: i for i, h in enumerate(hotspots) if h['scene'] == scene}
            self.assertEqual(hotspots[by_id['camel']]['speaker'], by_id['desert-guide'])
            self.assertEqual(hotspots[by_id['desert-guide']]['speaker'], by_id['desert-guide'])
            self.assertEqual(hotspots[by_id['campus-path']]['speaker'], -1)
        # A voice clip is referenced only when it exists, with its own text.
        for number, line in enumerate(LINES):
            for language, text in zip(('en', 'de', 'es'), line):
                path = f'assets/jungle/title/desert/{language}/line{number}.wav'
                receipt = ROOT/path.replace('.wav', '.speech.json')
                if (ROOT/path).exists():
                    self.assertIn(json.dumps(path), generated)
                    self.assertEqual(json.loads(receipt.read_text())['text'], text)
                    self.assertEqual(json.loads(receipt.read_text())['sha256'], digest(path))

    def test_bubble_is_beside_the_speaker_not_a_bottom_caption(self):
        source = (ROOT/'host/jungle_title_dialogue.zi').read_text()
        self.assertIn('TitleDialogueLayout(width, height, TitleDialogueAnchor(', source)
        self.assertIn('RetroTap(7600', source)
        self.assertNotIn('height - 30', source)
        menu = (ROOT/'host/jungle_menu.zi').read_text()
        self.assertIn('#import, file "jungle_title_dialogue.zi";', menu)
        self.assertIn('TitleDialogueFrame(session, *title_state', menu)

    def test_provenance_matches_runtime(self):
        receipt = json.loads((ROOT/'tools/art_provenance/desert-edge.json').read_text())
        rows = receipt['assets']
        runtime = {row['runtime']: row['sha256'] for row in rows}
        for orientation, view, _ in self.views:
            self.assertEqual(runtime[view['image']], digest(view['image']))
            low = next(row for row in rows if row.get('low') == view['low'])
            self.assertEqual(low['low_sha256'], digest(view['low']))
        for row in rows:
            if 'layer' in row:
                self.assertEqual(row['sha256'], digest(row['runtime']))
                self.assertEqual(row['glow_sha256'], digest(row['glow']))
            for key in ('master', 'generated'):
                if key in row:
                    self.assertTrue(row[key].startswith('local/art-development/desert-edge/'))
                    self.assertTrue(row[key].endswith('.png'))


if __name__ == '__main__':
    unittest.main()

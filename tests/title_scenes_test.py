"""Validate title variants without selecting unapproved portrait artwork."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
APPROVED_TITLE_WEBP = ROOT/'tests/approved_title_webp.json'
spec = importlib.util.spec_from_file_location('title_scenes', ROOT/'tools/title_scenes.py')
title = importlib.util.module_from_spec(spec)
spec.loader.exec_module(title)
sys.path.insert(0, str(ROOT/'tools'))


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
    def test_generated_data_and_routes(self):
        data, scenes, parents, hotspots = title.Load()
        self.assertEqual(title.OUTPUT.read_text(), title.Render(data,scenes,parents,hotspots))
        for scene in scenes:
            if scene['name'].startswith('campus'):
                routes={h['id']:h['target'] for h in scene['hotspots']}
                self.assertEqual(routes['farm-path'],'scene:farm')
                self.assertEqual(routes['beach-path'],'scene:beach')
                self.assertEqual(routes['desert-path'],'notice:Desert')
                self.assertNotIn('garden',routes)
                farm=next(h for h in scene['hotspots'] if h['id']=='farm-path')
                music=next(h for h in scene['hotspots'] if h['id']=='music-hut')
                self.assertLess(farm['glow_rect'][0], music['glow_rect'][0]+music['glow_rect'][2])
                self.assertGreater(farm['glow_rect'][1],music['glow_rect'][1]+music['glow_rect'][3])
            if scene['name'].startswith('beach'):
                self.assertEqual(next(h for h in scene['hotspots'] if h['id']=='campus-path')['target'],'scene:campus')
                self.assertEqual({h['id'] for h in scene['hotspots']}, {'campus-path','bunker-door','fishing-boat','crab-family'})

    def test_portrait_campus_uses_approved_mapping_and_full_background(self):
        _, scenes, _, _ = title.Load()
        scene = next(s for s in scenes if s['name'] == 'campus-portrait')
        plan = json.loads((ROOT/'tools/art_provenance/campus-portrait-v3.json').read_text())
        canonical = ROOT/plan['source']
        if canonical.exists():
            self.assertEqual(json.loads(canonical.read_text())['orientations']['portrait'],
                             {k:v for k,v in plan.items() if k not in ('source','directions')})
        self.assertEqual([scene['width'], scene['height']], plan['canvas'])
        names = {'portrait-music-original.png':'music-hut', 'portrait-piano.png':'piano',
                 'portrait-picnic.png':'picnic', 'frogs.png':'frogs', 'hiding-tail.png':'hiding-bush'}
        for obj in plan['objects']:
            if obj['file'] in names:
                h = next(h for h in scene['hotspots'] if h['id'] == names[obj['file']])
                self.assertEqual(h['glow_rect'], obj['scene_rect'])
                self.assertIn('portrait-', h['rest'])
                x,y,w,ht = obj['scene_rect']
                self.assertEqual(hit(scene,x+w/2,y+ht/2),h['id'])
            else:
                self.assertEqual(scene['decorations'][0]['rect'],obj['scene_rect'])
        for label,rect in plan['signs'].items():
            h = next(h for h in scene['hotspots'] if h.get('sign',{}).get('label') == label)
            self.assertEqual(h['glow_rect'],rect)
            self.assertEqual(h['sign']['direction'],plan['directions'][label])
        for h in scene['hotspots']:
            x,y,w,ht = h['glow_rect']
            self.assertTrue(0 <= x < x+w <= scene['width'])
            self.assertTrue(0 <= y < y+ht <= scene['height'])
            for px,py in h['polygon']:
                self.assertTrue(0 <= px <= scene['width'] and 0 <= py <= scene['height'])
        row = next(r for r in json.loads(APPROVED_TITLE_WEBP.read_text())['images']
                   if r['path'] == scene['image'])
        self.assertTrue(row['canonical_source'].endswith('/'+plan['plate']))
        self.assertEqual((row['width'],row['height']),(1024,1536))
        # Check the image actually drawn after layers load, not just the fallback.
        for path in (scene['image'],scene['background']):
            with Image.open(ROOT/path) as im:
                self.assertEqual(im.size,(1024,1536))
                self.assertEqual(hashlib.sha256(im.convert('RGBA').tobytes()).hexdigest(),
                                 'b92fb237cefd67de931e318d483c7883ad76147da5a69996677f937742bd0d81')

    def test_landscape_campus_is_unchanged(self):
        data = json.loads((ROOT/'tools/title_hotspots.json').read_text())
        scene = next(s for s in data['scenes'] if s['name'] == 'campus')
        scene.pop('portrait')
        self.assertEqual(hashlib.sha256(json.dumps(scene,sort_keys=True).encode()).hexdigest(),
                         'a2a369060578673739e50422bebf76b2093a00531b1f475e17269ea99ef034b4')

    def test_signs_are_localized_boards_with_travel_arrows(self):
        data,scenes,_,hotspots=title.Load()
        translations=json.loads((ROOT/'locales/ui.json').read_text())
        for label,expected in {'Beach':['Strand','Playa'],'Farm':['Bauernhof','Granja'],'Desert':['Wüste','Desierto']}.items():
            self.assertEqual(translations[label],expected)
        for scene in scenes:
            for h in scene['hotspots']:
                if not h.get('sign'):continue
                self.assertIn(h['sign']['direction'], ('left','right','up','down'))
                if h['id']=='farm-path':self.assertEqual(h['sign']['direction'],'left')
                x,y,w,ht=h['glow_rect'];bx,by,bw,bh=h['sign']['label_rect']
                self.assertEqual(hit(scene,x+bx+bw/2,y+by+bh/2),h['id'])
                with Image.open(ROOT/h['rest']) as im:
                    self.assertEqual(im.format,'WEBP')
                    self.assertGreater(im.convert('RGBA').getpixel((round((bx+bw/2)*im.width/w),round((by+bh/2)*im.height/ht)))[3],200)
        self.assertIn('TITLE_SIGN_DIRECTION',(ROOT/'host/jungle_title_data.zi').read_text())

    def test_approved_webp_fingerprints(self):
        approved=json.loads(APPROVED_TITLE_WEBP.read_text())
        self.assertEqual((approved['quality'],approved['method']),(50,6))
        self.assertEqual(sum(r['bytes'] for r in approved['images']),approved['total_bytes'])
        self.assertEqual(len({r['path'] for r in approved['images']}),len(approved['images']))
        for row in approved['images']:
            path=ROOT/row['path']
            with self.subTest(path=row['path']),Image.open(path) as im:
                self.assertEqual(im.format,'WEBP')
                self.assertEqual(im.size,(row['width'],row['height']))
                self.assertEqual(path.stat().st_size,row['bytes'])
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),row['sha256'])
                self.assertEqual(hashlib.sha256(im.convert('RGBA').tobytes()).hexdigest(),row['decoded_rgba_sha256'])
                canonical=ROOT/row['canonical_source']
                if canonical.exists():
                    self.assertEqual(hashlib.sha256(canonical.read_bytes()).hexdigest(),row['canonical_sha256'])

    def test_new_runtime_title_layers_are_webp(self):
        _,scenes,_,_=title.Load()
        for scene in scenes:
            if not scene['name'].startswith(('campus','beach')):continue
            for h in scene['hotspots']:
                if h.get('sign') or scene['name'].startswith('campus') and h.get('rest'):
                    self.assertTrue(h['rest'].endswith('.webp'))
                    with Image.open(ROOT/h['rest']) as rest,Image.open(ROOT/h['glow']) as glow:
                        self.assertEqual(rest.getchannel('A').tobytes(),glow.getchannel('A').tobytes())

    def test_shelf_cover_priority_and_stories_row(self):
        _,scenes,_,_=title.Load()
        for scene in scenes:
            if not scene['name'].startswith('bookshelf'):continue
            for name in ('tiger','frogs','rabbit'):
                h=next(h for h in scene['hotspots'] if h['id']=='book-cover-'+name)
                x,y,w,ht=h['glow_rect']
                self.assertEqual(hit(scene,x+w/2,y+ht/2),h['id'])
            row=next(h for h in scene['hotspots'] if h['id']=='picture-books')
            x,y,w,ht=row['glow_rect']
            self.assertEqual(hit(scene,x+3,y+3),'picture-books')
            story=next(h for h in scene['hotspots'] if h['id']=='fairy-tale')
            x,y,w,ht=story['glow_rect']
            for u in (.1,.5,.9):self.assertEqual(hit(scene,x+w*u,y+ht*.5),'fairy-tale')

    def test_no_testing_room_surface(self):
        for name in ('host/jungle_title.zi','host/jungle_menu.zi','tools/build_web.py','Makefile'):
            body=(ROOT/name).read_text()
            for obsolete in ('JUNGLE_TEST_ROOMS','TEST_ROOMS','preview_room','TitleDevelopmentControls','--test-rooms'):
                self.assertNotIn(obsolete,body)

if __name__=='__main__':unittest.main()

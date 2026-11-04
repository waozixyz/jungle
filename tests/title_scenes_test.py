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
                self.assertEqual(routes['farm-path'],'game:Farm')
                self.assertEqual(routes['jungle-path'],'scene:jungle-path')
                self.assertNotIn('beach-path',routes)
                self.assertEqual(routes['desert-path'],'scene:desert')
                self.assertNotIn('garden',routes)
                farm=next(h for h in scene['hotspots'] if h['id']=='farm-path')
                music=next(h for h in scene['hotspots'] if h['id']=='music-hut')
                self.assertLess(farm['glow_rect'][0], music['glow_rect'][0]+music['glow_rect'][2])
                self.assertGreater(farm['glow_rect'][1],music['glow_rect'][1]+music['glow_rect'][3])
            # Owner: the Beach is the Port; its way home is the Jungle Path,
            # which leads on to Campus, and a shopping street joins it to the Farm.
            routes={h['id']:(h['target'],h.get('sign',{}).get('direction')) for h in scene['hotspots']}
            if scene['name'].startswith('port'):
                self.assertEqual(set(routes), {'jungle-path','bunker-door','fishing-boat','crab-family','market-path'})
                self.assertEqual(routes['jungle-path'],('scene:jungle-path','left'))
                self.assertEqual(routes['market-path'],('scene:market','right'))
            if scene['name'].startswith('jungle-path'):
                self.assertEqual(routes['port-path'],('scene:port','left'))
                self.assertEqual(routes['campus-path'],('scene:campus','right'))
            if scene['name'].startswith('market'):
                self.assertEqual(routes['port-path'],('scene:port','left'))
                self.assertEqual(routes['farm-path'],('game:Farm','right'))
                shops={h['id'] for h in scene['hotspots'] if h['target'].startswith('look:')}
                self.assertEqual(shops,{'toy-shop','fish-stall','bakery','fruit-stall'})
        self.assertNotIn('beach',{scene['name'] for scene in scenes})
        self.assertEqual(title.SCENE_ALIASES,{'beach':'port'})

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
                                 '63761f1dd59db99a88a3ec5dd3465a2ea42c72ed9eba071b24998b8fb8343bf6')

    def test_landscape_campus_art_and_placements_are_unchanged(self):
        # Painted art and every placement; routes, sign faces and directions
        # are checked by their own tests so destinations can evolve freely.
        data = json.loads((ROOT/'tools/title_hotspots.json').read_text())
        scene = next(s for s in data['scenes'] if s['name'] == 'campus')
        scene.pop('portrait')
        for h in scene['hotspots']:
            h.pop('target',None)
            if h.pop('sign',None):
                for key in ('rest','glow','polygon'): h.pop(key,None)
        self.assertEqual(hashlib.sha256(json.dumps(scene,sort_keys=True).encode()).hexdigest(),
                         'f7db4f42a9575424033c3074a0936c53207b4fb31a9afb35e5c1b3ceac5e64e2')

    def test_signs_are_localized_boards_with_travel_arrows(self):
        data,scenes,_,hotspots=title.Load()
        translations=json.loads((ROOT/'locales/ui.json').read_text())
        for label,expected in {'Port':['Hafen','Puerto'],'Market':['Markt','Mercado'],'Jungle Path':['Dschungelpfad','Sendero de la selva'],
                               'Farm':['Bauernhof','Granja'],'Desert':['Wüste','Desierto']}.items():
            self.assertEqual(translations[label],expected)
        for scene in scenes:
            for h in scene['hotspots']:
                if not h.get('sign'):continue
                # Only Campus's sign up into the Jungle Path stands upright.
                upright = scene['name'].startswith('campus') and h['target'] == 'scene:jungle-path'
                self.assertEqual(h['sign']['direction'].startswith('diagonal-'), upright, (scene['name'], h['id']))
                self.assertIn(h['sign']['direction'], ('left','right','diagonal-left','diagonal-right'))
                self.assertEqual(h['rest'], 'assets/jungle/title/objects/wood-arrow-'+h['sign']['direction']+'.webp')
                if h['id']=='farm-path':self.assertEqual(h['sign']['direction'],'right' if scene['name'].startswith('market') else 'left')
                x,y,w,ht=h['glow_rect'];bx,by,bw,bh=h['sign']['label_rect']
                self.assertEqual(hit(scene,x+bx+bw/2,y+by+bh/2),h['id'])
                with Image.open(ROOT/h['rest']) as im:
                    self.assertEqual(im.format,'WEBP')
                    self.assertGreater(im.convert('RGBA').getpixel((round((bx+bw/2)*im.width/w),round((by+bh/2)*im.height/ht)))[3],200)
                # The post is scenery; the arrowhead itself is a real target.
                self.assertNotEqual(hit(scene,x+w*.5,y+ht*.9),h['id'])
                tip = (min(h['polygon'],key=lambda p:p[0]) if h['sign']['direction'] in ('left','diagonal-left') else
                       min(h['polygon'],key=lambda p:p[1]) if h['sign']['direction']=='up' else
                       max(h['polygon'],key=lambda p:p[0]))
                cx,cy=x+bx+bw/2,y+by+bh/2
                tx,ty=cx+(tip[0]-cx)*.88,cy+(tip[1]-cy)*.88
                self.assertEqual(hit(scene,tx,ty),h['id'])
                with Image.open(ROOT/h['rest']) as im:
                    self.assertGreater(im.getchannel('A').getpixel((round((tx-x)*im.width/w),round((ty-y)*im.height/ht))),100)
        self.assertIn('TITLE_SIGN_DIRECTION' ,(ROOT/'host/jungle_title_data.zi').read_text())
        renderer=(ROOT/'host/jungle_menu.zi').read_text().split('TitlePathSign ::')[1].split('TitleLanguageFlags ::')[0]
        self.assertNotIn('Line(session',renderer)
        self.assertNotIn('text_board.x +=',renderer)

    def test_peekaboo_trail_opens_hide_seek_in_both_views(self):
        _, scenes, _, _ = title.Load()
        for name in ('jungle-path', 'jungle-path-portrait'):
            scene = next(s for s in scenes if s['name'] == name)
            spot = next(h for h in scene['hotspots'] if h['id'] == 'peekaboo-trail')
            self.assertEqual(spot['target'], 'game:Hide & Seek')
            x,y,w,h = spot['glow_rect']
            self.assertEqual(hit(scene,x+w/2,y+h/2), 'peekaboo-trail')
            for path in (spot['rest'], spot['glow']):
                self.assertTrue((ROOT/path).is_file())

    def test_signs_are_sideways_intact_planks(self):
        # Owner (2026-11-03): Campus's sign to the Port's side stands upright,
        # one plank pointing up its path into the Jungle Path; every other
        # sign, the Port's own included, is a sideways plank. A snapped,
        # splintered plank end read as a broken sign.
        data = json.loads((ROOT/'tools/title_hotspots.json').read_text())
        campus = next(s for s in data['scenes'] if s['name'] == 'campus')
        for view, direction in ((campus, 'diagonal-right'), (campus['portrait'], 'diagonal-left')):
            path = [h for h in view['hotspots'] if h.get('target') == 'scene:jungle-path']
            self.assertEqual(len(path), 1)
            self.assertEqual(path[0]['sign']['direction'], direction)
            self.assertEqual(path[0]['rest'], 'assets/jungle/title/objects/wood-arrow-'+direction+'.webp')
        upright = [h['id'] for s in data['scenes'] for view in (s, s.get('portrait') or {})
                   for h in view.get('hotspots', []) if h.get('sign', {}).get('direction') == 'diagonal-left']
        self.assertEqual(upright, ['jungle-path'])
        with Image.open(ROOT/'assets/jungle/title/objects/wood-arrow-right.webp') as right, \
             Image.open(ROOT/'assets/jungle/title/objects/wood-arrow-left.webp') as left:
            self.assertEqual(right.convert('RGBA').transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes(),
                             left.convert('RGBA').tobytes())
            alpha = right.convert('RGBA').getchannel('A').load()
        tail = [next(x for x in range(1254) if alpha[x, y] > 128) for y in range(330, 620, 2)]
        shaft = [x for x in range(120, 780, 4) if not 480 <= x <= 670]
        top = [next(y for y in range(1254) if alpha[x, y] > 128) for x in shaft]
        bottom = [next(y for y in range(760, 0, -1) if alpha[x, y] > 128) for x in shaft]
        for edge in (tail, top, bottom):
            self.assertLessEqual(max(edge) - min(edge), 4, 'chipped or splintered plank edge')

    def test_signs_stay_onscreen_when_cover_fit(self):
        # A portrait scene fills a phone's height and crops its sides; a
        # landscape scene crops a 16:10 window's. Every sign stays whole on
        # screen there. Campus portrait and the world map fit inside instead.
        data = json.loads((ROOT/'tools/title_hotspots.json').read_text())
        for scene in data['scenes']:
            for view, low, high in ((scene, 100, 1572), (scene.get('portrait'), 175, 850)):
                if not view or scene['name'] == 'map' or (scene['name'] == 'campus' and high == 850):
                    continue
                for hotspot in view['hotspots']:
                    if 'sign' in hotspot:
                        xs = [x for x, _ in hotspot['polygon']]
                        self.assertGreaterEqual(min(xs), low, (scene['name'], hotspot['id']))
                        self.assertLessEqual(max(xs), high, (scene['name'], hotspot['id']))

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
            if not scene['name'].startswith(('campus','port','market','jungle-path')):continue
            for h in scene['hotspots']:
                if h.get('sign') or scene['name'].startswith('campus') and h.get('rest'):
                    self.assertTrue(h['rest'].endswith('.webp'))
                    with Image.open(ROOT/h['rest']) as rest,Image.open(ROOT/h['glow']) as glow:
                        self.assertEqual(rest.getchannel('A').tobytes(),glow.getchannel('A').tobytes())

    def test_shelf_first_row_is_one_row_and_inventory_is_complete(self):
        _,scenes,_,_=title.Load()
        # Painted first-row covers (tiger, frogs, rabbit), stencil spot and inventory.
        shelf={'bookshelf':([[330,88],[609,102],[610,344],[330,334]],[[630,110],[864,122],[865,358],[630,350]],[[888,127],[1124,143],[1128,372],[888,360]]),
               'bookshelf-portrait':([[133,248],[347,256],[348,515],[133,504]],[[411,264],[604,272],[605,529],[411,521]],[[656,279],[848,288],[854,540],[656,531]])}
        for scene in scenes:
            if scene['name'] not in shelf:continue
            stem='assets/jungle/title/'+scene['name']
            glow='assets/jungle/title/glow/'+scene['name']
            # Before 4d2340cf, plus the approved whole Stories-row glow.
            self.assertEqual([(h['id'],h['target'],h['glow']) for h in scene['hotspots']],[
                ('picture-books','game:Picture Book',glow+'-picture-books.webp'),
                ('book-abc','game:ABC Book',glow+'-book-abc.webp'),
                ('book-123','game:123 Book',glow+'-book-123.webp'),
                ('ladder','scene:treehouse',glow+'-ladder.webp'),
                ('fairy-tale','book:sweet-porridge',glow+'-fairy-tale-hover.webp')])
            self.assertEqual((scene['image'],scene['low'],scene['background'],scene['foreground']),
                (stem+'.webp',stem+'-low.webp',stem.replace('title/','title/layers/')+'-background.webp',stem.replace('title/','title/layers/')+'-foreground.webp'))
            for path in [scene['image'],scene['low'],scene['background'],scene['foreground']]+[h['glow'] for h in scene['hotspots']]:
                with Image.open(ROOT/path) as im:self.assertEqual(im.format,'WEBP')
            # One whole-row hotspot owns every first-row book, the tiger included.
            for cover in shelf[scene['name']]:
                cx=sum(p[0] for p in cover)/4;cy=sum(p[1] for p in cover)/4
                for u,v in ((.5,.5),(.12,.15),(.88,.85)):
                    self.assertEqual(hit(scene,cover[0][0]+(cover[1][0]-cover[0][0])*u,cy+(v-.5)*(cover[2][1]-cover[1][1])),'picture-books')
            # The stencil's visible edge, right of the tiger, belongs to no book.
            sx,sy,edge,_=scene['paper']
            self.assertIsNone(hit(scene,shelf[scene['name']][0][1][0]+edge*.1,sy))
            self.assertEqual(hit(scene,sx-edge*.3,sy),'picture-books')
            story=next(h for h in scene['hotspots'] if h['id']=='fairy-tale')
            x,y,w,ht=story['glow_rect']
            for u in (.1,.5,.9):self.assertEqual(hit(scene,x+w*u,y+ht*.5),'fairy-tale')
        paper=next(c for c in json.loads((ROOT/'tools/collectibles.json').read_text())['collectibles'] if c['slug']=='bookshelf-scene')
        self.assertEqual((paper['source'],paper['how']['kind']),({'kind':'title','scene':'bookshelf'},'paper'))
        menu=(ROOT/'host/jungle_menu.zi').read_text()
        self.assertNotIn('book-cover-',menu)
        self.assertNotIn('!paper_available || shelf,',menu)

    def test_no_testing_room_surface(self):
        for name in ('host/jungle_title.zi','host/jungle_menu.zi','tools/build_web.py','Makefile'):
            body=(ROOT/name).read_text()
            for obsolete in ('JUNGLE_TEST_ROOMS','TEST_ROOMS','preview_room','TitleDevelopmentControls','--test-rooms'):
                self.assertNotIn(obsolete,body)

if __name__=='__main__':unittest.main()

"""Integrate the Market, the Jungle Path and the routes that join them.

The owner asked (2026-11-03) for a path at the left of the Farm to a Market
shopping street that also connects back to the Port (the Beach, renamed), and
for a tropical Jungle Path between Campus and the Port to click through: its
right leads to Campus, its left to the Port. Campus's sign to it stands
upright, pointing up the path, which in portrait now starts between the
treehouse and the drums; the portrait frogs sit on their rocks.

Masters stay in ignored local/art-development/{market,jungle-path,farm-fields,
campus-object-layers}/; this explicit authoring command exports the runtime
WebPs, glows and hotspots. Normal builds never run it.

    python3 tools/title_places.py
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image
from image_exports import export_image
from title_signs import BOARDS
from title_desert import outline
from title_glow import glow

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT/'local/art-development'
GARDEN_PROVENANCE = ROOT/'assets/garden/scene-provenance.json'
MANIFEST = ROOT/'tools/title_hotspots.json'
PROVENANCE = ROOT/'tools/art_provenance/title-places.json'
APPROVED = ROOT/'tests/approved_title_webp.json'
TITLE = 'assets/jungle/title/'
OBJECTS = TITLE+'objects/'
CANVAS = {'landscape': (1672, 941), 'portrait': (1024, 1536)}

# The Market's four shops, traced around each stall's roof, awning, posts and
# counter in scene pixels. The landscape flower cart stays scenery: the
# portrait street has no room for it, and both orientations share hotspots.
SHOPS = {
    'landscape': {
        'toy-shop': [(465,222),(612,318),(612,350),(592,358),(592,618),(322,618),(322,360),(302,352),(302,318)],
        'fish-stall': [(616,212),(644,212),(644,290),(898,290),(906,368),(886,372),(886,620),(652,620),(652,600),(616,600)],
        'bakery': [(1085,188),(1180,232),(1272,318),(1272,345),(1252,350),(1252,620),(925,620),(925,350),(905,345),(905,318),(990,232)],
        'fruit-stall': [(1282,236),(1302,236),(1302,282),(1600,268),(1612,212),(1636,212),(1640,365),(1630,372),(1630,625),(1288,625),(1288,372),(1278,365)],
    },
    'portrait': {
        'toy-shop': [(402,58),(422,58),(424,108),(570,82),(700,118),(800,192),(760,204),(760,400),(424,400),(424,205),(366,196)],
        'fish-stall': [(66,386),(332,386),(442,418),(442,502),(408,506),(434,690),(420,748),(275,778),(118,762),(80,745),(66,600)],
        'bakery': [(776,312),(900,330),(1022,372),(1022,430),(990,430),(990,740),(720,740),(605,720),(600,450),(548,458),(560,410),(700,330)],
        'fruit-stall': [(262,838),(300,778),(560,742),(808,728),(842,728),(900,770),(1010,888),(990,905),(842,862),(842,1232),(760,1232),(760,1170),(320,1170),(300,1150),(296,884),(240,882)],
    },
}
# The Jungle Path's animals, outlined from offline background removal of
# these crops (cutouts/<orientation>-<name>.png beside the masters).
ANIMALS = {
    'landscape': {'parrot': (160,240,360,530), 'sloth': (1190,50,1370,220), 'butterfly': (1370,600,1550,780)},
    'portrait': {'parrot': (130,460,440,910), 'sloth': (580,120,890,400), 'butterfly': (660,660,920,900)},
}
# (hotspot id, target, label, direction, rect) beside each path's exit. Portrait
# scenes fill a phone's height and crop its sides, so every sign stays within
# x 175..850 (9:20 phones); landscape within x 100..1572 (16:10 windows).
SIGNS = {
    'market': {
        'landscape': [('port-path','scene:port','Port','left',[100,610,220,220]),
                      ('farm-path','game:Farm','Farm','right',[1350,610,220,220])],
        'portrait': [('port-path','scene:port','Port','left',[176,175,185,185]),
                     ('farm-path','game:Farm','Farm','right',[640,1250,200,200])],
    },
    'jungle-path': {
        'landscape': [('port-path','scene:port','Port','left',[100,500,190,190]),
                      ('campus-path','scene:campus','Campus','right',[1360,330,210,210])],
        'portrait': [('port-path','scene:port','Port','left',[178,300,190,190]),
                     ('campus-path','scene:campus','Campus','right',[640,1100,200,200])],
    },
}
# The Port's way to the Market leaves along its new sandy path at the right.
PORT_MARKET = {'landscape': [1360,740,190,190], 'portrait': [660,860,185,185]}
# Campus: the upright Jungle Path sign. Landscape keeps its place beside the
# path up into the jungle; portrait stands where the new path starts between
# the treehouse and the drums.
CAMPUS_SIGN = {'landscape': [240,300,180,180], 'portrait': [305,478,160,160]}
FROGS_PORTRAIT = [45,1032,250,172]
PLATES = {
    'market': 'market/market-{o}.png',
    'jungle-path': 'jungle-path/jungle-path-{o}.png',
    'port': 'market/port-{o}-market-path.png',
    'farm': 'farm-fields/farm-landscape-left-path.png',
    'campus-portrait': 'campus-object-layers/portrait-jungle-path-between.png',
}


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def sign(ident, target, label, direction, rect):
    board, polygon = BOARDS[direction]
    x, y, w, h = rect
    return dict(id=ident, target=target, glow_rect=list(rect),
                rest=OBJECTS+f'wood-arrow-{direction}.webp', glow=OBJECTS+f'wood-arrow-{direction}-glow.webp',
                polygon=[[x+round(px*w/1254), y+round(py*h/1254)] for px, py in polygon],
                sign=dict(label=label, direction=direction,
                          label_rect=[round(board[0]*w/1254), round(board[1]*h/1254),
                                      round(board[2]*w/1254), round(board[3]*h/1254)]))


def resign(hotspot, ident, target, label, direction, rect=None):
    """Point an existing sign elsewhere, keeping its place unless RECT moves it."""
    fresh = sign(ident, target, label, direction, rect or hotspot['glow_rect'])
    hotspot.clear()
    hotspot.update(fresh)


def bounds(polygon, size):
    xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
    left, top = max(0, min(xs)-14), max(0, min(ys)-14)
    right, bottom = min(size[0], max(xs)+15), min(size[1], max(ys)+15)
    return [left, top, right-left, bottom-top]


def animal(folder, orientation, name):
    """The animal's outline from its cutout, largest silhouette only."""
    from scipy import ndimage
    x0, y0, x1, y1 = ANIMALS[orientation][name]
    with Image.open(LOCAL/folder/'cutouts'/f'{orientation}-{name}.png') as cut:
        alpha = np.asarray(cut.convert('RGBA').getchannel('A'))
    if alpha.shape != (y1-y0, x1-x0):
        raise SystemExit(f'{folder} {orientation}-{name} cutout must match its crop')
    labels, count = ndimage.label(alpha >= 96)
    sizes = ndimage.sum(np.ones_like(alpha), labels, range(1, count+1))
    keep = labels == int(np.argmax(sizes))+1
    mask = Image.fromarray(np.where(keep, 255, 0).astype('uint8'))
    left, top, right, bottom = mask.getbbox()
    points = outline(mask.crop((left, top, right, bottom)), x0+left, y0+top, 1.0)
    return [[min(max(0, px), CANVAS[orientation][0]-1), min(max(0, py), CANVAS[orientation][1]-1)] for px, py in points]


def look(scene_name, ident, polygon, size):
    hotspot = dict(id=ident, target='look:'+ident, polygon=[list(p) for p in polygon],
                   glow_rect=bounds(polygon, size), glow=TITLE+f'glow/{scene_name}-{ident}.webp')
    path = ROOT/hotspot['glow']
    path.parent.mkdir(parents=True, exist_ok=True)
    glow(hotspot).save(path, 'WEBP', lossless=True, exact=True, method=6)
    return hotspot


class Ledger:
    def __init__(self):
        self.approved = json.loads(APPROVED.read_text())
        self.receipts = []

    def background(self, source, destination, size=None):
        destination = ROOT/destination
        export_image(source, destination, 'title-background', size=size)
        with Image.open(destination) as im:
            row = dict(name=destination.stem, path=str(destination.relative_to(ROOT)),
                       bytes=destination.stat().st_size, sha256=digest(destination),
                       width=im.width, height=im.height,
                       decoded_rgba_sha256=hashlib.sha256(im.convert('RGBA').tobytes()).hexdigest(),
                       canonical_source=str(Path(source).relative_to(ROOT)),
                       canonical_bytes=Path(source).stat().st_size, canonical_sha256=digest(source))
        images = self.approved['images']
        at = next((i for i, r in enumerate(images) if r['path'] == row['path']), None)
        if at is None: images.append(row)
        else: images[at] = row
        return row['path']

    def plate(self, source, image, low):
        with Image.open(source) as im:
            width, height = im.size
        self.background(source, image)
        self.background(source, low, size=(240, round(height*240/width)))
        self.receipts.append(dict(master=str(Path(source).relative_to(ROOT)), master_sha256=digest(source),
                                  runtime=image, sha256=digest(ROOT/image), low=low, low_sha256=digest(ROOT/low)))

    def save(self):
        self.approved['total_bytes'] = sum(r['bytes'] for r in self.approved['images'])
        APPROVED.write_text(json.dumps(self.approved, indent=2)+'\n')


def place(ledger, name, folder):
    scene = dict(name=name, image=TITLE+f'{name}.webp', low=TITLE+f'{name}-low.webp')
    portrait = dict(width=1024, height=1536, image=TITLE+f'{name}-portrait.webp',
                    low=TITLE+f'{name}-portrait-low.webp')
    for orientation, view in (('landscape', scene), ('portrait', portrait)):
        source = LOCAL/PLATES[name].format(o=orientation)
        with Image.open(source) as im:
            if im.size != CANVAS[orientation] or im.mode != 'RGB':
                raise SystemExit(f'{source.name} must be an opaque {CANVAS[orientation]} plate')
        ledger.plate(source, view['image'], view['low'])
        scene_name = name if orientation == 'landscape' else name+'-portrait'
        if name == 'market':
            items = [(ident, polygon) for ident, polygon in SHOPS[orientation].items()]
        else:
            items = [(ident, animal(folder, orientation, ident)) for ident in ANIMALS[orientation]]
        view['hotspots'] = ([look(scene_name, ident, polygon, CANVAS[orientation]) for ident, polygon in items] +
                            [sign(*row) for row in SIGNS[name][orientation]])
    scene['portrait'] = portrait
    return scene


def campus_portrait(ledger, campus):
    """New route between treehouse and drums, frogs on their rocks."""
    view = campus['portrait']
    source = LOCAL/PLATES['campus-portrait']
    if source.is_file():
        ledger.background(source, view['image'])
        ledger.background(source, view['background'])
        ledger.background(source, view['low'], size=(240, 360))
    frogs = next(h for h in view['hotspots'] if h['id'] == 'frogs')
    x, y, w, h = FROGS_PORTRAIT
    frogs.update(glow_rect=list(FROGS_PORTRAIT), polygon=[[x,y],[x+w-1,y],[x+w-1,y+h-1],[x,y+h-1]])
    # The approved portrait mapping records every placement.
    plan_path = ROOT/'tools/art_provenance/campus-portrait-v3.json'
    plan = json.loads(plan_path.read_text())
    if source.is_file(): plan['plate'] = source.name
    next(o for o in plan['objects'] if o['file'] == 'frogs.png')['scene_rect'] = list(FROGS_PORTRAIT)
    signs, directions = plan['signs'], plan['directions']
    plan['signs'] = {('Jungle Path' if k in ('Beach', 'Port') else k): v for k, v in signs.items()}
    plan['directions'] = {('Jungle Path' if k in ('Beach', 'Port') else k): v for k, v in directions.items()}
    plan['signs']['Jungle Path'] = list(CAMPUS_SIGN['portrait'])
    plan['directions']['Jungle Path'] = 'up'
    plan_path.write_text(json.dumps(plan, indent=1)+'\n')
    canonical = ROOT/plan['source']
    if canonical.exists():
        mapping = json.loads(canonical.read_text())
        mapping['orientations']['portrait'] = {k: v for k, v in plan.items() if k not in ('source', 'directions')}
        canonical.write_text(json.dumps(mapping, indent=1)+'\n')


def main():
    ledger = Ledger()
    data = json.loads(MANIFEST.read_text())
    scenes = {s['name']: s for s in data['scenes']}
    for name, folder in (('jungle-path', 'jungle-path'), ('market', 'market')):
        scene = place(ledger, name, folder)
        if name in scenes:
            data['scenes'][data['scenes'].index(scenes[name])] = scene
        else:
            data['scenes'].append(scene)
    campus, port = scenes['campus'], scenes['port']
    for orientation, view in (('landscape', campus), ('portrait', campus['portrait'])):
        # tools/title_art.py still writes Campus's sign as the Beach path.
        old = next(h for h in view['hotspots'] if h['id'] in ('beach-path', 'port-path', 'jungle-path'))
        resign(old, 'jungle-path', 'scene:jungle-path', 'Jungle Path', 'up', CAMPUS_SIGN[orientation])
    campus_portrait(ledger, campus)
    for orientation, view in (('landscape', port), ('portrait', port['portrait'])):
        source = LOCAL/PLATES['port'].format(o=orientation)
        if source.is_file():
            ledger.plate(source, view['image'], view['low'])
        old = next(h for h in view['hotspots'] if h['id'] in ('campus-path', 'jungle-path'))
        resign(old, 'jungle-path', 'scene:jungle-path', 'Jungle Path', old['sign']['direction'])
        view['hotspots'] = [h for h in view['hotspots'] if h['id'] != 'market-path']
        view['hotspots'].append(sign('market-path', 'scene:market', 'Market', 'right', PORT_MARKET[orientation]))
    farm = LOCAL/PLATES['farm']
    if farm.is_file():
        # The Farm game's entrance draws the same painting as the title scene.
        for image, low in ((scenes['farm']['image'], scenes['farm']['low']), ('assets/garden/art/scene-landscape.webp', None)):
            if low: ledger.plate(farm, image, low)
            else: ledger.background(farm, image)
        # The Farm game records its painting's origin and ships a small preview.
        ledger.background(farm, 'assets/garden/previews/scene-landscape.webp', size=(128, 72))
        garden = json.loads(GARDEN_PROVENANCE.read_text())
        row = next(a for a in garden['assets'] if a['runtime'] == 'assets/garden/art/scene-landscape.webp')
        row.update(source=str(farm.relative_to(ROOT)), sha256=digest(ROOT/row['runtime']), source_sha256=digest(farm))
        GARDEN_PROVENANCE.write_text(json.dumps(garden, ensure_ascii=False, indent=2)+'\n')
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    ledger.save()
    PROVENANCE.write_text(json.dumps(dict(
        owner_request='A path at the left of the Farm to a Market shopping street that also connects back to the Port '
                      '(the Beach, renamed); a tropical Jungle Path between Campus and the Port, right Campus, left Port; '
                      'the Campus sign to it upright; in portrait its path between the treehouse and the drums, '
                      'and the frogs on the rocks.',
        generator='Harmony generate_image (Codex built-in image generation); original Jungle watercolor',
        style_reference='assets/jungle/title/farm-portrait.webp and campus-portrait.webp (style only)',
        method='Whole new Market and Jungle Path plates; path edits regenerated only a crop around the join and '
               'were feathered into the unchanged plates. Shop outlines are traced by hand; animal outlines come '
               'from offline BiRefNet cutouts of each crop. Glows are lossless rims from those outlines.',
        assets=ledger.receipts), indent=2)+'\n')
    print('Integrated the Market, the Jungle Path and their routes; run python3 tools/title_scenes.py next')


if __name__ == '__main__':
    main()

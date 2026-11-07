"""Integrate the world map title scene: one shared clean painted plate
with a transparent landmark layer and hover glow for every area.

The owner asked for a world map in the painted style where every area we can go
to is a distinct, selectable building or landmark. tools/title_world_map.json
lists the landmarks, so a new area adds itself with one entry; masters stay in
ignored local/art-development/world-map/. This explicit authoring command
exports the runtime AVIFs and writes the "map" scene into
tools/title_hotspots.json. Normal builds never run it.

    python3 tools/title_world_map.py && python3 tools/title_scenes.py

A landmark whose scene does not exist yet stays locked (faded, "not yet") until
its scene lands and this command runs again. A "locked:" landmark is a place not
built yet, such as the darkness beyond the Desert; it keeps its own painting.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from image_exports import export_image
from title_desert import outline

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'tools/title_world_map.json'
LOCAL = ROOT/'local/art-development/world-map'
MANIFEST = ROOT/'tools/title_hotspots.json'
PROVENANCE = ROOT/'tools/art_provenance/world-map.json'
ASSETS = 'assets/jungle/title/world-map/'
CANVAS = {'landscape': (1672, 941), 'portrait': (1024, 1536)}
# Transparent layer margin (layer pixels) that holds the glow's outer rim.
PAD = 20
# The plate's outer band blends into the flat paper the window shows around it.
EDGE = 36


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def paper(spec):
    value = int(spec['paper'], 16)
    return (value >> 16 & 255, value >> 8 & 255, value & 255)


def layer(mark):
    """The landmark master, cleaned and cropped, at its largest placed width."""
    with Image.open(LOCAL/'layers'/mark['layer']) as original:
        picture = original.convert('RGBA')
    alpha = picture.getchannel('A').point(lambda v: 0 if v < 8 else 255 if v >= 246 else v)
    picture.putalpha(alpha)
    picture = picture.crop(alpha.getbbox())
    width = max(mark[orientation][2] for orientation in CANVAS)
    if width < picture.width:
        picture = picture.resize((width, round(picture.height * width / picture.width)), Image.Resampling.LANCZOS)
    padded = Image.new('RGBA', (picture.width + 2 * PAD, picture.height + 2 * PAD))
    padded.alpha_composite(picture, (PAD, PAD))
    rgba = np.array(padded)
    rgba[rgba[:, :, 3] == 0, :3] = 0
    return Image.fromarray(rgba), picture.width


def faded(picture, color):
    """A place that is not open yet: pale, washed toward the paper, half seen."""
    rgba = np.array(picture).astype(np.float32)
    grey = rgba[:, :, :3] @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    for channel in range(3):
        soft = rgba[:, :, channel] * 0.35 + grey * 0.65
        rgba[:, :, channel] = soft * 0.45 + color[channel] * 0.55
    rgba[:, :, 3] *= 0.62
    out = np.rint(rgba).clip(0, 255).astype(np.uint8)
    out[out[:, :, 3] == 0, :3] = 0
    return Image.fromarray(out)


def glow(picture, soft=False):
    """A bright cream halo around the landmark, which stands out on the
    yellow-green grass where the title scenes' golden rim would not, and a
    slight inner lift. The menu draws it at full pulse over the layer. A SOFT
    glow (the darkness) only brightens a little where it is thickest."""
    if soft:
        alpha = np.asarray(picture.getchannel('A').filter(ImageFilter.GaussianBlur(6)), dtype=np.float32) * 0.3
        rgba = np.zeros((picture.height, picture.width, 4), dtype=np.uint8)
        rgba[:, :, :3] = (214, 206, 255)
        rgba[:, :, 3] = np.rint(alpha).clip(0, 255).astype(np.uint8)
        rgba[rgba[:, :, 3] == 0, :3] = 0
        return Image.fromarray(rgba)
    mask = picture.getchannel('A').point(lambda v: 255 if v >= 96 else 0)
    interior = np.asarray(mask.filter(ImageFilter.GaussianBlur(0.7)), dtype=np.float32)/255
    near = np.asarray(mask.filter(ImageFilter.MaxFilter(13)).filter(ImageFilter.GaussianBlur(3)), dtype=np.float32)/255
    far = np.asarray(mask.filter(ImageFilter.MaxFilter(15)).filter(ImageFilter.GaussianBlur(10)), dtype=np.float32)/255
    outer = np.minimum(255, near*255 + far*200)
    alpha = outer*(1-interior) + interior*40
    rgba = np.zeros((picture.height, picture.width, 4), dtype=np.uint8)
    for channel, (outside, inside) in enumerate(zip((255, 247, 205), (255, 250, 230))):
        rgba[:, :, channel] = np.rint(outside*(1-interior)+inside*interior).astype(np.uint8)
    rgba[:, :, 3] = np.rint(alpha).clip(0, 255).astype(np.uint8)
    rgba[rgba[:, :, 3] == 0, :3] = 0
    return Image.fromarray(rgba)


def shadow(plate, rect, pad, spread):
    """A soft painted contact shadow, so a landmark stands on its ground."""
    x, y, w, h = rect
    mask = Image.new('L', plate.size, 0)
    cx, cy = x + w / 2, y + h - pad - 4
    rx, ry = w * spread / 2, max(8, h * 0.05)
    ImageDraw.Draw(mask).ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=96)
    mask = mask.filter(ImageFilter.GaussianBlur(ry))
    shade = Image.new('RGB', plate.size, (88, 92, 48))
    return Image.composite(Image.blend(plate, shade, 0.5), plate, mask)


def edge(plate, color):
    """Fade the plate's outermost band into the flat paper color."""
    width, height = plate.size
    ys, xs = np.mgrid[0:height, 0:width]
    distance = np.minimum(np.minimum(xs, width - 1 - xs), np.minimum(ys, height - 1 - ys)).astype(np.float32)
    share = np.clip(1 - distance / EDGE, 0, 1)
    share = share * share * (3 - 2 * share)
    pixels = np.asarray(plate, dtype=np.float32)
    pixels = pixels * (1 - share[:, :, None]) + np.array(color, dtype=np.float32) * share[:, :, None]
    return Image.fromarray(np.rint(pixels).astype(np.uint8))


def resolve(mark, names, games):
    """The landmark's target, locked while its scene is still missing."""
    kind, _, dest = mark['target'].partition(':')
    if kind == 'scene' and dest in names or kind == 'game' and dest in games:
        return mark['target']
    if kind == 'locked' and dest == mark['id']:
        return mark['target']
    if kind == 'scene':
        print(f'{mark["id"]}: scene {dest} does not exist yet, so its landmark stays locked')
        return 'locked:' + mark['id']
    raise SystemExit(f'world map: {mark["id"]} has an unknown target {mark["target"]}')


def SharedGeometry(mark, rect, polygon):
    """The landscape rectangle is the one map, even for legacy split metadata."""
    shared = mark.get('rects', {}).get('landscape')
    if shared is None:
        return rect, polygon
    if not isinstance(shared, list) or len(shared)!=4 or any(type(v) is not int for v in shared) or min(shared[2:])<1:
        raise ValueError('world map: invalid shared landmark rectangle')
    return list(shared), [[round(shared[0]+(x-rect[0])*shared[2]/rect[2]),
                           round(shared[1]+(y-rect[1])*shared[3]/rect[3])] for x,y in polygon]


def main():
    spec = json.loads(DATA.read_text())
    data = json.loads(MANIFEST.read_text())
    names = {s['name'] for s in data['scenes']} - {spec['scene']}
    games = {line.split('|')[1] for line in (ROOT/'games/catalog.txt').read_text().splitlines() if '|' in line}
    source = ROOT/spec['source']
    with Image.open(source) as original:
        if list(original.size) != spec['canvas']:
            raise SystemExit('world map: approved terrain dimensions differ from the specification')
    # Both window orientations show this same whole, unwarped painting.
    # Existing transparent landmark artwork is reused byte for byte.
    scene = dict(name=spec['scene'], width=spec['canvas'][0], height=spec['canvas'][1],
                 image='assets/jungle/title/world-map.avif', low='assets/jungle/title/world-map-low.avif', back=True)
    portrait = dict(width=spec['canvas'][0], height=spec['canvas'][1],
                    image=scene['image'], low=scene['low'])
    for view in (scene, portrait):
        view['preload'] = ['assets/jungle/title/window-animation/cloud.avif',
                           'assets/jungle/title/window-animation/cloud-wisp.avif']
    # Each place clears its painted region ("region": core ellipses), and two
    # visited neighbours clear the land along the route that joins them.
    scene['exploration'] = [dict(area=m['id'], center=m['center'], region=m['region']) for m in spec['landmarks']
                            if not m['target'].startswith('locked:')]
    scene['exploration_routes'] = spec['routes']
    portrait['exploration'] = scene['exploration']
    portrait['exploration_routes'] = scene['exploration_routes']
    receipts, exports = [], []
    for orientation, view in (('landscape', scene), ('portrait', portrait)):
        hotspots = []
        for mark in spec['landmarks']:
            target = resolve(mark, names, games)
            cx, cy = mark['center']
            if mark.get('terrain_region'):
                # The arid terrain remains a destination without a camel,
                # guide or painted footpath. Feedback uses the existing UI.
                rect = [cx - 130, cy - 90, 260, 180]
                rest = highlight = ''
                x, y, w, h = rect
                polygon = [[x,y],[x+w,y],[x+w,y+h],[x,y+h]]
            else:
                rest = ASSETS + mark['id'] + '.avif'
                highlight = ASSETS + mark['id'] + '-glow.avif'
                with Image.open(ROOT/rest) as original:
                    picture = original.convert('RGBA')
                placed = mark['landscape'][2]
                scale = placed / (picture.width - PAD * 2)
                width, height = round(picture.width * scale), round(picture.height * scale)
                rect = [round(cx - width / 2), round(cy - height / 2), width, height]
                polygon = outline(picture.getchannel('A'), rect[0], rect[1], scale)
            rect, polygon = SharedGeometry(mark,rect,polygon)
            if rect[0] < 0 or rect[1] < 0 or rect[0]+rect[2] > view['width'] or rect[1]+rect[3] > view['height']:
                raise SystemExit(f'world map: {mark["id"]} leaves the {orientation} plate')
            hotspots.append(dict(id=mark['id'], target=target, glow_rect=rect, rest=rest, glow=highlight, polygon=polygon, **({'rotation':mark['rotation']} if 'rotation' in mark else {})))
            if orientation == 'landscape':
                receipts.append(dict(landmark=mark['id'], target=target, center=mark['center'],
                                     rect=rect, runtime=rest, terrain_region=bool(mark.get('terrain_region')),
                                     **(dict(sha256=digest(ROOT/rest), glow=highlight, glow_sha256=digest(ROOT/highlight)) if rest else {})))
        view['hotspots'] = hotspots
        if orientation == 'landscape':
            for key, size in (('image', None), ('low', (240, round(spec['canvas'][1] * 240 / spec['canvas'][0])))):
                exported = export_image(source, ROOT/view[key], 'title-background', **({'size': size} if size else {}))
                exports.append((source, ROOT/view[key], exported))
        receipts.append(dict(plate=orientation, master=spec['source'], master_sha256=digest(source),
                             runtime=view['image'], sha256=digest(ROOT/view['image']), low=view['low'], low_sha256=digest(ROOT/view['low'])))
    scene['portrait'] = portrait
    data['scenes'] = [s for s in data['scenes'] if s['name'] != spec['scene']] + [scene]
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    PROVENANCE.write_text(json.dumps(dict(
        owner_request='Fully implement approved terrain v3 and clouds around areas not yet visited.',
        approval='Owner accepted the flagged before-after-v3 comparison on 2026-11-04; terrain integrated as approved without regeneration.',
        layout=f'{spec["canvas"][0]}x{spec["canvas"][1]} whole painting and shared landscape layout in both orientations; '
               + '; '.join(f'{mark["id"]} center {mark["center"][0]},{mark["center"][1]}' for mark in spec['landmarks'])
               + '. No camel or desert footpath.',
        method='Original-based AVIF q35; existing exact landmark AVIFs reused. Existing window clouds cover unvisited terrain; genuine scene/activity visits clear their surroundings and persist separately from activity progress.',
        assets=receipts), indent=2) + '\n')
    # Update only these changed plates in the canonical AVIF receipt.
    canonical = ROOT/'tools/canonical_avif.json'
    catalog = json.loads(canonical.read_text())
    for master, runtime, exported in exports:
        with Image.open(runtime) as picture, Image.open(master) as original:
            decoded = picture.convert('RGBA')
            rgba = original.convert('RGBA')
            if rgba.size != decoded.size:
                rgba = rgba.resize(decoded.size, Image.Resampling.LANCZOS)
            ah = hashlib.sha256(decoded.getchannel('A').tobytes()).hexdigest()
            catalog['files'][runtime.relative_to(ROOT).as_posix()] = dict(
                source=master.relative_to(ROOT).as_posix(), source_sha256=digest(master), source_bytes=master.stat().st_size,
                source_rgba_sha256=hashlib.sha256(rgba.tobytes()).hexdigest(), dimensions=list(decoded.size),
                alpha=False, source_alpha_sha256=ah, alpha_sha256=ah,
                rgba_sha256=hashlib.sha256(decoded.tobytes()).hexdigest(), sha256=digest(runtime), bytes=runtime.stat().st_size,
                quality=exported.quality, lossless=exported.lossless, subsampling='444' if exported.lossless else '420', speed=6)
    catalog['count'] = len(catalog['files'])
    catalog['before_bytes'] = sum(row['source_bytes'] for row in catalog['files'].values())
    catalog['after_bytes'] = sum(row['bytes'] for row in catalog['files'].values())
    canonical.write_text(json.dumps(catalog, indent=2) + '\n')
    print('world map: approved full-size terrain, placements and AVIF receipts integrated')


if __name__ == '__main__':
    main()

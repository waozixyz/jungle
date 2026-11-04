"""Integrate the world map title scene: one clean painted plate per orientation
with a transparent landmark layer and hover glow for every area.

The owner asked for a world map in the painted style where every area we can go
to is a distinct, selectable building or landmark. tools/title_world_map.json
lists the landmarks, so a new area adds itself with one entry; masters stay in
ignored local/art-development/world-map/. This explicit authoring command
exports the runtime WebPs and writes the "map" scene into
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


def main():
    spec = json.loads(DATA.read_text())
    data = json.loads(MANIFEST.read_text())
    color = paper(spec)
    names = {s['name'] for s in data['scenes']} - {spec['scene']}
    games = {line.split('|')[1] for line in (ROOT/'games/catalog.txt').read_text().splitlines() if '|' in line}
    scratch = LOCAL/'runtime-exports'
    scratch.mkdir(parents=True, exist_ok=True)
    marks, receipts = [], []
    for mark in spec['landmarks']:
        target = resolve(mark, names, games)
        picture, width = layer(mark)
        planned = target.startswith('locked:') and not mark['target'].startswith('locked:')
        if planned:
            picture = faded(picture, color)
        light = glow(picture, soft=mark['target'].startswith('locked:'))
        rest, highlight = ASSETS + mark['id'] + '.webp', ASSETS + mark['id'] + '-glow.webp'
        for image, path in ((picture, rest), (light, highlight)):
            raw = scratch/(Path(path).stem + '.png')
            image.save(raw)
            export_image(raw, ROOT/path, 'cutout')
        marks.append((mark, target, picture, width, rest, highlight))
        source = LOCAL/'layers'/mark['layer']
        receipts.append(dict(landmark=mark['id'], target=target, master=str(source.relative_to(ROOT)),
                             master_sha256=digest(source), runtime=rest, sha256=digest(ROOT/rest),
                             glow=highlight, glow_sha256=digest(ROOT/highlight), size=list(picture.size)))
    scene = dict(name=spec['scene'], image='assets/jungle/title/world-map.webp',
                 low='assets/jungle/title/world-map-low.webp', back=True)
    portrait = dict(width=CANVAS['portrait'][0], height=CANVAS['portrait'][1],
                    image='assets/jungle/title/world-map-portrait.webp', low='assets/jungle/title/world-map-portrait-low.webp')
    for orientation, view in (('landscape', scene), ('portrait', portrait)):
        source = LOCAL/spec['plates'][orientation]
        with Image.open(source) as original:
            plate = original.convert('RGB')
        if plate.size != CANVAS[orientation]:
            raise SystemExit(f'{source.name} must be {CANVAS[orientation]}')
        hotspots = []
        for mark, target, picture, width, rest, highlight in marks:
            x, y, placed = mark[orientation]
            scale = placed / width
            pad = round(PAD * scale)
            rect = [x - pad, y - pad, round(picture.width * scale), round(picture.height * scale)]
            if rect[0] < 0 or rect[1] < 0 or rect[0] + rect[2] > plate.width or rect[1] + rect[3] > plate.height:
                raise SystemExit(f'world map: {mark["id"]} leaves the {orientation} plate')
            if mark.get('shadow'):
                plate = shadow(plate, rect, pad, mark['shadow'])
            hotspots.append(dict(id=mark['id'], target=target, glow_rect=rect, rest=rest, glow=highlight,
                                 polygon=outline(picture.getchannel('A'), rect[0], rect[1], scale)))
        plate = edge(plate, color)
        master = LOCAL/f'map-{orientation}-plate.png'
        plate.save(master)
        export_image(master, ROOT/view['image'], 'title-background')
        export_image(master, ROOT/view['low'], 'title-background', size=(240, round(plate.height * 240 / plate.width)))
        view['hotspots'] = hotspots
        receipts.append(dict(plate=orientation, generated=str(source.relative_to(ROOT)), generated_sha256=digest(source),
                             master=str(master.relative_to(ROOT)), master_sha256=digest(master),
                             runtime=view['image'], sha256=digest(ROOT/view['image']),
                             low=view['low'], low_sha256=digest(ROOT/view['low'])))
    scene['portrait'] = portrait
    # Only the current landmarks' pictures stay in the runtime folder.
    keep = {Path(path).name for _, _, _, _, rest, highlight in marks for path in (rest, highlight)}
    for stale in (ROOT/ASSETS).glob('*.webp'):
        if stale.name not in keep:
            stale.unlink()
    data['scenes'] = [s for s in data['scenes'] if s['name'] != spec['scene']] + [scene]
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    PROVENANCE.write_text(json.dumps(dict(
        owner_request='Design a world map inspired by the painted style, where each area we can go to is a '
                      'distinct building or landmark that can be selected.',
        generator='Harmony generate_image (Codex built-in image generation); original Jungle watercolor',
        style_reference='the Jungle title paintings (treehouse, Campus, Port, Desert edge)',
        layout='owner 2026-11-03: Market, Farm, Campus with the Treehouse, Desert from left to right; the Port '
               'above the Market, the Beach right of the Port and the Aquarium above the Beach; the Jungle Path '
               'between the Beach and Campus, shifted left to leave the Treehouse directly behind the music huts; '
               'beyond the Desert the world fades into darkness (no mountain yet).',
        method='Codex paints a clean background plate per orientation from a position guide and each landmark '
               'as its own transparent layer, shared by both orientations; a cream halo glows from each '
               'silhouette; the darkness beyond the Desert is a locked layer that answers "not yet"; the '
               'outer band fades into the flat paper shown around the map.',
        assets=receipts), indent=2) + '\n')
    print('Integrated the world map; run python3 tools/title_scenes.py next')


if __name__ == '__main__':
    main()

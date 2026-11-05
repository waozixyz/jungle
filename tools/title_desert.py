"""Integrate the Desert edge title scene: painted plates, guide and camel layers.

The owner asked for the Desert sign to lead to the edge of the jungle, where a
guide and his camel explain why we cannot cross the desert yet. Masters stay in
ignored local/art-development/desert-edge/; this explicit authoring command
exports the runtime AVIFs and the scene's hotspots. Normal builds never run it.

    python3 tools/title_desert.py
"""
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
from image_exports import export_image
from title_signs import BOARDS

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT/'local/art-development/desert-edge'
MANIFEST = ROOT/'tools/title_hotspots.json'
PROVENANCE = ROOT/'tools/art_provenance/desert-edge.json'
OBJECTS = 'assets/jungle/title/objects/'
CANVAS = {'landscape': (1672, 941), 'portrait': (1024, 1536)}
# v2: the path back to Campus runs straight left out of the picture (owner,
# 2026-11-03); only that region was regenerated and feathered into v1.
PLATES = {'landscape': 'desert-landscape-v2.png', 'portrait': 'desert-portrait-v2.png'}
CUTOUTS = {'camel': ('guide-camel-v3.png', 'guide-camel-v2.png', 'guide-camel-v1.png'), 'guide': ('guide-man-v1.png',)}
# Where each layer stands: left edge, feet line and height in scene pixels.
# The camel waits just behind its guide at the jungle's edge, on open sand.
# All three stay whole at the centered cover fit from 4:3 tablets to 9:20
# phones (portrait shows x 166-858, landscape 4:3 shows x 209-1463).
PLACES = {
    'landscape': {'camel': (948, 772, 420), 'guide': (826, 792, 362), 'sign': [232, 584, 232, 232]},
    'portrait': {'camel': (422, 1002, 474), 'guide': (250, 1024, 424), 'sign': [184, 1112, 240, 240]},
}
BANDS = 28


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def cutout(name):
    """The first existing master, with stray haze removed, cropped to the figure."""
    source = next(LOCAL/n for n in CUTOUTS[name] if (LOCAL/n).is_file())
    with Image.open(source) as original:
        picture = original.convert('RGBA')
    alpha = picture.getchannel('A').point(lambda v: 0 if v < 8 else 255 if v >= 246 else v)
    picture.putalpha(alpha)
    left, top, right, bottom = alpha.getbbox()
    margin = 4
    box = (max(0, left - margin), max(0, top - margin),
           min(picture.width, right + margin), min(picture.height, bottom + margin))
    return source, picture.crop(box)


def outline(alpha, x, y, scale):
    """Left and right silhouette edges in horizontal bands, as a scene polygon."""
    width, height = alpha.size
    rows = []
    for band in range(BANDS):
        top = band * height // BANDS
        strip = alpha.crop((0, top, width, max(top + 1, (band + 1) * height // BANDS)))
        box = strip.point(lambda v: 255 if v >= 96 else 0).getbbox()
        if box:
            rows.append((top, box[0], box[2], (band + 1) * height // BANDS))
    left = [(x + round(l * scale), y + round(t * scale)) for t, l, _, _ in rows]
    left += [(x + round(rows[-1][1] * scale), y + round(rows[-1][3] * scale) - 1)]
    right = [(x + round(r * scale), y + round(b * scale) - 1) for _, _, r, b in reversed(rows)]
    right += [(x + round(rows[0][2] * scale), y + round(rows[0][0] * scale))]
    points = []
    for point in left + right:
        if not points or points[-1] != list(point):
            points.append(list(point))
    return points


def shadow(plate, rect, spread):
    """A soft painted contact shadow, so the figures stand on the sand."""
    x, y, w, h = rect
    mask = Image.new('L', plate.size, 0)
    cx, cy = x + w * spread[0], y + h - 4
    rx, ry = w * spread[1], max(10, h * 0.035)
    ImageDraw.Draw(mask).ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=120)
    mask = mask.filter(ImageFilter.GaussianBlur(ry * 0.9))
    shade = Image.new('RGB', plate.size, (150, 112, 70))
    return Image.composite(Image.blend(plate, shade, 0.55), plate, mask)


def sign_hotspot(rect):
    board, polygon = BOARDS['left']
    x, y, w, h = rect
    return dict(id='campus-path', target='scene:campus', glow_rect=rect,
                rest=OBJECTS+'wood-arrow-left.avif', glow=OBJECTS+'wood-arrow-left-glow.avif',
                polygon=[[x+round(px*w/1254), y+round(py*h/1254)] for px, py in polygon],
                sign=dict(label='Campus', direction='left',
                          label_rect=[round(board[0]*w/1254), round(board[1]*h/1254),
                                      round(board[2]*w/1254), round(board[3]*h/1254)]))


def main():
    scratch = LOCAL/'runtime-exports'
    scratch.mkdir(parents=True, exist_ok=True)
    layers, receipts = {}, []
    for name in CUTOUTS:
        source, picture = cutout(name)
        raw = scratch/f'desert-{name}.png'
        picture.save(raw)
        glow = Image.new('RGBA', picture.size, (255, 249, 222, 0))
        glow.putalpha(picture.getchannel('A'))
        light = scratch/f'desert-{name}-glow.png'
        glow.save(light)
        rest, highlight = OBJECTS+f'desert-{name}.avif', OBJECTS+f'desert-{name}-glow.avif'
        export_image(raw, ROOT/rest, 'cutout')
        export_image(light, ROOT/highlight, 'cutout')
        layers[name] = (picture, rest, highlight)
        receipts.append(dict(layer=name, master=str(source.relative_to(ROOT)), master_sha256=digest(source),
                             runtime=rest, sha256=digest(ROOT/rest), glow=highlight, glow_sha256=digest(ROOT/highlight),
                             size=list(picture.size)))
    scene = dict(name='desert', image='assets/jungle/title/desert.avif', low='assets/jungle/title/desert-low.avif')
    portrait = dict(width=1024, height=1536, image='assets/jungle/title/desert-portrait.avif',
                    low='assets/jungle/title/desert-portrait-low.avif')
    for orientation, view in (('landscape', scene), ('portrait', portrait)):
        source = LOCAL/PLATES[orientation]
        with Image.open(source) as original:
            plate = original.convert('RGB')
        if plate.size != CANVAS[orientation]:
            raise SystemExit(f'{source.name} must be {CANVAS[orientation]}')
        hotspots = [sign_hotspot(PLACES[orientation]['sign'])]
        for name, ident, spread in (('camel', 'camel', (0.55, 0.42)), ('guide', 'desert-guide', (0.5, 0.42))):
            picture, rest, highlight = layers[name]
            left, feet, height = PLACES[orientation][name]
            scale = height / picture.height
            rect = [left, feet - height, round(picture.width * scale), height]
            plate = shadow(plate, rect, spread)
            hotspots.append(dict(id=ident, target='dialogue:desert-guide', glow_rect=rect, rest=rest, glow=highlight,
                                 polygon=outline(picture.getchannel('A'), rect[0], rect[1], scale)))
        master = LOCAL/f'desert-{orientation}-plate.png'
        plate.save(master)
        export_image(master, ROOT/view['image'], 'title-background')
        export_image(master, ROOT/view['low'], 'title-background',
                     size=(240, round(plate.height * 240 / plate.width)))
        view['hotspots'] = hotspots
        receipts.append(dict(plate=orientation, generated=str(source.relative_to(ROOT)), generated_sha256=digest(source),
                             master=str(master.relative_to(ROOT)), master_sha256=digest(master),
                             runtime=view['image'], sha256=digest(ROOT/view['image']),
                             low=view['low'], low_sha256=digest(ROOT/view['low'])))
    scene['portrait'] = portrait
    data = json.loads(MANIFEST.read_text())
    data['scenes'] = [s for s in data['scenes'] if s['name'] != 'desert'] + [scene]
    campus = next(s for s in data['scenes'] if s['name'] == 'campus')
    for view in (campus, campus['portrait']):
        next(h for h in view['hotspots'] if h['id'] == 'desert-path')['target'] = 'scene:desert'
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    PROVENANCE.write_text(json.dumps(dict(
        owner_request='When we click on desert we should be at the edge of the forest with a guy and a camel; '
                      'clicking him gives dialogue on why we are not ready to cross the desert yet.',
        generator='Harmony generate_image (Codex built-in image generation); original Jungle watercolor',
        style_reference='local/art-development/title-covers.png and the Campus title painting',
        method='clean plates without figures; separate transparent guide and camel layers placed over them '
               'with soft painted contact shadows; Campus sign reuses the shared arrow plank. '
               'The path back to Campus runs straight left: only the left path region of each plate was '
               'regenerated and feathered into the original plate (v2).',
        assets=receipts), indent=2) + '\n')
    print('Integrated the Desert edge scene; run python3 tools/title_scenes.py next')


if __name__ == '__main__':
    main()

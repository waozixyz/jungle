"""Integrate the Wüste (Desert) title scene: white dunes, a lagoon oasis and a big
branch full of colorful birds, each bird its own cut-out layer.

The owner asked (2026-11-05) for the desert to look like the world map, white
and with the oasis, with no camel or person but "a big branch of colorful
parrots", and "each bird must be its own asset, not in the scene directly".
The painted plates carry only the sand, oasis and branch; every bird is a
separate transparent layer placed here. Tapping any bird opens the parrots'
tap-through speech bubble beside the macaw. Masters stay in ignored
local/art-development/desert-edge/; this explicit authoring command exports
the runtime AVIFs, their canonical receipts and the scene's hotspots. Normal
builds never run it.

    python3 tools/title_desert.py && python3 tools/title_scenes.py
"""
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
from image_exports import export_image, save_scaled

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT/'local/art-development/desert-edge'
MANIFEST = ROOT/'tools/title_hotspots.json'
PROVENANCE = ROOT/'tools/art_provenance/desert-edge.json'
CANONICAL = ROOT/'tools/canonical_avif.json'
OBJECTS = 'assets/jungle/title/objects/'
CANVAS = {'landscape': (1672, 941), 'portrait': (1024, 1536)}
# v3 (owner, 2026-11-05): white sand, a turquoise lagoon oasis and one big
# mossy branch, painted without any bird; the jungle edge and the path straight
# left to Campus keep their places from v2.
PLATES = {'landscape': 'desert-landscape-v3.png', 'portrait': 'desert-portrait-v3.png'}
DIALOGUE = 'dialogue:desert-birds'
SPEAKER = 'macaw'
# Every bird: its trimmed transparent master in LOCAL/birds/.
BIRDS = ('macaw', 'blue-parrot', 'green-parakeet', 'cockatiel', 'lovebird', 'pink-parrot',
         'budgie', 'finch', 'parrotlet', 'rosella', 'sky-chick', 'macaw-chick')
# Where each bird perches, in paint order (earlier birds sit behind later
# ones): center x, feet line on the branch and height in scene pixels. The back
# row stands a little larger so the front birds, painted over it, own the
# smaller glow rect and win the host's smallest-rect tap rule. All stay
# whole at the centered cover fit from 4:3 tablets to 20:9 phones (landscape
# 4:3 shows x 209-1463) and 3:4 tablets to 9:20 phones (portrait x 166-858).
PLACES = {
    'landscape': {
        'cockatiel': (292, 511, 168), 'rosella': (472, 514, 168), 'pink-parrot': (651, 519, 168),
        'parrotlet': (843, 523, 168), 'macaw-chick': (1038, 523, 168), 'budgie': (1244, 520, 168),
        'blue-parrot': (388, 562, 150), 'lovebird': (557, 566, 150), 'macaw': (746, 572, 150),
        'sky-chick': (940, 573, 150), 'green-parakeet': (1136, 572, 150), 'finch': (1352, 567, 150),
    },
    'portrait': {
        'cockatiel': (236, 683, 138), 'rosella': (332, 692, 138), 'pink-parrot': (428, 704, 138),
        'parrotlet': (518, 710, 138), 'macaw-chick': (610, 714, 138), 'budgie': (712, 704, 138),
        'blue-parrot': (230, 733, 122), 'lovebird': (321, 743, 122), 'macaw': (429, 754, 122),
        'sky-chick': (541, 761, 122), 'green-parakeet': (656, 760, 122), 'finch': (776, 749, 122),
    },
}
# The Campus plank's v2 top and how far v3 moves it (rerunnable: the drop is
# measured from the v2 top, not from whatever the manifest holds now).
PLANK_TOP = {'landscape': 614, 'portrait': 1143}
PLANK_DROP = {'landscape': 76, 'portrait': 0}
# The back row stands behind the front birds; its feet are hidden, so only the
# front row casts a contact shadow on the moss.
BACK_ROW = {'cockatiel', 'rosella', 'pink-parrot', 'parrotlet', 'macaw-chick', 'budgie'}
BANDS = 28
ALPHA_FLOOR = 8


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def cutout(name):
    """A bird's master with stray haze removed, cropped to the bird."""
    source = LOCAL/'birds'/f'{name}.png'
    with Image.open(source) as original:
        picture = original.convert('RGBA')
    alpha = picture.getchannel('A').point(lambda v: 0 if v < ALPHA_FLOOR else 255 if v >= 246 else v)
    picture.putalpha(alpha)
    picture.paste((0, 0, 0, 0), mask=alpha.point(lambda v: 255 if v == 0 else 0))
    left, top, right, bottom = alpha.getbbox()
    margin = 6
    box = (max(0, left - margin), max(0, top - margin),
           min(picture.width, right + margin), min(picture.height, bottom + margin))
    cropped = Image.new('RGBA', (box[2] - box[0], box[3] - box[1]), (0, 0, 0, 0))
    cropped.paste(picture.crop(box), (0, 0))
    return source, cropped


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


def shadow(plate, rect):
    """A soft painted contact shadow where a bird's feet grip the branch."""
    x, y, w, h = rect
    mask = Image.new('L', plate.size, 0)
    cx, cy = x + w * 0.5, y + h - 2
    rx, ry = w * 0.32, max(5, h * 0.04)
    ImageDraw.Draw(mask).ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=110)
    mask = mask.filter(ImageFilter.GaussianBlur(ry * 0.8))
    shade = Image.new('RGB', plate.size, (70, 60, 40))
    return Image.composite(Image.blend(plate, shade, 0.5), plate, mask)


def ship_scaled(master, runtime):
    """The owner's 75% standard for MASTER, with its canonical receipt row."""
    with Image.open(master) as original:
        original.load()
        alpha = save_scaled(original, runtime)
        source = original.convert('RGBA')
    with Image.open(runtime) as shipped:
        rgba = shipped.convert('RGBA')
    name = master.relative_to(ROOT).as_posix()
    return dict(source=name, source_sha256=digest(master), source_bytes=master.stat().st_size,
                source_rgba_sha256=sha(source.tobytes()), dimensions=list(rgba.size), alpha=alpha,
                source_alpha_sha256=sha(source.getchannel('A').tobytes()),
                alpha_sha256=sha(rgba.getchannel('A').tobytes()), rgba_sha256=sha(rgba.tobytes()),
                sha256=digest(runtime), bytes=runtime.stat().st_size, quality=35, lossless=False,
                subsampling='444' if alpha else '420', speed=6, design_dimensions=list(source.size), scale=0.75,
                master=name, master_sha256=digest(master), exact_alpha=False, alpha_quality=90 if alpha else 100)


def ship_low(master, runtime, size):
    """The small first-paint plate: a q35 export at SIZE, as before."""
    exported = export_image(master, runtime, 'title-background', size=size)
    with Image.open(runtime) as shipped, Image.open(master) as original:
        decoded = shipped.convert('RGBA')
        source = original.convert('RGBA').resize(decoded.size, Image.Resampling.LANCZOS)
    plain = sha(decoded.getchannel('A').tobytes())
    return dict(source=master.relative_to(ROOT).as_posix(), source_sha256=digest(master),
                source_bytes=master.stat().st_size, source_rgba_sha256=sha(source.tobytes()),
                dimensions=list(decoded.size), alpha=False, source_alpha_sha256=plain, alpha_sha256=plain,
                rgba_sha256=sha(decoded.tobytes()), sha256=digest(runtime), bytes=runtime.stat().st_size,
                quality=exported.quality, lossless=exported.lossless,
                subsampling='444' if exported.lossless else '420', speed=6)


def record(rows, retired):
    catalog = json.loads(CANONICAL.read_text())
    for name in retired:
        catalog['files'].pop(name, None)
    catalog['files'].update(rows)
    catalog['count'] = len(catalog['files'])
    catalog['before_bytes'] = sum(row['source_bytes'] for row in catalog['files'].values())
    catalog['after_bytes'] = sum(row['bytes'] for row in catalog['files'].values())
    CANONICAL.write_text(json.dumps(catalog, indent=2) + '\n')


def main():
    scratch = LOCAL/'runtime-exports'
    scratch.mkdir(parents=True, exist_ok=True)
    layers, receipts, rows = {}, [], {}
    for name in BIRDS:
        source, picture = cutout(name)
        raw = scratch/f'desert-{name}.png'
        picture.save(raw)
        glow = Image.new('RGBA', picture.size, (255, 249, 222, 0))
        glow.putalpha(picture.getchannel('A'))
        light = scratch/f'desert-{name}-glow.png'
        glow.save(light)
        rest, highlight = OBJECTS+f'desert-{name}.avif', OBJECTS+f'desert-{name}-glow.avif'
        rows[rest] = ship_scaled(raw, ROOT/rest)
        rows[highlight] = ship_scaled(light, ROOT/highlight)
        layers[name] = (picture, rest, highlight)
        receipts.append(dict(layer=name, master=str(source.relative_to(ROOT)), master_sha256=digest(source),
                             runtime=rest, sha256=digest(ROOT/rest), glow=highlight, glow_sha256=digest(ROOT/highlight),
                             size=list(picture.size)))
    data = json.loads(MANIFEST.read_text())
    previous = next(s for s in data['scenes'] if s['name'] == 'desert')
    scene = dict(name='desert', image='assets/jungle/title/desert.avif', low='assets/jungle/title/desert-low.avif')
    portrait = dict(width=1024, height=1536, image='assets/jungle/title/desert-portrait.avif',
                    low='assets/jungle/title/desert-portrait-low.avif')
    for orientation, view, old in (('landscape', scene, previous), ('portrait', portrait, previous['portrait'])):
        source = LOCAL/PLATES[orientation]
        with Image.open(source) as original:
            plate = original.convert('RGB')
        if plate.size != CANVAS[orientation]:
            raise SystemExit(f'{source.name} must be {CANVAS[orientation]}')
        # The Campus plank keeps its approved board and outline; it only follows
        # the v3 path down where the landscape branch now spans its old place.
        plank = json.loads(json.dumps(next(h for h in old['hotspots'] if h['id'] == 'campus-path')))
        drop = PLANK_DROP[orientation] - (plank['glow_rect'][1] - PLANK_TOP[orientation])
        for rect in (plank['glow_rect'], plank['editor_legacy_rect']):
            rect[1] += drop
        plank['polygon'] = [[x, y + drop] for x, y in plank['polygon']]
        hotspots = [plank]
        # Its post (a plain object layer) moves with it.
        view['objects'] = json.loads(json.dumps(old.get('objects', [])))
        for item in view['objects']:
            item['rect'][1] += drop
        places = PLACES[orientation]
        if set(places) != set(BIRDS):
            raise SystemExit(f'{orientation}: every bird needs exactly one perch')
        for name, (center, feet, height) in places.items():
            picture, rest, highlight = layers[name]
            scale = height / picture.height
            width = round(picture.width * scale)
            rect = [round(center - width / 2), feet - height, width, height]
            if name not in BACK_ROW:
                plate = shadow(plate, rect)
            hotspots.append(dict(id=f'desert-{name}', target=DIALOGUE, glow_rect=rect, rest=rest, glow=highlight,
                                 polygon=outline(picture.getchannel('A'), rect[0], rect[1], scale)))
        master = LOCAL/f'desert-{orientation}-plate.png'
        plate.save(master)
        rows[view['image']] = ship_scaled(master, ROOT/view['image'])
        rows[view['low']] = ship_low(master, ROOT/view['low'], (240, round(plate.height * 240 / plate.width)))
        view['hotspots'] = hotspots
        receipts.append(dict(plate=orientation, generated=str(source.relative_to(ROOT)), generated_sha256=digest(source),
                             master=str(master.relative_to(ROOT)), master_sha256=digest(master),
                             runtime=view['image'], sha256=digest(ROOT/view['image']),
                             low=view['low'], low_sha256=digest(ROOT/view['low'])))
    scene['portrait'] = portrait
    data['scenes'] = [scene if s['name'] == 'desert' else s for s in data['scenes']]
    campus = next(s for s in data['scenes'] if s['name'] == 'campus')
    for view in (campus, campus['portrait']):
        next(h for h in view['hotspots'] if h['id'] == 'desert-path')['target'] = 'scene:desert'
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    retired = [OBJECTS+f'desert-{old}{kind}.avif' for old in ('camel', 'guide') for kind in ('', '-glow')]
    for name in retired:
        (ROOT/name).unlink(missing_ok=True)
    record(rows, retired)
    PROVENANCE.write_text(json.dumps(dict(
        owner_request='The desert must be like in the map, so white and with the oasis; no camel or person but a '
                      'big branch of colorful, unique parrots; each bird must be its own asset, not in the scene '
                      'directly (owner, 2026-11-05).',
        generator='Harmony generate_image (Codex built-in image generation); original Jungle watercolor',
        style_reference='the world map Desert (white dunes, turquoise lagoons, palm clumps) and the Campus '
                        'title painting; the owner\'s bird screenshot only as a mood guide',
        method='v3 plates repaint the v2 desert edge as white sand with a lagoon oasis and one big mossy branch, '
               'without birds; every bird is cut from its own transparent master and placed here as a '
               'separate layer with a soft contact shadow on the branch. The Campus plank keeps its board.',
        assets=receipts), indent=2) + '\n')
    print('Integrated the Wüste scene; run python3 tools/title_scenes.py next')


if __name__ == '__main__':
    main()

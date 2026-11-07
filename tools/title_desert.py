"""Integrate the Wüste (Desert) title scene: white dunes, a lagoon oasis and a giant
tree at the side with two clear mossy branches and a magic bird house.

The owner asked (2026-11-05) for the desert to look like the world map, white
and with the oasis, and "each bird must be its own asset, not in the scene
directly". On 2026-11-06: "a giant tree on the side with a branch ... not
straight the full width, just half", then "add a bird house on the tree, at
start there should be no birds but a clear section of 2 branches where we put
a total of 18 birds that we will fill in from the magic bird house". So the
plates carry only the sand, oasis and tree; the bird house is its own cut-out
layer, and PERCHES holds the 18 empty perch slots the birds will use later.
Tapping the bird house opens the desert's tap-through speech bubble. Masters
stay in ignored local/art-development/desert-edge/; this explicit authoring
command exports the runtime AVIFs, their canonical receipts and the scene's
hotspots. Normal builds never run it.

    python3 tools/title_desert.py && python3 tools/title_scenes.py
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage
from image_exports import export_low_master, save_scaled

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT/'local/art-development/desert-edge'
MANIFEST = ROOT/'tools/title_hotspots.json'
PROVENANCE = ROOT/'tools/art_provenance/desert-edge.json'
CANONICAL = ROOT/'tools/canonical_avif.json'
OBJECTS = 'assets/jungle/title/objects/'
CANVAS = {'landscape': (1672, 941), 'portrait': (1024, 1536)}
# v5 (owner, 2026-11-06): the white-sand lagoon oasis with a giant tree at the
# left and two clear mossy branches (portrait: the crown limb and the lower
# branch), painted without any bird.
PLATES = {'landscape': 'desert-landscape-v5.png', 'portrait': 'desert-portrait-v4.png'}
DIALOGUE = 'dialogue:desert-birds'
HOUSE = 'bird-house'
# The bird house master (cut from its generated picture) and where it hangs:
# its rope's top tucked under a limb at HANG (x, y) and its width in pixels,
# between the hanging vines and inside the always-visible part of the scene.
HOUSE_MASTER = 'bird-house-cut.png'
HOUSE_SOURCE = 'bird-house-generated.png'
HANGS = {'landscape': dict(hang=[708, 520], width=104), 'portrait': dict(hang=[400, 788], width=90)}
# The empty perches the bird house's birds will fill, per orientation: each
# perch line is a limb's painted top edge as a polyline (x, y in scene pixels,
# measured on the plate), and each row spreads COUNT slots evenly across its x
# range on one line, feet FEET pixels below that edge, HEIGHT tall. A front row
# paints over its back row. Everything stays whole at the centered cover fit
# from 4:3 tablets to 20:9 phones (landscape 4:3 shows x 209-1463) and 3:4
# tablets to 9:20 phones (portrait x 166-858).
SLOTS = 18
PERCHES = {
    'landscape': dict(
        lines=dict(upper=[[200, 285], [325, 294], [450, 303], [550, 295], [640, 298]],
                   lower=[[230, 470], [475, 463], [600, 467], [750, 470], [790, 476]]),
        rows=[dict(on='upper', count=4, height=92, feet=-6, range=[222, 610]),
              dict(on='upper', count=4, height=84, feet=40, range=[240, 600], front=True),
              dict(on='lower', count=5, height=100, feet=-6, range=[250, 772]),
              dict(on='lower', count=5, height=92, feet=44, range=[270, 760], front=True)]),
    'portrait': dict(
        lines=dict(crown=[[160, 487], [250, 490], [300, 492], [350, 496], [400, 501]],
                   branch=[[160, 700], [200, 705], [300, 716], [400, 724], [500, 734]]),
        rows=[dict(on='crown', count=4, height=72, feet=-4, range=[172, 396]),
              dict(on='crown', count=4, height=66, feet=30, range=[178, 390], front=True),
              dict(on='branch', count=5, height=80, feet=-4, range=[176, 498]),
              dict(on='branch', count=5, height=74, feet=34, range=[180, 494], front=True)]),
}
# The Campus plank's v2 top and how far v3 moves it (rerunnable: the drop is
# measured from the v2 top, not from whatever the manifest holds now).
PLANK_TOP = {'landscape': 614, 'portrait': 1143}
PLANK_DROP = {'landscape': 76, 'portrait': 0}
BANDS = 28
ALPHA_FLOOR = 8


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def cutout(source):
    """A transparent master with stray haze removed, cropped to its subject."""
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
    return cropped


def limb_top(line, x):
    """A limb's top edge at X, interpolated along its measured polyline."""
    for (x0, y0), (x1, y1) in zip(line, line[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    raise SystemExit(f'x {x} is off the measured limb {line[0][0]}-{line[-1][0]}')


def perches(spec):
    """The empty perch slots as (center x, feet y, height, in front): a row's
    slots share its height and sit evenly across its x range on its limb."""
    slots = []
    for row in spec['rows']:
        left, right = row['range']
        step = (right - left) / row['count']
        for index in range(row['count']):
            center = left + step * (index + 0.5)
            feet = round(limb_top(spec['lines'][row['on']], center) + row['feet'])
            slots.append((round(center), feet, row['height'], row.get('front', False)))
    return slots


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


def house_cutout():
    """The bird house cut from its generated picture. The background remover
    also cleared the dark entrance hole; enclosed holes that were not the
    picture's white background (the rope loop's) take back their pixels."""
    with Image.open(LOCAL/HOUSE_SOURCE) as original:
        painted = original.convert('RGBA')
    with Image.open(LOCAL/HOUSE_MASTER) as cut:
        picture = cut.convert('RGBA')
    clear = np.asarray(picture.getchannel('A')) < ALPHA_FLOOR
    holes, count = ndimage.label(clear)
    outside = set(np.unique(np.concatenate([holes[0], holes[-1], holes[:, 0], holes[:, -1]])))
    white = np.asarray(painted.convert('L')) > 235
    alpha = np.asarray(picture.getchannel('A')).copy()
    pixels = np.asarray(picture).copy()
    for label in range(1, count + 1):
        hole = holes == label
        if label in outside or white[hole].mean() > 0.5:
            continue
        pixels[hole] = np.asarray(painted)[hole]
        alpha[hole] = 255
    pixels[..., 3] = alpha
    master = LOCAL/'runtime-exports'/'desert-bird-house-master.png'
    Image.fromarray(pixels, 'RGBA').save(master)
    return cutout(master)


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
    receipts, rows = [], {}
    house = house_cutout()
    raw = scratch/f'desert-{HOUSE}.png'
    house.save(raw)
    glow = Image.new('RGBA', house.size, (255, 249, 222, 0))
    glow.putalpha(house.getchannel('A'))
    light = scratch/f'desert-{HOUSE}-glow.png'
    glow.save(light)
    rest, highlight = OBJECTS+f'desert-{HOUSE}.avif', OBJECTS+f'desert-{HOUSE}-glow.avif'
    rows[rest] = ship_scaled(raw, ROOT/rest)
    rows[highlight] = ship_scaled(light, ROOT/highlight)
    receipts.append(dict(layer=HOUSE, generated=str((LOCAL/HOUSE_SOURCE).relative_to(ROOT)),
                         generated_sha256=digest(LOCAL/HOUSE_SOURCE), master=str(raw.relative_to(ROOT)),
                         master_sha256=digest(raw), runtime=rest, sha256=digest(ROOT/rest), glow=highlight,
                         glow_sha256=digest(ROOT/highlight), size=list(house.size)))
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
        if len(perches(PERCHES[orientation])) != SLOTS:
            raise SystemExit(f'{orientation}: the branches need exactly {SLOTS} perch slots')
        (x, y), width = HANGS[orientation]['hang'], HANGS[orientation]['width']
        height = round(house.height * width / house.width)
        rect = [x - width // 2, y, width, height]
        hotspots.append(dict(id=f'desert-{HOUSE}', target=DIALOGUE, glow_rect=rect, rest=rest, glow=highlight,
                             polygon=outline(house.getchannel('A'), rect[0], rect[1], width / house.width)))
        master = LOCAL/f'desert-{orientation}-plate.png'
        plate.save(master)
        rows[view['image']] = ship_scaled(master, ROOT/view['image'])
        rows[view['low']] = export_low_master(master, ROOT/view['low'])
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
    # The earlier camel, guide and perched birds; the birds return later from the bird house.
    gone = ('camel', 'guide', 'macaw', 'blue-parrot', 'green-parakeet', 'cockatiel', 'lovebird', 'pink-parrot',
            'budgie', 'finch', 'parrotlet', 'rosella', 'sky-chick', 'macaw-chick')
    retired = [OBJECTS+f'desert-{old}{kind}.avif' for old in gone for kind in ('', '-glow')]
    for name in retired:
        (ROOT/name).unlink(missing_ok=True)
    record(rows, retired)
    PROVENANCE.write_text(json.dumps(dict(
        owner_request='The desert must be like in the map, so white and with the oasis; no camel or person but a '
                      'big branch of colorful, unique parrots; each bird must be its own asset, not in the scene '
                      'directly (owner, 2026-11-05). It should be a giant tree on the side with a branch, not '
                      'straight the full width, just half; add a bird house on the tree, at start there should '
                      'be no birds but a clear section of 2 branches where we put a total of 18 birds that we will '
                      'fill in from the magic bird house (owner, 2026-11-06).',
        generator='Harmony generate_image (Codex built-in image generation); original Jungle watercolor',
        style_reference='the world map Desert (white dunes, turquoise lagoons, palm clumps) and the Campus '
                        'title painting; the owner\'s bird screenshot only as a mood guide',
        method='The landscape v5 plate repaints the white-sand lagoon oasis with a giant tree at the left and '
               'two clear mossy branches; the portrait v4 plate has the crown limb and a lower branch; no bird is '
               'painted. The bird house is cut from its own generated picture (BiRefNet, entrance hole restored) '
               'and hangs under the lower branch as a separate layer; PERCHES lays out the 18 empty perch slots '
               'along the measured limb lines. The Campus plank keeps its board.',
        assets=receipts), indent=2) + '\n')
    print('Integrated the Wüste scene; run python3 tools/title_scenes.py next')


if __name__ == '__main__':
    main()

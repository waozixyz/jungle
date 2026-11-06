#!/usr/bin/env python3
"""Owner fixes of 2026-11-05 for Campus, the Jungle Path and the window view.

- The Hide & Seek tail leaves Campus's triceratops corner and peeks out of a
  bush beside the Jungle Path: the plate's own leaves are a cut-out drawn in
  front of the tail's base (`--tail`).
- The Treehouse window's top-left leaves are a still layer above the birds
  and butterflies (`--leaves`).
- The window twig is one full-size picture that sways in code about its join
  with the trunk (`--twig`); the portrait join is regenerated.
- Portrait Campus fills portrait windows: its painting widens by INSET pixels
  on each side, each join regenerated only around its seam and merged with
  harness merge-map-gap; every placement moves with it, and its "safe" rect
  keeps the original painting whole on phones (`--campus`). Its distant
  desert is white with an oasis, like the world map, and so is landscape
  Campus's, whose desert crop alone is regenerated and feathered back in
  (`--desert`).

Masters stay in ignored local/art-development/; this explicit authoring
command exports the runtime AVIFs. Normal builds never run it.

    python3 tools/title_campus_fixes.py --tail --leaves --twig --campus --desert
    python3 tools/title_scenes.py && python3 tools/title_animations.py
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from avif_codec import SPEED, save_avif
from image_exports import export_scaled_master, record_canonical_rows
from title_desert import outline
from title_glow import glow

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT/'local/art-development'
WORK = LOCAL/'campus-fix'
MANIFEST = ROOT/'tools/title_hotspots.json'
ANIMATIONS = ROOT/'tools/title_animations.json'
PROVENANCE = ROOT/'tools/art_provenance/campus-fixes-2026-11-05.json'
APPROVED = ROOT/'tests/approved_title_avif.json'
TITLE = 'assets/jungle/title/'
WINDOW = TITLE+'window-animation/'
TAIL_IMAGE = TITLE+'objects/portrait-hiding-tail.avif'

# The tail stands behind a leafy bush at the path's edge: beside the bridge
# in landscape, at the path's bend under the parrot in portrait. Each cover
# polygon bounds the bush leaves (green clearly above red) that hide its base.
TAIL = {'landscape': [528, 572, 72, 106], 'portrait': [552, 688, 80, 118]}
TAIL_COVER = {'landscape': ([(500, 645), (640, 645), (640, 730), (500, 730)], 25),
              'portrait': ([(520, 760), (680, 760), (680, 860), (520, 860)], 20)}
# The window's top-left branch and leaves, inside the opening, which birds and
# butterflies cross; distant hills and canopy stay outside these polygons.
LEAVES = {'portrait': [(0, 0), (640, 0), (640, 330), (330, 330), (200, 520), (140, 600), (0, 600)],
          'landscape': [(0, 0), (720, 0), (720, 225), (430, 225), (345, 330), (300, 372), (182, 372), (150, 420), (0, 420)]}
# Window twigs: rect, pivot (the attached end, a fraction of the rect).
TWIG_PIVOT = {'landscape': [0.0, 0.5], 'portrait': [1.0, 0.5]}
TWIG_RECT = {'landscape': (75, 329, 619, 324), 'portrait': (482, 664, 532, 247)}

INSET = 256
CAMPUS_WIDE = LOCAL/'campus-wide/campus-portrait-wide.png'
CAMPUS_DESERT = LOCAL/'campus-wide/campus-landscape-white-desert.png'
# Until the right strip is joined, portrait Campus keeps its 1024 px frame:
# the original with the left join's seam (the drums' grass trail gone).
CAMPUS_LEFT = LOCAL/'campus-wide/campus-portrait-left-joined.png'
CAMPUS_LEFT_JOIN = WORK/'join/campus-wide-left.png'
# The painted monstera bush where the tail used to peek out (original 1024 px
# coordinates; the wide painting shifts them by the left strip).
HIDING_BUSH = [(862, 1150), (905, 1128), (960, 1125), (1000, 1150), (1012, 1200), (1005, 1260),
               (985, 1310), (950, 1345), (905, 1345), (872, 1310), (858, 1250), (855, 1195)]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def ship_cutout(picture, master, name):
    """Save a transparent PICTURE as its private MASTER and ship NAME with its
    pixels kept (q70 4:4:4 color, exact alpha); returns its canonical row."""
    picture = picture.convert('RGBA')
    pixels = np.asarray(picture).copy()
    pixels[pixels[..., 3] == 0, :3] = 0
    picture = Image.fromarray(pixels)
    master.parent.mkdir(parents=True, exist_ok=True)
    picture.save(master)
    destination = ROOT/name
    save_avif(picture, destination, lossless=True)
    with Image.open(destination) as shipped:
        rgba = shipped.convert('RGBA')
        dimensions = list(shipped.size)
    assert rgba.getchannel('A').tobytes() == picture.getchannel('A').tobytes(), name
    source = master.relative_to(ROOT).as_posix()
    return dict(source=source, source_sha256=digest(master), source_bytes=master.stat().st_size,
                source_rgba_sha256=sha(picture.tobytes()), dimensions=dimensions, alpha=True,
                source_alpha_sha256=sha(picture.getchannel('A').tobytes()),
                alpha_sha256=sha(rgba.getchannel('A').tobytes()), rgba_sha256=sha(rgba.tobytes()),
                sha256=digest(destination), bytes=destination.stat().st_size, quality=70,
                lossless=False, subsampling='444', speed=SPEED, exact_alpha=True, alpha_quality=100)


def region(size, polygon):
    mask = Image.new('L', size)
    ImageDraw.Draw(mask).polygon([tuple(p) for p in polygon], fill=255)
    return np.asarray(mask) > 0


def soften(mask, grow=1):
    """Drop specks and pinholes, then feather the edge by under a pixel."""
    image = Image.fromarray((mask * 255).astype('uint8'))
    image = image.filter(ImageFilter.MaxFilter(1 + 2 * grow)).filter(ImageFilter.MinFilter(1 + 4 * grow))
    image = image.filter(ImageFilter.MaxFilter(1 + 2 * grow))
    return image.filter(ImageFilter.GaussianBlur(0.7))


def scene(data, name):
    return next(s for s in data['scenes'] if s['name'] == name)


def tail_hotspot(orientation):
    """The Hide & Seek tail, its silhouette outlined at its place."""
    x, y, w, h = TAIL[orientation]
    with Image.open(ROOT/TAIL_IMAGE) as tail:
        alpha = tail.convert('RGBA').getchannel('A').resize((w, h), Image.Resampling.LANCZOS)
    # A forgiving tap area for small fingers: the curl's silhouette, padded.
    pad = 12
    padded = Image.new('L', (w + 2*pad, h + 2*pad))
    padded.paste(alpha, (pad, pad))
    padded = padded.filter(ImageFilter.MaxFilter(2*pad + 1))
    return dict(id='peekaboo-trail', target='game:Hide & Seek', glow=TITLE+'objects/portrait-hiding-tail-glow.avif',
                glow_rect=[x, y, w, h], rest=TAIL_IMAGE, polygon=outline(padded, x - pad, y - pad, 1.0), occlusion=[])


def tail_bush(orientation):
    """The bush leaves in front of the tail's base, cut from the plate itself."""
    plate = Image.open(LOCAL/f'jungle-path/jungle-path-{orientation}.png').convert('RGBA')
    rgb = np.asarray(plate.convert('RGB')).astype(int)
    cover, threshold = TAIL_COVER[orientation]
    leaves = (rgb[..., 1] - rgb[..., 0] > threshold) & region(plate.size, cover)
    # Only where the tail and its glow can be: a few pixels around its rect.
    x, y, w, h = TAIL[orientation]
    near = np.zeros_like(leaves)
    near[max(0, y-6):y+h+6, max(0, x-6):x+w+6] = True
    alpha = soften(leaves & near)
    plate.putalpha(alpha)
    box = alpha.point(lambda v: 255 if v > 0 else 0).getbbox()
    name = TITLE+f'objects/jungle-path{"-portrait" if orientation == "portrait" else ""}-tail-bush.avif'
    row = ship_cutout(plate.crop(box), WORK/f'jungle-path-{orientation}-tail-bush.png', name)
    return dict(path=name, rect=[box[0], box[1], box[2]-box[0], box[3]-box[1]]), {name: row}


def tails(data, rows):
    for orientation in ('landscape', 'portrait'):
        base = scene(data, 'jungle-path')
        view = base if orientation == 'landscape' else base['portrait']
        view['hotspots'] = [h for h in view['hotspots'] if h['id'] != 'peekaboo-trail'] + [tail_hotspot(orientation)]
        decoration, row = tail_bush(orientation)
        view['decorations'] = [decoration]
        rows.update(row)


def window_layers(data):
    layers = json.loads(ANIMATIONS.read_text())['layers']
    base = scene(data, 'window')
    return layers, {'landscape': ('window', base), 'portrait': ('window-portrait', base['portrait'])}


def window_plate(orientation):
    return Image.open(LOCAL/f'treehouse-window-animation/sky-clouds-twig/{orientation}-final-background.png').convert('RGBA')


def top_left_leaves(orientation):
    """Branch and leaves inside the opening, minus sky and the frame above them."""
    plate = window_plate(orientation)
    rgb = np.asarray(plate.convert('RGB')).astype(int)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    sky = (b > r + 12) & (b + 8 >= g)
    # Pale, greyed distant hills are no foreground; leaves and bark are vivid.
    hsv = np.asarray(plate.convert('RGB').convert('HSV')).astype(int)
    sky |= (hsv[..., 1] < 72) & (hsv[..., 2] > 150)
    with Image.open(ROOT/(WINDOW+f'{orientation}-frame.avif')) as frame:
        framed = np.asarray(frame.convert('RGBA').getchannel('A')) > 250
    alpha = soften(~sky & ~framed & region(plate.size, LEAVES[orientation]))
    plate.putalpha(alpha)
    box = alpha.point(lambda v: 255 if v > 8 else 0).getbbox()
    return plate.crop(box), box


def leaves(data, rows):
    layers, scenes = window_layers(data)
    for orientation, (name, view) in scenes.items():
        picture, box = top_left_leaves(orientation)
        path = WINDOW+f'{orientation}-leaves-top-left.avif'
        rows[path] = ship_cutout(picture, WORK/f'window-{orientation}-leaves-top-left.png', path)
        layer = dict(scene=name, path=path, sheet=[1, 1, picture.width, picture.height],
                     rect=[box[0], box[1], picture.width, picture.height], timing=[1, 1, 0], mode=0)
        layers = [l for l in layers if l['path'] != path]
        last = max(i for i, l in enumerate(layers) if l['scene'] == name and l['mode'] == 0)
        layers.insert(last + 1, layer)
        if path not in view['animations']:
            view['animations'].append(path)
    ANIMATIONS.write_text(json.dumps({'layers': layers}, indent=2)+'\n')


def twig_picture(orientation):
    """The twig's still frame at painting size: the old atlas's first cell."""
    folder = LOCAL/'treehouse-window-animation/sky-clouds-twig'
    joined = WORK/f'{orientation}-twig-joined.png'
    if joined.is_file():
        return Image.open(joined).convert('RGBA')
    sheet = Image.open(folder/f'{orientation}-twig-master.png').convert('RGBA')
    return sheet.crop((0, 0, sheet.width // 24, sheet.height))


def twigs(data, rows):
    layers, _ = window_layers(data)
    for orientation in ('landscape', 'portrait'):
        layer = next(l for l in layers if l['path'] == WINDOW+f'{orientation}-twig.avif')
        picture = twig_picture(orientation)
        x, y, width, height = TWIG_RECT[orientation]
        assert picture.size == (width, height), (orientation, picture.size)
        # Trim to the painted twig: the portrait twig fades out before the
        # join, which then is its attached end (the pivot's x); the pivot's
        # height stays where the old twig met the trunk.
        box = picture.getchannel('A').getbbox()
        picture = picture.crop(box)
        rect = [x + box[0], y + box[1], picture.width, picture.height]
        attach_y = y + height*TWIG_PIVOT[orientation][1]
        pivot = [TWIG_PIVOT[orientation][0], round((attach_y - rect[1])/rect[3], 4)]
        rows[layer['path']] = ship_cutout(picture, WORK/f'window-{orientation}-twig.png', layer['path'])
        layer.update(rect=rect, sheet=[1, 1, picture.width, picture.height], timing=[1, 4, 0], pivot=pivot)
    ANIMATIONS.write_text(json.dumps({'layers': layers}, indent=2)+'\n')
    # The regenerated portrait join grows from the trunk in the still plate;
    # the swaying twig fades out just before it.
    plate = WORK/'window-portrait-twig-plate.png'
    if plate.is_file():
        path = scene(data, 'window')['portrait']['image']
        rows[path] = export_scaled_master(plate, ROOT/path)


def shift(points, dx):
    return [[x + dx, y] for x, y in points]


def widen_campus(data, rows):
    """Move portrait Campus's placements into its widened painting, once."""
    campus = scene(data, 'campus')
    view = campus['portrait']
    with Image.open(CAMPUS_WIDE) as wide:
        assert wide.mode == 'RGB' and wide.size == (1024 + 2*INSET, 1536), wide.size
    if view['width'] == 1024:
        for hotspot in view['hotspots']:
            hotspot['glow_rect'][0] += INSET
            for key in ('polygon', 'occlusion'):
                if hotspot.get(key):
                    hotspot[key] = shift(hotspot[key], INSET)
            if 'editor_legacy_rect' in hotspot:
                hotspot['editor_legacy_rect'][0] += INSET
        for item in view.get('decorations', []) + view.get('objects', []):
            item['rect'][0] += INSET
        view['paper'][0] += INSET
        view.update(width=1024 + 2*INSET, safe=[INSET, 0, 1024, 1536])
        widen_plan(INSET)
    hiding_bush(view, rows, INSET)
    for path in (view['image'], view['background']):
        rows[path] = export_scaled_master(CAMPUS_WIDE, ROOT/path)
    low = Image.open(CAMPUS_WIDE).resize((240, 240), Image.Resampling.LANCZOS)
    low_master = WORK/'campus-portrait-wide-low.png'
    low.save(low_master)
    save_avif(low, ROOT/view['low'], quality=35)
    rows[view['low']] = low_row(low_master, ROOT/view['low'])
    foreground(view, rows)


def campus_left(data, rows):
    """Portrait Campus in its 1024 px frame with the left join's seam: the
    drums' grass trail is gone and the bush hides the game without the tail."""
    view = scene(data, 'campus')['portrait']
    assert view['width'] == 1024, 'portrait Campus is already widened'
    with Image.open(CAMPUS_LEFT_JOIN) as joined:
        joined.convert('RGB').crop((INSET, 0, INSET + 1024, 1536)).save(CAMPUS_LEFT)
    widen_plan(0, CAMPUS_LEFT)
    hiding_bush(view, rows, 0)
    for path in (view['image'], view['background']):
        rows[path] = export_scaled_master(CAMPUS_LEFT, ROOT/path)
    low = Image.open(CAMPUS_LEFT).resize((240, 360), Image.Resampling.LANCZOS)
    low_master = WORK/'campus-portrait-left-low.png'
    low.save(low_master)
    save_avif(low, ROOT/view['low'], quality=35)
    rows[view['low']] = low_row(low_master, ROOT/view['low'])


def widen_plan(dx, plate=CAMPUS_WIDE):
    """The approved portrait mapping records every placement in the painting."""
    path = ROOT/'tools/art_provenance/campus-portrait-v3.json'
    plan = json.loads(path.read_text())
    plan.update(canvas=[1024 + 2*dx, 1536], plate=plate.name)
    plan['signs'] = {label: [x + dx, y, w, h] for label, (x, y, w, h) in plan['signs'].items()}
    # The tail went to the Jungle Path; Campus's bush itself hides the game.
    plan['objects'] = [o for o in plan['objects'] if o['file'] != 'hiding-tail.png']
    for obj in plan['objects']:
        obj['scene_rect'][0] += dx
    path.write_text(json.dumps(plan, indent=1)+'\n')
    canonical = ROOT/plan['source']
    if canonical.exists():
        mapping = json.loads(canonical.read_text())
        mapping['orientations']['portrait'] = {k: v for k, v in plan.items() if k not in ('source', 'directions')}
        canonical.write_text(json.dumps(mapping, indent=1)+'\n')


def hiding_bush(view, rows, dx):
    """Hide & Seek stays on Campus as the painted bush beside the triceratops,
    glowing like landscape's bush, without the tail."""
    bush = [[x + dx, y] for x, y in HIDING_BUSH]
    hotspot = next(h for h in view['hotspots'] if h['id'] == 'hiding-bush')
    hotspot.clear()
    hotspot.update(id='hiding-bush', target='game:Hide & Seek', polygon=bush,
                   glow=TITLE+'glow/campus-portrait-hiding-bush.avif')
    xs, ys = [p[0] for p in bush], [p[1] for p in bush]
    left, top = max(0, min(xs)-14), max(0, min(ys)-14)
    right, bottom = min(view['width'], max(xs)+15), min(view['height'], max(ys)+15)
    hotspot['glow_rect'] = [left, top, right-left, bottom-top]
    picture = glow(hotspot)
    master = WORK/'campus-portrait-hiding-bush-glow.png'
    picture.save(master)
    rows[hotspot['glow']] = ship_cutout(picture, master, hotspot['glow'])


def low_row(master, destination):
    with Image.open(master) as source, Image.open(destination) as shipped:
        picture, rgba = source.convert('RGBA'), shipped.convert('RGBA')
        dimensions = list(shipped.size)
    return dict(source=master.relative_to(ROOT).as_posix(), source_sha256=digest(master),
                source_bytes=master.stat().st_size, source_rgba_sha256=sha(picture.tobytes()),
                dimensions=dimensions, alpha=False, source_alpha_sha256=sha(picture.getchannel('A').tobytes()),
                alpha_sha256=sha(rgba.getchannel('A').tobytes()), rgba_sha256=sha(rgba.tobytes()),
                sha256=digest(destination), bytes=destination.stat().st_size, quality=35, lossless=False,
                subsampling='420', speed=SPEED, exact_alpha=False, alpha_quality=100)


def foreground(view, rows):
    """The tiger foreground layer, padded by the strips so it keeps its place."""
    master = WORK/'campus-portrait-foreground-wide.png'
    if not master.is_file():
        # The full-size layer the AVIF migration encoded, kept in ignored backup/.
        original = ROOT/'backup/avif-migration'/view['foreground'].replace('.avif', '.webp')
        with Image.open(original if original.is_file() else ROOT/view['foreground']) as old:
            layer = old.convert('RGBA').resize((1024, 1536), Image.Resampling.LANCZOS)
        wide = Image.new('RGBA', (1024 + 2*INSET, 1536))
        wide.paste(layer, (INSET, 0))
        wide.save(master)
    rows[view['foreground']] = export_scaled_master(master, ROOT/view['foreground'])


def white_desert(data, rows):
    """Landscape Campus with the white desert: image, background and low."""
    view = scene(data, 'campus')
    with Image.open(CAMPUS_DESERT) as plate:
        assert plate.mode == 'RGB' and plate.size == (1672, 941), plate.size
        low = plate.resize((240, 135), Image.Resampling.LANCZOS)
    for path in (view['image'], view['background']):
        rows[path] = export_scaled_master(CAMPUS_DESERT, ROOT/path)
    low_master = WORK/'campus-landscape-white-desert-low.png'
    low.save(low_master)
    save_avif(low, ROOT/view['low'], quality=35)
    rows[view['low']] = low_row(low_master, ROOT/view['low'])


def approve(rows):
    """Refresh tests/approved_title_avif.json for re-exported approved plates."""
    approved = json.loads(APPROVED.read_text())
    for row in approved['images']:
        if row['path'] not in rows:
            continue
        destination, source = ROOT/row['path'], ROOT/rows[row['path']]['source']
        canonical = rows[row['path']]
        with Image.open(destination) as im:
            row.update(bytes=destination.stat().st_size, sha256=digest(destination),
                       width=(canonical.get('design_dimensions') or canonical['dimensions'])[0],
                       height=(canonical.get('design_dimensions') or canonical['dimensions'])[1],
                       decoded_rgba_sha256=sha(im.convert('RGBA').tobytes()),
                       canonical_source=source.relative_to(ROOT).as_posix(),
                       canonical_bytes=source.stat().st_size, canonical_sha256=digest(source))
    approved['total_bytes'] = sum(r['bytes'] for r in approved['images'])
    APPROVED.write_text(json.dumps(approved, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    for flag in ('tail', 'leaves', 'twig', 'campus-left', 'campus', 'desert'):
        parser.add_argument('--'+flag, action='store_true')
    options = parser.parse_args()
    data = json.loads(MANIFEST.read_text())
    rows = {}
    if options.tail: tails(data, rows)
    if options.leaves: leaves(data, rows)
    if options.twig: twigs(data, rows)
    if options.campus_left: campus_left(data, rows)
    if options.campus: widen_campus(data, rows)
    if options.desert: white_desert(data, rows)
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    record_canonical_rows(rows)
    approve(rows)
    record = json.loads(PROVENANCE.read_text()) if PROVENANCE.exists() else {}
    record.update(owner_request='2026-11-05: portrait Campus extended on both sides; the weird tail moved out of '
                                'Campus into a well-placed Jungle Path bush; the window twig join improved; the '
                                "top-left leaves a layer above the birds; the drums' grass trail removed; "
                                'the desert seen from Campus white with an oasis like the world map.',
                  generator='Harmony generate_image (Codex built-in image generation); original Jungle watercolor',
                  method='Joins regenerate only a crop spanning each seam and merge with harness merge-map-gap '
                         '(registered without warping, best cut columns, brief feathering; source and outside '
                         'pixels preserved). Bush and leaf layers are the plates\' own pixels with color masks.')
    record.setdefault('assets', {}).update({name: dict(master=row['source'], master_sha256=row['source_sha256'],
                                                       sha256=row['sha256']) for name, row in rows.items()})
    PROVENANCE.write_text(json.dumps(record, indent=2)+'\n')
    print(f'title campus fixes: {len(rows)} AVIFs; run python3 tools/title_scenes.py && python3 tools/title_animations.py')


if __name__ == '__main__':
    main()

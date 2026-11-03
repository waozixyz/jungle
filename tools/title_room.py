#!/usr/bin/env python3
"""Build the Treehouse room from its ignored masters: a clean room plate,
separate object layers on top and the view out of the round window.

Masters live in local/art-development/treehouse-room/ (never tracked):
  source-<orientation>-background.png  the approved room without the tiger
  gen-<orientation>-clean.png          the generated empty room plate
  gen-<orientation>-<group>.png        generated full-canvas RGBA extractions
  gen-<orientation>-window.png         the generated view out of the window
Each object keeps the approved painting's own pixels inside its generated
silhouette; generated pixels fill only what other objects used to hide, so
every layer is complete and can move. Runtime files are WebP: opaque plates
q50/method 6 and exact lossless cut-outs and glows.

    python3 tools/title_room.py           export every runtime picture
    python3 tools/title_room.py --place   also place the objects and their
                                          hotspots at their painted positions

After that, tools/title_hotspots.json owns the room: add, move or swap an
entry in a scene's "objects" (drawn in list order), then run
python3 tools/title_scenes.py; hotspots with "object" follow their layer.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage
from scipy.spatial import ConvexHull

sys.path.insert(0, str(Path(__file__).resolve().parent))
from image_exports import export_image  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MASTERS = ROOT / 'local/art-development/treehouse-room'
ROOM = 'assets/jungle/title/room'
SOURCE = ROOT / 'tools/title_hotspots.json'
APPROVED = ROOT / 'tests/approved_title_webp.json'
# Transparent margin around every cut-out, so its hover glow fits its rect.
PAD = 24
LOW_WIDTH = 240
# The approved painting stays outside the objects' footprints, grown by this
# many pixels to cover their painted edges and contact shadows.
FOOTPRINT = 14
VERBOSE = False
# The removed hanging picture board above the landscape ladder, with its ropes.
REMOVED = {'landscape': [(1380, 0), (1605, 0), (1605, 80), (1668, 80), (1668, 535), (1235, 565),
                         (1235, 400), (1265, 380), (1265, 80), (1380, 80)]}

# Paint order, back to front: id, extraction group, the object's rough box
# in the approved painting (x0, y0, x1, y1) and the hotspot it carries.
OBJECTS = {
    'landscape': [
        ('plant-window', 'l4', (640, 370, 850, 560), None),
        ('bookshelf', 'l1', (60, 0, 455, 560), 'bookshelf'),
        ('plant-shelf', 'l4', (300, 470, 440, 550), None),
        ('easel', 'l1', (955, 250, 1265, 605), 'easel'),
        ('crayons', 'l3', (865, 450, 1100, 640), None),
        ('ladder', 'l1', (1375, 470, 1620, 770), 'ladder'),
        ('rug', 'l2', (275, 585, 945, 750), None),
        ('toy-basket', 'l2', (0, 425, 245, 665), None),
        ('shape-sorter', 'l3', (20, 655, 475, 895), 'shape-sorter'),
        ('cushion-left', 'l4', (385, 840, 665, 941), None),
        ('cushion-right', 'l1', (1140, 780, 1370, 900), None),
        ('puzzle-table', 'l3', (560, 670, 1200, 941), 'puzzle-table'),
        ('plant-corner-right', 'l4', (1470, 750, 1672, 830), None),
        ('bean-bag', 'l2', (1465, 785, 1672, 941), None),
        ('plant-corner-left', 'l4', (0, 620, 235, 941), None),
    ],
    'portrait': [
        ('plant-window', 'p4', (560, 560, 690, 690), None),
        ('bookshelf', 'p1', (20, 60, 345, 700), 'bookshelf'),
        ('plant-shelf', 'p4', (220, 560, 305, 690), None),
        ('toy-basket', 'p3', (0, 570, 235, 810), None),
        ('plant-left', 'p4', (0, 760, 80, 860), None),
        ('crayons', 'p2', (665, 560, 760, 700), None),
        ('easel', 'p1', (745, 345, 1015, 760), 'easel'),
        ('rug', 'p2', (160, 770, 800, 970), None),
        ('shape-sorter', 'p3', (0, 890, 430, 1135), 'shape-sorter'),
        ('cushion-left', 'p1', (440, 1015, 665, 1150), None),
        ('puzzle-table', 'p3', (550, 840, 1020, 1205), 'puzzle-table'),
        ('cushion-right', 'p2', (890, 1060, 1024, 1200), None),
        ('ladder', 'p1', (775, 1170, 1015, 1480), 'ladder'),
        ('plant-corner-left', 'p4', (0, 960, 520, 1536), None),
    ],
}
# The round window frame in each clean plate: center x, y and radii.
WINDOW = {'landscape': (825, 192, 316, 262), 'portrait': (642, 282, 292, 284)}
STEMS = {'landscape': 'treehouse', 'portrait': 'treehouse-portrait'}
VIEWS = {'landscape': 'window', 'portrait': 'window-portrait'}


def load(path, mode):
    with Image.open(path) as image:
        return np.asarray(image.convert(mode)).astype(np.float32)


def register(layer, original):
    """The shift and scale that lay a generated object over its painted self:
    generations drift up to a few dozen pixels, so search coarse, then fine."""
    height, width = original.shape[:2]
    ys, xs = np.nonzero(layer[..., 3] > 250)
    pick = slice(None, None, max(1, len(ys) // 8000))
    ys, xs = ys[pick], xs[pick]
    cy, cx = ys.mean(), xs.mean()
    colors = layer[ys, xs, :3]

    def error(scale, dx, dy):
        py = np.rint(cy + scale * (ys - cy) + dy).astype(int)
        px = np.rint(cx + scale * (xs - cx) + dx).astype(int)
        ok = (py >= 0) & (py < height) & (px >= 0) & (px < width)
        return float(np.abs(original[py[ok], px[ok]] - colors[ok]).mean())

    _, bx, by = min((error(1, dx, dy), dx, dy) for dy in range(-48, 49, 4) for dx in range(-48, 49, 4))
    return min((error(scale, bx + dx, by + dy), scale, bx + dx, by + dy, cy, cx)
               for scale in (0.92, 0.94, 0.96, 0.98, 1, 1.02, 1.04, 1.06, 1.08)
               for dy in range(-4, 5) for dx in range(-4, 5))


def extract(group, box, original):
    """The object's generated alpha and colors, registered to the painting."""
    alpha = group[..., 3]
    x0, y0, x1, y1 = box
    labels, _ = ndimage.label(alpha > 24)
    core = labels[y0:y1, x0:x1]
    # Keep the pieces that mostly lie in the box; a neighbour the generation
    # also drew (the crayon cup beside the easel) belongs to its own layer.
    sizes = np.bincount(labels.ravel())
    found = [n for n in np.unique(core) if n and (core == n).sum() >= max(30, 0.3 * sizes[n])]
    if not found:
        raise SystemExit(f'title room: no extracted object inside {box}')
    keep = np.isin(labels, found)
    near = np.zeros_like(keep)
    near[max(0, y0 - 80):y1 + 80, max(0, x0 - 80):x1 + 80] = True
    layer = group.copy()
    # The extractions keep about 253 inside; real objects are fully opaque.
    layer[..., 3] = np.where(keep & near, np.clip((alpha - 8) * 255 / 236, 0, 255), 0)
    _, scale, dx, dy, cy, cx = register(layer, original)
    # Premultiplied resampling: generated colors under alpha zero never bleed.
    premultiplied = layer.copy()
    premultiplied[..., :3] *= layer[..., 3:] / 255
    offset = [cy - (cy + dy) / scale, cx - (cx + dx) / scale]
    moved = np.stack([ndimage.affine_transform(premultiplied[..., c], np.eye(2) / scale, offset=offset,
                                               order=1, mode='constant') for c in range(4)], axis=-1)
    a = moved[..., 3:]
    moved[..., :3] = np.where(a > 0, moved[..., :3] * 255 / np.maximum(a, 1e-3), 0)
    return moved.clip(0, 255), (scale, dx, dy)


def cutouts(orientation):
    """Every object as a full-canvas RGBA array, in paint order."""
    original = load(MASTERS / f'source-{orientation}-background.png', 'RGB')
    groups = {}
    layers = []
    for name, group, box, hotspot in OBJECTS[orientation]:
        if group not in groups:
            groups[group] = load(MASTERS / f'gen-{orientation}-{group}.png', 'RGBA')
        layer, fit = extract(groups[group], box, original)
        if VERBOSE:
            print(f'  {orientation} {name}: scale {fit[0]}, shift {fit[1]:+d} {fit[2]:+d}')
        layers.append([name, layer, hotspot])
    # Keep the approved painting wherever the object was actually visible and
    # matches; generated pixels show at soft edges, where a front object hid
    # it and wherever the generation drew the object a little differently.
    for index, (name, layer, _) in enumerate(layers):
        alpha = layer[..., 3]
        hidden = np.zeros(alpha.shape, bool)
        for _, front, _ in layers[index + 1:]:
            hidden |= front[..., 3] > 12
        hidden = ndimage.binary_dilation(hidden, iterations=2)
        agree = ndimage.gaussian_filter(np.abs(original - layer[..., :3]).mean(axis=2), 1.5) < 36
        visible = ndimage.binary_erosion(alpha >= 250, iterations=3) & ~hidden & agree
        weight = ndimage.gaussian_filter(visible.astype(np.float32), 1.2)[..., None]
        layer[..., :3] = original * weight + layer[..., :3] * (1 - weight)
        alpha = np.where(alpha < 10, 0, alpha)
        layer[..., 3] = alpha
        layer[alpha == 0, :3] = 0
    return original, layers


def plate(orientation, original, layers):
    """The empty room: the approved painting itself, except inside every
    object's footprint (and the removed picture board), where the generated
    empty room shows. Moving an object then reveals floor, not a ghost."""
    generated = load(MASTERS / f'gen-{orientation}-clean.png', 'RGB')
    # Each object's convex hull, so shadows between legs go with the object.
    shapes = Image.new('L', (original.shape[1], original.shape[0]))
    draw = ImageDraw.Draw(shapes)
    for _, layer, _ in layers:
        ys, xs = np.nonzero(layer[..., 3] > 12)
        points = np.column_stack([xs, ys])
        draw.polygon([tuple(points[i]) for i in ConvexHull(points).vertices], fill=255)
    footprint = ndimage.binary_dilation(np.asarray(shapes) > 0, iterations=FOOTPRINT)
    if orientation in REMOVED:
        board = Image.new('L', shapes.size)
        ImageDraw.Draw(board).polygon([tuple(p) for p in REMOVED[orientation]], fill=255)
        footprint |= np.asarray(board) > 0
    weight = ndimage.gaussian_filter(footprint.astype(np.float32), FOOTPRINT / 3)[..., None]
    room = original * (1 - weight) + generated * weight
    return Image.fromarray(np.rint(room).clip(0, 255).astype(np.uint8), 'RGB')


def crop(layer):
    """A padded cut-out and its rect inside the scene."""
    height, width = layer.shape[:2]
    ys, xs = np.nonzero(layer[..., 3] > 0)
    x0, y0 = max(0, xs.min() - PAD), max(0, ys.min() - PAD)
    x1, y1 = min(width, xs.max() + 1 + PAD), min(height, ys.max() + 1 + PAD)
    picture = Image.fromarray(np.rint(layer[y0:y1, x0:x1]).clip(0, 255).astype(np.uint8), 'RGBA')
    return picture, [int(x0), int(y0), int(x1 - x0), int(y1 - y0)]


def trace(mask):
    """The outer boundary of one filled component, clockwise, as (x, y)."""
    padded = np.pad(mask, 1)
    ys, xs = np.nonzero(padded)
    start = (ys[0], xs[0])
    # Moore neighbourhood, starting west of the first pixel in reading order.
    steps = [(0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1)]
    contour = [start]
    current, came = start, 0
    for _ in range(mask.size * 4):
        for turn in range(8):
            direction = (came + turn) % 8
            y, x = current[0] + steps[direction][0], current[1] + steps[direction][1]
            if padded[y, x]:
                current = (y, x)
                came = (direction + 5) % 8
                break
        else:
            break
        if current == start:
            break
        contour.append(current)
    return [(x - 1, y - 1) for y, x in contour]


def simplify(points, tolerance):
    """Douglas-Peucker on a closed outline."""
    def reduce(chain):
        if len(chain) < 3:
            return chain
        (ax, ay), (bx, by) = chain[0], chain[-1]
        dx, dy = bx - ax, by - ay
        length = max(1e-9, (dx * dx + dy * dy) ** 0.5)
        distances = [abs(dy * (x - ax) - dx * (y - ay)) / length for x, y in chain[1:-1]]
        far = int(np.argmax(distances)) + 1
        if distances[far - 1] <= tolerance:
            return [chain[0], chain[-1]]
        return reduce(chain[:far + 1])[:-1] + reduce(chain[far:])
    half = len(points) // 2
    return reduce(points[:half + 1])[:-1] + reduce(points[half:] + points[:1])[:-1]


def outline(alpha, rect, tolerance=2.5):
    """An even-odd hit polygon covering every solid piece of a cut-out.
    Separate pieces join through retraced zero-width bridges."""
    solid = ndimage.binary_closing(alpha > 96, iterations=5)
    solid = ndimage.binary_fill_holes(solid)
    labels, count = ndimage.label(solid)
    sizes = ndimage.sum(solid, labels, range(1, count + 1))
    pieces = [n + 1 for n, size in enumerate(sizes) if size >= max(60, 0.004 * sizes.sum())]
    rings = []
    for piece in sorted(pieces, key=lambda n: -sizes[n - 1]):
        ring = simplify(trace(labels == piece), tolerance)
        rings.append([[int(rect[0] + x), int(rect[1] + y)] for x, y in ring])
    polygon = list(rings[0]) + [rings[0][0]]
    for ring in rings[1:]:
        polygon += ring + [ring[0], rings[0][0]]
    return polygon


def glow_picture(alpha):
    """title_glow.glow's hover style (golden rim just outside the silhouette,
    soft inner lift), made from the cut-out's own alpha instead of a polygon."""
    mask = Image.fromarray(alpha.astype(np.uint8), 'L')
    interior = np.asarray(mask.filter(ImageFilter.GaussianBlur(0.7)), dtype=np.float32) / 255
    rim = mask.filter(ImageFilter.MaxFilter(7))
    near = np.asarray(rim.filter(ImageFilter.GaussianBlur(2.8)), dtype=np.float32) / 255
    far = np.asarray(mask.filter(ImageFilter.GaussianBlur(9)), dtype=np.float32) / 255
    outer = np.minimum(240, near * 255 + far * 100)
    value = outer * (1 - interior) + interior * 82
    rgba = np.zeros(alpha.shape + (4,), np.uint8)
    for channel, (outside, inside) in enumerate(zip((255, 213, 74), (255, 249, 222))):
        rgba[..., channel] = np.rint(outside * (1 - interior) + inside * interior).astype(np.uint8)
    rgba[..., 3] = np.rint(value).clip(0, 255).astype(np.uint8)
    rgba[rgba[..., 3] == 0, :3] = 0
    return Image.fromarray(rgba, 'RGBA')


def ellipse(cx, cy, rx, ry, width, height, count=56):
    points = []
    for n in range(count):
        angle = 2 * np.pi * n / count
        points.append([int(min(width - 1, max(0, round(cx + rx * np.cos(angle))))),
                       int(min(height - 1, max(0, round(cy + ry * np.sin(angle)))))])
    return [p for i, p in enumerate(points) if p != points[i - 1]]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(picture, master, destination, role, size=None):
    """Keep the full-size master privately and ship its WebP export."""
    master.parent.mkdir(parents=True, exist_ok=True)
    picture.save(master)
    (ROOT / destination).parent.mkdir(parents=True, exist_ok=True)
    export_image(master, ROOT / destination, role, size=size)
    return destination


def approve(rows, master, destination):
    """Fingerprint a replaced opaque title picture for canonical_webp_test."""
    path = ROOT / destination
    with Image.open(path) as image:
        row = dict(name=path.stem, path=destination, bytes=path.stat().st_size, sha256=digest(path),
                   width=image.width, height=image.height,
                   decoded_rgba_sha256=hashlib.sha256(image.convert('RGBA').tobytes()).hexdigest(),
                   canonical_source=str(master.relative_to(ROOT)), canonical_bytes=master.stat().st_size,
                   canonical_sha256=digest(master))
    rows[destination] = row


def build(orientation, approved):
    """Export one orientation; returns its placed objects and hotspots."""
    stem = STEMS[orientation]
    work = MASTERS / 'export'
    with Image.open(ROOT / f'assets/jungle/title/layers/{stem}-foreground.webp') as tiger:
        tiger = tiger.convert('RGBA')
    original, layers = cutouts(orientation)
    empty = plate(orientation, original, layers)
    if empty.size != tiger.size:
        raise SystemExit(f'title room: {orientation} plate must match the {tiger.size} scene')
    width, height = empty.size
    plate_master = work / f'{orientation}-plate.png'
    work.mkdir(parents=True, exist_ok=True)
    empty.save(plate_master)
    room = empty.convert('RGBA')
    placed, hotspots = [], {}
    for name, layer, hotspot in layers:
        picture, rect = crop(layer)
        image = f'{ROOM}/{orientation}-{name}.webp'
        save(picture, work / f'{orientation}-{name}.png', image, 'cutout')
        room.alpha_composite(picture, tuple(rect[:2]))
        placed.append({'id': name, 'image': image, 'rect': rect})
        if hotspot:
            alpha = np.asarray(picture.getchannel('A'))
            glow = f'{ROOM}/{orientation}-{name}-glow.webp'
            save(glow_picture(alpha), work / f'{orientation}-{name}-glow.png', glow, 'cutout')
            hotspots[hotspot] = {'object': name, 'polygon': outline(alpha, rect), 'glow': glow,
                                 'glow_rect': list(rect)}
    full = room.copy()
    full.alpha_composite(tiger)
    composite_master = work / f'{orientation}-composite.png'
    full.convert('RGB').save(composite_master)
    for destination, master, size in (
            (f'assets/jungle/title/layers/{stem}-background.webp', plate_master, None),
            (f'assets/jungle/title/{stem}.webp', composite_master, None),
            (f'assets/jungle/title/{stem}-low.webp', composite_master,
             (LOW_WIDTH, round(height * LOW_WIDTH / width)))):
        export_image(master, ROOT / destination, 'title-background', size=size)
        approve(approved, master, destination)
    # The window view, the same composition rules as every title scene.
    view_master = MASTERS / f'gen-{orientation}-window.png'
    with Image.open(view_master) as view:
        if view.size != (width, height):
            raise SystemExit(f'title room: {view_master.name} must be {width}x{height}')
    view = VIEWS[orientation]
    for destination, size in ((f'assets/jungle/title/{view}.webp', None),
                              (f'assets/jungle/title/{view}-low.webp',
                               (LOW_WIDTH, round(height * LOW_WIDTH / width)))):
        export_image(view_master, ROOT / destination, 'title-background', size=size)
        approve(approved, view_master, destination)
    # The window is part of the room itself; the tiger in front keeps its own taps.
    from title_glow import glow
    cx, cy, rx, ry = WINDOW[orientation]
    polygon = ellipse(cx, cy, rx, ry, width, height)
    x0, y0 = max(0, min(p[0] for p in polygon) - PAD), max(0, min(p[1] for p in polygon) - PAD)
    x1 = min(width, max(p[0] for p in polygon) + 1 + PAD)
    y1 = min(height, max(p[1] for p in polygon) + 1 + PAD)
    tiger_alpha = np.asarray(tiger.getchannel('A'))
    occlusion = outline(tiger_alpha, [0, 0, width, height], tolerance=3.0)
    window = {'id': 'window', 'target': 'scene:window', 'polygon': polygon,
              'glow': f'assets/jungle/title/glow/{stem}-window.webp',
              'glow_rect': [int(x0), int(y0), int(x1 - x0), int(y1 - y0)], 'occlusion': occlusion}
    picture = glow(window)
    master = work / f'{stem}-window-glow.png'
    picture.save(master)
    export_image(master, ROOT / window['glow'], 'cutout')
    hotspots['window'] = window
    full.convert('RGB').save(work / f'{orientation}-preview.png')
    return placed, hotspots


def place(data, orientation, placed, hotspots):
    """Write the painted positions and object-following hotspots."""
    base = next(s for s in data['scenes'] if s['name'] == 'treehouse')
    scene = base if orientation == 'landscape' else base['portrait']
    scene['objects'] = placed
    kept, replaced = [], []
    for hotspot in scene['hotspots']:
        new = hotspots.get(hotspot['id'])
        if new is None:
            kept.append(hotspot)
            continue
        if hotspot['glow'] != new['glow']:
            replaced.append(hotspot['glow'])
        hotspot = {key: value for key, value in hotspot.items()
                   if key not in ('object', 'polygon', 'glow', 'glow_rect', 'occlusion')}
        for key in ('object', 'polygon', 'glow', 'glow_rect', 'occlusion'):
            if key in new:
                hotspot[key] = new[key]
        kept.append(hotspot)
    if not any(h['id'] == 'window' for h in kept):
        kept.append(hotspots['window'])
    scene['hotspots'] = kept
    if not any(s['name'] == 'window' for s in data['scenes']):
        data['scenes'].append({
            'name': 'window', 'image': 'assets/jungle/title/window.webp',
            'low': 'assets/jungle/title/window-low.webp', 'back': True, 'hotspots': [],
            'portrait': {'width': 1024, 'height': 1536,
                         'image': 'assets/jungle/title/window-portrait.webp',
                         'low': 'assets/jungle/title/window-portrait-low.webp', 'hotspots': []}})
    return replaced


def retire(paths):
    """Delete glows the object layers replaced and retire their ledger rows."""
    ledger_path = ROOT / 'tools/title_webp_layers.json'
    ledger = json.loads(ledger_path.read_text())
    for name, row in ledger.items():
        if row.get('path') in paths:
            ledger[name] = {'original_sha256': row['original_sha256'], 'retired': True}
    ledger_path.write_text(json.dumps(ledger, indent=2) + '\n')
    for path in paths:
        (ROOT / path).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--place', action='store_true',
                        help='write object rects and hotspots at their painted positions')
    arguments = parser.parse_args()
    receipt = json.loads(APPROVED.read_text())
    approved = {row['path']: row for row in receipt['images']}
    data = json.loads(SOURCE.read_text())
    replaced = []
    for orientation in ('landscape', 'portrait'):
        placed, hotspots = build(orientation, approved)
        if arguments.place:
            replaced += place(data, orientation, placed, hotspots)
        print(f'title room: {orientation} plate, {len(placed)} objects and the window view exported')
    receipt['images'] = list(approved.values())
    receipt['total_bytes'] = sum(row['bytes'] for row in receipt['images'])
    APPROVED.write_text(json.dumps(receipt, indent=2) + '\n')
    if arguments.place:
        SOURCE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
        retire(replaced)
        print('title room: placed objects in tools/title_hotspots.json; run python3 tools/title_scenes.py')


if __name__ == '__main__':
    main()

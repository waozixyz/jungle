#!/usr/bin/env python3
"""Farm entrance fields: whole-bed hover glows and the soil crops stand in.

The owner (2026-11-03): the crop fields carry no labels; hovering a field
lights the whole field; the crops sit inside the soil in every orientation.
Each raised bed is found in the entrance painting itself: its dark soil, and
the bamboo frame around it. The frame's outline becomes a lossless golden glow
(assets/garden/art/field-<orientation>-<bed>.webp) and a hover polygon; the
soil's four corners become the quad crops are placed in, in perspective.

    python3 tools/farm_fields.py           write the glows and the data file
    python3 tools/farm_fields.py --check   fail when either is out of date
"""
import argparse
import hashlib
import io
import sys
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.spatial import ConvexHull
from title_glow import glow

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'games/garden/garden_fields.zi'
ORIENTATIONS = ('landscape', 'portrait')
# Crops stand this far inside the soil's painted edge, as a share of the bed.
INSET = 0.07


def masks(picture):
    """The four beds' (soil, whole bed) masks: back-left, back-right, front-left, front-right."""
    rgb = np.asarray(picture.convert('RGB')).astype(np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    top, bottom = rgb.max(2), rgb.min(2)
    spread = np.maximum(top-bottom, 1e-6)
    hue = np.where(top == r, ((g-b)/spread) % 6, np.where(top == g, (b-r)/spread+2, (r-g)/spread+4))/6
    saturation = np.where(top > 0, (top-bottom)/np.maximum(top, 1e-6), 0)
    soil = (r < 175) & (r > g+25) & (g > b-5) & (r+g+b < 380)
    soil = ndimage.binary_closing(ndimage.binary_opening(soil, iterations=2), iterations=6)
    bamboo = (hue > 0.055) & (hue < 0.135) & (saturation >= 0.58) & (top >= 115)
    labels, count = ndimage.label(soil)
    found = []
    for index in range(1, count+1):
        ys, xs = np.nonzero(labels == index)
        # The shed's dark wood is higher up; beds are wide, filled soil.
        if ys.min() < picture.height//4 or len(xs) < 8000:
            continue
        found.append((len(xs), index))
    beds = []
    for _, index in sorted(found, reverse=True)[:4]:
        bed_soil = ndimage.binary_fill_holes(labels == index)
        # The frame rises a little above the soil's back edge and its front
        # wall falls well below the front edge, column by column.
        bound = np.zeros_like(bed_soil)
        for x in np.nonzero(bed_soil.any(0))[0]:
            rows = np.nonzero(bed_soil[:, x])[0]
            bound[max(0, rows.min()-28):rows.max()+130, x] = True
        bound = ndimage.maximum_filter1d(bound, 73, axis=1)
        material = ndimage.binary_closing((bamboo | bed_soil) & bound, iterations=3)
        parts, _ = ndimage.label(material)
        whole = np.isin(parts, np.unique(parts[bed_soil & material]))
        whole = ndimage.binary_opening(ndimage.binary_fill_holes(whole), iterations=3)
        parts, part_count = ndimage.label(whole)
        sizes = ndimage.sum(whole, parts, range(1, part_count+1))
        beds.append((bed_soil, parts == int(np.argmax(sizes))+1))
    if len(beds) != 4:
        raise SystemExit(f'farm fields: found {len(beds)} beds, not 4')
    beds.sort(key=lambda bed: np.nonzero(bed[0])[0].mean())
    back, front = sorted(beds[:2], key=lambda bed: np.nonzero(bed[0])[1].mean()), \
        sorted(beds[2:], key=lambda bed: np.nonzero(bed[0])[1].mean())
    return back + front


def hull(mask, size):
    """The bed's convex outline, simplified to the points that shape it."""
    ys, xs = np.nonzero(mask)
    points = np.column_stack([xs, ys]).astype(float)
    shape = ConvexHull(points)
    outline = [tuple(points[i]) for i in shape.vertices]
    # Drop points whose triangle is under 40 px^2, one at a time.
    while len(outline) > 12:
        areas = []
        for i, (x, y) in enumerate(outline):
            (ax, ay), (bx, by) = outline[i-1], outline[(i+1) % len(outline)]
            areas.append(abs((ax-x)*(by-y)-(bx-x)*(ay-y))/2)
        i = int(np.argmin(areas))
        if areas[i] >= 40:
            break
        outline.pop(i)
    width, height = size
    return [[min(max(0, round(x)), width-1), min(max(0, round(y)), height-1)] for x, y in outline]


def soil_quad(mask):
    """Back-left, back-right, front-right, front-left soil corners, inset.

    The beds are painted turned, three-quarter on: the back edge runs from the
    soil's topmost point to its rightmost, the front edge from its leftmost
    to its bottommost. Each corner is the middle of the soil's few most
    extreme pixels there, on the rounded corner."""
    ys, xs = np.nonzero(mask)

    def corner(along, across, smallest):
        edge = along.min() if smallest else along.max()
        return across[np.abs(along-edge) <= 3].mean(), edge
    top_x, top_y = corner(ys, xs, True)
    right_y, right_x = corner(xs, ys, False)
    bottom_x, bottom_y = corner(ys, xs, False)
    left_y, left_x = corner(xs, ys, True)
    quad = np.array([[top_x, top_y], [right_x, right_y], [bottom_x, bottom_y], [left_x, left_y]])
    centre = quad.mean(0)
    return [[round(v) for v in centre+(point-centre)*(1-2*INSET)] for point in quad]


def build():
    """(generated Ziran text, {glow path: lossless WebP bytes})."""
    first, count, xs, ys, rects, soil_x, soil_y, glows = [], [], [], [], [], [], [], {}
    for orientation in ORIENTATIONS:
        with Image.open(ROOT/f'assets/garden/art/scene-{orientation}.webp') as picture:
            size = picture.size
            beds = masks(picture)
        for bed, (soil, whole) in enumerate(beds):
            polygon = hull(whole, size)
            left, top = max(0, min(p[0] for p in polygon)-14), max(0, min(p[1] for p in polygon)-14)
            right = min(size[0], max(p[0] for p in polygon)+15)
            bottom = min(size[1], max(p[1] for p in polygon)+15)
            rect = [left, top, right-left, bottom-top]
            stream = io.BytesIO()
            glow(dict(polygon=polygon, glow_rect=rect)).save(stream, 'WEBP', lossless=True, exact=True, method=6)
            glows[f'assets/garden/art/field-{orientation}-{bed}.webp'] = stream.getvalue()
            first.append(len(xs)); count.append(len(polygon))
            xs += [p[0] for p in polygon]; ys += [p[1] for p in polygon]
            rects += rect
            for x, y in soil_quad(soil):
                soil_x.append(x); soil_y.append(y)
    numbers = lambda values: ', '.join(str(v) for v in values)
    lines = [
        '// Generated by tools/farm_fields.py from the Farm entrance paintings; do not edit.',
        '// Field F is bed (0 back-left, 1 back-right, 2 front-left, 3 front-right)',
        '// plus 4 in portrait. Every number is a painting pixel.',
        '// The whole bed, soil and bamboo frame: hover polygon and glow rectangle.',
        f'GARDEN_FIELD_FIRST: [8]s32 = .[{numbers(first)}];',
        f'GARDEN_FIELD_POINTS: [8]s32 = .[{numbers(count)}];',
        f'GARDEN_FIELD_X: [{len(xs)}]s32 = .[{numbers(xs)}];',
        f'GARDEN_FIELD_Y: [{len(ys)}]s32 = .[{numbers(ys)}];',
        f'GARDEN_FIELD_GLOW: [32]s32 = .[{numbers(rects)}];',
        '// The soil crops stand in: back-left, back-right, front-right, front-left.',
        f'GARDEN_SOIL_X: [32]s32 = .[{numbers(soil_x)}];',
        f'GARDEN_SOIL_Y: [32]s32 = .[{numbers(soil_y)}];',
    ]
    return '\n'.join(lines)+'\n', glows


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true', help='fail when the glows or data file are out of date')
    arguments = parser.parse_args()
    text, glows = build()
    stale = [str(OUTPUT.relative_to(ROOT))] if not OUTPUT.exists() or OUTPUT.read_text() != text else []
    stale += [path for path, data in glows.items() if not (ROOT/path).exists() or (ROOT/path).read_bytes() != data]
    if arguments.check:
        if stale:
            sys.exit('farm fields: out of date: '+', '.join(stale)+'; run python3 tools/farm_fields.py')
        print('farm fields: glows and data file are current')
        return
    OUTPUT.write_text(text)
    for path, data in glows.items():
        (ROOT/path).write_bytes(data)
    print(f'farm fields: wrote {OUTPUT.relative_to(ROOT)} and {len(glows)} lossless glows')
    for path, data in sorted(glows.items()):
        print(' ', path, len(data), hashlib.sha256(data).hexdigest()[:12])


if __name__ == '__main__':
    main()

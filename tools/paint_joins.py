#!/usr/bin/env python3
"""Close the gaps that let one coloring area flow into another.

Usage: python3 tools/paint_joins.py NAME ...   (art/paint/NAME.svg, e.g. scene15)

Traced line art often stops a few pixels short of the line it meets, so a
fill meant for the sky also paints the ground. A small gap is a place that
closing the lines with a disk would fill; it is a leak only when filling it
parts two areas that are both large, so open line ends inside one area, such
as grass strokes, stay as drawn. Wider openings are closed between the areas
tools/coloring_areas.json names: the roomiest way from one to the other is
cut where it is narrowest, until no way is left. Every leak gets one short
round line between the two lines it bridges, kept in the page's joins path.
tools/dino_art.py closes every traced tall page; this command closes an
existing page again, replacing the joins it had.
"""
import json
from pathlib import Path
import re
import sys

import numpy
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import breadth_first_order, minimum_spanning_tree

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'art/paint'
# Gaps up to twice this radius close; the painted lines are about five wide.
RADIUS = 12
WIDTH = 5
# Both areas a gap parts must hold this many pixels, about 1% of a page, so a
# thin strip along the border is never cut into pieces.
LARGE = 5000
FOUR = ndimage.generate_binary_structure(2, 1)


def _line(segment, size):
    image = Image.new('1', size)
    ImageDraw.Draw(image).line(segment, fill=1, width=WIDTH)
    x0, y0, x1, y1 = segment
    for x, y in ((x0, y0), (x1, y1)):
        r = WIDTH / 2
        ImageDraw.Draw(image).ellipse((x - r, y - r, x + r, y + r), fill=1)
    return numpy.asarray(image)


def _large_parts(ink):
    pieces, count = ndimage.label(~ink, FOUR)
    return int(numpy.count_nonzero(numpy.bincount(pieces.ravel())[1:] >= LARGE))


def _bridge(ink, gap):
    """The shortest line across gap between the two lines on either side."""
    edge = ndimage.binary_dilation(gap, iterations=2) & ink
    sides, count = ndimage.label(edge, numpy.ones((3, 3), bool))
    if count < 2:
        return None
    sizes = ndimage.sum_labels(edge, sides, range(1, count + 1))
    first, second = (numpy.argsort(sizes)[::-1][:2] + 1)
    a = numpy.argwhere(sides == first)
    b = numpy.argwhere(sides == second)
    # Few enough pixels for an exact search after thinning to every other one.
    a, b = a[::max(1, len(a) // 400)], b[::max(1, len(b) // 400)]
    distance = numpy.hypot(*(a[:, None, :] - b[None, :, :]).transpose(2, 0, 1))
    i, j = numpy.unravel_index(numpy.argmin(distance), distance.shape)
    (y0, x0), (y1, x1) = a[i], b[j]
    return int(x0), int(y0), int(x1), int(y1)


def joins(ink, radius=RADIUS):
    """Line segments (x0, y0, x1, y1) that close the leaks of a page's ink mask,
    across gaps up to twice radius wide."""
    ink = numpy.array(ink, bool)
    height, width = ink.shape
    # Only gaps between lines close here: a cloud or a treetop near the edge
    # leaves the sky open around it. Areas that end at the edge, such as
    # ground under a horizon, are parted by separate() from their named points.
    disk = numpy.hypot(*numpy.mgrid[-radius:radius + 1, -radius:radius + 1]) <= radius
    framed = numpy.pad(ink, radius + 1)
    closed = ndimage.binary_closing(framed, disk)[radius + 1:-radius - 1, radius + 1:-radius - 1]
    gaps, count = ndimage.label(closed & ~ink, FOUR)
    sides = ink.copy()
    found = []
    before = _large_parts(ink)
    for index in range(1, count + 1):
        gap = (gaps == index) & ~ink
        if not gap.any():
            continue
        segment = _bridge(sides, gap)
        if segment is None:
            continue
        closed = ink | _line(segment, (width, height))
        after = _large_parts(closed)
        if after > before:
            ink, before = closed, after
            sides |= closed
            found.append(segment)
    return found


def _widest_path_neck(ink, start, end):
    """The pixel where the roomiest way from start to end is narrowest.

    Paper pixels are joined along a maximum spanning tree of their room, the
    distance to the nearest line, so the tree's path between two points is the
    way that keeps the most room; its narrowest pixel is the gap to close.
    """
    height, width = ink.shape
    # The page border bounds the room like a line.
    room = ndimage.distance_transform_edt(numpy.pad(~ink, 1))[1:-1, 1:-1]
    index = numpy.arange(ink.size).reshape(ink.shape)
    rows, columns, weights = [], [], []
    for a, b in ((index[:, :-1], index[:, 1:]), (index[:-1, :], index[1:, :])):
        open_ = ~ink.ravel()[a.ravel()] & ~ink.ravel()[b.ravel()]
        rows.append(a.ravel()[open_])
        columns.append(b.ravel()[open_])
        # Spanning trees minimize, so the roomiest edges weigh least.
        weights.append(room.max() + 1 - numpy.minimum(room.ravel()[a.ravel()[open_]], room.ravel()[b.ravel()[open_]]))
    graph = csr_matrix((numpy.concatenate(weights), (numpy.concatenate(rows), numpy.concatenate(columns))),
                       shape=(ink.size, ink.size))
    tree = minimum_spanning_tree(graph)
    _, parent = breadth_first_order(tree, start[1] * width + start[0], directed=False)
    at, neck = end[1] * width + end[0], None
    while at >= 0:
        if neck is None or room.ravel()[at] < room.ravel()[neck]:
            neck = at
        at = parent[at]
    return divmod(int(neck), width)[::-1]


def _cut(ink, neck):
    """A line through the neck pixel between the lines on its two sides."""
    height, width = ink.shape
    x, y = neck
    walls = ink.copy()
    walls[0, :] = walls[-1, :] = walls[:, 0] = walls[:, -1] = True
    ys, xs = numpy.nonzero(walls)
    distance = numpy.hypot(xs - x, ys - y)
    if x in (0, width - 1) or y in (0, height - 1):
        # A gap at the border closes from the nearest line to the border.
        lines = numpy.flatnonzero(ink[ys, xs])
        first = lines[numpy.argmin(distance[lines])]
        return int(xs[first]), int(ys[first]), x, y
    first = numpy.argmin(distance)
    # The other side lies away from the first, more than a right angle round.
    facing = (xs - x) * (xs[first] - x) + (ys - y) * (ys[first] - y)
    across = numpy.flatnonzero(facing < -0.3 * distance * distance[first])
    second = across[numpy.argmin(distance[across])]
    return int(xs[first]), int(ys[first]), int(xs[second]), int(ys[second])


def separate(ink, seeds):
    """Line segments that part every pair of seed points, each across the
    narrowest gap still joining them."""
    ink = numpy.array(ink, bool)
    height, width = ink.shape
    for x, y in seeds:
        if ink[y, x]:
            raise ValueError(f'Seed {x},{y} is on a line, not in an area')
    found = []
    for at, start in enumerate(seeds):
        for end in seeds[at + 1:]:
            for _ in range(40):
                labels, _ = ndimage.label(~ink, FOUR)
                if not labels[start[1], start[0]] or not labels[end[1], end[0]]:
                    raise ValueError(f'A join covers seed {start} or {end}; move it into roomier paper')
                if labels[start[1], start[0]] != labels[end[1], end[0]]:
                    break
                segment = _cut(ink, _widest_path_neck(ink, start, end))
                ink |= _line(segment, (width, height))
                found.append(segment)
            else:
                raise ValueError(f'Could not part {start} from {end}')
    return found


def joins_path(segments):
    """An SVG stroke drawing segments, or an empty string."""
    if not segments:
        return ''
    data = ' '.join(f'M{x0} {y0}L{x1} {y1}' for x0, y0, x1, y1 in segments)
    return (f'<path id="joins" fill="none" stroke="#000" stroke-width="{WIDTH}" '
            f'stroke-linecap="round" d="{data}"/>\n')


def page_ink(svg, size):
    from paint_pages import render
    return numpy.asarray(render(svg, *size).convert('L')) < 128


def page_areas(name):
    """The named points of a page's areas that must stay apart, from tools/coloring_areas.json."""
    pages = json.loads((ROOT / 'tools/coloring_areas.json').read_text())['pages']
    return pages.get(name, {})


def close_page(name):
    """Close the leaks of art/paint/NAME.svg, replacing the joins it had."""
    path = ART / f'{name}.svg'
    svg = re.sub(r'<path id="joins"[^>]*/>\n', '', path.read_text())
    width, height = (int(v) for v in re.search(r'viewBox="0 0 (\d+) (\d+)"', svg).groups())
    ink = page_ink(svg, (width, height))
    segments = joins(ink)
    for segment in segments:
        ink |= _line(segment, (width, height))
    segments += separate(ink, list(page_areas(name).values()))
    path.write_text(svg.replace('</svg>', joins_path(segments) + '</svg>'))
    return segments


if __name__ == '__main__':
    for name in sys.argv[1:]:
        print(name, close_page(name))

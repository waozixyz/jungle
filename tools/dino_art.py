#!/usr/bin/env python3
"""Trace the generated coloring sheets into Dino Colors' vector artwork.

Usage: python3 tools/dino_art.py   (needs libpotrace, as in Inkscape's tracer)

Each dinosaur becomes art/paint/dinoN.svg: a white body path holding its
whole silhouette, under the black ink path of its lines, so a placed
dinosaur covers the scenery behind it. Each scene becomes
art/paint/sceneN.svg, black lines on white paper at 960 by 720. The SVGs
are the only source for every size tools/paint_pages.py makes.
"""
from collections import deque
import ctypes
import json
from pathlib import Path
import sys

import numpy
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'art/paint'
SCENE_SIZE = (960, 720)
# Tracing at a few times the sheet's pixels keeps curves smooth.
DINO_UPSCALE = 3
SCENE_UPSCALE = 2

potrace = ctypes.CDLL('libpotrace.so.0')
WORD = ctypes.c_ulong
WORD_BITS = ctypes.sizeof(WORD) * 8


class Progress(ctypes.Structure):
    _fields_ = [('callback', ctypes.c_void_p), ('data', ctypes.c_void_p),
                ('min', ctypes.c_double), ('max', ctypes.c_double), ('epsilon', ctypes.c_double)]


class Param(ctypes.Structure):
    _fields_ = [('turdsize', ctypes.c_int), ('turnpolicy', ctypes.c_int), ('alphamax', ctypes.c_double),
                ('opticurve', ctypes.c_int), ('opttolerance', ctypes.c_double), ('progress', Progress)]


class Bitmap(ctypes.Structure):
    _fields_ = [('w', ctypes.c_int), ('h', ctypes.c_int), ('dy', ctypes.c_int), ('map', ctypes.POINTER(WORD))]


class Point(ctypes.Structure):
    _fields_ = [('x', ctypes.c_double), ('y', ctypes.c_double)]


class Curve(ctypes.Structure):
    _fields_ = [('n', ctypes.c_int), ('tag', ctypes.POINTER(ctypes.c_int)), ('c', ctypes.POINTER(Point * 3))]


class Path_(ctypes.Structure):
    pass


Path_._fields_ = [('area', ctypes.c_int), ('sign', ctypes.c_int), ('curve', Curve),
                  ('next', ctypes.POINTER(Path_)), ('childlist', ctypes.POINTER(Path_)),
                  ('sibling', ctypes.POINTER(Path_)), ('priv', ctypes.c_void_p)]


class State(ctypes.Structure):
    _fields_ = [('status', ctypes.c_int), ('plist', ctypes.POINTER(Path_)), ('priv', ctypes.c_void_p)]


potrace.potrace_param_default.restype = ctypes.POINTER(Param)
potrace.potrace_trace.restype = ctypes.POINTER(State)
potrace.potrace_trace.argtypes = [ctypes.POINTER(Param), ctypes.POINTER(Bitmap)]
POTRACE_CURVETO = 1


def trace(mask, scale_x=1.0, scale_y=1.0):
    """Outline a 1-bit image's set pixels as even-odd SVG path data, y down."""
    width, height = mask.size
    dy = (width + WORD_BITS - 1) // WORD_BITS
    rows = numpy.zeros((height, dy * WORD_BITS), dtype=numpy.uint8)
    rows[:, :width] = numpy.asarray(mask.convert('L')) > 0
    # potrace keeps the leftmost pixel in a word's highest bit.
    packed = numpy.packbits(rows, axis=1)
    big = numpy.ascontiguousarray(packed).view(f'>u{WORD_BITS // 8}').reshape(height * dy)
    words = (WORD * (dy * height))(*big.astype(numpy.uint64).tolist())
    bitmap = Bitmap(width, height, dy, words)
    param = potrace.potrace_param_default()
    param.contents.turdsize = 6
    state = potrace.potrace_trace(param, ctypes.byref(bitmap))
    assert state and state.contents.status == 0, 'potrace failed'

    def at(point):
        return f'{point.x * scale_x:.1f} {point.y * scale_y:.1f}'

    data = []
    path = state.contents.plist
    while path:
        curve = path.contents.curve
        data.append('M' + at(curve.c[curve.n - 1][2]))
        for index in range(curve.n):
            segment = curve.c[index]
            if curve.tag[index] == POTRACE_CURVETO:
                data.append(f'C{at(segment[0])} {at(segment[1])} {at(segment[2])}')
            else:
                data.append(f'L{at(segment[1])} {at(segment[2])}')
        data.append('Z')
        path = path.contents.next
    potrace.potrace_state_free(state)
    potrace.potrace_param_free(param)
    return ''.join(data)


def components(image):
    """Connected dark strokes of more than 100 pixels: (size, box, points)."""
    ink = image.convert('L').point(lambda v: 255 if v < 160 else 0)
    pixels = ink.load()
    width, height = image.size
    seen = bytearray(width * height)
    result = []
    for y in range(height):
        for x in range(width):
            if seen[y * width + x] or not pixels[x, y]:
                continue
            seen[y * width + x] = 1
            queue = deque([(x, y)])
            points = []
            while queue:
                xx, yy = queue.popleft()
                points.append((xx, yy))
                for ny in range(max(0, yy - 1), min(height, yy + 2)):
                    for nx in range(max(0, xx - 1), min(width, xx + 2)):
                        if not seen[ny * width + nx] and pixels[nx, ny]:
                            seen[ny * width + nx] = 1
                            queue.append((nx, ny))
            if len(points) > 100:
                box = (min(p[0] for p in points), min(p[1] for p in points),
                       max(p[0] for p in points) + 1, max(p[1] for p in points) + 1)
                result.append((len(points), box, points))
    return result


def silhouette(outline):
    """Everything an outline encloses, outline included."""
    closed = outline.filter(ImageFilter.MaxFilter(7))
    outside = closed.point(lambda v: 0 if v else 255)
    ImageDraw.floodfill(outside, (0, 0), 128)
    body = outside.point(lambda v: 0 if v == 128 else 255)
    # Undo the gap-closing growth so the body ends at the outline's edge.
    return body.filter(ImageFilter.MinFilter(7))


def dinosaur(sheet, component):
    _, (left, top, right, bottom), points = component
    margin = 8
    box = (left - margin, top - margin, right + margin, bottom + margin)
    width, height = (box[2] - box[0]) * DINO_UPSCALE, (box[3] - box[1]) * DINO_UPSCALE
    gray = sheet.crop(box).resize((width, height), Image.Resampling.LANCZOS)
    ink = gray.point(lambda v: 255 if v < 150 else 0)
    outline = Image.new('L', (box[2] - box[0], box[3] - box[1]))
    for x, y in points:
        outline.putpixel((x - box[0], y - box[1]), 255)
    outline = outline.resize((width, height), Image.Resampling.NEAREST)
    # The sheet's single outline, smoothed at the traced size.
    outline = Image.composite(ink, outline, outline.filter(ImageFilter.MaxFilter(5)))
    body = silhouette(outline)
    # Eyes, teeth and inner lines are separate strokes inside the body;
    # strokes of neighboring cells stay outside it.
    lines = Image.composite(ink, Image.new('L', ink.size), body.filter(ImageFilter.MaxFilter(3)))
    return (width, height, trace(body.point(lambda v: 255 if v else 0, mode='1')),
            trace(lines.point(lambda v: 255 if v else 0, mode='1')))


def scene(sheet, index):
    row, column = divmod(index, 2)
    # The sheet draws cell borders up to 9 pixels inside each cell.
    inset = 12
    box = (round(column * sheet.width / 2) + inset, round(row * sheet.height / 3) + inset,
           round((column + 1) * sheet.width / 2) - inset, round((row + 1) * sheet.height / 3) - inset)
    width, height = (box[2] - box[0]) * SCENE_UPSCALE, (box[3] - box[1]) * SCENE_UPSCALE
    gray = sheet.crop(box).resize((width, height), Image.Resampling.LANCZOS)
    ink = gray.point(lambda v: 255 if v < 160 else 0, mode='1')
    # Each landscape fills the whole picture, as the earlier pages did.
    return trace(ink, SCENE_SIZE[0] / width, SCENE_SIZE[1] / height)


def standalone_stencils():
    """Trace each new stencil from its own generated image."""
    manifest = json.loads((ROOT / 'tools/coloring_stencils.json').read_text())
    for item in manifest['stencils']:
        index = item['index']
        source = ROOT / 'art/generated/coloring-stencils' / (item['name'] + '.png')
        with Image.open(source) as image:
            rgba = image.convert('RGBA')
            paper = Image.new('RGBA', rgba.size, 'white')
            paper.alpha_composite(rgba)
            ink = paper.convert('L').point(lambda value: 255 if value < 160 else 0)
        bounds = ink.getbbox()
        assert bounds, f'Empty stencil: {source}'
        ink = ink.crop(bounds)
        ink.thumbnail((960, 960), Image.Resampling.LANCZOS)
        margin = 12
        outline = Image.new('L', (ink.width + margin * 2, ink.height + margin * 2))
        outline.paste(ink, (margin, margin))
        body = silhouette(outline)
        width, height = outline.size
        body_path = trace(body.point(lambda value: 255 if value else 0, mode='1'))
        ink_path = trace(outline.point(lambda value: 255 if value >= 128 else 0, mode='1'))
        (OUT / f'dino{index}.svg').write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}">\n'
            f'<path id="body" fill="#fff" fill-rule="evenodd" d="{body_path}"/>\n'
            f'<g id="ink" fill="#000" fill-rule="evenodd">\n'
            f'<path d="{ink_path}"/>\n'
            f'<path d="{body_path}" fill="none" stroke="#000" stroke-width="10" '
            f'stroke-linejoin="round"/>\n</g>\n</svg>\n')
    print(f"Traced {len(manifest['stencils'])} individual animal, people and object stencils.")


def main():
    OUT.mkdir(exist_ok=True)
    if '--stencils-only' in sys.argv:
        standalone_stencils()
        return
    sheet = Image.open(ROOT / 'art/generated/dino-coloring-shapes.png').convert('L')
    found = components(sheet)
    for index in range(12):
        row, column = divmod(index, 4)
        candidates = [item for item in found if
                      column * sheet.width / 4 <= (item[1][0] + item[1][2]) / 2 < (column + 1) * sheet.width / 4 and
                      row * sheet.height / 4 <= (item[1][1] + item[1][3]) / 2 < (row + 1) * sheet.height / 4]
        assert candidates, f'Missing complete dinosaur {index + 1}'
        width, height, body, ink = dinosaur(sheet, max(candidates, key=lambda item: item[0]))
        (OUT / f'dino{index + 1}.svg').write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}">\n'
            f'<path id="body" fill="#fff" fill-rule="evenodd" d="{body}"/>\n'
            f'<path id="ink" fill="#000" fill-rule="evenodd" d="{ink}"/>\n</svg>\n')
    scenery = Image.open(ROOT / 'art/generated/dino-coloring-scenery.png').convert('L')
    width, height = SCENE_SIZE
    for index in range(6):
        (OUT / f'scene{index + 1}.svg').write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}">\n'
            f'<rect width="{width}" height="{height}" fill="#fff"/>\n'
            f'<path id="ink" fill="#000" fill-rule="evenodd" d="{scene(scenery, index)}"/>\n</svg>\n')
    standalone_stencils()
    print('Traced twelve dinosaurs and six scenes into art/paint.')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Compile art/paint/*.svg into the Coloring Book's runtime vector outlines.

Usage: python3 tools/paint_vectors.py [--check] [--out DIR] [--only NAME ...]
       (needs CairoSVG and libpotrace, as tools/dino_art.py does)

The SVGs mix filled paths, strokes, clips and <use> reinforcement. Each picture
is rendered large and traced once more, so a runtime file holds only filled
paths and every stroke and reinforcement stays in it. Its view box is the page
space the masks of tools/paint_pages.py use: 960 by 720 for a scene, the Huge
mask's width and height for a stencil.

A file follows Kryon's KVP1 format (src/ui/vector_path.zi): a scene has one ink
path; a stencil has its body path, then its ink path.
"""
import argparse
import io
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import cairosvg
from PIL import Image

from dino_art import trace
from paint_pages import CANVAS, SIZES, dinosaur, fit

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'art/paint'
OUT = ROOT / 'assets/dino-paint/vector'
# Tracing this many times the page's pixels keeps its curves within a fraction
# of a page pixel of the drawn art.
TRACE_SCALE = 4
UNITS = 16
TOKEN = re.compile(r'([MLCZ])|(-?\d+(?:\.\d+)?)')
COORDINATES = {'M': 2, 'L': 2, 'C': 6}
MAX_VECTOR_BYTES = 96 * 1024
MAX_SOURCE_BYTES = 512 * 1024


def varint(value):
    out = bytearray()
    while value >= 128:
        out.append(128 | (value & 127))
        value >>= 7
    out.append(value)
    return bytes(out)


def zigzag(value):
    return varint(value * 2 if value >= 0 else -value * 2 - 1)


def encode_path(data):
    """SVG path data of absolute M, L, C and Z as KVP1 commands."""
    if TOKEN.sub('', data).strip(' \t\r\n,'):
        raise ValueError('Expected absolute M, L, C and Z path commands')
    out = bytearray()
    previous = [0, 0]
    axis = 0
    current = ''
    written = 0
    for command, number in TOKEN.findall(data):
        if command:
            if current in COORDINATES and (not written or written % COORDINATES[current]):
                raise ValueError('Incomplete path coordinates')
            current = command
            written = 0
            out += command.encode()
            axis = 0
            continue
        # Path data may repeat L or M's coordinates without its letter.
        if current not in COORDINATES:
            raise ValueError('Coordinate without a path command')
        if written and written % COORDINATES[current] == 0:
            # SVG's additional moveto pairs are implicit lineto commands.
            if current == 'M':
                current = 'L'
            out += current.encode()
        value = round(float(number) * UNITS)
        out += zigzag(value - previous[axis])
        previous[axis] = value
        axis = 1 - axis
        written += 1
    if current in COORDINATES and (not written or written % COORDINATES[current]):
        raise ValueError('Incomplete path coordinates')
    return bytes(out)


def encode_file(width, height, paths):
    out = bytearray(b'KVP1') + varint(width * UNITS) + varint(height * UNITS) + varint(len(paths))
    for commands in paths:
        out += b'E' + varint(len(commands)) + commands
    return bytes(out)


def traced(svg, width, height, ink=False):
    """The alpha of svg, rendered TRACE_SCALE times width by height, traced in that page space."""
    data = cairosvg.svg2png(bytestring=svg.encode(), output_width=width * TRACE_SCALE,
                            output_height=height * TRACE_SCALE)
    rgba = Image.open(io.BytesIO(data)).convert('RGBA')
    if ink:
        # White scene shapes occlude lines behind them. Keep that composition,
        # then select black ink; alpha alone would turn those shapes solid black.
        paper = Image.new('RGBA', rgba.size, 'white')
        paper.alpha_composite(rgba)
        mask = paper.convert('L').point(lambda value: 255 if value < 128 else 0, mode='1')
    else:
        mask = rgba.getchannel('A').point(lambda value: 255 if value >= 128 else 0, mode='1')
    return trace(mask, 1.0 / TRACE_SCALE, 1.0 / TRACE_SCALE)


def compile_scene(index):
    svg = (ART / f'scene{index}.svg').read_text()
    return encode_file(*CANVAS, [encode_path(traced(svg, *CANVAS, ink=True))])


def compile_stencil(index):
    _, width, height, ink, body = dinosaur(index)
    w, h = fit(width, height, CANVAS[0], CANVAS[1])
    return encode_file(w, h, [encode_path(traced(body, w, h)), encode_path(traced(ink, w, h))])


def source_names():
    """Stable asset IDs; gaps must fail rather than silently omit an asset."""
    names = []
    for kind in ('scene', 'dino'):
        indices = sorted(int(path.stem[len(kind):]) for path in ART.glob(f'{kind}[0-9]*.svg'))
        if indices != list(range(1, len(indices) + 1)):
            raise ValueError(f'Non-contiguous {kind} asset IDs')
        names += [f'{kind}{index}' for index in indices]
    return names


def validate_source(path):
    """Masters contain geometry, never bitmap wrappers or external artwork."""
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError(f'Oversized vector source: {path}')
    root = ET.parse(path).getroot()
    if not any(node.tag.split('}')[-1] == 'path' for node in root.iter()):
        raise ValueError(f'Missing path geometry: {path}')
    for node in root.iter():
        if node.tag.split('}')[-1] in ('image', 'foreignObject'):
            raise ValueError(f'Raster/foreign content in vector source: {path}')
        for key, value in node.attrib.items():
            if key.split('}')[-1] == 'href' and not value.startswith('#'):
                raise ValueError(f'External content in vector source: {path}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=OUT)
    parser.add_argument('--only', nargs='*')
    parser.add_argument('--check', action='store_true', help='verify exact generated bytes without writes')
    args = parser.parse_args()
    if not args.check:
        args.out.mkdir(parents=True, exist_ok=True)
    total = 0
    names = source_names()
    if args.only and set(args.only) - set(names):
        parser.error(f'Unknown assets: {sorted(set(args.only) - set(names))}')
    assert SIZES == 4
    for name in names:
        if args.only and name not in args.only:
            continue
        index = int(re.search(r'\d+', name).group())
        validate_source(ART / f'{name}.svg')
        data = compile_scene(index) if name.startswith('scene') else compile_stencil(index)
        if len(data) > MAX_VECTOR_BYTES:
            raise ValueError(f'Oversized runtime vector: {name} ({len(data)} bytes)')
        target = args.out / f'{name}.kvp'
        if args.check:
            if not target.is_file() or target.read_bytes() != data:
                raise ValueError(f'Missing or stale runtime vector: {target}')
        else:
            target.write_bytes(data)
        total += len(data)
    if not args.only and {p.stem for p in args.out.glob('*.kvp')} != set(names):
        raise ValueError('Unexpected runtime vector assets')
    print(f'{"Verified" if args.check else "Wrote"} {total} bytes of vector outlines in {args.out}.')


if __name__ == '__main__':
    main()

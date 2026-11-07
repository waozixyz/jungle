#!/usr/bin/env python3
"""Compile the vector art in art/paint into Dino Colors' masks and pictures.

Usage: python3 tools/paint_pages.py   (needs CairoSVG)

Scenes become 960 by 720 line masks, and each scene's tall page
(art/paint/portraitN.svg) a 720 by 960 one. Each dinosaur becomes ink and body
masks in its four sizes, rendered from its SVG at that size so every size
keeps smooth lines. Masks are runs of paper and ink in the digits of
games/paint/paint_runs.zi, split into lines the compiler accepts. Picker
and placement previews are small smooth RGBA renderings. The full-size
outlines are KVP1 vectors compiled by tools/paint_vectors.py; do not ship full
raster copies, mirrored copies, or unused thumbnails.
"""
import hashlib
import io
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import cairosvg
import numpy
from avif_codec import QUALITY, SPEED, save_avif
from PIL import Image
from image_exports import export_painted_image, record_canonical_rows

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'art/paint'
ASSETS = ROOT / 'assets/dino-paint/art'
CANVAS = (960, 720)
TALL = (720, 960)
SIZES = 4
DIGITS = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_'
CHUNK = 4000


def render(svg, width, height):
    data = cairosvg.svg2png(bytestring=svg.encode(), output_width=width, output_height=height)
    return Image.open(io.BytesIO(data)).convert('RGBA')


def number(value):
    """Five bits a digit, lowest first; a digit of 32 or more continues."""
    text = ''
    while value >= 32:
        text += DIGITS[32 + (value & 31)]
        value >>= 5
    return text + DIGITS[value]


def runs(mask):
    """Alternating paper and ink run lengths, row after row, paper first."""
    flat = mask.reshape(-1)
    changes = numpy.flatnonzero(flat[1:] != flat[:-1]) + 1
    lengths = numpy.diff(numpy.concatenate(([0], changes, [flat.size])))
    if flat[0]:
        lengths = numpy.concatenate(([0], lengths))
    return ''.join(number(int(length)) for length in lengths)


def chunks(text):
    return [text[at:at + CHUNK] for at in range(0, len(text), CHUNK)]


def dinosaur(index):
    svg = (ART / f'dino{index}.svg').read_text()
    width, height = (float(v) for v in re.search(r'viewBox="0 0 (\S+) (\S+)"', svg).groups())
    nodes = {node.get('id'): node for node in ET.fromstring(svg).iter() if node.get('id')}
    head = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}">'

    def only(name):
        return head + ET.tostring(nodes[name], encoding='unicode') + '</svg>'

    return svg, width, height, only('ink'), only('body')


def scene_indices(kind):
    """One-based scene IDs of art/paint/<kind>N.svg, which must be contiguous."""
    indices = sorted(int(path.stem[len(kind):]) for path in ART.glob(f'{kind}[0-9]*.svg'))
    if indices != list(range(1, len(indices) + 1)):
        raise ValueError(f'Non-contiguous {kind} asset IDs')
    return indices


def thumbnail_row(source, picture, destination):
    """The tools/canonical_avif.json row of a thumbnail encoded from an SVG."""
    def sha(data):
        return hashlib.sha256(data).hexdigest()
    with Image.open(destination) as shipped:
        decoded = shipped.convert('RGBA')
    opaque = sha(decoded.getchannel('A').tobytes())
    return dict(source=source.relative_to(ROOT).as_posix(), source_sha256=sha(source.read_bytes()),
                source_bytes=source.stat().st_size, source_rgba_sha256=sha(picture.convert('RGBA').tobytes()),
                dimensions=list(decoded.size), alpha=False, source_alpha_sha256=opaque, alpha_sha256=opaque,
                rgba_sha256=sha(decoded.tobytes()), sha256=sha(destination.read_bytes()),
                bytes=destination.stat().st_size, quality=QUALITY, lossless=False, subsampling='420', speed=SPEED)


def fit(width, height, box_width, box_height):
    scale = min(box_width / width, box_height / height)
    return max(1, round(width * scale)), max(1, round(height * scale))


def main():
    pieces = []
    starts = []

    def add(mask):
        starts.append(len(pieces))
        pieces.extend(chunks(runs(mask)))

    scene_count = len(scene_indices('scene'))
    if len(scene_indices('portrait')) != scene_count:
        raise ValueError('Every scene needs its tall page, art/paint/portraitN.svg')

    def scenes(kind, size, thumb):
        rows = {}
        for index in range(1, scene_count + 1):
            source = ART / f'{kind}{index}.svg'
            page = render(source.read_text(), *size)
            add(numpy.asarray(page.convert('L')) < 128)
            picture = page.convert('RGB').resize(thumb, Image.Resampling.LANCZOS)
            destination = ASSETS / f'{kind}{index}-thumb.avif'
            save_avif(picture, destination)
            rows[destination.relative_to(ROOT).as_posix()] = thumbnail_row(source, picture, destination)
        return rows

    scenes('scene', CANVAS, (256, 192))
    widths, heights = [], []
    stencil_count = len(list(ART.glob('dino[0-9]*.svg')))
    for index in range(1, stencil_count + 1):
        svg, width, height, ink, body = dinosaur(index)
        for size in range(1, SIZES + 1):
            w, h = fit(width, height, CANVAS[0] * size / SIZES, CANVAS[1] * size / SIZES)
            widths.append(w)
            heights.append(h)
            # Lines keep pixels they half cover; the body keeps whole ones.
            add(numpy.asarray(render(ink, w, h).getchannel('A')) >= 96)
            add(numpy.asarray(render(body, w, h).getchannel('A')) >= 128)
        export_painted_image(render(svg, *fit(width, height, 240, 376)), ASSETS / f'dino{index}-preview.avif', 'cutout')
    # Tall pages come last, so the masks before them keep their numbers.
    # The wide thumbnails keep the receipts of their WebP migration.
    record_canonical_rows(scenes('portrait', TALL, (192, 256)))
    starts.append(len(pieces))

    def table(name, kind, values):
        return f'{name}: [{len(values)}]{kind} = .[' + ', '.join(map(str, values)) + '];\n'

    code = '// Generated by tools/paint_pages.py from art/paint/*.svg.\n'
    code += f'SCENE_COUNT :: {scene_count}\nDINO_COUNT :: {stencil_count}\nDINO_SIZES :: 4\n\n'
    code += '// Small to Huge for each dinosaur, at dino * DINO_SIZES + size - 1.\n'
    code += table('DINO_WIDTH', 's32', widths) + table('DINO_HEIGHT', 's32', heights)
    code += '\n// Masks in order: the wide scenes, each dinosaur size\'s ink and body,\n'
    code += '// then the tall scenes. Mask m is chunks MASK_START[m] up to MASK_START[m + 1].\n'
    code += table('MASK_START', 's32', starts)
    # A declaration, even across lines, must stay within one source line's
    # limit, so each chunk is its own constant.
    code += '\n' + ''.join(f'MASK_{index} :: "{piece}"\n' for index, piece in enumerate(pieces))
    code += '\nMaskChunk :: (index: s32) -> string {\n'
    code += ''.join(f'    if index == {index} {{ return MASK_{index} }}\n' for index in range(len(pieces)))
    code += '    return ""\n}\n'
    (ROOT / 'games/paint/paint_pages.zi').write_text(code)
    print(f'Compiled {scene_count} scenes and {len(widths)} dinosaur sizes into {len(pieces)} mask chunks '
          f'({sum(map(len, pieces)) // 1024} KiB).')


if __name__ == '__main__':
    main()

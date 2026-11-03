"""Rebuild Jungle's cursors: the app-wide hand and the Farm's two tool cursors.

The hand comes from its ignored generated master,
local/art-development/cursor/hand-generated-v1.png; the tools from the Farm's
own play art. Beside the master this writes each cleaned master, 32/48/64 px
review exports and composites over dark, light and green backgrounds. Each
runtime is one exact lossless 128 px WebP. Hosts draw it at CURSOR_UNITS
logical units with the hotspot recorded in cursor.json, through Kryon's
CursorSetDefault (hand) or CursorSet (tools), at their own pixel density.

Cleaning: keep only the object (largest alpha component), make the interior
fully opaque, give every partly transparent edge pixel the colour of its
nearest opaque neighbour, so no light matte can show, and add a smooth outer
stroke in the hand's outline brown so every cursor reads on any scene.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from image_exports import export_image

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'local/art-development/cursor'
RUNTIME_SIZE = 128
CURSOR_UNITS = 32
REVIEW_SIZES = (32, 48, 64)
STROKE = 1 / 64
# name, source, runtime, hotspot rule, top-aligned
CURSORS = (
    ('hand', ART / 'hand-generated-v1.png', ROOT / 'assets/jungle/hand-cursor.webp', 'fingertip', True),
    ('watering-can', ROOT / 'assets/garden/play/watering-can.webp',
     ROOT / 'assets/garden/play/cursor-watering-can.webp', 'spout', False),
    ('harvest-basket', ROOT / 'assets/garden/play/harvest-basket.webp',
     ROOT / 'assets/garden/play/cursor-harvest-basket.webp', 'centre', False),
)


def outline_colour(rgba, inside):
    return np.median(rgba[..., :3][inside & ~ndimage.binary_erosion(inside, iterations=4)], axis=0)


def clean(picture, outline=None):
    rgba = np.asarray(picture.convert('RGBA')).astype(np.float64)
    alpha = rgba[..., 3]
    labels, count = ndimage.label(alpha > 16)
    if count == 0:
        raise SystemExit('cursor master has no visible object')
    sizes = ndimage.sum(np.ones_like(alpha), labels, range(1, count + 1))
    shape = labels == 1 + int(np.argmax(sizes))
    # Soft antialiasing survives only on the object's own boundary; holes fill.
    shape = ndimage.binary_fill_holes(ndimage.binary_dilation(shape, iterations=2))
    alpha = np.where(shape, np.clip((alpha - 16.0) * 255.0 / (224.0 - 16.0), 0.0, 255.0), 0.0)
    opaque = alpha >= 255.0
    # Nearest opaque pixel supplies every edge colour.
    _, (rows, cols) = ndimage.distance_transform_edt(~opaque, return_indices=True)
    colour = rgba[..., :3][rows, cols]
    colour = np.where(opaque[..., None], rgba[..., :3], colour)
    # A smooth outer stroke about one pixel wide at 2x keeps the silhouette
    # readable over light and dark scenes.
    inside = alpha >= 128.0
    distance = ndimage.distance_transform_edt(~inside)
    stroke = np.clip(STROKE * max(alpha.shape) + 0.5 - distance, 0.0, 1.0) * 255.0
    if outline is None:
        outline = outline_colour(rgba, inside)
    cover = alpha[..., None] / 255.0
    colour = colour * cover + outline * (1.0 - cover)
    alpha = np.maximum(alpha, stroke)
    result = np.dstack([colour, alpha]).round().clip(0, 255).astype(np.uint8)
    return Image.fromarray(result, 'RGBA'), outline


def square(picture, top):
    box = picture.getchannel('A').getbbox()
    shape = picture.crop(box)
    side = max(shape.size)
    # About one logical unit of clear border at every size.
    margin = max(2, side // 30)
    canvas = Image.new('RGBA', (side + 2 * margin, side + 2 * margin), (0, 0, 0, 0))
    # The hand's fingertip sits at the top; tools centre both ways.
    y = margin if top else (canvas.height - shape.height) // 2
    canvas.alpha_composite(shape, ((canvas.width - shape.width) // 2, y))
    return canvas


def hotspot(picture, rule):
    solid = np.asarray(picture.getchannel('A')) >= 128
    rows = np.where(solid.any(axis=1))[0]
    columns = np.where(solid.any(axis=0))[0]
    if rule == 'fingertip':
        top = int(rows[0])
        band = solid[top:top + max(2, picture.height // 40)]
        x = float(np.where(band.any(axis=0))[0].mean())
        y = float(top + picture.height / 64)
    elif rule == 'spout':
        # The rose's face: the leftmost band of the can, where water leaves.
        left = int(columns[0])
        band = solid[:, left:left + max(2, picture.width // 12)]
        x = float(left + picture.width / 24)
        y = float(np.where(band.any(axis=1))[0].mean())
    else:
        x = float(columns[0] + columns[-1]) / 2.0
        y = float(rows[0] + rows[-1]) / 2.0
    return [min(CURSOR_UNITS - 1, round(value / size * CURSOR_UNITS))
            for value, size in ((x, picture.width), (y, picture.height))]


def resize(picture, size):
    # Premultiplied resampling: transparent pixels never bleed colour.
    small = picture.convert('RGBa').resize((size, size), Image.Resampling.LANCZOS).convert('RGBA')
    pixels = np.asarray(small).copy()
    pixels[pixels[..., 3] < 3] = 0
    return Image.fromarray(pixels, 'RGBA')


def composite(picture, colour):
    background = Image.new('RGBA', picture.size, colour)
    background.alpha_composite(picture)
    return background.convert('RGB')


def review(name, master, spot):
    sheet = Image.new('RGB', (sum(REVIEW_SIZES) * 8 + 40, max(REVIEW_SIZES) * 8 * 3 + 40), (128, 128, 128))
    x = 10
    for size in REVIEW_SIZES:
        small = resize(master, size)
        small.save(ART / f'{name}-{size}.png')
        for row, colour in enumerate(((24, 26, 34, 255), (250, 244, 228, 255), (52, 120, 60, 255))):
            view = composite(small, colour).resize((size * 8, size * 8), Image.Resampling.NEAREST)
            # Hotspot marker, one review pixel at this size.
            px = spot[0] * size // CURSOR_UNITS * 8
            py = spot[1] * size // CURSOR_UNITS * 8
            for dx in range(8):
                view.putpixel((px + dx, py + 3), (255, 0, 255))
                view.putpixel((px + 3, py + dx), (255, 0, 255))
            sheet.paste(view, (x, 10 + row * (max(REVIEW_SIZES) * 8 + 10)))
        x += size * 8 + 10
    sheet.save(ART / f'review-{name}.png')


def main():
    ART.mkdir(parents=True, exist_ok=True)
    manifest = {'units': CURSOR_UNITS, 'cursors': {}}
    outline = None
    for name, source, runtime, rule, top in CURSORS:
        if not source.exists():
            print(f'{name}: {source.relative_to(ROOT)} is missing; skipped')
            continue
        cleaned, found = clean(Image.open(source), outline)
        outline = found if outline is None else outline
        master = square(cleaned, top)
        master.save(ART / f'{name}-clean.png')
        spot = hotspot(master, rule)
        review(name, master, spot)
        exported = resize(master, RUNTIME_SIZE)
        exported.save(ART / f'{name}-{RUNTIME_SIZE}.png')
        export = export_image(ART / f'{name}-{RUNTIME_SIZE}.png', runtime, 'exact')
        manifest['cursors'][name] = {'runtime': str(runtime.relative_to(ROOT)), 'hotspot': spot,
                                     'lossless': export.lossless}
        print(f'{name} cursor: {runtime.relative_to(ROOT)} {RUNTIME_SIZE}px lossless={export.lossless}, '
              f'hotspot {spot} of {CURSOR_UNITS} units')
    (ART / 'cursor.json').write_text(json.dumps(manifest, indent=1) + '\n')


if __name__ == '__main__':
    main()

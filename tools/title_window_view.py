"""Put the world map's coast in the Treehouse window: white dunes, lagoons
and the jungle below, as on the world map.

The owner (2026-11-06): "the view of the treehouse while pretty doesn't make
complete sense, should match a bit more with the actual map". A generated
view (an edit of the old plate, same frame and vine) replaces the plate inside
the window; the frame, swaying twig, leaves and clouds stay separate layers.
`keep` envelopes hold the old plate's own branch pixels where a still layer
joins it (the branch the portrait twig hangs from). The sky occluder, which hides
clouds behind near foliage, keeps only foliage that is still in the plate.

Masters live in local/art-development/treehouse-window-view/ (never tracked):
  <orientation>-view-generated.png   the generated view, the plate's size
Explicit art authoring only; ordinary builds use the committed AVIFs.

    python3 tools/title_window_view.py
then python3 tools/title_animations.py (the occluder's draw strips).
"""
from pathlib import Path
import json

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from image_exports import export_scaled_master, export_low_master, export_cutout_master, record_canonical_rows
from title_map_palette import approve

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT/'local/art-development'
MASTERS = LOCAL/'treehouse-window-view'
ANIMATION = 'assets/jungle/title/window-animation/'
APPROVED = ROOT/'tests/approved_title_avif.json'
VIEWS = {
    'landscape': dict(plate=LOCAL/'treehouse-window-animation/sky-clouds-twig/landscape-final-background.png',
                      image='assets/jungle/title/window.avif', low='assets/jungle/title/window-low.avif',
                      keep=[]),
    'portrait': dict(plate=LOCAL/'campus-fix/window-portrait-twig-plate.png',
                     image='assets/jungle/title/window-portrait.avif',
                     low='assets/jungle/title/window-portrait-low.avif',
                     keep=[[(1024, 330), (930, 335), (860, 365), (780, 380), (700, 405), (650, 465), (640, 525),
                            (700, 530), (770, 505), (810, 530), (830, 590), (865, 600), (880, 690), (860, 740),
                            (870, 790), (930, 840), (985, 905), (1024, 935)]]),
}
# Plate and view colors closer than this (0..255 per channel) count as the same foliage.
SAME = 18


def envelope_mask(plate, polygons):
    """1.0 on the still branch inside each traced envelope: saturated leaves
    and bark, never the pale sky, haze or distant hills around them."""
    values = np.asarray(plate.convert('HSV'), np.float32) / 255.0
    h, s = values[..., 0], values[..., 1]
    foliage = (s > 0.3) & ~((h > 0.45) & (h < 0.75))
    out = np.zeros(foliage.shape, bool)
    for polygon in polygons:
        shape = Image.new('L', plate.size)
        ImageDraw.Draw(shape).polygon(polygon, fill=255)
        out |= foliage & (np.asarray(shape) > 0)
    # Close leaf-vein gaps, then soften the join by a pixel.
    solid = Image.fromarray((out * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
    return np.asarray(solid.filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255.0


def build(orientation, spec):
    plate = Image.open(spec['plate']).convert('RGB')
    view = Image.open(MASTERS/f'{orientation}-view-generated.png').convert('RGB')
    if view.size != plate.size:
        raise SystemExit(f'{orientation}-view-generated.png must be {plate.size[0]}x{plate.size[1]}')
    frame = Image.open(ROOT/ANIMATION/f'{orientation}-frame.avif').convert('RGBA').getchannel('A')
    # The frame layer covers its own pixels; the plate keeps them for the first paint.
    keep = np.maximum(np.asarray(frame, np.float32) / 255.0, envelope_mask(plate, spec['keep']))[..., None]
    old, new = np.asarray(plate, np.float32), np.asarray(view, np.float32)
    background = Image.fromarray(np.clip(old * keep + new * (1 - keep) + 0.5, 0, 255).astype(np.uint8))
    occluder = Image.open(ROOT/ANIMATION/f'{orientation}-sky-occluder.avif').convert('RGBA')
    near = np.abs(np.asarray(occluder.convert('RGB'), np.float32) -
                  np.asarray(background, np.float32)[:occluder.height]).max(axis=2)
    same = Image.fromarray(((near < SAME) * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3))
    alpha = np.minimum(np.asarray(occluder.getchannel('A')), np.asarray(same))
    occluder.putalpha(Image.fromarray(alpha))
    return background, occluder


def main():
    approved = json.loads(APPROVED.read_text())
    rows = {}
    for orientation, spec in VIEWS.items():
        background, occluder = build(orientation, spec)
        master = MASTERS/f'{orientation}-background.png'
        background.save(master)
        depth = MASTERS/f'{orientation}-sky-occluder.png'
        occluder.save(depth)
        rows[spec['image']] = export_scaled_master(master, ROOT/spec['image'])
        rows[spec['low']] = export_low_master(master, ROOT/spec['low'])
        for name in (spec['image'], spec['low']):
            approve(approved, master, rows[name], name)
        target = ANIMATION+f'{orientation}-sky-occluder.avif'
        rows[target] = export_cutout_master(depth, ROOT/target)
        print(f'title window: {orientation} view and sky occluder exported')
    approved['total_bytes'] = sum(r['bytes'] for r in approved['images'])
    APPROVED.write_text(json.dumps(approved, indent=2) + '\n')
    record_canonical_rows(rows)


if __name__ == '__main__':
    main()

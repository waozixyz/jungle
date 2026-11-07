"""Give the waterfront and Market title plates the world map's white sand.

The owner (2026-11-06): "it is a white beach, white sand must match the actual
map". The map's dunes are a warm white with grey-lilac shadows; Beach, Port,
Market and Aquarium were painted with yellow sand. A repaint would move the
stalls, boat and signs away from their hotspots and glow cut-outs, so this
recolors only the sand in the existing masters, pixel-aligned: sand-colored
pixels (tools/title_map_palette.json `sand`) below each plate's ground line and
outside its keep-out boxes take the map's sand ramp at the same relative
brightness, so footprints, ripples and shadows stay. The map ramp is measured
from the world-map painting itself.

Explicit art authoring only; ordinary builds use the committed AVIFs.

    python3 tools/title_map_palette.py [--preview]
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from image_exports import export_scaled_master, export_low_master, record_canonical_rows

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT/'tools/title_map_palette.json'
APPROVED = ROOT/'tests/approved_title_avif.json'
OUT = ROOT/'local/art-development/map-palette'
RAMP = (5, 25, 50, 75, 95)


def hsv(picture):
    return np.asarray(picture.convert('HSV'), dtype=np.float32) / 255.0


def sand_weight(values, sand):
    """0..1 per pixel: how sand-colored a pixel is (soft hue/saturation/value ramps)."""
    h, s, v = values[..., 0], values[..., 1], values[..., 2]

    def ramp(x, lo, hi, soft):
        return np.clip(np.minimum((x - lo) / soft + 1.0, (hi - x) / soft + 1.0), 0.0, 1.0)
    return (ramp(h, *sand['hue'], 0.02) * ramp(s, *sand['saturation'], 0.06) *
            np.clip((v - sand['value_min']) / 0.06 + 1.0, 0.0, 1.0))


def solid_color(values, sand):
    """0..1 protection for large saturated areas (planks, piers, carts, roofs):
    an opening drops the thin path edges and speckles, which stay sand."""
    saturated = Image.fromarray(((values[..., 1] > sand['solid_saturation']) * 255).astype(np.uint8), 'L')
    size = sand['solid_size']
    opened = saturated.filter(ImageFilter.MinFilter(size)).filter(ImageFilter.MaxFilter(size))
    grown = opened.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(2))
    return np.asarray(grown, dtype=np.float32) / 255.0


def map_ramp(config):
    """The world map's sand color at the RAMP brightness percentiles."""
    with Image.open(ROOT/config['map']) as picture:
        rgb = np.asarray(picture.convert('RGB'), dtype=np.float32)
        values = hsv(picture)
    rule = config['map_sand']
    h, s, v = values[..., 0], values[..., 1], values[..., 2]
    mask = (v > rule['value_min']) & (s < rule['saturation_max']) & ~((h > rule['green_blue'][0]) & (h < rule['green_blue'][1]))
    levels = np.percentile(v[mask], RAMP)
    colors = [rgb[mask & (np.abs(v - level) < 0.01)].mean(axis=0) for level in levels]
    return np.array(colors, dtype=np.float32)


def region(size, plate, hotspots):
    """Where sand may change: the include boxes (or everything below the ground
    line), minus keep-out boxes and the painted landmarks' hit shapes."""
    mask = Image.new('L', size, 0)
    draw = ImageDraw.Draw(mask)
    for box in plate.get('include', [[0, plate.get('ground_top', 0), size[0], size[1]]]):
        draw.rectangle(box, fill=255)
    for box in plate.get('keep', []):
        draw.rectangle(box, fill=0)
    for name in plate.get('keep_hotspots', []):
        found = [h for h in hotspots if h['id'] == name]
        if not found:
            raise SystemExit(f"{plate['image']}: no hotspot {name} to keep")
        draw.polygon([tuple(point) for point in found[0]['polygon']], fill=0)
    return np.asarray(mask.filter(ImageFilter.GaussianBlur(plate.get('feather', 12))), dtype=np.float32) / 255.0


def view(data, plate):
    scene = next(s for s in data['scenes'] if s['name'] == plate['scene'])
    return scene['portrait'] if plate['orientation'] == 'portrait' else scene


def recolor(master, plate, config, colors, hotspots):
    with Image.open(master) as picture:
        rgb = np.asarray(picture.convert('RGB'), dtype=np.float32)
        values = hsv(picture)
    sand = dict(config['sand'], **plate.get('sand', {}))
    weight = sand_weight(values, sand) * (1.0 - solid_color(values, sand)) * region((rgb.shape[1], rgb.shape[0]), plate, hotspots)
    v = values[..., 2]
    found = weight > 0.5
    if not found.any():
        raise SystemExit(f'{master.name}: no sand found below its ground line')
    # Each pixel keeps its rank in this plate's own sand brightness range.
    lo, hi = np.percentile(v[found], (RAMP[0], RAMP[-1]))
    t = np.clip((v - lo) / max(hi - lo, 1e-3), 0.0, 1.0) * (len(RAMP) - 1)
    index = np.minimum(t.astype(np.int32), len(RAMP) - 2)
    frac = (t - index)[..., None]
    target = colors[index] * (1.0 - frac) + colors[index + 1] * frac
    out = rgb * (1.0 - weight[..., None]) + target * weight[..., None]
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), 'RGB'), float(found.mean())


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def approve(approved, master, row, destination):
    """The title ledger row tests/title_scenes_test.py checks for DESTINATION."""
    path = ROOT/destination
    with Image.open(path) as image:
        decoded = hashlib.sha256(image.convert('RGBA').tobytes()).hexdigest()
    width, height = row.get('design_dimensions', row['dimensions'])
    entry = dict(name=path.stem, path=destination, bytes=path.stat().st_size, sha256=digest(path),
                 width=width, height=height, decoded_rgba_sha256=decoded,
                 canonical_source=master.relative_to(ROOT).as_posix(), canonical_bytes=master.stat().st_size,
                 canonical_sha256=digest(master))
    images = approved['images']
    at = next((i for i, r in enumerate(images) if r['path'] == destination), None)
    if at is None:
        images.append(entry)
    else:
        images[at] = entry


def main(preview=False):
    """Recolor every plate; PREVIEW writes only the local masters."""
    config = json.loads(CONFIG.read_text())
    data = json.loads((ROOT/'tools/title_hotspots.json').read_text())
    colors = map_ramp(config)
    OUT.mkdir(parents=True, exist_ok=True)
    approved = json.loads(APPROVED.read_text())
    rows = {}
    for plate in config['plates']:
        source = ROOT/plate['master']
        picture, share = recolor(source, plate, config, colors, view(data, plate)['hotspots'])
        master = OUT/f"{Path(plate['image']).stem}.png"
        picture.save(master)
        print(f"{plate['image']}: {share:.0%} sand recolored")
        if preview:
            continue
        rows[plate['image']] = export_scaled_master(master, ROOT/plate['image'])
        rows[plate['low']] = export_low_master(master, ROOT/plate['low'])
        for name in (plate['image'], plate['low']):
            approve(approved, master, rows[name], name)
    if preview:
        return
    approved['total_bytes'] = sum(r['bytes'] for r in approved['images'])
    APPROVED.write_text(json.dumps(approved, indent=2) + '\n')
    record_canonical_rows(rows)


if __name__ == '__main__':
    import sys
    main(preview='--preview' in sys.argv[1:])

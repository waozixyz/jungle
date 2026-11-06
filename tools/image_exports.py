"""Original-based AVIF exports; preserve dimensions and approved artwork."""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import shutil
from PIL import Image, ImageOps, __version__
from avif_codec import save_avif, CUTOUT_QUALITY, QUALITY, SPEED, encoder_version

ROOT = Path(__file__).resolve().parents[1]
TITLE_BACKGROUND_QUALITY = QUALITY
PRESETS = {'title-background': QUALITY, 'book-page': QUALITY,
           'scene': QUALITY, 'book-preview': 50, 'puzzle': 60, 'icon': 60, 'cutout': None, 'exact': None}
# Jigsaw pieces are cut from the painting at runtime and small menu icons show
# every pixel; full chroma keeps their detail.
SUBSAMPLING = {'puzzle': '444', 'icon': '444'}

# Owner standard (2026-11-05): Lanczos-downscale each master to 75% of its
# size, then AVIF q35 -- about 30 KB per full scene at the approved tiger-page
# quality. Hosts draw every picture into its layout rectangle, so the smaller
# texture keeps its on-screen size. Transparent art uses 4:4:4 color and
# near-lossless alpha (q90) so edges stay clean.
SCALE = 0.75
SCALE_QUALITY = 35
SCALE_ALPHA_QUALITY = 90
SCALE_MIN = 512
# Drawn through pixel source rectangles (sprite sheets, window frame, sky
# occluder, jigsaw cells, paint pages), pixel-exact cursors and the Farm: keep pixels.
UNSCALED = ('assets/jungle/title/window-animation/', 'assets/jigsaw/', 'assets/dino-paint/',
            'assets/garden/')  # Farm geometry is traced in its painting pixels


def scaled_role(name, size, exact=False):
    """Whether shipped NAME of SIZE takes the 75% standard."""
    return (not exact and max(size) >= SCALE_MIN and not name.startswith(UNSCALED)
            and 'cursor' not in Path(name).name)


def runtime_size(size):
    return max(1, round(size[0] * SCALE)), max(1, round(size[1] * SCALE))


def save_scaled(master, destination):
    """Encode MASTER (a PIL image) under the 75% standard; returns its alpha flag."""
    picture = ImageOps.exif_transpose(master).convert('RGBA')
    alpha = picture.getchannel('A').getextrema()[0] < 255
    solid = picture.convert('RGB').getcolors(1)
    picture = picture.resize(runtime_size(picture.size), Image.Resampling.LANCZOS)
    if alpha and solid:
        # One-color glows: un-premultiplied Lanczos would add color noise in the
        # faint halo; keep the single color so only the alpha costs bytes.
        halo = picture.getchannel('A')
        picture = Image.new('RGBA', picture.size, solid[0][1] + (0,))
        picture.putalpha(halo)
    if alpha:
        save_avif(picture, destination, lossless=True, cutout_quality=SCALE_QUALITY,
                  alpha_quality=SCALE_ALPHA_QUALITY)
    else:
        save_avif(picture.convert('RGB'), destination, quality=SCALE_QUALITY)
    return alpha


@dataclass(frozen=True)
class ImageExport:
    source: Path
    quality: int | None
    lossless: bool
    reused_source: bool


def optimize_new_image_exports(source, role, cache, *, size=None):
    """Cache one original-based export. Existing AVIF is reused byte for byte.

    Only explicitly requested preview/established derivative sizes may resize.
    Role 'exact' keeps every RGBA value, including hidden RGB under alpha 0.
    Other roles on transparent art (use 'cutout' for layers) keep every alpha
    value exact with q70 4:4:4 color; opaque 'cutout' art stays lossless.
    """
    quality = PRESETS[role]
    source, cache = Path(source), Path(cache)
    with Image.open(source) as original:
        if original.format == 'AVIF':
            if size is not None:
                raise ValueError('Use the original, not an exported AVIF, for derivatives')
            return ImageExport(source, None, False, True)
        picture = ImageOps.exif_transpose(original).convert('RGBA')
    alpha = picture.getchannel('A').getextrema()[0] < 255
    if role == 'title-background' and alpha:
        raise ValueError('Title backgrounds must be opaque; use the cutout role for layers')
    if size is not None:
        picture = picture.resize(size, Image.Resampling.LANCZOS)
    if not alpha:
        picture = picture.convert('RGB')
    exact = role == 'exact'
    lossless = alpha or quality is None
    cache.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    variant = '-rgba' if exact else ''  # Older exact-role entries were cut-outs.
    key = hashlib.sha256(f'{digest}-{role}-{quality}-{size}-{__version__}-{encoder_version()}-avif-{SPEED}-v2{variant}'.encode()).hexdigest()
    target = cache / (key + '.avif')
    if not target.exists():
        save_avif(picture, target, lossless=lossless, exact=exact, quality=quality or 100,
                  subsampling=SUBSAMPLING.get(role, '420'))
        if not lossless:
            smaller = target.with_suffix('.exact.avif')
            try:
                save_avif(picture, smaller, lossless=True)
                if smaller.stat().st_size < target.stat().st_size:
                    smaller.replace(target)
            finally:
                smaller.unlink(missing_ok=True)
    with Image.open(target) as decoded:
        decoded.load()
        assert decoded.format == 'AVIF' and decoded.size == picture.size
        exact_pixels = decoded.convert(picture.mode).tobytes() == picture.tobytes()
        if exact:
            # Every RGBA value, including color hidden under alpha 0.
            assert exact_pixels, 'exact export changed RGBA values'
        elif alpha:
            # Cut-outs: every alpha value exact, q70 4:4:4 color.
            assert decoded.convert('RGBA').getchannel('A').tobytes() == picture.getchannel('A').tobytes()
        elif lossless:
            assert exact_pixels
        lossless = (lossless and not alpha) or exact_pixels
    return ImageExport(target, None if lossless else (CUTOUT_QUALITY if alpha else quality), lossless, False)


def export_image(source, destination, role, *, size=None):
    """Explicit art-export step; encoding grants no artwork approval."""
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError('An export must not overwrite its original')
    if destination.suffix.lower() != '.avif':
        raise ValueError('Runtime image exports must use a .avif destination')
    export = optimize_new_image_exports(source, role, ROOT / 'local/art-development/image-exports', size=size)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists() or destination.read_bytes() != export.source.read_bytes():
        shutil.copyfile(export.source, destination)
    return export


def export_painted_image(picture, destination, role='exact'):
    """Keep a private painted PNG master and export only runtime AVIF."""
    destination = Path(destination)
    master = ROOT / 'local/art-development/masters' / destination.relative_to(ROOT).with_suffix('.png')
    master.parent.mkdir(parents=True, exist_ok=True)
    picture.save(master, 'PNG')
    return export_image(master, destination, role)


def trim_cutout(picture, max_display, *, margin=4, alpha_floor=8, align=1):
    """Trim a lossless cut-out and cap it at twice its full-canvas display size.

    Return the derivative and its original-pixel crop rectangle. Draw callers
    apply that rectangle AFTER containing the original canvas in the target;
    this preserves feet, pointer hotspots and aspect even in nonsquare boxes.
    Pillow resamples RGBA in premultiplied alpha, avoiding a light matte.
    ALIGN supports cursors whose crop/hotspot must land on logical pixels.
    """
    import math
    picture = picture.convert('RGBA')
    alpha = picture.getchannel('A')
    alpha = alpha.point(lambda value: value if value > alpha_floor else 0)
    picture.putalpha(alpha)
    # Discard hidden RGB, including the invisible generation speckles.
    picture.paste((0, 0, 0, 0), mask=alpha.point(lambda value: 255 if value == 0 else 0))
    box = alpha.getbbox()
    if box is None:
        raise ValueError('Empty cut-out')
    scale = min(1.0, 2 * max_display / max(picture.size))
    padding = max(margin, math.ceil(2 / scale))
    left, top, right, bottom = box
    box = (max(0, (left-padding)//align*align), max(0, (top-padding)//align*align),
           min(picture.width, math.ceil((right+padding)/align)*align),
           min(picture.height, math.ceil((bottom+padding)/align)*align))
    result = picture.crop(box)
    size = tuple(max(1, round(edge*scale)) for edge in result.size)
    if size != result.size:
        result = result.resize(size, Image.Resampling.LANCZOS)
    # Lanczos may create invisible RGB; keep exact alpha with clean hidden RGB.
    result.paste((0, 0, 0, 0), mask=result.getchannel('A').point(lambda value: 255 if value == 0 else 0))
    return result, box


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def export_scaled_master(master, destination):
    """Ship a new private PNG master under the 75% standard and return the
    tools/canonical_avif.json row that tests/canonical_avif_test.py checks."""
    master, destination = Path(master), Path(destination)
    with Image.open(master) as original:
        original.load()
        alpha = save_scaled(original, destination)
        design = list(original.size)
        source_rgba = original.convert('RGBA')
    with Image.open(destination) as shipped:
        rgba = shipped.convert('RGBA')
        dimensions = list(shipped.size)
    with master.open('rb') as handle:
        master_sha = hashlib.file_digest(handle, 'sha256').hexdigest()
    with destination.open('rb') as handle:
        sha = hashlib.file_digest(handle, 'sha256').hexdigest()
    name = master.relative_to(ROOT).as_posix()
    return dict(source=name, source_sha256=master_sha, source_bytes=master.stat().st_size,
                source_rgba_sha256=_sha(source_rgba.tobytes()), dimensions=dimensions, alpha=alpha,
                source_alpha_sha256=_sha(source_rgba.getchannel('A').tobytes()),
                alpha_sha256=_sha(rgba.getchannel('A').tobytes()), rgba_sha256=_sha(rgba.tobytes()),
                sha256=sha, bytes=destination.stat().st_size, quality=SCALE_QUALITY, lossless=False,
                subsampling='444' if alpha else '420', speed=SPEED, design_dimensions=design, scale=SCALE,
                master=name, master_sha256=master_sha, exact_alpha=False,
                alpha_quality=SCALE_ALPHA_QUALITY if alpha else 100)


def record_canonical_rows(rows, receipt=ROOT / 'tools/canonical_avif.json'):
    """Add or replace shipped rows and keep the receipt's count and byte totals."""
    import json
    data = json.loads(Path(receipt).read_text())
    data['files'].update(rows)
    data['count'] = len(data['files'])
    data['after_bytes'] = sum(row['bytes'] for row in data['files'].values())
    data['before_bytes'] = sum(row['source_bytes'] for row in data['files'].values())
    Path(receipt).write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    return data


def check_cutout(path, max_display, *, padding=6):
    """Fail a shipping check for oversized/padded/nonlossless cut-outs."""
    path = Path(path)
    with Image.open(path) as picture:
        assert picture.format == 'AVIF', (path, 'cut-outs must use AVIF')
        assert picture.mode == 'RGBA', (path, 'missing alpha')
        assert max(picture.size) <= 2 * max_display + 1, (path, 'oversized', picture.size)
        box = picture.getchannel('A').point(lambda value: 255 if value > 8 else 0).getbbox()
        assert box, (path, 'empty cut-out')
        margins = (box[0], box[1], picture.width-box[2], picture.height-box[3])
        assert max(margins) <= padding, (path, 'transparent padding', margins)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--role', choices=PRESETS, required=True)
    options = parser.parse_args()
    export_image(options.source, options.destination, options.role)

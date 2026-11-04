"""Optimize original-based image exports within the existing art approval workflow.

Callers own the existing review/install step. No implicit resizing, source writes,
or attempt to improve previously lossy WebP exports by transcoding them.
"""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import shutil
import tempfile

from PIL import Image, ImageOps, __version__, features

ROOT = Path(__file__).resolve().parents[1]

TITLE_BACKGROUND_QUALITY = 50
PRESETS = {'title-background': TITLE_BACKGROUND_QUALITY, 'book-page': 85,
           'scene': 85, 'cutout': None, 'exact': None}


@dataclass(frozen=True)
class ImageExport:
    source: Path
    quality: int | None
    lossless: bool
    reused_source: bool


def optimize_new_image_exports(source, role, cache, *, size=None):
    """Return a cached WebP candidate, retaining the full-resolution original.

    SIZE is only for an explicit established runtime size or preview derivative.
    Transparent images always use exact lossless RGBA, including hidden RGB.
    For opaque images choose the smaller of the preset and exact lossless WebP.
    Existing WebP is passed through unchanged (including oversized exports).
    """
    quality = PRESETS[role]  # Explicit roles; typos must not select a fallback.
    source, cache = Path(source), Path(cache)
    with Image.open(source) as original:
        if original.format == 'WEBP':
            if size is not None:
                raise ValueError('Use the original, not an exported WebP, for derivatives')
            return ImageExport(source, None, False, True)
        profile = original.info.get('icc_profile')
        picture = ImageOps.exif_transpose(original).convert('RGBA')
    alpha = picture.getchannel('A').getextrema()[0] < 255
    if role == 'title-background' and alpha:
        raise ValueError('Title backgrounds must be opaque; use the cutout role for layers')
    if size is not None:
        picture = picture.resize(size, Image.Resampling.LANCZOS)
    if not alpha:
        picture = picture.convert('RGB')
    lossless = alpha or quality is None
    cache.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    key = hashlib.sha256(f'{digest}-{role}-{quality}-{size}-{__version__}-{features.version("webp")}-v1'.encode()).hexdigest()
    target = cache / (key + '.webp')
    if not target.exists():
        candidates = []
        try:
            for exact in ([True] if lossless else [False, True]):
                with tempfile.NamedTemporaryFile(dir=cache, suffix='.webp', delete=False) as handle:
                    candidate = Path(handle.name)
                candidates.append(candidate)
                picture.save(candidate, 'WEBP', lossless=exact, quality=100 if exact else quality,
                             method=6, exact=True, alpha_quality=100,
                             **({'icc_profile': profile} if profile else {}))
            chosen = min(candidates, key=lambda path: path.stat().st_size)
            with Image.open(chosen) as decoded:
                decoded.load()
                assert decoded.size == picture.size
                if alpha:
                    assert decoded.convert('RGBA').tobytes() == picture.tobytes()
            chosen.replace(target)
        finally:
            for candidate in candidates:
                candidate.unlink(missing_ok=True)
    # Inspect the chosen bitstream, including cache hits: a lossless candidate
    # may have beaten the lossy preset for a simple opaque illustration.
    with target.open('rb') as handle:
        handle.seek(12)
        while header := handle.read(8):
            if header[:4] in (b'VP8L', b'VP8 '):
                lossless = header[:4] == b'VP8L'
                break
            length = int.from_bytes(header[4:], 'little')
            handle.seek(length + length % 2, 1)
    return ImageExport(target, None if lossless else quality, lossless, False)


def export_image(source, destination, role, *, size=None):
    """Explicit existing art-export step; candidates themselves grant no approval."""
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError('An export must not overwrite its original')
    # Cache lives beside project sources, never in shipping assets.
    root = ROOT
    if destination.suffix.lower() != '.webp':
        raise ValueError('Runtime image exports must use a .webp destination')
    export = optimize_new_image_exports(source, role, root / 'local/art-development/image-exports', size=size)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists() or destination.read_bytes() != export.source.read_bytes():
        shutil.copyfile(export.source, destination)
    return export


def export_painted_image(picture, destination, role='exact'):
    """Keep a generated/painted master privately, then export the runtime WebP."""
    destination = Path(destination)
    relative = destination.relative_to(ROOT)
    master = ROOT / 'local/art-development/masters' / relative.with_suffix('.png')
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


def check_cutout(path, max_display, *, padding=6):
    """Fail a shipping check for oversized/padded/nonlossless cut-outs."""
    path = Path(path)
    with path.open('rb') as stream:
        assert stream.read(16)[12:16] == b'VP8L', (path, 'cut-outs must be lossless WebP')
    with Image.open(path) as picture:
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

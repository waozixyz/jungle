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
           'scene': 85, 'cutout': None}


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
    export = optimize_new_image_exports(source, role, root / 'work/image-exports', size=size)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists() or destination.read_bytes() != export.source.read_bytes():
        shutil.copyfile(export.source, destination)
    return export

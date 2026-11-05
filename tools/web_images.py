"""AVIF staging shared by desktop, Android and web. Approved exports are reused.

Only the explicit 128px preview paths resize; full artwork retains dimensions.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import hashlib
from pathlib import Path
from PIL import Image, ImageOps
from avif_codec import save_avif, QUALITY, SPEED, encoder_version

NATIVE_PREVIEW_QUALITY = QUALITY


@dataclass(frozen=True)
class RuntimeExport:
    target: str
    source: Path
    info: dict


RUNTIME_ROOT = 'assets/runtime-images/'
RUNTIME_QUALITY = QUALITY
RUNTIME_ALPHA_QUALITY = 100
RUNTIME_FOLDERS = {
    'assets/jungle-book/portraits',
    'assets/jungle-book/pages',
    'assets/jungle-book/previews',
    'assets/jungle-book/items',
    'assets/collectibles',
    'assets/shapes/wooden',
    'assets/drums/pictures',
    'assets/hide_seek/scenes',
    'assets/hide_seek/props',
    'assets/jigsaw',
}

# Approved Farm scenes and field layers are already app-ready exports. Keep
# their native resolution and lossless alpha, without another lossy encode.
APP_READY_FARM_AVIF = {
    'assets/garden/art/scene-landscape.avif',
    'assets/garden/art/scene-portrait.avif',
}

# Full runtime assets are reused; these folders also receive explicit previews.
PHOTO_FOLDERS = {'assets/jungle-book/portraits', 'assets/jungle-book/pages', 'assets/jungle-book/previews',
                 'assets/jigsaw', 'assets/jungle/title'}
LOSSLESS_PNG_FOLDERS = {'assets/jungle-book/items', 'assets/hide_seek/props',
                        'assets/hide_seek/scenes', 'assets/drums/pictures'}
WEB_PHOTO_FOLDERS = {'assets/jungle/title'}
PREVIEW_FOLDERS = PHOTO_FOLDERS | LOSSLESS_PNG_FOLDERS
PREVIEW_PIXELS = 128
PREVIEW_QUALITY = NATIVE_PREVIEW_QUALITY


def _alpha(image):
    return image.convert('RGBA').getchannel('A').getextrema()[0] < 255


def _digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _export(source, cache, *, preview=False):
    source, cache = Path(source), Path(cache)
    if source.suffix.lower() == '.avif' and not preview:
        with Image.open(source) as image:
            assert image.format == 'AVIF'
        return source
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f'{_digest(source)}-avif-q{QUALITY}-s{SPEED}-preview{preview}-{encoder_version()}-v1'.encode()).hexdigest()
    target = cache / (key + '.avif')
    if not target.exists():
        with Image.open(source) as original:
            picture = ImageOps.exif_transpose(original).convert('RGBA')
            alpha = _alpha(picture)
            if not alpha:
                picture = picture.convert('RGB')
            if preview:
                picture.thumbnail((PREVIEW_PIXELS, PREVIEW_PIXELS), Image.Resampling.LANCZOS)
            save_avif(picture, target, lossless=alpha)
    return target


def native_preview_sources(files):
    return {name: source for name, source in files.items()
            if str(Path(name).parent) in PREVIEW_FOLDERS
            and Path(name).suffix in ('.avif', '.png')}


def prepare_previews(files, cache):
    wanted = {name: source for name, source in native_preview_sources(files).items()
              if name not in APP_READY_FARM_AVIF}
    with ThreadPoolExecutor(max_workers=2) as pool:
        return dict(pool.map(lambda item: (item[0], _export(item[1], cache, preview=True)),
                             sorted(wanted.items())))


PREVIEW_ROOT = 'assets/previews/'


def preview_path(name):
    assert name.startswith('assets/') and not name.startswith(PREVIEW_ROOT), name
    return PREVIEW_ROOT + str(Path(name[len('assets/'):]).with_suffix('.avif'))


def prepare_native_previews(files, cache):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = dict(pool.map(lambda item: (preview_path(item[0]), _export(item[1], cache, preview=True)),
                               sorted(native_preview_sources(files).items())))
    used = set(result.values())
    for path in cache.iterdir():
        if path.is_file() and path not in used:
            path.unlink()
    return result


def runtime_size(name, size):
    """Every runtime AVIF keeps its full dimensions; previews are separate."""
    return tuple(size)


def prepare_runtime_images(files, cache):
    wanted = sorted((name, Path(source)) for name, source in files.items()
                    if str(Path(name).parent) in RUNTIME_FOLDERS
                    and Path(name).suffix in ('.avif', '.png')
                    and name not in APP_READY_FARM_AVIF)
    def convert(item):
        name, source = item
        target = _export(source, cache)
        with Image.open(source) as original, Image.open(target) as decoded:
            assert decoded.format == 'AVIF' and decoded.size == original.size, name
            alpha = _alpha(original)
            if alpha:
                assert decoded.getchannel('A').tobytes() == original.getchannel('A').tobytes(), name
            reuse = source == target
            info = {'encoding': 'avif', 'source_path': name, 'source_sha256': _digest(source),
                    'source_bytes': source.stat().st_size, 'runtime_bytes': target.stat().st_size,
                    'width': original.width, 'height': original.height,
                    'runtime_width': decoded.width, 'runtime_height': decoded.height,
                    'quality': None if reuse or alpha else QUALITY, 'reused_source': reuse,
                    'long_edge': max(original.size), 'alpha_quality': 100, 'alpha': alpha}
            if alpha:
                info['alpha_sha256'] = hashlib.sha256(original.getchannel('A').tobytes()).hexdigest()
        return name, RuntimeExport(RUNTIME_ROOT+_digest(target)+'.avif', target, info)
    with ThreadPoolExecutor(max_workers=2) as pool:
        return dict(pool.map(convert, wanted))


def prepare_web_images(files, cache, force_title=False):
    result, archive_names, metadata = dict(files), {}, {}
    for name, source in sorted(files.items()):
        if str(Path(name).parent) not in WEB_PHOTO_FOLDERS or Path(name).suffix not in ('.avif', '.png'):
            continue
        target = _export(source, cache)
        result[name] = target
        if target != source:
            archive_names[name] = str(Path(name).with_suffix('.avif'))
            with Image.open(target) as decoded:
                metadata[name] = {'encoding': 'avif', 'source_path': name, 'source_sha256': _digest(source),
                                  'source_bytes': Path(source).stat().st_size, 'runtime_bytes': target.stat().st_size,
                                  'width': decoded.width, 'height': decoded.height, 'quality': QUALITY,
                                  'long_edge': max(decoded.size), 'alpha_quality': 100}
    return result, archive_names, metadata

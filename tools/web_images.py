"""Prepare reviewed runtime photo encodings and every host's small preview
pictures; keep canonical artwork intact."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import hashlib
import shutil
from pathlib import Path
import tempfile

from PIL import Image, ImageOps, __version__ as pillow_version, features

NATIVE_PREVIEW_QUALITY = 60


@dataclass(frozen=True)
class RuntimeRule:
    long_edge: int
    quality: int


@dataclass(frozen=True)
class RuntimeExport:
    target: str
    source: Path
    info: dict


RUNTIME_ROOT = 'assets/runtime-images/'
RUNTIME_QUALITY = 85
RUNTIME_ALPHA_QUALITY = 100
RUNTIME_RULES = {
    'assets/jungle-book/portraits': RuntimeRule(1536, RUNTIME_QUALITY),
    'assets/jungle-book/pages': RuntimeRule(1024, RUNTIME_QUALITY),
    'assets/jungle-book/previews': RuntimeRule(512, RUNTIME_QUALITY),
    'assets/jungle-book/items': RuntimeRule(1024, RUNTIME_QUALITY),
    'assets/collectibles': RuntimeRule(1024, RUNTIME_QUALITY),
    'assets/garden/art': RuntimeRule(1024, RUNTIME_QUALITY),
    'assets/shapes/wooden': RuntimeRule(1024, RUNTIME_QUALITY),
    'assets/drums/pictures': RuntimeRule(1024, RUNTIME_QUALITY),
    'assets/hide_seek/scenes': RuntimeRule(1024, RUNTIME_QUALITY),
    'assets/hide_seek/props': RuntimeRule(1024, RUNTIME_QUALITY),
    'assets/jigsaw': RuntimeRule(1200, RUNTIME_QUALITY),
}

# Approved Farm scenes and sign layers are already app-ready exports. Keep
# their native resolution and lossless alpha, without another lossy encode.
APP_READY_FARM_WEBP = {
    'assets/garden/art/scene-landscape.webp',
    'assets/garden/art/scene-portrait.webp',
    'assets/garden/art/campus-sign.webp',
    'assets/garden/art/campus-sign-glow.webp',
}

# These folders receive previews. Runtime WebP replaces the former lossless
# PNG copies; title art remains host-only and browser-encoded.
PHOTO_FOLDERS = {'assets/jungle-book/portraits', 'assets/jungle-book/pages', 'assets/jungle-book/previews',
                 'assets/jigsaw', 'assets/jungle/title'}
LOSSLESS_PNG_FOLDERS = {'assets/jungle-book/items', 'assets/hide_seek/props',
                        'assets/hide_seek/scenes', 'assets/drums/pictures'}
WEB_PHOTO_FOLDERS = {'assets/jungle/title'}
WEBP_QUALITY = RUNTIME_QUALITY
WEBP_LONG_EDGE = 2048
PREVIEW_FOLDERS = PHOTO_FOLDERS | LOSSLESS_PNG_FOLDERS
PREVIEW_PIXELS = 128
PREVIEW_QUALITY = NATIVE_PREVIEW_QUALITY


def _alpha(image):
    return image.mode in ('RGBA', 'LA', 'PA') or (
        image.mode == 'P' and 'transparency' in image.info)


def prepare_previews(files, cache):
    """{logical path: cached preview WebP} for every previewed picture."""
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    version = pillow_version + '-' + str(features.version('webp'))

    def convert(item):
        name, source = item
        digest = hashlib.sha256(Path(source).read_bytes()).hexdigest()
        with Image.open(source) as image:
            alpha = _alpha(image)
        mode = 'RGBA' if alpha else 'RGB'
        key = hashlib.sha256(
            f'preview-{digest}-{version}-{PREVIEW_PIXELS}-{PREVIEW_QUALITY}-{mode}'.encode()
        ).hexdigest()
        target = cache/(key+'.webp')
        if not target.exists():
            with Image.open(source) as image:
                picture = image.convert(mode)
                picture.thumbnail((PREVIEW_PIXELS, PREVIEW_PIXELS), Image.Resampling.LANCZOS)
                with tempfile.NamedTemporaryFile(dir=cache, suffix='.webp', delete=False) as temporary:
                    staged = Path(temporary.name)
                try:
                    picture.save(staged, 'WEBP', quality=PREVIEW_QUALITY, method=6, exact=alpha)
                    staged.replace(target)
                finally:
                    staged.unlink(missing_ok=True)
        return name, target

    wanted = sorted((name, source) for name, source in files.items()
                    if str(Path(name).parent) in PREVIEW_FOLDERS
                    and Path(name).suffix in ('.webp', '.png')
                    and name not in APP_READY_FARM_WEBP)
    with ThreadPoolExecutor(max_workers=2) as pool:
        return dict(pool.map(convert, wanted))


PREVIEW_ROOT = 'assets/previews/'


def preview_path(name):
    """The path of NAME's WebP preview."""
    assert name.startswith('assets/') and not name.startswith(PREVIEW_ROOT), name
    return PREVIEW_ROOT + str(Path(name[len('assets/'):]).with_suffix('.webp'))


def native_preview_sources(files):
    """{picture: source} for the pictures in FILES that get previews."""
    return {name: source for name, source in files.items()
            if str(Path(name).parent) in PREVIEW_FOLDERS
            and Path(name).suffix in ('.webp', '.png')}


def prepare_native_previews(files, cache):
    """{preview path: cached file} for every picture in PREVIEW_FOLDERS."""
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    settings = (f'native-preview-webp-{pillow_version}-{features.version("webp")}'
                f'-{PREVIEW_PIXELS}-{NATIVE_PREVIEW_QUALITY}')

    def convert(item):
        name, source = item
        digest = hashlib.sha256(Path(source).read_bytes()).hexdigest()
        target = cache/(hashlib.sha256(
            f'{settings}-{digest}{Path(name).suffix}'.encode()).hexdigest()+'.webp')
        if not target.exists():
            with Image.open(source) as image:
                alpha = _alpha(image)
                picture = image.convert('RGBA' if alpha else 'RGB')
                picture.thumbnail((PREVIEW_PIXELS, PREVIEW_PIXELS), Image.Resampling.LANCZOS)
            with tempfile.NamedTemporaryFile(dir=cache, suffix='.webp', delete=False) as temporary:
                staged = Path(temporary.name)
            try:
                picture.save(staged, 'WEBP', quality=NATIVE_PREVIEW_QUALITY, method=6, exact=alpha)
                staged.replace(target)
            finally:
                staged.unlink(missing_ok=True)
        return preview_path(name), target

    with ThreadPoolExecutor(max_workers=2) as pool:
        previews = dict(pool.map(convert, sorted(native_preview_sources(files).items())))
    used = set(previews.values())
    for path in cache.iterdir():
        if path.is_file() and path not in used:
            path.unlink()
    return previews


def prepare_runtime_images(files, cache):
    """Export optimized runtime WebP derivatives without touching sources."""
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    version = pillow_version + '-' + str(features.version('webp'))
    wanted = sorted((name, Path(source)) for name, source in files.items()
                    if str(Path(name).parent) in RUNTIME_RULES
                    and Path(name).suffix in ('.webp', '.png')
                    and name not in APP_READY_FARM_WEBP)

    def convert(item):
        name, source = item
        rule = RUNTIME_RULES[str(Path(name).parent)]
        source_bytes = source.read_bytes()
        digest = hashlib.sha256(source_bytes).hexdigest()
        settings = f'runtime-reuse-webp-{rule.long_edge}-{rule.quality}-{RUNTIME_ALPHA_QUALITY}'
        key = hashlib.sha256((digest+version+settings).encode()).hexdigest()
        target = cache/(key+'.webp')
        if target.exists() and (target.stat().st_size < 12
                                or target.read_bytes()[:4] != b'RIFF'
                                or target.read_bytes()[8:12] != b'WEBP'):
            target.unlink()
        with Image.open(source) as image:
            picture = ImageOps.exif_transpose(image)
            width, height = picture.size
            alpha = _alpha(picture)
            reuse = source.suffix.lower() == '.webp' and max(picture.size) <= rule.long_edge
            picture = picture.convert('RGBA' if alpha else 'RGB')
            picture.thumbnail((rule.long_edge, rule.long_edge), Image.Resampling.LANCZOS)
            expected_size = picture.size
            expected_alpha = picture.getchannel('A').tobytes() if alpha else b''
            if not target.exists():
                with tempfile.NamedTemporaryFile(dir=cache, suffix='.webp', delete=False) as temporary:
                    staged = Path(temporary.name)
                try:
                    if reuse:
                        shutil.copyfile(source, staged)
                    else:
                        picture.save(staged, 'WEBP', quality=rule.quality, lossless=False,
                                     exact=True, alpha_quality=RUNTIME_ALPHA_QUALITY, method=6)
                    staged.replace(target)
                finally:
                    staged.unlink(missing_ok=True)
        with Image.open(target) as decoded:
            decoded.load()
            runtime_size = target.stat().st_size
            if runtime_size >= len(source_bytes) and not reuse:
                target.unlink(missing_ok=True)
                return name, None
            payload_digest = hashlib.sha256(target.read_bytes()).hexdigest()
            info = {
                'encoding': 'webp', 'source_path': name, 'source_sha256': digest,
                'source_bytes': len(source_bytes), 'runtime_bytes': runtime_size,
                'width': width, 'height': height,
                'runtime_width': decoded.width, 'runtime_height': decoded.height,
                'quality': None if reuse else rule.quality, 'reused_source': reuse, 'long_edge': rule.long_edge,
                'alpha_quality': RUNTIME_ALPHA_QUALITY, 'alpha': alpha,
            }
            if alpha:
                info['alpha_sha256'] = hashlib.sha256(expected_alpha).hexdigest()
            has_alpha = decoded.mode == 'RGBA'
            minimum_alpha = decoded.getchannel('A').getextrema()[0] if has_alpha else 255
        assert max(info['runtime_width'], info['runtime_height']) <= rule.long_edge, name
        assert (info['runtime_width'], info['runtime_height']) == expected_size, name
        assert has_alpha == alpha and (not alpha or minimum_alpha == 0), name
        assert (not alpha or hashlib.sha256(
            decoded.getchannel('A').tobytes()).hexdigest() == info['alpha_sha256']), name
        return name, RuntimeExport(RUNTIME_ROOT+payload_digest+'.webp', target, info)

    with ThreadPoolExecutor(max_workers=2) as pool:
        pairs = list(pool.map(convert, wanted))
    exports = {name: export for name, export in pairs if export is not None}
    used = {export.source for export in exports.values()}
    for path in cache.iterdir():
        if path.is_file() and path not in used:
            path.unlink()
    return exports


def prepare_web_images(files, cache, force_title=False):
    """Encode browser-only title photos; staged runtime WebP is reused as-is."""
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    version = pillow_version + '-' + str(features.version('webp'))

    def convert(item):
        name, source = item
        source = Path(source)
        parent = str(Path(name).parent)
        if source.suffix.lower() == '.webp':
            if parent not in WEB_PHOTO_FOLDERS:
                return name, source, None
            with Image.open(source) as image:
                if max(image.size) <= WEBP_LONG_EDGE:
                    return name, source, None
        suffix = Path(name).suffix
        if parent not in WEB_PHOTO_FOLDERS or suffix not in ('.webp', '.png'):
            return name, source, None
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        settings = f'browser-{WEBP_LONG_EDGE}-{WEBP_QUALITY}'
        key = hashlib.sha256((digest+version+settings).encode()).hexdigest()
        target = cache/(key+'.webp')
        if target.exists() and (target.stat().st_size < 12
                                or target.read_bytes()[:4] != b'RIFF'
                                or target.read_bytes()[8:12] != b'WEBP'):
            target.unlink()
        if not target.exists():
            with Image.open(source) as image:
                alpha = _alpha(image)
                picture = image.convert('RGBA' if alpha else 'RGB')
                picture.thumbnail((WEBP_LONG_EDGE, WEBP_LONG_EDGE), Image.Resampling.LANCZOS)
                with tempfile.NamedTemporaryFile(dir=cache, suffix='.webp', delete=False) as temporary:
                    staged = Path(temporary.name)
                try:
                    picture.save(staged, 'WEBP', quality=WEBP_QUALITY, method=6,
                                 exact=True, alpha_quality=RUNTIME_ALPHA_QUALITY)
                    staged.replace(target)
                finally:
                    staged.unlink(missing_ok=True)
        original_size = source.stat().st_size
        forced = force_title and parent == 'assets/jungle/title'
        if target.stat().st_size >= original_size and not forced:
            target.unlink(missing_ok=True)
            return name, source, None
        with Image.open(target) as decoded:
            width, height = decoded.size
        info = {'encoding': 'webp', 'source_path': name, 'source_sha256': digest,
                'source_bytes': original_size, 'runtime_bytes': target.stat().st_size,
                'width': width, 'height': height, 'quality': WEBP_QUALITY,
                'long_edge': WEBP_LONG_EDGE, 'alpha_quality': RUNTIME_ALPHA_QUALITY}
        return name, target, info

    result, archive_names, metadata = dict(files), {}, {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        for name, path, info in pool.map(convert, sorted(files.items())):
            result[name] = path
            if info:
                archive_names[name] = str(Path(name).with_suffix('.webp'))
                metadata[name] = info
    before = sum(info['source_bytes'] for info in metadata.values())
    after = sum(result[name].stat().st_size for name in metadata)
    print(f'Browser-only WebP: {len(metadata)} quality-{WEBP_QUALITY} pictures, '
          f'{before/1_000_000:.1f} → {after/1_000_000:.1f} MB; '
          'runtime exports reused unchanged', flush=True)
    return result, archive_names, metadata

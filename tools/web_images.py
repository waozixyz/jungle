"""Prepare reviewed web-only photo encodings and every host's small preview
pictures; keep canonical artwork intact."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import tempfile

from PIL import Image, __version__ as pillow_version, features

PHOTO_FOLDERS = {'assets/jungle-book/pages', 'assets/jungle-book/previews', 'assets/jigsaw', 'assets/jungle/title'}
LOSSLESS_PNG_FOLDERS = {'assets/jungle-book/items', 'assets/hide_seek/props',
                        'assets/hide_seek/scenes', 'assets/drums/pictures'}
WEBP_QUALITY = 90
# Every picture drawn whole first appears as a few-KB picture while its full
# bytes download: book pages and covers, cut-outs, hiding places and their
# scenes, and the Music Room's pictures. Cut-outs keep their transparency, so
# a stand-in never shows a white box. Jigsaw pictures have one too: Kryon maps
# each piece's full-size source rectangle onto it (ImageProps.full_size).
PREVIEW_FOLDERS = PHOTO_FOLDERS | LOSSLESS_PNG_FOLDERS
PREVIEW_PIXELS = 128
PREVIEW_QUALITY = 50


def prepare_previews(files, cache):
    """{logical path: cached preview WebP} for every picture in PREVIEW_FOLDERS.

    Previews keep each picture's aspect ratio at PREVIEW_PIXELS on its longer
    side. Their names are their SHA-256, so identical previews share a file
    and a browser never mistakes one build's preview for another's.
    """
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    version = pillow_version + '-' + str(features.version('webp'))

    def convert(item):
        name, source = item
        digest = hashlib.sha256(Path(source).read_bytes()).hexdigest()
        with Image.open(source) as image:
            alpha = image.mode in ('RGBA', 'LA', 'PA') or (image.mode == 'P' and 'transparency' in image.info)
        mode = 'RGBA' if alpha else 'RGB'
        key = hashlib.sha256(f'preview-{digest}-{version}-{PREVIEW_PIXELS}-{PREVIEW_QUALITY}-{mode}'.encode()).hexdigest()
        target = cache/(key+'.webp')
        if not target.exists():
            with Image.open(source) as image:
                picture = image.convert(mode)
                picture.thumbnail((PREVIEW_PIXELS, PREVIEW_PIXELS), Image.Resampling.LANCZOS)
                with tempfile.NamedTemporaryFile(dir=cache, suffix='.webp', delete=False) as temporary:
                    staged = Path(temporary.name)
                try:
                    # exact keeps the colors under transparent pixels, so a
                    # smoothly scaled stand-in has no dark fringe.
                    picture.save(staged, 'WEBP', quality=PREVIEW_QUALITY, method=6, exact=alpha)
                    staged.replace(target)
                finally:
                    staged.unlink(missing_ok=True)
        return name, target

    wanted = sorted((name, source) for name, source in files.items()
                    if str(Path(name).parent) in PREVIEW_FOLDERS and Path(name).suffix in ('.jpg', '.png'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        return dict(pool.map(convert, wanted))


# Every host finds a picture's preview at one path: PREVIEW_ROOT, then the
# picture's path after "assets/" (Kryon ImageProps.preview_path). The browser
# writes its WebP preview there; desktop and Android install these files.
PREVIEW_ROOT = 'assets/previews/'
NATIVE_PREVIEW_QUALITY = 60


def preview_path(name):
    """The path of NAME's preview, such as assets/previews/jigsaw/garden.jpg."""
    assert name.startswith('assets/') and not name.startswith(PREVIEW_ROOT), name
    return PREVIEW_ROOT + name[len('assets/'):]


def native_preview_sources(files):
    """{picture: source} for the pictures in FILES that get previews."""
    return {name: source for name, source in files.items()
            if str(Path(name).parent) in PREVIEW_FOLDERS and Path(name).suffix in ('.jpg', '.png')}


def prepare_native_previews(files, cache):
    """{preview path: cached file} for every picture in PREVIEW_FOLDERS.

    Desktop and Android decode the same formats as the pictures themselves,
    so each preview keeps its picture's format and name: a JPEG for a .jpg, a
    PNG for a .png, with its transparency, so a cut-out's stand-in never shows
    a box. Previews keep the aspect ratio at PREVIEW_PIXELS on the longer
    side. A cached file is named by the SHA-256 of its picture's bytes and
    these settings, so a changed picture gets a new preview; files no current
    picture uses leave CACHE, which stays as large as one set of previews.
    """
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    settings = f'native-preview-{pillow_version}-{PREVIEW_PIXELS}-{NATIVE_PREVIEW_QUALITY}'

    def convert(item):
        name, source = item
        suffix = Path(name).suffix
        digest = hashlib.sha256(Path(source).read_bytes()).hexdigest()
        target = cache/(hashlib.sha256(f'{settings}-{digest}{suffix}'.encode()).hexdigest()+suffix)
        if not target.exists():
            with Image.open(source) as image:
                alpha = image.mode in ('RGBA', 'LA', 'PA') or (image.mode == 'P' and 'transparency' in image.info)
                picture = image.convert('RGBA' if alpha and suffix == '.png' else 'RGB')
                picture.thumbnail((PREVIEW_PIXELS, PREVIEW_PIXELS), Image.Resampling.LANCZOS)
            with tempfile.NamedTemporaryFile(dir=cache, suffix=suffix, delete=False) as temporary:
                staged = Path(temporary.name)
            try:
                if suffix == '.jpg':
                    picture.save(staged, 'JPEG', quality=NATIVE_PREVIEW_QUALITY, optimize=True)
                else:
                    picture.save(staged, 'PNG', optimize=True)
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

def prepare_web_images(files, cache):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    version = pillow_version + '-' + str(features.version('webp'))

    def convert(item):
        name, source = item
        parent = str(Path(name).parent)
        suffix = Path(name).suffix
        photo = parent in PHOTO_FOLDERS and suffix == '.jpg'
        lossless = parent in LOSSLESS_PNG_FOLDERS and suffix == '.png'
        if not photo and not lossless:
            return name, source, None
        digest = hashlib.sha256(Path(source).read_bytes()).hexdigest()
        settings = str(WEBP_QUALITY) if photo else 'lossless-exact'
        key = hashlib.sha256((digest+version+settings).encode()).hexdigest()
        target = cache/(key+'.webp')
        with Image.open(source) as image:
            if lossless and image.mode not in ('RGB', 'RGBA'):
                return name, source, None
            if not target.exists():
                with tempfile.NamedTemporaryFile(dir=cache, suffix='.webp', delete=False) as temporary:
                    staged=Path(temporary.name)
                try:
                    if photo:
                        image.convert('RGB').save(staged, 'WEBP', quality=WEBP_QUALITY,
                                                  lossless=False, exact=True, method=4)
                    else:
                        image.save(staged, 'WEBP', lossless=True, exact=True, method=6)
                    staged.replace(target)
                finally:
                    staged.unlink(missing_ok=True)
            width, height = image.size
        original_size = Path(source).stat().st_size
        if target.stat().st_size >= original_size:
            return name, source, None
        info={'encoding': 'webp', 'source_sha256': digest, 'source_bytes': original_size,
              'width': width, 'height': height}
        if photo: info['quality'] = WEBP_QUALITY
        else: info['lossless'] = True
        return name, target, info

    result, archive_names, metadata = dict(files), {}, {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        for name, path, info in pool.map(convert, sorted(files.items())):
            result[name] = path
            if info:
                archive_names[name] = str(Path(name).with_suffix('.webp'))
                metadata[name] = info
    lossless_count = sum(info.get('lossless', False) for info in metadata.values())
    before = sum(info['source_bytes'] for info in metadata.values())
    after = sum(result[name].stat().st_size for name in metadata)
    print(f'Web-only WebP: {len(metadata)-lossless_count} quality-{WEBP_QUALITY} photos and '
          f'{lossless_count} exact textures, {before/1_000_000:.1f} → {after/1_000_000:.1f} MB; '
          'originals unchanged', flush=True)
    return result, archive_names, metadata

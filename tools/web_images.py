"""Prepare reviewed web-only photo encodings; keep canonical artwork intact."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import tempfile

from PIL import Image, __version__ as pillow_version, features

PHOTO_FOLDERS = {'assets/jungle-book/pages', 'assets/jungle-book/previews', 'assets/jigsaw'}
WEBP_QUALITY = 90
# Book pages and covers first appear as a few-KB picture while their full
# bytes download. Jigsaw pieces need full-size pixels, so they have none.
PREVIEW_FOLDERS = {'assets/jungle-book/pages', 'assets/jungle-book/previews'}
PREVIEW_PIXELS = 128
PREVIEW_QUALITY = 50


def prepare_previews(files, cache):
    """{logical path: cached preview WebP} for every book page and cover.

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
        key = hashlib.sha256(f'preview-{digest}-{version}-{PREVIEW_PIXELS}-{PREVIEW_QUALITY}'.encode()).hexdigest()
        target = cache/(key+'.webp')
        if not target.exists():
            with Image.open(source) as image:
                picture = image.convert('RGB')
                picture.thumbnail((PREVIEW_PIXELS, PREVIEW_PIXELS), Image.Resampling.LANCZOS)
                with tempfile.NamedTemporaryFile(dir=cache, suffix='.webp', delete=False) as temporary:
                    staged = Path(temporary.name)
                try:
                    picture.save(staged, 'WEBP', quality=PREVIEW_QUALITY, method=6)
                    staged.replace(target)
                finally:
                    staged.unlink(missing_ok=True)
        return name, target

    wanted = sorted((name, source) for name, source in files.items()
                    if str(Path(name).parent) in PREVIEW_FOLDERS and Path(name).suffix == '.jpg')
    with ThreadPoolExecutor(max_workers=2) as pool:
        return dict(pool.map(convert, wanted))


def prepare_web_images(files, cache):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    version = pillow_version + '-' + str(features.version('webp'))

    def convert(item):
        name, source = item
        if str(Path(name).parent) not in PHOTO_FOLDERS or Path(name).suffix != '.jpg':
            return name, source, None
        digest = hashlib.sha256(Path(source).read_bytes()).hexdigest()
        key = hashlib.sha256((digest+version+str(WEBP_QUALITY)).encode()).hexdigest()
        target = cache/(key+'.webp')
        with Image.open(source) as image:
            if not target.exists():
                with tempfile.NamedTemporaryFile(dir=cache, suffix='.webp', delete=False) as temporary:
                    staged=Path(temporary.name)
                try:
                    image.convert('RGB').save(staged, 'WEBP', quality=WEBP_QUALITY,
                                              lossless=False, exact=True, method=4)
                    staged.replace(target)
                finally:
                    staged.unlink(missing_ok=True)
            width, height = image.size
        original_size = Path(source).stat().st_size
        if target.stat().st_size >= original_size:
            return name, source, None
        return name, target, {'encoding': 'webp', 'quality': WEBP_QUALITY,
                              'source_sha256': digest, 'source_bytes': original_size,
                              'width': width, 'height': height}

    result, archive_names, metadata = dict(files), {}, {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        for name, path, info in pool.map(convert, sorted(files.items())):
            result[name] = path
            if info:
                archive_names[name] = str(Path(name).with_suffix('.webp'))
                metadata[name] = info
    before = sum(info['source_bytes'] for info in metadata.values())
    after = sum(result[name].stat().st_size for name in metadata)
    print(f'Web-only quality-{WEBP_QUALITY} WebP: {len(metadata)} photos, '
          f'{before/1_000_000:.1f} → {after/1_000_000:.1f} MB; originals unchanged', flush=True)
    return result, archive_names, metadata

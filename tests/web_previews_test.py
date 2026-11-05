"""Few-KB stand-ins for every whole picture (tools/web_images.py prepare_previews).

Real shipped pictures from each preview folder become small AVIF previews of
the same aspect ratio. Cut-outs keep their transparency, so a stand-in never
shows a white box, and photos stay opaque. Jigsaw pictures get one as well,
since Kryon maps each piece's source onto it. Each folder's previews share
their own pack name.
"""
from pathlib import Path
import sys
import tempfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from web_images import (PREVIEW_FOLDERS, PREVIEW_PIXELS, prepare_native_previews, prepare_previews,  # noqa: E402
                        preview_path)
from build_web import preview_group  # noqa: E402

samples = {}
for folder in sorted(PREVIEW_FOLDERS):
    for path in sorted((ROOT/folder).iterdir())[:2]:
        if path.suffix in ('.avif', '.png'):
            samples[f'{folder}/{path.name}'] = path
for folder in ('assets/jungle-book/items', 'assets/hide_seek/props', 'assets/hide_seek/scenes', 'assets/drums/pictures', 'assets/jigsaw', 'assets/jungle/title'):
    assert folder in PREVIEW_FOLDERS, folder

(ROOT/'work').mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='preview-test-', dir=ROOT/'work') as cache:
    previews = prepare_previews(samples, cache)
    assert any(name.startswith('assets/jigsaw/') for name in previews), sorted(previews)
    transparent = 0
    for name, source in samples.items():
        preview = previews[name]
        with Image.open(source) as original, Image.open(preview) as small:
            assert small.format == 'AVIF', name
            assert max(small.size) == min(PREVIEW_PIXELS, max(original.size)), (name, small.size)
            assert abs(small.size[0] / small.size[1] - original.size[0] / original.size[1]) < 0.05, name
            source_alpha = original.mode in ('RGBA', 'LA') or 'transparency' in original.info
            if source_alpha:
                lowest = original.convert('RGBA').getchannel('A').getextrema()[0]
                assert small.mode == 'RGBA', (name, small.mode)
                expected = original.convert('RGBA')
                expected.thumbnail((PREVIEW_PIXELS, PREVIEW_PIXELS), Image.Resampling.LANCZOS)
                assert small.convert('RGBA').tobytes() == expected.tobytes(), name
                if lowest == 0:
                    assert small.getchannel('A').getextrema()[0] < 16, (name, 'transparency lost')
                    transparent += 1
            else:
                assert small.mode == 'RGB', (name, small.mode)
        assert preview.stat().st_size < (40_000 if source_alpha else 12_000), (name, preview.stat().st_size)
    assert transparent >= 2, transparent

# Desktop and Android previews: the picture's own format at the one preview
# path every host uses, transparency kept, from a cache holding one set.
assert preview_path('assets/jigsaw/garden.avif') == 'assets/previews/jigsaw/garden.avif'
with tempfile.TemporaryDirectory(prefix='native-preview-test-', dir=ROOT/'work') as scratch:
    cache = Path(scratch)/'cache'
    native = prepare_native_previews(samples, cache)
    assert set(native) == {preview_path(name) for name in samples}, sorted(native)
    assert any(name.startswith('assets/previews/jigsaw/') for name in native)
    native_transparent = 0
    for name, source in samples.items():
        preview = native[preview_path(name)]
        with Image.open(source) as original, Image.open(preview) as small:
            assert small.format == 'AVIF', (name, small.format)
            assert max(small.size) == min(PREVIEW_PIXELS, max(original.size)), (name, small.size)
            source_alpha = original.mode in ('RGBA', 'LA') or 'transparency' in original.info
            if source_alpha:
                assert small.mode == 'RGBA', (name, small.mode)
                expected = original.convert('RGBA')
                expected.thumbnail((PREVIEW_PIXELS, PREVIEW_PIXELS), Image.Resampling.LANCZOS)
                assert small.convert('RGBA').tobytes() == expected.tobytes(), name
                if original.convert('RGBA').getchannel('A').getextrema()[0] == 0:
                    assert small.getchannel('A').getextrema()[0] < 16, (name, 'transparency lost')
                    native_transparent += 1
        assert preview.stat().st_size < 40_000, (name, preview.stat().st_size)
    assert native_transparent >= 2, native_transparent
    # Unchanged pictures reuse their files; a changed one gets a new file and
    # files nobody uses leave the cache.
    first = sorted(cache.iterdir())
    assert prepare_native_previews(samples, cache) == native and sorted(cache.iterdir()) == first
    one = sorted(samples)[0]
    changed = Path(scratch)/('changed' + Path(one).suffix)
    with Image.open(samples[one]) as image:
        image.rotate(90).save(changed)
    again = prepare_native_previews({one: changed}, cache)
    assert list(again) == [preview_path(one)] and again[preview_path(one)] != native[preview_path(one)]
    assert sorted(cache.iterdir()) == [again[preview_path(one)]], sorted(cache.iterdir())
assert preview_group('assets/hide_seek/scenes/cottage-yard.avif') == 'hide-seek-scenes'
assert preview_group('assets/jungle-book/items/alpaca.avif') == 'jungle-book-items'
assert preview_group('assets/jigsaw/garden.avif') == 'jigsaw'
assert preview_group('assets/jungle/title/treehouse.avif') == 'jungle-title'
print(f'local web preview test: {len(previews)} stand-ins from {len(PREVIEW_FOLDERS)} folders, '
      f'{transparent} transparent cut-outs kept, jigsaw included; {len(native)} desktop/Android previews, '
      f'{native_transparent} transparent')

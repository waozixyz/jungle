"""Runtime image exports are real, capped, smaller WebP with provenance."""
from pathlib import Path
import hashlib
import sys
import tempfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from web_images import prepare_runtime_images, APP_READY_FARM_WEBP


def main():
    with tempfile.TemporaryDirectory(prefix='runtime-images-', dir=ROOT / 'work') as directory:
        root = Path(directory)
        source = root / 'source'
        cache = root / 'cache'
        page = source / 'assets/jungle-book/pages/large.webp'
        cutout = source / 'assets/hide_seek/props/cutout.png'
        for path in (page, cutout):
            path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (2000, 1200), (180, 90, 30)).save(page, 'WEBP', quality=95)
        alpha = Image.new('RGBA', (1400, 900), (30, 120, 70, 255))
        alpha.paste((0, 0, 0, 0), (0, 0, 700, 900))
        alpha.save(cutout, 'PNG')
        stale = cache / 'stale.webp'
        cache.mkdir()
        stale.write_bytes(b'not-webp')

        exports = prepare_runtime_images({
            page.relative_to(source).as_posix(): page,
            cutout.relative_to(source).as_posix(): cutout,
        }, cache)
        assert stale.exists() is False and len(exports) == 2
        for name, path, long_edge, has_alpha in (
                ('assets/jungle-book/pages/large.webp', page, 1024, False),
                ('assets/hide_seek/props/cutout.png', cutout, 1024, True)):
            export = exports[name]
            payload = export.source.read_bytes()
            assert payload[:4] == b'RIFF' and payload[8:12] == b'WEBP'
            assert len(payload) < path.stat().st_size
            assert export.info['source_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
            assert export.info['source_path'] == name and export.info['quality'] == 85
            with Image.open(export.source) as decoded:
                decoded.load()
                assert decoded.format == 'WEBP' and decoded.mode == ('RGBA' if has_alpha else 'RGB')
                assert max(decoded.size) <= long_edge and decoded.size == (
                    export.info['runtime_width'], export.info['runtime_height'])
                if has_alpha:
                    assert decoded.getchannel('A').getextrema()[0] == 0
            assert export.target.startswith('assets/runtime-images/')
            assert export.target.endswith(hashlib.sha256(payload).hexdigest() + '.webp')

        assert all(export.source.exists() for export in exports.values())
        # A canonical WebP already within the cap ships byte for byte, avoiding
        # another lossy generation merely because its source format changed.
        small = source / 'assets/jigsaw/ready.webp'
        small.parent.mkdir(parents=True)
        Image.new('RGB', (600, 400), (90, 150, 60)).save(small, 'WEBP', quality=90)
        name = small.relative_to(source).as_posix()
        reused = prepare_runtime_images({name: small}, cache)[name]
        assert reused.info['reused_source'] and reused.info['quality'] is None
        assert reused.source.read_bytes() == small.read_bytes()

        # App-ready Farm WebPs bypass derivative staging; normal bundling uses
        # these approved native-resolution/lossless files unchanged.
        farm = {name: ROOT/name for name in APP_READY_FARM_WEBP}
        assert prepare_runtime_images(farm, cache) == {}

    print('local runtime image test: real capped WebP, alpha, magic and provenance passed')


if __name__ == '__main__':
    main()

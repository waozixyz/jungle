"""Runtime AVIF staging preserves exact alpha, full dimensions and independent previews."""
from pathlib import Path
import hashlib
import sys
import tempfile
from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from avif_codec import save_avif
from web_images import prepare_runtime_images, prepare_native_previews, APP_READY_FARM_AVIF


def main():
    scratch = ROOT/'local/art-development/runtime-image-tests'
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as folder:
        root = Path(folder)
        page, cutout = root/'page.avif', root/'cutout.png'
        save_avif(Image.new('RGB',(2000,1200),(180,90,30)),page)
        alpha = Image.new('RGBA',(1400,900),(30,120,70,255))
        alpha.paste((17,25,33,0),(0,0,700,900))
        alpha.save(cutout)
        names = {'assets/jungle-book/pages/large.avif':page,'assets/hide_seek/props/cutout.png':cutout}
        exports = prepare_runtime_images(names,root/'cache')
        assert len(exports) == 2
        for name, source in names.items():
            result = exports[name]
            with Image.open(result.source) as decoded, Image.open(source) as original:
                assert decoded.format == 'AVIF' and decoded.size == original.size
                if original.mode == 'RGBA':
                    # Cut-outs keep exact alpha; their visible color is q70 4:4:4.
                    rgba = decoded.convert('RGBA')
                    assert rgba.getchannel('A').tobytes() == original.getchannel('A').tobytes()
                    visible = (800, 100, 1300, 800)
                    error = ImageStat.Stat(ImageChops.difference(rgba.crop(visible).convert('RGB'),
                                                                 original.crop(visible).convert('RGB'))).mean
                    assert max(error) < 3, error
                else:
                    assert result.info['reused_source']
                    assert result.source.read_bytes() == source.read_bytes()
            assert result.target.endswith(hashlib.sha256(result.source.read_bytes()).hexdigest()+'.avif')
        warm = prepare_runtime_images(names,root/'cache')
        assert all(warm[n].source.read_bytes()==exports[n].source.read_bytes() for n in names)
        previews = prepare_native_previews(names,root/'preview')
        for name, path in previews.items():
            with Image.open(path) as decoded:
                assert decoded.format == 'AVIF' and max(decoded.size) <= 128
        farm = {name:ROOT/name for name in APP_READY_FARM_AVIF}
        assert prepare_runtime_images(farm,root/'farm') == {}
        assert prepare_native_previews({}, root/'empty-preview') == {}
    print('local runtime images: full-size AVIF reuse, exact cutout RGBA, cold/warm cache and separate 128px previews passed')


if __name__ == '__main__':
    main()

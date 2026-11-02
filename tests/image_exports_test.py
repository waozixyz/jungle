"""Exercise real candidate exporters and staging with generated originals only."""
from pathlib import Path
import json
import random
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageCms

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import image_exports
import title_layers
import title_glow
import title_scenes
import menu_art
import jigsaw_art
import story_book
from web_images import prepare_runtime_images, prepare_web_images


class Exports(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT/'work', prefix='image-export-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.original = self.root/'original.png'
        # Deterministic detailed fixture, not AI media.
        im = Image.frombytes('RGB', (320,192), random.Random(71).randbytes(320*192*3))
        im.save(self.original)
        self.before = self.original.read_bytes()
        self.cache = self.root/'cache'

    def test_presets_native_original_and_once(self):
        for role, quality in [('title-background', image_exports.TITLE_BACKGROUND_QUALITY), ('book-page', 85)]:
            first = image_exports.optimize_new_image_exports(self.original, role, self.cache)
            self.assertEqual(first.quality, quality)
            with Image.open(first.source) as decoded:
                self.assertEqual(decoded.size, (320, 192))
                self.assertEqual(decoded.format, 'WEBP')
            with patch.object(Image.Image, 'save', side_effect=AssertionError('second encode')):
                again = image_exports.optimize_new_image_exports(self.original, role, self.cache)
                reused = image_exports.optimize_new_image_exports(first.source, role, self.cache)
            self.assertEqual(first.source, again.source)
            self.assertTrue(reused.reused_source)
            self.assertEqual(reused.source.read_bytes(), first.source.read_bytes())
        self.assertEqual(self.original.read_bytes(), self.before)

    def test_exact_alpha_including_hidden_rgb_and_opaque_rgba(self):
        original = self.root/'alpha.png'
        im = Image.open(self.original).convert('RGBA')
        im.putalpha(Image.linear_gradient('L').resize(im.size))
        im.save(original)
        export = image_exports.optimize_new_image_exports(original, 'cutout', self.cache)
        self.assertTrue(export.lossless)
        with Image.open(export.source) as decoded:
            self.assertEqual(decoded.convert('RGBA').tobytes(), im.tobytes())
        with self.assertRaises(ValueError):
            image_exports.optimize_new_image_exports(original, 'title-background', self.cache)
        im.putalpha(255)
        im.save(original)
        export = image_exports.optimize_new_image_exports(original, 'title-background', self.cache)
        self.assertEqual(export.quality, image_exports.TITLE_BACKGROUND_QUALITY)

    def test_smaller_valid_export_and_no_shipping_writes(self):
        im = Image.new('RGB', (320, 192), '#acf')
        im.save(self.original)
        export = image_exports.optimize_new_image_exports(self.original, 'book-page', self.cache)
        reference = self.root/'lossless.webp'
        im.save(reference, 'WEBP', lossless=True, method=6, exact=True)
        self.assertLessEqual(export.source.stat().st_size, reference.stat().st_size)
        self.assertTrue(export.lossless)
        self.assertIsNone(export.quality)
        self.assertFalse((self.root/'assets').exists())
        with self.assertRaises(ValueError):
            image_exports.export_image(self.original, self.original, 'book-page')

    def test_app_ready_new_exports_pass_established_staging_unchanged(self):
        import shutil
        for role, name in [('book-page', 'assets/jungle-book/pages/new.webp'),
                           ('title-background', 'assets/jungle/title/new.webp')]:
            ready = self.root / Path(name).name
            with patch.object(image_exports, 'ROOT', self.root):
                image_exports.export_image(self.original, ready, role)
            expected = ready.read_bytes()
            warm, _, _ = prepare_web_images({name: ready}, self.root/'web-warm')
            if role == 'book-page':
                runtime = prepare_runtime_images({name: ready}, self.root/'runtime')[name]
                self.assertTrue(runtime.info['reused_source'])
                self.assertEqual(runtime.source.read_bytes(), expected)
            shutil.rmtree(self.root/'work/image-exports')
            cold, _, _ = prepare_web_images({name: ready}, self.root/'web-cold')
            self.assertEqual(warm[name].read_bytes(), expected)
            self.assertEqual(cold[name].read_bytes(), expected)
        self.assertEqual(self.original.read_bytes(), self.before)

    def test_icc_and_orientation(self):
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        im = Image.open(self.original)
        exif = Image.Exif()
        exif[274] = 6
        im.save(self.original, icc_profile=profile, exif=exif)
        export = image_exports.optimize_new_image_exports(self.original, 'book-page', self.cache)
        with Image.open(export.source) as decoded:
            self.assertEqual(decoded.info['icc_profile'], profile)
            self.assertEqual(decoded.size, (192, 320))
            self.assertNotIn(274, decoded.getexif())

    def test_established_representative_page_staging_regression(self):
        source = ROOT/'assets/jungle-book/pages/tiger.webp'
        with Image.open(source) as original:
            expected = original.convert('RGB')
            expected.thumbnail((1024,1024), Image.Resampling.LANCZOS)
        baseline = self.root/'baseline.webp'
        expected.save(baseline, 'WEBP', quality=85, lossless=False,
                      exact=True, alpha_quality=100, method=6)
        name = 'assets/jungle-book/pages/tiger.webp'
        result = prepare_runtime_images({name: source}, self.cache)[name]
        self.assertEqual(result.source.read_bytes(), baseline.read_bytes())
        self.assertEqual(result.info['quality'], 85)
        self.assertLess(result.info['runtime_bytes'], result.info['source_bytes'])
        (self.root/'regression.json').write_text(json.dumps(result.info))

    def test_export_stable_after_clean_cache_without_private_receipts(self):
        import shutil
        dest = self.root/'candidate.webp'
        with patch.object(image_exports, 'ROOT', self.root):
            image_exports.export_image(self.original, dest, 'title-background')
            before = dest.read_bytes()
            modified = dest.stat().st_mtime_ns
            shutil.rmtree(self.root/'work/image-exports')
            image_exports.export_image(self.original, dest, 'title-background')
            self.assertEqual(dest.read_bytes(), before)
            self.assertEqual(dest.stat().st_mtime_ns, modified)
            self.assertFalse(list((self.root/'work').rglob('*.json')))

    def test_book_original_export_then_staging_is_cache_independent(self):
        original = self.root/'large-original.png'
        Image.open(self.original).resize((1254,1100)).save(original)
        # Established original-based book pipeline encodes q85 at its established cap.
        name = 'assets/jungle-book/pages/new.png'
        first = prepare_runtime_images({name:original}, self.cache)[name]
        dest = self.root/'new.webp'
        dest.write_bytes(first.source.read_bytes())
        shipped_name = 'assets/jungle-book/pages/new.webp'
        warm = prepare_runtime_images({shipped_name:dest}, self.root/'warm')[shipped_name]
        import shutil
        shutil.rmtree(self.cache)
        # No private provenance/cache is needed to retain app-ready WebP bytes.
        cold = prepare_runtime_images({shipped_name:dest}, self.root/'cold')[shipped_name]
        self.assertEqual(warm.source.read_bytes(), cold.source.read_bytes())
        self.assertEqual(cold.source.read_bytes(), dest.read_bytes())
        self.assertEqual(cold.info['runtime_width'], 1024)
        self.assertTrue(cold.info['reused_source'])

    def test_story_entrypoint_uses_original_native_page(self):
        root = self.root
        (root/'tools').mkdir()
        (root/'games/book').mkdir(parents=True)
        masters = root/'art/generated/sweet-porridge-portrait'
        masters.mkdir(parents=True)
        Image.open(self.original).save(masters/'fixture.png')
        page = {'asset': 'scene', 'portrait_asset': 'fixture', 'paper_top': 0,
                'en': 'Hello', 'de': 'Hallo', 'es': 'Hola'}
        (root/'tools/sweet_porridge.json').write_text(json.dumps({'pages':[page]}))
        for lang in ('en','de','es'):
            path = root/f'assets/jungle-book/story-sounds/{lang}/scene.speech.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'text':page[lang], 'duration':1.2}))
        with patch.object(story_book, 'ROOT', root), patch.object(image_exports, 'ROOT', root):
            story_book.main()
            dest = root/'assets/jungle-book/portraits/fixture.webp'
            with Image.open(dest) as decoded:
                self.assertEqual(decoded.size, (320,192))
            self.assertTrue((root/'games/book/sweet_porridge.zi').exists())

    def test_title_layer_entrypoint(self):
        root = self.root
        (root/'art').mkdir()
        (root/'tools').mkdir()
        for kind in ('background', 'foreground'):
            im = Image.open(self.original).convert('RGBA')
            if kind == 'foreground':
                im.putalpha(Image.linear_gradient('L').resize(im.size))
            im.save(root/f'art/title-{kind}.png')
        (root/'tools/manifest.json').write_text('{}')
        (root/'art/generated/title-layers').mkdir(parents=True)
        (root/'art/generated/title-layers/prompts.json').write_text(json.dumps({'assets': [
            {'name': 'fixture', 'source': 'art/title', 'runtime': 'assets/jungle/title/fixture'}]}))
        original_bytes = (root/'art/title-foreground.png').read_bytes()
        calls = []
        def export(source, destination, role, **kwargs):
            calls.append(role)
            result = image_exports.optimize_new_image_exports(source, role, self.cache, **kwargs)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(result.source.read_bytes())
            return result
        with patch.object(title_layers, 'ROOT', root), patch.object(title_layers, 'export_image', export), patch.object(sys, 'argv', ['title_layers.py']):
            title_layers.main()
        self.assertEqual(calls, ['title-background', 'cutout'])
        # Normal staging receives only the approved runtime inputs, never discovers art/.
        self.assertEqual((root/'art/title-foreground.png').read_bytes(), original_bytes)

    def test_title_scene_entrypoints(self):
        root = self.root
        source_dir = root/'art/generated/title-world-proposal'
        source_dir.mkdir(parents=True)
        Image.new('RGB',(1672,941),'#abd').save(source_dir/'treehouse-room.png')
        (root/'tools').mkdir()
        (root/'games').mkdir()
        (root/'games/catalog.txt').write_text('')
        (root/'tools/title_hotspots.json').write_text(json.dumps({
            'width':1672, 'height':941, 'scenes':[{'name':'treehouse',
            'image':'assets/jungle/title/tree.webp','low':'assets/jungle/title/tree-low.webp',
            'hotspots':[]}]}))
        with patch.object(title_glow, 'ROOT', root), patch.object(title_glow, 'SOURCE', source_dir), \
             patch.object(title_glow, 'DEBUG', root/'review'), patch.object(image_exports, 'ROOT', root), \
             patch.object(sys, 'argv', ['title_glow.py']):
            title_glow.main()
        self.assertEqual(image_exports.TITLE_BACKGROUND_QUALITY, 50)
        with Image.open(root/'assets/jungle/title/tree.webp') as im:
            self.assertEqual(im.size, (1672,941))
        with Image.open(root/'assets/jungle/title/tree-low.webp') as im:
            self.assertEqual(im.width, 240)
        beach_dir = root/'art/generated/world-scene-refresh'
        beach_dir.mkdir(parents=True)
        for orientation in ('landscape','portrait'):
            Image.open(self.original).save(beach_dir/f'beach-{orientation}-clean.png')
        door = {'id':'bunker-door','glow_rect':[0,0,30,30],
                'polygon':[[2,2],[25,2],[25,25]],'glow':'assets/jungle/title/door.png'}
        manifest = root/'tools/beach.json'
        manifest.write_text(json.dumps({'scenes':[{'name':'beach','hotspots':[door],
                                                  'portrait':{'hotspots':[door]}}]}))
        with patch.object(title_scenes, 'ROOT', root), patch.object(title_scenes, 'SOURCE', manifest), \
             patch.object(image_exports, 'ROOT', root):
            title_scenes.ExportBeach()
        for stem in ('beach-port','beach-portrait-port'):
            with Image.open(root/f'assets/jungle/title/{stem}.webp') as im:
                self.assertEqual(im.size,(320,192))

    def test_menu_and_jigsaw_entrypoints_from_originals(self):
        for module, folder, names in [(menu_art, 'menu-covers', ('book','count','paint','abc-123')),
                                      (jigsaw_art, 'jigsaw', jigsaw_art.SCENES)]:
            directory = self.root/'art/generated'/folder
            directory.mkdir(parents=True)
            for name in names:
                Image.open(self.original).resize((320,320)).save(directory/(name+'.png'))
            calls = []
            def export(source, destination, role, **kwargs):
                self.assertTrue(str(source).startswith(str(directory)))
                calls.append((role, kwargs['size']))
                return image_exports.optimize_new_image_exports(source, role, self.cache, **kwargs)
            with patch.object(module, 'ROOT', self.root), patch.object(module, 'export_image', export):
                module.main()
            self.assertEqual(len(calls), 4)
            self.assertTrue(all(role == 'scene' for role, _ in calls))


if __name__ == '__main__':
    unittest.main()

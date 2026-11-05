#!/usr/bin/env python3
"""Shared artwork ships once; identical pictures and fonts are safe aliases;
every previewed picture's small preview is installed under assets/previews/."""
from io import BytesIO
from pathlib import Path
import hashlib
import json
import os
import re
import sys
import tempfile
import time

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import shared_assets
from asset_packs import pack_assets


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def picture(color, suffix, size=(300, 200)):
    """A real picture's bytes, for folders whose pictures get previews."""
    image = Image.new('RGBA' if len(color) == 4 else 'RGB', size, color)
    if len(color) == 4:
        image.paste((0, 0, 0, 0), (0, 0, size[0] // 2, size[1]))
    data = BytesIO()
    image.save(data, 'AVIF' if suffix == '.avif' else 'PNG')
    return data.getvalue()


TIGER_PAGE = picture((200, 120, 40), '.avif')
LION_PAGE = picture((180, 160, 60), '.avif')
TIGER_ITEM = picture((230, 140, 30, 255), '.avif')
COVER = picture((40, 90, 160), '.avif', (200, 200))
SCENE = picture((90, 150, 70), '.avif')
BASKET = picture((150, 100, 50, 255), '.avif', (200, 200))
JIGSAW = picture((60, 120, 90), '.avif', (1200, 1200))
# The previews staging installs for fake_tree.
PREVIEWED = {path.with_suffix('.avif').as_posix() for path in map(Path, (
    'assets/previews/jungle-book/portraits/story.avif', 'assets/previews/jungle-book/pages/tiger.avif', 'assets/previews/jungle-book/pages/lion.avif',
    'assets/previews/jungle-book/items/tiger.png', 'assets/previews/jungle-book/previews/bedroom.avif',
    'assets/previews/jungle-book/previews/bedtime.avif', 'assets/previews/hide_seek/scenes/cottage-yard.png',
    'assets/previews/hide_seek/props/basket.png'))}
RUNTIME_LOGICAL = {'assets/jungle-book/portraits/story.avif', 'assets/jungle-book/pages/tiger.avif', 'assets/jungle-book/pages/lion.avif',
                   'assets/jungle-book/items/tiger.avif', 'assets/jungle-book/previews/bedroom.avif',
                   'assets/jungle-book/previews/bedtime.avif', 'assets/hide_seek/scenes/cottage-yard.avif',
                   'assets/hide_seek/props/basket.avif',
                   'assets/collectibles/magic-pot.avif', 'assets/collectibles/sunflower.avif',
                   'assets/collectibles/drum.avif'}


def write(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def fake_tree(root):
    """A miniature assets/ with every kind of duplicate the real one has."""
    font = b'font'
    write(root, 'assets/jungle/font.png', font)
    for i, name in enumerate(('right', 'right-glow', 'left', 'left-glow')):
        write(root, f'assets/jungle/title/objects/wood-arrow-{name}.avif',
              picture((170+i*20, 120, 50, 255), '.avif'))
    for i, name in enumerate(('sign-right-board', 'sign-right-board-glow', 'sign-right-post')):
        write(root, f'assets/jungle/title/objects/{name}.avif', picture((150+i*20, 110, 60, 255), '.avif'))
    write(root, 'assets/jungle/icon.png', b'icon')
    write(root, 'assets/jungle/icons/icon-64.png', b'icon')
    write(root, 'assets/jungle/sounds/select.wav', b'select')
    write(root, 'assets/jungle-book/font.png', font)
    write(root, 'assets/jungle-book/portraits/story.avif', picture((160, 150, 90), '.avif', (1024,1536)))
    write(root, 'assets/jungle-book/pages/tiger.avif', TIGER_PAGE)
    write(root, 'assets/jungle-book/pages/lion.avif', LION_PAGE)
    write(root, 'assets/jungle-book/items/tiger.avif', TIGER_ITEM)
    write(root, 'assets/jungle-book/previews/bedroom.avif', COVER)
    write(root, 'assets/jungle-book/previews/bedtime.avif', COVER)
    write(root, 'assets/jungle-book/sounds/en/tiger.wav', b'tiger voice')
    write(root, 'assets/jungle-book/sounds/en/tiger.speech.json', b'{}')
    write(root, 'assets/jungle-book/collect.wav', b'collect')
    for index, name in enumerate(('magic-pot', 'sunflower', 'drum')):
        write(root, f'assets/collectibles/{name}.avif', picture((80 + index, 90, 100, 255), '.avif'))
    write(root, 'assets/jungle-book/sounds/de/simple/lettuce.wav', b'retired voice')
    write(root, 'assets/jungle-book/sounds/en/letters/0061.wav', b'a')
    for name in shared_assets.COUNTING:
        write(root, f'assets/jungle-book/counting/{name}.avif', name.encode())
    write(root, 'assets/abc/sounds/en/letters/0061.wav', b'a')
    write(root, 'assets/abc/sounds/en/letters/0061.speech.json', b'{}')
    write(root, 'assets/numbers/sounds/one.wav', b'one')
    write(root, 'assets/numbers/sounds/two.wav', b'two')
    write(root, 'assets/animal-count/font.png', b'counting font')
    write(root, 'assets/animal-count/latin.png', font)
    write(root, 'assets/animal-count/sounds/right.wav', b'font')
    write(root, 'assets/dino-paint/font.png', font)
    write(root, 'assets/dino-paint/sounds/voice-1.wav', b'voice')
    write(root, 'assets/dino-paint/art/dino1.png', b'dino')
    write(root, 'assets/hide_seek/scenes/cottage-yard.avif', SCENE)
    write(root, 'assets/hide_seek/props/basket.avif', BASKET)
    # Farm signs/crops now ship as their own trimmed derivatives; development
    # provenance and the retired collection chime do not enter its bundle.
    write(root, 'assets/garden/play/carrot.avif', picture((210, 105, 31, 255), '.avif'))
    write(root, 'assets/garden/scene-provenance.json', b'{}')


def manifest(path):
    lines = Path(path).read_text().splitlines()
    assert lines[0] == shared_assets.HEADER.strip(), lines[0]
    shared, aliases = [], {}
    for line in lines[1:]:
        kind, name, target = line.split('|')
        if kind == 'shared':
            assert target == '' and name.endswith('/') and shared_assets.SafePath(name), line
            shared.append(name)
        else:
            assert kind == 'alias' and name not in aliases, line
            assert shared_assets.SafePath(name) and shared_assets.SafePath(target), line
            aliases[name] = target
    assert not set(aliases.values()) & set(aliases), 'aliases must be one step'
    return shared, aliases


# Speech staging is tests/speech_playback_test.py's; these trees have none.
NO_SPEECH = (shared_assets.NO_SPEECH, {})
SPEECH_STUB = """LANGUAGES = ('en', 'de', 'es')


def BuildSpeechManifest(root=None, extra_voices=()):
    assert not extra_voices
    return {'clips': {}, 'voices': {}}


def AddSpeechProfiles(manifest, root=None):
    return manifest
"""


def staging_test():
    original = shared_assets.ROOT
    with tempfile.TemporaryDirectory(prefix='shared-assets-', dir=ROOT / 'build') as directory:
        root = Path(directory)
        fake_tree(root / 'source')
        app, stage = root / 'app', root / 'stage'
        # Stale files from an earlier build, including renamed artwork.
        write(app, 'assets/jungle-book/pages/old.avif', b'old')
        write(app, 'assets/jungle-book/sounds/de/simple/lettuce.wav', b'old retired voice')
        write(app, 'assets/jungle-book/previews/bedtime.avif', COVER)
        write(app, 'assets/previews/jungle-book/pages/old.avif', b'old preview')
        write(stage, 'jungle-book/assets/jungle-book/pages/tiger.avif', b'tiger page')
        write(stage, 'animal-count/assets/animal-count/pictures/tiger.avif', b'tiger')
        write(stage, 'jungle-abc/leftover/file.txt', b'old')
        shared_assets.ROOT = root / 'source'
        try:
            installed, aliases, bundles = shared_assets.StageSharedAssets(app, stage, NO_SPEECH)
            listings = {name: (stage / (name + '.files')).stat().st_mtime_ns for name in bundles}
            text = (app / shared_assets.MANIFEST).read_text()
            os.utime(app / shared_assets.MANIFEST, ns=(1, 1))
            for name in listings:
                os.utime(stage / (name + '.files'), ns=(1, 1))
            shared_assets.StageSharedAssets(app, stage, NO_SPEECH)
            web = shared_assets.WebAliases()
        finally:
            shared_assets.ROOT = original
        # Unchanged staging keeps file times, so make rebuilds no bundle.
        assert (app / shared_assets.MANIFEST).stat().st_mtime_ns == 1
        assert all((stage / (name + '.files')).stat().st_mtime_ns == 1 for name in listings)
        assert (app / shared_assets.MANIFEST).read_text() == text
        assert (root / 'source/assets/jungle-book/sounds/de/simple/lettuce.wav').read_bytes() == b'retired voice'
        assert not (app / 'assets/jungle-book/sounds/de/simple/lettuce.wav').exists()
        assert not any(name.endswith('.wav') and name.startswith('assets/jungle-book/sounds/') for name in web)
        shared, parsed = manifest(app / shared_assets.MANIFEST)
        assert shared == [*shared_assets.SHARED, 'assets/previews/']
        expected = {f'assets/animal-count/pictures/{name}.avif': f'assets/jungle-book/counting/{name}.avif'
                    for name in shared_assets.COUNTING}
        expected.update({'assets/animal-count/latin.png': 'assets/jungle/font.png',
                         'assets/dino-paint/font.png': 'assets/jungle/font.png',
                         'assets/jungle-book/font.png': 'assets/jungle/font.png'})
        assert set(parsed) == set(expected) | RUNTIME_LOGICAL, set(parsed) ^ (set(expected) | RUNTIME_LOGICAL)
        assert parsed.items() >= expected.items()
        runtime_targets = {parsed[name] for name in RUNTIME_LOGICAL}
        assert all(target.startswith(shared_assets.RUNTIME_ROOT) and target.endswith('.avif')
                   for target in runtime_targets), runtime_targets
        files = {path.relative_to(app).as_posix() for path in app.rglob('*') if path.is_file()}
        assert files == {'assets/shared-assets.txt', 'assets/speech.txt', 'assets/jungle/font.png', 'assets/jungle/icon.png',
                         'assets/jungle/icons/icon-64.png', 'assets/jungle/sounds/select.wav',
                         'assets/jungle/title/objects/wood-arrow-right.avif',
                         'assets/jungle/title/objects/wood-arrow-right-glow.avif',
                         'assets/jungle/title/objects/wood-arrow-left.avif',
                         'assets/jungle/title/objects/wood-arrow-left-glow.avif',
                         *{f'assets/jungle/title/objects/{name}.avif'
                           for name in ('sign-right-board', 'sign-right-board-glow', 'sign-right-post')},
                         'assets/jungle-book/collect.wav',
                         'assets/dino-paint/art/dino1.png', *runtime_targets, *PREVIEWED,
                         *{f'assets/jungle-book/counting/{name}.avif' for name in shared_assets.COUNTING}}, files
        # Previews keep aspect and transparency; an aliased cover still has
        # its own preview path.
        with Image.open(app / 'assets/previews/jungle-book/pages/tiger.avif') as small:
            assert small.format == 'AVIF' and small.size == (128, 85), small.size
        with Image.open(app / 'assets/previews/hide_seek/props/basket.avif') as small:
            assert small.format == 'AVIF' and small.mode == 'RGBA' and small.size == (128, 128)
            assert small.getpixel((2, 64))[3] == 0 and small.getpixel((125, 64))[3] == 255
        with Image.open(app / 'assets/previews/hide_seek/scenes/cottage-yard.avif') as small:
            assert small.format == 'AVIF' and small.mode == 'RGB'
        assert all(installed[name].parent == root / 'source' / shared_assets.PREVIEW_CACHE for name in PREVIEWED)
        assert not any(path.startswith('assets/previews/') for files in bundles.values() for path in files)
        # Shared-book activities skip bundle extraction: logical scenes and
        # props resolve to the installed runtime target, not another packed copy.
        assert (root / 'source/assets/hide_seek/scenes/cottage-yard.avif').read_bytes() == SCENE
        assert 'assets/hide_seek/scenes/cottage-yard.avif' not in bundles['jungle-hide-seek']
        assert (app / 'assets/dino-paint/art/dino1.png').read_bytes() == b'dino'
        assert not any(path.startswith('assets/dino-paint/art/') for path in bundles['dino-paint'])
        assert (root / 'source/assets/hide_seek/props/basket.avif').read_bytes() == BASKET
        assert 'assets/hide_seek/props/basket.avif' not in bundles['jungle-hide-seek']
        staged = {path.relative_to(stage).as_posix() for path in stage.rglob('*') if path.is_file()}
        assert staged == {'.shared-assets', 'speech-manifest.json', *{name + '.files' for name in bundles},
                          'jungle-abc/assets/abc/sounds/en/letters/0061.wav',
                          'jungle-numbers/assets/numbers/sounds/one.wav',
                          'jungle-numbers/assets/numbers/sounds/two.wav',
                          'jungle-book/assets/jungle-book/collect.wav',
                          'jungle-matching/assets/jungle-book/collect.wav',
                          'jungle-hide-seek/assets/jungle-book/collect.wav',
                          'jungle-garden/assets/garden/play/carrot.avif',
                          *{f'jungle-garden/assets/jungle/title/objects/{name}.avif'
                            for name in ('sign-right-board', 'sign-right-board-glow', 'sign-right-post')},
                          'jungle-drums/assets/jungle-book/collect.wav',
                          'animal-count/assets/animal-count/font.png',
                          'animal-count/assets/animal-count/sounds/right.wav'}, staged
        assert (stage / 'jungle-book/assets/jungle-book/collect.wav').is_file()
        # A sound with a picture's bytes keeps its own copy.
        assert (stage / 'animal-count/assets/animal-count/sounds/right.wav').read_bytes() == b'font'
        assert set(web) == RUNTIME_LOGICAL
        assert {sha(source) for source in web.values()} == {
            sha(installed[target]) for target in runtime_targets}
        # The browser's packs store each optimized payload once.
        packed = pack_assets(web, root / 'web')
        assert {entry['sha256'] for entry in packed['files'].values()} == {
            sha(installed[target]) for target in runtime_targets}


def unsafe_test():
    for name in ('/assets/x.png', 'assets/../x.png', 'assets//x.png', 'assets/./x.png', 'assets/a|b.png',
                 'games/x.png', 'assets/a\\b.png', 'assets/a\nb.png'):
        assert not shared_assets.SafePath(name), name
    installed = {'assets/jungle-book/portraits/story.avif': ROOT / 'assets/jungle-book/portraits/porridge_00_cover.avif',
                 'assets/jungle/font.png': ROOT / 'assets/jungle/font.png',
                 'assets/jungle-book/pages/tiger.avif': ROOT / 'assets/jungle-book/pages/tiger.avif',
                 'assets/jungle-book/items/tiger.avif': ROOT / 'assets/jungle-book/items/tiger.avif',
                 'assets/jungle-book/counting/tiger.avif': ROOT / 'assets/jungle-book/counting/tiger.avif',
                 'assets/jungle-book/previews/jungle.avif': ROOT / 'assets/jungle-book/previews/jungle.avif'}
    for aliases in ({'assets/a.png': 'assets/missing.png'},
                    {'assets/a.png': 'assets/b.png', 'assets/b.png': 'assets/jungle/font.png'},
                    {'assets/../a.png': 'assets/jungle/font.png'}):
        try:
            shared_assets.Check(installed, aliases)
        except AssertionError:
            continue
        raise AssertionError('accepted unsafe aliases: ' + str(aliases))


def real_tree_test():
    installed, aliases, bundles, runtime = shared_assets.PlanWithRuntime()
    for item in json.loads((ROOT / 'tools/collectibles.json').read_text())['collectibles']:
        if item['pending']:
            continue
        path = item['color']
        assert aliases.get(path, path) in installed, ('album picture is not installed', item['slug'], path)
    pictures = {}
    for path, source in installed.items():
        if source.suffix in shared_assets.PICTURES and not path.startswith(shared_assets.HOST_ONLY):
            assert sha(source) not in pictures, (path, pictures.get(sha(source)))
            pictures[sha(source)] = path
    for path, target in aliases.items():
        source = shared_assets.ROOT / path if (shared_assets.ROOT / path).exists() else None
        assert Path(path).suffix in shared_assets.PICTURES and target in installed and target not in aliases
        export = runtime.get(path)
        if export is not None:
            assert target == export.target and source is not None, path
            assert sha(source) == export.info['source_sha256'], path
            assert installed[target].stat().st_size == export.info['runtime_bytes'], path
        elif source:
            assert sha(source) == sha(installed[target]), path
    assert 'assets/jungle-book/font.png' in aliases and 'assets/dino-paint/font.png' in aliases
    assert all(f'assets/animal-count/pictures/{name}.avif' in aliases for name in shared_assets.COUNTING)
    catalog_pages = {f'assets/jungle-book/pages/{name}.avif'
                     for _, names in __import__('book_catalog').BOOKS for name in names}
    assert len(catalog_pages) == 435 and catalog_pages <= set(aliases), 'a catalog page lost its runtime alias'
    assert len(runtime) >= 700, len(runtime)
    assert set(bundles['jungle-book']) == {'assets/jungle-book/collect.wav'}, 'Picture Book bundle holds only its chime; album pictures are shared'
    sounds = 0
    for name, files in bundles.items():
        for path, source in files.items():
            assert not shared_assets.IsShared(path) and path not in aliases, (name, path)
            if source.suffix in shared_assets.PICTURES:
                assert sha(source) not in pictures, (name, path)
        # Every sound and piece of progress data the game had still ships.
        for path in shared_assets.GameFiles(name):
            if not path.endswith(('.png', '.avif')):
                assert path in files or (name == 'jungle-book' and path in installed), (name, path)
                sounds += 1
    assert sounds > 150
    book_sounds = [path for path in shared_assets.Folder('assets/jungle-book') if '/sounds/' in path]
    assert all(path in installed for path in book_sounds)
    assert not any(path.startswith('assets/jungle-book/sounds/') and path.endswith('.wav') for path in installed)
    assert (ROOT / 'assets/jungle-book/sounds/de/simple/lettuce.wav').is_file()
    # Original artwork bytes are never changed, only copied or aliased.
    for path, source in installed.items():
        if path.startswith(shared_assets.RUNTIME_ROOT):
            assert source.suffix == '.avif'
            export = next(row for row in runtime.values() if row.target == path)
            assert source == export.source
            if export.info['reused_source']:
                assert source == shared_assets.ROOT / export.info['source_path']
                assert sha(source) == export.info['source_sha256']
            else:
                assert source.parent == shared_assets.ROOT / shared_assets.RUNTIME_CACHE
        else:
            assert source == shared_assets.ROOT / path
    make = (ROOT / 'Makefile').read_text()
    assert re.search(r'^STAGED_GAMES := (.*)$', make, re.M)[1].split() == list(shared_assets.GAMES)
    host = (ROOT / 'host/jungle_host.zi').read_text()
    assert 'WidgetHostBegin(app.session, GameAssetAllowed, GameAssetResolve)' in host
    assert '"assets/shared-assets.txt"' in host
    # The host accepts exactly this format's header.
    assert f'SHARED_HEADER :: "{shared_assets.HEADER.strip()}"' in host
    built = ROOT / 'build/app' / shared_assets.MANIFEST
    if built.exists() and any(path.relative_to(ROOT / 'build/app').as_posix().startswith(shared_assets.RUNTIME_ROOT)
                              for path in (ROOT / 'build/app/assets').rglob('*')):
        assert built.read_text() == shared_assets.ManifestText(aliases), 'build/app has a stale manifest'
        for path in aliases:
            assert not (ROOT / 'build/app' / path).exists(), 'aliased copy installed: ' + path


def make_test():
    """Direct staging is idempotent and removes deleted source files."""
    import shutil
    import subprocess
    with tempfile.TemporaryDirectory(prefix='shared-make-', dir=ROOT / 'build') as directory:
        root = Path(directory)
        fake_tree(root)
        write(root, 'assets/jigsaw/tiger.avif', JIGSAW)
        (root / 'tools').mkdir()
        for name in ('shared_assets.py', 'web_images.py', 'avif_codec.py', 'speech_codec.py', 'book_speech.py', 'book_catalog.py',
                     'book_expansion.json', 'book_learning_expansion.json', 'outdoor_books.json',
                     'book_unique_expansion.json', 'book_minimum_expansion.json'):
            shutil.copy2(ROOT / 'tools' / name, root / 'tools' / name)
        (root / 'tools/speech_manifest.py').write_text(SPEECH_STUB)

        def stage(*args):
            result = subprocess.run(['python3', 'tools/shared_assets.py', *args],
                                  cwd=root, capture_output=True, text=True, timeout=120)
            assert result.returncode == 0, (result.stdout + '\n' + result.stderr)[-4000:]
            return result.stdout

        assert 'Shared assets:' in stage()
        assert (root / 'build/app/assets/speech.txt').read_text() == shared_assets.SPEECH_HEADER
        jigsaw_preview = root / 'build/app/assets/previews/jigsaw/tiger.avif'
        assert jigsaw_preview.is_file(), 'a Jigsaw picture has no installed preview'
        page = root / 'build/app/assets/jungle-book/pages/tiger.avif'
        staged = root / 'build/stage/jungle-numbers/assets/numbers/sounds/one.wav'
        listing = root / 'build/stage/jungle-numbers.files'
        assert not page.exists() and staged.exists()
        os.utime(listing, ns=(1, 1))
        assert 'Shared assets:' in stage()
        assert listing.stat().st_mtime_ns == 1, 'unchanged files rebuild a bundle'
        (root / 'assets/jungle-book/pages/tiger.avif').unlink()
        (root / 'assets/numbers/sounds/one.wav').unlink()
        assert 'Shared assets:' in stage(), 'a deleted source did not restage'
        assert not page.exists() and not staged.exists(), 'deleted assets still ship'
        assert not (root / 'build/app/assets/previews/jungle-book/pages/tiger.avif').exists(), 'a deleted picture keeps its preview'
        assert listing.stat().st_mtime_ns != 1, 'the game bundle would not rebuild'
        assert (root / 'build/stage/jungle-numbers/assets/numbers/sounds/two.wav').exists()
        # A private APP owns both output assets and its bundle-stage tree.
        owner = {str(p.relative_to(root)): (p.stat().st_mtime_ns,p.read_bytes())
                 for folder in ('build/app','build/stage') for p in (root/folder).rglob('*') if p.is_file()}
        assert 'Shared assets:' in stage('--app','build/tests/private','--stage','build/tests/private/stage')
        assert (root/'build/tests/private/assets/shared-assets.txt').is_file()
        assert (root/'build/tests/private/stage/jungle-numbers.files').is_file()
        assert 'Shared assets:' in stage('--app','build/tests/another')
        assert (root/'build/tests/another/stage/jungle-numbers.files').is_file()
        for name,(mtime,content) in owner.items():
            assert (root/name).stat().st_mtime_ns == mtime and (root/name).read_bytes() == content
        dry = subprocess.run(['make','-n','-B','APP=build/tests/private','TOOLCHAIN=/unused',
            'KRYON=/unused','MINGCUTE=/unused','build/tests/private/assets/shared-assets.txt'],
            cwd=ROOT,capture_output=True,text=True,check=True).stdout
        calls = [line for line in dry.splitlines() if 'python3 tools/shared_assets.py' in line]
        assert calls and all("--app 'build/tests/private' --stage 'build/tests/private/stage'" in line for line in calls),calls



def host_parser_test():
    """The built host refuses every malformed manifest before any game opens."""
    program = ROOT / 'build/app/jungle'
    if not program.exists():
        print('local shared asset test: build/app/jungle not built; host parser check skipped')
        return
    import shutil
    import subprocess
    header = shared_assets.HEADER
    good = header + 'shared|assets/jungle-book/pages/|\nalias|assets/a.png|assets/jungle/font.png\n'
    bad = ['', 'shared|assets/jungle-book/pages/|\n', '#jungle-shared-assets-2\nshared|assets/jungle-book/pages/|\n',
           header, header + 'shared|assets/jungle-book/pages/|\nspeech|assets/a.wav|\n',
           good + 'alias|assets/a.png|assets/jungle/font.png\n',
           good + 'alias|assets/b.png|assets/a.png\n',
           header + 'shared|assets/jungle-book/pages/|\nalias|assets/../a.png|assets/jungle/font.png\n',
           header + 'shared|assets/../|\n', header + 'shared|assets/jungle-book/pages|\n',
           header + 'shared|assets/jungle-book/pages/|\nalias|/assets/a.png|assets/jungle/font.png\n',
           header + 'shared|assets/jungle-book/pages/|\nalias|assets/a.png|assets/jungle/font.png|extra\n']
    with tempfile.TemporaryDirectory(prefix='shared-host-', dir=ROOT / 'build') as directory:
        app = Path(directory) / 'app'
        (app / 'games').mkdir(parents=True)
        (app / 'assets').mkdir()
        shutil.copy2(program, app / 'jungle')
        (app / shared_assets.SPEECH_INDEX).write_text(shared_assets.SPEECH_HEADER)
        (app / 'games/catalog.txt').write_text('missing.zx|Missing|Test|assets/jungle/covers/book.avif|2\n')
        environment = {**os.environ, 'JUNGLE_DATA': str(Path(directory) / 'data')}
        for text in [good, *bad]:
            (app / shared_assets.MANIFEST).write_text(text)
            result = subprocess.run([str(app / 'jungle'), '--check'], env=environment, capture_output=True,
                                    text=True, timeout=60)
            refused = 'shared-assets.txt is missing or invalid' in result.stderr
            assert result.returncode != 0 and refused == (text != good), (text, result.stderr)


def main():
    unsafe_test()
    make_test()
    host_parser_test()
    staging_test()
    real_tree_test()
    print('local shared asset test: shared artwork ships once, aliases are safe one-step identical bytes, '
          'stale staged files are removed and sounds are kept')


if __name__ == '__main__':
    main()

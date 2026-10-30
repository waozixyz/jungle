#!/usr/bin/env python3
"""Shared artwork ships once; identical pictures and fonts are safe aliases."""
from pathlib import Path
import hashlib
import json
import os
import re
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import shared_assets
from asset_packs import pack_assets


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def fake_tree(root):
    """A miniature assets/ with every kind of duplicate the real one has."""
    font = b'font'
    write(root, 'assets/jungle/font.png', font)
    write(root, 'assets/jungle/icon.png', b'icon')
    write(root, 'assets/jungle/icons/icon-64.png', b'icon')
    write(root, 'assets/jungle/sounds/select.wav', b'select')
    write(root, 'assets/jungle-book/font.png', font)
    write(root, 'assets/jungle-book/pages/tiger.jpg', b'tiger page')
    write(root, 'assets/jungle-book/pages/lion.jpg', b'lion page')
    write(root, 'assets/jungle-book/items/tiger.png', b'tiger item')
    write(root, 'assets/jungle-book/previews/bedroom.jpg', b'cover')
    write(root, 'assets/jungle-book/previews/bedtime.jpg', b'cover')
    write(root, 'assets/jungle-book/sounds/en/tiger.wav', b'tiger voice')
    write(root, 'assets/jungle-book/sounds/en/tiger.speech.json', b'{}')
    write(root, 'assets/jungle-book/sounds/en/letters/0061.wav', b'a')
    for name in shared_assets.COUNTING:
        write(root, f'assets/jungle-book/counting/{name}.png', name.encode())
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
"""


def staging_test():
    original = shared_assets.ROOT
    with tempfile.TemporaryDirectory(prefix='shared-assets-', dir=ROOT / 'build') as directory:
        root = Path(directory)
        fake_tree(root / 'source')
        app, stage = root / 'app', root / 'stage'
        # Stale files from an earlier build, including renamed artwork.
        write(app, 'assets/jungle-book/pages/old.jpg', b'old')
        write(app, 'assets/jungle-book/previews/bedtime.jpg', b'cover')
        write(stage, 'jungle-book/assets/jungle-book/pages/tiger.jpg', b'tiger page')
        write(stage, 'animal-count/assets/animal-count/pictures/tiger.png', b'tiger')
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
        shared, parsed = manifest(app / shared_assets.MANIFEST)
        assert shared == list(shared_assets.SHARED)
        expected = {f'assets/animal-count/pictures/{name}.png': f'assets/jungle-book/counting/{name}.png'
                    for name in shared_assets.COUNTING}
        expected.update({'assets/animal-count/latin.png': 'assets/jungle/font.png',
                         'assets/dino-paint/font.png': 'assets/jungle/font.png',
                         'assets/jungle-book/font.png': 'assets/jungle/font.png',
                         'assets/jungle-book/previews/bedtime.jpg': 'assets/jungle-book/previews/bedroom.jpg'})
        assert parsed == expected, parsed
        files = {path.relative_to(app).as_posix() for path in app.rglob('*') if path.is_file()}
        assert files == {'assets/shared-assets.txt', 'assets/speech.txt', 'assets/jungle/font.png', 'assets/jungle/icon.png',
                         'assets/jungle/icons/icon-64.png', 'assets/jungle/sounds/select.wav',
                         'assets/jungle-book/pages/tiger.jpg', 'assets/jungle-book/pages/lion.jpg',
                         'assets/jungle-book/items/tiger.png',
                         'assets/jungle-book/previews/bedroom.jpg', 'assets/jungle-book/sounds/en/tiger.wav',
                         *{f'assets/jungle-book/counting/{name}.png' for name in shared_assets.COUNTING}}, files
        staged = {path.relative_to(stage).as_posix() for path in stage.rglob('*') if path.is_file()}
        assert staged == {'.shared-assets', 'speech-manifest.json', *{name + '.files' for name in bundles},
                          'jungle-abc/assets/abc/sounds/en/letters/0061.wav',
                          'jungle-numbers/assets/numbers/sounds/one.wav',
                          'jungle-numbers/assets/numbers/sounds/two.wav',
                          'animal-count/assets/animal-count/font.png',
                          'animal-count/assets/animal-count/sounds/right.wav',
                          'dino-paint/assets/dino-paint/art/dino1.png'}, staged
        assert (stage / 'jungle-book/assets').is_dir() and not any((stage / 'jungle-book/assets').iterdir())
        # A sound with a picture's bytes keeps its own copy.
        assert (stage / 'animal-count/assets/animal-count/sounds/right.wav').read_bytes() == b'font'
        assert {name: sha(source) for name, source in web.items()} == {
            name: sha(root / 'source' / target) for name, target in expected.items()}
        # The browser's packs store each aliased picture once.
        packed = pack_assets({**{name: root / 'source' / name for name in expected.values()}, **web}, root / 'web')
        assert len({json.dumps(entry, sort_keys=True) for entry in packed['files'].values()}) == len(set(expected.values()))


def unsafe_test():
    for name in ('/assets/x.png', 'assets/../x.png', 'assets//x.png', 'assets/./x.png', 'assets/a|b.png',
                 'games/x.png', 'assets/a\\b.png', 'assets/a\nb.png'):
        assert not shared_assets.SafePath(name), name
    installed = {'assets/jungle/font.png': ROOT / 'assets/jungle/font.png',
                 'assets/jungle-book/pages/tiger.jpg': ROOT / 'assets/jungle-book/pages/tiger.jpg',
                 'assets/jungle-book/items/tiger.png': ROOT / 'assets/jungle-book/items/tiger.png',
                 'assets/jungle-book/counting/tiger.png': ROOT / 'assets/jungle-book/counting/tiger.png',
                 'assets/jungle-book/previews/jungle.jpg': ROOT / 'assets/jungle-book/previews/jungle.jpg'}
    for aliases in ({'assets/a.png': 'assets/missing.png'},
                    {'assets/a.png': 'assets/b.png', 'assets/b.png': 'assets/jungle/font.png'},
                    {'assets/../a.png': 'assets/jungle/font.png'}):
        try:
            shared_assets.Check(installed, aliases)
        except AssertionError:
            continue
        raise AssertionError('accepted unsafe aliases: ' + str(aliases))


def real_tree_test():
    installed, aliases, bundles = shared_assets.Plan()
    pictures = {}
    for path, source in installed.items():
        if source.suffix in shared_assets.PICTURES and not path.startswith(shared_assets.HOST_ONLY):
            assert sha(source) not in pictures, (path, pictures.get(sha(source)))
            pictures[sha(source)] = path
    for path, target in aliases.items():
        source = shared_assets.ROOT / path if (shared_assets.ROOT / path).exists() else None
        assert Path(path).suffix in shared_assets.PICTURES and target in installed and target not in aliases
        if source:
            assert sha(source) == sha(installed[target]), path
    assert 'assets/jungle-book/font.png' in aliases and 'assets/dino-paint/font.png' in aliases
    assert all(f'assets/animal-count/pictures/{name}.png' in aliases for name in shared_assets.COUNTING)
    assert bundles['jungle-book'] == {}, 'Picture Book bundle must not repeat the installed book'
    sounds = 0
    for name, files in bundles.items():
        for path, source in files.items():
            assert not shared_assets.IsShared(path) and path not in aliases, (name, path)
            if source.suffix in shared_assets.PICTURES:
                assert sha(source) not in pictures, (name, path)
        # Every sound and piece of progress data the game had still ships.
        for path in shared_assets.GameFiles(name):
            if not path.endswith(('.png', '.jpg', '.jpeg', '.webp')):
                assert path in files or (name == 'jungle-book' and path in installed), (name, path)
                sounds += 1
    assert sounds > 150
    book_sounds = [path for path in shared_assets.Folder('assets/jungle-book') if '/sounds/' in path]
    assert book_sounds and all(path in installed for path in book_sounds)
    # Original artwork bytes are never changed, only copied or aliased.
    for path, source in installed.items():
        assert source == shared_assets.ROOT / path
    make = (ROOT / 'Makefile').read_text()
    assert re.search(r'^STAGED_GAMES := (.*)$', make, re.M)[1].split() == list(shared_assets.GAMES)
    host = (ROOT / 'host/jungle_host.zi').read_text()
    assert 'WidgetHostBegin(app.session, GameAssetAllowed, GameAssetResolve)' in host
    assert '"assets/shared-assets.txt"' in host
    # The host accepts exactly this format's header.
    assert f'SHARED_HEADER :: "{shared_assets.HEADER.strip()}"' in host
    built = ROOT / 'build/app' / shared_assets.MANIFEST
    if built.exists():
        assert built.read_text() == shared_assets.ManifestText(aliases), 'build/app has a stale manifest'
        for path in aliases:
            assert not (ROOT / 'build/app' / path).exists(), 'aliased copy installed: ' + path


def make_test():
    """make reruns staging when a source file is deleted, and only then."""
    import shutil
    import subprocess
    with tempfile.TemporaryDirectory(prefix='shared-make-', dir=ROOT / 'build') as directory:
        root = Path(directory)
        fake_tree(root)
        write(root, 'assets/jigsaw/tiger.jpg', b'jigsaw')
        (root / 'tools').mkdir()
        for name in ('shared_assets.py', 'speech_codec.py', 'book_speech.py', 'book_catalog.py',
                     'book_expansion.json', 'outdoor_books.json'):
            shutil.copy2(ROOT / 'tools' / name, root / 'tools' / name)
        (root / 'tools/speech_manifest.py').write_text(SPEECH_STUB)
        shutil.copy2(ROOT / 'Makefile', root / 'Makefile')

        def make():
            return subprocess.run(['make', '--no-print-directory', 'ZIRAN=true', 'build/app/assets/shared-assets.txt',
                                   'build/stage/jungle-numbers.files'],
                                  cwd=root, capture_output=True, text=True, timeout=120, check=True).stdout

        assert 'shared_assets.py' in make()
        assert (root / 'build/app/assets/speech.txt').read_text() == shared_assets.SPEECH_HEADER
        page = root / 'build/app/assets/jungle-book/pages/tiger.jpg'
        staged = root / 'build/stage/jungle-numbers/assets/numbers/sounds/one.wav'
        listing = root / 'build/stage/jungle-numbers.files'
        assert page.exists() and staged.exists()
        assert 'shared_assets.py' not in make(), 'staging reran with nothing changed'
        os.utime(listing, ns=(1, 1))
        # File times use the kernel's coarse clock; step past the last stamp.
        time.sleep(.05)
        (root / 'assets/jungle-book/pages/tiger.jpg').touch()
        assert 'shared_assets.py' in make() and listing.stat().st_mtime_ns == 1, 'unchanged files rebuild a bundle'
        time.sleep(.05)
        (root / 'assets/jungle-book/pages/tiger.jpg').unlink()
        (root / 'assets/numbers/sounds/one.wav').unlink()
        assert 'shared_assets.py' in make(), 'a deleted source did not rerun staging'
        assert not page.exists() and not staged.exists(), 'deleted assets still ship'
        assert listing.stat().st_mtime_ns != 1, 'the game bundle would not rebuild'
        assert (root / 'build/stage/jungle-numbers/assets/numbers/sounds/two.wav').exists()


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
        (app / 'games/catalog.txt').write_text('missing.zx|Missing|Test|assets/jungle/covers/book.jpg|2\n')
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

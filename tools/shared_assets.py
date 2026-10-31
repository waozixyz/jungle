#!/usr/bin/env python3
"""Stage Jungle's installed assets and each game's bundle assets.

Picture Book artwork is installed once beside the app and every game draws it
from there. A game picture or font whose bytes equal an installed file is left
out of its bundle; build/app/assets/shared-assets.txt names the installed file
to draw instead. Speech ships once as Ogg Vorbis clips under assets/speech/,
and the narration WAVs they represent are omitted from the app and every
bundle; build/app/assets/speech.txt tells every host how to compose each
narration path from those clips (SpeechIndexText).

The manifest is plain text so every host can read it: one "KIND|PATH|TARGET"
line each, after the exact "#jungle-shared-assets-FORMAT" header.

    shared|assets/jungle-book/pages/|    read-only folder installed beside the app
    alias|assets/animal-count/latin.png|assets/jungle/font.png

Hosts reject a header or kind they do not know, so a later format (speech
manifests, compressed audio) raises FORMAT and its kinds together with the
hosts that read them; they always ship together.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

from book_catalog import LANGUAGES
from speech_codec import EncodeSpeech, SHIPPED, ValidateEncodedSpeech
from speech_manifest import BuildSpeechManifest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'build/app'
STAGE = ROOT / 'build/stage'
MANIFEST = 'assets/shared-assets.txt'
# Every host reads speech through this index; the full manifest stays beside
# the staged bundles for audits.
SPEECH_INDEX = 'assets/speech.txt'
SPEECH_HEADER = '#jungle-speech-1\n'
SPEECH_MANIFEST = 'speech-manifest.json'
NO_SPEECH = {'clips': {}, 'voices': {}, 'encoded': {}}
FORMAT = 1
HEADER = f"#jungle-shared-assets-{FORMAT}\n"
# Activities whose narration is recorded per language, as FOLDER/LANGUAGE/
# NAME.wav beside its receipt. Their other sounds are effects and stay WAV.
NARRATED = ('assets/animal-count/sounds', 'assets/drums/sounds', 'assets/hide_seek/sounds', 'assets/shapes/sounds')

# Installed beside the app: the menu's own files and the Picture Book.
INSTALLED = ('assets/jungle', 'assets/jungle-book', 'assets/hide_seek/scenes', 'assets/hide_seek/props', 'assets/dino-paint/art')
# Read-only artwork every game may draw from the installed copy.
SHARED = ('assets/jungle-book/counting/', 'assets/jungle-book/items/',
          'assets/jungle-book/pages/', 'assets/jungle-book/previews/',
          'assets/hide_seek/scenes/', 'assets/hide_seek/props/', 'assets/dino-paint/art/')
# Only pictures and fonts are aliased. Speech is described separately by
# SPEECH_MANIFEST: canonical clips ship once, encoded under SHIPPED, and the
# voice WAVs they represent are omitted.
PICTURES = ('.png', '.jpg', '.jpeg', '.webp')
# The host menu reads these directly, so they are never replaced by an alias.
HOST_ONLY = 'assets/jungle/'
COUNTING = ('tiger', 'frog', 'butterfly', 'ladybug', 'snail', 'elephant', 'giraffe', 'monkey', 'panda',
            'lion', 'zebra', 'crocodile', 'parrot', 'toucan', 'rabbit', 'cat', 'dog', 'sheep')

# Bundled games with staged assets: their source folders and extra files.
# Picture Book narration is installed; its bundle needs no copy of it.
GAMES = {
    'jungle-book': {'folders': ('assets/jungle-book',), 'skip': ('assets/jungle-book/sounds/',)},
    'jungle-abc': {'folders': ('assets/abc',)},
    'jungle-numbers': {'folders': ('assets/numbers',)},
    'animal-count': {'folders': ('assets/animal-count',),
                     'extra': {f'assets/animal-count/pictures/{name}.png': f'assets/jungle-book/counting/{name}.png'
                               for name in COUNTING}},
    'dino-paint': {'folders': ('assets/dino-paint',), 'voices': True},
    'jungle-shapes': {'folders': ('assets/shapes',)},
    'jungle-hide-seek': {'folders': ('assets/hide_seek',)},
    'jungle-drums': {'folders': ('assets/drums',)},
}


def SafePath(name):
    """A relative asset path without empty, '.' or '..' parts."""
    path = Path(name)
    return (name.startswith('assets/') and not path.is_absolute() and str(path) == name.rstrip('/')
            and all(part not in ('', '.', '..') for part in name.rstrip('/').split('/'))
            and '|' not in name and '\n' not in name and '\\' not in name)


def Shipped(name):
    """Whether a source file ships at all. Speech receipts stay in the source,
    and ABC Book carries its own spoken letters, so the book's copies do not."""
    path = Path(name)
    book_letters = name.startswith('assets/jungle-book/') and 'letters' in path.parts[:-1]
    book_narration = name.startswith('assets/jungle-book/sounds/') and path.suffix.lower() == '.wav'
    return not path.name.endswith('.speech.json') and not book_letters and not book_narration


def Folder(source):
    return {path.relative_to(ROOT).as_posix(): path for path in sorted((ROOT / source).rglob('*'))
            if path.is_file() and Shipped(path.relative_to(ROOT).as_posix())}


def Digest(path, cache):
    if path not in cache:
        cache[path] = hashlib.sha256(path.read_bytes()).hexdigest()
    return cache[path]


def GameFiles(name):
    """Every file a game reaches by path: {asset path: source file}."""
    game = GAMES[name]
    files = {}
    for folder in game['folders']:
        files.update(Folder(folder))
    for path, source in game.get('extra', {}).items():
        files[path] = ROOT / source
    for path in list(files):
        if any(path.startswith(prefix) for prefix in game.get('skip', ())):
            del files[path]
        elif game.get('voices') and Path(path).name.startswith('voice-'):
            del files[path]
    return files


# speech can be supplied when staging already built it, avoiding duplicate work;
# speech_files then names the encoded file of each shipped speech path.
def Plan(speech=None, speech_files=None):
    """(installed files, {alias: target}, {game: bundle files}), all checked."""
    speech = NO_SPEECH if speech is None else speech
    speech_files = {} if speech_files is None else speech_files
    speech_clips = set(speech['clips'])
    cache = {}
    installed = {}
    for folder in INSTALLED:
        installed.update(Folder(folder))
    games = {name: GameFiles(name) for name in GAMES}
    # Canonical copies: the menu's files first, then shared art, by path.
    canonical = {}
    candidates = sorted(installed, key=lambda path: (not path.startswith(HOST_ONLY), path))
    for path in candidates:
        if Path(path).suffix in PICTURES:
            canonical.setdefault(Digest(installed[path], cache), path)
    aliases = {}
    for path in candidates:
        if path.startswith(HOST_ONLY) or Path(path).suffix not in PICTURES:
            continue
        target = canonical[Digest(installed[path], cache)]
        if target != path:
            aliases[path] = target
    for files in games.values():
        for path, source in files.items():
            if Path(path).suffix in PICTURES and not path.startswith(HOST_ONLY):
                target = canonical.get(Digest(source, cache))
                if target and target != path:
                    aliases[path] = target
    for path in aliases:
        installed.pop(path, None)
    for path in list(installed):
        if path in speech['voices'] and path not in speech_clips:
            del installed[path]
    for path in speech_clips:
        installed.pop(path, None)
    for path, source in speech_files.items():
        assert SafePath(path) and path.startswith(SHIPPED + '/'), path
        installed[path] = Path(source)
    bundles = {name: {path: source for path, source in files.items()
                      if path not in aliases and not IsShared(path)
                      and path not in speech_clips and path not in speech['voices']}
               for name, files in games.items()}
    Check(installed, aliases)
    return installed, aliases, bundles


def IsShared(path):
    return any(path.startswith(prefix) for prefix in SHARED)


def Check(installed, aliases):
    for prefix in SHARED:
        assert SafePath(prefix) and prefix.endswith('/'), prefix
        logical = set(installed) | set(aliases)
        assert any(path.startswith(prefix) for path in logical), 'shared folder is empty: ' + prefix
    for path, target in aliases.items():
        assert SafePath(path) and SafePath(target), (path, target)
        # One step only: a target is a real installed file, never an alias.
        assert target in installed and target not in aliases, (path, target)


def ManifestText(aliases):
    lines = [HEADER]
    lines += [f'shared|{prefix}|\n' for prefix in SHARED]
    lines += [f'alias|{path}|{target}\n' for path, target in sorted(aliases.items())]
    return ''.join(lines)


def WriteIfChanged(path, text):
    """Keeps the file time when nothing changed, so make skips its users."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() == text:
        return
    temporary = path.with_name(path.name + '.new')
    temporary.write_text(text)
    os.replace(temporary, path)


def Sync(files, destination, owned):
    """Makes destination's owned folders hold exactly files, copying changes."""
    for folder in owned:
        root = destination / folder
        if not root.exists():
            continue
        for path in sorted(root.rglob('*'), reverse=True):
            name = path.relative_to(destination).as_posix()
            if path.is_symlink() or (path.is_file() and name not in files):
                path.unlink()
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()
    for name, source in sorted(files.items()):
        target = destination / name
        stat = source.stat()
        if target.is_file() and not target.is_symlink():
            current = target.stat()
            if current.st_size == stat.st_size and current.st_mtime_ns == stat.st_mtime_ns:
                continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + '.new')
        shutil.copy2(source, temporary)
        os.replace(temporary, target)


def Listing(files):
    return ''.join(f'{name} {source.stat().st_size} {source.stat().st_mtime_ns}\n'
                   for name, source in sorted(files.items()))


def CatalogGames(app=APP):
    """The active game bundle names in app/games/catalog.txt."""
    app = Path(app)
    games = []
    for line in (app / 'games/catalog.txt').read_text().splitlines():
        name = line.split('|', 1)[0]
        if not name:
            continue
        path = Path(name)
        assert path.suffix == '.zx' and not path.is_absolute() and len(path.parts) == 1, name
        assert name not in games, 'duplicate catalog game: ' + name
        assert (app / 'games' / name).is_file(), 'catalog game is not built: ' + name
        games.append(name)
    assert games, 'games/catalog.txt has no active games'
    return games


def StageReleaseApp(app=APP, destination=ROOT / 'build/package', program=True):
    """Copies the app, exe and only catalog-registered games to fresh staging.

    Concurrent build output is left untouched: an unregistered .zx beside the
    catalog is useful to another session but never leaks into a distribution.
    """
    app, destination = Path(app), Path(destination)
    games = CatalogGames(app)
    if destination.is_symlink() or destination.is_file():
        destination.unlink()
    else:
        shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True)
    if program:
        shutil.copy2(app / 'jungle', destination / 'jungle')
    shutil.copytree(app / 'assets', destination / 'assets')
    (destination / 'games').mkdir()
    shutil.copy2(app / 'games/catalog.txt', destination / 'games/catalog.txt')
    for name in games:
        shutil.copy2(app / 'games' / name, destination / 'games' / name)
    return games


def NarratedVoices(root=None):
    """{narration path: language} for the NARRATED activities. Every WAV in a
    language folder there is narration and must have its receipt."""
    root = ROOT if root is None else Path(root)
    voices = {}
    for folder in NARRATED:
        for path in sorted((root / folder).glob('*/*.wav')):
            if path.parent.name not in LANGUAGES:
                continue
            if not path.with_suffix('.speech.json').is_file():
                raise ValueError('narration without its speech receipt: ' + str(path))
            voices[path.relative_to(root).as_posix()] = path.parent.name
    return voices


def Speech(root=None):
    """(encoded speech manifest, {shipped path: encoded file}) for every
    narration path, checked against its sources."""
    root = ROOT if root is None else Path(root)
    speech = BuildSpeechManifest(root, extra_voices=NarratedVoices(root))
    encoded = EncodeSpeech(speech, root)
    speech = dict(speech, encoding=encoded['encoding'], encoded=encoded['encoded'],
                  shipping=dict(speech.get('shipping', {}),
                                clips='Ship each clip once, as Ogg Vorbis at its encoded path.',
                                index=SPEECH_INDEX))
    ValidateEncodedSpeech(speech, encoded['files'])
    return speech, encoded['files']


def SpeechIndexText(speech):
    """The hosts' speech index, after the exact SPEECH_HEADER line.

    "clip|PATH|FRAMES" lines name each shipped Ogg Vorbis file, by path order,
    and its exact frame count. One "voice|PATH|SEGMENTS" line per narration
    path follows, by path order; its segments, separated by spaces, are
    "CLIP:START:FRAMES", a range of the CLIPth clip line, or "FRAMES" of
    silence, played in order. Hosts reject any other header or line.
    """
    frames = {}
    for name, entry in speech['encoded'].items():
        count = speech['clips'][name]['frame_count']
        assert frames.setdefault(entry['path'], count) == count, entry['path']
    order = {path: index for index, path in enumerate(sorted(frames))}
    lines = [SPEECH_HEADER]
    lines += [f'clip|{path}|{frames[path]}\n' for path in sorted(frames)]
    for path, segments in sorted(speech['voices'].items()):
        assert SafePath(path) and path.endswith('.wav') and ' ' not in path, path
        parts = []
        for segment in segments:
            if 'silence' in segment:
                parts.append(str(segment['silence']))
            else:
                clip = order[speech['encoded'][segment['clip']]['path']]
                parts.append(f'{clip}:{segment["start"]}:{segment["frames"]}')
        lines.append(f'voice|{path}|{" ".join(parts)}\n')
    return ''.join(lines)


def StageSharedAssets(app=APP, stage=STAGE, speech=None):
    """Installs shared assets, encoded speech and both manifests; stages each
    game's bundle files.

    Folders are synchronized, so files removed from assets/ disappear from the
    installed app and the staged bundles. build/stage/GAME.files lists each
    game's staged files and changes only when they do. SPEECH, as Speech()
    returns it, is built when not given.
    """
    app, stage = Path(app), Path(stage)
    speech, speech_files = Speech() if speech is None else speech
    installed, aliases, bundles = Plan(speech, speech_files)
    Sync(installed, app, INSTALLED + (SHIPPED,))
    WriteIfChanged(app / MANIFEST, ManifestText(aliases))
    WriteIfChanged(app / SPEECH_INDEX, SpeechIndexText(speech))
    WriteIfChanged(stage / SPEECH_MANIFEST, json.dumps(speech, ensure_ascii=False, separators=(',', ':')) + '\n')
    for name, files in bundles.items():
        root = stage / name
        if root.is_symlink() or root.is_file():
            root.unlink()
        (root / 'assets').mkdir(parents=True, exist_ok=True)
        for child in root.iterdir():
            if child.name != 'assets':
                shutil.rmtree(child) if child.is_dir() and not child.is_symlink() else child.unlink()
        Sync(files, root, ('assets',))
        WriteIfChanged(stage / (name + '.files'), Listing(files))
    (stage / '.shared-assets').touch(exist_ok=True)
    for path in sorted((app / 'assets').rglob('*'), reverse=True):
        name = path.relative_to(app).as_posix()
        if name in (MANIFEST, SPEECH_INDEX):
            continue
        if path.is_symlink() or (path.is_file() and name not in installed):
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    # Earlier transitional speech staging.
    (stage / '.speech-assets').unlink(missing_ok=True)
    return installed, aliases, bundles


def WebAliases():
    """{alias: source file of its target}, for the browser's asset packs.

    The packs store identical bytes once, so each alias costs one index entry.
    """
    installed, aliases, _ = Plan()
    return {path: installed[target] for path, target in aliases.items()}


if __name__ == '__main__':
    if sys.argv[1:]:
        raise SystemExit('usage: shared_assets.py')
    installed, aliases, bundles = StageSharedAssets()
    print(f'Shared assets: {len(installed)} installed files, {len(aliases)} aliases, '
          + ', '.join(f'{name} {len(files)}' for name, files in bundles.items()))

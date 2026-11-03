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

Every picture Kryon may draw before it has loaded gets a small preview under
assets/previews/ (tools/web_images.py prepare_native_previews), installed
beside the app and shared like the artwork.

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
from speech_manifest import BuildSpeechManifest, AddSpeechProfiles
from web_images import (PREVIEW_FOLDERS, PREVIEW_ROOT, RUNTIME_ROOT,
                        prepare_native_previews, prepare_runtime_images, preview_path)

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
NARRATED = ('assets/jungle-book/story-sounds', 'assets/animal-count/sounds', 'assets/drums/sounds', 'assets/garden/sounds', 'assets/hide_seek/sounds', 'assets/shapes/sounds', 'assets/jungle/title/guide', 'assets/jungle/title/desert')

# Installed beside the app: the menu's own files and the Picture Book.
INSTALLED = ('assets/jungle', 'assets/jungle-book', 'assets/hide_seek/scenes', 'assets/hide_seek/props', 'assets/dino-paint/art', 'assets/collectibles')
# Read-only artwork every game may draw from the installed copy.
SHARED = ('assets/jungle-book/counting/', 'assets/jungle-book/items/',
          'assets/jungle-book/pages/', 'assets/jungle-book/portraits/', 'assets/jungle-book/previews/',
          'assets/hide_seek/scenes/', 'assets/hide_seek/props/', 'assets/dino-paint/art/',
          'assets/collectibles/', RUNTIME_ROOT)
# Previews of the pictures in PREVIEW_FOLDERS, generated while staging; their
# cache holds one set, keyed by each picture's bytes.
PREVIEW_CACHE = 'build/native-previews'
RUNTIME_CACHE = 'work/runtime-image-cache'
# Only pictures and fonts are aliased. Speech is described separately by
# SPEECH_MANIFEST: canonical clips ship once, encoded under SHIPPED, and the
# voice WAVs they represent are omitted.
PICTURES = ('.png', '.webp')
# The host menu reads these directly, so they are never replaced by an alias.
HOST_ONLY = 'assets/jungle/'
COUNTING = ('tiger', 'frog', 'butterfly', 'ladybug', 'snail', 'elephant', 'giraffe', 'monkey', 'panda',
            'lion', 'zebra', 'crocodile', 'parrot', 'toucan', 'rabbit', 'cat', 'dog', 'sheep')
PORT_FOLDERS = ('assets/fishing', 'assets/beach_families')

# Bundled games with staged assets: their source folders and extra files.
# Picture Book narration is installed; its bundle needs no copy of it.
GAMES = {
    # The Sweet Porridge pot tap flies the colored magic pot.
    'jungle-book': {'folders': ('assets/jungle-book',), 'skip': ('assets/jungle-book/sounds/', 'assets/jungle-book/story-sounds/'),
                    'extra': {'assets/collectibles/magic-pot.webp': 'assets/collectibles/magic-pot.webp'}},
    'jungle-abc': {'folders': ('assets/abc',)},
    'jungle-numbers': {'folders': ('assets/numbers',)},
    'animal-count': {'folders': ('assets/animal-count',),
                     'extra': {f'assets/animal-count/pictures/{name}.webp': f'assets/jungle-book/counting/{name}.webp'
                               for name in COUNTING}},
    'dino-paint': {'folders': ('assets/dino-paint',), 'voices': True},
    'jungle-shapes': {'folders': ('assets/shapes',)},
    'jungle-jigsaw': {'folders': ('assets/jigsaw',)},
    # The hidden paper's chime comes from the book bundle's shared sound.
    'jungle-hide-seek': {'folders': ('assets/hide_seek',),
                         'extra': {'assets/jungle-book/collect.wav': 'assets/jungle-book/collect.wav'}},
    # The hidden paper's chime is the only sound Matching Pairs adds.
    'jungle-matching': {'folders': (),
                        'extra': {'assets/jungle-book/collect.wav': 'assets/jungle-book/collect.wav'}},
    # The hidden paper's chime and the colored drum it flies.
    'jungle-drums': {'folders': ('assets/drums',),
                     'extra': {'assets/jungle-book/collect.wav': 'assets/jungle-book/collect.wav',
                               'assets/collectibles/drum.webp': 'assets/collectibles/drum.webp'}},
    # The hidden paper's chime and the colored sunflower it flies.
    # The Farm chooser draws the title scene's own Campus arrow sign.
    'jungle-garden': {'folders': ('assets/garden',),
                      'extra': {'assets/jungle-book/collect.wav': 'assets/jungle-book/collect.wav',
                                'assets/collectibles/sunflower.webp': 'assets/collectibles/sunflower.webp',
                                'assets/garden/play/campus-arrow.webp': 'assets/jungle/title/objects/wood-arrow-right.webp',
                                'assets/garden/play/campus-arrow-glow.webp': 'assets/jungle/title/objects/wood-arrow-right-glow.webp',
                                'assets/garden/play/market-arrow.webp': 'assets/jungle/title/objects/wood-arrow-left.webp',
                                'assets/garden/play/market-arrow-glow.webp': 'assets/jungle/title/objects/wood-arrow-left-glow.webp'}},
    'jungle-fishing': {'folders': ('assets/fishing',), 'skip': ('assets/fishing/previews/',)},
    'jungle-beach-families': {'folders': ('assets/beach_families',), 'skip': ('assets/beach_families/previews/',)},
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


def PortGamePreviews():
    """Reviewed 128px exports, keyed by their full picture's logical path."""
    return {f'{folder}/{path.name}': path
            for folder in PORT_FOLDERS
            for path in sorted((ROOT / folder / 'previews').glob('*.webp'))
            if (ROOT / folder / path.name).is_file()}


def Previews():
    """{preview path: generated file} for every picture in PREVIEW_FOLDERS."""
    files = {}
    for folder in sorted(PREVIEW_FOLDERS):
        files.update(Folder(folder))
    previews = prepare_native_previews(files, ROOT / PREVIEW_CACHE)
    previews.update({preview_path(name): path for name, path in PortGamePreviews().items()})
    return previews


# speech can be supplied when staging already built it, avoiding duplicate work;
# speech_files then names the encoded file of each shipped speech path.
# previews, from Previews(), are installed as they are; they are never aliased.
def PlanWithRuntime(speech=None, speech_files=None, previews=None):
    """(installed files, aliases, bundles, runtime exports), all checked."""
    speech = NO_SPEECH if speech is None else speech
    speech_files = {} if speech_files is None else speech_files
    speech_clips = set(speech['clips'])
    cache = {}
    installed = {}
    for folder in INSTALLED:
        installed.update(Folder(folder))
    games = {name: GameFiles(name) for name in GAMES}
    runtime_sources = {}
    for files in (installed, *games.values()):
        for path, source in files.items():
            if not path.startswith(HOST_ONLY) and Path(path).suffix in PICTURES:
                runtime_sources[path] = source
    runtime = prepare_runtime_images(runtime_sources, ROOT / RUNTIME_CACHE)
    runtime_by_digest = {}
    aliases = {}
    for path, export in sorted(runtime.items()):
        installed[export.target] = export.source
        aliases[path] = export.target
        runtime_by_digest.setdefault(export.info['source_sha256'], export.target)
    for path in aliases:
        installed.pop(path, None)

    # Canonical copies: the menu's files first, then remaining shared art, by path.
    canonical = {}
    candidates = sorted(installed, key=lambda path: (not path.startswith(HOST_ONLY), path))
    for path in candidates:
        if Path(path).suffix in PICTURES:
            canonical.setdefault(Digest(installed[path], cache), path)
    for path in candidates:
        if path.startswith(HOST_ONLY) or Path(path).suffix not in PICTURES:
            continue
        target = canonical[Digest(installed[path], cache)]
        if target != path:
            aliases[path] = target
    for files in games.values():
        for path, source in files.items():
            if path in aliases:
                continue
            if Path(path).suffix in PICTURES and not path.startswith(HOST_ONLY):
                target = canonical.get(Digest(source, cache))
                if target is None:
                    target = runtime_by_digest.get(Digest(source, cache))
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
    for path, source in (previews or {}).items():
        assert SafePath(path) and path.startswith(PREVIEW_ROOT) and path not in installed, path
        installed[path] = Path(source)
    bundles = {name: {path: source for path, source in files.items()
                      if path not in aliases and not IsShared(path)
                      and path not in speech_clips and path not in speech['voices']}
               for name, files in games.items()}
    Check(installed, aliases)
    return installed, aliases, bundles, runtime


def Plan(speech=None, speech_files=None, previews=None):
    """(installed files, {alias: target}, {game: bundle files}), all checked."""
    installed, aliases, bundles, _ = PlanWithRuntime(speech, speech_files, previews)
    return installed, aliases, bundles


def IsShared(path):
    return any(path.startswith(prefix) for prefix in SHARED + (PREVIEW_ROOT,))


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
    lines += [f'shared|{prefix}|\n' for prefix in SHARED + (PREVIEW_ROOT,)]
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
    speech = AddSpeechProfiles(BuildSpeechManifest(root, extra_voices=NarratedVoices(root)), root)
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


def StageSharedAssets(app=APP, stage=STAGE, speech=None, previews=None):
    """Installs shared assets, encoded speech, previews and both manifests;
    stages each game's bundle files.

    Folders are synchronized, so files removed from assets/ disappear from the
    installed app and the staged bundles. build/stage/GAME.files lists each
    game's staged files and changes only when they do. SPEECH, as Speech()
    returns it, and PREVIEWS, as Previews() returns them, are built when not
    given.
    """
    app, stage = Path(app), Path(stage)
    speech, speech_files = Speech() if speech is None else speech
    previews = Previews() if previews is None else previews
    installed, aliases, bundles, _ = PlanWithRuntime(speech, speech_files, previews)
    Sync(installed, app, INSTALLED + (SHIPPED, RUNTIME_ROOT.rstrip('/'), PREVIEW_ROOT.rstrip('/')))
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


def WebFiles():
    """({alias: runtime file}, metadata) for the browser's asset packs.

    Runtime exports are already WebP, so the browser reuses their exact bytes.
    """
    installed, aliases, _, runtime = PlanWithRuntime()
    runtime_by_target = {export.target: export for export in runtime.values()}
    files, metadata = {}, {}
    for path, target in aliases.items():
        export = runtime_by_target.get(target)
        if export is None:
            continue
        files[path] = installed[target]
        metadata[path] = {**export.info, 'source_path': path}
    return files, metadata


def WebAliases():
    """{alias: source file of its target}, for callers needing native staging."""
    return WebFiles()[0]


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, default=APP)
    parser.add_argument('--stage', type=Path)
    # --app alone must also keep bundle staging out of the owner's app.

    args = parser.parse_args()
    installed, aliases, bundles = StageSharedAssets(app=args.app, stage=args.stage or (STAGE if args.app.resolve() == APP.resolve() else args.app / 'stage'))
    print(f'Shared assets: {len(installed)} installed files, {len(aliases)} aliases, '
          + ', '.join(f'{name} {len(files)}' for name, files in bundles.items()))

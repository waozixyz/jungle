"""Build preload dependencies from the catalog, build recipes and source imports.

Logical paths remain the same ones used by the game and the pack index. Both
orientations are included. Speech is resolved to encoded clips per locale and
profile, so no runtime maintains a second list of books, pictures or voices.

Picture Book downloads one book at a time: its activity lists only what its
shelves draw, and each book (picture_books) its own pictures per orientation
and its narration, so opening a shelf never fetches a page.
"""
import json
from pathlib import Path
import re

from book_catalog import BOOKS, BOOK_GROUPS, voice_path

LANGUAGES = ('en', 'de', 'es')
PROFILES = ('normal', 'slow', 'fast')
BOOK_ACTIVITY = 'jungle-book'
# The two stories in story-shelf order; the game's selected_story indexes it.
STORIES = (('sweet-porridge', 'sweet_porridge'), ('town-musicians', 'town_musicians'))
# Picture Book's book media come with their books. Its shelves draw only their
# covers, never the counting cut-outs or other games' collectibles.
BOOK_MEDIA = ('assets/jungle-book/pages/', 'assets/jungle-book/portraits/', 'assets/jungle-book/items/',
              'assets/jungle-book/counting/', 'assets/jungle-book/previews/', 'assets/collectibles/')


def voice_clips(speech, voices, profile):
    """The encoded clips of narration paths VOICES in PROFILE, which falls
    back to the normal recording."""
    clips = set()
    for path in voices:
        segments = speech['voices'].get('assets/speech-profiles/'+profile+'/'+path[7:], speech['voices'].get(path))
        if segments is None:
            raise ValueError('Missing book narration: '+path)
        clips.update(speech['encoded'][segment['clip']]['path'] for segment in segments if 'clip' in segment)
    return clips


def picture_books(root, paths, speech):
    """Picture Book's books in shelf order, then the stories, each with only
    its own files: pictures per orientation (portrait story pages also draw
    the landscape picture's paper), the collectible a page offers and both
    reading modes' narration per language and profile."""
    root = Path(root)
    colors = {}
    for entry in json.loads((root/'tools/collectibles.json').read_text())['collectibles']:
        source = entry['source']
        if entry.get('pending') or entry.get('color') not in paths:
            continue
        if source['kind'] == 'book':
            colors[source['page']] = entry['color']
        elif source['kind'] == 'story':
            colors[source['story']+'/'+source['page']] = entry['color']
    def book(name, cover, landscape, portrait, voices):
        for path in {cover, *landscape, *portrait}:
            if path not in paths:
                raise ValueError('Unstaged book picture: '+path)
        # A profile without its own recordings uses the normal list.
        speech_clips = {}
        for language in LANGUAGES:
            speech_clips[language] = {}
            for profile in PROFILES:
                clips = sorted(voice_clips(speech, voices[language], profile))
                if set(clips)-paths:
                    raise ValueError('Unstaged narration: '+str(sorted(set(clips)-paths)))
                if profile == 'normal' or clips != speech_clips[language]['normal']:
                    speech_clips[language][profile] = clips
        return {'id': name, 'cover': cover, 'files': {'landscape': sorted(set(landscape)), 'portrait': sorted(set(portrait))},
                'voices': sorted({path for paths in voices.values() for path in paths}), 'speech': speech_clips}
    books = dict(BOOKS)
    result = []
    for category in (category for _, members in BOOK_GROUPS for category in members):
        pages = [f'assets/jungle-book/pages/{name}.avif' for name in books[category]]
        own = pages+[colors[page] for page in pages if page in colors]
        voices = {language: [voice_path(name, language, simple) for name in books[category] for simple in (True, False)]
                  for language in LANGUAGES}
        result.append(book(category, f'assets/jungle-book/previews/{category}.avif', own, own, voices))
    for name, data in STORIES:
        pages = json.loads((root/'tools'/(data+'.json')).read_text())['pages']
        landscape = [f'assets/jungle-book/pages/{page["asset"]}.avif' for page in pages]
        collectible = [colors[name+'/'+page['asset']] for page in pages if name+'/'+page['asset'] in colors]
        portrait = [f'assets/jungle-book/portraits/{page["portrait_asset"]}.avif' for page in pages]
        voices = {language: [f'assets/jungle-book/story-sounds/{language}/{page["asset"]}.wav' for page in pages]
                  for language in LANGUAGES}
        result.append(book(name, landscape[0], landscape+collectible, portrait+landscape+collectible, voices))
    return result


def source_assets(source, seen=None):
    seen = set() if seen is None else seen
    source = source.resolve()
    if source in seen:
        return set()
    seen.add(source)
    text = re.sub(r'//[^\n]*', '', source.read_text())
    assets = set(re.findall(r'"(assets/[^"\n]+)"', text))
    for name in re.findall(r'#import[^\n]*file\s+"([^"]+)"', text):
        assets.update(source_assets(source.parent / name, seen))
    return assets


def book_pack_groups(manifest):
    """{logical path: pack group} for Picture Book: each shelf's covers, each
    book's pictures, its portrait-only pictures, its collectibles and its
    narration per language and profile pack apart, so opening a shelf or a
    book downloads nothing of another book."""
    groups = {}
    for activity in manifest['activities']:
        for shelf, covers in activity.get('shelves', {}).items():
            for path in covers:
                groups.setdefault(path, 'shelf-'+(shelf or 'books'))
        for book in activity.get('books', ()):
            for orientation in ('landscape', 'portrait'):
                for path in book['files'][orientation]:
                    kind = '-collectibles' if path.startswith(('assets/jungle-book/items/', 'assets/collectibles/')) else (
                        '' if orientation == 'landscape' else '-portrait')
                    groups.setdefault(path, 'book-'+book['id']+kind)
            for language, profiles in book['speech'].items():
                for profile in PROFILES:
                    for clip in profiles.get(profile, ()):
                        groups.setdefault(clip, f'speech-{language}-{book["id"]}-{profile}')
    return groups


def build_activity_manifest(root, paths, speech, games):
    root, paths = Path(root), set(paths)
    recipes = (root/'Makefile').read_text()
    result = {'format': 1, 'activities': [], 'scenes': {}}
    for line in (root/'games/catalog.txt').read_text().splitlines():
        if '|' not in line:
            continue
        bundle, title, _, cover, *_ = line.split('|')
        name = bundle.removesuffix('.zx')
        recipe = re.search(r'^\$\(APP\)/games/' + re.escape(bundle) + r':(.*?)(?=\n\n)', recipes, re.M | re.S)
        if not recipe:
            raise ValueError('Missing activity build recipe: ' + bundle)
        source = re.findall(r'games/[\w/-]+\.zi', recipe[1])[-1]
        refs = source_assets(root/source)
        config = games.get(name, {})
        refs.update(folder.rstrip('/')+'/' for folder in config.get('folders', ()))
        refs.update(config.get('extra', {}))
        refs.add(cover)
        # Shared host effects can run on entry, exit, or collection.
        refs.add('assets/jungle/sounds/')
        exact = {ref for ref in refs if Path(ref).suffix}
        prefixes = tuple(ref for ref in refs if not Path(ref).suffix)
        def used(path):
            return path in exact or path.startswith(prefixes)
        books = picture_books(root, paths, speech) if name == BOOK_ACTIVITY else []
        book_voices = {path for book in books for path in book.pop('voices')}
        common = sorted(path for path in paths if used(path) and not path.startswith('assets/speech/')
                        and path != 'assets/speech.txt' and not (books and path.startswith(BOOK_MEDIA)))
        voices = {}
        for language in ('en', 'de', 'es'):
            voices[language] = {}
            for profile in ('normal', 'slow', 'fast'):
                clips = set()
                for path, segments in speech['voices'].items():
                    # Profile selection falls back to the normal recording.
                    if path.startswith('assets/speech-profiles/') or not used(path) or path in book_voices:
                        continue
                    lang = re.search(r'/(en|de|es)/', path)
                    clip_languages = {speech.get('clips', {}).get(s['clip'], {}).get('language')
                                      for s in segments if 'clip' in s}
                    clip_languages.discard(None)
                    if (lang and lang[1] != language) or (not lang and clip_languages and language not in clip_languages):
                        continue
                    selected = f'assets/speech-profiles/{profile}/'+path[7:]
                    for segment in speech['voices'].get(selected, segments):
                        if 'clip' in segment:
                            clips.add(speech['encoded'][segment['clip']]['path'])
                missing = clips-paths
                if missing:
                    raise ValueError('Unstaged narration: '+str(sorted(missing)))
                voices[language][profile] = sorted(clips)
        activity = {'id': name, 'title': title, 'cover': cover, 'files': common, 'speech': voices}
        if books:
            # Each shelf, by the title's book-start request, draws its books'
            # covers: the category previews, or the stories' first pages.
            activity['shelves'] = {'': sorted(book['cover'] for book in books[:-len(STORIES)]),
                                   'sweet-porridge': sorted(book['cover'] for book in books[-len(STORIES):])}
            activity['books'] = books
        result['activities'].append(activity)
    scenes_path = root/'tools/title_hotspots.json'
    if scenes_path.exists():
        for base in json.loads(scenes_path.read_text())['scenes']:
            for scene in (base, base.get('portrait', {})):
                if not scene:
                    continue
                def pictures(value):
                    if isinstance(value, dict):
                        return set().union(*(pictures(v) for v in value.values()))
                    if isinstance(value, list):
                        return set().union(*(pictures(v) for v in value))
                    return {value} if isinstance(value, str) and value in paths else set()
                own = dict(scene); own.pop('portrait', None)
                result['scenes'][scene['image']] = sorted(pictures(own))
    return result

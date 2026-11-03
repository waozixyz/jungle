"""Build preload dependencies from the catalog, build recipes and source imports.

Logical paths remain the same ones used by the game and the pack index. Both
orientations are included. Speech is resolved to encoded clips per locale and
profile, so no runtime maintains a second list of books, pictures or voices.
"""
import json
from pathlib import Path
import re


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
        common = sorted(path for path in paths if used(path) and not path.startswith('assets/speech/')
                        and path != 'assets/speech.txt')
        voices = {}
        for language in ('en', 'de', 'es'):
            voices[language] = {}
            for profile in ('normal', 'slow', 'fast'):
                clips = set()
                for path, segments in speech['voices'].items():
                    # Profile selection falls back to the normal recording.
                    if path.startswith('assets/speech-profiles/') or not used(path):
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
        result['activities'].append({'id': name, 'title': title, 'cover': cover, 'files': common, 'speech': voices})
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

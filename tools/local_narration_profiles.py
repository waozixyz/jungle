"""Offline Qwen profile staging. Never imports a model or promotes source assets.

Call stage_profiles(root, corpus) only after local_narration.validate succeeds.
The returned inventory lives at work/qwen-profiles/staged/assets/speech-profiles.json.
Normal mappings refer to the exact natural-rate Qwen stage, without copying it.
After promoting that stage, the caller may copy the validated slow/fast tree and
publish this inventory last. validate_inventory checks the resulting asset tree.
"""
from pathlib import Path
import math
import subprocess
import wave

import local_narration as narration
from book_speech import read_clip

STAGE = Path('work/qwen-profiles')
FORMAT = 'jungle-speech-profiles-2'
MODEL = 'qwen3-tts-0.6b-customvoice'
SPEEDS = {'normal': 1.0, 'slow': .8, 'fast': 1.25}


def profile_path(name, profile):
    if (not isinstance(name, str) or not name.startswith('assets/') or not name.endswith('.wav')
            or any(c in name for c in ('|', '\n', '\r', '\\', '\x00'))
            or any(p in ('', '.', '..', 'speech-profiles') for p in name.split('/'))
            or profile not in SPEEDS):
        raise ValueError(f'unsafe canonical profile path: {name!r}')
    return name if profile == 'normal' else f'assets/speech-profiles/{profile}/' + name.removeprefix('assets/')


def _measure(path):
    with wave.open(str(path), 'rb') as clip:
        if clip.getparams()[:3] != (1, 2, narration.RATE) or clip.getcomptype() != 'NONE':
            raise ValueError(f'invalid profile PCM: {path}')
        frames = clip.getnframes()
        if not 0 < frames <= narration.RATE * 60:
            raise ValueError(f'invalid profile frame count: {path}')
        count = 0
        while data := clip.readframes(16384):
            count += len(data)
        if count != frames * 2:
            raise ValueError(f'truncated profile PCM: {path}')
    return frames


def _evidence(path, language):
    return dict(sha256=narration.digest(path), receipt_sha256=narration.digest(path.with_suffix('.speech.json')),
                frame_count=_measure(path), language=language)


def _parts(entry, profile):
    return [dict(source=profile_path(part['source'], profile)) if 'source' in part else dict(part)
            for part in entry['recipe']['parts']]


def _assembled(root, parts):
    return b''.join(read_clip(narration._inside(root, part['source']))[0] if 'source' in part
                    else bytes(part['silence_frames'] * 2) for part in parts)


def stage_profiles(root, corpus):
    """Validate the complete Qwen stage, then stage slow/fast PCM and receipts.

    All input paths are read-only. Returns the v2 inventory; does not publish it.
    Call again to safely recreate the stage; ffmpeg is bounded to one thread.
    """
    root = Path(root).resolve()
    result = narration.validate(root, corpus)
    if result['identity']['model'] != MODEL:
        raise ValueError('profiles require the approved Qwen model')
    ordered = narration._order(root, corpus)
    output = narration._ignored(root, STAGE / 'staged')
    normal = narration._inside(root, (narration.STAGE / 'staged').as_posix())
    inventory = dict(format=FORMAT, model=MODEL, voice='Serena', languages=['en', 'de', 'es'],
                     default='normal', corpus_sha256=narration._identity(corpus), profiles={})
    for profile, speed in SPEEDS.items():
        mappings, recordings = {}, {}
        for name in ordered:
            entry = corpus[name]
            source = narration._asset(normal, name)
            target_name = profile_path(name, profile)
            mappings[name] = target_name
            if profile == 'normal':
                recordings[name] = _evidence(source, entry['language'])
                continue
            target = narration._inside(output, target_name)
            target.parent.mkdir(parents=True, exist_ok=True)
            metadata = dict(result['identity'], text=entry['text'], language=entry['language'],
                            speed=speed, profile=profile, original_path=name,
                            source_sha256=narration.digest(source),
                            source_receipt_sha256=narration.digest(source.with_suffix('.speech.json')),
                            input_identity=entry['input_identity'])
            temporary = target.with_name(target.stem + '.new.wav')
            if 'sources' in entry:
                parts = _parts(entry, profile)
                metadata.update(method=narration.METHOD,
                                recipe=dict(entry['recipe'], parts=parts),
                                sources=[dict(path=profile_path(s, profile),
                                              sha256=narration.digest(output / profile_path(s, profile)))
                                         for s in entry['sources']])
                with wave.open(str(temporary), 'wb') as clip:
                    clip.setparams((1, 2, narration.RATE, 0, 'NONE', 'not compressed'))
                    clip.writeframes(_assembled(output, parts))
            else:
                metadata['method'] = 'Offline ffmpeg atempo from approved natural-rate Qwen PCM'
                subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-threads', '1',
                                '-i', str(source), '-map_metadata', '-1', '-af', f'atempo={speed}',
                                '-ac', '1', '-ar', str(narration.RATE), '-c:a', 'pcm_s16le', str(temporary)],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=180)
            frames = _measure(temporary)
            temporary.replace(target)
            narration._write_json(target.with_suffix('.speech.json'),
                                  dict(metadata, sha256=narration.digest(target), frame_count=frames,
                                       duration=frames / narration.RATE))
            recordings[name] = _evidence(target, entry['language'])
        inventory['profiles'][profile] = dict(speed=speed, voices=mappings, recordings=recordings)
    validate_inventory(output, inventory, normal_root=normal)
    narration._write_json(output / 'assets/speech-profiles.json', inventory)
    return inventory


def validate_inventory(root, inventory, *, normal_root=None):
    """Validate full coverage, paths, receipts, measured frames and exact recipes.

    normal_root is only for validating an unpublished stage. With it omitted,
    all normal Qwen audio must already be promoted into root/assets.
    Returns canonical receipts for the manifest's exact recipe construction.
    """
    root = Path(root).resolve()
    normal_root = root if normal_root is None else Path(normal_root).resolve()
    if not isinstance(inventory, dict):
        raise ValueError('speech profile inventory must be an object')
    if (inventory.get('format'), inventory.get('model'), inventory.get('voice'),
            inventory.get('languages'), inventory.get('default')) != (
            FORMAT, MODEL, 'Serena', ['en', 'de', 'es'], 'normal'):
        raise ValueError('unsupported multilingual speech profiles')
    profiles = inventory.get('profiles')
    if not isinstance(profiles, dict) or set(profiles) != set(SPEEDS):
        raise ValueError('expected three multilingual speech profiles')
    canonical = {p.relative_to(normal_root).as_posix().removesuffix('.speech.json') + '.wav'
                 for p in narration._receipts(normal_root)}
    if not canonical:
        raise ValueError('empty canonical profile inventory')
    if normal_root != root:
        expected = {profile_path(name, profile) for name in canonical for profile in ('slow', 'fast')}
        actual = {p.relative_to(root).as_posix() for p in (root / 'assets').rglob('*.wav')}
        actual_receipts = {p.relative_to(root).as_posix().removesuffix('.speech.json') + '.wav'
                           for p in (root / 'assets').rglob('*.speech.json')}
        if actual != expected or actual_receipts != expected:
            raise ValueError('incomplete or extra staged profile inventory')
    receipts, corpus = {}, {}
    for profile, speed in SPEEDS.items():
        entry = profiles[profile]
        if (not isinstance(entry, dict) or type(entry.get('speed')) not in (float, int)
                or entry['speed'] != speed or not isinstance(entry.get('voices'), dict)
                or not isinstance(entry.get('recordings'), dict)
                or set(entry['voices']) != canonical or set(entry['recordings']) != canonical):
            raise ValueError('incomplete multilingual speech profile: ' + profile)
        for name in sorted(canonical):
            narration._asset(normal_root, name)
            target = entry['voices'][name]
            if target != profile_path(name, profile):
                raise ValueError('unsafe speech profile mapping: ' + name)
            asset_root = normal_root if profile == 'normal' else root
            path = narration._inside(asset_root, target)
            receipt_path = narration._inside(asset_root, target.removesuffix('.wav') + '.speech.json')
            receipt = narration._json(receipt_path)
            if (not isinstance(receipt, dict) or not isinstance(receipt.get('text'), str)
                    or not receipt['text'].strip() or not isinstance(receipt.get('input_identity'), dict)):
                raise ValueError('invalid profile receipt: ' + target)
            language = narration.identify_language(name, receipt)
            if (type(receipt.get('speed')) not in (int, float)
                    or (receipt.get('provider'), receipt.get('model'), receipt.get('voice'),
                        receipt.get('speed'), receipt.get('language')) != (
                        'local_speech', MODEL, 'Serena', speed, language)
                    or not receipt.get('pack')):
                raise ValueError('profile receipt identity mismatch: ' + target)
            evidence = _evidence(path, language)
            recorded = entry['recordings'][name]
            if (not isinstance(recorded, dict) or type(recorded.get('frame_count')) is not int
                    or evidence != recorded or receipt.get('sha256') != evidence['sha256']):
                raise ValueError('profile evidence mismatch: ' + target)
            duration = receipt.get('duration')
            if (type(duration) not in (int, float) or not math.isfinite(duration)
                    or duration != evidence['frame_count'] / narration.RATE):
                raise ValueError('profile duration mismatch: ' + target)
            if profile == 'normal':
                receipts[name] = receipt
                corpus[name] = {k: receipt[k] for k in ('text', 'language', 'input_identity')}
                if 'sources' in receipt:
                    corpus[name].update(sources=[s['path'] for s in receipt['sources']], recipe=receipt['recipe'])
            else:
                original = receipts[name]
                normal_evidence = profiles['normal']['recordings'][name]
                if receipt['pack'] != original['pack']:
                    raise ValueError('profile pack identity mismatch: ' + target)
                if (receipt.get('profile'), receipt.get('original_path'), receipt.get('source_sha256'),
                        receipt.get('source_receipt_sha256'), receipt.get('text'), receipt.get('input_identity')) != (
                        profile, name, normal_evidence['sha256'], normal_evidence['receipt_sha256'],
                        original['text'], original['input_identity']):
                    raise ValueError('profile source identity mismatch: ' + target)
                if type(receipt.get('frame_count')) is not int or receipt['frame_count'] != evidence['frame_count']:
                    raise ValueError('profile measured frames mismatch: ' + target)
                if 'sources' not in original and not (
                        evidence['frame_count'] > normal_evidence['frame_count'] if profile == 'slow'
                        else evidence['frame_count'] < normal_evidence['frame_count']):
                    raise ValueError('profile speed duration mismatch: ' + target)
            original = receipts[name]
            if 'sources' in original:
                expected_recipe = narration._recipe(original['text'], [s['path'] for s in original['sources']])
                parts = _parts(dict(recipe=expected_recipe), profile)
                sources = [dict(path=profile_path(s['path'], profile),
                                sha256=narration.digest(narration._inside(normal_root if profile == 'normal' else root,
                                                                          profile_path(s['path'], profile))))
                           for s in original['sources']]
                if (receipt.get('method') != narration.METHOD or receipt.get('sources') != sources
                        or receipt.get('recipe') != dict(expected_recipe, parts=parts)):
                    raise ValueError('profile assembly provenance mismatch: ' + target)
                with wave.open(str(path)) as clip:
                    if clip.readframes(clip.getnframes()) != _assembled(normal_root if profile == 'normal' else root, parts):
                        raise ValueError('profile assembly PCM mismatch: ' + target)
    narration._order(normal_root, corpus)
    identity = narration._harness(receipts[next(iter(receipts))])
    for name, receipt in receipts.items():
        expected = narration._metadata(corpus[name], identity, normal_root)
        if any(receipt.get(key) != value for key, value in expected.items()):
            raise ValueError('normal profile receipt mismatch: ' + name)
    if narration._identity(corpus) != inventory.get('corpus_sha256'):
        raise ValueError('profile corpus identity mismatch')
    return receipts

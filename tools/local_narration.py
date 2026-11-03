"""Offline narration staging; importing this module never loads a speech engine.

API: capture_corpus(root) freezes canonical receipts and original input hashes.
Generate with generate(root, {'model': 'Qwen3-TTS-...', 'pack': <exact identity>},
engine, corpus=corpus), where engine is the caller's local_speech.Engine(pack).
Only engine.write(text, 'Serena', language, output_path) is called, at its natural
rate. validate(root, corpus) verifies the entire stage. promote(root, corpus) is
an explicit, separate operation; it backs up every original before replacing any.
The stage CLI loads local_speech_qwen.py from an explicit --harness-root and
passes the --pack JSON object to Engine. --provider-module selects another
safe Python filename under that root. --workers runs independent spawned CPU
engines with exclusive request claims. pause requests a validated checkpoint
stop; stage --resume retains verified clips and clears that pause. Per-item progress is flushed to stderr;
the final validation summary is JSON on stdout.
Promotion is deliberately available only through the Python API.
"""
from array import array
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
import fcntl
import importlib.util
import multiprocessing
import os
import time
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import wave

from book_speech import read_clip

ROOT = Path(__file__).resolve().parents[1]
RATE = 22050
STAGE = Path('work/qwen-narration')
METHOD = 'Verified word, literal letter names, word; PCM assembly'
LANGUAGES = {'en', 'de', 'es'}
SHA = re.compile(r'^[0-9a-f]{64}$')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def _json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.new')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def _inside(root, relative):
    """Refuse traversal and symlinks, including links within the repository."""
    name = PurePosixPath(relative)
    if name.is_absolute() or '..' in name.parts or '\\' in str(relative) or str(name) != str(relative):
        raise ValueError(f'unsafe path: {relative}')
    path = root
    for part in name.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f'symlink in narration path: {path}')
    path.resolve().relative_to(root)
    return path


def _asset(root, name):
    path = _inside(root, name)
    if not name.startswith('assets/') or not name.endswith('.wav') or 'speech-profiles' in PurePosixPath(name).parts:
        raise ValueError(f'not a canonical narration asset: {name}')
    return path


def _ignored(root, relative):
    path = _inside(root, relative.as_posix())
    result = subprocess.run(['git', '-C', str(root), 'check-ignore', '-q', str(path / 'probe')],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode:
        raise ValueError(f'narration scratch must be ignored by git: {path}')
    return path


def _receipts(root):
    return sorted(p for p in (root / 'assets').rglob('*.speech.json')
                  if 'speech-profiles' not in p.relative_to(root).parts)


def identify_language(name, receipt):
    """Prefer an explicit supported receipt language; cross-check path markers."""
    aliases = {'english': 'en', 'german': 'de', 'spanish': 'es'}
    raw = receipt.get('language')
    explicit = aliases.get(str(raw).lower(), str(raw).lower().replace('_', '-').split('-')[0]) if raw else None
    markers = set(PurePosixPath(name).parts) & LANGUAGES
    suffix = re.search(r'-(en|de|es)\.wav$', name)
    if suffix:
        markers.add(suffix[1])
    if len(markers) > 1 or (explicit and (explicit not in LANGUAGES or markers - {explicit})):
        raise ValueError(f'conflicting or unsupported language: {name}: {raw}')
    language = explicit or next(iter(markers), None)
    if not language and PurePosixPath(name).parent == PurePosixPath('assets/jungle-book/sounds'):
        language = 'en'
    if not language:
        raise ValueError(f'cannot identify language: {name}')
    return language


def _recipe(text, sources):
    """Keep ordered dependency files, repeated letters, trims and integer gaps."""
    word = text.split('. ')[0].lower()
    if not sources or len(sources) != 1 + sum(not letter.isspace() for letter in word):
        raise ValueError(f'assembly source count does not match receipt text: {text!r}')
    parts = [{'source': sources[0]}, {'silence_frames': RATE // 2}]
    letters = iter(sources[1:])
    for letter in word:
        if letter.isspace():
            parts.append({'silence_frames': RATE // 3})
        else:
            parts.extend(({'source': next(letters)}, {'silence_frames': RATE // 4}))
    parts.extend(({'silence_frames': RATE // 4}, {'source': sources[0]}))
    return {'method': METHOD, 'trim': 'book_speech.read_clip', 'parts': parts}


def capture_corpus(root=ROOT, *, expected_counts=None):
    """Return every canonical path with exact text, language and original hashes.

    Does not write a snapshot or audio. expected_counts may pin the migration to
    {'en': 985, 'de': 1007, 'es': 1005}; fixtures can use smaller inventories.
    """
    root = Path(root).resolve()
    corpus = {}
    for receipt_path in _receipts(root):
        name = receipt_path.relative_to(root).as_posix().removesuffix('.speech.json') + '.wav'
        path = _asset(root, name)
        receipt = _json(receipt_path)
        text = receipt.get('text')
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f'empty narration text: {receipt_path}')
        audio_hash = digest(path)
        if receipt.get('sha256') != audio_hash:
            raise ValueError(f'original audio hash mismatch: {path}')
        entry = {'text': text, 'language': identify_language(name, receipt),
                 'input_identity': {'audio_sha256': audio_hash, 'receipt_sha256': digest(receipt_path)}}
        if 'sources' in receipt or 'PCM assembly' in receipt.get('method', ''):
            if receipt.get('method') != METHOD:
                raise ValueError(f'unsupported assembly method: {receipt_path}')
            entry['sources'] = [source['path'] for source in receipt['sources']]
            entry['recipe'] = _recipe(text, entry['sources'])
        corpus[name] = entry
    _order(root, corpus)
    counts = {lang: sum(e['language'] == lang for e in corpus.values()) for lang in LANGUAGES}
    if expected_counts is not None and counts != expected_counts:
        raise ValueError(f'incomplete corpus: expected {expected_counts}, got {counts}')
    return corpus


def _order(root, corpus):
    if not isinstance(corpus, dict) or not corpus:
        raise ValueError('complete nonempty corpus required')
    for name, entry in corpus.items():
        _asset(root, name)
        if not isinstance(entry.get('text'), str) or not entry['text'].strip() or entry.get('language') not in LANGUAGES:
            raise ValueError(f'invalid corpus entry: {name}')
        if identify_language(name, entry) != entry['language']:
            raise ValueError(f'language mismatch: {name}')
        if set(entry.get('input_identity', {})) != {'audio_sha256', 'receipt_sha256'} or not all(
                isinstance(h, str) and SHA.fullmatch(h) for h in entry['input_identity'].values()):
            raise ValueError(f'missing input identity: {name}')
        if 'sources' in entry:
            if entry.get('recipe') != _recipe(entry['text'], entry['sources']):
                raise ValueError(f'assembly recipe mismatch: {name}')
            for source in entry['sources']:
                if source not in corpus:
                    raise ValueError(f'missing assembly dependency: {source} for {name}')
                if corpus[source]['language'] != entry['language']:
                    raise ValueError(f'assembly language mismatch: {name}: {source}')
    ordered, active, done = [], set(), set()

    def visit(name):
        if name in active:
            raise ValueError(f'assembly dependency cycle: {name}')
        if name in done:
            return
        active.add(name)
        for source in corpus[name].get('sources', []):
            visit(source)
        active.remove(name)
        done.add(name)
        ordered.append(name)

    for name in sorted(corpus):
        visit(name)
    return ordered


def _harness(harness):
    """The caller supplies the actual model/pack identity, never a provider URL."""
    if not isinstance(harness, dict) or not harness.get('model') or not harness.get('pack'):
        raise ValueError('harness requires nonempty model and exact pack identity')
    if harness.get('provider', 'local_speech') != 'local_speech':
        raise ValueError('only the shared local_speech engine is supported')
    if harness.get('voice', 'Serena') != 'Serena' or harness.get('speed', 1.0) != 1.0:
        raise ValueError('Jungle narration uses Serena at natural rate 1.0')
    identity = dict(provider='local_speech', model=harness['model'], pack=harness['pack'], voice='Serena', speed=1.0)
    # Freeze mutable caller dictionaries and reject non-JSON identities.
    return json.loads(json.dumps(identity, allow_nan=False))


def _request(entry, identity):
    return _identity(dict(language=entry['language'], text=entry['text'],
                          pack={k: identity[k] for k in ('provider', 'model', 'pack')}, voice=identity['voice']))


def _metadata(entry, identity, output_root):
    metadata = dict(identity, text=entry['text'], language=entry['language'],
                    input_identity=entry['input_identity'], request_sha256=_request(entry, identity))
    if 'sources' in entry:
        metadata.update(method=METHOD, recipe=entry['recipe'],
                        sources=[{'path': name, 'sha256': digest(_asset(output_root, name))}
                                 for name in entry['sources']])
    return metadata


def _audio(path, text):
    """Bounded, streaming PCM verification, including duration and audibility."""
    with wave.open(str(path), 'rb') as clip:
        if clip.getparams()[:3] != (1, 2, RATE) or clip.getcomptype() != 'NONE':
            raise ValueError(f'expected mono PCM16 at {RATE} Hz: {path}')
        frames = clip.getnframes()
        duration = frames / RATE
        characters = sum(not char.isspace() for char in text)
        if not max(.08, characters / 150) <= duration <= min(60, max(5, characters * .8 + 2)):
            raise ValueError(f'unreasonable narration duration: {path}: {duration:g}s')
        count = audible = clipped = 0
        while data := clip.readframes(16384):
            samples = array('h', data)
            if sys.byteorder != 'little':
                samples.byteswap()
            count += len(samples)
            audible += sum(abs(value) > 180 for value in samples)
            clipped += sum(abs(value) >= 32767 for value in samples)
        if count != frames or audible < min(220, max(1, frames // 1000)):
            raise ValueError(f'truncated or silent narration: {path}')
        if clipped:
            raise ValueError(f'clipped narration: {path}: {clipped} samples')
    return duration


def _verified(path, expected):
    receipt = _json(path.with_suffix('.speech.json'))
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ValueError(f'stale narration receipt: {path}')
    if receipt.get('sha256') != digest(path):
        raise ValueError(f'narration hash mismatch: {path}')
    duration = _audio(path, expected['text'])
    recorded = receipt.get('duration')
    if not isinstance(recorded, (float, int)) or not math.isfinite(recorded) or abs(recorded - duration) >= 1 / RATE:
        raise ValueError(f'narration duration mismatch: {path}')
    return receipt


def _reusable(path, expected):
    try:
        _verified(path, expected)
        return True
    except (ValueError, OSError, EOFError, wave.Error, KeyError, TypeError):
        return False


def _copy(source, target):
    """Stream copies and atomically replace each destination file."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.new')
    with source.open('rb') as incoming, temporary.open('wb') as outgoing:
        shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
    temporary.replace(target)


def _save_receipt(path, metadata):
    duration = _audio(path, metadata['text'])
    _write_json(path.with_suffix('.speech.json'), dict(metadata, sha256=digest(path), duration=duration))


def _assemble(output_root, entry):
    pieces = []
    for part in entry['recipe']['parts']:
        pieces.append(read_clip(_asset(output_root, part['source']))[0] if 'source' in part
                      else bytes(part['silence_frames'] * 2))
    return b''.join(pieces)


class Paused(RuntimeError):
    """A requested checkpoint stop; completed clips remain resumable."""


@contextmanager
def _claim(path, *, blocking=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f'symlink in claim path: {path}')
    with path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            raise RuntimeError('another narration coordinator owns this stage') from None
        yield


def _pause(work):
    if (work / 'pause.request').exists():
        raise Paused('narration paused at a validated clip checkpoint; use stage --resume')


def _cache_clip(cache, name, entry, identity, engine):
    """One lock per immutable synthesis request, covering WAV AND receipt."""
    shared = {k: v for k, v in _metadata(entry, identity, None).items()
              if k != 'input_identity'}
    cached = cache / (shared['request_sha256'] + '.wav')
    with _claim(cache / (shared['request_sha256'] + '.lock')):
        _pause(cache.parent)
        action = 'cache'
        if not _reusable(cached, shared):
            action = 'clip'
            with tempfile.TemporaryDirectory(dir=cache, prefix='synthesis-') as directory:
                raw, converted = Path(directory) / 'engine.wav', Path(directory) / 'pcm.wav'
                engine.write(entry['text'], identity['voice'], entry['language'], raw)
                if not raw.is_file() or raw.stat().st_size > 256 * 1024 * 1024:
                    raise ValueError(f'missing or oversized engine output: {name}')
                subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-threads', '1',
                                '-i', str(raw), '-t', '61', '-map_metadata', '-1', '-ac', '1', '-ar', str(RATE),
                                '-c:a', 'pcm_s16le', str(converted)], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=180)
                _audio(converted, entry['text'])
                _copy(converted, cached)
                _save_receipt(cached, shared)
        return action


_WORKER_ENGINE = None


def _provider_engine(provider, pack):
    provider = Path(provider)
    sys.path.insert(0, str(provider.parent))
    spec = importlib.util.spec_from_file_location('jungle_local_speech_provider', provider)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.Engine(pack)


def _worker_init(provider, pack, cache):
    global _WORKER_ENGINE
    # Spawn gives each process a separate Torch RNG and model; never fork a
    # running Torch thread pool or share its mutable generation override.
    # Serialize loading peaks; both persistent engines then synthesize in parallel.
    with _claim(Path(cache) / 'model-load.lock'):
        _WORKER_ENGINE = _provider_engine(provider, pack)
    _worker_stats(Path(cache))


def _resources():
    stats = {'pid': os.getpid(), 'at': time.time()}
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith(('VmRSS:', 'VmHWM:', 'VmSwap:', 'Threads:')):
            key, value = line.split(':', 1)
            stats[key] = value.strip()
    group = Path('/proc/self/cgroup').read_text().strip().split('::', 1)[1]
    directory = Path('/sys/fs/cgroup') / group.lstrip('/')
    stats['cgroup'] = group
    stats['limits'] = {}
    for key in ('memory.max', 'memory.current', 'memory.high', 'memory.events',
                'memory.swap.current', 'memory.swap.max', 'cpu.max'):
        try:
            stats['limits'][key] = (directory / key).read_text().strip()
        except OSError:
            pass
    return stats


def _worker_stats(cache):
    _write_json(cache.parent / 'workers' / (str(os.getpid()) + '.json'), _resources())


def _worker_clip(cache, name, entry, identity):
    action = _cache_clip(Path(cache), name, entry, identity, _WORKER_ENGINE)
    _worker_stats(Path(cache))
    print(f'local synthesis {action}: {name}', file=sys.stderr, flush=True)
    return action


def synthesis_requests(corpus, identity):
    """Stable disjoint claims: identical text/language/voice has ONE owner."""
    requests = {}
    for name in sorted(corpus):
        entry = corpus[name]
        if 'sources' not in entry:
            requests.setdefault(_request(entry, identity), (name, entry))
    return requests


def _pending_requests(cache, corpus, identity):
    return {key: pair for key, pair in synthesis_requests(corpus, identity).items()
            if not _reusable(cache / (key + '.wav'),
                             {k: v for k, v in _metadata(pair[1], identity, None).items()
                              if k != 'input_identity'})}


def generate(root, harness, engine=None, *, corpus=None, workers=1,
             worker_config=None, resume=False):
    """Resume full staged coverage with bounded independent CPU processes.

    Only the coordinator writes staged targets and dependency assemblies. Workers
    own disjoint synthesis requests and atomically save the same cache receipts
    as sequential generation. Each process reuses its own model and seeded RNG.
    """
    if not isinstance(workers, int) or isinstance(workers, bool) or not 1 <= workers <= 3:
        raise ValueError('workers must be between 1 and 3')
    if workers > 1 and (engine is not None or not worker_config):
        raise ValueError('parallel generation requires a provider configuration, not a shared engine')
    root = Path(root).resolve()
    identity = _harness(harness)
    current = capture_corpus(root)
    if corpus is not None and current != corpus:
        raise ValueError('corpus changed since capture; recapture before generation')
    corpus = current
    ordered = _order(root, corpus)
    work = _ignored(root, STAGE)
    with _claim(work / 'coordinator.lock', blocking=False):
        if resume:
            (work / 'pause.request').unlink(missing_ok=True)
        _pause(work)
        return _generate_locked(root, identity, engine, corpus, ordered, work,
                                workers, worker_config)


def _generate_locked(root, identity, engine, corpus, ordered, work, workers, worker_config):
    output_root = _inside(root, (STAGE / 'staged').as_posix())
    cache = _inside(root, (STAGE / 'cache').as_posix())
    cache.mkdir(parents=True, exist_ok=True)
    _write_json(work / 'corpus.json', corpus)
    _write_json(work / 'inventory.json', {'format': 'jungle-local-narration-1',
                                        'corpus_sha256': _identity(corpus), 'identity': identity})
    if workers == 1 and engine is None:
        engine = _provider_engine(*worker_config)
    _write_json(work / 'coordinator-resources.json', _resources())
    pool, futures = None, {}
    if workers > 1:
        pool = ProcessPoolExecutor(max_workers=workers,
                                   mp_context=multiprocessing.get_context('spawn'),
                                   initializer=_worker_init, initargs=(*worker_config, str(cache)))
        for key, (name, entry) in _pending_requests(cache, corpus, identity).items():
            futures[key] = pool.submit(_worker_clip, str(cache), name, entry, identity)
    try:
        for index, name in enumerate(ordered, 1):
            _pause(work)
            entry = corpus[name]
            target = _asset(output_root, name)
            metadata = _metadata(entry, identity, output_root)
            if _reusable(target, metadata):
                print(f'local narration {index}/{len(ordered)} staged: {name}', file=sys.stderr, flush=True)
                continue
            if 'sources' in entry:
                action = 'assembly'
                data = _assemble(output_root, entry)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + '.new')
                with wave.open(str(temporary), 'wb') as clip:
                    clip.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
                    clip.writeframes(data)
                _audio(temporary, entry['text'])
                temporary.replace(target)
            else:
                key = metadata['request_sha256']
                if key in futures:
                    action = futures.pop(key).result()
                else:
                    action = _cache_clip(cache, name, entry, identity, engine)
                _copy(cache / (key + '.wav'), target)
            _save_receipt(target, metadata)
            print(f'local narration {index}/{len(ordered)} {action}: {name}', file=sys.stderr, flush=True)
        validate(root, corpus)
        return corpus
    except BaseException as error:
        if pool:
            _write_json(work / 'parallel-failure.json', {
                'error': repr(error), 'resources': _resources(),
                'workers': [{'pid': p.pid, 'exitcode': p.exitcode}
                            for p in pool._processes.values()]})
        raise
    finally:
        if pool:
            pool.shutdown(wait=True, cancel_futures=True)


def validate(root, corpus):
    """Validate complete staged coverage, identity, PCM, hashes and assemblies."""
    root = Path(root).resolve()
    ordered = _order(root, corpus)
    canonical = {p.relative_to(root).as_posix().removesuffix('.speech.json') + '.wav' for p in _receipts(root)}
    if canonical != set(corpus):
        raise ValueError('corpus does not cover the entire canonical inventory')
    work = _inside(root, STAGE.as_posix())
    inventory = _json(work / 'inventory.json')
    if inventory.get('format') != 'jungle-local-narration-1' or inventory.get('corpus_sha256') != _identity(corpus):
        raise ValueError('staged inventory does not match corpus')
    identity = _harness(inventory['identity'])
    if _json(work / 'corpus.json') != corpus:
        raise ValueError('staged corpus snapshot mismatch')
    output_root = _inside(root, (STAGE / 'staged').as_posix())
    staged = {p.relative_to(output_root).as_posix() for p in output_root.rglob('*.wav')}
    receipts = {p.relative_to(output_root).as_posix().removesuffix('.speech.json') + '.wav'
                for p in output_root.rglob('*.speech.json')}
    if staged != set(corpus) or receipts != set(corpus):
        raise ValueError('incomplete or extra staged narration inventory')
    total = 0
    for name in ordered:
        path = _asset(output_root, name)
        metadata = _metadata(corpus[name], identity, output_root)
        _verified(path, metadata)
        if 'sources' in corpus[name]:
            expected = _assemble(output_root, corpus[name])
            with wave.open(str(path)) as clip:
                if clip.readframes(clip.getnframes()) != expected:
                    raise ValueError(f'assembly PCM does not match exact recipe: {name}')
        total += path.stat().st_size
    return {'paths': len(corpus), 'audio_bytes': total, 'identity': identity}


def promote(root, corpus, *, languages=None):
    """Explicit promotion only after full validation; resumable per-file copies.

    A stable backup directory records the original audio AND receipts. All
    backups finish before the first replacement. Interrupted WAV/receipt pairs
    can resume only when each file is still original or matches this stage.
    """
    root = Path(root).resolve()
    selected = LANGUAGES if languages is None else set(languages)
    if not selected or not selected <= LANGUAGES:
        raise ValueError('promotion requires supported languages')
    validate(root, corpus)
    inventory = _json(_inside(root, (STAGE / 'inventory.json').as_posix()))
    output_root = _inside(root, (STAGE / 'staged').as_posix())
    backup = _ignored(root, Path('backup/qwen-narration') / _identity(inventory))
    files = []
    for name, entry in sorted(corpus.items()):
        if entry['language'] not in selected:
            continue
        original = _asset(root, name)
        staged = _asset(output_root, name)
        saved = _asset(backup, name)
        for target, source, prior, original_hash in (
                (original, staged, saved, entry['input_identity']['audio_sha256']),
                (original.with_suffix('.speech.json'), staged.with_suffix('.speech.json'),
                 saved.with_suffix('.speech.json'), entry['input_identity']['receipt_sha256'])):
            current_hash = digest(target)
            staged_hash = digest(source)
            if prior.exists() and digest(prior) != original_hash:
                raise ValueError(f'backup hash mismatch: {prior}')
            if current_hash != original_hash and not (prior.exists() and current_hash == staged_hash):
                raise ValueError(f'original changed since capture: {target}')
            files.append((target, source, prior, original_hash, staged_hash))
    for target, source, prior, original_hash, staged_hash in files:
        if not prior.exists():
            _copy(target, prior)
        if digest(prior) != original_hash:
            raise ValueError(f'backup verification failed: {prior}')
    journal = backup / 'promotion.json'
    _write_json(journal, {'inventory': inventory, 'languages': sorted(selected), 'status': 'promoting'})
    for target, source, prior, original_hash, staged_hash in files:
        if digest(target) not in (original_hash, staged_hash):
            raise ValueError(f'asset changed during promotion: {target}')
        if digest(target) != staged_hash:
            _copy(source, target)
        if digest(target) != staged_hash:
            raise ValueError(f'promoted asset hash mismatch: {target}')
    _write_json(journal, {'inventory': inventory, 'languages': sorted(selected), 'status': 'complete'})
    return backup


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['corpus', 'validate', 'stage', 'pause'])
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--harness-root', type=Path, help='directory containing the standalone provider module')
    parser.add_argument('--provider-module', default='local_speech_qwen.py', help='safe Python filename under --harness-root')
    parser.add_argument('--pack', type=Path, help='JSON object passed to Engine, e.g. provider qwen3-tts and model checkpoint path')
    parser.add_argument('--identity', type=Path, help='JSON with model and exact immutable pack identity')
    parser.add_argument('--workers', type=int, default=1, choices=range(1, 4))
    parser.add_argument('--resume', action='store_true', help='clear a cooperative pause after obtaining the stage lock')
    args = parser.parse_args()
    if args.command == 'corpus':
        corpus = capture_corpus(args.root)
        print(json.dumps({'paths': len(corpus), 'languages': {
            lang: sum(e['language'] == lang for e in corpus.values()) for lang in sorted(LANGUAGES)}}))
    elif args.command == 'pause':
        work = _ignored(args.root.resolve(), STAGE)
        _write_json(work / 'pause.request', {'requested_at': time.time()})
        print(json.dumps({'pause_requested': True, 'note': 'requires a coordinator with pause support'}))
    elif args.command == 'validate':
        print(json.dumps(validate(args.root, _json(args.root / STAGE / 'corpus.json'))))
    else:
        if not all((args.harness_root, args.pack, args.identity)):
            parser.error('stage requires --harness-root, --pack and --identity')
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*\.py', args.provider_module):
            parser.error('--provider-module must be a safe Python basename')
        identity = _harness(_json(args.identity))
        pack = _json(args.pack)
        if not isinstance(pack, dict) or not pack:
            parser.error('--pack must contain a nonempty JSON object')
        corpus = capture_corpus(args.root)
        provider = args.harness_root.resolve() / args.provider_module
        if not provider.is_file():
            parser.error(f'standalone local provider not found: {provider}')
        engine = None
        try:
            generate(args.root, identity, engine, corpus=corpus, workers=args.workers,
                     worker_config=(str(provider), pack), resume=args.resume)
        except Paused as error:
            print(str(error), file=sys.stderr)
            return 75
        print(json.dumps(validate(args.root, corpus)))


if __name__ == '__main__':
    sys.exit(main())

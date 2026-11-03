"""Offline orchestration tests. Every engine and asset is a disposable fixture."""
from array import array
from contextlib import redirect_stderr
import io
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import local_narration as narration
from book_speech import read_clip

IDENTITY = {'model': 'Qwen3-TTS-fixture', 'pack': {'sha256': 'fixture-pack-1'}}


def write_wave(path, *, rate=22050, channels=1, silent=False, seconds=.4):
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = array('h')
    for index in range(int(rate * seconds)):
        value = 0 if silent or index < rate // 12 or index > rate * (seconds - .12) else int(
            6000 * math.sin(index * 2 * math.pi * 330 / rate))
        samples.extend([value] * channels)
    if sys.byteorder != 'little':
        samples.byteswap()
    with wave.open(str(path), 'wb') as clip:
        clip.setparams((channels, 2, rate, 0, 'NONE', 'not compressed'))
        clip.writeframes(samples.tobytes())


class Engine:
    def __init__(self):
        self.calls = []
        self.fail_at = None
        self.silent = False
        self.seconds = .4

    def write(self, text, voice, language, output):
        self.calls.append((text, voice, language))
        if self.fail_at == len(self.calls):
            raise RuntimeError('fixture interruption')
        # Force real ffmpeg channel/rate conversion instead of mocking it.
        write_wave(output, rate=24000, channels=2, silent=self.silent, seconds=self.seconds)


class NarrationFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('ffmpeg'):
            raise RuntimeError('offline narration tests require ffmpeg')
        ignored = subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '-q', 'work/local-narration-test/probe'])
        if ignored.returncode:
            raise RuntimeError('fixture work directory must be ignored')
        (ROOT / 'work').mkdir(exist_ok=True)

    def setUp(self):
        self.progress = io.StringIO()
        self.enterContext(redirect_stderr(self.progress))
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / 'work', prefix='local-narration-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.engine = Engine()
        self.word = 'assets/jungle-book/sounds/en/simple/word.wav'
        self.a = 'assets/jungle-book/sounds/en/letters/a.wav'
        self.b = 'assets/jungle-book/sounds/en/letters/b.wav'
        self.assembly = 'assets/jungle-book/sounds/word.wav'
        self.add(self.word, 'A b')
        self.add(self.a, 'A')
        self.add(self.b, 'B')
        self.add(self.assembly, 'A b. A. B. A b.', sources=[self.word, self.a, self.b])
        self.add('assets/jungle-book/sounds/en/simple/duplicate.wav', 'A b')
        self.add('assets/jungle-book/sounds/de/simple/word.wav', 'A b')
        self.add('assets/abc/sounds/word-es.wav', 'A b')
        # A malformed profile is deliberately outside the canonical inventory.
        profile = self.root / 'assets/speech-profiles/slow/en/ignored.speech.json'
        profile.parent.mkdir(parents=True)
        profile.write_text('{}')

    def add(self, name, text, *, sources=None, language=None):
        path = self.root / name
        write_wave(path)
        receipt = {'text': text, 'sha256': narration.digest(path)}
        if language:
            receipt['language'] = language
        if sources is not None:
            receipt.update(method=narration.METHOD, sources=[{'path': source, 'sha256': narration.digest(self.root / source)}
                                                           for source in sources])
        narration._write_json(path.with_suffix('.speech.json'), receipt)

    def update_receipt(self, name, **changes):
        path = (self.root / name).with_suffix('.speech.json')
        value = json.loads(path.read_text())
        value.update(changes)
        narration._write_json(path, value)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): narration.digest(p)
                for p in (self.root / 'assets').rglob('*') if p.is_file()}

    def stage(self):
        return narration.generate(self.root, IDENTITY, self.engine)

    def staged(self, name):
        return self.root / narration.STAGE / 'staged' / name


class LocalNarrationTest(NarrationFixture):
    def test_language_identification_and_complete_capture(self):
        self.add('assets/other/explicit.wav', 'Hola', language='Spanish')
        corpus = narration.capture_corpus(self.root, expected_counts={'en': 5, 'de': 1, 'es': 2})
        self.assertEqual(len(corpus), 8)
        self.assertEqual(corpus[self.assembly]['language'], 'en')
        self.assertEqual(corpus['assets/other/explicit.wav']['language'], 'es')
        self.assertEqual(corpus[self.assembly]['text'], 'A b. A. B. A b.')
        self.assertEqual(corpus[self.assembly]['sources'], [self.word, self.a, self.b])
        self.assertFalse((self.root / narration.STAGE).exists())
        with self.assertRaisesRegex(ValueError, 'incomplete corpus'):
            narration.capture_corpus(self.root, expected_counts={'en': 985, 'de': 1007, 'es': 1005})
        self.update_receipt(self.word, language='de')
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            narration.capture_corpus(self.root)

    def test_stage_dedup_conversion_exact_assembly_and_no_asset_writes(self):
        before = self.snapshot()
        corpus = self.stage()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(len(self.engine.calls), 5)  # duplicate English text shares; de/es do not
        self.assertEqual({call[1] for call in self.engine.calls}, {'Serena'})
        self.assertEqual({call[2] for call in self.engine.calls}, {'en', 'de', 'es'})
        self.assertEqual(sum(call[0] == 'A b' for call in self.engine.calls), 3)
        word, _ = read_clip(self.staged(self.word))
        a, _ = read_clip(self.staged(self.a))
        b, _ = read_clip(self.staged(self.b))
        expected = b''.join([word, bytes(11025 * 2), a, bytes(5512 * 2), bytes(7350 * 2),
                             b, bytes(5512 * 2), bytes(5512 * 2), word])
        with wave.open(str(self.staged(self.assembly))) as clip:
            self.assertEqual(clip.getparams()[:3], (1, 2, 22050))
            self.assertEqual(clip.readframes(clip.getnframes()), expected)
        receipt = json.loads(self.staged(self.assembly).with_suffix('.speech.json').read_text())
        self.assertEqual(receipt['text'], corpus[self.assembly]['text'])
        self.assertEqual(receipt['recipe'], corpus[self.assembly]['recipe'])
        self.assertEqual([s['path'] for s in receipt['sources']], [self.word, self.a, self.b])
        self.assertEqual(receipt['provider'], 'local_speech')
        self.assertEqual(receipt['model'], IDENTITY['model'])
        self.assertEqual(receipt['speed'], 1.0)
        self.assertEqual(receipt['input_identity'], corpus[self.assembly]['input_identity'])
        self.assertEqual(narration.validate(self.root, corpus)['paths'], 7)
        progress = self.progress.getvalue().splitlines()
        self.assertEqual(len(progress), len(corpus))
        for index, line in enumerate(progress, 1):
            self.assertTrue(line.startswith(f'local narration {index}/7 '), line)
            self.assertIn(line.split(': ', 1)[1], corpus)
        self.assertEqual(sum(' clip: ' in line for line in progress), 5)
        self.assertEqual(sum(' cache: ' in line for line in progress), 1)
        self.assertEqual(sum(' assembly: ' in line for line in progress), 1)

    def test_resume_is_noop_and_recovers_interrupted_engine(self):
        self.engine.fail_at = 3
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, 'interruption'):
            self.stage()
        self.assertEqual(self.snapshot(), before)
        self.engine.fail_at = None
        corpus = self.stage()
        self.assertEqual(len(self.engine.calls), 6)  # failed third call is retried
        stamps = {p: p.stat().st_mtime_ns for p in (self.root / narration.STAGE / 'staged').rglob('*') if p.is_file()}
        with patch('builtins.print') as progress:
            self.stage()
        self.assertEqual(progress.call_count, 7)
        for index, call in enumerate(progress.call_args_list, 1):
            self.assertTrue(call.args[0].startswith(f'local narration {index}/7 staged: '))
            self.assertTrue(call.kwargs['flush'])
            self.assertIs(call.kwargs['file'], sys.stderr)
        self.assertEqual(len(self.engine.calls), 6)
        self.assertTrue(all(p.stat().st_mtime_ns == stamp for p, stamp in stamps.items()))
        narration.validate(self.root, corpus)

    def test_resume_invalidates_text_pack_and_original_receipt_identity(self):
        corpus = self.stage()
        self.update_receipt(self.b, text='Bee')
        with self.assertRaisesRegex(ValueError, 'changed since capture'):
            narration.generate(self.root, IDENTITY, self.engine, corpus=corpus)
        changed = self.stage()
        self.assertEqual(len(self.engine.calls), 6)
        self.assertNotEqual(changed[self.b]['input_identity'], corpus[self.b]['input_identity'])
        self.assertEqual(self.engine.calls[-1][0], 'Bee')
        # A receipt-only edit changes path provenance but reuses the same synthesis.
        self.update_receipt(self.b, note='original receipt updated')
        changed = self.stage()
        self.assertEqual(len(self.engine.calls), 6)
        receipt = json.loads(self.staged(self.b).with_suffix('.speech.json').read_text())
        self.assertEqual(receipt['input_identity'], changed[self.b]['input_identity'])
        alternate = dict(IDENTITY, pack={'sha256': 'fixture-pack-2'})
        narration.generate(self.root, alternate, self.engine)
        self.assertEqual(len(self.engine.calls), 11)
        old_key = narration._request(changed[self.b], narration._harness(IDENTITY))
        self.assertNotEqual(old_key, narration._request(changed[self.b], narration._harness(alternate)))
        self.assertNotEqual(old_key, narration._request(changed[self.b], dict(narration._harness(IDENTITY), voice='Ryan')))

    def test_corrupt_stage_and_cache_regenerated_and_assemblies_rebuilt(self):
        self.stage()
        target = self.staged(self.b)
        receipt = json.loads(target.with_suffix('.speech.json').read_text())
        cached = self.root / narration.STAGE / 'cache' / (receipt['request_sha256'] + '.wav')
        target.write_bytes(b'broken')
        cached.write_bytes(b'broken')
        corpus = self.stage()
        self.assertEqual(len(self.engine.calls), 6)
        narration.validate(self.root, corpus)
        # A changed source with valid self-consistent PCM/receipt still cannot
        # make an old assembly valid; validation reconstructs its exact bytes.
        write_wave(target, seconds=.5)
        narration._save_receipt(target, {k: v for k, v in receipt.items() if k not in ('sha256', 'duration')})
        with self.assertRaisesRegex(ValueError, 'stale narration receipt'):
            narration.validate(self.root, corpus)
        self.stage()
        self.assertEqual(len(self.engine.calls), 6)

    def test_cycles_and_missing_dependencies_fail_before_engine_writes(self):
        for source, message in [(self.assembly, 'cycle'), ('assets/en/missing.wav', 'missing assembly dependency')]:
            with self.subTest(source=source):
                self.update_receipt(self.assembly, sources=[{'path': s} for s in [source, self.a, self.b]])
                with self.assertRaisesRegex(ValueError, message):
                    self.stage()
                self.assertFalse(self.engine.calls)
                self.assertFalse((self.root / narration.STAGE).exists())

    def test_empty_text_unknown_language_empty_inventory_and_source_hash_fail(self):
        self.update_receipt(self.b, text=' ')
        with self.assertRaisesRegex(ValueError, 'empty narration text'):
            self.stage()
        self.update_receipt(self.b, text='B')
        self.add('assets/unknown/word.wav', 'Hello')
        with self.assertRaisesRegex(ValueError, 'cannot identify language'):
            self.stage()
        self.update_receipt('assets/unknown/word.wav', language='en')
        (self.root / self.b).write_bytes(b'corrupt original')
        with self.assertRaisesRegex(ValueError, 'original audio hash mismatch'):
            self.stage()
        with self.assertRaisesRegex(ValueError, 'nonempty corpus'):
            narration._order(self.root, {})
        self.assertFalse(self.engine.calls)

    def test_silent_and_long_output_rejected_without_asset_changes(self):
        original = self.snapshot()
        self.engine.silent = True
        with self.assertRaisesRegex(ValueError, 'silent narration'):
            self.stage()
        self.engine.silent = False
        self.engine.seconds = 6
        with self.assertRaisesRegex(ValueError, 'unreasonable narration duration'):
            self.stage()
        self.assertEqual(self.snapshot(), original)

    def test_validation_failure_prevents_all_promotion_writes(self):
        corpus = self.stage()
        original = self.snapshot()
        self.staged(self.b).write_bytes(b'invalid')
        with self.assertRaises(ValueError):
            narration.promote(self.root, corpus)
        self.assertEqual(self.snapshot(), original)
        self.assertFalse((self.root / 'backup').exists())

    def test_clipped_pcm_is_rejected(self):
        path = self.root / 'clipped.wav'
        with wave.open(str(path), 'wb') as clip:
            clip.setparams((1, 2, narration.RATE, 0, 'NONE', 'not compressed'))
            clip.writeframes(b'\xff\x7f' * 8820)
        with self.assertRaisesRegex(ValueError, 'clipped narration'):
            narration._audio(path, 'Hello')

    def test_language_promotion_preserves_english_profiles(self):
        corpus = self.stage()
        before = self.snapshot()
        narration.promote(self.root, corpus, languages={'de', 'es'})
        after = self.snapshot()
        for name in before:
            canonical = name.removesuffix('.speech.json') + '.wav' if name.endswith('.speech.json') else name
            if canonical not in corpus or corpus[canonical]['language'] == 'en':
                self.assertEqual(after[name], before[name], name)
            else:
                self.assertEqual(after[name], narration.digest(self.root / narration.STAGE / 'staged' / name))

    def test_complete_backups_precede_replacement_and_interruption_resumes(self):
        original = self.snapshot()
        corpus = self.stage()
        real_copy = narration._copy
        writes = []

        def interrupt(source, target):
            if target.is_relative_to(self.root / 'assets'):
                backups = list((self.root / 'backup').rglob('*.speech.json'))
                self.assertEqual(len(backups), 7)
                writes.append(target)
                if len(writes) == 2:  # stop between a WAV and its receipt
                    raise RuntimeError('fixture promotion interrupted')
            real_copy(source, target)

        with patch.object(narration, '_copy', side_effect=interrupt):
            with self.assertRaisesRegex(RuntimeError, 'promotion interrupted'):
                narration.promote(self.root, corpus)
        backup = narration.promote(self.root, corpus)
        for name, original_hash in original.items():
            if 'speech-profiles' not in name:
                self.assertEqual(narration.digest(backup / name), original_hash)
                self.assertEqual(narration.digest(self.root / name), narration.digest(
                    self.root / narration.STAGE / 'staged' / name))
        self.assertEqual(json.loads((backup / 'promotion.json').read_text())['status'], 'complete')
        self.assertEqual(narration.promote(self.root, corpus), backup)
        narration.validate(self.root, corpus)

    def test_changed_original_refuses_promotion_before_backups(self):
        corpus = self.stage()
        self.update_receipt(self.b, text='Owner changed this')
        original = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'original changed since capture'):
            narration.promote(self.root, corpus)
        self.assertEqual(self.snapshot(), original)
        self.assertFalse((self.root / 'backup').exists())

    def test_missing_extra_inventory_tampered_receipts_and_recipe_rejected(self):
        corpus = self.stage()
        with self.assertRaisesRegex(ValueError, 'entire canonical inventory'):
            narration.validate(self.root, {k: v for k, v in corpus.items() if k != self.assembly})
        extra = self.staged('assets/en/extra.wav')
        write_wave(extra)
        with self.assertRaisesRegex(ValueError, 'extra staged'):
            narration.validate(self.root, corpus)
        extra.unlink()
        path = self.staged(self.assembly).with_suffix('.speech.json')
        receipt = json.loads(path.read_text())
        receipt['voice'] = 'Ryan'
        narration._write_json(path, receipt)
        with self.assertRaisesRegex(ValueError, 'stale narration receipt'):
            narration.validate(self.root, corpus)
        self.stage()
        receipt = json.loads(path.read_text())
        receipt['recipe']['parts'][1]['silence_frames'] += 1
        narration._write_json(path, receipt)
        with self.assertRaisesRegex(ValueError, 'stale narration receipt'):
            narration.validate(self.root, corpus)

    def test_unsafe_paths_and_unsupported_engine_settings_fail_without_generation(self):
        with self.assertRaisesRegex(ValueError, 'unsafe path'):
            narration._asset(self.root, 'assets/../escape.wav')
        (self.root / 'linked').symlink_to(self.root / 'assets', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            narration._inside(self.root, 'linked/output.wav')
        for identity in [{}, dict(IDENTITY, provider='paid'), dict(IDENTITY, voice='Ryan'), dict(IDENTITY, speed=.8)]:
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                narration.generate(self.root, identity, self.engine)
        self.assertFalse(self.engine.calls)

    def test_parallel_claims_deduplicate_resume_and_match_sequential_audio(self):
        # Preserve real progress made by the old sequential implementation.
        self.engine.fail_at = 3
        with self.assertRaisesRegex(RuntimeError, 'interruption'):
            self.stage()
        before = self.snapshot()
        saved = {p: (narration.digest(p), p.stat().st_mtime_ns)
                 for p in (self.root / narration.STAGE / 'staged').rglob('*') if p.is_file()}
        corpus = narration.capture_corpus(self.root)
        identity = narration._harness(IDENTITY)
        requests = narration.synthesis_requests(corpus, identity)
        self.assertEqual(len(requests), 5)  # 6 leaves, duplicate English request
        self.assertEqual(set(requests), {narration._request(e, identity)
                                        for e in corpus.values() if 'sources' not in e})
        cache = self.root / narration.STAGE / 'cache'
        pending = narration._pending_requests(cache, corpus, identity)
        self.assertEqual(len(pending), 3)
        provider = self.root / 'parallel_provider.py'
        # Real spawned processes, real ffmpeg, append-only synthesis claims.
        # Its PCM bytes match the sequential Engine fixture above.
        write_wave(self.root / 'tone.wav', rate=24000, channels=2)
        provider.write_text(
            'import os,json,time,shutil\nfrom pathlib import Path\n'
            'class Engine:\n'
            ' def __init__(self, pack): self.root=Path(pack["root"])\n'
            ' def write(self,text,voice,language,output):\n'
            '  fd=os.open(self.root/"claims.jsonl",os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)\n'
            '  os.write(fd,(json.dumps([os.getpid(),text,voice,language])+"\\n").encode());os.close(fd)\n'
            '  time.sleep(.25)\n'
            '  shutil.copyfile(self.root/"tone.wav",output)\n')
        config = (str(provider), {'root': str(self.root)})
        narration.generate(self.root, IDENTITY, corpus=corpus, workers=2, worker_config=config)
        claims = [json.loads(line) for line in (self.root / 'claims.jsonl').read_text().splitlines()]
        self.assertEqual(len(claims), len(pending))
        self.assertEqual(len({row[0] for row in claims}), 2)
        self.assertEqual({tuple(row[1:]) for row in claims},
                         {(e['text'], 'Serena', e['language']) for _, e in pending.values()})
        for path, (checksum, stamp) in saved.items():
            self.assertEqual((narration.digest(path), path.stat().st_mtime_ns), (checksum, stamp))
        self.assertEqual(self.snapshot(), before)
        narration.validate(self.root, corpus)
        parallel = {p.relative_to(self.root / narration.STAGE / 'staged'): narration.digest(p)
                    for p in (self.root / narration.STAGE / 'staged').rglob('*') if p.is_file()}
        # Full sequential reference: identical WAVs and receipts, including the
        # dependency assembly. No RNG state is shared between spawned workers.
        shutil.rmtree(self.root / narration.STAGE)
        self.engine.fail_at = None
        self.stage()
        self.assertEqual(parallel, {p.relative_to(self.root / narration.STAGE / 'staged'): narration.digest(p)
                                   for p in (self.root / narration.STAGE / 'staged').rglob('*') if p.is_file()})

    def test_exclusive_coordinator_and_cooperative_pause_resume(self):
        work = narration._ignored(self.root, narration.STAGE)
        with narration._claim(work / 'coordinator.lock'):
            with self.assertRaisesRegex(RuntimeError, 'another narration coordinator'):
                self.stage()
        narration._write_json(work / 'pause.request', {'requested': True})
        with self.assertRaises(narration.Paused):
            self.stage()
        self.assertFalse(self.engine.calls)
        corpus = narration.generate(self.root, IDENTITY, self.engine, resume=True)
        narration.validate(self.root, corpus)
        self.assertFalse((work / 'pause.request').exists())
        for workers in (0, 4, True):
            with self.assertRaisesRegex(ValueError, 'workers'):
                narration.generate(self.root, IDENTITY, self.engine, workers=workers)

    def test_parallel_pause_finishes_inflight_cache_and_resume_keeps_it(self):
        provider = self.root / 'pause_provider.py'
        write_wave(self.root / 'tone.wav', rate=24000, channels=2)
        provider.write_text(
            'import shutil,time\nfrom pathlib import Path\n'
            'class Engine:\n'
            ' def __init__(self,pack): self.root=Path(pack["root"])\n'
            ' def write(self,text,voice,language,output):\n'
            '  if not (self.root/"pause-once").exists():\n'
            '   (self.root/"pause-once").touch()\n'
            '   (self.root/"work/qwen-narration/pause.request").touch()\n'
            '  time.sleep(.1)\n'
            '  shutil.copyfile(self.root/"tone.wav",output)\n')
        config = (str(provider), {'root': str(self.root)})
        corpus = narration.capture_corpus(self.root)
        original = self.snapshot()
        with self.assertRaises(narration.Paused):
            narration.generate(self.root, IDENTITY, workers=2, worker_config=config)
        cache = self.root / narration.STAGE / 'cache'
        # A pause during inference still commits that validated cache pair.
        saved = {p: (narration.digest(p), p.stat().st_mtime_ns)
                 for p in cache.glob('*.wav')}
        self.assertTrue(saved)
        identity = narration._harness(IDENTITY)
        requests = narration.synthesis_requests(corpus, identity)
        for path in saved:
            _, entry = requests[path.stem]
            metadata = {k: v for k, v in narration._metadata(entry, identity, None).items()
                        if k != 'input_identity'}
            narration._verified(path, metadata)
        narration.generate(self.root, IDENTITY, workers=2, worker_config=config, resume=True)
        narration.validate(self.root, corpus)
        self.assertEqual(self.snapshot(), original)
        for path, expected in saved.items():
            self.assertEqual((narration.digest(path), path.stat().st_mtime_ns), expected)

    def test_standalone_provider_cli_stages_only_disposable_fixture(self):
        provider = self.root / 'provider'
        provider.mkdir()
        source = (
            'import shutil\nfrom pathlib import Path\nclass Engine:\n'
            '    def __init__(self, pack):\n'
            '        assert isinstance(pack, dict), "Engine requires a dict"\n'
            '        assert pack["provider"] == "qwen3-tts"\n'
            '        self.pack = Path(pack["model"])\n'
            '    def write(self, text, voice, language, output):\n'
            '        assert voice == "Serena" and language in ("en", "de", "es")\n'
            '        shutil.copyfile(self.pack / "tone.wav", output)\n')
        (provider / 'local_speech_qwen.py').write_text(source)
        (provider / 'fixture_provider.py').write_text(source)
        pack = self.root / 'pack'
        write_wave(pack / 'tone.wav', rate=24000, channels=2)
        pack_json = self.root / 'pack.json'
        narration._write_json(pack_json, {'provider': 'qwen3-tts', 'model': str(pack)})
        identity = self.root / 'identity.json'
        narration._write_json(identity, IDENTITY)
        original = self.snapshot()
        command = [sys.executable, str(ROOT / 'tools/local_narration.py'), 'stage',
                   '--root', str(self.root), '--harness-root', str(provider),
                   '--pack', str(pack_json), '--identity', str(identity)]
        result = subprocess.run(command, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['paths'], 7)
        self.assertEqual(len(result.stderr.splitlines()), 7)
        self.assertIn('local narration 7/7 ', result.stderr)
        for action in ('clip', 'cache', 'assembly'):
            self.assertIn(f' {action}: assets/', result.stderr)
        resumed = subprocess.run(command + ['--provider-module', 'fixture_provider.py'],
                                 text=True, capture_output=True, timeout=30)
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertEqual(sum(' staged: ' in line for line in resumed.stderr.splitlines()), 7)
        for unsafe in ('../local_speech_qwen.py', '/local_speech_qwen.py', 'folder/provider.py', 'provider\\escape.py'):
            with self.subTest(provider_module=unsafe):
                rejected = subprocess.run(command + ['--provider-module', unsafe],
                                          text=True, capture_output=True, timeout=30)
                self.assertEqual(rejected.returncode, 2)
                self.assertIn('safe Python basename', rejected.stderr)
        self.assertEqual(self.snapshot(), original)
        self.assertFalse((self.root / 'backup').exists())
        narration.validate(self.root, narration.capture_corpus(self.root))


class SeededEngine(Engine):
    """Fixture engine that also accepts pinned retake seeds."""
    def write(self, text, voice, language, output, seeds=None):
        self.calls.append((text, voice, language, seeds))
        write_wave(output, rate=24000, channels=2, silent=self.silent, seconds=self.seconds)


RYAN = {'model': 'Qwen3-TTS-fixture', 'pack': {'sha256': 'fixture-pack-1'}}
RETAKE_PACK = {'sha256': 'fixture-pack-retake'}


class VoicePlanTest(NarrationFixture):
    """Per-kind voices, retake seeds and scoped promotion on disposable fixtures."""

    def setUp(self):
        super().setUp()
        self.engine = SeededEngine()
        self.one = 'assets/jungle-book/sounds/de/simple/one.wav'
        self.de_a = 'assets/jungle-book/sounds/de/letters/a.wav'
        self.de_b = 'assets/jungle-book/sounds/de/letters/b.wav'
        self.lesson = 'assets/jungle-book/sounds/de/lesson.wav'
        self.add(self.one, 'Ab.')
        self.add(self.de_a, 'A')
        self.add(self.de_b, 'B')
        self.add(self.lesson, 'Ab. A. B. Ab.', sources=[self.one, self.de_a, self.de_b])
        self.plan = {
            'voices': {'Serena': dict(IDENTITY, retake_pack=RETAKE_PACK), 'Ryan': RYAN},
            'default': 'Serena',
            'languages': {'de': {'word': 'Ryan', 'sentence': 'Ryan', 'letter': 'Serena'}},
            'retakes': {self.de_a: {'seeds': [7, 8]}},
        }

    def receipt(self, name):
        return json.loads(self.staged(name).with_suffix('.speech.json').read_text())

    def test_kinds(self):
        corpus = narration.capture_corpus(self.root)
        self.assertEqual(narration.content_kind(self.one, corpus[self.one]), 'word')
        self.assertEqual(narration.content_kind(self.de_a, corpus[self.de_a]), 'letter')
        self.assertEqual(narration.content_kind('assets/jungle-book/sounds/de/simple/word.wav',
                                                corpus['assets/jungle-book/sounds/de/simple/word.wav']), 'sentence')
        self.assertEqual(narration.content_kind(self.lesson, corpus[self.lesson]), 'spelling')

    def test_plan_routes_voices_pins_retake_seeds_and_records_receipts(self):
        before = self.snapshot()
        corpus = narration.generate(self.root, self.plan, self.engine)
        self.assertEqual(self.snapshot(), before)
        calls = {(text, language): (voice, seeds) for text, voice, language, seeds in self.engine.calls}
        self.assertEqual(calls[('Ab.', 'de')], ('Ryan', None))
        self.assertEqual(calls[('A b', 'de')], ('Ryan', None))
        self.assertEqual(calls[('B', 'de')], ('Serena', None))
        self.assertEqual(calls[('A', 'de')], ('Serena', [7, 8]))
        self.assertEqual(calls[('A', 'en')], ('Serena', None))
        self.assertEqual(calls[('A b', 'es')], ('Serena', None))
        word, letter, lesson = self.receipt(self.one), self.receipt(self.de_a), self.receipt(self.lesson)
        self.assertEqual((word['voice'], word['kind'], word['pack']), ('Ryan', 'word', RYAN['pack']))
        self.assertNotIn('seeds', word)
        # Retakes record their seeds and the identity of the provider honouring them.
        self.assertEqual((letter['voice'], letter['kind'], letter['seeds'], letter['pack']),
                         ('Serena', 'letter', [7, 8], RETAKE_PACK))
        self.assertEqual((lesson['voice'], lesson['kind'], lesson['voices']), ('Ryan', 'spelling', ['Ryan', 'Serena']))
        self.assertNotIn('retake_pack', letter)
        result = narration.validate(self.root, corpus)
        self.assertEqual(result['plan']['retakes'], self.plan['retakes'])
        inventory = json.loads((self.root / narration.STAGE / 'inventory.json').read_text())
        self.assertEqual(inventory['format'], 'jungle-local-narration-2')
        # A changed retake seed is a different synthesis request; resume is a noop.
        self.engine.calls.clear()
        narration.generate(self.root, self.plan, self.engine)
        self.assertFalse(self.engine.calls)
        changed = dict(self.plan, retakes={self.de_a: {'seeds': [9]}})
        narration.generate(self.root, changed, self.engine)
        self.assertEqual(self.engine.calls, [('A', 'Serena', 'de', [9])])
        tampered = json.loads(self.staged(self.de_a).with_suffix('.speech.json').read_text())
        tampered['voice'] = 'Ryan'
        narration._write_json(self.staged(self.de_a).with_suffix('.speech.json'), tampered)
        with self.assertRaisesRegex(ValueError, 'stale'):
            narration.validate(self.root, corpus)

    def test_engines_per_voice(self):
        serena, ryan = SeededEngine(), SeededEngine()
        narration.generate(self.root, self.plan, {'Serena': serena, 'Ryan': ryan})
        self.assertEqual({c[1] for c in serena.calls}, {'Serena'})
        self.assertEqual({c[1] for c in ryan.calls}, {'Ryan'})
        shutil.rmtree(self.root / narration.STAGE)
        with self.assertRaisesRegex(ValueError, 'no local engine configured for voice Ryan'):
            narration.generate(self.root, self.plan, {'Serena': serena})

    def test_invalid_plans_fail_before_generation(self):
        for plan in [dict(self.plan, default='Aiden'),
                     dict(self.plan, languages={'de': {'story': 'Ryan'}}),
                     dict(self.plan, languages={'de': {'word': 'Aiden'}}),
                     dict(self.plan, languages={'fr': {'word': 'Ryan'}}),
                     dict(self.plan, retakes={self.de_a: {'seeds': []}}),
                     dict(self.plan, retakes={self.de_a: {'seeds': [-1]}}),
                     dict(self.plan, retakes={self.de_a: {'seeds': [1], 'voice': 'Ryan'}}),
                     dict(self.plan, retakes={self.lesson: {'seeds': [1]}}),
                     dict(self.plan, retakes={'assets/missing.wav': {'seeds': [1]}}),
                     dict(self.plan, voices={'Ser ena': IDENTITY}),
                     dict(self.plan, voices={'Ryan': dict(RYAN, speed=.8)}),
                     dict(self.plan, extra=True)]:
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                narration.generate(self.root, plan, self.engine)
        self.assertFalse(self.engine.calls)

    def test_promote_selected_paths_with_dependents_only(self):
        corpus = narration.generate(self.root, self.plan, self.engine)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'dependent assembly'):
            narration.promote(self.root, corpus, paths={self.one})
        with self.assertRaisesRegex(ValueError, 'canonical'):
            narration.promote(self.root, corpus, paths={'assets/missing.wav'})
        self.assertEqual(self.snapshot(), before)
        chosen = {self.one, self.lesson}
        backup = narration.promote(self.root, corpus, paths=chosen)
        after = self.snapshot()
        changed = {name for name in after if after[name] != before[name]}
        self.assertEqual(changed, {n.removesuffix('.wav') + suffix for n in chosen for suffix in ('.wav', '.speech.json')})
        journal = json.loads((backup / 'promotion.json').read_text())
        self.assertEqual((journal['status'], journal['paths']), ('complete', sorted(chosen)))
        self.assertTrue((backup / self.one).is_file())
        self.assertFalse((backup / self.de_a).exists())

    def test_settings_plan_from_speech_json(self):
        narration._write_json(self.root / 'speech.json', {'narration': {
            'de': {'voice': 'Serena', 'voices': {'word': 'Ryan', 'sentence': 'Ryan'},
                   'retakes': {self.de_a: {'seeds': [7, 8]}}},
            'es': {'voice': 'Serena'}, 'en': {'voice': 'af_bella'}}})
        plan = narration.settings_plan(self.root, {'Serena': dict(IDENTITY, retake_pack=RETAKE_PACK), 'Ryan': RYAN})
        self.assertEqual(plan['languages']['de'], {'letter': 'Serena', 'word': 'Ryan', 'sentence': 'Ryan'})
        self.assertEqual(plan['languages']['es'], {'letter': 'Serena', 'word': 'Serena', 'sentence': 'Serena'})
        self.assertEqual(plan['retakes'], {self.de_a: {'seeds': [7, 8]}})
        self.assertNotIn('en', plan['languages'])
        with self.assertRaisesRegex(ValueError, 'no identity for planned voices: Ryan'):
            narration.settings_plan(self.root, {'Serena': IDENTITY})

    def test_voices_cli_stages_plan_from_speech_json(self):
        narration._write_json(self.root / 'speech.json', {'narration': {
            'de': {'voice': 'Serena', 'voices': {'word': 'Ryan', 'sentence': 'Ryan'},
                   'retakes': {self.de_a: {'seeds': [7]}}},
            'es': {'voice': 'Serena'}}})
        provider = self.root / 'provider'
        provider.mkdir()
        (provider / 'local_speech_qwen.py').write_text(
            'import json,shutil\nfrom pathlib import Path\nclass Engine:\n'
            '    def __init__(self, pack):\n'
            '        self.pack = pack\n'
            '    def write(self, text, voice, language, output, seeds=None):\n'
            '        assert voice == self.pack["voice"], (voice, self.pack)\n'
            '        with open(self.pack["log"], "a") as log: log.write(json.dumps([text, voice, language, seeds]) + "\\n")\n'
            '        shutil.copyfile(self.pack["tone"], output)\n')
        write_wave(self.root / 'tone.wav', rate=24000, channels=2)
        log = self.root / 'calls.jsonl'
        voices = {name: dict(identity, engine={'voice': name, 'tone': str(self.root / 'tone.wav'), 'log': str(log)})
                  for name, identity in (('Serena', IDENTITY), ('Ryan', RYAN))}
        narration._write_json(self.root / 'voices.json', voices)
        command = [sys.executable, str(ROOT / 'tools/local_narration.py'), 'stage', '--root', str(self.root),
                   '--harness-root', str(provider), '--voices', str(self.root / 'voices.json')]
        result = subprocess.run(command, text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['plan']['retakes'], {self.de_a: {'seeds': [7]}})
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertIn(['A', 'Serena', 'de', [7]], calls)
        self.assertIn(['Ab.', 'Ryan', 'de', None], calls)
        mixed = subprocess.run(command + ['--pack', str(self.root / 'voices.json')], text=True,
                               capture_output=True, timeout=60)
        self.assertEqual(mixed.returncode, 2)


if __name__ == '__main__':
    unittest.main()

"""Synthetic Qwen stages only: real ffmpeg, no model, no application assets."""
from array import array
from contextlib import redirect_stderr
import copy
import io
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
import local_narration_profiles as profiles
from book_speech import read_clip
from speech_manifest import AddSpeechProfiles, ValidateSpeechManifest, FORMAT, PCM_FORMAT


def write_wave(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    values = array('h', (int(6000 * math.sin(i * math.tau * 330 / 22050))
                         if 1500 < i < 15000 else 0 for i in range(17640)))
    if sys.byteorder != 'little':
        values.byteswap()
    with wave.open(str(path), 'wb') as clip:
        clip.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
        clip.writeframes(values.tobytes())


class SyntheticEngine:
    def write(self, text, voice, language, output):
        write_wave(output)


def snapshot(folder):
    return {p.relative_to(folder).as_posix(): narration.digest(p)
            for p in folder.rglob('*') if p.is_file()}


class LocalNarrationProfilesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('ffmpeg'):
            raise RuntimeError('profile tests require ffmpeg')
        (ROOT / 'work').mkdir(exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(dir=ROOT / 'work', prefix='qwen-profiles-fixture-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.fixture = Path(cls.temporary.name)
        subprocess.run(['git', 'init', '-q', str(cls.fixture)], check=True)
        (cls.fixture / '.gitignore').write_text('work/\nbackup/\n')
        for language in ('en', 'de', 'es'):
            prefix = f'assets/jungle-book/sounds/{language}/'
            names = [prefix + 'simple/word.wav', prefix + 'letters/a.wav', prefix + 'letters/b.wav']
            for name, text in zip(names, ['A b', 'A', 'B']):
                path = cls.fixture / name
                write_wave(path)
                narration._write_json(path.with_suffix('.speech.json'),
                                      dict(text=text, language=language, sha256=narration.digest(path)))
            path = cls.fixture / (prefix + 'lesson.wav')
            write_wave(path)
            narration._write_json(path.with_suffix('.speech.json'),
                                  dict(text='A b. A. B. A b.', language=language,
                                       sha256=narration.digest(path), method=narration.METHOD,
                                       sources=[dict(path=n, sha256=narration.digest(cls.fixture / n)) for n in names]))
        cls.original = snapshot(cls.fixture / 'assets')
        with redirect_stderr(io.StringIO()):
            cls.corpus = narration.generate(cls.fixture, dict(model=profiles.MODEL, pack={'fixture': 'synthetic'}),
                                            SyntheticEngine())
        cls.normal = snapshot(cls.fixture / narration.STAGE)
        cls.inventory = profiles.stage_profiles(cls.fixture, cls.corpus)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT / 'work', prefix='qwen-profiles-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        shutil.copytree(self.fixture, self.root, dirs_exist_ok=True)
        self.inventory = copy.deepcopy(self.inventory)
        self.output = self.root / profiles.STAGE / 'staged'

    def promote_fixture(self):
        # Only disposable assets are promoted, never the repository's real stage.
        shutil.copytree(self.root / narration.STAGE / 'staged/assets', self.root / 'assets', dirs_exist_ok=True)
        shutil.copytree(self.output / 'assets', self.root / 'assets', dirs_exist_ok=True)

    def save_inventory(self):
        narration._write_json(self.root / 'assets/speech-profiles.json', self.inventory)

    def manifest(self):
        manifest = dict(format=FORMAT, audio=PCM_FORMAT, clips={}, voices={}, counts={})
        return AddSpeechProfiles(manifest, self.root)

    def edit_receipt(self, profile, name, **changes):
        path = self.root / profiles.profile_path(name, profile)
        receipt = narration._json(path.with_suffix('.speech.json'))
        receipt.update(changes)
        narration._write_json(path.with_suffix('.speech.json'), receipt)
        self.inventory['profiles'][profile]['recordings'][name] = profiles._evidence(path, receipt['language'])
        self.save_inventory()

    def test_stage_is_readonly_and_frames_are_measured(self):
        self.assertEqual(snapshot(self.root / 'assets'), self.original)
        self.assertEqual(snapshot(self.root / narration.STAGE), self.normal)
        self.assertEqual(self.inventory['languages'], ['en', 'de', 'es'])
        self.assertEqual(self.inventory['default'], 'normal')
        for name in self.corpus:
            frames = [self.inventory['profiles'][p]['recordings'][name]['frame_count']
                      for p in ('slow', 'normal', 'fast')]
            self.assertGreater(frames[0], frames[1])
            self.assertGreater(frames[1], frames[2])
            for p, speed in profiles.SPEEDS.items():
                self.assertEqual(set(self.inventory['profiles'][p]['voices']), set(self.corpus))
                self.assertEqual(self.inventory['profiles'][p]['speed'], speed)
        self.assertFalse((self.output / 'assets/jungle-book').exists())

    def test_multilingual_manifest_and_exact_assembly(self):
        self.promote_fixture()
        manifest = self.manifest()
        ValidateSpeechManifest(manifest, self.root)
        self.assertEqual(manifest['counts']['voices'], len(self.corpus) * 3)
        for name, entry in self.corpus.items():
            for p in profiles.SPEEDS:
                target = profiles.profile_path(name, p)
                if 'sources' not in entry:
                    self.assertEqual(manifest['clips'][target]['language'], entry['language'])
                    continue
                segments = manifest['voices'][target]
                gaps = [s['silence'] for s in segments if 'silence' in s]
                self.assertEqual(gaps, [11025, 5512, 7350, 5512, 5512])
                expected = profiles._assembled(self.root, profiles._parts(entry, p))
                with wave.open(str(self.root / target)) as clip:
                    self.assertEqual(clip.readframes(clip.getnframes()), expected)
                # First and last word are trimmed copies of the exact profile word.
                self.assertTrue(expected.startswith(read_clip(self.root / profiles.profile_path(entry['sources'][0], p))[0]))

    def test_incomplete_or_extra_mapping_rejected(self):
        self.promote_fixture()
        name = next(iter(self.corpus))
        for p in profiles.SPEEDS:
            del self.inventory['profiles'][p]['voices'][name]
            del self.inventory['profiles'][p]['recordings'][name]
        self.save_inventory()
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            self.manifest()
        self.inventory = copy.deepcopy(type(self).inventory)
        self.inventory['profiles']['slow']['voices']['assets/en/extra.wav'] = 'assets/en/extra.wav'
        self.save_inventory()
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            self.manifest()

    def test_paths_and_symlinks_rejected(self):
        self.promote_fixture()
        name = next(iter(self.corpus))
        for target in ('assets/../escape.wav', '/tmp/escape.wav', 'assets/speech-profiles/fast/wrong.wav'):
            self.inventory['profiles']['slow']['voices'][name] = target
            self.save_inventory()
            with self.assertRaisesRegex(ValueError, 'unsafe'):
                self.manifest()
        self.inventory = copy.deepcopy(type(self).inventory)
        self.save_inventory()
        path = self.root / profiles.profile_path(name, 'slow')
        path.unlink()
        path.symlink_to(self.root / name)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.manifest()

    def test_language_voice_and_speed_rejected(self):
        self.promote_fixture()
        name = 'assets/jungle-book/sounds/de/simple/word.wav'
        path = self.root / profiles.profile_path(name, 'slow')
        original = path.with_suffix('.speech.json').read_text()
        for changes in (dict(language='en'), dict(voice='Ryan'), dict(speed=1.0), dict(model='other')):
            path.with_suffix('.speech.json').write_text(original)
            self.edit_receipt('slow', name, **changes)
            with self.assertRaises(ValueError):
                self.manifest()

    def test_source_hash_and_frame_evidence_rejected(self):
        self.promote_fixture()
        name = 'assets/jungle-book/sounds/es/simple/word.wav'
        self.edit_receipt('slow', name, source_sha256='0' * 64)
        with self.assertRaisesRegex(ValueError, 'source identity'):
            self.manifest()
        self.promote_fixture()
        self.inventory = copy.deepcopy(type(self).inventory)
        self.inventory['profiles']['fast']['recordings'][name]['frame_count'] += 1
        self.save_inventory()
        with self.assertRaisesRegex(ValueError, 'evidence'):
            self.manifest()

    def test_original_receipt_and_variant_pack_rejected(self):
        self.promote_fixture()
        name = 'assets/jungle-book/sounds/en/simple/word.wav'
        self.edit_receipt('slow', name, pack={'fixture': 'different'})
        with self.assertRaisesRegex(ValueError, 'pack identity'):
            self.manifest()
        self.promote_fixture()
        self.inventory = copy.deepcopy(type(self).inventory)
        path = self.root / name
        receipt = narration._json(path.with_suffix('.speech.json'))
        receipt['request_sha256'] = '0' * 64
        narration._write_json(path.with_suffix('.speech.json'), receipt)
        self.inventory['profiles']['normal']['recordings'][name] = profiles._evidence(path, 'en')
        self.save_inventory()
        with self.assertRaises(ValueError):
            self.manifest()

    def test_stale_stage_files_rejected(self):
        extra = self.output / 'assets/speech-profiles/slow/en/stale.wav'
        write_wave(extra)
        with self.assertRaisesRegex(ValueError, 'extra staged'):
            profiles.validate_inventory(self.output, self.inventory,
                                        normal_root=self.root / narration.STAGE / 'staged')

    def test_original_silence_recipe_required(self):
        self.promote_fixture()
        name = 'assets/jungle-book/sounds/de/lesson.wav'
        receipt = narration._json((self.root / profiles.profile_path(name, 'fast')).with_suffix('.speech.json'))
        receipt['recipe']['parts'][1]['silence_frames'] -= 1
        self.edit_receipt('fast', name, recipe=receipt['recipe'])
        with self.assertRaisesRegex(ValueError, 'assembly provenance'):
            self.manifest()

    def test_exact_assembly_rejected_even_with_fresh_hashes(self):
        self.promote_fixture()
        name = 'assets/jungle-book/sounds/es/lesson.wav'
        path = self.root / profiles.profile_path(name, 'slow')
        with wave.open(str(path)) as clip:
            pcm = bytearray(clip.readframes(clip.getnframes()))
        pcm[100:102] = b'\xff\x3f'
        with wave.open(str(path), 'wb') as clip:
            clip.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
            clip.writeframes(pcm)
        self.edit_receipt('slow', name, sha256=narration.digest(path))
        with self.assertRaisesRegex(ValueError, 'assembly PCM'):
            self.manifest()

    def test_incomplete_qwen_stage_fails_before_output(self):
        shutil.rmtree(self.root / profiles.STAGE)
        name = next(iter(self.corpus))
        (self.root / narration.STAGE / 'staged' / name).unlink()
        with patch.object(profiles.subprocess, 'run') as command:
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                profiles.stage_profiles(self.root, self.corpus)
            command.assert_not_called()
        self.assertFalse((self.root / profiles.STAGE).exists())

    def test_v1_remains_compatible(self):
        from speech_profiles_test import staging_test
        staging_test()


if __name__ == '__main__':
    unittest.main()

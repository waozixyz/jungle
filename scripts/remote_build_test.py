#!/usr/bin/env python3
"""Local protocol tests; no SSH, build, display, or owner data access."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import shlex
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import remote_build as workflow


class SyncTest(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[1] / 'work/remote-build-tests'
        base.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(dir=base))
        self.name = workflow.PROJECT + '/host/current.zi'

    def tearDown(self):
        shutil.rmtree(self.root)

    def receive(self, files, payloads=None):
        payloads = files if payloads is None else payloads
        proposal = {'files': {name: {'sha256': hashlib.sha256(data).hexdigest(), 'mode': 0o644}
                              for name, data in files.items()}, 'content_sha256': 'test', 'heads': {}}
        buffer = io.BytesIO()
        buffer.write((json.dumps(proposal) + '\n').encode())
        with tarfile.open(fileobj=buffer, mode='w') as archive:
            for name, data in payloads.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        buffer.seek(0)
        with patch('sys.stdin', io.TextIOWrapper(buffer)), contextlib.redirect_stdout(io.StringIO()):
            workflow.receive(self.root)

    def test_current_edits_update_and_private_files_survive(self):
        self.receive({self.name: b'current uncommitted edit'})
        private = self.root / workflow.PROJECT / 'work/private-save'
        private.write_text('owner data')
        self.receive({self.name: b'latest edit'})
        self.assertEqual((self.root / self.name).read_bytes(), b'latest edit')
        self.assertEqual(private.read_text(), 'owner data')

    def test_source_mutates_after_snapshot_receiver_uses_captured_bytes(self):
        desktop = self.root / 'desktop'
        folder = desktop / workflow.PROJECT
        source = folder / 'host/current.zi'
        source.parent.mkdir(parents=True)
        source.write_bytes(b'captured working edit')
        private = folder / 'work/private-save'
        private.parent.mkdir()
        private.write_bytes(b'local owner data')
        remote_private = self.root / workflow.PROJECT / 'work/private-save'
        remote_private.parent.mkdir(parents=True)
        remote_private.write_bytes(b'remote owner data')
        payload_path = self.root / 'snapshot.tar'
        git_results = [SimpleNamespace(stdout='revision-at-capture\n'),
                       SimpleNamespace(stdout=b'host/current.zi\0')]
        with payload_path.open('w+b') as payload:
            with patch.object(workflow, 'QUEUE_FILES', ()), patch.object(workflow, 'run', side_effect=git_results):
                proposal = workflow.collect(desktop, payload, {workflow.PROJECT: folder})
            source.write_bytes(b'newer desktop edit')
            buffer = io.BytesIO()
            buffer.write((json.dumps(proposal) + '\n').encode())
            workflow.transfer_payload(payload, buffer, proposal['files'])
        buffer.seek(0)
        with patch('sys.stdin', io.TextIOWrapper(buffer)), contextlib.redirect_stdout(io.StringIO()):
            workflow.receive(self.root)
        self.assertEqual((self.root / self.name).read_bytes(), b'captured working edit')
        self.assertEqual(workflow.digest(self.root / self.name), proposal['files'][self.name]['sha256'])
        self.assertEqual(source.read_bytes(), b'newer desktop edit')
        self.assertEqual(private.read_bytes(), b'local owner data')
        self.assertEqual(remote_private.read_bytes(), b'remote owner data')
        self.assertEqual(proposal['heads'][workflow.PROJECT], 'revision-at-capture')
        self.assertLessEqual(proposal['capture_started_at'], proposal['captured_at'])

    def test_payload_transfer_selects_only_changed_members(self):
        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode='w') as archive:
            for name in ('unchanged', 'changed'):
                member = tarfile.TarInfo(name)
                member.size = 3
                archive.addfile(member, io.BytesIO(b'old'))
        target = io.BytesIO()
        workflow.transfer_payload(payload, target, ['changed'])
        target.seek(0)
        with tarfile.open(fileobj=target) as archive:
            self.assertEqual(archive.getnames(), ['changed'])
            self.assertEqual(archive.extractfile('changed').read(), b'old')

    def test_remote_edit_stops_sync(self):
        self.receive({self.name: b'desktop'})
        (self.root / self.name).write_bytes(b'remote work')
        with self.assertRaisesRegex(RuntimeError, 'Remote source changed'):
            self.receive({self.name: b'new desktop'})
        self.assertEqual((self.root / self.name).read_bytes(), b'remote work')

    def test_unmanaged_collision_stops_sync(self):
        path = self.root / self.name
        path.parent.mkdir(parents=True)
        path.write_bytes(b'private')
        with self.assertRaisesRegex(RuntimeError, 'Unmanaged remote file'):
            self.receive({self.name: b'desktop'})
        self.assertEqual(path.read_bytes(), b'private')

    def test_deleted_managed_file_is_backed_up(self):
        self.receive({self.name: b'old source'})
        self.receive({})
        backup = self.root / workflow.PROJECT / 'backup/remote-build/removed' / self.name
        self.assertEqual(backup.read_bytes(), b'old source')
        self.assertFalse((self.root / self.name).exists())

    def test_changed_in_transit_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'Source changed during transfer'):
            self.receive({self.name: b'expected'}, {self.name: b'changed'})
        self.assertFalse((self.root / self.name).exists())

    def test_interrupted_update_can_resume_without_overwriting_remote_edits(self):
        other = workflow.PROJECT + '/host/other.zi'
        self.receive({self.name: b'old', other: b'old'})
        with self.assertRaisesRegex(RuntimeError, 'Source changed during transfer'):
            self.receive({self.name: b'new', other: b'expected'},
                         {self.name: b'new', other: b'changed during transfer'})
        workflow.recover_pending(self.root)
        self.receive({self.name: b'new', other: b'latest'})
        self.assertEqual((self.root / other).read_bytes(), b'latest')

    def test_traversal_and_linked_parent_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'Unsafe relative path'):
            workflow.safe_path(self.root, '../outside')
        (self.root / 'link').symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, 'linked destination'):
            workflow.safe_path(self.root, 'link/owner-data')


class MakeGoalsTest(unittest.TestCase):
    def setUp(self):
        self.project = Path(__file__).resolve().parents[1]
        base = self.project / 'work/remote-build-tests'
        base.mkdir(parents=True, exist_ok=True)
        self.work = Path(tempfile.mkdtemp(dir=base))
        self.marker = self.work / 'local-compiler-invoked'
        self.sentinel = self.work / 'ziran-sentinel'
        self.sentinel.write_text('#!/bin/sh\necho invoked >> ' + shlex.quote(str(self.marker)) + '\nexit 99\n')
        self.sentinel.chmod(0o755)
        self.make = shutil.which('make', path='/usr/bin:/bin')

    def tearDown(self):
        shutil.rmtree(self.work)

    def test_remote_only_dry_run_never_invokes_local_toolchain(self):
        for goals in (['remote-debug'], ['remote-run'], ['remote-debug', 'remote-run']):
            result = subprocess.run([self.make, '-n', 'ZIRAN=' + str(self.sentinel), *goals],
                                    cwd=self.project, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('scripts/remote_build.py', result.stdout)
            self.assertFalse(self.marker.exists(), 'Remote-only goal resolved a desktop package')

    def test_default_and_mixed_goals_keep_native_rule_parsing(self):
        # Question mode never executes recipes or builds; the sentinel records
        # only native prerequisite expansion while Make parses the real file.
        for goals in ([], ['remote-debug', 'all']):
            subprocess.run([self.make, '-q', 'ZIRAN=' + str(self.sentinel), *goals],
                           cwd=self.project, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.assertTrue(self.marker.exists(), 'Native rules were omitted for default/mixed goals')
            self.marker.unlink()


if __name__ == '__main__':
    unittest.main()

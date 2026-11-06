#!/usr/bin/env python3
"""Two UI test runs at once each keep their own captures, logs and receipts.

Tasks and CI groups start the same smoke tests side by side. Every run writes
into its own runtime_test.run_folder(), so one run never overwrites or reads
another's screenshots. Without --ui two processes write same-named captures
at the same moment; with --ui two real smoke runs each open Jungle on their
own private Xvfb and capture the start screen together.
"""
import argparse
from datetime import datetime, timedelta
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import runtime_test as rt

ROOT = rt.ROOT
BASE = 'backup/run-isolation'


def child(mode, binary):
    """One run: report its folders, then write captures under the same names."""
    folder = rt.run_folder(BASE)
    print(f'run={rt.RUN}', flush=True)
    print(f'folder={folder}', flush=True)
    if mode == 'files':
        print(f'output={rt.OUTPUT}', flush=True)
        rt.claim(rt.OUTPUT)
        stamp = rt.RUN.encode()
        for index in range(200):
            for target in (folder, rt.OUTPUT):
                (target / 'capture.png').write_bytes(stamp * 50 + str(index).encode())
            time.sleep(.005)
        for target in (folder, rt.OUTPUT):
            assert (target / 'capture.png').read_bytes() == stamp * 50 + b'199'
        return
    rt.OUTPUT = folder / 'captures'
    print(f'output={rt.OUTPUT}', flush=True)
    with tempfile.TemporaryDirectory(dir=folder) as data:
        (Path(data) / 'sound.txt').write_text('off\n')
        with rt.Desktop(binary, Path(data)) as desktop:
            desktop.capture('start')
            time.sleep(1)
            desktop.capture('start')
    (folder / 'receipt.txt').write_text(rt.RUN + '\n')


def both(mode, binary):
    """Start two runs together and check every file is the run's own."""
    command = [sys.executable, __file__, '--child', mode, '--binary', str(binary)]
    env = {k: v for k, v in os.environ.items() if k not in ('JUNGLE_TEST_RUN', 'JUNGLE_TEST_OUTPUT')}
    runs = [subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for _ in range(2)]
    outputs = [run.communicate(timeout=240)[0] for run in runs]
    for run, output in zip(runs, outputs):
        assert run.returncode == 0, output
    found = [dict(line.split('=', 1) for line in output.splitlines() if line.split('=', 1)[0] in ('run', 'folder', 'output'))
             for output in outputs]
    assert found[0]['run'] != found[1]['run'], found
    for key in ('folder', 'output'):
        assert found[0][key] != found[1][key], (key, found)
    for item in found:
        folder, output = Path(item['folder']), Path(item['output'])
        assert folder.parent == ROOT / BASE and folder.name == item['run'], item
        if mode == 'files':
            for target in (folder, output):
                assert (target / 'capture.png').read_bytes() == item['run'].encode() * 50 + b'199', target
        else:
            assert (folder / 'receipt.txt').read_text() == item['run'] + '\n'
            assert {'start.png', 'xvfb.log', 'jungle.log'} <= {p.name for p in output.iterdir()}, output
            from PIL import Image
            with Image.open(output / 'start.png') as picture:
                picture.load()
                assert picture.width > 300 and picture.height > 200, picture.size
    for item in found:
        shutil.rmtree(item['folder'], ignore_errors=True)
        if mode == 'files':
            shutil.rmtree(item['output'], ignore_errors=True)
    return found


def pruning():
    """Old finished runs beyond the newest few go; young runs and other names stay."""
    with tempfile.TemporaryDirectory(dir=ROOT / 'build') as scratch:
        base = Path(scratch)
        old = datetime.now() - timedelta(hours=8)
        names = [f'{old + timedelta(minutes=i):%Y%m%d-%H%M%S}-{100 + i}-abcd' for i in range(6)]
        young = f'{datetime.now():%Y%m%d-%H%M%S}-7-abcd'
        for name in names + [young, 'captures', 'ci-group-1']:
            (base / name).mkdir()
        rt.run_folder(base)
        left = {p.name for p in base.iterdir()}
        assert left == set(names[3:]) | {young, 'captures', 'ci-group-1', rt.RUN}, sorted(left)
        recent = [f'{datetime.now() - timedelta(minutes=30 - i):%Y%m%d-%H%M%S}-{i}-abcd' for i in range(6)]
        for name in recent:
            (base / name).mkdir()
        rt.prune_runs(base)
        assert set(recent) <= {p.name for p in base.iterdir()}, 'a run younger than the stale age was removed'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ui', action='store_true', help='also run two real smoke runs on private Xvfb displays')
    parser.add_argument('--child', choices=('files', 'ui'))
    parser.add_argument('--binary', type=Path, default=ROOT / 'build/app/jungle')
    args = parser.parse_args()
    if args.child:
        child(args.child, args.binary.resolve())
        return
    pruning()
    both('files', args.binary.resolve())
    print('local run isolation test: two concurrent runs kept their own folders and captures; old runs pruned', flush=True)
    if args.ui:
        found = both('ui', args.binary.resolve())
        print('local run isolation UI test: two smoke runs at once, captures in '
              + ' and '.join(item['output'] for item in found) + ' (removed after checking)', flush=True)


if __name__ == '__main__':
    main()

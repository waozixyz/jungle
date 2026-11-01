#!/usr/bin/env python3
"""Synchronize current canonical sources and build Jungle on an SSH host."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import shutil
import subprocess
import sys
import tarfile
import time

PROJECT = 'waozixyz/learning/jungle'
REPOS = ('ziranlang/ziran', 'kryonlabs/kryon', 'kryonlabs/packages/mingcute', PROJECT)
QUEUE = 'waozixyz/harness/harmony'
QUEUE_FILES = ('install-build-queue.py', 'build-queue.py', 'session-resources.py')
PACKAGES = ('git', 'pkg-config', 'libssl-dev', 'libsdl2-dev', 'libcairo2-dev',
            'libfreetype-dev', 'libfontconfig-dev', 'libpango1.0-dev', 'libvorbis-dev',
            'ffmpeg', 'python3-pil')


def run(args, **kwargs):
    command = [str(x) for x in args]
    try:
        return subprocess.run(command, check=True, **kwargs)
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or '')[-2000:] if isinstance(error.stderr, str) else ''
        raise RuntimeError(f'{Path(command[0]).name} exited {error.returncode}' + (': ' + detail if detail else '')) from None


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_path(root, name):
    parts = PurePosixPath(name).parts
    if not parts or name != '/'.join(parts) or any(x in ('.', '..') for x in parts) or name.startswith('/'):
        raise RuntimeError('Unsafe relative path: ' + name)
    path = root.joinpath(*parts)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise RuntimeError('Refusing linked destination: ' + str(path))
    return path


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.next')
    temporary.write_text(json.dumps(value, sort_keys=True) + '\n')
    temporary.replace(path)


def remote_state(root):
    work = safe_path(root, PROJECT + '/work/remote-build')
    work.mkdir(parents=True, exist_ok=True)
    manifest = work / 'sources.json'
    old = json.loads(manifest.read_text()) if manifest.exists() else {'files': {}}
    return work, manifest, old


def recover_pending(root):
    work, manifest, old = remote_state(root)
    journal = work / 'pending.json'
    if not journal.exists():
        return
    pending = json.loads(journal.read_text())
    recovered = {}
    for name in old['files'].keys() | pending['files'].keys():
        path = safe_path(root, name)
        before, after = old['files'].get(name), pending['files'].get(name)
        if not path.exists() and before is None:
            continue
        if not path.exists() and after is None:
            backup = safe_path(root, PROJECT + '/backup/remote-build/removed/' + name)
            if backup.is_file() and digest(backup) == before['sha256']:
                continue
        observed = digest(path) if path.is_file() else None
        matches = [entry for entry in (before, after) if entry and entry['sha256'] == observed]
        if not matches:
            raise RuntimeError('Remote edit during interrupted sync; preserve/reconcile: ' + name)
        recovered[name] = matches[-1]
    save_json(manifest, {'files': recovered, 'content_sha256': None, 'heads': {}, 'incomplete': True})
    journal.unlink()


def inventory(root):
    work, _, old = remote_state(root)
    actual = {}
    for name in old['files']:
        path = safe_path(root, name)
        if path.is_file():
            actual[name] = digest(path)
    ledger = work / 'git-heads.json'
    heads = json.loads(ledger.read_text()) if ledger.exists() else {}
    for repo, head in heads.items():
        folder = safe_path(root, repo)
        safe_path(root, repo + '/.git')
        observed = run(['git', '-C', folder, 'rev-parse', 'HEAD'], env=environment(root),
                       capture_output=True, text=True).stdout.strip()
        if observed != head:
            raise RuntimeError('Remote Git revision changed; preserve/reconcile: ' + repo)
    print(json.dumps({'recorded': old['files'], 'actual': actual, 'git_heads': heads}))


def receive(root):
    proposal = json.loads(sys.stdin.buffer.readline())
    work, manifest, old = remote_state(root)
    # Validate every managed file and every new collision before changing source.
    for name, expected in old['files'].items():
        path = safe_path(root, name)
        if not path.is_file() or digest(path) != expected['sha256']:
            raise RuntimeError('Remote source changed; preserve/reconcile it before syncing: ' + name)
    for name, entry in proposal['files'].items():
        path = safe_path(root, name)
        if name not in old['files'] and path.exists() and (
                not path.is_file() or digest(path) != entry['sha256']):
            raise RuntimeError('Unmanaged remote file conflicts with source: ' + name)
    save_json(work / 'pending.json', proposal)
    with tarfile.open(fileobj=sys.stdin.buffer, mode='r|') as archive:
        for member in archive:
            if not member.isfile() or member.name not in proposal['files']:
                raise RuntimeError('Unexpected archive entry: ' + member.name)
            path = safe_path(root, member.name)
            path.parent.mkdir(parents=True, exist_ok=True)
            staged = path.with_name(path.name + '.remote-next')
            if staged.exists():
                raise RuntimeError('Staging file already exists: ' + str(staged))
            try:
                with archive.extractfile(member) as source, staged.open('xb') as target:
                    shutil.copyfileobj(source, target)
                if digest(staged) != proposal['files'][member.name]['sha256']:
                    raise RuntimeError('Source changed during transfer: ' + member.name)
                previous = old['files'].get(member.name, proposal['files'][member.name])
                if path.exists() and digest(path) != previous['sha256']:
                    raise RuntimeError('Remote source changed while transferring: ' + member.name)
                staged.chmod(proposal['files'][member.name]['mode'])
                staged.replace(path)
            finally:
                staged.unlink(missing_ok=True)
    # Only previously managed, unchanged files absent locally are retired.
    # Keep their bytes in backup; unrelated/private files are never enumerated.
    for name in old['files'].keys() - proposal['files'].keys():
        path = safe_path(root, name)
        backup = safe_path(root, PROJECT + '/backup/remote-build/removed/' + name)
        backup.parent.mkdir(parents=True, exist_ok=True)
        if backup.exists():
            raise RuntimeError('Retired source backup already exists: ' + str(backup))
        path.replace(backup)
    for name, entry in proposal['files'].items():
        path = safe_path(root, name)
        if not path.is_file() or digest(path) != entry['sha256']:
            raise RuntimeError('Remote verification failed: ' + name)
    proposal['verified_at'] = time.time()
    save_json(manifest, proposal)
    (work / 'pending.json').unlink()
    print('Verified current source:', proposal['content_sha256'], 'files:', len(proposal['files']), flush=True)


def environment(root):
    work, _, _ = remote_state(root)
    prefix = work / 'sysroot'
    env = dict(os.environ)
    env['PATH'] = str(Path.home() / '.local/bin') + ':' + str(prefix / 'usr/bin') + ':' + env['PATH']
    env['PKG_CONFIG_PATH'] = ':'.join(str(prefix / p) for p in (
        'usr/lib/x86_64-linux-gnu/pkgconfig', 'usr/lib/pkgconfig', 'usr/share/pkgconfig'))
    env['LD_LIBRARY_PATH'] = str(prefix / 'usr/lib/x86_64-linux-gnu')
    env['LIBRARY_PATH'] = str(prefix / 'usr/lib/x86_64-linux-gnu')
    env['CPATH'] = str(prefix / 'usr/include') + ':' + str(prefix / 'usr/include/x86_64-linux-gnu')
    env['GIT_EXEC_PATH'] = str(prefix / 'usr/lib/git-core')
    env['PYTHONPATH'] = str(prefix / 'usr/lib/python3/dist-packages')
    # Package resolution must use synchronized canonical dependencies only.
    # Fail closed if a future lock adds an unsynchronized source.
    env['GIT_ALLOW_PROTOCOL'] = ''
    temporary = work / 'tmp'
    temporary.mkdir(exist_ok=True)
    env['TMPDIR'] = str(temporary)
    for name in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS'):
        env.pop(name, None)
    return env


def repositories(root):
    selected = {name: root / name for name in REPOS}
    lock = json.loads((root / PROJECT / 'ziran.lock').read_text())
    for package in lock['packages']:
        if not package.get('source'):
            continue
        url = package['url']
        if not url.startswith('https://github.com/') or not url.endswith('.git'):
            raise RuntimeError('Source dependency needs a canonical GitHub directory: ' + url)
        name = url.removeprefix('https://github.com/').removesuffix('.git')
        if len(PurePosixPath(name).parts) != 2:
            raise RuntimeError('Invalid source dependency: ' + url)
        folder = root / name
        if not folder.is_dir():
            cache = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache')))
            folder = cache / 'ziran/sources' / package['id']
            if not folder.is_dir():
                raise RuntimeError('Dependency source is not available locally; no download attempted: ' + name)
            head = run(['git', '-C', folder, 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
            if head != package['commit']:
                raise RuntimeError('Existing dependency source does not match the lock: ' + name)
        selected[name] = folder
    return selected


def receive_git(root, repository, head):
    work, _, source = remote_state(root)
    if source['heads'].get(repository) != head:
        raise RuntimeError('Git metadata does not match the synchronized source receipt')
    folder = safe_path(root, repository)
    for part in ('.git', '.git/objects', '.git/refs', '.git/index', '.git/shallow'):
        safe_path(root, repository + '/' + part)
    env = environment(root)
    ledger = work / 'git-heads.json'
    old = json.loads(ledger.read_text()) if ledger.exists() else {}
    pending = work / ('git-pending-' + hashlib.sha256(repository.encode()).hexdigest() + '.json')
    if (folder / '.git').exists():
        result = subprocess.run(['git', '-C', str(folder), 'rev-parse', '--verify', 'HEAD'], env=env,
                                capture_output=True, text=True)
        observed = result.stdout.strip() if result.returncode == 0 else None
        branch = run(['git', '-C', folder, 'symbolic-ref', '--short', 'HEAD'], env=env,
                     capture_output=True, text=True).stdout.strip()
        ours_unborn = observed is None and pending.exists() and json.loads(pending.read_text()) == head
        if ((observed is None and not ours_unborn)
                or (observed is not None and observed not in (old.get(repository), head))
                or branch != 'master'):
            raise RuntimeError('Remote Git state changed; preserve/reconcile: ' + repository)
        if observed:
            run(['git', '-C', folder, 'diff', '--cached', '--quiet'], env=env)
    else:
        save_json(pending, head)
        run(['git', 'init', '--quiet', '--initial-branch=master', folder], env=env)
    run(['git', '-C', folder, 'unpack-objects', '-q'], env=env, stdin=sys.stdin.buffer)
    shallow = folder / '.git/shallow'
    boundaries = set(shallow.read_text().splitlines()) if shallow.exists() else set()
    shallow.write_text('\n'.join(sorted(boundaries | {head})) + '\n')
    run(['git', '-C', folder, 'update-ref', 'refs/heads/master', head], env=env)
    # Populate only the index; keep the synchronized dirty/untracked files.
    run(['git', '-C', folder, 'read-tree', head], env=env)
    old[repository] = head
    save_json(ledger, old)
    pending.unlink(missing_ok=True)
    print('Verified canonical Git HEAD:', repository, head, flush=True)


def setup(root):
    work, _, _ = remote_state(root)
    archives = work / 'debs'
    (archives / 'partial').mkdir(parents=True, exist_ok=True)
    # Debian's downloader resolves against installed packages, with no dpkg
    # transaction, sudo, maintainer scripts, or system configuration writes.
    run(['apt-get', '-y', '--download-only', '--no-install-recommends',
         '-o', 'Debug::NoLocking=1', '-o', 'Dir::Cache::archives=' + str(archives),
         'install', *PACKAGES], cwd=work)
    prefix = work / 'sysroot'
    prefix.mkdir(exist_ok=True)
    for package in sorted(archives.glob('*.deb')):
        run(['dpkg-deb', '--extract', package, prefix])
    # APT does not download runtime libraries already installed system-wide.
    # Development .so links in extracted packages still need those targets.
    for link in prefix.rglob('*.so*'):
        if link.is_symlink() and not link.exists() and not os.path.isabs(os.readlink(link)):
            target = link.resolve(strict=False)
            if target.is_relative_to(prefix) and not target.exists():
                system = Path('/') / target.relative_to(prefix)
                if system.is_file():
                    target.symlink_to(system)
    # Relocate only downloaded pkg-config metadata. System metadata retains
    # its ordinary paths; existing development packages remain usable.
    for pc in prefix.rglob('*.pc'):
        text = pc.read_text()
        pc.write_text(text.replace('=/usr', '=' + str(prefix / 'usr')))
    env = environment(root)
    run(['pkg-config', '--exists', 'sdl2', 'cairo', 'freetype2', 'fontconfig', 'pangocairo'], env=env)
    run(['python3', '-c', 'from PIL import Image'], env=env)
    print('User-local Debian prerequisites ready; no system packages installed.', flush=True)


def build(root, jobs):
    work, _, source = remote_state(root)
    if not source.get('content_sha256'):
        raise RuntimeError('Source sync is incomplete; rerun synchronization before building')
    env = environment(root)
    if not shutil.which('pkg-config', path=env['PATH']):
        raise RuntimeError('Missing prerequisites: run with --setup on Debian first')
    queue = Path.home() / '.local/bin/build-queue'
    if not queue.is_file():
        install_env = dict(env, YUE_INSTALL_PREFIX=str(Path.home() / '.local'))
        run(['python3', root / QUEUE / 'scripts/install-build-queue.py'], env=install_env)
    # Canonical relative overrides are portable between the two Projects roots.
    config = root / PROJECT / 'ziran.local.toml'
    base = '[overrides]\nkryon = "../../../kryonlabs/kryon"\nziran = "../../../ziranlang/ziran"\nmingcute = "../../../kryonlabs/packages/mingcute"\n'
    lock = json.loads((root / PROJECT / 'ziran.lock').read_text())
    wanted = base
    for package in lock['packages']:
        if package.get('source'):
            name = package['url'].removeprefix('https://github.com/').removesuffix('.git')
            if name not in source['heads']:
                raise RuntimeError('Source dependency was not synchronized: ' + name)
            wanted += package['name'] + ' = ' + json.dumps('../../../' + name) + '\n'
    generated = work / 'overrides.toml'
    allowed = {wanted, generated.read_text() if generated.exists() else base}
    if config.exists() and config.read_text() not in allowed:
        raise RuntimeError('Existing private ziran.local.toml differs; reconcile it before building')
    config.write_text(wanted)
    generated.write_text(wanted)
    toolchain = root / 'ziranlang/ziran'
    run([queue, '--', 'make', '-j' + str(jobs), 'BOOTSTRAP=1', 'all'], cwd=toolchain, env=env)
    compiler = toolchain / 'build/bin/ziran'
    flags = '-std=c11 -O0 -g -ffunction-sections -fdata-sections -I$(TOOLCHAIN)/include'
    binary = root / PROJECT / 'build/app/jungle'
    prior = work / 'build.json'
    # Rebuild a host produced outside this workflow with other compiler flags.
    force = []
    if binary.exists() and (not prior.exists() or json.loads(prior.read_text())['binary_sha256'] != digest(binary)):
        force = ['-W', 'host/desktop.zi']
    run([queue, '--', 'make', '-j' + str(jobs), 'ZIRAN=' + str(compiler),
         'CFLAGS_ZI=' + flags, 'CFLAGS=-O0 -g', *force, 'all'], cwd=root / PROJECT, env=env)
    linked = run(['ldd', binary], env=env, capture_output=True, text=True).stdout
    if 'not found' in linked:
        raise RuntimeError('Executable has unresolved libraries: ' + linked)
    sections = run(['readelf', '--sections', binary], capture_output=True, text=True).stdout
    if '.debug_info' not in sections:
        raise RuntimeError('Executable has no debug information')
    test_env = dict(env, JUNGLE_DATA=str(work / 'test-data'), SDL_AUDIODRIVER='dummy')
    run([queue, '--', binary, '--check'], cwd=binary.parent, env=test_env)
    for name, entry in source['files'].items():
        if digest(safe_path(root, name)) != entry['sha256']:
            raise RuntimeError('Source changed while building: ' + name)
    receipt = {'source_sha256': source['content_sha256'], 'binary_sha256': digest(binary),
               'binary': str(binary), 'built_at': time.time(), 'jobs': jobs,
               'heads': source['heads']}
    save_json(work / 'build.json', receipt)
    print('Built and verified:', json.dumps(receipt), flush=True)


def launch(root):
    work, _, source = remote_state(root)
    receipt = json.loads((work / 'build.json').read_text())
    binary = root / PROJECT / 'build/app/jungle'
    if receipt['source_sha256'] != source['content_sha256'] or receipt['binary_sha256'] != digest(binary):
        raise RuntimeError('Build receipt does not match current synced source/executable')
    env = environment(root)
    env['XDG_RUNTIME_DIR'] = '/run/user/' + str(os.getuid())
    env['DBUS_SESSION_BUS_ADDRESS'] = 'unix:path=' + env['XDG_RUNTIME_DIR'] + '/bus'
    output = run(['systemctl', '--user', 'show-environment'], capture_output=True, text=True, env=env).stdout
    display = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
    if not display.get('DISPLAY') and not display.get('WAYLAND_DISPLAY'):
        raise RuntimeError('Remote user has no graphical session in systemd environment')
    unit = 'jungle-current-' + str(time.time_ns())
    args = ['systemd-run', '--user', '--unit=' + unit,
            '--working-directory=' + str(binary.parent), '--collect']
    for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'XDG_RUNTIME_DIR'):
        if display.get(key):
            args.append('--setenv=' + key + '=' + display[key])
    args.append('--setenv=LD_LIBRARY_PATH=' + env['LD_LIBRARY_PATH'])
    run([*args, str(binary)], env=env)
    time.sleep(2)
    state = run(['systemctl', '--user', 'show', unit, '-p', 'MainPID', '-p', 'ActiveState'],
                env=env, capture_output=True, text=True).stdout
    props = dict(line.split('=', 1) for line in state.splitlines() if '=' in line)
    pid = int(props.get('MainPID', '0'))
    if props.get('ActiveState') != 'active' or not pid or Path('/proc', str(pid), 'exe').resolve() != binary:
        run(['journalctl', '--user', '-u', unit, '-n', '25', '--no-pager'], env=env)
        raise RuntimeError('Remote Jungle did not remain running')
    print('LIVE launch:', unit, 'PID', pid, 'executable', binary, flush=True)


def remote(host, action, stdin=None, capture=False, jobs=2, expected=None, repository=None, head=None):
    script = Path(__file__).read_text()
    command_args = ['python3', '-c', script, '--worker', action, '--jobs', str(jobs)]
    if expected:
        command_args += ['--expect-source', expected]
    if repository:
        command_args += ['--repository', repository, '--head', head]
    if action == 'build':
        command_args = ['systemd-run', '--user', '--scope', '--quiet',
                        '-p', 'MemoryMax=6G', '-p', 'MemorySwapMax=512M',
                        '-p', 'CPUQuota=200%', '-p', 'TasksMax=128', *command_args]
    command = shlex.join(command_args)
    args = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', host, command]
    if stdin == 'pipe':
        return subprocess.Popen(args, stdin=subprocess.PIPE)
    return run(args, capture_output=capture, text=capture)


def collect(root):
    files, heads = {}, {}
    for repo, folder in repositories(root).items():
        heads[repo] = run(['git', '-C', folder, 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
        names = run(['git', '-C', folder, 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
                    capture_output=True).stdout.split(b'\0')
        for raw in names:
            if not raw:
                continue
            name = os.fsdecode(raw)
            path = safe_path(folder, name)
            if path.is_file():
                files[repo + '/' + name] = {'sha256': digest(path), 'mode': path.stat().st_mode & 0o777}
    for name in QUEUE_FILES:
        path = root / QUEUE / 'scripts' / name
        files[QUEUE + '/scripts/' + name] = {'sha256': digest(path), 'mode': path.stat().st_mode & 0o777}
    content = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {'files': files, 'heads': heads, 'content_sha256': content}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='luna-laptop', help='Existing pinned SSH alias (default: luna-laptop)')
    parser.add_argument('--setup', action='store_true', help='Download/extract Debian prerequisites into project work/, no sudo')
    parser.add_argument('--launch', action='store_true', help='Launch after successful build in remote graphical session')
    parser.add_argument('--launch-only', action='store_true', help='Launch the last verified remote build without syncing')
    parser.add_argument('--sync-only', action='store_true')
    parser.add_argument('--jobs', type=int, choices=range(1, 5), default=2)
    parser.add_argument('--worker', choices=('inventory', 'receive', 'receive-git', 'setup', 'build', 'launch'), help=argparse.SUPPRESS)
    parser.add_argument('--expect-source', help=argparse.SUPPRESS)
    parser.add_argument('--repository', help=argparse.SUPPRESS)
    parser.add_argument('--head', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        root = Path.home() / 'Projects'
        work, _, _ = remote_state(root)
        with (work / 'operation.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            recover_pending(root)
            if args.expect_source and remote_state(root)[2].get('content_sha256') != args.expect_source:
                raise RuntimeError('Another sync replaced the requested source snapshot; rerun')
            if args.worker == 'build':
                build(root, args.jobs)
            elif args.worker == 'receive-git':
                receive_git(root, args.repository, args.head)
            else:
                globals()[args.worker](root)
        return
    if args.launch_only:
        remote(args.host, 'launch')
        return
    root = Path(__file__).resolve().parents[4]
    folders = repositories(root)
    proposal = collect(root)
    actual = json.loads(remote(args.host, 'inventory', capture=True).stdout)
    for name, entry in actual['recorded'].items():
        if actual['actual'].get(name) != entry['sha256']:
            raise RuntimeError('Remote edit detected; sync stopped: ' + name)
    changed = [name for name, entry in proposal['files'].items()
               if actual['actual'].get(name) != entry['sha256']
               or actual['recorded'].get(name, {}).get('mode') != entry['mode']]
    print('Syncing', len(changed), 'changed files; content', proposal['content_sha256'], flush=True)
    process = remote(args.host, 'receive', stdin='pipe')
    try:
        process.stdin.write((json.dumps(proposal) + '\n').encode())
        with tarfile.open(fileobj=process.stdin, mode='w|') as archive:
            for name in changed:
                path = root / name
                for repo, folder in folders.items():
                    if name.startswith(repo + '/'):
                        path = folder / name.removeprefix(repo + '/')
                        break
                archive.add(path, arcname=name, recursive=False)
        process.stdin.close()
    except BaseException:
        process.stdin.close()
        process.wait()
        raise
    if process.wait():
        raise RuntimeError('Remote source synchronization failed')
    current = collect(root)
    if current['content_sha256'] != proposal['content_sha256'] or current['heads'] != proposal['heads']:
        changed_names = [name for name in current['files'].keys() | proposal['files'].keys()
                         if current['files'].get(name) != proposal['files'].get(name)]
        raise RuntimeError('Desktop source changed during synchronization; rerun before building: '
                           + ', '.join(sorted(changed_names)[:10]))
    if args.setup:
        remote(args.host, 'setup')
    if not args.sync_only:
        # Import an exact shallow HEAD and its tree into each canonical Git
        # directory. No clone, checkout, copied .git directory, or network fetch.
        for repo, head in proposal['heads'].items():
            folder = folders[repo]
            previous = actual.get('git_heads', {}).get(repo)
            if previous == head:
                continue
            objects = [head + '^{tree}']
            if previous and subprocess.run(['git', '-C', str(folder), 'cat-file', '-e', previous + '^{tree}'],
                                           capture_output=True).returncode == 0:
                objects.append('^' + previous + '^{tree}')
            tree = run(['git', '-C', folder, 'rev-list', '--objects', '--no-object-names', *objects],
                       capture_output=True).stdout
            receiver = remote(args.host, 'receive-git', stdin='pipe', repository=repo, head=head,
                              expected=proposal['content_sha256'])
            pack = subprocess.Popen(['git', '-C', str(folder), '-c', 'pack.threads=1',
                                     'pack-objects', '--compression=1', '--stdout'],
                                    stdin=subprocess.PIPE, stdout=receiver.stdin)
            receiver.stdin.close()
            pack.communicate(head.encode() + b'\n' + tree)
            if pack.returncode or receiver.wait():
                raise RuntimeError('Canonical Git metadata synchronization failed: ' + repo)
        remote(args.host, 'build', jobs=args.jobs, expected=proposal['content_sha256'])
        if args.launch:
            remote(args.host, 'launch', expected=proposal['content_sha256'])


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print('remote-build:', error, file=sys.stderr)
        sys.exit(1)

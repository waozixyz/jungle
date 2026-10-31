#!/usr/bin/env python3
"""Share one candidate's compiled outputs between its gated CI jobs.

Archives contain regular files only. Restore verifies the entire archive in a
private staging directory before installing into otherwise absent output roots.
It never extracts archive paths directly into the checkout.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOTS = ("build/app", "build/stage", "build/tests", "build/tools", "build/ziran", "build/web")
WEB_ROOTS = ("build/web", "build/itch-web")
MANIFEST = "manifest.json"
MAX_MANIFEST = 16 * 1024 * 1024
MAX_FILES = 100000
MAX_BYTES = 16 * 1024**3
CHUNK = 1024 * 1024


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def identity(root, revision, toolchain=None):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("revision must be a full lowercase Git commit")
    if git(root, "rev-parse", "HEAD") != revision:
        raise ValueError("checkout is not the candidate revision")
    if git(root, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("tracked source changes cannot be shared")
    lock = json.loads((root / "ziran.lock").read_text())
    if toolchain is not None:
        if git(toolchain, "rev-parse", "HEAD") != lock["toolchain"]["commit"]:
            raise ValueError("toolchain does not match ziran.lock")
        if git(toolchain, "status", "--porcelain", "--untracked-files=no"):
            raise ValueError("tracked toolchain changes cannot be shared")
    return {"revision": revision, "lock_sha256": digest(root / "ziran.lock"),
            "version": (root / "VERSION").read_text().strip()}


def safe_path(name):
    if not isinstance(name, str) or len(name) > 1024 or not name or "\\" in name:
        raise ValueError("invalid archive path")
    path = PurePosixPath(name)
    if path.is_absolute() or str(path) != name or any(part in (".", "..") for part in path.parts):
        raise ValueError("non-canonical archive path")
    if any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ValueError("control character in archive path")
    return name


def allowed(kind, area, name):
    safe_path(name)
    if area == "project":
        roots = PROJECT_ROOTS if kind == "build" else WEB_ROOTS
        return any(name.startswith(prefix + "/") for prefix in roots)
    if area == "toolchain" and kind == "build":
        return name.startswith("build/bin/") or bool(re.fullmatch(r"build/[A-Za-z0-9_.-]+\.a", name))
    return False


def no_links(path, base):
    """Check parents too: a regular leaf behind a symlink is unsafe."""
    relative = path.relative_to(base)
    if relative.parts:
        safe_path(relative.as_posix())
    current = base
    if current.is_symlink():
        raise ValueError("output base is a symlink")
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"symlink in output path: {current}")


def collect(root, toolchain, kind):
    result = []
    sources = [("project", root, prefix) for prefix in (PROJECT_ROOTS if kind == "build" else WEB_ROOTS)]
    if kind == "build":
        sources.append(("toolchain", toolchain, "build/bin"))
        sources += [("toolchain", toolchain, str(path.relative_to(toolchain)))
                    for path in sorted((toolchain / "build").glob("*.a"))]
    for area, base, prefix in sources:
        target = base / prefix
        no_links(target, base)
        if not target.exists():
            continue
        paths = sorted(target.rglob("*")) if target.is_dir() else [target]
        for path in paths:
            no_links(path, base)
            if path.is_dir():
                continue
            info = path.stat()
            name = path.relative_to(base).as_posix()
            if not stat.S_ISREG(info.st_mode) or not allowed(kind, area, name):
                raise ValueError(f"unsupported output file: {path}")
            result.append(({"area": area, "path": name, "size": info.st_size,
                            "mode": 0o755 if info.st_mode & 0o111 else 0o644,
                            "sha256": digest(path)}, path))
    return result


def check_entries(kind, entries):
    if not isinstance(entries, list) or not entries or len(entries) > MAX_FILES:
        raise ValueError("invalid file count")
    names, total = set(), 0
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"area", "path", "size", "mode", "sha256"}:
            raise ValueError("invalid file record")
        area, name = entry["area"], entry["path"]
        if not allowed(kind, area, name):
            raise ValueError("output outside the fixed roots")
        key = area + "/" + name
        if key in names:
            raise ValueError("duplicate output")
        names.add(key)
        if type(entry["size"]) is not int or entry["size"] < 0:
            raise ValueError("invalid output size")
        total += entry["size"]
        if total > MAX_BYTES or entry["mode"] not in (0o644, 0o755):
            raise ValueError("invalid output size or permissions")
        if not isinstance(entry["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise ValueError("invalid output digest")
    required = {"project/build/web/version.json", "project/build/web/index.html"}
    if kind == "build":
        required |= {"project/build/app/jungle", "toolchain/build/bin/ziran", "toolchain/build/libziran.a"}
    else:
        required |= {"project/build/itch-web/version.json", "project/build/itch-web/index.html"}
    if not required <= names:
        raise ValueError("required compiled outputs missing")
    # A file can never also be a parent directory of another file.
    for name in names:
        if any(parent.as_posix() in names for parent in PurePosixPath(name).parents):
            raise ValueError("file/directory collision")


def check_versions(base, kind, expected):
    for prefix in (WEB_ROOTS if kind == "web" else ("build/web",)):
        path = base / "project" / prefix / "version.json"
        if path.stat().st_size > 65536:
            raise ValueError("oversized version record")
        version = json.loads(path.read_text())
        if version.get("revision") != expected["revision"] or version.get("version") != expected["version"]:
            raise ValueError("website version does not match candidate")


def pack(root, toolchain, kind, revision, output):
    output = output if output.is_absolute() else root / output
    expected = identity(root, revision, toolchain if kind == "build" else None)
    files = collect(root, toolchain, kind)
    check_entries(kind, [entry for entry, _ in files])
    # Validate the actual metadata without making copies of the app payload.
    for prefix in (WEB_ROOTS if kind == "web" else ("build/web",)):
        path = root / prefix / "version.json"
        if path.stat().st_size > 65536:
            raise ValueError("oversized version record")
        version = json.loads(path.read_text())
        if any(version.get(key) != expected[key] for key in ("revision", "version")):
            raise ValueError("website version does not match candidate")
    payload = json.dumps({"format": 1, "kind": kind, **expected,
                          "files": [entry for entry, _ in files]}, sort_keys=True).encode()
    if len(payload) > MAX_MANIFEST:
        raise ValueError("manifest too large")
    no_links(output, root)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.is_symlink():
        raise ValueError("archive destination already exists")
    scratch = root / "work/ci-artifacts"
    no_links(scratch, root)
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as temporary:
        archive = Path(temporary) / "outputs.tar.gz"
        with tarfile.open(archive, "w:gz", compresslevel=1, format=tarfile.GNU_FORMAT) as tar:
            header = tarfile.TarInfo(MANIFEST)
            header.size, header.mode = len(payload), 0o644
            tar.addfile(header, io.BytesIO(payload))
            for entry, path in files:
                header = tarfile.TarInfo(entry["area"] + "/" + entry["path"])
                header.size, header.mode = entry["size"], entry["mode"]
                with path.open("rb") as stream:
                    tar.addfile(header, stream)
                if digest(path) != entry["sha256"]:
                    raise ValueError("output changed while packing")
        # A final source check protects against concurrent edits during packing.
        if identity(root, revision, toolchain if kind == "build" else None) != expected:
            raise ValueError("source changed while packing")
        os.replace(archive, output)


def restore(root, toolchain, kind, revision, archive):
    archive = archive if archive.is_absolute() else root / archive
    expected = identity(root, revision, toolchain if kind == "build" else None)
    scratch = root / "work/ci-artifacts"
    no_links(scratch, root)
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as temporary:
        staged = Path(temporary)
        with tarfile.open(archive, "r|gz") as tar:
            first = tar.next()
            if (first is None or first.name != MANIFEST or not first.isfile() or first.pax_headers or
                    not 0 < first.size <= MAX_MANIFEST):
                raise ValueError("archive must start with a bounded manifest")
            manifest = json.load(tar.extractfile(first))
            if (not isinstance(manifest, dict) or
                    set(manifest) != {"format", "kind", "revision", "version", "lock_sha256", "files"} or
                    manifest["format"] != 1 or manifest["kind"] != kind or
                    any(manifest[key] != value for key, value in expected.items())):
                raise ValueError("archive candidate or lock differs from checkout")
            entries = manifest["files"]
            check_entries(kind, entries)
            for entry in entries:
                member = tar.next()
                name = entry["area"] + "/" + entry["path"]
                if (member is None or member.name != name or not member.isfile() or
                        member.size != entry["size"] or member.mode != entry["mode"] or member.pax_headers):
                    raise ValueError("archive member differs from manifest")
                destination = staged / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                hasher = hashlib.sha256()
                with tar.extractfile(member) as source, destination.open("xb") as target:
                    while block := source.read(CHUNK):
                        hasher.update(block)
                        target.write(block)
                if hasher.hexdigest() != entry["sha256"]:
                    raise ValueError("archive file digest mismatch")
                destination.chmod(entry["mode"])
            if tar.next() is not None:
                raise ValueError("unexpected archive member")
        check_versions(staged, kind, expected)
        targets = []
        for area, base, prefixes in (("project", root, PROJECT_ROOTS if kind == "build" else WEB_ROOTS),
                                     ("toolchain", toolchain, ("build/bin", "build/libziran.a") if kind == "build" else ())):
            if kind == "build" and area == "toolchain":
                prefixes = ("build/bin", *sorted({entry["path"] for entry in entries
                                                  if entry["area"] == area and not entry["path"].startswith("build/bin/")}))
            for prefix in prefixes:
                source = staged / area / prefix
                if not source.exists():
                    continue
                destination = base / prefix
                no_links(destination, base)
                if destination.exists():
                    raise ValueError(f"refusing to replace existing output: {destination}")
                targets.append((source, destination))
        # Validation, including collision checks, completes before output changes.
        if identity(root, revision, toolchain if kind == "build" else None) != expected:
            raise ValueError("source changed while restoring")
        now = time.time_ns()
        for entry in entries:
            os.utime(staged / entry["area"] / entry["path"], ns=(now, now))
        installed = []
        try:
            for source, destination in targets:
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.rename(source, destination)
                installed.append((source, destination))
        except BaseException:
            for source, destination in reversed(installed):
                os.rename(destination, source)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("pack", "restore"))
    parser.add_argument("--kind", choices=("build", "web"), required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--toolchain", type=Path,
                        default=Path(os.environ.get("ZIRAN_ROOT", ROOT.parents[2] / "ziranlang/ziran")))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    if args.action == "pack" and args.output and not args.archive:
        pack(ROOT, args.toolchain, args.kind, args.revision, args.output)
    elif args.action == "restore" and args.archive and not args.output:
        restore(ROOT, args.toolchain, args.kind, args.revision, args.archive)
    else:
        parser.error("pack needs --output; restore needs --archive")
    print(f"Verified {args.kind} artifact {args.action} for {args.revision}")


if __name__ == "__main__":
    main()

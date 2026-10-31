"""Archive round trips and hostile-input controls; no compiler or app runs."""
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import ci_artifacts as ci

REVISION = "a" * 40
IDENTITY = {"revision": REVISION, "version": "0.1.32", "lock_sha256": "b" * 64}


class Artifacts(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "work/ci-artifact-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source, self.compiler = self.base / "source", self.base / "compiler"
        self.destination, self.restore_compiler = self.base / "destination", self.base / "restore-compiler"
        for path in (self.source, self.compiler, self.destination, self.restore_compiler):
            path.mkdir()
        self.identity = patch.object(ci, "identity", return_value=IDENTITY.copy())
        self.identity.start()
        self.addCleanup(self.identity.stop)
        self.archive = self.source / "work/build.tar.gz"
        for root, name, content in (
            (self.source, "build/app/jungle", b"fake compiled app"),
            (self.source, "build/app/games/test.zx", b"fake bundle"),
            (self.source, "build/stage/.shared-assets", b""),
            (self.source, "build/tests/test", b"fake test"),
            (self.source, "build/web/index.html", b"fake website"),
            (self.source, "build/itch-web/index.html", b"fake embed"),
            (self.compiler, "build/bin/ziran", b"fake compiler"),
            (self.compiler, "build/libziran.a", b"fake runtime"),
        ):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        (self.source / "build/app/jungle").chmod(0o755)
        (self.compiler / "build/bin/ziran").chmod(0o755)
        for prefix in ci.WEB_ROOTS:
            (self.source / prefix / "version.json").write_text(json.dumps(IDENTITY))

    def pack(self, kind="build"):
        ci.pack(self.source, self.compiler, kind, REVISION, self.archive)

    def restore(self, kind="build"):
        ci.restore(self.destination, self.restore_compiler, kind, REVISION, self.archive)

    def rewrite(self, mutate):
        """Small fake fixture archives only; production code always streams."""
        with tarfile.open(self.archive, "r:gz") as tar:
            members = [(member, tar.extractfile(member).read()) for member in tar]
        members = mutate(members)
        self.archive.unlink()
        with tarfile.open(self.archive, "w:gz") as tar:
            for member, data in members:
                member.size = len(data)
                tar.addfile(member, io.BytesIO(data))

    def untouched(self):
        self.assertFalse((self.destination / "build").exists())
        self.assertFalse((self.restore_compiler / "build").exists())

    def test_build_roundtrip_exec_permissions_and_fresh_mtimes(self):
        self.pack()
        before = time.time_ns()
        self.restore()
        self.assertEqual((self.destination / "build/app/jungle").read_bytes(), b"fake compiled app")
        self.assertEqual((self.restore_compiler / "build/bin/ziran").stat().st_mode & 0o777, 0o755)
        self.assertEqual((self.destination / "build/web/index.html").stat().st_mode & 0o777, 0o644)
        self.assertGreaterEqual((self.destination / "build/stage/.shared-assets").stat().st_mtime_ns, before)
        self.assertFalse((self.destination / "build/itch-web").exists())

    def test_web_roundtrip_never_restores_compiler_or_native_outputs(self):
        self.pack("web")
        self.restore("web")
        self.assertTrue((self.destination / "build/itch-web/index.html").is_file())
        self.assertFalse((self.destination / "build/app").exists())
        self.assertFalse((self.restore_compiler / "build").exists())

    def test_corrupt_blob_does_not_mutate_outputs(self):
        self.pack()
        def corrupt(members):
            member, data = members[1]
            members[1] = member, b"X" + data[1:]
            return members
        self.rewrite(corrupt)
        with self.assertRaisesRegex(ValueError, "digest"):
            self.restore()
        self.untouched()

    def test_wrong_revision_lock_or_kind_do_not_mutate_outputs(self):
        for key, value in (("revision", "c" * 40), ("lock_sha256", "c" * 64), ("kind", "web")):
            with self.subTest(key=key):
                self.archive.unlink(missing_ok=True)
                self.pack()
                def modify(members):
                    header, data = members[0]
                    manifest = json.loads(data)
                    manifest[key] = value
                    members[0] = header, json.dumps(manifest).encode()
                    return members
                self.rewrite(modify)
                with self.assertRaisesRegex(ValueError, "candidate or lock"):
                    self.restore()
                self.untouched()

    def test_unsafe_and_unknown_manifest_paths_fail_before_writes(self):
        for name in ("../../escape", "/absolute", "build/app/../escape", "build/app\\escape",
                     "build/app/evil\nname", "build/unowned/file"):
            with self.subTest(name=name):
                self.archive.unlink(missing_ok=True)
                self.pack()
                def modify(members):
                    header, data = members[0]
                    manifest = json.loads(data)
                    manifest["files"][0]["path"] = name
                    members[0] = header, json.dumps(manifest).encode()
                    return members
                self.rewrite(modify)
                with self.assertRaises(ValueError):
                    self.restore()
                self.untouched()

    def test_duplicate_and_link_members_are_rejected(self):
        self.pack()
        self.rewrite(lambda members: members + [members[1]])
        with self.assertRaisesRegex(ValueError, "unexpected"):
            self.restore()
        self.untouched()
        self.archive.unlink()
        self.pack()
        def link(members):
            members[1][0].type = tarfile.SYMTYPE
            members[1][0].linkname = "/outside"
            return members
        self.rewrite(link)
        with self.assertRaises(ValueError):
            self.restore()
        self.untouched()

    def test_existing_target_canary_is_preserved_and_nothing_else_installs(self):
        self.pack()
        target = self.restore_compiler / "build/bin"
        target.mkdir(parents=True)
        (target / "owner-canary").write_text("preserve")
        with self.assertRaisesRegex(ValueError, "existing output"):
            self.restore()
        self.assertEqual((target / "owner-canary").read_text(), "preserve")
        self.assertFalse((self.destination / "build").exists())

    def test_symlink_output_parent_is_rejected(self):
        self.pack()
        outside = self.base / "outside"
        outside.mkdir()
        (self.destination / "build").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.restore()
        self.assertEqual(list(outside.iterdir()), [])

    def test_pack_refuses_symlink_and_stale_website(self):
        target = self.source / "build/app/link"
        target.symlink_to(self.source / "build/app/jungle")
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.pack()
        target.unlink()
        (self.source / "build/web/version.json").write_text('{"revision":"old"}')
        with self.assertRaisesRegex(ValueError, "version"):
            self.pack()
        self.assertFalse(self.archive.exists())

    def test_streaming_roundtrip_large_file(self):
        path = self.source / "build/app/large"
        with path.open("wb") as stream:
            for _ in range(5):
                stream.write(b"s" * ci.CHUNK)
        self.pack()
        self.restore()
        self.assertEqual(ci.digest(path), ci.digest(self.destination / "build/app/large"))

    def test_long_filename_roundtrip(self):
        name = "build/tests/generated/" + "module_" * 30 + ".c"
        path = self.source / name
        path.parent.mkdir(parents=True)
        path.write_text("fake generated output")
        self.pack()
        self.restore()
        self.assertEqual((self.destination / name).read_text(), path.read_text())

    def test_duplicate_manifest_and_excessive_sizes_fail_before_writes(self):
        for change in ("duplicate", "size", "permissions", "digest"):
            with self.subTest(change=change):
                self.archive.unlink(missing_ok=True)
                self.pack()
                def modify(members):
                    header, data = members[0]
                    manifest = json.loads(data)
                    if change == "duplicate":
                        manifest["files"].append(manifest["files"][0])
                    elif change == "size":
                        manifest["files"][0]["size"] = ci.MAX_BYTES + 1
                    elif change == "permissions":
                        manifest["files"][0]["mode"] = 0o4755
                    else:
                        manifest["files"][0]["sha256"] = "not a digest"
                    members[0] = header, json.dumps(manifest).encode()
                    return members
                self.rewrite(modify)
                with self.assertRaises(ValueError):
                    self.restore()
                self.untouched()

    def test_source_identity_requires_exact_clean_commit(self):
        self.identity.stop()
        (self.source / "VERSION").write_text(IDENTITY["version"])
        (self.source / "ziran.lock").write_text(json.dumps({"toolchain": {"commit": REVISION}}))
        with patch.object(ci, "git", side_effect=[REVISION, "", REVISION, ""]):
            self.assertEqual(ci.identity(self.source, REVISION, self.compiler)["revision"], REVISION)
        with patch.object(ci, "git", return_value="c" * 40):
            with self.assertRaisesRegex(ValueError, "candidate"):
                ci.identity(self.source, REVISION)
        with patch.object(ci, "git", side_effect=[REVISION, " M tracked-file"]):
            with self.assertRaisesRegex(ValueError, "tracked source"):
                ci.identity(self.source, REVISION)


if __name__ == "__main__":
    unittest.main()

"""Orchestration tests for tools/run_ci_validation.py; fake commands only, no app or browser."""
import collections
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import run_ci_validation as rcv  # noqa: E402

try:
    import yaml
except ImportError:  # GitHub's runner image ships PyYAML; local runs may not.
    yaml = None

# The browser gates exactly as the workflow ran them before the runner.
OLD_BROWSER_GATES = [
    "JUNGLE_WEB_PAGE=dom.html node tests/book_browser_interaction_test.mjs",
    "JUNGLE_WEB_PAGE=canvas.html node tests/book_browser_interaction_test.mjs",
    "python3 tests/book_shelf_test.py",
    *[f"JUNGLE_TEST_LANG={lang} JUNGLE_WEB_PAGE={page} node tests/new_activities_web_test.mjs"
      for page in ("dom.html", "canvas.html") for lang in ("en", "de", "es")],
    "python3 tests/speech_playback_test.py",
    "node tests/asset_packs_test.mjs",
    "python3 tests/web_images_test.py",
    "python3 tools/prepare_itch.py",
    "python3 tools/test_itch_web.py",
    "JUNGLE_WEB_PAGE=canvas.html node tests/jigsaw_web_test.mjs",
    "JUNGLE_WEB_PAGE=dom.html node tests/jigsaw_web_test.mjs",
    "JUNGLE_WEB_PAGE=canvas.html node tests/piano_web_test.mjs",
    "JUNGLE_WEB_PAGE=dom.html node tests/piano_web_test.mjs",
    "JUNGLE_WEB_PAGE=canvas.html node tests/paint_layers_web_test.mjs",
    "JUNGLE_WEB_PAGE=dom.html node tests/paint_layers_web_test.mjs",
    "JUNGLE_WEB_PAGE=canvas.html node tests/web_test.mjs",
    "JUNGLE_WEB_PAGE=dom.html node tests/web_test.mjs",
    "node tests/dom_native_web_test.mjs",
    "python3 tools/measure_web.py",
]


def groups_of(*specs):
    return tuple(rcv.Group(name, tuple(rcv.Step(("fake", name, str(i))) for i in range(count)))
                 for name, count in specs)


class Schedule(unittest.TestCase):
    def setUp(self):
        self.prerequisites, self.recipe = rcv.test_ui_recipe((ROOT / "Makefile").read_text())
        self.groups = rcv.schedule()

    def test_covers_the_complete_makefile_test_ui_recipe(self):
        self.assertEqual(self.prerequisites, ["all"])
        self.assertGreater(len(self.recipe), 20)
        self.assertEqual(rcv.coverage_problems(self.groups, self.recipe, rcv.book_languages()), [])

    def test_a_new_or_removed_test_ui_line_is_reported(self):
        languages = rcv.book_languages()
        added = rcv.coverage_problems(self.groups, self.recipe + ["python3 tests/future_ui_test.py"], languages)
        self.assertEqual(added, ["test-ui line not scheduled: python3 tests/future_ui_test.py"])
        removed = rcv.coverage_problems(self.groups, self.recipe[1:], languages)
        self.assertEqual(removed, [f"scheduled line not in test-ui: {self.recipe[0]}"])
        with self.assertRaises(ValueError):
            rcv.test_ui_recipe("test-ui: all\n\t-python3 tests/x.py\n")
        with self.assertRaises(ValueError):
            rcv.test_ui_recipe("test-ui: all\n\tpython3 $(X)\n")

    def test_book_runs_once_per_language_and_otherwise_matches_its_recipe(self):
        books = [step.argv for group in self.groups for step in group.steps if step.recipe == rcv.BOOK_RECIPE]
        self.assertEqual(books, [("python3", "tests/book_ui_test.py", "--language", lang) for lang in ("en", "de", "es")])
        self.assertEqual(rcv.book_languages(), ("en", "de", "es"))
        missing = rcv.coverage_problems(self.groups, self.recipe, ("en", "de", "es", "fr"))
        self.assertTrue(any("Book languages" in problem for problem in missing))
        doubled = self.groups + (rcv.Group("again", (rcv.book("de"),)),)
        self.assertTrue(rcv.coverage_problems(doubled, self.recipe, rcv.book_languages()))

    def test_browser_gates_are_partitioned_with_nothing_lost(self):
        by_name = {group.name: group for group in self.groups}
        packaging = rcv.packaging_group()
        browser = [step.label() for step in by_name["browser"].steps]
        moved = ["python3 tools/prepare_itch.py", "python3 tools/test_itch_web.py", "python3 tools/measure_web.py"]
        self.assertEqual(collections.Counter(browser + moved), collections.Counter(OLD_BROWSER_GATES))
        painting = [gate for gate in OLD_BROWSER_GATES if "tests/paint_layers_web_test.mjs" in gate]
        self.assertEqual(browser, painting + [gate for gate in OLD_BROWSER_GATES if gate not in painting + moved])
        self.assertEqual([step.label() for step in by_name["performance"].steps], moved[2:])
        self.assertEqual([step.label() for step in packaging.steps], moved[:2])
        self.assertEqual(by_name["browser"].tmpdir, "work/b")
        short = {by_name["browser"].tmpdir, by_name["performance"].tmpdir, packaging.tmpdir}
        self.assertEqual(len(short), 3, "groups that may overlap never share a browser scratch folder")
        self.assertTrue(all(len(folder) <= len("work/b") for folder in short))
        others = [step for group in self.groups if group.name not in ("browser", "performance") for step in group.steps]
        self.assertTrue(all(step.recipe for step in others), "other groups run only test-ui lines")

    def test_hide_seek_is_its_own_group_and_covered_once(self):
        by_name = {group.name: group for group in self.groups}
        self.assertEqual([step.recipe for step in by_name["hide-seek"].steps], ["python3 tests/hide_seek_levels_test.py"])
        self.assertNotIn("tests/hide_seek_levels_test.py", [step.argv[1] for step in by_name["activities"].steps])

    def test_every_group_is_on_exactly_one_lane(self):
        packaging = rcv.packaging_group()
        self.assertEqual(rcv.plan_problems(self.groups, packaging), [])
        self.assertEqual(rcv.coverage_problems((*self.groups, packaging), self.recipe, rcv.book_languages()), [])
        self.assertEqual(len(rcv.CI_LANES), 4)
        lanes = [("a", ("browser", "browser"))] + list(rcv.CI_LANES[1:])
        self.assertIn("CI lane group not in the schedule or repeated: browser", rcv.plan_problems(self.groups, packaging, lanes))
        self.assertIn("group on no CI lane: browser", rcv.plan_problems(self.groups, packaging, rcv.CI_LANES[1:]))
        on_lane = [("a", ("browser", rcv.PACKAGING))] + list(rcv.CI_LANES[1:])
        self.assertIn(f"CI lane group not in the schedule or repeated: {rcv.PACKAGING}",
                      rcv.plan_problems(self.groups, packaging, on_lane))

    def test_a_lost_or_reordered_browser_gate_is_reported(self):
        packaging = rcv.packaging_group()
        fewer = tuple(group for group in self.groups if group.name != "performance")
        self.assertIn("browser gate not scheduled: python3 tools/measure_web.py", rcv.plan_problems(fewer, packaging))
        reordered = rcv.Group(rcv.PACKAGING, tuple(reversed(packaging.steps)))
        self.assertTrue(any("prepare the embed package" in problem for problem in rcv.plan_problems(self.groups, reordered)))

    def test_paint_group_starts_first(self):
        first = self.groups[0]
        self.assertEqual(first.name, "paint")
        self.assertEqual([step.argv[1] for step in first.steps],
                         ["tests/slot_preview_test.py", "tests/paint_layers_test.py", "tests/paint_history_test.py",
                          "tests/paint_library_test.py", "tests/language_ui_test.py"])

    def test_no_scheduled_script_hardcodes_the_shared_capture_folder(self):
        scripts = {step.argv[1] for group in self.groups for step in group.steps if step.argv[0] == "python3"}
        for script in sorted(scripts):
            text = (ROOT / script).read_text()
            if script == "tests/runtime_test.py":
                text = text.replace('ROOT / "build/tests/ui")', "", 1)
            self.assertNotIn("build/tests/ui", text, script)


class BookFilter(unittest.TestCase):
    def test_selected_languages_keeps_the_real_menu_index(self):
        sys.path.insert(0, str(ROOT / "tests"))
        import book_ui_test
        self.assertEqual(book_ui_test.selected_languages(), [(0, "en"), (1, "de"), (2, "es")])
        self.assertEqual(book_ui_test.selected_languages("de"), [(1, "de")])
        self.assertEqual(book_ui_test.selected_languages("es"), [(2, "es")])
        with self.assertRaises(ValueError):
            book_ui_test.selected_languages("fr")

    def test_invalid_language_is_rejected_before_any_desktop_starts(self):
        result = subprocess.run([sys.executable, "tests/book_ui_test.py", "--language", "fr"], cwd=ROOT,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)
        self.assertNotIn("private Xvfb", result.stdout)


class FakeLaunch:
    def __init__(self, fail=(), delay=0.02):
        self.fail, self.delay = set(fail), delay
        self.lock = threading.Lock()
        self.active = self.peak = 0
        self.ran = []

    def __call__(self, group, step):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.ran.append(step.argv)
        try:
            time.sleep(self.delay)
            return 1 if step.argv in self.fail else 0
        finally:
            with self.lock:
                self.active -= 1


class Scheduler(unittest.TestCase):
    def run_groups(self, groups, launch, **options):
        output = io.StringIO()
        code = rcv.RunCIValidation(groups, launch, console=rcv.Console(output), **options)
        return code, output.getvalue()

    def test_every_step_runs_with_at_most_two_at_once(self):
        groups = groups_of(("a", 3), ("b", 1), ("c", 4), ("d", 2), ("e", 1))
        launch = FakeLaunch()
        code, output = self.run_groups(groups, launch)
        self.assertEqual(code, 0)
        self.assertEqual(launch.peak, 2)
        self.assertEqual(collections.Counter(launch.ran),
                         collections.Counter(step.argv for group in groups for step in group.steps))
        for group in groups:  # each group's steps keep their order
            self.assertEqual([argv for argv in launch.ran if argv[1] == group.name],
                             [step.argv for step in group.steps])
        self.assertIn("CI validation passed", output)
        with self.assertRaises(ValueError):
            rcv.RunCIValidation(groups, launch, max_workers=3)

    def test_the_real_schedule_never_exceeds_two(self):
        launch = FakeLaunch(delay=0.001)
        code, _ = self.run_groups(rcv.schedule(), launch)
        self.assertEqual(code, 0)
        self.assertEqual(launch.peak, 2)
        self.assertEqual(len(launch.ran), sum(len(group.steps) for group in rcv.schedule()))

    def test_a_failure_lets_running_commands_finish_and_starts_nothing_new(self):
        release = threading.Event()
        finished = []

        def launch(group, step):
            if step.argv == ("fake", "slow", "0"):
                release.wait(5)
                finished.append(step.argv)
                return 0
            if step.argv == ("fake", "bad", "0"):
                release.set()
                return 3
            return 0

        groups = groups_of(("slow", 2), ("bad", 2), ("later", 1))
        code, output = self.run_groups(groups, launch)
        self.assertEqual(code, 1)
        self.assertEqual(finished, [("fake", "slow", "0")])
        self.assertIn("::error title=CI validation bad::exit 3", output)
        self.assertIn("CI validation slow: stopped", output)
        self.assertIn("CI validation later: not started", output)
        self.assertNotIn("start: fake bad 1", output)
        self.assertNotIn("start: fake slow 1", output)

    def test_a_launch_error_fails_the_run(self):
        def launch(group, step):
            raise FileNotFoundError("node")
        code, output = self.run_groups(groups_of(("a", 1)), launch)
        self.assertEqual(code, 1)
        self.assertIn("could not run", output)

    def test_only_full_success_is_success(self):
        self.assertEqual(self.run_groups(groups_of(("a", 1), ("b", 1)), FakeLaunch(fail={("fake", "b", "0")}))[0], 1)
        self.assertEqual(self.run_groups(groups_of(("a", 2), ("b", 1)), FakeLaunch())[0], 0)


class FrozenRun(unittest.TestCase):
    """--group's run: a restored app must be reused, and packaging must have its benchmark."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.app, self.web = self.root / "app", self.root / "web"
        (self.app / "games").mkdir(parents=True)
        (self.app / "jungle").write_text("one")
        self.web.mkdir()
        self.prepare = rcv.Group("prepare", (rcv.Step(("make", "all")),))

    def tearDown(self):
        self.temporary.cleanup()

    def run_frozen(self, stages, launch, **options):
        output = io.StringIO()
        code = rcv.RunFrozen(stages, launch, console=rcv.Console(output), prepare=self.prepare,
                             app=self.app, web=self.web, **options)
        return code, output.getvalue()

    def rebuild(self):
        replacement = self.app / "jungle.new"
        replacement.write_text("two")
        replacement.replace(self.app / "jungle")

    def test_one_group_runs_after_the_prepare_in_order(self):
        launch = FakeLaunch()
        groups = groups_of(("a", 2))
        code, _ = self.run_frozen(((groups, 1),), launch, restored=True)
        self.assertEqual(code, 0)
        self.assertEqual(launch.ran, [("make", "all"), ("fake", "a", "0"), ("fake", "a", "1")])

    def test_a_missing_restored_build_runs_nothing(self):
        (self.app / "jungle").unlink()
        launch = FakeLaunch()
        code, output = self.run_frozen((((), 1),), launch, restored=True)
        self.assertEqual((code, launch.ran), (1, []))
        self.assertIn("no restored build", output)

    def test_a_rebuild_during_prepare_fails_only_a_restored_run(self):
        ran = []

        def launch(group, step):
            ran.append(step.argv)
            if group.name == "prepare":
                self.rebuild()
            return 0
        groups = groups_of(("a", 1))
        code, output = self.run_frozen(((groups, 1),), launch, restored=True)
        self.assertEqual((code, ran), (1, [("make", "all")]))
        self.assertIn("rebuilt, not reused", output)
        self.assertEqual(self.run_frozen(((groups, 1),), launch)[0], 0)

    def test_a_rebuild_during_a_group_fails(self):
        def launch(group, step):
            if group.name != "prepare":
                self.rebuild()
            return 0
        code, output = self.run_frozen(((groups_of(("a", 1)), 1),), launch, restored=True)
        self.assertEqual(code, 1)
        self.assertIn("changed while tests ran", output)

    def test_a_failed_stage_stops_later_stages(self):
        first, second = groups_of(("a", 1)), groups_of(("b", 1))
        launch = FakeLaunch(fail={("fake", "a", "0")})
        code, _ = self.run_frozen(((first, 2), (second, 1)), launch)
        self.assertEqual(code, 1)
        self.assertNotIn(("fake", "b", "0"), launch.ran)

    def test_packaging_never_runs_without_this_builds_benchmark(self):
        write_build(self.web)
        launch = FakeLaunch()
        packaging = rcv.packaging_group()
        code, output = self.run_frozen((((packaging,), 1),), launch, restored=True)
        self.assertEqual((code, launch.ran), (1, [("make", "all")]))
        self.assertIn("packaging needs this build's benchmark", output)
        overlay = self.root / "overlay"
        write_overlay(overlay, self.web)
        rcv.apply_performance_overlay(overlay, self.web, REVISION)
        launch = FakeLaunch()
        self.assertEqual(self.run_frozen((((packaging,), 1),), launch, restored=True)[0], 0)
        self.assertEqual(launch.ran, [("make", "all"), *rcv.ITCH_STEPS])

    def test_running_one_group_keeps_other_groups_results(self):
        work = self.root / "work"
        (work / "paint/ui").mkdir(parents=True)
        (work / "paint/ui/capture.png").write_text("kept")
        (work / "paint.log").write_text("kept")
        (work / "performance/ui").mkdir(parents=True)
        (work / "performance/ui/old.png").write_text("stale")
        (work / "performance.log").write_text("stale")
        rcv.clear_group(rcv.Group("performance", ()), work)
        self.assertEqual((work / "paint/ui/capture.png").read_text(), "kept")
        self.assertEqual((work / "paint.log").read_text(), "kept")
        self.assertFalse((work / "performance").exists())
        self.assertFalse((work / "performance.log").exists())


REVISION = "a" * 40


def write_build(web, revision=REVISION):
    web.mkdir(parents=True, exist_ok=True)
    (web / "version.json").write_text(json.dumps({"version": "0.1.31", "revision": revision}))
    for name in ("canvas.html", "dom.html", "jungle.js", "jungle-dom.js", "jungle.wasm", "jungle-dom.wasm"):
        (web / name).write_text(name)


def write_overlay(folder, web):
    import measure_web
    folder.mkdir(parents=True, exist_ok=True)
    payload = {"build": json.loads((web / "version.json").read_text()),
               "build_artifacts_sha256": measure_web.fingerprints(web)}
    (folder / "performance.json").write_text(json.dumps(payload))
    (folder / "performance.html").write_text("benchmark page")
    (folder / "performance-report.md").write_text("benchmark report")


class PerformanceOverlay(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.web, self.overlay = self.root / "web", self.root / "overlay"
        write_build(self.web)
        write_overlay(self.overlay, self.web)
        self.before = sorted(path.name for path in self.web.iterdir())

    def tearDown(self):
        self.temporary.cleanup()

    def assert_refused(self, message, revision=REVISION):
        with self.assertRaisesRegex(ValueError, message):
            rcv.apply_performance_overlay(self.overlay, self.web, revision)
        self.assertEqual(sorted(path.name for path in self.web.iterdir()), self.before, "a refused overlay writes nothing")

    def test_a_matching_overlay_is_copied_and_then_complete(self):
        self.assertEqual(rcv.performance_problem(self.web), "performance.html is missing")
        rcv.apply_performance_overlay(self.overlay, self.web, REVISION)
        self.assertEqual((self.web / "performance.html").read_text(), "benchmark page")
        self.assertEqual(sorted(set(path.name for path in self.web.iterdir()) - set(self.before)),
                         sorted(rcv.PERFORMANCE_FILES))
        self.assertIsNone(rcv.performance_problem(self.web, REVISION))

    def test_another_revision_is_refused(self):
        self.assert_refused("not " + "b" * 40, "b" * 40)

    def test_a_benchmark_of_another_build_is_refused(self):
        write_build(self.web, "b" * 40)
        self.assert_refused("measured another build", "b" * 40)

    def test_changed_core_files_are_refused(self):
        (self.web / "jungle.wasm").write_text("different")
        self.assert_refused("fingerprints differ")

    def test_only_the_three_regular_files_are_accepted(self):
        (self.overlay / "index.html").write_text("replaced")
        self.assert_refused("must hold exactly")
        (self.overlay / "index.html").unlink()
        (self.overlay / "performance.html").unlink()
        self.assert_refused("must hold exactly")
        (self.overlay / "performance.html").symlink_to(self.web / "dom.html")
        self.assert_refused("not a regular file")

    def test_the_command_refuses_before_any_group_starts(self):
        result = subprocess.run([sys.executable, "tools/run_ci_validation.py", "--group", "no-such-group"], cwd=ROOT,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown group no-such-group", result.stdout)


class GroupCommand(unittest.TestCase):
    """The real command in a private root: fake make, python3 and node record what they ran."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "tools").mkdir()
        for name in ("run_ci_validation.py", "measure_web.py"):
            shutil.copy(ROOT / "tools" / name, self.root / "tools" / name)
        (self.root / "tools/book_catalog.py").write_text(f"LANGUAGES = {rcv.book_languages()!r}\n")
        shutil.copy(ROOT / "Makefile", self.root / "Makefile")
        (self.root / "build/app").mkdir(parents=True)
        (self.root / "build/app/jungle").write_text("restored")
        self.record = self.root / "ran.txt"
        fake = self.root / "fake-bin"
        fake.mkdir()
        for tool in ("make", "python3", "node"):
            (fake / tool).write_text(f'#!/bin/sh\necho "{tool} $*" >> "{self.record}"\necho "output of {tool} $*"\n')
            (fake / tool).chmod(0o755)
        self.env = {"PATH": f"{fake}{os.pathsep}{os.environ['PATH']}", "DISPLAY": ":0"}

    def tearDown(self):
        self.temporary.cleanup()

    def command(self, *args):
        return subprocess.run([sys.executable, str(self.root / "tools/run_ci_validation.py"), *args], cwd=self.root,
                              env=self.env, capture_output=True, text=True, timeout=60)

    def test_sequential_groups_keep_each_others_logs_and_run_only_their_own_steps(self):
        first = self.command("--group", "hide-seek")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        capture = self.root / "work/ci-validation/hide-seek/ui/capture.png"
        capture.write_text("kept")
        second = self.command("--group", "activities")
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(capture.read_text(), "kept")
        self.assertIn("tests/hide_seek_levels_test.py", (self.root / "work/ci-validation/hide-seek.log").read_text())
        self.assertIn("tests/drums_playground_test.py", (self.root / "work/ci-validation/activities.log").read_text())
        ran = self.record.read_text().splitlines()
        self.assertEqual(ran.count("make all"), 2)
        self.assertEqual(ran.count("python3 tests/hide_seek_levels_test.py"), 1)
        self.assertEqual(len(ran), 2 + 1 + 4)

    def test_a_group_without_a_restored_build_or_benchmark_runs_nothing(self):
        refused = self.command("--group", rcv.PACKAGING)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("packaging needs this build's benchmark", refused.stdout)
        self.assertEqual(self.record.read_text().splitlines(), ["make all"])
        (self.root / "build/app/jungle").unlink()
        self.assertEqual(self.command("--group", "paint").returncode, 1)

    def test_apply_performance_needs_the_exact_revision(self):
        web, overlay = self.root / "build/web", self.root / "overlay"
        write_build(web)
        write_overlay(overlay, web)
        self.assertEqual(self.command("--apply-performance", str(overlay)).returncode, 2)
        self.assertEqual(self.command("--apply-performance", str(overlay), "--revision", "b" * 40).returncode, 1)
        self.assertFalse((web / "performance.json").exists())
        applied = self.command("--apply-performance", str(overlay), "--revision", REVISION)
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
        self.assertTrue((web / "performance.json").exists())
        self.assertFalse(self.record.exists(), "applying the benchmark runs no build or test")


class Isolation(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.work = self.root / "work/ci-validation"

    def tearDown(self):
        self.temporary.cleanup()

    def environment(self, group, step=None, base=None):
        base = base or {"PATH": "/usr/bin", "DISPLAY": ":0", "XAUTHORITY": "/home/x", rcv.LOCK_HELD: "1", "KEEP": "1"}
        return rcv.group_environment(base, group, step, root=self.root, work=self.work,
                                     bin_dir=self.root / "work/ci-bin", real_make="/usr/bin/make")

    def test_each_group_gets_private_folders_and_the_locked_make(self):
        paint, books = rcv.Group("paint", ()), rcv.Group("books", ())
        first, second = self.environment(paint), self.environment(books)
        for key in ("JUNGLE_TEST_OUTPUT", "TMPDIR", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
            self.assertNotEqual(first[key], second[key], key)
            self.assertTrue(Path(first[key]).is_dir())
            self.assertTrue(Path(first[key]).is_relative_to(self.work / "paint"), key)
        self.assertEqual(first["PATH"], f"{self.root}/work/ci-bin{os.pathsep}/usr/bin")
        self.assertEqual(first[rcv.MAKE_LOCK], second[rcv.MAKE_LOCK])
        for key in ("DISPLAY", "XAUTHORITY", rcv.LOCK_HELD):
            self.assertNotIn(key, first)
        self.assertEqual(first["KEEP"], "1")

    def test_step_environment_and_browser_scratch(self):
        browser = rcv.Group("browser", (), tmpdir="work/b")
        env = self.environment(browser, rcv.web("tests/web_test.mjs", "dom.html"))
        self.assertEqual(env["TMPDIR"], str(self.root / "work/b"))
        self.assertEqual(env["JUNGLE_WEB_PAGE"], "dom.html")
        self.assertEqual(env["JUNGLE_TEST_OUTPUT"], str(self.work / "browser/ui"))

    def test_runtime_harness_uses_the_group_capture_folder(self):
        command = [sys.executable, "-c", "import runtime_test; print(runtime_test.OUTPUT)"]
        env = {key: value for key, value in os.environ.items() if key != "JUNGLE_TEST_OUTPUT"}
        default = subprocess.run(command, cwd=ROOT / "tests", env=env, capture_output=True, text=True, check=True)
        self.assertEqual(default.stdout.strip(), str(ROOT / "build/tests/ui"))
        private = subprocess.run(command, cwd=ROOT / "tests", env={**env, "JUNGLE_TEST_OUTPUT": str(self.work / "g/ui")},
                                 capture_output=True, text=True, check=True)
        self.assertEqual(private.stdout.strip(), str(self.work / "g/ui"))

    def test_launcher_streams_prefixed_output_and_a_group_log(self):
        self.work.mkdir(parents=True)
        output = io.StringIO()
        launch = rcv.Launcher(rcv.Console(output), "/usr/bin/make", {"PATH": os.environ["PATH"]},
                              root=self.root, work=self.work, bin_dir=self.root / "work/ci-bin")
        step = rcv.Step((sys.executable, "-c", "import os;print('hello', os.environ['JUNGLE_TEST_OUTPUT']);raise SystemExit(4)"))
        self.assertEqual(launch(rcv.Group("g", ()), step), 4)
        self.assertIn(f"[g] hello {self.work}/g/ui\n", output.getvalue())
        log = (self.work / "g.log").read_text()
        self.assertIn("$ " + step.label(), log)
        self.assertIn("hello", log)
        self.assertEqual(launch(rcv.Group("g", ()), rcv.Step(("/nonexistent/node",))), 127)

    def test_app_snapshot_sees_a_rebuilt_binary(self):
        app = self.root / "app"
        (app / "games").mkdir(parents=True)
        (app / "jungle").write_text("one")
        (app / "games/book.zx").write_text("bundle")
        before = rcv.app_snapshot(app)
        self.assertEqual(set(before), {"jungle", "games/book.zx"})
        self.assertEqual(before, rcv.app_snapshot(app))
        replacement = app / "jungle.new"
        replacement.write_text("two")
        replacement.replace(app / "jungle")
        self.assertNotEqual(before, rcv.app_snapshot(app))


class MakeLock(unittest.TestCase):
    """The PATH make wrapper serializes makes across groups and allows nested makes."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.bin = self.root / "ci-bin"
        rcv.write_make_wrapper(self.bin)
        self.record = self.root / "record.txt"
        self.real = self.root / "real/make"
        self.real.parent.mkdir()
        # A fake make that records its interval and can start one nested make.
        self.real.write_text(f"""#!{sys.executable}
import os, subprocess, sys, time
with open({str(self.record)!r}, "a") as f: f.write(f"start {{sys.argv[1]}} {{time.monotonic()}}\\n")
if os.environ.get("NEST") == "1":
    subprocess.run(["make", sys.argv[1] + "-nested"], env={{**os.environ, "NEST": "0"}}, check=True, timeout=10)
time.sleep(0.3)
with open({str(self.record)!r}, "a") as f: f.write(f"end {{sys.argv[1]}} {{time.monotonic()}}\\n")
""")
        self.real.chmod(0o755)

    def tearDown(self):
        self.temporary.cleanup()

    def env(self, **extra):
        return {"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", rcv.REAL_MAKE: str(self.real),
                rcv.MAKE_LOCK: str(self.root / "make.lock"), **extra}

    def intervals(self):
        times = {}
        for line in self.record.read_text().splitlines():
            kind, name, moment = line.split()
            times.setdefault(name, {})[kind] = float(moment)
        return times

    def test_concurrent_makes_never_overlap(self):
        processes = [subprocess.Popen(["make", name], env=self.env()) for name in ("one", "two", "three")]
        self.assertEqual([process.wait(timeout=20) for process in processes], [0, 0, 0])
        spans = sorted((t["start"], t["end"]) for t in self.intervals().values())
        self.assertEqual(len(spans), 3)
        for (_, end), (start, _) in zip(spans, spans[1:]):
            self.assertLessEqual(end, start)

    def test_a_nested_make_inside_a_locked_make_does_not_deadlock(self):
        result = subprocess.run(["make", "outer"], env=self.env(NEST="1"), timeout=20)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(set(self.intervals()), {"outer", "outer-nested"})

    def test_an_inherited_held_flag_is_not_trusted_by_group_environments(self):
        env = rcv.group_environment({"PATH": "/usr/bin", rcv.LOCK_HELD: "1"}, rcv.Group("g", ()),
                                    root=self.root, work=self.root / "w", bin_dir=self.bin, real_make=str(self.real))
        self.assertNotIn(rcv.LOCK_HELD, env)

    def test_the_wrapper_is_never_the_real_make(self):
        with self.assertRaises(SystemExit):
            rcv.resolve_real_make(str(self.bin), self.bin)
        self.assertEqual(rcv.resolve_real_make(str(self.real.parent), self.bin), str(self.real.resolve()))


MASTER_ONLY = "github.ref == 'refs/heads/master' && github.event_name != 'pull_request'"
RUN_GROUP = "python3 tools/run_ci_validation.py --group "


def lines_of(step):
    return step.get("run", "").splitlines()


def named(steps, name):
    return next(step for step in steps if step.get("name") == name)


def commands(steps):
    return [line.strip() for step in steps for line in lines_of(step)]


class Workflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if yaml is None:
            raise unittest.SkipTest("PyYAML is not installed")
        cls.text = (ROOT / ".github/workflows/pages.yml").read_text()
        cls.workflow = yaml.safe_load(cls.text)
        cls.jobs = cls.workflow["jobs"]

    def steps(self, job):
        return self.jobs[job]["steps"]

    def test_runner_and_this_test_compile(self):
        for path in ("tools/run_ci_validation.py", "tests/ci_validation_test.py", "tests/book_ui_test.py",
                     "tests/runtime_test.py"):
            compile((ROOT / path).read_text(), path, "exec")  # syntax only; writes no bytecode

    def test_public_benchmark_verification_matches_the_generated_page(self):
        import ast
        import measure_web
        script = named(self.steps("publish"), "Verify public version")["run"]
        script = script.split("python3 - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        page_checks = next(node for node in ast.walk(ast.parse(script))
                          if isinstance(node, ast.Dict) and any(
                              isinstance(key, ast.Constant) and key.value == "performance.html"
                              for key in node.keys))
        markers = ast.literal_eval(next(value for key, value in zip(page_checks.keys, page_checks.values)
                                       if isinstance(key, ast.Constant) and key.value == "performance.html"))
        page = measure_web.html_report({})
        self.assertGreaterEqual(len(markers), 2)
        for marker in markers:
            self.assertIn(marker, page)

    def test_the_jobs_run_in_a_gated_chain_on_standard_machines(self):
        self.assertEqual(list(self.jobs), ["build", "validate", "package", "publish"])
        self.assertEqual(self.jobs["validate"]["needs"], "build")
        self.assertEqual(self.jobs["package"]["needs"], ["build", "validate"])
        self.assertEqual(self.jobs["publish"]["needs"], "package")
        self.assertEqual(self.jobs["publish"]["if"], MASTER_ONLY)
        for job in ("build", "validate", "package"):
            self.assertNotIn("if", self.jobs[job], "every revision runs the same gates, pull requests too")
        for name, job in self.jobs.items():
            self.assertEqual(job["runs-on"], "ubuntu-latest", name)
            self.assertNotIn("continue-on-error", job, name)
            self.assertNotIn("permissions", job, name)
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})

    def test_secrets_exist_only_in_the_publish_job(self):
        for job in ("build", "validate", "package"):
            self.assertNotIn("secrets.", yaml.safe_dump(self.jobs[job]), job)
        self.assertNotIn("secrets.", yaml.safe_dump(self.workflow.get("env", {})))
        self.assertEqual(self.text.count("secrets."), 2)

    def test_the_build_job_builds_once_before_uploading_the_shared_build(self):
        steps = self.steps("build")
        names = [step.get("name") for step in steps]
        schedule_check = named(steps, "Check the validation schedule and shared build contract")
        self.assertEqual(lines_of(schedule_check), ["python3 tests/ci_validation_test.py", "python3 tests/ci_artifacts_test.py"])
        order = ["Check the validation schedule and shared build contract", "Build compiler",
                 "Select the compiler and locked source directories", "Build and run local tests",
                 "Preserve the browser build for diagnosis", "Pack the shared build", "Upload the shared build"]
        self.assertEqual(sorted(order, key=names.index), order)
        build = [line for line in lines_of(named(steps, "Build and run local tests")) if line.startswith(("make", "python3", "node"))]
        self.assertEqual(build, ["make -j2 all", "make test", "python3 tools/build_web.py"])
        self.assertNotIn("continue-on-error", named(steps, "Build and run local tests"))
        artifact = named(steps, "Preserve the browser build for diagnosis")
        self.assertEqual(artifact["with"]["path"], "waozixyz/learning/jungle/build/web/")
        self.assertTrue(artifact["continue-on-error"])
        self.assertEqual(artifact["with"]["name"], "browser-build-${{ github.sha }}")
        self.assertNotIn("continue-on-error", named(steps, "Upload the shared build"))
        everywhere = [line for job in self.jobs for line in commands(self.steps(job))]
        for command in ("make -j2 all", "make test", "python3 tools/build_web.py"):
            self.assertEqual(everywhere.count(command), 1, command)
        self.assertEqual([uses for job in self.jobs for uses in
                          [step.get("uses", "") for step in self.steps(job)] if "setup-emsdk" in uses],
                         ["emscripten-core/setup-emsdk@v15"])
        self.assertEqual(sum("make -j2 -C" in line for line in everywhere), 1, "only the build job builds the compiler")

    def test_every_job_uses_the_exact_candidate_and_locked_sources(self):
        for job in self.jobs:
            checkout = self.steps(job)[0]
            self.assertTrue(checkout["uses"].startswith("actions/checkout@"), job)
            self.assertEqual(checkout["with"], {"ref": "${{ github.sha }}", "path": "waozixyz/learning/jungle"}, job)
        for job in ("build", "validate", "package"):
            used = {step["with"].get("repository"): step["with"]["ref"] for step in self.steps(job)
                    if step.get("uses", "").startswith("actions/checkout@") and "repository" in step["with"]}
            self.assertEqual(used, {"ziranlang/ziran": "${{ steps.deps.outputs.ziran }}",
                                    "kryonlabs/kryon": "${{ steps.deps.outputs.kryon }}"}, job)
            self.assertIn('echo "$GITHUB_WORKSPACE/ziranlang/ziran/build/bin" >> "$GITHUB_PATH"', commands(self.steps(job)))
            self.assertIn('echo "ZIRAN_ROOT=$GITHUB_WORKSPACE/ziranlang/ziran" >> "$GITHUB_ENV"', commands(self.steps(job)))

    def test_the_matrix_assigns_every_group_exactly_once(self):
        strategy = self.jobs["validate"]["strategy"]
        self.assertEqual(strategy["max-parallel"], 4)
        self.assertIs(strategy["fail-fast"], False)
        lanes = tuple((entry["lane"], tuple(json.loads(entry["groups"]))) for entry in strategy["matrix"]["include"])
        self.assertEqual(lanes, rcv.CI_LANES)
        self.assertEqual(list(strategy["matrix"]), ["include"])
        assigned = [name for _, names in lanes for name in names]
        self.assertEqual(collections.Counter(assigned), collections.Counter(group.name for group in rcv.schedule()))

    def test_each_group_is_its_own_visible_step_in_lane_order(self):
        steps = self.steps("validate")
        runs = [step for step in steps if step.get("run", "").startswith(RUN_GROUP)]
        names = [step["run"][len(RUN_GROUP):] for step in runs]
        self.assertEqual(collections.Counter(names), collections.Counter(group.name for group in rcv.schedule()))
        for step, name in zip(runs, names):
            self.assertEqual(step["name"], f"Validate {name}")
            self.assertEqual(step["if"], f"contains(fromJSON(matrix.groups), '{name}')")
            self.assertNotIn("continue-on-error", step)
        for _, lane in rcv.CI_LANES:
            self.assertEqual([name for name in names if name in lane], list(lane))
        self.assertEqual(names[0], "hide-seek", "the short gate reports first")
        self.assertNotIn(rcv.PACKAGING, names)

    def test_lanes_restore_the_shared_build_before_any_group(self):
        for job in ("validate", "package"):
            steps = self.steps(job)
            names = [step.get("name") for step in steps]
            download = named(steps, "Download the shared build")
            self.assertEqual(download["uses"], "actions/download-artifact@v4")
            self.assertEqual(download["with"], {"name": "ci-build-${{ github.sha }}",
                                                "path": "waozixyz/learning/jungle/work/ci-artifacts"})
            restore = named(steps, "Restore the shared build")
            self.assertEqual(lines_of(restore), ['python3 tools/ci_artifacts.py restore --kind build --revision "$GITHUB_SHA" '
                                                 '--archive work/ci-artifacts/ci-build.tar.gz --toolchain "$ZIRAN_ROOT"'])
            self.assertLess(names.index("Select the compiler and locked source directories"), names.index("Download the shared build"))
            self.assertLess(names.index("Download the shared build"), names.index("Restore the shared build"))
            first_group = min(index for index, step in enumerate(steps) if step.get("run", "").startswith(RUN_GROUP))
            self.assertLess(names.index("Restore the shared build"), first_group)
            checkouts = [index for index, step in enumerate(steps) if step.get("uses", "").startswith("actions/checkout@")]
            self.assertLess(max(checkouts), names.index("Restore the shared build"), "outputs are refreshed after all sources")

    def test_shared_outputs_are_short_lived_and_stored_uncompressed(self):
        for job, name, archive in (("build", "Upload the shared build", "work/ci-build.tar.gz"),
                                   ("package", "Upload the tested website", "work/ci-web.tar.gz")):
            upload = named(self.steps(job), name)["with"]
            self.assertEqual(upload["retention-days"], 1)
            self.assertEqual(upload["compression-level"], 0)
            self.assertEqual(upload["if-no-files-found"], "error")
            self.assertEqual(upload["path"], "waozixyz/learning/jungle/" + archive)
        pack = lines_of(named(self.steps("build"), "Pack the shared build"))
        self.assertEqual(pack, ['python3 tools/ci_artifacts.py pack --kind build --revision "$GITHUB_SHA" '
                                '--output work/ci-build.tar.gz --toolchain "$ZIRAN_ROOT"'])

    def test_only_the_benchmark_lane_uploads_only_the_benchmark_at_its_end(self):
        steps = self.steps("validate")
        upload = named(steps, "Upload the benchmark of the shared build")
        self.assertEqual(upload["if"], "contains(fromJSON(matrix.groups), 'performance')")
        self.assertEqual(upload["with"]["retention-days"], 1)
        self.assertEqual(upload["with"]["if-no-files-found"], "error")
        self.assertEqual(sorted(path.rsplit("/", 1)[1] for path in upload["with"]["path"].splitlines()), sorted(rcv.PERFORMANCE_FILES))
        groups = max(index for index, step in enumerate(steps) if step.get("run", "").startswith(RUN_GROUP))
        self.assertGreater(steps.index(upload), groups)

    def test_the_package_job_tests_the_benchmarked_build_once(self):
        steps = self.steps("package")
        order = ["Restore the shared build", "Download the benchmark of the shared build",
                 "Add the benchmark to the tested website", "Prepare and test the embed edition",
                 "Pack the tested website", "Upload the tested website"]
        names = [step.get("name") for step in steps]
        self.assertEqual(sorted(order, key=names.index), order)
        self.assertEqual(lines_of(named(steps, "Add the benchmark to the tested website")),
                         ['python3 tools/run_ci_validation.py --apply-performance work/ci-artifacts/performance --revision "$GITHUB_SHA"'])
        self.assertEqual(lines_of(named(steps, "Prepare and test the embed edition")), [RUN_GROUP + rcv.PACKAGING])
        self.assertEqual(lines_of(named(steps, "Pack the tested website")),
                         ['python3 tools/ci_artifacts.py pack --kind web --revision "$GITHUB_SHA" --output work/ci-web.tar.gz'])
        self.assertFalse([step for step in steps if "if" in step and step["if"] != "failure()"])

    def test_publishing_uses_only_the_tested_website(self):
        steps = self.steps("publish")
        names = [step.get("name") for step in steps]
        self.assertEqual(names[names.index("Download the tested website"):],
                         ["Download the tested website", "Restore the tested website", "Publish the tested website",
                          "Verify public version", "Install itch.io Butler", "Publish the tested browser edition to itch.io"])
        self.assertEqual(named(steps, "Download the tested website")["with"]["name"], "ci-web-${{ github.sha }}")
        self.assertEqual(lines_of(named(steps, "Restore the tested website")),
                         ['python3 tools/ci_artifacts.py restore --kind web --revision "$GITHUB_SHA" --archive work/ci-artifacts/ci-web.tar.gz'])
        lines = commands(steps)
        self.assertIn('npx --yes wrangler@4.152.0 pages deploy build/web --project-name jungle --branch master --commit-hash "$GITHUB_SHA"', lines)
        self.assertIn('butler push build/itch-web waozi/jungle:html5 --userversion "$(cat VERSION)"', lines)
        self.assertIn("python3 tools/connect_domain.py", lines)
        for line in lines:
            self.assertFalse(line.startswith(("make", "python3 tests/", RUN_GROUP)), line)
        self.assertFalse([step for step in steps if "repository" in step.get("with", {})], "publishing needs no compiler")
        self.assertFalse([step for step in steps if "continue-on-error" in step])

    def test_failure_captures_stay_private_to_each_failed_job(self):
        for job in ("build", "validate", "package"):
            capture = named(self.steps(job), "Save private test captures on failure")
            self.assertEqual(capture["if"], "failure()")
            self.assertTrue(capture["continue-on-error"])
            self.assertEqual(capture["with"]["name"], "website-ui-failure-${{ github.job }}-${{ strategy.job-index }}")
            self.assertEqual(capture["with"]["retention-days"], 1)
            paths = capture["with"]["path"]
            self.assertIn("waozixyz/learning/jungle/work/ci-validation/*.log", paths)
            self.assertIn("waozixyz/learning/jungle/work/hide-seek-levels/ui/*", paths)


if __name__ == "__main__":
    unittest.main()

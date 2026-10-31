"""Orchestration tests for tools/run_ci_validation.py; fake commands only, no app or browser."""
import collections
import io
import os
from pathlib import Path
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

    def test_browser_matrix_keeps_every_gate_with_painting_first(self):
        browser = next(group for group in self.groups if group.name == "browser")
        actual = [step.label() for step in browser.steps]
        painting = [gate for gate in OLD_BROWSER_GATES if "tests/paint_layers_web_test.mjs" in gate]
        self.assertEqual(collections.Counter(actual), collections.Counter(OLD_BROWSER_GATES))
        self.assertEqual(actual, painting + [gate for gate in OLD_BROWSER_GATES if gate not in painting])
        self.assertEqual(browser.tmpdir, "work/b")
        others = [step for group in self.groups if group.name != "browser" for step in group.steps]
        self.assertTrue(all(step.recipe for step in others), "non-browser groups run only test-ui lines")

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


class Workflow(unittest.TestCase):
    def test_runner_and_this_test_compile(self):
        for path in ("tools/run_ci_validation.py", "tests/ci_validation_test.py", "tests/book_ui_test.py",
                     "tests/runtime_test.py"):
            compile((ROOT / path).read_text(), path, "exec")  # syntax only; writes no bytecode

    @unittest.skipIf(yaml is None, "PyYAML is not installed")
    def test_public_benchmark_verification_matches_the_generated_page(self):
        import ast
        import measure_web
        workflow = yaml.safe_load((ROOT / ".github/workflows/pages.yml").read_text())
        steps = workflow["jobs"]["test-build"]["steps"]
        script = next(step["run"] for step in steps if step.get("name") == "Verify public version")
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

    @unittest.skipIf(yaml is None, "PyYAML is not installed")
    def test_one_job_builds_once_then_runs_the_validation(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/pages.yml").read_text())
        self.assertEqual(list(workflow["jobs"]), ["test-build"])
        steps = workflow["jobs"]["test-build"]["steps"]
        names = [step.get("name") for step in steps]
        self.assertLess(names.index("Check the validation schedule"),
                        names.index("Build compiler and select locked source directories"))
        build = steps[names.index("Build and run local tests")]["run"].splitlines()
        commands = [line for line in build if line.startswith(("make", "python3", "node"))]
        self.assertEqual(commands, ["make -j2 all", "make test", "python3 tools/build_web.py",
                                    "python3 tools/run_ci_validation.py"])
        self.assertNotIn("continue-on-error", steps[names.index("Build and run local tests")])
        capture = steps[names.index("Save private test captures on failure")]
        self.assertEqual(capture["if"], "failure()")
        self.assertIn("waozixyz/learning/jungle/work/ci-validation/*.log", capture["with"]["path"])
        publishing = names[names.index("Publish the tested website"):]
        self.assertEqual(publishing, ["Publish the tested website", "Verify public version", "Install itch.io Butler",
                                      "Publish the tested browser edition to itch.io"])
        for step in steps[names.index("Publish the tested website"):]:
            self.assertEqual(step["if"], "github.ref == 'refs/heads/master' && github.event_name != 'pull_request'")


if __name__ == "__main__":
    unittest.main()

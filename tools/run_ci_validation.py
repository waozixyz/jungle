#!/usr/bin/env python3
"""Run Jungle's post-build native UI and browser gates, at most two at a time.

GitHub CI runs this once, after the one shared `make all`, `make test` and
`tools/build_web.py`. It runs every `make test-ui` recipe line and every
browser gate the workflow used to run one after another, as disjoint groups
with at most two test subprocesses at once. Each group gets its own capture
folder, scratch and XDG directories under work/ci-validation. Lazy `make`
calls from tests go through a reentrant lock, so no two builds write the
same outputs, and the installed app must stay byte-for-byte the build that
was tested. Success means every gate passed; after a failure, commands
already running finish and nothing new starts.
"""
from __future__ import annotations

import argparse
import collections
import dataclasses
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work/ci-validation"
BIN = ROOT / "work/ci-bin"
MAX_WORKERS = 2
BOOK_RECIPE = "python3 tests/book_ui_test.py"
# Environment of the PATH make wrapper (see MAKE_WRAPPER).
REAL_MAKE, MAKE_LOCK, LOCK_HELD = "JUNGLE_CI_REAL_MAKE", "JUNGLE_CI_MAKE_LOCK", "JUNGLE_CI_MAKE_LOCK_HELD"
INHERITED_DESKTOP = ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS", "SESSION_MANAGER")


@dataclasses.dataclass(frozen=True)
class Step:
    argv: tuple[str, ...]
    env: tuple[tuple[str, str], ...] = ()
    # The Makefile test-ui recipe line this step runs, if any.
    recipe: str | None = None

    def label(self) -> str:
        return " ".join([f"{key}={shlex.quote(value)}" for key, value in self.env] + [shlex.join(self.argv)])


@dataclasses.dataclass(frozen=True)
class Group:
    name: str
    steps: tuple[Step, ...]
    # Scratch TMPDIR relative to ROOT; None uses the group's own folder.
    tmpdir: str | None = None


def native(command: str) -> Step:
    return Step(tuple(shlex.split(command)), recipe=command)


def book(language: str) -> Step:
    return Step(("python3", "tests/book_ui_test.py", "--language", language), recipe=BOOK_RECIPE)


def web(script: str, page: str | None = None, **env: str) -> Step:
    pairs = tuple(env.items()) + ((("JUNGLE_WEB_PAGE", page),) if page else ())
    return Step(("node", script), pairs)


def browser_steps() -> tuple[Step, ...]:
    """All original browser gates, painting first; prepare_itch stays before test_itch."""
    steps = [web("tests/paint_layers_web_test.mjs", "canvas.html"),
             web("tests/paint_layers_web_test.mjs", "dom.html"),
             web("tests/book_browser_interaction_test.mjs", "dom.html"),
             web("tests/book_browser_interaction_test.mjs", "canvas.html"),
             Step(("python3", "tests/book_shelf_test.py"))]
    steps += [web("tests/new_activities_web_test.mjs", page, JUNGLE_TEST_LANG=language)
              for page in ("dom.html", "canvas.html") for language in ("en", "de", "es")]
    steps += [Step(("python3", "tests/speech_playback_test.py")),
              Step(("node", "tests/asset_packs_test.mjs")),
              Step(("python3", "tests/web_images_test.py")),
              Step(("python3", "tools/prepare_itch.py")),
              Step(("python3", "tools/test_itch_web.py"))]
    steps += [web(f"tests/{name}.mjs", page)
              for name in ("jigsaw_web_test", "piano_web_test", "web_test")
              for page in ("canvas.html", "dom.html")]
    steps += [Step(("node", "tests/dom_native_web_test.mjs")),
              Step(("python3", "tools/measure_web.py"))]
    return tuple(steps)


def schedule() -> tuple[Group, ...]:
    """Groups in start order: a free slot takes the next one."""
    def group(name, *commands, tmpdir=None):
        return Group(name, tuple(native(c) if isinstance(c, str) else c for c in commands), tmpdir)
    return (
        group("paint", "python3 tests/slot_preview_test.py", "python3 tests/paint_layers_test.py",
              "python3 tests/paint_history_test.py", "python3 tests/paint_library_test.py",
              "python3 tests/language_ui_test.py"),
        # Chromium's singleton socket must fit a Unix socket path, so the
        # browser group keeps the short TMPDIR the workflow always used.
        Group("browser", browser_steps(), tmpdir="work/b"),
        group("book-en", book("en")),
        group("book-de", book("de")),
        group("navigation", "python3 tests/menu_ui_test.py", "python3 tests/runtime_test.py --ui",
              "python3 tests/learning_menu_test.py", "python3 tests/piano_ui_test.py",
              "python3 tests/jigsaw_sizes_ui_test.py", "python3 tests/jigsaw_ui_test.py"),
        group("book-es", book("es")),
        group("activities", "python3 tests/shapes_guidance_test.py", "python3 tests/counting_exercises_test.py",
              "python3 tests/drums_playground_test.py", "python3 tests/new_activities_ui_test.py",
              "python3 tests/hide_seek_levels_test.py"),
        group("books", "python3 tests/book_interaction_test.py", "python3 tests/book_additions_ui_test.py",
              "python3 tests/abc_sequence_ui_test.py", "python3 tests/playback_ui_test.py"),
    )


def test_ui_recipe(makefile: str) -> tuple[list[str], list[str]]:
    """The test-ui target's prerequisites and its recipe lines, verbatim."""
    lines = makefile.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("test-ui:")), None)
    if start is None:
        raise ValueError("Makefile has no test-ui target")
    prerequisites = lines[start].split(":", 1)[1].split()
    recipe = []
    for line in lines[start + 1:]:
        if not line.startswith("\t"):
            break
        command = line.strip()
        # Plain commands only, so running the argv is exactly what make ran.
        if not command or command[0] in "@-+" or "$" in command or command.endswith("\\"):
            raise ValueError(f"test-ui recipe line needs a runner update: {line!r}")
        recipe.append(command)
    return prerequisites, recipe


def coverage_problems(groups, recipe, languages) -> list[str]:
    """Every test-ui line runs exactly once; Book runs once per language."""
    problems = []
    names = [group.name for group in groups]
    if len(set(names)) != len(names):
        problems.append(f"duplicate group names: {names}")
    labels = collections.Counter(step.label() for group in groups for step in group.steps)
    problems += [f"step scheduled {count} times: {label}" for label, count in labels.items() if count > 1]
    covered, book_languages = collections.Counter(), []
    for group in groups:
        for step in group.steps:
            if step.recipe == BOOK_RECIPE:
                if step.argv[:-1] != (*shlex.split(BOOK_RECIPE), "--language") or step.env:
                    problems.append(f"unexpected Book sweep form: {step.label()}")
                book_languages.append(step.argv[-1])
            elif step.recipe is not None:
                if step.argv != tuple(shlex.split(step.recipe)) or step.env:
                    problems.append(f"step differs from its recipe {step.recipe!r}: {step.label()}")
                covered[step.recipe] += 1
    if book_languages:
        if collections.Counter(book_languages) != collections.Counter(languages):
            problems.append(f"Book languages {book_languages} must be {list(languages)} once each")
        else:
            covered[BOOK_RECIPE] += 1
    expected = collections.Counter(recipe)
    problems += [f"test-ui line not scheduled: {line}" for line in expected - covered]
    problems += [f"scheduled line not in test-ui: {line}" for line in covered - expected]
    return problems


class Console:
    """Prefixed, line-atomic output shared by every group."""
    def __init__(self, stream=None):
        self.stream = stream or sys.stdout
        self.lock = threading.Lock()

    def line(self, text: str):
        with self.lock:
            self.stream.write(text if text.endswith("\n") else text + "\n")
            self.stream.flush()


def RunCIValidation(groups, launch, *, console: Console | None = None, max_workers: int = MAX_WORKERS) -> int:
    """Run groups' steps in order, at most max_workers groups (one subprocess each) at once.

    launch(group, step) runs one command and returns its exit status. Returns 0
    only when every step of every group passed; the first failure stops new
    steps from starting while already running commands finish.
    """
    if not 1 <= max_workers <= MAX_WORKERS:
        raise ValueError(f"max_workers must be between 1 and {MAX_WORKERS}")
    console = console or Console()
    pending, threads, results = list(groups), [], {}
    stop, changed = threading.Event(), threading.Condition()
    running = 0

    def work(group):
        nonlocal running
        started, status = time.monotonic(), "passed"
        try:
            for step in group.steps:
                if stop.is_set():
                    status = "stopped"
                    break
                console.line(f"[{group.name}] start: {step.label()}")
                began = time.monotonic()
                try:
                    code = launch(group, step)
                except Exception as error:  # a launch problem is a failed gate
                    console.line(f"[{group.name}] could not run {step.label()}: {error!r}")
                    code = -1
                seconds = time.monotonic() - began
                if code != 0:
                    status = "failed"
                    stop.set()
                    console.line(f"::error title=CI validation {group.name}::exit {code} after {seconds:.0f}s: {step.label()}")
                    break
                console.line(f"[{group.name}] passed in {seconds:.0f}s: {step.label()}")
        except BaseException:
            status = "failed"
            stop.set()
            raise
        finally:
            with changed:
                results[group.name] = (status, time.monotonic() - started)
                running -= 1
                changed.notify_all()

    try:
        with changed:
            while pending and not stop.is_set():
                while running >= max_workers and not stop.is_set():
                    changed.wait()
                if stop.is_set():
                    break
                group = pending.pop(0)
                running += 1
                thread = threading.Thread(target=work, args=(group,), name=f"ci-{group.name}")
                threads.append(thread)
                thread.start()
    except KeyboardInterrupt:
        stop.set()
        console.line("::error title=CI validation::interrupted; waiting for running commands")
    finally:
        for thread in threads:
            thread.join()
    for name, (status, seconds) in results.items():
        console.line(f"CI validation {name}: {status} ({seconds:.0f}s)")
    for group in pending:
        console.line(f"CI validation {group.name}: not started")
    passed = not pending and all(status == "passed" for status, _ in results.values())
    passed = passed and len(results) == len(groups)
    console.line("CI validation passed: every gate succeeded" if passed else "::error title=CI validation::failed")
    return 0 if passed else 1


def group_environment(base, group: Group, step: Step | None = None, *, root=ROOT, work=WORK, bin_dir=BIN,
                      real_make: str) -> dict[str, str]:
    """A private environment: own captures, scratch, XDG folders and the locked make."""
    env = {key: value for key, value in base.items() if key not in INHERITED_DESKTOP and key != LOCK_HELD}
    scratch = work / group.name
    folders = {"JUNGLE_TEST_OUTPUT": scratch / "ui",
               "TMPDIR": root / group.tmpdir if group.tmpdir else scratch / "tmp",
               "XDG_CONFIG_HOME": scratch / "config", "XDG_CACHE_HOME": scratch / "cache",
               "XDG_DATA_HOME": scratch / "data", "XDG_STATE_HOME": scratch / "state"}
    for key, folder in folders.items():
        folder.mkdir(parents=True, exist_ok=True)
        env[key] = str(folder)
    env.update(PATH=str(bin_dir) + os.pathsep + base.get("PATH", os.defpath),
               PYTHONUNBUFFERED="1", **{REAL_MAKE: real_make, MAKE_LOCK: str(work / "make.lock")})
    env.update(step.env if step else ())
    return env


class Launcher:
    """Run a step from ROOT, streaming prefixed output to the console and the group's log."""
    def __init__(self, console: Console, real_make: str, base=None, *, root=ROOT, work=WORK, bin_dir=BIN):
        self.console, self.real_make, self.base = console, real_make, dict(os.environ if base is None else base)
        self.root, self.work, self.bin_dir = root, work, bin_dir

    def __call__(self, group: Group, step: Step) -> int:
        env = group_environment(self.base, group, step, root=self.root, work=self.work,
                                bin_dir=self.bin_dir, real_make=self.real_make)
        with (self.work / f"{group.name}.log").open("a", encoding="utf-8") as log:
            log.write(f"$ {step.label()}\n")
            log.flush()
            try:
                process = subprocess.Popen(step.argv, cwd=self.root, env=env, stdin=subprocess.DEVNULL,
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           text=True, errors="replace", bufsize=1)
            except OSError as error:
                log.write(f"could not start: {error}\n")
                self.console.line(f"[{group.name}] could not start {step.label()}: {error}")
                return 127
            def stream():
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    self.console.line(f"[{group.name}] {line}")
            reader = threading.Thread(target=stream, name=f"ci-{group.name}-output", daemon=True)
            reader.start()
            code = process.wait()
            # A leftover grandchild may keep the pipe open; never hang on it.
            reader.join(30)
            if reader.is_alive():
                self.console.line(f"[{group.name}] note: a leftover process still holds this command's output")
            else:
                process.stdout.close()
            return code


# Installed on PATH as `make` for test subprocesses. The lock fd stays open
# across exec, so make and its nested makes hold it until they exit; the
# inherited flag makes a make started inside a locked make proceed directly.
MAKE_WRAPPER = '''import fcntl, os, sys, time
real = os.environ["{real}"]
if os.environ.get("{held}") != "1":
    fd = os.open(os.environ["{lock}"], os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    deadline, waiting = time.monotonic() + float(os.environ.get("JUNGLE_CI_MAKE_LOCK_TIMEOUT", "1800")), False
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() > deadline:
                sys.exit("CI make lock: another make held the shared build lock too long")
            if not waiting:
                print("CI make lock: waiting for another group's make", file=sys.stderr, flush=True)
                waiting = True
            time.sleep(0.2)
    os.set_inheritable(fd, True)
    os.environ["{held}"] = "1"
os.execv(real, [real] + sys.argv[1:])
'''.format(real=REAL_MAKE, held=LOCK_HELD, lock=MAKE_LOCK)


def write_make_wrapper(bin_dir: Path = BIN, python: str = sys.executable) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    wrapper = bin_dir / "make"
    wrapper.write_text(f"#!{python} -I\n" + MAKE_WRAPPER)
    wrapper.chmod(0o755)
    return wrapper


def resolve_real_make(path: str | None = None, bin_dir: Path = BIN) -> str:
    found = shutil.which("make", path=os.environ.get("PATH", os.defpath) if path is None else path)
    if not found:
        raise SystemExit("make is not on PATH")
    real = Path(found).resolve()
    if real.parent == bin_dir.resolve():
        raise SystemExit(f"refusing to use the CI make wrapper as the real make: {real}")
    return str(real)


def app_snapshot(app: Path) -> dict[str, tuple[int, int, int]]:
    """Identity of the app binary, its bundles and catalog, which tests only read."""
    files = [app / "jungle", app / "games/catalog.txt", *sorted((app / "games").glob("*.zx"))]
    snapshot = {}
    for path in files:
        if path.exists():
            info = path.stat()
            snapshot[str(path.relative_to(app))] = (info.st_ino, info.st_size, info.st_mtime_ns)
    return snapshot


def book_languages() -> tuple[str, ...]:
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        from book_catalog import LANGUAGES
    finally:
        sys.path.pop(0)
    return tuple(LANGUAGES)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--list", action="store_true", help="print the checked schedule and exit")
    args = parser.parse_args(argv)
    prerequisites, recipe = test_ui_recipe((ROOT / "Makefile").read_text())
    groups = schedule()
    problems = coverage_problems(groups, recipe, book_languages())
    for problem in problems:
        print(f"::error title=CI validation schedule::{problem}", flush=True)
    if problems:
        return 2
    if args.list:
        for group in groups:
            print(group.name)
            for step in group.steps:
                print("  " + step.label())
        return 0
    real_make = resolve_real_make()
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    write_make_wrapper()
    console = Console()
    launch = Launcher(console, real_make)
    # make test-ui's own prerequisites, once, before any test starts.
    prepare = Group("prepare", (Step(("make", *prerequisites)),))
    if RunCIValidation((prepare,), launch, console=console, max_workers=1):
        return 1
    before = app_snapshot(ROOT / "build/app")
    code = RunCIValidation(groups, launch, console=console)
    after = app_snapshot(ROOT / "build/app")
    if before != after:
        changed = sorted(set(before.items()) ^ set(after.items()))
        console.line(f"::error title=CI validation::the tested app changed while tests ran: {changed}")
        return 1
    return code


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Coloring Book undo history survives reopening and restarts, stays bound to
its exact working picture, and refuses damaged or stale histories. Uses only
disposable saves and an owned private Xvfb."""
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from runtime_test import Desktop, PICTURE_HEADER, ROOT, environment

HEADER = b"JUNGLE UNDO 1\n"
STEPS = 8


def scenery(picture):
    """A picture without its chosen crayon, which Undo keeps as it is."""
    crayon = len(PICTURE_HEADER) + 1
    return picture[:crayon] + picture[crayon + 1:]


def same(steps, pictures):
    return [scenery(step) for step in steps] == [scenery(picture) for picture in pictures]


def fnv(data):
    value = 14695981039346656037
    for byte in data:
        value = ((value ^ byte) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return value


def history(folder):
    """The steps of working-undo.txt, after checking that it names working.txt."""
    saved = (folder / "working-undo.txt").read_bytes()
    working = (folder / "working.txt").read_bytes()
    assert saved.startswith(HEADER), "the history has no header"
    bound, rest = saved[len(HEADER):].split(b"\n", 1)
    length, digest = bound.split(b" ")
    assert int(length) == len(working) and digest == b"%016x" % fnv(working), "the history names another picture"
    count, rest = rest.split(b"\n", 1)
    steps = []
    for _ in range(int(count)):
        size, rest = rest.split(b"\n", 1)
        steps.append(rest[:int(size)])
        rest = rest[int(size):]
    assert rest == b"" and len(steps) <= STEPS
    return steps


def pure():
    env = environment()
    subprocess.run(["make", "-s", "build/tests/paint_history"], cwd=ROOT, env=env, check=True, timeout=600)
    result = subprocess.run([str(ROOT / "build/tests/paint_history")], env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, f"pure history test failed at step {result.returncode}"
    print(result.stdout.strip(), flush=True)


def changed(path, before, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and path.read_bytes() != before:
            return path.read_bytes()
        time.sleep(.1)
    raise AssertionError(f"{path.name} did not change")


def open_paint(desktop, name):
    desktop.game("Coloring Book")
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        picture = desktop.capture(name, header=56)
        if (0, 0, 170) not in [color for _, color in picture.crop((20, 42, 45, 64)).getcolors(10000)]:
            time.sleep(.5)
            return desktop.capture(name, header=56)
        time.sleep(.1)
    raise AssertionError("Coloring Book did not open")


def undo(desktop, working, expected):
    before = working.read_bytes()
    desktop.click(30, 160)
    if scenery(expected) == scenery(before):
        time.sleep(.6)
        assert working.read_bytes() == before, "Undo changed a picture with no history left"
    else:
        assert scenery(changed(working, before)) == scenery(expected), "Undo restored a different picture"


def fill(desktop, working, swatch):
    before = working.read_bytes()
    desktop.click(30, 40)
    desktop.capture("paint-history-colors", header=56)
    desktop.click(38 + swatch % 7 * 41, 40 + swatch // 7 * 23)
    desktop.click(71, 13)
    return changed(working, before)


def ui():
    binary = ROOT / "build/app/jungle"
    with tempfile.TemporaryDirectory(prefix="jungle-paint-history-") as temporary:
        root = Path(temporary)
        data = root / "data"
        folder = data / "games/jungle.paint"
        working = folder / "working.txt"
        pictures = []
        with Desktop(binary, data) as desktop:
            desktop.game("Coloring Book")
            desktop.wait_scene_picker("paint-history-scenes")
            desktop.click(65, 60)
            pictures.append(changed(working, b""))
            desktop.key("Escape")
            desktop.capture("paint-history-main", header=56)
            for swatch in range(10):
                pictures.append(fill(desktop, working, swatch))
            desktop.capture("paint-history-filled", header=56)
            # Ten fills keep the eight newest earlier pictures.
            assert same(history(folder), pictures[2:10]), "the history is not the eight newest steps"
            undo(desktop, working, pictures[9])
            assert same(history(folder), pictures[2:9])
            desktop.key("Escape")
            desktop.wait_menu("paint-history-menu")
        after_first = root / "after-first"
        shutil.copytree(data, after_first)
        with Desktop(binary, data) as desktop:
            open_paint(desktop, "paint-history-restarted")
            assert scenery(working.read_bytes()) == scenery(pictures[9]), "restarting changed the working picture"
            undo(desktop, working, pictures[8])
            undo(desktop, working, pictures[7])
            desktop.key("Escape")
            desktop.wait_menu("paint-history-menu-again")
            open_paint(desktop, "paint-history-reopened")
            undo(desktop, working, pictures[6])
            assert same(history(folder), pictures[2:6])
        print("local UI test: undo continues after restart and reopening", flush=True)
        with Desktop(binary, data) as desktop:
            open_paint(desktop, "paint-history-third")
            for index in (5, 4, 3, 2, 2):
                undo(desktop, working, pictures[index])
            assert history(folder) == []
        with Desktop(binary, data) as desktop:
            open_paint(desktop, "paint-history-exhausted")
            undo(desktop, working, pictures[2])
        print("local UI test: eight undo steps, consumed steps stay consumed", flush=True)

        # A damaged history is refused whole; the picture is untouched and the
        # next change starts a new history.
        damaged = root / "damaged"
        shutil.copytree(after_first, damaged)
        undo_file = damaged / "games/jungle.paint/working-undo.txt"
        text = bytearray(undo_file.read_bytes())
        text[-3] = ord("!")
        undo_file.write_bytes(bytes(text))
        # A picture saved before histories existed opens without one.
        legacy = root / "legacy"
        shutil.copytree(after_first, legacy)
        (legacy / "games/jungle.paint/working-undo.txt").unlink()
        for name, copy in (("damaged", damaged), ("legacy", legacy)):
            paint = copy / "games/jungle.paint"
            with Desktop(binary, copy) as desktop:
                open_paint(desktop, f"paint-history-{name}")
                assert scenery((paint / "working.txt").read_bytes()) == scenery(pictures[9])
                undo(desktop, paint / "working.txt", pictures[9])
                fill(desktop, paint / "working.txt", 20)
                assert same(history(paint), [pictures[9]]), f"the {name} history was not replaced"
        print("local UI test: damaged and missing histories leave the picture intact", flush=True)

        # Saving a slot keeps the history; loading one starts without any.
        slots = root / "slots"
        shutil.copytree(after_first, slots)
        paint = slots / "games/jungle.paint"
        with Desktop(binary, slots) as desktop:
            open_paint(desktop, "paint-history-slots")
            desktop.click(30, 110)
            desktop.capture("paint-history-save", header=56)
            desktop.click(50, 80)
            deadline = time.monotonic() + 10
            while not (paint / "slot-0.txt").exists() and time.monotonic() < deadline:
                time.sleep(.1)
            assert scenery((paint / "slot-0.txt").read_bytes()) == scenery(pictures[9])
            assert same(history(paint), pictures[2:9]), "saving a slot changed the history"
            desktop.click(30, 110)
            desktop.click(210, 38)
            desktop.click(50, 80)
            time.sleep(.6)
            assert scenery((paint / "working.txt").read_bytes()) == scenery(pictures[9])
            assert history(paint) == [], "loading a slot kept the earlier history"
            undo(desktop, paint / "working.txt", pictures[9])
        print("local UI test: loading a slot clears the history", flush=True)


if __name__ == "__main__":
    pure()
    ui()
    print("local paint history test passed")

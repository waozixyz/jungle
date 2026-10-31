#!/usr/bin/env python3
"""Coloring Book undo history survives reopening and restarts, stays bound to
its exact working picture, and refuses damaged or stale histories. Uses only
disposable saves and an owned private Xvfb."""
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import runtime_test
from runtime_test import PICTURE_HEADER, ROOT, environment

WORK = ROOT / "work/paint-native-tests"


class Desktop(runtime_test.Desktop):
    """Reuse the owned Xvfb harness with disposable captures and logs."""
    def __enter__(self):
        WORK.mkdir(parents=True, exist_ok=True)
        self._captures = tempfile.TemporaryDirectory(prefix="captures-", dir=WORK)
        self._old_output = runtime_test.OUTPUT
        runtime_test.OUTPUT = Path(self._captures.name)
        self.log_tail = ""
        return super().__enter__()

    def capture(self, name, header=None):
        picture = super().capture(name, header)
        from PIL import Image
        with Image.open(runtime_test.OUTPUT / (name + ".png")) as actual:
            self.actual_size = actual.size
        return picture

    def __exit__(self, *args):
        try:
            super().__exit__(*args)
            path = runtime_test.OUTPUT / "jungle.log"
            if path.exists():
                with path.open() as stream:
                    stream.seek(0, 2)
                    stream.seek(max(0, stream.tell() - 8000))
                    self.log_tail = stream.read(8000)
                if args and args[0] is not None and self.log_tail.strip():
                    print(self.log_tail[-2000:], flush=True)
        finally:
            runtime_test.OUTPUT = self._old_output
            self._captures.cleanup()



def paint_layout(desktop):
    """Native LayoutMain geometry, in owned-window pixels below TitleBar."""
    width, height = desktop.actual_size
    height -= 56
    pad = max(6, min(20, min(width, height) // 40))
    gap = max(4, min(10, min(width, height) // 80))
    if height > width:
        tw = (width - pad * 2 - gap * 2) // 3
        th = max(44, min(110, tw * 3 // 4))
        cw = width - pad * 2
        ch = cw * 3 // 4
        room = height - pad * 3 - gap * 2 - th * 3
        if ch > room:
            ch, cw = room, room * 4 // 3
        cx, cy = (width - cw) // 2, pad
        below = cy + ch + pad
        top = below + (height - pad - below - th * 3 - gap * 2) // 2
        tools = [(pad + i % 3 * (tw + gap), top + i // 3 * (th + gap)) for i in range(9)]
    else:
        columns = 2 if height < 440 else 1
        rows = 5 if columns == 2 else 9
        th = (height - pad * 2 - gap * (rows - 1)) // rows
        tw = max(64, min(th * 5 // 2, width // (8 if columns == 2 else 5)))
        rail = tw * columns + gap * (columns - 1)
        cw, room = width - pad * 3 - rail, height - pad * 2
        ch = cw * 3 // 4
        if ch > room:
            ch, cw = room, room * 4 // 3
        left = (width - rail - pad - cw) // 2
        cx, cy = left + rail + pad, pad + (room - ch) // 2
        top = cy + (ch - th * rows - gap * (rows - 1)) // 2
        tools = [(left + i % columns * (tw + gap), top + i // columns * (th + gap)) for i in range(9)]
    return (cx, cy, cw, ch), [(x + tw / 2, y + th / 2 + 56) for x, y in tools]


def stencil_layout(desktop):
    """Picker hit rectangles in actual window pixels; legacy dialogs stay virtual."""
    width, total = desktop.actual_size
    height = total - 56
    pad, gap = (8, 6) if height < 440 else (16, 10)
    cols, tab_cols = (2, 2) if width < 600 else (3, 4)
    rows = 6 // cols
    tab_y = pad + 30 + gap
    tab_w = (width - pad * 2 - gap * (tab_cols - 1)) // tab_cols
    grid_y = tab_y + 4 // tab_cols * (44 + gap)
    footer_y = height - pad - 44
    card_w = (width - pad * 2 - gap * (cols - 1)) // cols
    card_h = (footer_y - gap - grid_y - gap * (rows - 1)) // rows
    footer_w = (width - pad * 2 - gap * 2) // 3
    return {
        'category': [(pad + i % tab_cols * (tab_w + gap), 56 + tab_y + i // tab_cols * (44 + gap), tab_w, 44) for i in range(4)],
        'tile': [(pad + i % cols * (card_w + gap), 56 + grid_y + i // cols * (card_h + gap), card_w, card_h) for i in range(6)],
        'previous': [(pad, 56 + footer_y, footer_w, 44)],
        'next': [(width - pad - footer_w, 56 + footer_y, footer_w, 44)],
    }


def stencil_click(desktop, kind='tile', index=0):
    x, y, w, h = stencil_layout(desktop)[kind][index]
    desktop.click_actual(x + w / 2, y + h / 2)


def tool(desktop, index):
    desktop.click_actual(*paint_layout(desktop)[1][index])


def pixel_click(desktop, x, y):
    left, top, width, height = paint_layout(desktop)[0]
    desktop.click_actual(left + (x + .5) * width / 960, 56 + top + (y + .5) * height / 720)


def open_slots(desktop):
    tool(desktop, 4)
    desktop.capture("paint-gallery", header=56)
    desktop.click(250, 38)
    desktop.capture("paint-slots", header=56)

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


def _history(folder):
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


def history(folder):
    # working.txt is atomically replaced before its bound sidecar. Wait for
    # both documents to settle instead of mistaking that frame for corruption.
    deadline = time.monotonic() + 10
    while True:
        try:
            return _history(folder)
        except (FileNotFoundError, AssertionError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(.1)


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
    tool(desktop, 6)
    if scenery(expected) == scenery(before):
        time.sleep(.6)
        assert working.read_bytes() == before, "Undo changed a picture with no history left"
    else:
        assert scenery(changed(working, before)) == scenery(expected), "Undo restored a different picture"


def fill(desktop, working, swatch):
    before = working.read_bytes()
    tool(desktop, 1)
    desktop.capture("paint-history-colors", header=56)
    desktop.click(38 + swatch % 7 * 41, 40 + swatch // 7 * 23)
    pixel_click(desktop, 20, 20)
    return changed(working, before)


def ui():
    binary = ROOT / "build/app/jungle"
    WORK.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="history-", dir=WORK) as temporary:
        root = Path(temporary)
        data = root / "data"
        folder = data / "games/jungle.paint"
        working = folder / "working.txt"
        pictures = []
        with Desktop(binary, data) as desktop:
            desktop.game("Coloring Book")
            desktop.wait_scene_picker("paint-history-scenes")
            from paint_library_test import scene_click
            scene_click(desktop)
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
            open_slots(desktop)
            desktop.capture("paint-history-save", header=56)
            desktop.click(50, 80)
            deadline = time.monotonic() + 10
            while not (paint / "slot-0.txt").exists() and time.monotonic() < deadline:
                time.sleep(.1)
            assert scenery((paint / "slot-0.txt").read_bytes()) == scenery(pictures[9])
            assert same(history(paint), pictures[2:9]), "saving a slot changed the history"
            open_slots(desktop)
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

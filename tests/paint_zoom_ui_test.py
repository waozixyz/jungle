#!/usr/bin/env python3
"""The Coloring Book's picture zooms and pans with the Zoom tool, the wheel and a
right-button drag, in wide, short and tall windows. Its lines stay sharp, a tap
while zoomed fills the page point under it, and Fit returns the same picture.
Uses only disposable saves and an owned private Xvfb."""
import subprocess
import tempfile
import time
from pathlib import Path

import runtime_test
from paint_history_test import Desktop, WORK, changed, paint_layout, pixel_click, tool
from paint_geometry import scene_click
from runtime_test import ROOT

ZOOM_TOOL = 10
BINARY = ROOT / "build/app/jungle"
HEADER = 56


def canvas(desktop, name):
    """The picture's own window pixels, in grays."""
    from PIL import Image
    desktop.capture(name, header=HEADER)
    left, top, width, height = paint_layout(desktop)[0]
    with Image.open(runtime_test.OUTPUT / (name + ".png")) as actual:
        return actual.convert("L").crop((left, HEADER + top, left + width, HEADER + top + height))


def difference(a, b):
    from PIL import ImageChops
    assert a.size == b.size, (a.size, b.size)
    histogram = ImageChops.difference(a, b).histogram()
    return sum(histogram[24:]) / (a.width * a.height)


def blur(picture):
    """How many pixels are edge grays for each black one; soft lines have more."""
    histogram = picture.histogram()
    black, gray = sum(histogram[:48]), sum(histogram[48:208])
    assert black > 0, "the picture shows no lines"
    return gray / black


def control(desktop, index):
    """The middle of a zoom control: 0 Fit, 1 zoom in, 2 zoom out."""
    left, top, width, _ = paint_layout(desktop)[0]
    return left + width - (index + 1) * 50 + 22, HEADER + top + 6 + 22


def middle(desktop):
    left, top, width, height = paint_layout(desktop)[0]
    return left + width // 2, HEADER + top + height // 2


def xdo(desktop, *command):
    subprocess.run(["xdotool", *map(str, command)], env=desktop.env, check=True, timeout=10)


def lake(desktop):
    """A window point on open paper in the first scene, away from its lines."""
    left, top, width, height = paint_layout(desktop)[0]
    return left + 480.5 * width / 960, HEADER + top + 540.5 * height / 720


def wheel(desktop, button, times, point=None):
    x, y = point or middle(desktop)
    xdo(desktop, "mousemove", "--window", desktop.window, x, y)
    for _ in range(times):
        xdo(desktop, "click", button)
        time.sleep(.05)
    time.sleep(.6)


def settle():
    # Longer than the time the picture's sharp ink waits for the view to settle.
    time.sleep(.6)


def start(desktop, working):
    desktop.game("Coloring Book")
    desktop.wait_scene_picker("paint-zoom-scenes")
    scene_click(desktop)
    changed(working, b"")
    desktop.key("Escape")
    settle()


def crayon(desktop):
    """A green crayon, since the first one matches the empty page."""
    tool(desktop, 1)
    desktop.capture("paint-zoom-colors", header=HEADER)
    desktop.click(38 + 3 * 41, 40)
    settle()


def views(desktop, working, tag):
    fit = canvas(desktop, f"paint-zoom-{tag}-fit")
    saved = working.read_bytes()
    fit_blur = blur(fit)

    # The wheel zooms in about the pointer, and the lines stay sharp.
    wheel(desktop, 4, 12)
    zoomed = canvas(desktop, f"paint-zoom-{tag}-wheel")
    assert difference(fit, zoomed) > .01, f"{tag}: the wheel did not zoom"
    assert blur(zoomed) < max(fit_blur, .5) * 1.5, f"{tag}: zoomed lines are soft: {blur(zoomed)} against {fit_blur}"

    # A right-button drag pans.
    x, y = middle(desktop)
    xdo(desktop, "mousemove", "--window", desktop.window, x, y)
    xdo(desktop, "mousedown", 3)
    time.sleep(.2)
    xdo(desktop, "mousemove", "--window", desktop.window, x - 90, y - 60)
    time.sleep(.2)
    xdo(desktop, "mouseup", 3)
    settle()
    panned = canvas(desktop, f"paint-zoom-{tag}-pan")
    assert difference(zoomed, panned) > .005, f"{tag}: the right button did not pan"

    # Fit returns the same picture.
    desktop.click_actual(*control(desktop, 0))
    settle()
    assert difference(fit, canvas(desktop, f"paint-zoom-{tag}-refit")) < .01, f"{tag}: Fit shows a different picture"

    # The Zoom tool shows its buttons, and its drag pans instead of painting.
    tool(desktop, ZOOM_TOOL)
    settle()
    desktop.click_actual(*control(desktop, 1))
    desktop.click_actual(*control(desktop, 1))
    settle()
    closer = canvas(desktop, f"paint-zoom-{tag}-tool")
    assert difference(fit, closer) > .01, f"{tag}: zoom in did nothing"
    x, y = middle(desktop)
    xdo(desktop, "mousemove", "--window", desktop.window, x, y)
    xdo(desktop, "mousedown", 1)
    time.sleep(.2)
    xdo(desktop, "mousemove", "--window", desktop.window, x + 70, y + 50)
    time.sleep(.2)
    xdo(desktop, "mouseup", 1)
    settle()
    assert difference(closer, canvas(desktop, f"paint-zoom-{tag}-drag")) > .005, f"{tag}: the Zoom tool did not pan"
    desktop.click_actual(x, y)
    settle()
    assert working.read_bytes() == saved, f"{tag}: zooming changed the picture"
    desktop.click_actual(*control(desktop, 2))
    desktop.click_actual(*control(desktop, 2))
    settle()
    tool(desktop, ZOOM_TOOL)
    settle()
    # Zooming all the way out is Fit again, and the Fit button leaves.
    assert difference(fit, canvas(desktop, f"paint-zoom-{tag}-out")) < .01, f"{tag}: zooming out missed the fit"
    assert working.read_bytes() == saved, f"{tag}: zooming changed the picture"
    print(f"local UI test: wheel, pan, Zoom tool and Fit work in the {tag} window", flush=True)


def drag(desktop, start, to):
    xdo(desktop, "mousemove", "--window", desktop.window, round(start[0]), round(start[1]))
    time.sleep(.2)
    xdo(desktop, "mousedown", 1)
    time.sleep(.2)
    middle_point = (start[0] + to[0]) / 2, (start[1] + to[1]) / 2
    xdo(desktop, "mousemove", "--window", desktop.window, round(middle_point[0]), round(middle_point[1]))
    time.sleep(.2)
    xdo(desktop, "mousemove", "--window", desktop.window, round(to[0]), round(to[1]))
    time.sleep(.3)
    xdo(desktop, "mouseup", 1)
    time.sleep(.4)


def page_scale(desktop):
    return paint_layout(desktop)[0][2] / 960


def zoomed_point(point, pivot, notches):
    """Where a fitted window point lies after the wheel zooms about pivot."""
    zoom = 1.2 ** notches
    return pivot[0] + (point[0] - pivot[0]) * zoom, pivot[1] + (point[1] - pivot[1]) * zoom


def pencil_stays_aligned(root):
    data = root / "pencil"
    working = data / "games/jungle.paint/working.txt"
    with Desktop(BINARY, data) as desktop:
        start(desktop, working)
        notches = 6
        point = lake(desktop)
        wheel(desktop, 4, notches, point)
        tool(desktop, 9)
        settle()
        before = working.read_bytes()
        drag(desktop, point, (point[0] + 120, point[1]))
        changed(working, before)
        tool(desktop, 9)
        settle()
        desktop.click_actual(*control(desktop, 0))
        settle()
        # 120 window pixels at this zoom are about 40 once fitted.
        picture = canvas(desktop, "paint-zoom-pencil")
        left, top = paint_layout(desktop)[0][:2]
        across = 120 / 1.2 ** notches
        row = round(point[1]) - HEADER - top
        column = lambda x: round(point[0] + x) - left
        dark = lambda x: min(picture.getpixel((column(x), row + offset)) for offset in range(-3, 4)) < 110
        assert all(dark(across * part) for part in (.1, .5, .9)), "the line left the pointer's page points"
        assert not dark(across + 8) and not dark(-8), "the line is longer than the drag"
    print("local UI test: a pencil line drawn while zoomed stays on the pointer's page points", flush=True)


def rotation_handle_stays_aligned(root):
    import numpy as np
    from paint_library_test import document, object_records, rotation_handle, setup
    base = np.full((720, 960), 22, np.uint8)
    paint = np.full((90, 50), 40, np.uint8)
    obj = (440, 320, paint)
    data = root / "rotate"
    data.mkdir()
    initial = document(base, [obj])
    _, working = setup(data, "en", initial)
    with Desktop(BINARY, data) as desktop:
        desktop.game("Coloring Book")
        settle()
        settle()
        tool(desktop, 8)
        pixel_click(desktop, 465, 365)
        center, handle = rotation_handle(desktop, obj)
        notches = 3
        wheel(desktop, 4, notches, center)
        settle()
        handle = zoomed_point(handle, center, notches)
        radius = center[1] - handle[1]
        drag(desktop, handle, (center[0] + radius, center[1]))
        rotated = object_records(changed(working, initial))[0][2]
        assert abs(rotated.shape[0] - 50) <= 2 and abs(rotated.shape[1] - 90) <= 2, f"rotated to {rotated.shape}"
    print("local UI test: the rotation handle answers where it is drawn while zoomed", flush=True)


def placed(root, name, gesture=None):
    """A stencil placed on an empty page, after an optional gesture while zoomed."""
    from paint_geometry import stencil_click
    from paint_layers_test import HEADER as PICTURE, runs
    from paint_library_test import object_records, placement_click
    import numpy as np
    data = root / name
    folder = data / "games/jungle.paint"
    folder.mkdir(parents=True)
    working = folder / "working.txt"
    original = PICTURE.replace(b"PICTURE 3", b"PICTURE 2") + runs(np.full((720, 960), 22, np.uint8)) + b"\n"
    working.write_bytes(original)
    (folder / "choices.txt").write_bytes(b"JUNGLE PAINT CHOICES 1\n10020000")
    with Desktop(BINARY, data) as desktop:
        desktop.game("Coloring Book")
        settle()
        settle()
        tool(desktop, 0)
        stencil_click(desktop)
        settle()
        if gesture:
            gesture(desktop)
        placement_click(desktop)
        record = object_records(changed(working, original))[0]
    return record[0], record[1], record[2].shape[1], record[2].shape[0]


def placement_stays_aligned(root):
    x, y, w, h = placed(root, "place-fit")
    notches = 2
    zoom = 1.2 ** notches

    def move(desktop):
        wheel(desktop, 4, notches)
        settle()
        here = middle(desktop)
        drag(desktop, here, (here[0] + 60, here[1] + 40))
        move.scale = page_scale(desktop) * zoom

    moved_x, moved_y, moved_w, moved_h = placed(root, "place-move", move)
    assert abs(moved_x - x - 60 / move.scale) <= 3 and abs(moved_y - y - 40 / move.scale) <= 3, \
        f"a drag while zoomed moved {moved_x - x},{moved_y - y} page pixels"
    assert (moved_w, moved_h) == (w, h), "moving changed the stencil's size"

    def resize(desktop):
        wheel(desktop, 4, notches)
        settle()
        here = middle(desktop)
        scale = page_scale(desktop) * zoom
        corner = here[0] + w * scale / 2, here[1] + h * scale / 2
        resize.scale = scale
        drag(desktop, corner, (corner[0] - 40, corner[1] - 40 * h / w))

    resized_x, resized_y, resized_w, resized_h = placed(root, "place-resize", resize)
    # The dragged corner follows the pointer and the opposite one stays put.
    assert abs(resized_w - (w - 40 / resize.scale)) <= 6, f"a corner drag while zoomed made width {resized_w} from {w}"
    assert abs(resized_x - x) <= 4 and abs(resized_y - y) <= 4, "the opposite corner moved"
    print("local UI test: a stencil moves and resizes under the pointer while zoomed", flush=True)


def ui():
    WORK.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="zoom-", dir=WORK) as temporary:
        root = Path(temporary)
        # A fill at the page's middle, at fit.
        data = root / "fit"
        working = data / "games/jungle.paint/working.txt"
        with Desktop(BINARY, data) as desktop:
            start(desktop, working)
            crayon(desktop)
            before = working.read_bytes()
            pixel_click(desktop, 480, 540)
            fitted = changed(working, before)
        # The same fill through a zoomed picture is the same document.
        data = root / "zoomed"
        working = data / "games/jungle.paint/working.txt"
        with Desktop(BINARY, data) as desktop:
            start(desktop, working)
            crayon(desktop)
            before = working.read_bytes()
            wheel(desktop, 4, 8, lake(desktop))
            desktop.click_actual(*lake(desktop))
            assert changed(working, before) == fitted, "a tap while zoomed filled a different page point"
            # Far enough out to show the lines around the filled lake.
            wheel(desktop, 5, 5, lake(desktop))
            settle()
            filled = canvas(desktop, "paint-zoom-filled")
            assert blur(filled) < 3.0, "fills and lines blur together while zoomed"
            desktop.key("Escape")
        print("local UI test: a tap while zoomed fills the same page point", flush=True)
        pencil_stays_aligned(root)
        rotation_handle_stays_aligned(root)
        placement_stays_aligned(root)
        for tag, size in (("wide", None), ("short", (800, 500)), ("tall", (600, 900))):
            data = root / tag
            working = data / "games/jungle.paint/working.txt"
            with Desktop(BINARY, data, screen_size="1280x1000") as desktop:
                start(desktop, working)
                if size:
                    desktop.resize(*size)
                    settle()
                views(desktop, working, tag)


if __name__ == "__main__":
    ui()
    print("local UI test: Coloring Book zoom and pan passed", flush=True)

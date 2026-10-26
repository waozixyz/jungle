#!/usr/bin/env python3
"""Exercise Jungle's real host with disposable saves and an owned Xvfb."""

import argparse
import os
from pathlib import Path
import select
import shutil
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "build/tests/ui"


def environment():
    env = os.environ.copy()
    for key in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY",
                "DBUS_SESSION_BUS_ADDRESS", "SESSION_MANAGER"):
        env.pop(key, None)
    env.update(YUE_DESKTOP_RECOVERY="0", SDL_AUDIODRIVER="dummy",
               LIBGL_ALWAYS_SOFTWARE="1")
    return env


def run(command, env):
    return subprocess.run(command, env=env, text=True, capture_output=True,
                          check=True, timeout=15).stdout.strip()


def check_saves(binary):
    with tempfile.TemporaryDirectory(prefix="jungle-runtime-") as temporary:
        data = Path(temporary)
        progress = data / "games/jungle.animals/progress.txt"
        progress.parent.mkdir(parents=True)
        original = "animal 4 23 2 1\n"
        progress.write_text(original)
        env = environment()
        env["JUNGLE_DATA"] = str(data)
        before = sorted(str(path.relative_to(data)) for path in data.rglob("*"))
        run([str(binary), "--check"], env)
        assert progress.read_text() == original, "--check overwrote counting progress"
        assert sorted(str(path.relative_to(data)) for path in data.rglob("*")) == before, "--check created save data"
        print("local runtime test: --check preserves saved progress", flush=True)


class Desktop:
    def __init__(self, binary, data, extra_env=None, screen_size="1280x800"):
        self.env = environment()
        self.env.update(extra_env or {})
        self.binary = binary
        self.data = data
        self.server = None
        self.app = None
        self.logs = []
        self.screen_size = screen_size

    def __enter__(self):
        OUTPUT.mkdir(parents=True, exist_ok=True)
        readfd, writefd = os.pipe()
        log = (OUTPUT / "xvfb.log").open("w")
        self.logs.append(log)
        try:
            self.server = subprocess.Popen(
                ["Xvfb", "-displayfd", str(writefd), "-screen", "0",
                 self.screen_size + "x24", "-nolisten", "tcp", "-ac"],
                pass_fds=(writefd,), env=self.env, stdout=log, stderr=log)
        finally:
            os.close(writefd)
        try:
            ready, _, _ = select.select([readfd], [], [], 10)
            assert ready, "private Xvfb did not become ready"
            number = os.read(readfd, 32).decode().strip()
            assert number.isdigit(), "private Xvfb failed; see build/tests/ui/xvfb.log"
            self.env["DISPLAY"] = ":" + number
            self.env["JUNGLE_DATA"] = str(self.data)
            # Capture approval is based on this actual owned server process,
            # including its -displayfd pipe, never on a display number alone.
            self.verify_server()
            print(f"private Xvfb pid={self.server.pid} display={self.env['DISPLAY']}", flush=True)
            log = (OUTPUT / "jungle.log").open("w")
            self.logs.append(log)
            self.app = subprocess.Popen([str(self.binary)], env=self.env,
                                        stdout=log, stderr=log)
            for _ in range(100):
                self.alive()
                result = subprocess.run(
                    ["xdotool", "search", "--onlyvisible", "--pid", str(self.app.pid),
                     "--name", "^Jungle Academy$"], env=self.env,
                    capture_output=True, text=True, timeout=2)
                if result.returncode == 0:
                    self.window = result.stdout.splitlines()[0]
                    run(["xdotool", "windowfocus", self.window], self.env)
                    return self
                time.sleep(.1)
            raise AssertionError("Jungle Academy did not open its window")
        except BaseException:
            self.__exit__(None, None, None)
            raise
        finally:
            os.close(readfd)

    def verify_server(self):
        assert self.server.poll() is None, "private Xvfb exited"
        command = Path(f"/proc/{self.server.pid}/cmdline").read_bytes().split(b"\0")
        assert Path(os.fsdecode(command[0])).name == "Xvfb"
        assert b"-displayfd" in command and (self.screen_size + "x24").encode() in command

    def alive(self):
        assert self.app.poll() is None, "Jungle exited; see build/tests/ui/jungle.log"

    def key(self, key):
        run(["xdotool", "key", "--clearmodifiers", key], self.env)
        time.sleep(.18)
        self.alive()

    def click(self, x, y, button=1):
        run(["xdotool", "mousemove", "--window", self.window,
             str(round(x * self.scale + self.left)),
             str(round(y * self.scale + self.top))], self.env)
        run(["xdotool", "click", str(button)], self.env)
        time.sleep(.3)
        self.alive()

    def move(self, x, y):
        run(["xdotool", "mousemove", "--window", self.window,
             str(round(x * self.scale + self.left)),
             str(round(y * self.scale + self.top))], self.env)
        time.sleep(.15)

    def drag(self, x, y, to_x, to_y, mirror=False):
        self.move(x, y)
        run(["xdotool", "mousedown", "1"], self.env)
        try:
            time.sleep(.15)
            self.move(to_x, to_y)
            if mirror:
                run(["xdotool", "mousedown", "3"], self.env)
                time.sleep(.15)
        finally:
            run(["xdotool", "mouseup", "1"], self.env)
            time.sleep(.2)
            if mirror:
                run(["xdotool", "mouseup", "3"], self.env)
        time.sleep(.3)
        self.alive()

    def type(self, text):
        run(["xdotool", "type", "--clearmodifiers", "--delay", "60", text], self.env)
        time.sleep(.3)
        self.alive()

    def click_actual(self, x, y, button=1):
        run(["xdotool", "mousemove", "--window", self.window, str(x), str(y)], self.env)
        run(["xdotool", "click", str(button)], self.env)
        time.sleep(.3)
        self.alive()

    def resize(self, width, height):
        run(["xdotool", "windowsize", "--sync", self.window, str(width), str(height)], self.env)
        time.sleep(.5)
        self.alive()

    def capture_actual(self, name):
        self.capture(name)
        from PIL import Image
        return Image.open(OUTPUT / (name + ".png")).convert("RGB")

    def capture(self, name):
        self.verify_server()
        self.alive()
        time.sleep(.25)
        path = OUTPUT / (name + ".png")
        run(["import", "-display", self.env["DISPLAY"], "-window",
             self.window, str(path)], self.env)
        from PIL import Image
        picture = Image.open(path).convert("RGB")
        # Jungle opens windowed at a default integral scale.
        header = 56 if picture.height > 56 and picture.getpixel((0,55)) == (218,205,181) else 0
        scale = min(picture.width / 320, (picture.height - header) / 200)
        left = (picture.width - 320 * scale) / 2
        top = header + (picture.height - header - 200 * scale) / 2
        self.scale, self.left, self.top = scale, left, top
        return picture.crop(tuple(round(v) for v in (left, top, left + 320 * scale, top + 200 * scale))).resize(
            (320, 200), Image.Resampling.NEAREST)

    def wait_book(self, name):
        # A complete offline speech library is larger than the original book;
        # wait for its real first frame before sending further input.
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            picture = self.capture(name)
            if picture.getpixel((0, 0)) == (227, 236, 228) and (0, 0, 170) not in [c for _, c in picture.crop((20,42,45,64)).getcolors(10000)]:
                return picture
            time.sleep(.1)
        raise AssertionError("Picture Book did not reach its first frame")

    def wait_menu(self, name):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            picture = self.capture(name)
            if picture.getpixel((0, 0)) == (227, 236, 228) and (0, 0, 170) in [c for _, c in picture.crop((20,42,45,64)).getcolors(10000)]:
                return picture
            time.sleep(.1)
        raise AssertionError("Jungle did not return to its menu")

    def __exit__(self, *unused):
        for process in (self.app, self.server):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        for log in self.logs:
            log.close()


PICTURE_HEADER = b"JUNGLE PICTURE 2\n"
DIGITS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_"
CANVAS = (960, 720)


def read_picture(path):
    data = path.read_bytes()
    assert data.startswith(PICTURE_HEADER), "save is not a complete picture"
    head = len(PICTURE_HEADER)
    story = data[head + 3:head + 3 + 8 * 39].decode("ascii").splitlines()
    return data, story


def run_number(text, at):
    value = shift = 0
    while True:
        digit = DIGITS.index(text[at])
        at += 1
        value |= (digit & 31) << shift
        shift += 5
        if digit < 32:
            return value, at


def picture_pixels(data):
    """A saved picture's crayon indices, decoded from its runs."""
    import numpy
    text = data[len(PICTURE_HEADER) + 3 + 8 * 39:-1].decode("ascii")
    pixels, at = [], 0
    while at < len(text):
        color = DIGITS.index(text[at])
        length, at = run_number(text, at + 1)
        pixels.append(numpy.full(length, color, numpy.uint8))
    return numpy.concatenate(pixels).reshape(CANVAS[1], CANVAS[0])


def dinosaur_masks(dino, size):
    """Ink and body masks of a dinosaur size, from games/paint/paint_pages.zi."""
    import numpy
    import re
    source = (ROOT / "games/paint/paint_pages.zi").read_text()
    table = lambda name: [int(v) for v in re.search(name + r": \[\d+\]s32 = \.\[([^\]]*)\]", source).group(1).split(",")]
    starts = table("MASK_START")
    chunks = dict(re.findall(r'^MASK_(\d+) :: "([^"]*)"', source, re.M))
    index = dino * 4 + size - 1
    width, height = table("DINO_WIDTH")[index], table("DINO_HEIGHT")[index]
    masks = []
    for mask in (6 + index * 2, 7 + index * 2):
        text = "".join(chunks[str(chunk)] for chunk in range(starts[mask], starts[mask + 1]))
        bits, ink, at = [], False, 0
        while at < len(text):
            length, at = run_number(text, at)
            bits.append(numpy.full(length, ink))
            ink = not ink
        masks.append(numpy.concatenate(bits).reshape(height, width))
    return masks


def assert_dinosaur(before, after, mirror=False):
    """Compare an actual Huge T-rex placement with its compiled ink and body.
    Returns where it was placed."""
    import numpy
    old, new = picture_pixels(before), picture_pixels(after)
    ink, body = dinosaur_masks(0, 4)
    if mirror:
        ink, body = ink[:, ::-1], body[:, ::-1]
    height, width = ink.shape
    changed = numpy.argwhere(old != new)
    assert len(changed), "placing changed nothing"
    covers = ink | body
    columns = numpy.flatnonzero(covers.any(axis=0))
    rows = numpy.flatnonzero(covers.any(axis=1))
    for x in range(changed[:, 1].min() - columns[0] - 2, changed[:, 1].min() - columns[0] + 3):
        for y in range(changed[:, 0].min() - rows[0] - 2, changed[:, 0].min() - rows[0] + 3):
            if x < 0 or y < 0 or x + width > CANVAS[0] or y + height > CANVAS[1]:
                continue
            expected = old.copy()
            area = expected[y:y + height, x:x + width]
            area[body] = 15
            area[ink] = 0
            if numpy.array_equal(expected, new):
                return x, y
    raise AssertionError("placement did not replace exactly the dinosaur body")


def ui(binary):
    for tool in ("Xvfb", "xdotool", "import"):
        assert shutil.which(tool), f"UI tests need {tool}"
    from PIL import Image, ImageChops
    with tempfile.TemporaryDirectory(prefix="jungle-ui-") as temporary:
        data = Path(temporary)
        fake = data / "bin"
        fake.mkdir()
        printer = fake / "lp"
        printer.write_text("#!/usr/bin/env python3\nimport os,sys\nfrom pathlib import Path\n"
                           "p=Path(sys.argv[-1]);assert p.read_text().startswith('%!PS')\n"
                           "Path(os.environ['JUNGLE_PRINTER_LOG']).write_text(str(p))\n")
        printer.chmod(0o700)
        extra = {"PATH": str(fake) + os.pathsep + os.environ["PATH"],
                 "JUNGLE_PRINTER_LOG": str(data / "printed.txt")}
        with Desktop(binary, data, extra) as desktop:
            menu = desktop.capture("menu")
            desktop.click(250, 186)
            assert (data / "sound.txt").read_text() == "off\n", "menu mute was not saved"
            muted_menu = desktop.capture("menu-muted")
            desktop.key("F10")
            assert (data / "sound.txt").read_text() == "quiet\n", "F10 did not restore quiet sound"
            desktop.key("1")
            book = desktop.wait_book("book")
            assert book.getpixel((0, 0)) == (227, 236, 228), "Picture Book lost its cream background"
            desktop.key("d")
            book = desktop.capture("book-spelling-categories")
            desktop.key("Down")
            desktop.key("Return")
            pages = desktop.capture("book-pages")
            ink = (62, 51, 42)
            assert ink in [color for _, color in pages.crop((168, 57, 298, 96)).getcolors(10000)], "Picture Book did not show its large word"
            assert ink in [color for _, color in pages.crop((168, 103, 298, 125)).getcolors(10000)], "Picture Book did not show its spelling"
            desktop.key("Right")
            next_page = desktop.capture("book-next")
            assert ImageChops.difference(pages, next_page).getbbox(), "Picture Book did not turn the page"
            desktop.key("Left")
            desktop.key("Escape")
            desktop.key("Up")
            categories = desktop.capture("book-categories-return")
            assert ImageChops.difference(book, categories).getbbox() is None, "Picture Book did not return to categories"
            desktop.key("Escape")
            desktop.capture("menu-book-return")
            print("local UI test: Picture Book categories, pages and English names", flush=True)
            desktop.key("2")
            counting = desktop.capture("counting")
            assert counting.getpixel((0, 0)) == (227, 236, 228), "counting did not render its book background"
            progress = data / "games/jungle.animals/progress.txt"
            previous = 0
            for answer_index in range(6):
                counting = desktop.capture("counting")
                places = [(164,100),(132,100),(132,72),(164,72),(100,72),(100,100),(132,128),(164,128),
                          (100,128),(68,100),(68,72),(68,128),(36,72),(36,100),(36,128),(196,72),(196,100),(196,128)]
                background = Image.new("RGB", (24,20), (247,241,227))
                answer = sum(ImageChops.difference(counting.crop((x-12,y-10,x+12,y+10)), background).getbbox() is not None for x,y in places)
                assert 1 <= answer <= 4, "counting did not render its watercolor animals"
                assert answer != previous, "counting repeated a question"
                previous = answer
                desktop.key(str(answer))
                desktop.key("Return")
                saved = progress.read_text().split()
                assert int(saved[2]) == answer_index + 1, "a correct answer was not saved"
            assert saved[1:] == ["2", "6", "0", "0"], "six answers did not move up a level"
            for _ in range(6):
                desktop.key("0")
                desktop.key("Return")
            assert progress.read_text().split()[1:] == ["1", "6", "0", "0"], "six misses did not move down"
            desktop.key("Escape")
            desktop.key("Up")
            returned = desktop.capture("menu-return")
            assert ImageChops.difference(menu, returned).getbbox() is None, "counting did not return home"
            print("local UI test: watercolor counting artwork, questions, ladder and progress", flush=True)
            desktop.key("3")
            desktop.capture("paint-main")
            desktop.click(30, 15)
            scenes = desktop.capture("paint-scenes")
            assert scenes.getpixel((5, 5)) == (227, 236, 228), "scene picker did not render its book background"
            assert len(scenes.crop((19, 33, 97, 78)).getcolors(1 << 20)) > 1, "scene preview has no artwork"
            desktop.click(52, 58)
            desktop.capture("paint-dinosaurs")
            desktop.click(52, 58)
            desktop.capture("paint-sizes")
            desktop.click(280, 90)
            painting = desktop.capture("paint-placement")
            working = data / "games/jungle.paint/working.txt"
            scene_only = working.read_bytes()
            desktop.click(290, 170)
            hovering = desktop.capture("paint-placement-waiting")
            assert working.read_bytes() == scene_only, "clicking outside the box placed a dinosaur"
            box_edge = [color for _, color in hovering.crop((64, 5, 100, 9)).getcolors(10000)]
            assert (46, 105, 86) in box_edge, "placement box followed a hovering pointer"
            desktop.drag(72, 14, 102, 14)
            placed = desktop.capture("paint-placed")
            x, y = assert_dinosaur(scene_only, working.read_bytes())
            assert x > 60 and y == 0, f"the dinosaur did not move with the pointer: {x},{y}"
            assert ImageChops.difference(painting.crop((64, 6, 315, 194)),
                                        placed.crop((64, 6, 315, 194))).getbbox(), "Huge dinosaur could not be placed"
            black = dict((color, count) for count, color in placed.crop((64, 6, 315, 194)).getcolors(10000))
            assert black.get((0, 0, 0), 0) < 20000, "dinosaur outline rendered as a solid rectangle"
            once = working.read_bytes()
            desktop.click(30, 15)
            desktop.click(52, 58)
            desktop.click(280, 90)
            desktop.drag(72, 14, 117, 14)
            time.sleep(.5)
            assert_dinosaur(once, working.read_bytes())
            desktop.click(30, 160)
            assert working.read_bytes() == once, "second placement painted the ground or changed the selected stencil"
            desktop.click(30, 160)
            assert working.read_bytes() == scene_only, "Undo did not restore covered scene lines and colors"
            desktop.click(30, 15)
            desktop.click(52, 58)
            desktop.click(280, 90)
            desktop.drag(72, 14, 102, 14, mirror=True)
            desktop.capture("paint-mirrored")
            assert_dinosaur(scene_only, working.read_bytes(), mirror=True)
            desktop.click(30, 40)
            desktop.click(8, 160)
            desktop.capture("paint-color-cancelled")
            assert working.read_bytes() != scene_only, "color cancel removed the dinosaur"
            desktop.click(30, 40)
            colors = desktop.capture("paint-colors")
            assert len(colors.crop((256, 122, 308, 150)).getcolors(1 << 20)) >= 3, "crayon swatches are missing"
            assert colors.getpixel((282, 136)) == (192, 192, 192), "the last crayon is not its solid color"
            desktop.click(282, 136)
            desktop.click(71, 13)
            desktop.capture("paint-colored")
            desktop.click(30, 65)
            desktop.capture("paint-story")
            desktop.type("Roar (and friend)!")
            desktop.type("x")
            desktop.key("BackSpace")
            desktop.key("Down")
            desktop.key("Home")
            desktop.type("Second line")
            desktop.key("Return")
            desktop.click(30, 110)
            desktop.capture("paint-save")
            desktop.click(50, 80)
            slot = data / "games/jungle.paint/slot-0.txt"
            stored, story = read_picture(slot)
            (OUTPUT / "saved-picture.txt").write_bytes(stored)
            assert story[0].rstrip() == "Roar (and friend)!", repr(story)
            assert story[1].rstrip() == "Second line", repr(story)
            desktop.click(30, 90)
            desktop.capture("paint-erase")
            desktop.click(80, 85)
            desktop.click(30, 110)
            desktop.click(210, 38)
            desktop.click(50, 80)
            desktop.capture("paint-loaded")
            working = data / "games/jungle.paint/working.txt"
            assert working.read_bytes() == stored, "load lost the scene, story or dinosaur outlines"
            # Saving over a full slot must wait for an explicit confirmation.
            desktop.click(30, 65)
            desktop.key("Home")
            desktop.type("Changed")
            desktop.key("Return")
            desktop.click(30, 110)
            desktop.click(50, 80)
            desktop.capture("paint-overwrite")
            assert slot.read_bytes() == stored, "full slot was overwritten before confirmation"
            desktop.click(210, 134)
            desktop.key("Escape")
            assert slot.read_bytes() == stored, "cancelled overwrite changed the save"
            desktop.click(30, 110)
            desktop.click(50, 80)
            desktop.click(80, 134)
            assert slot.read_bytes() != stored, "confirmed overwrite was not stored"
            desktop.click(30, 135)
            desktop.capture("paint-print")
            desktop.click(120, 104)
            desktop.capture("paint-exported")
            exports = data / "games/jungle.paint/exports"
            assert len(list(exports.glob("*.png"))) == 1, "Export did not write its PNG"
            assert len(list(exports.glob("*.txt"))) == 1, "Export did not write its story"
            assert len(list(exports.glob("*.ps"))) == 1, "Export did not write its print page"
            shutil.copy2(next(exports.glob("*.png")), OUTPUT / "exported-picture.png")
            desktop.click(120, 140)
            desktop.capture("paint-printed")
            assert (data / "printed.txt").exists(), "Print did not submit the actual page"
            desktop.key("F10")
            assert (data / "sound.txt").read_text() == "off\n", "in-game mute did not persist"
            print("local UI test: dinosaur placement, crayons, edited stories, save/load, overwrite, export and print", flush=True)
            # On a tall window the picture spans the top and the tools sit in
            # two rows of four below it; Color is the second tool.
            desktop.key("Escape")
            desktop.resize(420, 700)
            tall = desktop.capture_actual("paint-portrait")
            width, height = tall.size
            height -= 56
            assert height > width, f"the window did not turn tall: {tall.size}"
            pad, gap = max(6, min(20, width // 40)), max(4, min(10, width // 80))
            tool_w = (width - pad * 2 - gap * 3) // 4
            tool_h = max(44, min(110, tool_w * 3 // 4))
            canvas_h = min((width - pad * 2) * 3 // 4, height - pad * 3 - gap - tool_h * 2)
            below = pad + canvas_h + pad
            top = below + (height - pad - below - tool_h * 2 - gap) // 2
            assert tall.getpixel((width // 2, 56 + pad + canvas_h // 2)) != (227, 236, 228), "the picture is not across the top"
            assert tall.getpixel((width // 2, 56 + below - pad // 2)) == (227, 236, 228), "the picture runs into the tools"
            desktop.click_actual(pad + tool_w + gap + tool_w // 2, 56 + top + tool_h // 2)
            shown = {color for _, color in desktop.capture_actual("paint-portrait-colors").getcolors(1 << 20)}
            crayons = {(0x82, 0x82, 0x82), (0x00, 0x00, 0xff), (0x00, 0xa2, 0xc3), (0xb2, 0x00, 0xcb), (0x00, 0xc3, 0x51),
                       (0xc3, 0x71, 0x00), (0xef, 0xef, 0x3c), (0x41, 0x41, 0xc0), (0x9a, 0x41, 0xa6), (0xc0, 0xc0, 0xc0)}
            assert len(crayons & shown) == len(crayons), "the Color tool is not below the picture in portrait"
            print("local UI test: portrait layout puts the tools below the picture", flush=True)
        # The complete working picture survives process restart without a slot.
        before = (data / "games/jungle.paint/working.txt").read_bytes()
        with Desktop(binary, data, extra) as desktop:
            restarted = desktop.capture("restart-menu")
            assert ImageChops.difference(muted_menu, restarted).getbbox() is None, "mute setting did not survive restart"
            desktop.key("3")
            desktop.capture("paint-recovered")
            assert (data / "games/jungle.paint/working.txt").read_bytes() == before
            print("local UI test: working picture recovers after restart", flush=True)
        legacy = data / "legacy"
        old = legacy / "games/jungle.math/progress.txt"
        old.parent.mkdir(parents=True)
        original = "skill 0 4 2 1\nskill 1 3 0 0\n"
        old.write_text(original)
        with Desktop(binary, legacy):
            migrated = legacy / "games/jungle.animals/progress.txt"
            assert migrated.read_text() == "animal 4 0 2 1\n"
            assert old.read_text() == original
            env = environment()
            env["JUNGLE_DATA"] = str(legacy)
            run([str(binary), "--check"], env)
            assert migrated.read_text() == "animal 4 0 2 1\n"
            print("local UI test: legacy counting migration and read-only validation", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/app/jungle")
    parser.add_argument("--ui", action="store_true")
    args = parser.parse_args()
    check_saves(args.binary.resolve())
    if args.ui:
        ui(args.binary.resolve())


if __name__ == "__main__":
    main()

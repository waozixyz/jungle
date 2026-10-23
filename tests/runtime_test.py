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
    def __init__(self, binary, data, extra_env=None):
        self.env = environment()
        self.env.update(extra_env or {})
        self.binary = binary
        self.data = data
        self.server = None
        self.app = None
        self.logs = []

    def __enter__(self):
        OUTPUT.mkdir(parents=True, exist_ok=True)
        readfd, writefd = os.pipe()
        log = (OUTPUT / "xvfb.log").open("w")
        self.logs.append(log)
        try:
            self.server = subprocess.Popen(
                ["Xvfb", "-displayfd", str(writefd), "-screen", "0",
                 "1280x800x24", "-nolisten", "tcp", "-ac"],
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
                    ["xdotool", "search", "--pid", str(self.app.pid),
                     "--name", "^Jungle$"], env=self.env,
                    capture_output=True, text=True, timeout=2)
                if result.returncode == 0:
                    self.window = result.stdout.splitlines()[0]
                    run(["xdotool", "windowfocus", self.window], self.env)
                    return self
                time.sleep(.1)
            raise AssertionError("Jungle did not open its window")
        except BaseException:
            self.__exit__(None, None, None)
            raise
        finally:
            os.close(readfd)

    def verify_server(self):
        assert self.server.poll() is None, "private Xvfb exited"
        command = Path(f"/proc/{self.server.pid}/cmdline").read_bytes().split(b"\0")
        assert Path(os.fsdecode(command[0])).name == "Xvfb"
        assert b"-displayfd" in command and b"1280x800x24" in command

    def alive(self):
        assert self.app.poll() is None, "Jungle exited; see build/tests/ui/jungle.log"

    def key(self, key):
        run(["xdotool", "key", "--clearmodifiers", key], self.env)
        time.sleep(.18)
        self.alive()

    def click(self, x, y, button=1):
        run(["xdotool", "mousemove", "--window", self.window,
             str(x * self.scale + self.left),
             str(y * self.scale + self.top)], self.env)
        run(["xdotool", "click", str(button)], self.env)
        time.sleep(.3)
        self.alive()

    def type(self, text):
        run(["xdotool", "type", "--clearmodifiers", "--delay", "60", text], self.env)
        time.sleep(.3)
        self.alive()

    def capture(self, name):
        self.verify_server()
        self.alive()
        time.sleep(.25)
        path = OUTPUT / (name + ".png")
        run(["import", "-display", self.env["DISPLAY"], "-window",
             self.window, str(path)], self.env)
        from PIL import Image
        picture = Image.open(path).convert("RGB")
        # WindowZoom chooses the largest integral scale fitting the display.
        scale = min(picture.width // 320, picture.height // 200)
        left = (picture.width - 320 * scale) // 2
        top = (picture.height - 200 * scale) // 2
        self.scale, self.left, self.top = scale, left, top
        return picture.crop((left, top, left + 320 * scale, top + 200 * scale)).resize(
            (320, 200), Image.Resampling.NEAREST)

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


def read_picture(path):
    data = path.read_bytes()
    assert data.startswith(b"JUNGLE PICTURE 1\n"), "save is not a complete picture"
    head = len(b"JUNGLE PICTURE 1\n")
    story = data[head + 3:head + 3 + 8 * 39].decode("ascii").splitlines()
    return data, story


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
            desktop.key("1")
            counting = desktop.capture("counting")
            assert counting.getpixel((0, 0)) == (0, 0, 170), "counting did not render its native blue background"
            places = [(164, 100), (132, 100), (132, 72), (164, 72),
                      (100, 72), (100, 100), (132, 128), (164, 128),
                      (100, 128), (68, 100), (68, 72), (68, 128),
                      (36, 72), (36, 100), (36, 128), (196, 72),
                      (196, 100), (196, 128)]
            progress = data / "games/jungle.animals/progress.txt"
            previous = 0
            for answer_index in range(6):
                counting = desktop.capture("counting")
                background = Image.new("RGB", (24, 20), (0, 0, 170))
                answer = sum(ImageChops.difference(counting.crop((x - 12, y - 10, x + 12, y + 10)),
                                                  background).getbbox() is not None for x, y in places)
                assert 1 <= answer <= 4, "counting did not render its native sprites"
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
            returned = desktop.capture("menu-return")
            assert ImageChops.difference(menu, returned).getbbox() is None, "counting did not return home"
            print("local UI test: native counting artwork, questions, ladder and progress", flush=True)
            desktop.key("2")
            desktop.capture("paint-main")
            desktop.click(30, 15)
            scenes = desktop.capture("paint-scenes")
            assert scenes.getpixel((5, 5)) == (255, 255, 255), "scene picker did not render"
            assert len(scenes.crop((19, 33, 97, 78)).getcolors()) > 1, "scene preview has no artwork"
            desktop.click(52, 58)
            desktop.capture("paint-dinosaurs")
            desktop.click(52, 58)
            desktop.capture("paint-sizes")
            desktop.click(280, 90)
            painting = desktop.capture("paint-placement")
            desktop.click(68, 11)
            placed = desktop.capture("paint-placed")
            assert ImageChops.difference(painting.crop((68, 10, 308, 190)),
                                        placed.crop((68, 10, 308, 190))).getbbox(), "Huge dinosaur could not be placed"
            black = dict((color, count) for count, color in placed.crop((68, 10, 308, 190)).getcolors(10000))
            assert black.get((0, 0, 0), 0) < 20000, "dinosaur outline rendered as a solid rectangle"
            desktop.click(30, 40)
            colors = desktop.capture("paint-colors")
            assert len(colors.crop((262, 128, 290, 142)).getcolors()) >= 2, "stippled crayons are missing"
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
            print("local UI test: dinosaur placement, crayons, edited stories, save/load, overwrite, export and print", flush=True)
        # The complete working picture survives process restart without a slot.
        before = (data / "games/jungle.paint/working.txt").read_bytes()
        with Desktop(binary, data, extra) as desktop:
            desktop.capture("restart-menu")
            desktop.key("2")
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

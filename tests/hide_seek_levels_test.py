#!/usr/bin/env python3
"""Focused rules and private-host verification for Hide & Seek levels."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from PIL import Image, ImageChops, ImageDraw, ImageStat, ImageOps

import runtime_test as rt

sys.path.insert(0, str(rt.ROOT / "tools"))
from book_catalog import WORDS  # noqa: E402

rt.OUTPUT = rt.ROOT / "work/hide-seek-levels/ui"
BINARY = rt.ROOT / "build/app/jungle"
MODEL = rt.ROOT / "games/hide_seek/hide_seek.zi"
SCREEN = rt.ROOT / "games/hide_seek/jungle_hide_seek.zi"
ANIMALS = ("frog", "rabbit", "cat", "dog", "monkey", "panda", "duck", "hen", "pig", "sheep", "tiger", "parrot")
CUES = ("peekaboo", "look_in", "look_behind", "look_under", "look_up", "in", "behind", "under", "up")
LANGUAGES = ("en", "de", "es")
SIZES = ((360, 720), (960, 600))
PREVIEW_SECONDS = 3.5
# Level names, the remembering prompt and its help, as shown.
WORDS_SHOWN = {
    "en": ("Peekaboo", "Find", "Remember", "Look and remember!", "Show again"),
    "de": ("Kuckuck", "Suchen", "Merken", "Schau und merk dir!", "Zeig nochmal"),
    "es": ("Cucú", "Buscar", "Recordar", "¡Mira y recuerda!", "Ver otra vez"),
}


def focused_build():
    subprocess.run(["make", "build/tests/hide_seek"], cwd=rt.ROOT, check=True)
    result = subprocess.run([str(rt.ROOT / "build/tests/hide_seek")], cwd=rt.ROOT, check=True, capture_output=True, text=True)
    assert BINARY.exists(), "build the stable host first: make build/app/jungle"
    bundle = rt.ROOT / "build/app/games/jungle-hide-seek.zx"
    assert bundle.exists() and bundle.stat().st_mtime >= max(MODEL.stat().st_mtime, SCREEN.stat().st_mtime), "wait for the parent coordinated app build"
    print("local hide & seek build: rules unit passed; coordinated hosted bundle is current", flush=True)
    return result.stdout



def check_art_pixels(receipt):
    """Real prop/cut-out pixels, driven by native geometry for every animal.

    These asset compositing tests complement the separate actual-host Xvfb
    suite. They do not claim to be captures of native host rendering.
    """
    feet = list(map(int, re.search(r"hide_animal_feet: \[12\]s32 = \.\[(.*?)\];", MODEL.read_text(), re.S).group(1).split(",")))
    records = [tuple(map(int, line.split()[1:])) for line in receipt.splitlines() if line.startswith("hide-art ")]
    assert len(records) == 480, len(records)
    props = [Image.open(rt.ROOT / f"assets/hide_seek/props/{name}.png").convert("RGBA")
             for name in ("basket", "bush", "table", "tree")]
    assert all(im.size == (1254, 1254) for im in props)
    animals = [Image.open(rt.ROOT / f"assets/jungle-book/items/{name}.png").convert("RGBA") for name in ANIMALS]
    ratios, panels = {}, {}
    for width, height, kind, frame, animal, x, y, edge, acx, base, ae, front, front_x, front_right in records:
        prop = props[kind].resize((edge, edge), Image.Resampling.LANCZOS)
        px, py = x + edge * front_x // 1254, y + edge * front // 1254
        foreground = Image.new("RGBA", (width, height))
        foreground.alpha_composite(prop.crop((px-x, py-y, edge*front_right//1254, edge)), (px, py))
        original = animals[animal]
        sprite = original.resize((ae, ae), Image.Resampling.LANCZOS)
        ax, ay = acx - ae // 2, base - ae * feet[animal] // 420
        assert ax >= 0 and ay >= 0 and ax + ae <= width and ay + ae <= height, (width, kind, ANIMALS[animal], "frame bounds")
        assert ay + ae * feet[animal] // 420 == base
        animal_layer = Image.new("RGBA", (width, height))
        animal_layer.alpha_composite(sprite, (ax, ay))
        alpha = animal_layer.getchannel("A")
        visible = ImageChops.multiply(alpha, ImageChops.invert(foreground.getchannel("A")))
        total = ImageStat.Stat(alpha).sum[0]
        ratio = ImageStat.Stat(visible).sum[0] / total
        ratios[width, kind, animal, frame] = ratio
        assert ratio >= .12, (width, kind, ANIMALS[animal], frame, "peek is too hard to see", ratio)
        if frame == 0:
            assert ratio < .85, (width, kind, ANIMALS[animal], "not hidden", ratio)
        if frame == 4:
            hidden = ratios[width, kind, animal, 0]
            assert ratio > hidden + .05, (width, kind, ANIMALS[animal], "reveal did not uncover body", hidden, ratio)
            assert ratio > .40, (width, kind, ANIMALS[animal], "reveal still obscured", ratio)
        if frame in (0, 4):
            picture = Image.new("RGBA", (width, height), "#e5ead5")
            if front or front_x or front_right < 1254:
                picture.alpha_composite(prop, (x, y))
            picture.alpha_composite(animal_layer)
            picture.alpha_composite(foreground)
            # Preserve all combinations for parent visual review, without
            # writing hundreds of individual private PNGs.
            box = (max(0, min(x, ax)-4), max(0, min(y, ay)-4),
                   min(width, max(x+edge, ax+ae)+4), min(height, max(y+edge, ay+ae)+4))
            tile = picture.crop(box).convert("RGB")
            tile.thumbnail((180, 190))
            panel = Image.new("RGB", (190, 214), "#fffaf0")
            panel.paste(tile, ((190-tile.width)//2, 20))
            ImageDraw.Draw(panel).text((4, 3), f"{ANIMALS[animal]} {'peek' if frame == 0 else 'shown'}", fill="black")
            panels[width, kind, animal, frame] = panel
    for width in (376, 893):
        for kind, name in enumerate(("basket", "bush", "table", "tree")):
            sheet = Image.new("RGB", (190*6, 214*4), "#fffaf0")
            for animal in range(12):
                for state, frame in enumerate((0, 4)):
                    index = animal*2+state
                    sheet.paste(panels[width, kind, animal, frame], ((index%6)*190, (index//6)*214))
            sheet.save(rt.OUTPUT.parent / f"{name}-all-animals-{width}.png")
    print("local hide & seek asset pixels: 12 animals x 4 props x 2 orientations x 5 reveal frames; partial body, larger reveal, fixed foot supports and bounded images passed", flush=True)

def check_words_and_voices():
    """Remembering names a friend with the picture book's word and clip."""
    model = MODEL.read_text()
    tables = {code: re.search(rf"hide_where_{code}: \[12\]string = \.\[(.*?)\];", model, re.S).group(1) for code in LANGUAGES}
    for code, table in tables.items():
        phrases = re.findall(r'"([^"]*)"', table)
        assert len(phrases) == len(ANIMALS) == len(set(phrases)), (code, phrases)
        for index, (animal, phrase) in enumerate(zip(ANIMALS, phrases)):
            word = WORDS[animal][LANGUAGES.index(code)]
            assert word.lower() in phrase.lower(), (code, animal, word, phrase)
            clip = rt.ROOT / f"assets/jungle-book/sounds/{code}/simple/{animal}.wav"
            assert clip.exists() and clip.with_suffix(".speech.json").exists(), clip
        for cue in CUES:
            assert (rt.ROOT / f"assets/hide_seek/sounds/{code}/{cue}.wav").exists(), (code, cue)
    listed = re.search(r"hide_animals: \[12\]string = \.\[(.*?)\];", model, re.S).group(1)
    assert tuple(re.findall(r'"([^"]*)"', listed)) == ANIMALS, listed
    screen = SCREEN.read_text()
    for code, shown in WORDS_SHOWN.items():
        assert all(text in model or text in screen for text in shown), (code, shown)
    for name in ("cottage-yard", "fenced-garden", "cozy-house", "farm-courtyard"):
        path = rt.ROOT / f"assets/hide_seek/scenes/{name}.png"
        assert path.exists() and min(Image.open(path).size) >= 1024, path
    print("local hide & seek words: friends, prompts and voice clips present in EN/DE/ES", flush=True)


def geometry(width, height):
    height -= 56
    scale = min(width / 400, height / 700) if width <= height else min(height / 520, width / 780)
    scale = max(.5, min(scale, 1.6))
    return scale, int(width / scale), int(height / scale)


def layout(width, height, mode=2):
    """Logical rectangles of the level, help and next buttons and the scene."""
    scale, w, h = geometry(width, height)
    two = w < 560
    controls_height = 124 if two else 66
    controls_y = h - controls_height - 12
    row = (controls_height - 8) // 2 if two else controls_height
    buttons = {}
    count = 3 if two else (5 if mode == 2 else 4)
    each = min(150, (w - 32 - 8 * (count - 1)) // count)
    x = (w - (each * count + 8 * (count - 1))) // 2
    for level in range(3):
        buttons[level] = (x + each / 2, controls_y + row / 2)
        x += each + 8
    y = controls_y + row / 2
    if two:
        y += row + 8
        actions = 2 if mode == 2 else 1
        each = min(190, (w - 32 - 8 * (actions - 1)) // actions)
        x = (w - (each * actions + 8 * (actions - 1))) // 2
    if mode == 2:
        buttons["help"] = (x + each / 2, y)
        x += each + 8
    buttons["next"] = (x + each / 2, y)
    return scale, w, h, buttons, (12, 84, w - 24, controls_y - 12 - 84)


def place_layout(width, height, places, place):
    """Same pure geometry as HideSeekSceneLayout; no time/reveal argument."""
    _, _, _, _, (left, top, w, h) = layout(width, height)
    tall = w < h
    columns = 2 if tall and places > 2 else places
    column, row = place % columns, place // columns
    slot = w // columns
    cx = slot * column + slot // 2
    ground = h * (82 if column % 2 == 0 else 90) // 100
    size, limit = slot * 64 // 100, h * 55 // 100
    if tall and places > 2:
        ground = h * (53 if row == 0 else 92) // 100
        cx += -slot // 16 if row == 0 else slot // 16
        limit = h * 27 // 100
    size = min(size, limit, 230, (ground - 12) * 100 // 160)
    return left + cx, top + ground, size


def place_center(width, height, places, place):
    cx, ground, size = place_layout(width, height, places, place)
    return cx, ground - size * .45


def save_path(data):
    return data / "games/jungle.hide_seek/hide_seek.txt"


def saved(data):
    path = save_path(data)
    assert path.exists(), "Hide & Seek did not write its isolated save"
    words = path.read_text().split()
    assert words[:2] == ["hideseek", "2"] and len(words) == 5, words
    return [int(value) for value in words[2:]]


class Screen:
    def __init__(self, desktop, data, language):
        self.d, self.data, self.language = desktop, data, language
        self.size = SIZES[0]

    def resize(self, size):
        self.size = size
        self.d.resize(*size)

    def click(self, x, y):
        scale = geometry(*self.size)[0]
        self.d.click_actual(round(x * scale), round(56 + y * scale))

    def button(self, name):
        self.click(*layout(*self.size, mode=saved(self.data)[0])[3][name])

    def capture(self, name):
        return self.d.capture_actual(f"hide-{self.language}-{name}-{self.size[0]}")


def open_hide_seek(screen):
    """Open the real game and wait for its actual first frame."""
    screen.d.game("Hide & Seek")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        frame = screen.capture("game-open")
        arrow = frame.crop((16, 16, 42, 42)).convert("RGB")
        ink = sum(max(color) < 170 for color in arrow.getdata())
        if ink >= 20:
            return frame
        time.sleep(.1)
    screen.capture("game-open-timeout")
    raise AssertionError("Hide & Seek did not paint its title-bar Back button")


def changed(before, after):
    return ImageChops.difference(before, after).getbbox() is not None


def remember_round(screen, label):
    """Preview counts nothing, hides, wrong places hint, Show again replays
    without progress, and the named friend is found by keyboard."""
    d, data = screen.d, screen.data
    level, found, remembered = saved(data)
    assert level == 2, saved(data)
    preview = screen.capture(f"{label}-preview")
    # Taps during the preview only bob the place.
    for place in range(4):
        screen.click(*place_center(*screen.size, 4, place))
    assert saved(data) == [2, found, remembered], ("preview mutated progress", saved(data))
    time.sleep(PREVIEW_SECONDS + .9)
    hidden = screen.capture(f"{label}-hidden")
    assert changed(preview, hidden), (label, "friends never hid")
    # Look through the places by keyboard until the named friend appears;
    # a wrong place never ends or counts the round.
    hints = 0
    for place in range(4):
        if place:
            d.key("Right")
        d.key("Return")
        state = saved(data)
        if state[2] == remembered + 1:
            break
        assert state == [2, found, remembered], state
        hints += 1
        if hints == 1:
            hint = screen.capture(f"{label}-hint")
            assert changed(hidden, hint), (label, "wrong place gave no hint")
            # Show again: the friends come back without changing progress.
            screen.button("help")
            again = screen.capture(f"{label}-show-again")
            assert changed(hint, again), (label, "Show again did not replay")
            assert saved(data) == [2, found, remembered], ("Show again mutated progress", saved(data))
            d.key("Return")  # ignored while showing
            assert saved(data) == [2, found, remembered], saved(data)
            time.sleep(PREVIEW_SECONDS + .9)
    else:
        raise AssertionError((label, "named friend never found", saved(data)))
    screen.capture(f"{label}-found")
    return remembered + 1


def find_round(screen, label):
    d, data = screen.d, screen.data
    level, found, remembered = saved(data)
    assert level == 1
    hidden = screen.capture(f"{label}-hidden")
    for place in range(3):
        if place:
            d.key("Right")
        d.key("Return")
        if saved(data)[1] == found + 1:
            break
        assert saved(data) == [1, found, remembered], saved(data)
    else:
        raise AssertionError((label, "finding friend never found", saved(data)))
    assert changed(hidden, screen.capture(f"{label}-found")), "Find never revealed its friend"
    return found + 1


def wait_state(data, expected, seconds=4):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if saved(data) == expected:
            return
        time.sleep(.05)
    raise AssertionError(("automatic progression", saved(data), expected))


def geometry_contract(screen):
    """Every touch center belongs to a bounded stage; props have fixed bases."""
    _, w, h, _, scene = layout(*screen.size)
    for count in (2, 3, 4):
        for place in range(count):
            cx, ground, size = place_layout(*screen.size, count, place)
            assert 12 < cx < w - 12 and scene[1] < ground < scene[1] + scene[3]
            assert ground - size * 1.60 >= scene[1]


def stage_crop(screen, frame):
    scale, _, _, _, (x, y, w, h) = layout(*screen.size)
    return frame.crop((round(x * scale), round(56 + y * scale),
                       round((x + w) * scale), round(56 + (y + h) * scale)))


def no_focus_rectangle(screen):
    """Arrow navigation must not paint a rectangular selection over the scene."""
    before = stage_crop(screen, screen.capture("focus-before"))
    screen.d.key("Right")
    after = stage_crop(screen, screen.capture("focus-after"))
    assert not changed(before, after), "keyboard navigation painted over the scene"
    # Reset the focus without depending on the previous keyboard-active state.
    screen.button("next")


def scene_image_present(screen):
    # A missing hosted asset draws a literal placeholder. Catch that in the
    # actual private raster instead of accepting merely present PNG files.
    frame = screen.capture("scene-loaded")
    stage = stage_crop(screen, frame)
    path = rt.OUTPUT / "scene-probe.png"
    stage.resize((stage.width * 2, stage.height * 2)).save(path)
    words = subprocess.run(["tesseract", str(path), "stdout", "--psm", "11"],
                           capture_output=True, text=True, check=True).stdout.lower()
    assert "missing image" not in words, "scene or hiding-place prop bitmap failed to load in the actual host"
    # This upper band is above every prop. Compare the actual host raster
    # with proportional image fitting, so a detailed stretched scene fails.
    scale = geometry(*screen.size)[0]
    band = (stage.width // 4, round(12 * scale), stage.width * 3 // 4, round(24 * scale))
    observed = stage.crop(band).convert('RGB')
    cover_errors, stretch_errors = [], []
    for source in (rt.ROOT/'assets/hide_seek/scenes').glob('*.png'):
        with Image.open(source) as image:
            image = image.convert('RGB')
            for target, expected in ((cover_errors, ImageOps.fit(image, stage.size, Image.Resampling.BILINEAR)),
                                     (stretch_errors, image.resize(stage.size, Image.Resampling.BILINEAR))):
                difference = ImageChops.difference(observed, expected.crop(band))
                target.append(sum(ImageStat.Stat(difference).mean) / 3)
    assert min(cover_errors) < 22, ('backdrop differs from proportional fitting', screen.size, cover_errors)
    if stage.width > stage.height * 1.3:
        assert min(cover_errors) + 3 < min(stretch_errors), ('landscape backdrop was stretched', cover_errors, stretch_errors)
    return stage


def language_pass(language, temporary, legacy=False):
    data = Path(temporary) / language
    data.mkdir()
    (data / "language.txt").write_text(language)
    save_path(data).parent.mkdir(parents=True)
    save_path(data).write_text("hideseek 1 1 4\n" if legacy else "hideseek 2 0 4 0\n")
    with rt.Desktop(BINARY, data, screen_size="1280x900") as d:
        screen = Screen(d, data, language)
        open_hide_seek(screen)
        screen.resize(SIZES[0])
        if legacy:
            screen.capture("legacy-find")
            assert save_path(data).read_text() == "hideseek 1 1 4\n", "legacy save changed on load"
        d.key("Escape")
        expected_mode = 1 if legacy else 0
        assert saved(data) == [expected_mode, 4, 0], saved(data)
        open_hide_seek(screen)
        found, remembered = 4, 0
        for size in SIZES:
            screen.resize(size)
            geometry_contract(screen)
            # Four consecutive manual rounds exercise the complete scene
            # rotation. Every actual raster must load its backdrop.
            stages = []
            for _ in range(4):
                screen.button("next")
                stage = scene_image_present(screen)
                stages.append(stage.crop((0, 0, stage.width, stage.height // 4)).tobytes())
            assert len(set(stages)) == 4, "scene rotation repeated a backdrop early"
            # All manual numbered buttons and keys keep the progress counts.
            for target in (0, 1, 2):
                screen.button(target)
                assert saved(data) == [target, found, remembered], (language, size, target, saved(data))
            # Manual touch controls remain available during a preview.
            screen.button(1)
            assert saved(data) == [1, found, remembered], "preview blocked manual level choice"
            screen.button(2)
            screen.button("next")
            assert saved(data) == [2, found, remembered], "preview blocked manual Next"
            screen.button(0)
            assert saved(data) == [0, found, remembered]
            no_focus_rectangle(screen)
            before = screen.capture("peekaboo-hidden")
            # Keyboard reveals every friend; no count increments in Peekaboo.
            # Three slots are possible. Extra Right/Return cannot count twice.
            for place in range(3):
                if place:
                    d.key("Right")
                d.key("Return")
                assert saved(data)[1:] == [found, remembered]
                # Once complete, stop before Enter's manual Next shortcut.
                # A completion changes only the prompt until the timer fires.
                if completion_visible(screen):
                    break
            else:
                raise AssertionError("Peekaboo never completed")
            shown = screen.capture("peekaboo-visible")
            assert changed(before, shown), "Peekaboo did not reveal"
            wait_state(data, [1, found, remembered])
            # No new input means no immediate second completion/level skip.
            time.sleep(.3)
            assert saved(data) == [1, found, remembered]
            found = find_round(screen, f"find-{size[0]}")
            # Hold a pointer across the round change, then release it over
            # the new scene. It must not activate a new round's hiding place.
            cx, cy = place_center(*size, 4, 0)
            scale = geometry(*size)[0]
            rt.run(["xdotool", "mousemove", "--window", d.window, str(round(cx * scale)), str(round(56 + cy * scale))], d.env)
            rt.run(["xdotool", "mousedown", "1"], d.env)
            try:
                wait_state(data, [2, found, remembered])
                time.sleep(.2)
            finally:
                rt.run(["xdotool", "mouseup", "1"], d.env)
            assert saved(data) == [2, found, remembered]
            # Remember's full preview, hidden state, hints, help and success.
            remembered = remember_round(screen, f"remember-{size[0]}")
            completed = screen.capture("remember-complete")
            time.sleep(2.8)
            assert saved(data) == [2, found, remembered], saved(data)
            renewed = screen.capture("remember-auto-preview")
            assert changed(completed, renewed), "Remember never started its new round"
            # Holding Enter across the transition/preview must not find a friend.
            rt.run(["xdotool", "keydown", "Return"], d.env)
            try:
                time.sleep(PREVIEW_SECONDS + .8)
                # Visit every target while Enter remains held: this catches
                # repeat carryover deterministically, not only when focus 0
                # happened to hide the randomly chosen friend.
                for _ in range(4):
                    assert saved(data) == [2, found, remembered], ("held Enter carried over", saved(data))
                    d.key("Right")
                assert saved(data) == [2, found, remembered], ("held Enter carried over", saved(data))
            finally:
                rt.run(["xdotool", "keyup", "Return"], d.env)
            # Manual Next can start over without changing level/counts.
            screen.button("next")
            assert saved(data) == [2, found, remembered], saved(data)
            screen.capture("manual-next-preview")
            # Replay/help starts the preview afresh without counting.
            screen.button("help")
            assert saved(data) == [2, found, remembered]
            d.key("Page_Up")
            assert saved(data) == [1, found, remembered]
            # Finish Find then manually Next before the timer: stay on Find.
            found = find_round(screen, "manual-find")
            screen.button("next")
            assert saved(data) == [1, found, remembered]
            time.sleep(2.8)
            assert saved(data) == [1, found, remembered], "old completion timer survived manual reset"
        # Reopen Remember mid-preview; old saves and counts stay compatible.
        d.key("3")
        before = save_path(data).read_text()
        d.key("Escape")
        assert save_path(data).read_text() == before
        open_hide_seek(screen)
        assert saved(data) == [2, found, remembered]
        screen.capture("reopened-preview")
        d.click_actual(28, 28)
        open_hide_seek(screen)
        assert saved(data) == [2, found, remembered]
        d.key("Escape")
    print(f"local hide & seek UI: {language} 3 modes x 2 orientations, auto/manual progression, held input, preview/help, old save and reopen passed", flush=True)


def completion_visible(screen):
    # Read the actual rendered completion words on this private window only.
    image = screen.capture("completion-probe")
    scale = geometry(*screen.size)[0]
    crop = image.crop((0, 56, image.width, round(56 + 84 * scale)))
    # OCR uses only this owned private capture and disposable project work.
    path = rt.OUTPUT / "prompt-probe.png"
    crop.resize((crop.width * 3, crop.height * 3)).save(path)
    result = subprocess.run(["tesseract", str(path), "stdout", "--psm", "6"],
                            capture_output=True, text=True, check=True).stdout.lower()
    return any(word in result for word in ("adventure", "gemacht", "aventura"))


def review_picture():
    picks = []
    for width in (360, 960):
        for state in ("peekaboo-hidden", "peekaboo-visible", "remember-complete"):
            path = rt.OUTPUT / f"hide-en-{state}-{width}.png"
            if path.exists():
                shot = Image.open(path).convert("RGB")
                shot.thumbnail((480, 600))
                panel = Image.new("RGB", (500, 630), "#fffaf0")
                panel.paste(shot, ((500 - shot.width) // 2, 26))
                ImageDraw.Draw(panel).text((8, 7), f"{state} {width}", fill="black")
                picks.append(panel)
    sheet = Image.new("RGB", (1500, 1260), "#fffaf0")
    for i, panel in enumerate(picks):
        sheet.paste(panel, ((i % 3) * 500, (i // 3) * 630))
    sheet.save(rt.OUTPUT.parent / "review.png")


def main():
    receipt = focused_build()
    check_words_and_voices()
    rt.OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    check_art_pixels(receipt)
    with tempfile.TemporaryDirectory(prefix="data-", dir=rt.OUTPUT.parent) as temporary:
        language_pass("en", temporary, legacy=True)
        language_pass("de", temporary)
        language_pass("es", temporary)
    review_picture()
    print("local hide & seek levels test: all focused rules and private-host cases passed", flush=True)


if __name__ == "__main__":
    main()

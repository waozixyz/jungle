#!/usr/bin/env python3
"""Focused rules and private-host verification for Hide & Seek levels."""
import os
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

# CI validation passes each group its own capture folder; keep failing
# captures there so they reach the uploaded artifacts.
rt.OUTPUT = (Path(os.environ["JUNGLE_TEST_OUTPUT"]).resolve() if os.environ.get("JUNGLE_TEST_OUTPUT")
             else rt.ROOT / "work/hide-seek-levels/ui")
BINARY = rt.ROOT / "build/app/jungle"
MODEL = rt.ROOT / "games/hide_seek/hide_seek.zi"
SCREEN = rt.ROOT / "games/hide_seek/jungle_hide_seek.zi"
ANIMALS = ("frog", "rabbit", "cat", "dog", "monkey", "panda", "duck", "hen", "pig", "sheep", "tiger", "parrot")
PROPS = ("basket", "bush", "table", "tree")
SCENES = ("cottage-yard", "fenced-garden", "cozy-house", "farm-courtyard")
# Only the generic prompt and the place answers are ever spoken.
CUES = ("peekaboo", "in", "behind", "under", "up")
LANGUAGES = ("en", "de", "es")
SIZES = ((360, 720), (960, 600))
# The prompt, empty-look note and the single action, as shown.
WORDS_SHOWN = {
    "en": ("Peekaboo! Who is hiding?", "Not here. Keep looking!", "Well done! Next adventure...", "Hide again", "Next"),
    "de": ("Kuckuck! Wer versteckt sich da?", "Hier nicht. Such weiter!", "Gut gemacht! Weiter geht's...", "Nochmal", "Weiter"),
    "es": ("¡Cucú! ¿Quién se esconde?", "¡Aquí no! Sigue buscando.", "¡Muy bien! Otra aventura...", "Otra vez", "Otro"),
}
# Old saves from every earlier level load as the one game, keeping counts.
OLD_SAVES = {"en": ("hideseek 1 1 4\n", 4, 0), "de": ("hideseek 2 2 4 3\n", 4, 3), "es": ("hideseek 2 0 4 0\n", 4, 0)}


def focused_build():
    subprocess.run(["make", "build/tests/hide_seek"], cwd=rt.ROOT, check=True)
    result = subprocess.run([str(rt.ROOT / "build/tests/hide_seek")], cwd=rt.ROOT, check=True, capture_output=True, text=True)
    assert BINARY.exists(), "build the stable host first: make build/app/jungle"
    bundle = rt.ROOT / "build/app/games/jungle-hide-seek.zx"
    assert bundle.exists() and bundle.stat().st_mtime >= max(MODEL.stat().st_mtime, SCREEN.stat().st_mtime), "wait for the parent coordinated app build"
    print("local hide & seek build: rules unit passed; coordinated hosted bundle is current", flush=True)
    return result.stdout



def records(receipt, tag):
    return [tuple(map(int, line.split()[1:])) for line in receipt.splitlines() if line.startswith(tag + " ")]


def feet():
    return list(map(int, re.search(r"hide_animal_feet: \[12\]s32 = \.\[(.*?)\];", MODEL.read_text(), re.S).group(1).split(",")))


def friend_layer(animals, width, height, animal, acx, base, ae, support):
    sprite = animals[animal].resize((ae, ae), Image.Resampling.LANCZOS)
    ax, ay = acx - ae // 2, base - ae * support[animal] // 420
    assert ax >= 0 and ay >= 0 and ax + ae <= width and ay + ae <= height, (width, ANIMALS[animal], "friend outside the stage")
    assert ay + ae * support[animal] // 420 == base
    layer = Image.new("RGBA", (width, height))
    layer.alpha_composite(sprite, (ax, ay))
    return layer


def check_art_pixels(receipt):
    """Real prop/cut-out pixels, driven by native geometry for every animal.

    These asset compositing tests complement the separate actual-host Xvfb
    suite. They do not claim to be captures of native host rendering.
    """
    support = feet()
    art = records(receipt, "hide-art")
    assert len(art) == 480, len(art)
    props = [Image.open(rt.ROOT / f"assets/hide_seek/props/{name}.png").convert("RGBA") for name in PROPS]
    assert all(im.size == (1254, 1254) for im in props)
    animals = [Image.open(rt.ROOT / f"assets/jungle-book/items/{name}.png").convert("RGBA") for name in ANIMALS]
    panels, ratios = {}, {}
    for width, height, kind, frame, animal, x, y, edge, acx, base, ae, behind in art:
        prop = props[kind].resize((edge, edge), Image.Resampling.LANCZOS)
        cover = Image.new("RGBA", (width, height))
        cover.alpha_composite(prop, (x, y))
        friend = friend_layer(animals, width, height, animal, acx, base, ae, support)
        alpha = friend.getchannel("A")
        # Only the whole, uncropped prop covers a friend behind it.
        visible = ImageChops.multiply(alpha, ImageChops.invert(cover.getchannel("A"))) if behind else alpha
        ratio = ImageStat.Stat(visible).sum[0] / ImageStat.Stat(alpha).sum[0]
        ratios[width, kind, animal, frame] = ratio
        name = (width, PROPS[kind], ANIMALS[animal], frame)
        if kind == 0:
            # In the basket: head and shoulders above the back rim.
            assert behind and .3 <= ratio <= .85, (name, "basket friend not rising from the basket", ratio)
        elif kind == 1:
            # Behind the bush, stepping out past its side as it is found.
            assert behind and ratio >= .12, (name, "found friend still lost in the bush", ratio)
            if frame:
                assert ratio >= ratios[width, kind, animal, frame - 1], (name, "friend went back behind the bush", ratio)
            if frame == 4:
                assert ratio >= .5, (name, "friend never stepped out from behind the bush", ratio)
        elif kind == 2:
            # Under the table: standing in the opening between the front
            # legs, wholly below the cloth's hem.
            assert behind and ratio >= .97, (name, "table legs or cloth cut the friend", ratio)
            box = alpha.point(lambda v: 255 if v > 128 else 0).getbbox()
            assert box[0] >= x + edge * 261 // 1254 and box[2] <= x + edge * 995 // 1254 + 1, (name, "not between the table legs", box)
            assert box[1] >= y + edge * 715 // 1254, (name, "friend's head inside the tablecloth", box)
        else:
            assert not behind and ratio == 1, (name, "tree friend not sitting on its branch")
        if frame in (0, 4):
            picture = Image.new("RGBA", (width, height), "#e5ead5")
            if behind:
                picture.alpha_composite(friend)
                picture.alpha_composite(cover)
            else:
                picture.alpha_composite(cover)
                picture.alpha_composite(friend)
            ax, ay = acx - ae // 2, base - ae * support[animal] // 420
            box = (max(0, min(x, ax)-4), max(0, min(y, ay)-4), min(width, max(x+edge, ax+ae)+4), min(height, max(y+edge, ay+ae)+4))
            tile = picture.crop(box).convert("RGB")
            tile.thumbnail((180, 190))
            panel = Image.new("RGB", (190, 214), "#fffaf0")
            panel.paste(tile, ((190-tile.width)//2, 20))
            ImageDraw.Draw(panel).text((4, 3), f"{ANIMALS[animal]} {'found' if frame == 4 else 'appearing'}", fill="black")
            panels[width, kind, animal, frame] = panel
    for width in (376, 893):
        for kind, name in enumerate(PROPS):
            sheet = Image.new("RGB", (190*6, 214*4), "#fffaf0")
            for animal in range(12):
                for state, frame in enumerate((0, 4)):
                    index = animal*2+state
                    sheet.paste(panels[width, kind, animal, frame], ((index%6)*190, (index//6)*214))
            sheet.save(rt.OUTPUT.parent / f"{name}-all-animals-{width}.png")
    print("local hide & seek asset pixels: 12 animals x 4 whole props x 2 orientations x 5 reveal frames; basket rim, bush side, table legs/hem and tree branch passed", flush=True)


def check_scene_pixels(receipt):
    """Every scene's natural places, hidden and found, on the real backdrop."""
    support = feet()
    places = records(receipt, "hide-place")
    assert len(places) == 2 * 2 * (3 + 3 + 2 + 3), len(places)
    props = [Image.open(rt.ROOT / f"assets/hide_seek/props/{name}.png").convert("RGBA") for name in PROPS]
    animals = [Image.open(rt.ROOT / f"assets/jungle-book/items/{name}.png").convert("RGBA") for name in ANIMALS]
    kinds = {0: {1, 3, 0}, 1: {1, 3, 0}, 2: {2, 0}, 3: {2, 1, 0}}
    for width, height in ((376, 505), (893, 346)):
        sheet = Image.new("RGB", ((width + 10) * 4, (height + 10) * 4), "white")
        for scene, name in enumerate(SCENES):
            backdrop = ImageOps.fit(Image.open(rt.ROOT / f"assets/hide_seek/scenes/{name}.png").convert("RGB"), (width, height))
            for flip in (0, 1):
                rows = sorted((r for r in places if r[:4] == (width, height, scene, flip)), key=lambda r: r[4])
                assert {r[5] for r in rows} == kinds[scene] and len(rows) == len(kinds[scene]), (name, rows)
                grounds = [r[7] for r in rows]
                assert grounds == sorted(set(grounds)), (name, "places are not painted back to front", grounds)
                hidden = backdrop.convert("RGBA")
                found = backdrop.convert("RGBA")
                for row in rows:
                    kind, cx, ground, size, hx, hy, hw, hh, animal, x, y, edge, acx, base, ae, behind = row[5:]
                    prop = Image.new("RGBA", (width, height))
                    prop.alpha_composite(props[kind].resize((edge, edge), Image.Resampling.LANCZOS), (x, y))
                    # A tap aimed at the middle of a hiding place lands on its prop.
                    assert prop.getchannel("A").getpixel((hx + hw // 2, hy + hh // 2)) > 128, (name, PROPS[kind], "hit box misses the prop")
                    friend = friend_layer(animals, width, height, animal, acx, base, ae, support)
                    hidden.alpha_composite(prop)
                    if behind:
                        found.alpha_composite(friend)
                        found.alpha_composite(prop)
                    else:
                        found.alpha_composite(prop)
                        found.alpha_composite(friend)
                sheet.paste(hidden.convert("RGB"), (scene * (width + 10), flip * 2 * (height + 10)))
                sheet.paste(found.convert("RGB"), (scene * (width + 10), (flip * 2 + 1) * (height + 10)))
        sheet.save(rt.OUTPUT.parent / f"scenes-{width}.png")
    print("local hide & seek scenes: 4 backdrops x mirrored arrangements, natural kinds, back-to-front depth and on-prop taps passed", flush=True)


def check_words_and_voices():
    """One hide-and-find game: no friend names, hints, previews or levels."""
    model = MODEL.read_text()
    screen = SCREEN.read_text()
    for code in LANGUAGES:
        for cue in CUES:
            assert (rt.ROOT / f"assets/hide_seek/sounds/{code}/{cue}.wav").exists(), (code, cue)
    listed = re.search(r"hide_animals: \[12\]string = \.\[(.*?)\];", model, re.S).group(1)
    assert tuple(re.findall(r'"([^"]*)"', listed)) == ANIMALS, listed
    # The owner's "sheep sheep": a friend's name is never spoken, before or
    # after finding it, and no cue points to where a friend hides.
    for token in ("jungle-book/sounds", "NamePath", "look_", "HideSeekWhere", "HideSeekLookWords"):
        assert token not in model and token not in screen, token
    # No memory preview, Show again, level choosers or target picture.
    for token in ("preview", "ShowAgain", "HideSeekLevel", "HIDE_PEEK ", "HIDE_HINT", "Remembering", "Targeted", "SmallPath"):
        assert token not in screen, token
    prompt = re.search(r"\nPrompt :: .*?\n}\n", screen, re.S).group(0)
    assert "Animal" not in prompt and "DrawPlace" not in prompt and "animals" not in prompt, "prompt card shows a friend"
    calls = re.findall(r"\bSay\(([^\n]*)", screen)
    assert calls and all(call.startswith("CuePath(") for call in calls), ("only cue clips are spoken", calls)
    assert re.findall(r'AppService\("jungle\.voice", ([^)]*)\)', screen) == ["path", '""'], "voice played outside Say/Hush"
    for code, shown in WORDS_SHOWN.items():
        assert all(text in model or text in screen for text in shown), (code, shown)
    for name in SCENES:
        path = rt.ROOT / f"assets/hide_seek/scenes/{name}.png"
        assert path.exists() and min(Image.open(path).size) >= 1024, path
    print("local hide & seek words: no names, hints or previews; prompt, notes and place answers present in EN/DE/ES", flush=True)


def geometry(width, height):
    height -= 56
    scale = min(width / 400, height / 700) if width <= height else min(height / 520, width / 780)
    scale = max(.5, min(scale, 1.6))
    return scale, int(width / scale), int(height / scale)


def layout(width, height):
    """Logical position of the one Hide again/Next button and the scene."""
    scale, w, h = geometry(width, height)
    controls_y = h - 66 - 12
    return scale, w, h, {"next": (w / 2, controls_y + 33)}, (12, 84, w - 24, controls_y - 12 - 84)


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
        self.click(*layout(*self.size)[3][name])

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


def stage_crop(screen, frame):
    scale, _, _, _, (x, y, w, h) = layout(*screen.size)
    return frame.crop((round(x * scale), round(56 + y * scale),
                       round((x + w) * scale), round(56 + (y + h) * scale)))


def stage(screen, name):
    return stage_crop(screen, screen.capture(name))


def look_everywhere(screen, label):
    """Every friend starts fully hidden. Looking at each place by keyboard
    reveals only a friend that is there; an empty place shows nothing new
    once its wiggle settles. Stops as soon as all friends are found."""
    d, data = screen.d, screen.data
    level, found, remembered = saved(data)
    assert level == 1, saved(data)
    start = stage(screen, f"{label}-hidden")
    time.sleep(1)
    assert not changed(start, stage(screen, f"{label}-still")), (label, "a hiding place moved or peeked before any look")
    count = 0
    for place in range(3):
        if place:
            d.key("Right")
        before = stage(screen, f"{label}-before-{place}")
        d.key("Return")
        time.sleep(.75)
        # One actual frame serves both the scene and the completion words,
        # well inside the completed round's automatic advance.
        frame = screen.capture(f"{label}-after-{place}")
        after = stage_crop(screen, frame)
        state = saved(data)
        assert state[0] == 1 and state[2] == remembered and state[1] in (found + count, found + count + 1), (label, state)
        if state[1] == found + count + 1:
            count += 1
            assert changed(before, after), (label, "a found friend did not appear")
            if completion_visible(screen, frame):
                return found + count, after
        else:
            assert not changed(before, after), (label, "an empty place revealed or hinted at something")
    raise AssertionError((label, "round never completed", saved(data)))


def no_focus_rectangle(screen):
    """Arrow navigation must not paint a rectangular selection over the scene."""
    before = stage(screen, "focus-before")
    screen.d.key("Right")
    after = stage(screen, "focus-after")
    assert not changed(before, after), "keyboard navigation painted over the scene"
    # Reset the focus without depending on the previous keyboard-active state.
    screen.button("next")


def scene_image_present(screen):
    # A missing hosted asset draws a literal placeholder. Catch that in the
    # actual private raster instead of accepting merely present PNG files.
    stage_image = stage(screen, "scene-loaded")
    path = rt.OUTPUT / "scene-probe.png"
    stage_image.resize((stage_image.width * 2, stage_image.height * 2)).save(path)
    words = subprocess.run(["tesseract", str(path), "stdout", "--psm", "11"],
                           capture_output=True, text=True, check=True).stdout.lower()
    assert "missing image" not in words, "scene or hiding-place prop bitmap failed to load in the actual host"
    # This upper band is above every prop. Compare the actual host raster
    # with proportional image fitting, so a detailed stretched scene fails.
    scale = geometry(*screen.size)[0]
    band = (stage_image.width // 4, round(12 * scale), stage_image.width * 3 // 4, round(24 * scale))
    observed = stage_image.crop(band).convert('RGB')
    cover_errors, stretch_errors = [], []
    for source in (rt.ROOT/'assets/hide_seek/scenes').glob('*.png'):
        with Image.open(source) as image:
            image = image.convert('RGB')
            for target, expected in ((cover_errors, ImageOps.fit(image, stage_image.size, Image.Resampling.BILINEAR)),
                                     (stretch_errors, image.resize(stage_image.size, Image.Resampling.BILINEAR))):
                difference = ImageChops.difference(observed, expected.crop(band))
                target.append(sum(ImageStat.Stat(difference).mean) / 3)
    assert min(cover_errors) < 22, ('backdrop differs from proportional fitting', screen.size, cover_errors)
    if stage_image.width > stage_image.height * 1.3:
        assert min(cover_errors) + 3 < min(stretch_errors), ('landscape backdrop was stretched', cover_errors, stretch_errors)
    return stage_image


def language_pass(language, temporary):
    data = Path(temporary) / language
    data.mkdir()
    (data / "language.txt").write_text(language)
    save_path(data).parent.mkdir(parents=True)
    old, found, remembered = OLD_SAVES[language]
    save_path(data).write_text(old)
    with rt.Desktop(BINARY, data, screen_size="1280x900") as d:
        screen = Screen(d, data, language)
        open_hide_seek(screen)
        screen.resize(SIZES[0])
        screen.capture("old-save")
        assert save_path(data).read_text() == old, "old save changed on load"
        d.key("Escape")
        # Any earlier level loads as the one hide-and-find game.
        assert saved(data) == [1, found, remembered], saved(data)
        open_hide_seek(screen)
        for size in SIZES:
            screen.resize(size)
            # Four consecutive manual rounds visit all four scenes. Every
            # actual raster must load its backdrop.
            stages = []
            for _ in range(4):
                screen.button("next")
                assert saved(data) == [1, found, remembered], ("Hide again changed counts", saved(data))
                image = scene_image_present(screen)
                stages.append(image.crop((0, 0, image.width, image.height // 4)).tobytes())
            assert len(set(stages)) == 4, "scene rotation repeated a backdrop early"
            no_focus_rectangle(screen)
            # Space repeats only the generic prompt; nothing is revealed.
            before = stage(screen, "space-before")
            d.key("space")
            assert not changed(before, stage(screen, "space-after")) and saved(data) == [1, found, remembered]
            found, complete = look_everywhere(screen, f"round-{size[0]}")
            screen.capture("round-complete")
            # A completed round moves to the next scene by itself.
            time.sleep(2.9)
            renewed = stage(screen, "round-next")
            assert changed(complete, renewed), "a completed round never moved on"
            assert saved(data) == [1, found, remembered], saved(data)
            # Hold Enter on a completed round: it starts the next scene, and
            # the held key must not look in any of the new places.
            found, _ = look_everywhere(screen, f"held-{size[0]}")
            rt.run(["xdotool", "keydown", "Return"], d.env)
            try:
                time.sleep(.8)
                held = stage(screen, "held-new-round")
                for _ in range(4):
                    d.key("Right")
                    assert saved(data) == [1, found, remembered], ("held Enter carried over", saved(data))
                assert not changed(held, stage(screen, "held-after-right")), "held Enter revealed a friend"
            finally:
                rt.run(["xdotool", "keyup", "Return"], d.env)
            assert saved(data) == [1, found, remembered]
            # Hide again mid-round keeps the counts and resets the old timer.
            found, _ = look_everywhere(screen, f"manual-{size[0]}")
            screen.button("next")
            assert saved(data) == [1, found, remembered]
            fresh = stage(screen, "manual-next")
            time.sleep(2.8)
            assert not changed(fresh, stage(screen, "manual-next-later")), "old completion timer survived manual Next"
        before = save_path(data).read_text()
        d.key("Escape")
        assert save_path(data).read_text() == before
        open_hide_seek(screen)
        assert saved(data) == [1, found, remembered]
        screen.capture("reopened")
        d.click_actual(28, 28)
        open_hide_seek(screen)
        assert saved(data) == [1, found, remembered]
        d.key("Escape")
    print(f"local hide & seek UI: {language} old save, hidden-until-found, empty looks, 4 scenes x 2 orientations, auto/manual next, held input and reopen passed", flush=True)


def completion_visible(screen, image):
    # Read the actual rendered completion words in this private window's frame.
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
        for state in (f"round-{width}-hidden", "round-complete", "manual-next"):
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
    check_scene_pixels(receipt)
    with tempfile.TemporaryDirectory(prefix="data-", dir=rt.OUTPUT.parent) as temporary:
        for language in LANGUAGES:
            language_pass(language, temporary)
    review_picture()
    print("local hide & seek levels test: all focused rules and private-host cases passed", flush=True)


if __name__ == "__main__":
    main()

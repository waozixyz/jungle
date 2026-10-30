#!/usr/bin/env python3
"""Focused rules and private-host verification for Hide & Seek levels."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from PIL import ImageChops

import runtime_test as rt

sys.path.insert(0, str(rt.ROOT / "tools"))
from book_catalog import WORDS  # noqa: E402

rt.OUTPUT = rt.ROOT / "backup/hide-seek-levels/ui"
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
    subprocess.run([str(rt.ROOT / "build/tests/hide_seek")], cwd=rt.ROOT, check=True)
    subprocess.run(["make", "build/app/games/jungle-hide-seek.zx"], cwd=rt.ROOT, check=True)
    assert BINARY.exists(), "build the stable host first: make build/app/jungle"
    print("local hide & seek build: rules unit and hosted bundle passed", flush=True)


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
    print("local hide & seek words: friends, prompts and voice clips present in EN/DE/ES", flush=True)


def geometry(width, height):
    height -= 56
    scale = min(width / 400, height / 700) if width <= height else min(height / 520, width / 780)
    scale = max(.5, min(scale, 1.6))
    return scale, int(width / scale), int(height / scale)


def layout(width, height):
    """Logical rectangles of the level, help and next buttons and the scene."""
    scale, w, h = geometry(width, height)
    two = w < 560
    controls_height = 124 if two else 66
    controls_y = h - controls_height - 12
    row = (controls_height - 8) // 2 if two else controls_height
    buttons = {}
    count = 3 if two else 5
    each = min(150, (w - 32 - 8 * (count - 1)) // count)
    x = (w - (each * count + 8 * (count - 1))) // 2
    for level in range(3):
        buttons[level] = (x + each / 2, controls_y + row / 2)
        x += each + 8
    y = controls_y + row / 2
    if two:
        y += row + 8
        each = min(190, (w - 32 - 8) // 2)
        x = (w - (each * 2 + 8)) // 2
    buttons["help"] = (x + each / 2, y)
    buttons["next"] = (x + each + 8 + each / 2, y)
    return scale, w, h, buttons, (12, 84, w - 24, controls_y - 12 - 84)


def place_center(width, height, places, place):
    _, w, h, _, (left, top, scene_w, scene_h) = layout(width, height)
    columns = 2 if places >= 4 and scene_w < scene_h else places
    rows = (places + columns - 1) // columns
    slot, row = scene_w // columns, scene_h // rows
    return left + (place % columns) * slot + slot / 2, top + (place // columns) * row + row / 2


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
    time.sleep(.8)
    screen.capture(f"{label}-found")
    return remembered + 1


def find_round(screen, label):
    d, data = screen.d, screen.data
    level, found, remembered = saved(data)
    assert level == 1
    for place in range(3):
        if place:
            d.key("Right")
        d.key("Return")
        if saved(data)[1] == found + 1:
            break
        assert saved(data) == [1, found, remembered], saved(data)
    else:
        raise AssertionError((label, "finding friend never found", saved(data)))
    screen.capture(f"{label}-found")
    return found + 1


def language_pass(language, temporary, legacy=False):
    data = Path(temporary) / language
    data.mkdir()
    (data / "language.txt").write_text(language)
    if legacy:
        save_path(data).parent.mkdir(parents=True)
        save_path(data).write_text("hideseek 1 1 4\n")
    with rt.Desktop(BINARY, data, screen_size="1280x900") as d:
        screen = Screen(d, data, language)
        d.game("Hide & Seek")
        screen.resize(SIZES[0])
        if legacy:
            # The earlier two-mode save opens Find with its three places.
            screen.capture("legacy-find")
            assert save_path(data).read_text() == "hideseek 1 1 4\n", "legacy save changed on load"
            d.key("Escape")
            assert saved(data) == [1, 4, 0], saved(data)
            d.game("Hide & Seek")
        else:
            # A fresh child starts on the gentle first level.
            screen.capture("fresh")
            d.key("Escape")
            assert saved(data) == [0, 0, 0], saved(data)
            d.game("Hide & Seek")
        level, found, remembered = saved(data)

        for size in SIZES:
            screen.resize(size)
            # Touch: every level from its numbered button, keeping progress.
            for target in (0, 1, 2):
                screen.button(target)
                assert saved(data) == [target, found, remembered], (language, size, target, saved(data))
                screen.capture(f"level{target + 1}")
            # Keyboard: the number keys choose levels too.
            d.key("1")
            assert saved(data)[0] == 0
            before = screen.capture("peekaboo-before")
            screen.click(*place_center(*size, 3, 0))
            time.sleep(.7)
            assert changed(before, screen.capture("peekaboo-peek")), "Peekaboo tap did not reveal"
            screen.button("help")  # hears the prompt again
            screen.button("next")
            assert saved(data) == [0, found, remembered], saved(data)
            d.key("2")
            found = find_round(screen, f"find-{size[0]}")
            assert saved(data) == [1, found, remembered], saved(data)
            d.key("Return")  # next finding round
            assert saved(data) == [1, found, remembered], saved(data)
            d.key("3")
            remembered = remember_round(screen, f"remember-{size[0]}")
            assert saved(data) == [2, found, remembered], saved(data)
            d.key("Return")  # a new remembering round previews again
            assert saved(data) == [2, found, remembered], saved(data)
            screen.capture("remember-next-preview")

        # Leaving mid-preview and reopening restarts the preview fairly with
        # every count kept.
        before = save_path(data).read_text()
        d.key("Escape")
        assert save_path(data).read_text() == before, "navigation changed progress"
        d.game("Hide & Seek")
        assert saved(data) == [2, found, remembered], saved(data)
        screen.resize(SIZES[0])
        remembered = remember_round(screen, "reopened")
        # Back from the title bar keeps the level and both counts.
        d.click_actual(28, 28)
        d.game("Hide & Seek")
        assert saved(data) == [2, found, remembered], saved(data)
        screen.capture("resumed")
        d.key("Page_Up")
        assert saved(data) == [1, found, remembered], saved(data)
        d.key("Escape")
    print(f"local hide & seek UI: {language} levels, touch/keyboard, help, preview, reopen and progress passed", flush=True)


def main():
    focused_build()
    check_words_and_voices()
    with tempfile.TemporaryDirectory(prefix="hide-seek-levels-") as temporary:
        language_pass("en", temporary, legacy=True)
        language_pass("de", temporary)
        language_pass("es", temporary)
    print("local hide & seek levels test: all focused rules and private-host cases passed", flush=True)


if __name__ == "__main__":
    main()

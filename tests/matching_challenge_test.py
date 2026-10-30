#!/usr/bin/env python3
"""Focused rules and private-host verification for harder Matching rounds."""
from collections import Counter
from pathlib import Path
import subprocess
import tempfile
import time

from PIL import ImageChops

import runtime_test as rt


rt.OUTPUT = rt.ROOT / "backup/matching-challenge-ui"
BINARY = rt.ROOT / "build/app/jungle"
PAIRS = (2, 2, 3, 4, 6, 8, 10)
WORDS = {
    "en": ("cards face up", "Memory", "Look at the cards!"),
    "de": ("Karten offen", "Gedächtnis", "Schau dir die Karten an!"),
    "es": ("cartas boca arriba", "Memoria", "¡Mira las cartas!"),
}


def focused_build():
    subprocess.run(["make", "build/tests/matching"], cwd=rt.ROOT, check=True)
    subprocess.run([str(rt.ROOT / "build/tests/matching")], cwd=rt.ROOT, check=True)
    subprocess.run(["make", "build/app/games/jungle-matching.zx"], cwd=rt.ROOT, check=True)
    print("local matching build: rules unit and hosted bundle passed", flush=True)


def save_path(data):
    return data / "games/jungle.matching/matching.txt"


def round_save(data):
    path = save_path(data)
    assert path.exists(), "Matching did not write an isolated save"
    words = path.read_text().split()
    assert words[:5] == ["matching", "1", words[2], words[3], words[4]]
    return words


def assert_exact_pairs(words, mode):
    cards = int(words[4])
    animals = [int(value) for value in words[5:5 + cards]]
    matched = words[5 + cards:5 + cards * 2]
    assert len(animals) == len(matched) == PAIRS[mode] * 2, (mode, words)
    counts = Counter(animals)
    assert set(counts.values()) == {2}, (mode, counts)
    assert len(counts) == PAIRS[mode], (mode, counts)
    assert all(0 <= animal < 22 for animal in animals), animals
    assert set(matched) <= {"0", "1"}, matched


def geometry(width, height):
    height -= 56
    scale = min(width / 360, height / 640)
    if width > height:
        scale = min(height / 520, width / 960)
    scale = max(.5, min(scale, 1.6))
    return scale, round(width / scale), round(height / scale)


def grid(cards, width, height, gap=14):
    best = (0, 1, 1)
    for columns in range(1, cards + 1):
        rows = (cards + columns - 1) // columns
        if cards % columns and columns < cards:
            continue
        edge = min((width - gap * (columns - 1)) // columns,
                   (height - gap * (rows - 1)) // rows)
        if edge > best[0]:
            best = (edge, columns, rows)
    return best


def assert_hard_layout(width, height, name):
    _, logical_width, logical_height = geometry(width, height)
    controls = 124 if logical_width < 560 else 66
    top, bottom = 70, logical_height - controls - 12 - 14
    edge, columns, rows = grid(20, logical_width - 32, bottom - top)
    span_width = columns * edge + (columns - 1) * 14
    span_height = rows * edge + (rows - 1) * 14
    assert edge >= 44, (name, edge)
    assert span_width <= logical_width - 32 and span_height <= bottom - top, (name, edge, columns, rows)


def move_focus(desktop, current, target, columns):
    while current != target:
        row, column = divmod(current, columns)
        target_row, target_column = divmod(target, columns)
        if target_row > row:
            key = "Down"; current += columns
        elif target_row < row:
            key = "Up"; current -= columns
        elif target_column > column:
            key = "Right"; current += 1
        else:
            key = "Left"; current -= 1
        desktop.key(key)
    return current


def complete_hard(desktop, words):
    cards = int(words[4])
    animals = [int(value) for value in words[5:5 + cards]]
    columns = grid(cards, *geometry(400, 756)[1:])[1]
    focus = 0
    unmatched = list(range(cards))
    while unmatched:
        first = unmatched[0]
        second = next(index for index in unmatched[1:] if animals[index] == animals[first])
        focus = move_focus(desktop, focus, first, columns)
        desktop.key("Return")
        focus = move_focus(desktop, focus, second, columns)
        desktop.key("Return")
        unmatched.remove(first); unmatched.remove(second)
    return animals


def language_pass(language, temporary, legacy=False):
    data = Path(temporary) / language
    data.mkdir()
    (data / "language.txt").write_text(language)
    legacy_text = None
    if legacy:
        legacy_path = save_path(data)
        legacy_path.parent.mkdir(parents=True)
        legacy_text = "matching 1 2 5 6 0 0 1 1 2 2 0 0 0 0 0 0\n"
        legacy_path.write_text(legacy_text)
    with rt.Desktop(BINARY, data, screen_size="1280x900") as desktop:
        desktop.game("Matching Pairs")
        if legacy:
            desktop.resize(400, 756)
            desktop.capture_actual("matching-legacy-portrait")
            assert save_path(data).read_text() == legacy_text, "legacy four-mode save changed on load"
            desktop.key("Page_Up"); desktop.key("Page_Up")
        else:
            desktop.key("Escape"); desktop.game("Matching Pairs")

        expected_labels = WORDS[language]
        source = (rt.ROOT / "games/matching/jungle_matching.zi").read_text()
        assert all(label in source for label in expected_labels), (language, expected_labels)
        expected_rounds = int(round_save(data)[3])
        for step in range(7):
            if step:
                desktop.key("Page_Down")
            words = round_save(data)
            assert int(words[2]) == step and int(words[3]) == expected_rounds, (language, step, words)
            assert_exact_pairs(words, step)
            portrait = step % 2 == 0
            desktop.resize(*(400, 756) if portrait else (960, 600))
            if portrait:
                assert_hard_layout(400, 756, f"{language}-{step}")
            else:
                assert_hard_layout(960, 600, f"{language}-{step}")
            name = f"matching-{language}-mode{step}-{'portrait' if portrait else 'landscape'}"
            if step >= 4:
                preview = desktop.capture_actual(name + "-preview")
                before = save_path(data).read_text()
                time.sleep(2.8)
                played = desktop.capture_actual(name + "-play")
                assert ImageChops.difference(preview, played).getbbox(), (language, step, "preview never cleared")
                assert save_path(data).read_text() == before, (language, step, "preview mutated progress")
            else:
                desktop.capture_actual(name)

        hard = round_save(data)
        animals = complete_hard(desktop, hard)
        finished = round_save(data)
        assert int(finished[3]) == expected_rounds + 1 and set(finished[25:]) == {"1"}, finished
        desktop.capture_actual(f"matching-{language}-hard-complete")
        desktop.key("Return")
        redeal = round_save(data)
        assert int(redeal[2]) == 6 and int(redeal[3]) == expected_rounds + 1 and set(redeal[25:]) == {"0"}, redeal
        assert_exact_pairs(redeal, 6)
        assert Counter(int(value) for value in redeal[5:25]) != Counter(animals), "New cards did not reshuffle"
        before = save_path(data).read_text()
        desktop.key("Escape")
        assert save_path(data).read_text() == before, "navigation changed Matching progress"
        desktop.capture_actual(f"matching-{language}-navigation-home")
    print(f"local matching UI: {language} every level, orientations, save/redeal and keyboard passed", flush=True)


def main():
    focused_build()
    with tempfile.TemporaryDirectory(prefix="matching-challenge-") as temporary:
        language_pass("en", temporary, legacy=True)
        language_pass("de", temporary)
        language_pass("es", temporary)
    print("local matching challenge test: all focused rules and private-host cases passed", flush=True)


if __name__ == "__main__":
    main()

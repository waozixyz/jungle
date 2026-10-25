#!/usr/bin/env python3
"""Validate recovered game data that the portable runtime loads at play time."""
from pathlib import Path
import hashlib
import json
import wave
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_catalog import NAMES, BOOKS, LANGUAGES, WORDS, narration, voice_path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    for number in range(1, 25):
        with Image.open(ROOT / f"assets/animal-count/items/animal-{number}.png") as sprite:
            assert sprite.size == (24, 20)
            assert sprite.getbbox(), f"native sprite {number} is empty"
    with Image.open(ROOT / "assets/animal-count/font.png") as font:
        assert font.size == (128, 48), "counting needs the original 8-pixel font"
    with Image.open(ROOT / "assets/jungle-book/font.png") as font:
        assert font.size == (128, 224), "Jungle Book needs the shared 8-by-16 font"
    expected = {name + ".png" for name in NAMES}
    actual = {path.name for path in (ROOT / "assets/jungle-book/items").glob("*.png")}
    assert actual == expected, "Picture Book has stale or missing category artwork"
    expected_previews = {name + ".png" for name, _ in BOOKS}
    actual_previews = {path.name for path in (ROOT / "assets/jungle-book/previews").glob("*.png")}
    assert actual_previews == expected_previews, "Picture Book needs clean category previews"
    with Image.open(ROOT / "art/generated/picture-book-watercolors.png") as source:
        assert source.width == source.height and source.width >= 1024, "Picture Book needs its generated watercolor source"
    with Image.open(ROOT / "assets/jungle/book.png") as icon:
        assert icon.size == (64, 64) and icon.mode == "RGBA", "Picture Book needs a generated raster icon"
    for path in sorted((ROOT / "assets/jungle-book/items").glob("*.png")):
        with Image.open(path) as sprite:
            assert sprite.size == (420, 420), f"{path.name} must match Picture Book's smooth page art"
            assert sprite.mode == "RGBA", f"{path.name} must preserve its transparency"
            assert sprite.getbbox(), f"{path.name} is empty"
            alpha = sprite.getchannel("A")
            assert alpha.getextrema()[1] == 255, f"{path.name} has no opaque artwork"
            assert alpha.getextrema()[0] == 255, f"{path.name} lost its picture-book background"
            colors = sprite.convert("RGBA").getcolors(420 * 420)
            assert colors is not None and len(colors) > 1000, f"{path.name} is not smooth generated artwork"
    for path in sorted((ROOT / "assets/jungle-book/previews").glob("*.png")):
        with Image.open(path) as preview:
            assert preview.size == (420, 420) and preview.mode == "RGBA"
    for language in LANGUAGES:
        for simple in (True, False):
            for name in NAMES:
                path = ROOT / voice_path(name, language, simple)
                receipt = json.loads(path.with_suffix(".speech.json").read_text())
                assert receipt["text"] == narration(name, language, simple), (name, language, simple)
                assert receipt["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
                with wave.open(str(path)) as voice:
                    assert (voice.getnchannels(), voice.getsampwidth(), voice.getframerate()) == (1, 2, 22050)
                    seconds = voice.getnframes() / voice.getframerate()
                    assert .3 < seconds < 60 and abs(seconds - receipt["duration"]) < .001
                    assert any(voice.readframes(voice.getnframes())), (name, language, simple)
                assert path.read_bytes()[36:40] == b"data"
    for name in ("book", "count", "paint"):
        with Image.open(ROOT / f"assets/jungle/covers/{name}.png") as cover:
            assert cover.size == (420, 420) and cover.mode == "RGBA"
    with Image.open(ROOT / "assets/animal-count/background.png") as background:
        assert background.size == (320, 200)
    for number in range(1, 31):
        with Image.open(ROOT / f"assets/dino-paint/crayons/{number}.png") as crayon:
            assert crayon.size == (44, 20)
            colors = crayon.convert("RGB").getcolors(100)
            assert 1 <= len(colors) <= 2
            if number > 16:
                assert len(colors) == 2, f"crayon {number} lost its stipple"
    for number in range(1, 13):
        with Image.open(ROOT / f"assets/dino-paint/art/dino{number}-s4.png") as dinosaur:
            colors = dict((color, count) for count, color in dinosaur.convert("RGBA").getcolors())
            assert colors.get((255, 255, 255, 255), 0) > 100, "dinosaur lost its opaque white body"
            assert colors.get((0, 0, 0, 255), 0) > 100, "dinosaur lost its ink"
            assert colors.get((0, 0, 0, 0), 0) > 100, "dinosaur erased its surrounding scenery"
        with wave.open(str(ROOT / f"assets/dino-paint/sounds/voice-{number}.wav")) as voice:
            assert voice.getnchannels() == 1 and voice.getsampwidth() == 2
            assert voice.getframerate() == 22050
            assert .5 < voice.getnframes() / voice.getframerate() < 3
            assert any(voice.readframes(voice.getnframes())), "empty dinosaur voice"
    for number in range(8):
        with wave.open(str(ROOT / f"assets/animal-count/sounds/right-{number}.wav")) as sound:
            assert .1 < sound.getnframes() / sound.getframerate() < .2
    with wave.open(str(ROOT / "assets/animal-count/sounds/reward.wav")) as reward:
        assert .2 < reward.getnframes() / reward.getframerate() < .5
    print("local asset test: cartoon pages, native sprites, opaque dinosaur bodies, BIOS font, VGA crayons, voices and brief feedback passed")


if __name__ == "__main__":
    main()

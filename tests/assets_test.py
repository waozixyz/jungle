#!/usr/bin/env python3
"""Validate recovered game data that the portable runtime loads at play time."""
from pathlib import Path
import wave

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    for number in range(1, 25):
        with Image.open(ROOT / f"assets/animal-count/items/animal-{number}.png") as sprite:
            assert sprite.size == (24, 20)
            assert sprite.getbbox(), f"native sprite {number} is empty"
    with Image.open(ROOT / "assets/animal-count/font.png") as font:
        assert font.size == (128, 48), "counting needs the original 8-pixel font"
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
    print("local asset test: native sprites, opaque dinosaur bodies, BIOS font, VGA crayons, voices and brief feedback passed")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Validate recovered game data that the portable runtime loads at play time."""
from pathlib import Path
import hashlib
import json
import wave
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_catalog import NAMES, BOOKS, LANGUAGES, WORDS, narration, voice_path

from PIL import Image, ImageChops

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
    # Each page is one whole watercolor scene whose edges fade into the paper.
    expected = {name + ".jpg" for name in NAMES}
    actual = {path.name for path in (ROOT / "assets/jungle-book/pages").glob("*")}
    assert actual == expected, "Picture Book has stale or missing scene pages"
    for name in NAMES:
        with Image.open(ROOT / f"assets/jungle-book/pages/{name}.jpg") as page:
            assert page.size == (1254, 1254) and page.mode == "RGB", f"{name} page is not a sharp full scene"
            corners = [page.getpixel(p) for p in [(4, 4), (1249, 4), (4, 1249), (1249, 1249)]]
            # A leaf or arm can reach a corner while the scene still fades
            # into paper around the rest of its edges.
            assert sum(min(color) > 190 for color in corners) >= 3, f"{name} page does not fade into the paper"
            assert len(page.resize((300, 300)).getcolors(300 * 300) or range(90001)) > 5000, f"{name} page is not smooth artwork"
    prompts = json.loads((ROOT / "tools/book_prompts.json").read_text())
    assert set(prompts["pages"]) == set(NAMES), "every full scene keeps its prompt"
    assert (ROOT / "art/generated/title-covers.png").exists(), "the cover style reference is missing"
    expected_previews = {name + ".jpg" for name, _ in BOOKS}
    actual_previews = {path.name for path in (ROOT / "assets/jungle-book/previews").glob("*")}
    assert actual_previews == expected_previews, "Picture Book needs one cover per book"
    for path in sorted((ROOT / "assets/jungle-book/previews").glob("*.jpg")):
        with Image.open(path) as preview:
            assert preview.size == (768, 768)
    assert not (ROOT / "assets/jungle-book/backgrounds").exists(), "scenes replace the shared backdrops"
    with Image.open(ROOT / "assets/jungle/book.png") as icon:
        assert icon.size == (64, 64), "Picture Book needs a generated raster icon"
    # Counting uses cut-outs; Picture Book and ABC examples use full scenes.
    # New words need no unused duplicate cut-out.
    expected = {name + ".png" for name in prompts["cutouts"]}
    actual = {path.name for path in (ROOT / "assets/jungle-book/items").glob("*.png")}
    assert actual == expected, "Picture Book has stale or missing cut-outs"
    assert set(prompts["cutouts"]) <= set(NAMES), "cut-outs must belong to a real word"
    counting = {'tiger','frog','butterfly','ladybug','snail','elephant','giraffe','monkey','panda','lion','zebra','crocodile','parrot','toucan','rabbit','cat','dog','sheep','duck','hen','pig','cow'}
    assert counting <= set(prompts["cutouts"]), "a counting animal has no cut-out"
    for path in sorted((ROOT / "assets/jungle-book/items").glob("*.png")):
        with Image.open(path) as sprite:
            assert sprite.size == (420, 420), f"{path.name} must be a 420 pixel cut-out"
            assert sprite.mode == "RGBA", f"{path.name} must preserve its transparency"
            assert sprite.getbbox(), f"{path.name} is empty"
            alpha = sprite.getchannel("A")
            assert alpha.getextrema() == (0, 255), f"{path.name} needs an isolated illustration without a paper panel"
            assert all(alpha.getpixel(p) == 0 for p in [(0,0),(419,0),(0,419),(419,419)]), f"{path.name} has a clipped edge"
            colors = sprite.convert("RGBA").getcolors(420 * 420)
            assert colors is not None and len(colors) > 1000, f"{path.name} is not smooth generated artwork"
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
    for name in ("book", "counting", "paint"):
        with Image.open(ROOT / f"assets/jungle/covers/{name}.jpg") as cover:
            assert cover.size == (420, 420) and cover.format == "JPEG"
    with Image.open(ROOT / "assets/animal-count/background.png") as background:
        assert background.size == (320, 200)
    art = ROOT / "assets/dino-paint/art"
    assert not (ROOT / "assets/dino-paint/crayons").exists(), "crayons are drawn as color boxes"
    for number in range(1, 7):
        assert (ROOT / f"art/paint/scene{number}.svg").read_text().count("<path") == 1
        with Image.open(art / f"scene{number}-thumb.jpg") as thumb:
            assert thumb.size == (256, 192) and len(thumb.getcolors(1 << 16) or range(1 << 16)) > 16, "scene thumbnail is not smooth"
    for number in range(1, 31):
        svg = (ROOT / f"art/paint/dino{number}.svg").read_text()
        assert '<path id="body" fill="#fff"' in svg and ('<path id="ink" fill="#000"' in svg or '<g id="ink"' in svg)
        with Image.open(art / f"dino{number}.png") as dinosaur, Image.open(art / f"dino{number}-flip.png") as flipped:
            assert 720 in dinosaur.size or 960 in dinosaur.size, "placement picture is not the Huge size"
            assert dinosaur.transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes() == flipped.tobytes()
            red, green, blue, alpha = dinosaur.convert("RGBA").split()
            opaque = alpha.point(lambda v: 255 if v == 255 else 0)
            lightest = ImageChops.darker(ImageChops.darker(red, green), blue).point(lambda v: 255 if v > 240 else 0)
            darkest = ImageChops.lighter(ImageChops.lighter(red, green), blue).point(lambda v: 255 if v < 40 else 0)
            levels = alpha.histogram()
            assert ImageChops.multiply(opaque, lightest).histogram()[255] > 10000, "dinosaur lost its opaque white body"
            assert ImageChops.multiply(opaque, darkest).histogram()[255] > 1000, "dinosaur lost its ink"
            assert levels[0] > 10000, "dinosaur erased its surrounding scenery"
            assert sum(levels[1:255]) > 100, "dinosaur edges are not smooth"
        for kind in ("thumb", "preview"):
            with Image.open(art / f"dino{number}-{kind}.png") as picture:
                assert picture.mode == "RGBA" and picture.getbbox()
        if number <= 12:
            with wave.open(str(ROOT / f"assets/dino-paint/sounds/voice-{number}.wav")) as voice:
                assert voice.getnchannels() == 1 and voice.getsampwidth() == 2
                assert voice.getframerate() == 22050
                assert .5 < voice.getnframes() / voice.getframerate() < 3
                assert any(voice.readframes(voice.getnframes())), "empty dinosaur voice"
    old = [path.name for path in art.glob("*.png") if "-s" in path.name or path.stem[-1].isdigit() and "preview" in path.stem]
    assert not old, f"stale pixel art: {old[:3]}"
    prompts = {"en":"How many animals?", "de":"Wie viele Tiere?", "es":"¿Cuántos animales hay?"}
    for language, text in prompts.items():
        path = ROOT / f"assets/animal-count/sounds/question-{language}.wav"
        receipt = json.loads(path.with_suffix(".speech.json").read_text())
        assert receipt["text"] == text and receipt["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        with wave.open(str(path)) as prompt:
            assert (prompt.getnchannels(), prompt.getsampwidth(), prompt.getframerate()) == (1,2,22050)
            assert .5 < prompt.getnframes()/prompt.getframerate() < 10
    for number in range(8):
        with wave.open(str(ROOT / f"assets/animal-count/sounds/right-{number}.wav")) as sound:
            assert .1 < sound.getnframes() / sound.getframerate() < .2
    with wave.open(str(ROOT / "assets/animal-count/sounds/reward.wav")) as reward:
        assert .2 < reward.getnframes() / reward.getframerate() < .5
    print("local asset test: watercolor scene pages, cut-outs, native sprites, opaque dinosaur bodies, BIOS font, VGA crayons, voices and brief feedback passed")


if __name__ == "__main__":
    main()

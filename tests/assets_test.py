#!/usr/bin/env python3
"""Validate recovered game data that the portable runtime loads at play time."""
from pathlib import Path
import hashlib
import json
import wave
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from design_size import design_size
from book_catalog import NAMES, BOOKS, LANGUAGES, WORDS, narration, voice_path

from PIL import Image, ImageChops, ImageStat
from paint_pages import dinosaur as stencil_source, render, fit, CANVAS

ROOT = Path(__file__).resolve().parents[1]


def main():
    assert not (ROOT/'assets/animal-count/items').exists(), 'Unused legacy sprites must not ship'
    assert not (ROOT/'assets/animal-count/background.png').exists(), 'Unused legacy background must not ship'
    with Image.open(ROOT / "assets/animal-count/font.png") as font:
        assert font.size == (128, 48), "counting needs the original 8-pixel font"
    with Image.open(ROOT / "assets/jungle-book/font.png") as font:
        assert font.size == (128, 224), "Jungle Book needs the shared 8-by-16 font"
    # Each page is one whole watercolor scene whose edges fade into the paper.
    story = json.loads((ROOT / 'tools/sweet_porridge.json').read_text())
    story_pages = {row['asset'] + '.avif' for row in story['pages']}
    bremen = json.loads((ROOT / 'tools/town_musicians.json').read_text())
    story_pages.update(row['asset'] + '.avif' for row in bremen['pages'])
    expected = {name + ".avif" for name in NAMES} | story_pages
    actual = {path.name for path in (ROOT / "assets/jungle-book/pages").glob("*")}
    assert actual == expected, "Picture Book has stale or missing scene pages"
    for name in NAMES:
        with Image.open(ROOT / f"assets/jungle-book/pages/{name}.avif") as page:
            assert design_size(page.filename, page) == (1254, 1254) and page.mode == "RGB", f"{name} page is not a sharp full scene"
            far = page.width - 5
            corners = [page.getpixel(p) for p in [(4, 4), (far, 4), (4, far), (far, far)]]
            # A leaf or arm can reach a corner while the scene still fades
            # into paper around the rest of its edges.
            assert sum(min(color) > 190 for color in corners) >= 3, f"{name} page does not fade into the paper"
            assert len(page.resize((300, 300)).getcolors(300 * 300) or range(90001)) > 5000, f"{name} page is not smooth artwork"
    prompts = json.loads((ROOT / "tools/book_prompts.json").read_text())
    assert set(prompts["pages"]) == set(NAMES), "every full scene keeps its prompt"
    expected_previews = {name + ".avif" for name, _ in BOOKS} | {'sweet-porridge.avif'}
    actual_previews = {path.name for path in (ROOT / "assets/jungle-book/previews").glob("*")}
    assert actual_previews == expected_previews, "Picture Book needs one cover per book"
    for path in sorted((ROOT / "assets/jungle-book/previews").glob("*.avif")):
        with Image.open(path) as preview:
            assert design_size(path, preview) == ((768, 512) if path.name == 'sweet-porridge.avif' else (768, 768))
    assert not (ROOT / "assets/jungle-book/backgrounds").exists(), "scenes replace the shared backdrops"
    with Image.open(ROOT / "assets/jungle/book.avif") as icon:
        assert icon.size == (64, 64), "Picture Book needs a generated raster icon"
    # Counting uses cut-outs; Picture Book and ABC examples use full scenes.
    # New words need no unused duplicate cut-out.
    expected = {name + ".avif" for name in prompts["cutouts"]}
    actual = {path.name for path in (ROOT / "assets/jungle-book/items").glob("*.avif")}
    assert actual == expected, "Picture Book has stale or missing cut-outs"
    assert set(prompts["cutouts"]) <= set(NAMES), "cut-outs must belong to a real word"
    counting = {'tiger','frog','butterfly','ladybug','snail','elephant','giraffe','monkey','panda','lion','zebra','crocodile','parrot','toucan','rabbit','cat','dog','sheep','duck','hen','pig','cow'}
    assert counting <= set(prompts["cutouts"]), "a counting animal has no cut-out"
    assert {p.stem for p in (ROOT / 'assets/jungle-book/counting').glob('*.avif')} == counting
    original_bytes = 0
    counting_bytes = 0
    for name in counting:
        original = ROOT / f'assets/jungle-book/items/{name}.avif'
        small = ROOT / f'assets/jungle-book/counting/{name}.avif'
        with Image.open(original) as source, Image.open(small) as picture:
            assert picture.size == (128, 128) and picture.mode == 'RGBA', name
            assert picture.getchannel('A').getextrema() == (0, 255), name
            expected = source.resize((128, 128), Image.Resampling.LANCZOS)
            # The same derivative of the painting; the 75% cut-out's q90 alpha
            # may drift slightly from the 128 px copy made from the master.
            drift = ImageChops.difference(picture.getchannel('A'), expected.getchannel('A'))
            assert ImageStat.Stat(drift).mean[0] < 1 and drift.getextrema()[1] <= 24, name
            def seen(image):  # visible color over paper; hidden RGB never shows
                paper = Image.new('RGBA', image.size, (255, 255, 255, 255))
                paper.alpha_composite(image.convert('RGBA'))
                return paper.convert('RGB')
            assert max(ImageStat.Stat(ImageChops.difference(seen(picture), seen(expected))).mean) < 3, name
        original_bytes += original.stat().st_size
        counting_bytes += small.stat().st_size
    assert counting_bytes < original_bytes / 5, 'Counting pictures are no longer small downloads'
    refreshed = {'tiger','elephant','giraffe','monkey','panda','lion','zebra',
                 'crocodile','parrot','toucan','gorilla','hippo','rhino','snake','bear'}
    assert set(json.loads((ROOT / 'tools/book_art_refresh.json').read_text())['cutouts']) == refreshed
    farm_cutouts = set(json.loads((ROOT / 'tools/book_farm_refresh.json').read_text())['cutouts'])
    for path in sorted((ROOT / "assets/jungle-book/items").glob("*.avif")):
        with Image.open(path) as sprite:
            edge = 1254 if path.stem in refreshed | farm_cutouts else 420
            assert design_size(path, sprite) == (edge, edge), f"{path.name} must preserve its {edge} pixel cut-out"
            edge = sprite.width
            assert sprite.mode == "RGBA", f"{path.name} must preserve its transparency"
            assert sprite.getbbox(), f"{path.name} is empty"
            alpha = sprite.getchannel("A")
            assert alpha.getextrema() == (0, 255), f"{path.name} needs an isolated illustration without a paper panel"
            last = edge - 1
            # Native generated PNGs can carry 1–2/255 alpha export noise, and the
            # 75% standard's q90 alpha a few more invisible levels.
            # Check their entire border for visible clipping; legacy corners
            # keep their exact transparent-pixel requirement.
            if path.stem in refreshed | farm_cutouts:
                borders = [alpha.crop(box).getextrema()[1] for box in
                           [(0,0,edge,1),(0,last,edge,edge),(0,0,1,edge),(last,0,edge,edge)]]
                assert max(borders) <= 6, f"{path.name} has visible artwork clipped at its edge"
            else:
                assert all(alpha.getpixel(p) == 0 for p in [(0,0),(last,0),(0,last),(last,last)]), f"{path.name} has a clipped edge"
            colors = sprite.convert("RGBA").getcolors(edge * edge)
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
                # Valid PCM WAVs may include metadata chunks before data.
                # Inspect the stream rather than assuming a 44-byte header.
                with wave.open(str(path)) as clip:
                    assert clip.getcomptype() == 'NONE'
                    assert len(clip.readframes(clip.getnframes())) == clip.getnframes() * clip.getnchannels() * clip.getsampwidth()
    for name in ("book", "counting", "paint", "piano"):
        with Image.open(ROOT / f"assets/jungle/covers/{name}.avif") as cover:
            assert cover.size == (420, 420) and cover.format == "AVIF"
    art = ROOT / "assets/dino-paint/art"
    assert not (ROOT / "assets/dino-paint/crayons").exists(), "crayons are drawn as color boxes"
    for number in range(1, 13):
        assert '<svg ' in (ROOT / f"art/paint/scene{number}.svg").read_text()
        with Image.open(art / f"scene{number}-thumb.avif") as thumb:
            assert thumb.size == (256, 192) and len(thumb.getcolors(1 << 16) or range(1 << 16)) > 16, "scene thumbnail is not smooth"
    # Every scene has its tall page, with a thumbnail of that shape.
    for number in range(1, 31):
        assert '<svg ' in (ROOT / f"art/paint/portrait{number}.svg").read_text()
        with Image.open(art / f"portrait{number}-thumb.avif") as thumb:
            assert thumb.size == (192, 256), "tall scene thumbnail has the wrong shape"
    for number in range(1, 31):
        svg = (ROOT / f"art/paint/dino{number}.svg").read_text()
        assert '<path id="body" fill="#fff"' in svg and ('<path id="ink" fill="#000"' in svg or '<g id="ink"' in svg)
        _, width, height, _, _ = stencil_source(number)
        with render(svg, *fit(width, height, *CANVAS)) as dinosaur:
            assert 720 in dinosaur.size or 960 in dinosaur.size, "vector source has the wrong page space"
            red, green, blue, alpha = dinosaur.convert("RGBA").split()
            opaque = alpha.point(lambda v: 255 if v == 255 else 0)
            lightest = ImageChops.darker(ImageChops.darker(red, green), blue).point(lambda v: 255 if v > 240 else 0)
            darkest = ImageChops.lighter(ImageChops.lighter(red, green), blue).point(lambda v: 255 if v < 40 else 0)
            levels = alpha.histogram()
            assert ImageChops.multiply(opaque, lightest).histogram()[255] > 10000, "dinosaur lost its opaque white body"
            assert ImageChops.multiply(opaque, darkest).histogram()[255] > 1000, "dinosaur lost its ink"
            assert levels[0] > 10000, "dinosaur erased its surrounding scenery"
            assert sum(levels[1:255]) > 100, "dinosaur edges are not smooth"
        for kind in ("preview",):
            with Image.open(art / f"dino{number}-{kind}.avif") as picture:
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
    print("local asset test: watercolor scene pages, cut-outs, current artwork only, opaque dinosaur bodies, BIOS font, VGA crayons, voices and brief feedback passed")


if __name__ == "__main__":
    main()

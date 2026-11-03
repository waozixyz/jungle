#!/usr/bin/env python3
"""Stage title foregrounds and background plates from full-detail PNG sources.

The built-in image_gen extractions/inpainting and prompts are recorded in
tools/art_provenance/title-layers/prompts.json. --finish-generated preserves the
approved scene's RGB, using the generated extraction's actual alpha matte;
inpainted pixels are restricted to that silhouette. It is an explicit artwork
preparation step, never part of a normal build. Normal invocation only exports
the ignored local PNG originals through the shared role-specific WebP exporter.
"""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageFilter
from image_exports import export_image

ROOT = Path(__file__).resolve().parents[1]


def finish(entry):
    name = entry['name']
    original = Image.open(ROOT/f'assets/jungle/title/{name}.webp').convert('RGB')
    inputs = ROOT/'work/title-layers/input'
    extraction = Image.open(inputs/f'{name}-extraction.png').convert('RGBA')
    inpaint = Image.open(inputs/f'{name}-inpaint.png').convert('RGB')
    assert original.size == extraction.size == inpaint.size
    alpha = extraction.getchannel('A')
    if entry['normalize_alpha']:
        # The portrait export's solid region was 253, with a diffuse low-alpha
        # halo outside it. Restore its matte range, keeping antialiased edges.
        alpha = alpha.point(lambda a: max(0, min(255, (a-238)*255//15)))
    else:
        alpha = alpha.point(lambda a: min(255, round(a*255/253)))
    dx, dy = entry['registration']
    registered = Image.new('L', original.size)
    registered.paste(alpha, (dx, dy))
    foreground = original.convert('RGBA')
    foreground.putalpha(registered)
    foreground.paste((0, 0, 0, 0), mask=registered.point(lambda a: 255 if a == 0 else 0))
    # Reconstruct only the pixels behind the object; the surrounding accepted
    # painting stays byte-for-byte identical. The soft boundary avoids seams.
    patch = registered.point(lambda a: 255 if a else 0)
    patch = patch.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(0.7))
    background = Image.composite(inpaint, original, patch)
    source = ROOT/entry['source']
    source.parent.mkdir(parents=True, exist_ok=True)
    foreground.save(str(source)+'-foreground.png', optimize=True)
    background.save(str(source)+'-background.png', optimize=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--finish-generated', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((ROOT/'tools/art_provenance/title-layers/prompts.json').read_text())
    for entry in manifest['assets']:
        if args.finish_generated:
            finish(entry)
        for kind in ('background', 'foreground'):
            source = ROOT/(entry['source']+f'-{kind}.png')
            destination = ROOT/(entry['runtime']+f'-{kind}.webp')
            destination.parent.mkdir(parents=True, exist_ok=True)
            export_image(source, destination, 'title-background' if kind == 'background' else 'cutout')
        print(f'title layers: {entry["name"]} original PNG and optimized WebP')


if __name__ == '__main__':
    main()

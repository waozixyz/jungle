#!/usr/bin/env python3
"""Reproduce the approved title WebP masters, silhouette glows and visual QA sheets.

The only geometry input is title_hotspots.json. Coordinates and glow rectangles
are source pixels, including for cropped glows. Pillow + numpy; no generators.
Run from any directory: python3 tools/title_glow.py
"""
from pathlib import Path
import argparse
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from image_exports import export_image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'local/art-development/title-world-proposal'
DEBUG = SOURCE / 'hotspot-debug'
ORIGINALS = {'treehouse': 'treehouse-room', 'bookshelf': 'bookshelf-closeup',
             'campus': 'jungle-campus', 'music': 'music-room',
             'farm': '../owner-farm-beach-source/27', 'port': '../market/port-landscape-market-path', 'aquarium': '../title-waterfront/aquarium'}


def room_owned(scene):
    """Rooms built from object layers, and the window view, come from
    tools/title_room.py; this tool must not overwrite them with old paintings.
    tools/title_desert.py exports the Desert edge scene and its layers whole;
    tools/title_places.py the Market, the Jungle Path and the Farm with its
    path to the Market."""
    return bool(scene.get('objects') or scene.get('back')) or scene.get('name') in ('desert', 'market', 'jungle-path', 'farm')


def validate(data):
    """Fail before writing on malformed geometry or unresolved destinations."""
    assert set(data) == {'width', 'height', 'scenes'}
    assert (data['width'], data['height']) == (1672, 941)
    names = {s['name'] for s in data['scenes']}
    assert {s['name'] for s in data['scenes'] if not room_owned(s)} <= set(ORIGINALS)
    games = {line.split('|')[1] for line in
             (ROOT / 'games/catalog.txt').read_text().splitlines() if '|' in line}
    for original in data['scenes']:
        assert set(original) <= {'name', 'image', 'low', 'hotspots', 'portrait', 'background', 'foreground', 'paper', 'decorations', 'objects', 'back'}
        variants = [dict(original, width=data['width'], height=data['height'])]
        if 'portrait' in original:
            portrait = original['portrait']
            assert {h['id']: h['target'] for h in portrait['hotspots']} == {h['id']: h['target'] for h in original['hotspots']}
            variants.append(dict(portrait, name=original['name'] + '-portrait'))
        for scene in variants:
            validate_variant(scene, names, games)


def validate_variant(scene, names, games):
    ids = set()
    for h in scene['hotspots']:
        assert {'id', 'target', 'polygon', 'glow', 'glow_rect'} <= set(h)
        assert set(h) <= {'id', 'target', 'polygon', 'glow', 'glow_rect', 'rest', 'occlusion', 'sign', 'object'}
        assert h['id'] not in ids
        ids.add(h['id'])
        kind, dest = h['target'].split(':', 1)
        assert (kind == 'scene' and dest in names) or (kind == 'game' and dest in games) or (kind == 'notice' and dest == 'Desert') or (kind == 'dialogue' and dest == 'desert-guide') or (kind == 'guide' and dest == 'tour') or (kind == 'book' and dest == 'sweet-porridge') or (kind == 'look' and bool(dest) and not h.get('sign')) or (kind == 'locked' and dest == h['id'] and not h.get('sign'))
        assert len(h['polygon']) >= 3
        for p in h['polygon']:
            assert len(p) == 2 and all(type(n) is int for n in p)
            assert 0 <= p[0] < scene['width'] and 0 <= p[1] < scene['height']
        x, y, w, height = h['glow_rect']
        assert all(type(n) is int for n in h['glow_rect'])
        assert 0 <= x < x+w <= scene['width'] and 0 <= y < y+height <= scene['height']
        assert all(x <= px < x+w and y <= py < y+height for px, py in h['polygon'])
        assert h['glow'].endswith(('.png','.webp'))


def occlude(image, h):
    """Keep the original foreground above every part of navigation feedback."""
    if not h.get('occlusion'):
        return image
    x, y, w, height = h['glow_rect']
    mask = Image.new('L', (w*3, height*3))
    ImageDraw.Draw(mask).polygon([((px-x)*3, (py-y)*3) for px, py in h['occlusion']], fill=255)
    # Expand one source pixel so antialiasing never spills onto the tiger.
    mask = mask.filter(ImageFilter.MaxFilter(7)).resize((w, height), Image.Resampling.LANCZOS)
    rgba = np.array(image)
    rgba[:, :, 3] = np.rint(rgba[:, :, 3].astype(float)*(1-np.asarray(mask)/255)).astype('uint8')
    rgba[rgba[:, :, 3] == 0, :3] = 0
    return Image.fromarray(rgba)

def glow(h):
    x, y, w, height = h['glow_rect']
    # Supersampling keeps curves and small frog fingers smooth. Retraced,
    # zero-area bridges let a single polygon describe detached loose shapes.
    scale = 3
    mask = Image.new('L', (w*scale, height*scale))
    ImageDraw.Draw(mask).polygon([((px-x)*scale, (py-y)*scale)
                                 for px, py in h['polygon']], fill=255)
    # Remove rasterized zero-area bridges, without changing the filled lobes.
    mask = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    mask = mask.resize((w, height), Image.Resampling.LANCZOS)
    interior = np.asarray(mask.filter(ImageFilter.GaussianBlur(0.7)), dtype=np.float32)/255
    # A luminous golden edge immediately outside the silhouette, then a
    # smooth falloff over roughly 24 px. Keep the inner lift separate so
    # warm watercolor paper cannot swallow the hover feedback.
    rim = mask.filter(ImageFilter.MaxFilter(7))
    near = np.asarray(rim.filter(ImageFilter.GaussianBlur(2.8)), dtype=np.float32)/255
    far = np.asarray(mask.filter(ImageFilter.GaussianBlur(9)), dtype=np.float32)/255
    outer = np.minimum(240, near*255 + far*100)
    alpha = outer*(1-interior) + interior*82
    rgba = np.zeros((height, w, 4), dtype=np.uint8)
    for channel, (outside, inside) in enumerate(zip((255, 213, 74), (255, 249, 222))):
        rgba[:, :, channel] = np.rint(outside*(1-interior)+inside*interior).astype(np.uint8)
    rgba[:, :, 3] = np.rint(alpha).clip(0, 255).astype(np.uint8)
    rgba[rgba[:, :, 3] == 0, :3] = 0
    # Layered navigation extends under its foreground. Occlusion geometry
    # remains an input exclusion, never a baked visual notch in this arrow.
    return Image.fromarray(rgba) if h.get('rest') else occlude(Image.fromarray(rgba), h)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenes', nargs='+', help='Only reproduce these base scenes')
    args = parser.parse_args()
    data = json.loads((ROOT / 'tools/title_hotspots.json').read_text())
    validate(data)
    debug = DEBUG / '-'.join(args.scenes) if args.scenes else DEBUG
    debug.mkdir(parents=True, exist_ok=True)
    panels = []
    count = 0
    variants = []
    for scene in data['scenes']:
        if args.scenes and scene['name'] not in args.scenes or room_owned(scene):
            continue
        variants.append(dict(scene, width=data['width'], height=data['height'], source=SOURCE / (ORIGINALS[scene['name']]+'.png')))
        if 'portrait' in scene:
            portrait_source = (ROOT / 'local/art-development/market/port-portrait-market-path.png'
                               if scene['name'] == 'port' else
                               ROOT / 'local/art-development/title-waterfront' / (scene['name'] + '-portrait.png')
                               if scene['name'] == 'aquarium' else
                               ROOT / 'local/art-development/title-portrait-candidates' / (scene['name'] + '.png'))
            variants.append(dict(scene['portrait'], name=scene['name'] + '-portrait', source=portrait_source))
    for scene in variants:
        source = Image.open(scene['source']).convert('RGB')
        assert source.size == (scene['width'], scene['height'])
        image_path = ROOT / scene['image']
        image_path.parent.mkdir(parents=True, exist_ok=True)
        export_image(scene['source'], image_path, 'title-background')
        low = source.resize((240, round(240 * scene['height'] / scene['width'])), Image.Resampling.LANCZOS)
        export_image(scene['source'], ROOT / scene['low'], 'title-background', size=low.size)
        composite = source.convert('RGBA')
        outlines = composite.copy()
        draw = ImageDraw.Draw(outlines)
        for i, h in enumerate(scene['hotspots']):
            overlay = glow(h)
            path = ROOT / h['glow']
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix == '.webp': overlay.save(path,'WEBP',lossless=True,exact=True,method=6)
            else: overlay.save(path, optimize=True)
            composite.alpha_composite(overlay, tuple(h['glow_rect'][:2]))
            color = ['#e33b51', '#165eff', '#019b7c', '#c343e3', '#ff8618'][i % 5]
            points = [tuple(p) for p in h['polygon']]
            draw.line(points+[points[0]], fill=color, width=2)
            px = min(p[0] for p in points)
            py = min(p[1] for p in points)
            draw.text((px, max(0, py-14)), h['id'], fill=color, stroke_width=2, stroke_fill='white')
            # Full-size individual overlay: inspect silhouettes without other glows.
            single = source.convert('RGBA')
            single.alpha_composite(overlay, tuple(h['glow_rect'][:2]))
            single.convert('RGB').save(debug / f"{scene['name']}-{h['id']}.webp", quality=90)
            single.save(debug / f"{scene['name']}-{h['id']}.png")
            count += 1
        composite.save(debug / f"{scene['name']}-all-glows.png")
        outlines.save(debug / f"{scene['name']}-polygons.png")
        panel = Image.new('RGB', (836, 498), '#fff7e5')
        ImageDraw.Draw(panel).text((12, 8), scene['name'], fill='#3c382d')
        panel.paste(composite.resize((836, 470), Image.Resampling.LANCZOS).convert('RGB'), (0, 28))
        panels.append(panel)
    sheet = Image.new('RGB', (1672, 498 * ((len(panels) + 1) // 2)), '#fff7e5')
    for i, panel in enumerate(panels):
        sheet.paste(panel, ((i % 2)*836, (i // 2)*498))
    sheet.save(debug / 'all-glows.png')
    print(f'Generated {len(variants)} WebP/placeholder pairs and {count} RGBA glows; geometry and catalog targets valid.')
    print('Contact sheet:', (debug/'all-glows.png').relative_to(ROOT))


if __name__ == '__main__':
    main()

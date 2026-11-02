#!/usr/bin/env python3
"""Reproduce translucent navigation art. The foreground scene layer occludes
the complete arrow; hit exclusions are kept independently in the manifest.
"""
import json
from PIL import Image, ImageDraw, ImageFilter
from title_glow import ROOT, glow


def arrow(h):
    x, y, w, height = h['glow_rect']
    points = [((px-x)*3, (py-y)*3) for px, py in h['polygon']]
    shadow = Image.new('RGBA', (w*3, height*3))
    ImageDraw.Draw(shadow).polygon([(px, py+12) for px, py in points], fill=(30, 100, 88, 42))
    shadow = shadow.filter(ImageFilter.GaussianBlur(7))
    draw = ImageDraw.Draw(shadow)
    draw.polygon(points, fill=(76, 180, 166, 88))
    draw.line(points + points[:1], fill=(255, 242, 192, 120), width=9, joint='curve')
    return shadow.resize((w, height), Image.Resampling.LANCZOS)


def main():
    count = 0
    for base in json.loads((ROOT/'tools/title_hotspots.json').read_text())['scenes']:
        for scene in [base] + ([base['portrait']] if 'portrait' in base else []):
            for h in scene['hotspots']:
                if not h.get('rest'):
                    continue
                path = ROOT/h['rest']
                path.parent.mkdir(parents=True, exist_ok=True)
                arrow(h).save(path, optimize=True)
                visual = dict(h)
                visual.pop('occlusion', None)
                glow(visual).save(ROOT/h['glow'], optimize=True)
                count += 1
    print(f'title navigation: {count} translucent arrows and complete glows; foreground layers own occlusion')


if __name__ == '__main__':
    main()

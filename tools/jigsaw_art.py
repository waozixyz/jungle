"""Cut original generated pictures into complementary, antialiased jigsaw atlases."""
from pathlib import Path
import math
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SCENES = ('tiger-stream', 'duck-pond', 'meadow-train')
GRIDS = (2, 3, 4, 5, 6, 8)
SIZE = 1200


def edge(x, y, dx, dy, sign):
    # A rounded neck and bulb; adjoining pieces traverse the same curve.
    points = []
    for step in range(81):
        t = step / 80
        bump = 0
        if .32 < t < .68:
            u = (t - .32) / .36
            bump = math.sin(math.pi * u) ** .65 * .20 * sign
        points.append((x + dx*t + dy*bump, y + dy*t - dx*bump))
    return points


def polygon(n, row, col, cell, pad):
    top = 0 if row == 0 else (1 if (row+col) % 2 else -1)
    right = 0 if col == n-1 else (1 if (row+col) % 2 else -1)
    bottom = 0 if row == n-1 else (1 if (row+col) % 2 else -1)
    left = 0 if col == 0 else (1 if (row+col) % 2 else -1)
    points = edge(0, 0, 1, 0, top) + edge(1, 0, 0, 1, right)
    points += edge(1, 1, -1, 0, bottom) + edge(0, 1, 0, -1, left)
    return [(round((x*cell+pad)*2), round((y*cell+pad)*2)) for x, y in points]


def main():
    dest = ROOT/'assets/jigsaw'
    dest.mkdir(parents=True, exist_ok=True)
    for name in SCENES:
        source = Image.open(ROOT/'art/generated/jigsaw'/f'{name}.png').convert('RGB')
        source = source.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
        source.save(dest/f'{name}.jpg', quality=92)
        source.resize((320,320), Image.Resampling.LANCZOS).save(dest/f'{name}-thumb.jpg', quality=90)
        for n in GRIDS:
            cell = SIZE//n
            pad = cell//4
            tile = cell + pad*2
            atlas = Image.new('RGBA', (tile*n, tile*n))
            for row in range(n):
                for col in range(n):
                    mask = Image.new('L', (tile*2, tile*2))
                    ImageDraw.Draw(mask).polygon(polygon(n,row,col,cell,pad), fill=255)
                    mask = mask.resize((tile,tile), Image.Resampling.LANCZOS)
                    fragment = source.crop((col*cell-pad,row*cell-pad,(col+1)*cell+pad,(row+1)*cell+pad)).convert('RGBA')
                    fragment.putalpha(mask)
                    # A fine warm outline makes each loose shape legible.
                    rim = Image.new('RGBA',fragment.size,(93,72,48,90))
                    rim.putalpha(Image.eval(mask.filter(ImageFilter.MaxFilter(3)),lambda x:x//3))
                    rim.alpha_composite(fragment)
                    atlas.paste(rim,(col*tile,row*tile))
            atlas.save(dest/f'{name}-{n}.png', optimize=True)
        print('Built jigsaw picture and six atlases:', name, flush=True)
    Image.open(dest/'tiger-stream.jpg').convert('RGB').resize((420,420),Image.Resampling.LANCZOS).save(ROOT/'assets/jungle/covers/jigsaw.jpg',quality=90,optimize=True,progressive=True)


if __name__ == '__main__':
    main()

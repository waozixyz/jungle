"""Extract one complete illustration and reject neighboring atlas fragments."""
from collections import deque
from math import hypot
from statistics import median
from PIL import Image, ImageChops, ImageDraw, ImageFilter


def regions(mask):
    width, height = mask.size
    pixels = mask.tobytes()
    seen = bytearray(len(pixels))
    result = []
    for start, value in enumerate(pixels):
        if not value or seen[start]:
            continue
        seen[start] = 1
        queue = deque([start])
        points = []
        left = right = start % width
        top = bottom = start // width
        while queue:
            at = queue.popleft()
            points.append(at)
            x, y = at % width, at // width
            left, right = min(left, x), max(right, x)
            top, bottom = min(top, y), max(bottom, y)
            for neighbor in ((at - 1 if x else -1), (at + 1 if x + 1 < width else -1),
                             (at - width if y else -1), (at + width if y + 1 < height else -1)):
                if neighbor >= 0 and pixels[neighbor] and not seen[neighbor]:
                    seen[neighbor] = 1
                    queue.append(neighbor)
        if len(points) >= 24:
            result.append((len(points), (left, top, right + 1, bottom + 1), points))
    return result


def illustration(atlas, index, columns, name):
    row, column = divmod(index, columns)
    cell_width, cell_height = atlas.width / columns, atlas.height / columns
    nominal = (column * cell_width, row * cell_height,
               (column + 1) * cell_width, (row + 1) * cell_height)
    margin = min(cell_width, cell_height) * .32
    box = tuple(round(v) for v in (max(0, nominal[0] - margin), max(0, nominal[1] - margin),
                                  min(atlas.width, nominal[2] + margin), min(atlas.height, nominal[3] + margin)))
    rgba = atlas.crop(box).convert('RGBA')
    source = rgba.convert('RGB')
    transparent = rgba.getchannel('A').getextrema()[0] < 255
    # Estimate the paper, rather than copying a rectangle of it into every tile.
    samples = [pixel for pixel in source.getdata() if min(pixel) > 220 and max(pixel) - min(pixel) < 28]
    background = tuple(round(median(p[c] for p in samples)) for c in range(3)) if samples else (249, 247, 237)
    differences = ImageChops.difference(source, Image.new('RGB', source.size, background)).split()
    distance = ImageChops.lighter(differences[0], ImageChops.lighter(differences[1], differences[2]))
    strong = (rgba.getchannel('A').point(lambda v: 255 if v > 32 else 0) if transparent else distance.point(lambda v: 255 if v > 24 else 0))
    strong = strong.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(3))
    found = regions(strong)
    cx, cy = (nominal[0] + nominal[2]) / 2 - box[0], (nominal[1] + nominal[3]) / 2 - box[1]
    def edge(region):
        _, (l, t, r, b), _ = region
        return l <= 1 or t <= 1 or r >= source.width - 1 or b >= source.height - 1
    def score(region):
        area, (l, t, r, b), _ = region
        d = ((l + r) / 2 - cx) ** 2 / cell_width ** 2 + ((t + b) / 2 - cy) ** 2 / cell_height ** 2
        return area / (1 + 12 * d)
    eligible = [region for region in found if not edge(region)]
    assert eligible, f'No isolated illustration for {name}'
    main = max(eligible, key=score)
    selected = [main]
    _, (ml, mt, mr, mb), _ = main
    # Keep detached slices, cloves and petals near this object. Reject any
    # component continuing beyond the expanded window into another picture.
    for region in eligible:
        if region is main:
            continue
        area, (l, t, r, b), _ = region
        separation = hypot(max(0, ml - r, l - mr), max(0, mt - b, t - mb))
        center_x, center_y = (l + r) / 2 + box[0], (t + b) / 2 + box[1]
        if (separation < min(cell_width, cell_height) * .10 and area >= main[0] * .008
            and nominal[0] + cell_width * .06 < center_x < nominal[2] - cell_width * .06
            and nominal[1] + cell_height * .06 < center_y < nominal[3] - cell_height * .06):
            selected.append(region)
    body = bytearray(source.width * source.height)
    for _, _, points in selected:
        for at in points:
            body[at] = 255
    alpha = Image.frombytes('L', source.size, bytes(body)).filter(ImageFilter.MaxFilter(3))
    if transparent:
        alpha = ImageChops.multiply(alpha.filter(ImageFilter.MaxFilter(3)), rgba.getchannel('A'))
    else:
        outside = alpha.copy()
        ImageDraw.floodfill(outside, (0, 0), 128)
        alpha = outside.point(lambda v: 0 if v == 128 else 255)
    bounds = alpha.getbbox()
    assert bounds, name
    alpha = alpha.filter(ImageFilter.GaussianBlur(.8))
    picture = source.convert('RGBA')
    picture.putalpha(alpha)
    picture = picture.crop((max(0, bounds[0] - 3), max(0, bounds[1] - 3),
                            min(source.width, bounds[2] + 3), min(source.height, bounds[3] + 3)))
    picture.thumbnail((360, 360), Image.Resampling.LANCZOS)
    output = Image.new('RGBA', (420, 420))
    output.alpha_composite(picture, ((420 - picture.width) // 2, (420 - picture.height) // 2))
    return output

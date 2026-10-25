"""Prepare the generated coloring art without changing the paint game's geometry.

Identify complete connected silhouettes rather than cutting creatures at atlas
cell boundaries. Keep the existing twelve stamp sizes and six scene sizes.
"""
from collections import deque
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'assets/dino-paint/art'
SIZES = ((240,125),(240,144),(240,87),(240,140),(209,184),(240,83),
         (126,184),(240,68),(240,71),(240,63),(240,109),(240,168))


def components(image):
    ink = image.convert('L').point(lambda v: 255 if v < 160 else 0)
    pixels = ink.load()
    width, height = image.size
    seen = bytearray(width * height)
    result = []
    for y in range(height):
        for x in range(width):
            at = y * width + x
            if seen[at] or not pixels[x,y]:
                continue
            seen[at] = 1
            queue = deque([(x,y)])
            points = []
            while queue:
                xx, yy = queue.popleft()
                points.append((xx,yy))
                for ny in range(max(0,yy-1), min(height,yy+2)):
                    for nx in range(max(0,xx-1), min(width,xx+2)):
                        pos = ny * width + nx
                        if not seen[pos] and pixels[nx,ny]:
                            seen[pos] = 1
                            queue.append((nx,ny))
            if len(points) > 100:
                box = (min(p[0] for p in points), min(p[1] for p in points),
                       max(p[0] for p in points)+1, max(p[1] for p in points)+1)
                result.append((len(points),box,points))
    return result


def dinosaur(source, component, size):
    _, box, points = component
    left, top, right, bottom = box
    region = Image.new('L', (right-left+6,bottom-top+6), 0)
    for x,y in points:
        region.putpixel((x-left+3,y-top+3),255)
    # Close small antialias gaps only for the opaque-body boundary.
    boundary = region.filter(ImageFilter.MaxFilter(3))
    outside = boundary.point(lambda v: 0 if v else 255)
    ImageDraw.floodfill(outside,(0,0),128)
    alpha = outside.point(lambda v: 0 if v == 128 else 255)
    art = source.convert('RGBA').crop((left-3,top-3,right+3,bottom+3))
    art.putalpha(alpha)
    width,height = size
    scale = min((width-8)/art.width,(height-8)/art.height)
    art = art.resize((max(1,round(art.width*scale)),max(1,round(art.height*scale))),Image.Resampling.LANCZOS)
    result = Image.new('RGBA',size)
    result.paste(art,((width-art.width)//2,(height-art.height)//2))
    # Canonical three-state pixels: transparent exterior, white body, black ink.
    canonical = Image.new('RGBA',size)
    for y in range(height):
        for x in range(width):
            r,g,b,a = result.getpixel((x,y))
            if a >= 128:
                canonical.putpixel((x,y),(0,0,0,255) if r+g+b < 540 else (255,255,255,255))
    assert canonical.getchannel('A').getbbox()
    assert dict((color,count) for count,color in canonical.getcolors(canonical.width*canonical.height)).get((255,255,255,255),0) > 100
    return canonical


def main():
    source = Image.open(ROOT/'art/generated/dino-coloring-shapes.png').convert('RGBA')
    found = components(source)
    for index,size in enumerate(SIZES):
        row,column = divmod(index,4)
        candidates = [item for item in found if
                      column*source.width/4 <= (item[1][0]+item[1][2])/2 < (column+1)*source.width/4 and
                      row*source.height/4 <= (item[1][1]+item[1][3])/2 < (row+1)*source.height/4]
        assert candidates, f'Missing complete dinosaur {index+1}'
        picture = dinosaur(source,max(candidates,key=lambda item:item[0]),size)
        for scale in range(1,5):
            version = picture if scale == 4 else picture.resize((max(1,size[0]*scale//4),max(1,size[1]*scale//4)),Image.Resampling.NEAREST)
            version.save(ART/f'dino{index+1}-s{scale}.png',optimize=True)
    scenery = Image.open(ROOT/'art/generated/dino-coloring-scenery.png').convert('L')
    for index in range(6):
        row,column = divmod(index,2)
        box = (round(column*scenery.width/2)+4,round(row*scenery.height/3)+4,
               round((column+1)*scenery.width/2)-4,round((row+1)*scenery.height/3)-4)
        page = scenery.crop(box).resize((240,180),Image.Resampling.LANCZOS)
        ink = page.point(lambda v:255 if v < 180 else 0).filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
        page = ink.point(lambda v:0 if v else 255).convert('RGBA')
        ImageDraw.Draw(page).rectangle((0,0,239,179),outline='white',width=4)
        page.save(ART/f'scene{index+1}.png',optimize=True)
        page.resize((78,48),Image.Resampling.LANCZOS).save(ART/f'scene{index+1}-thumb.png',optimize=True)
    print('Prepared twelve complete dinosaur silhouettes and six new coloring scenes; stamp geometry retained.')

if __name__ == '__main__':main()

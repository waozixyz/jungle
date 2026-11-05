"""Find a generous visible tap on each map landmark, including overlapping art."""
import math
from PIL import Image, ImageDraw, ImageFilter


def selectable_point(view, spot, size):
    """Return source x/y and the winning hit's clear radius in window pixels.

    Rasterize the rotated silhouettes at the actual viewport scale, subtract
    all hits with runtime priority, and find the largest remaining tap disk.
    This detects a covered destination without forbidding painted overlaps.
    """
    width, height = view['width'], view['height']
    scale = min(size[0]/width, size[1]/height)
    raster_size = (math.ceil(width*scale)+2, math.ceil(height*scale)+2)

    def mask(hotspot):
        x,y,w,h = hotspot['glow_rect']
        cx,cy = x+w/2,y+h/2
        angle = math.radians(hotspot.get('rotation',0))
        c,s = math.cos(angle),math.sin(angle)
        points = [((cx+(px-cx)*c-(py-cy)*s)*scale+1,
                   (cy+(px-cx)*s+(py-cy)*c)*scale+1) for px,py in hotspot['polygon']]
        result = Image.new('L',raster_size)
        ImageDraw.Draw(result).polygon(points,fill=255)
        return result

    own = mask(spot)
    area = spot['glow_rect'][2]*spot['glow_rect'][3]
    index = view['hotspots'].index(spot)
    for other_index,other in enumerate(view['hotspots']):
        other_area = other['glow_rect'][2]*other['glow_rect'][3]
        if other is not spot and (other_area < area or other_area == area and other_index < index):
            own.paste(0,mask=mask(other))
    box = own.getbbox()
    if not box:
        raise AssertionError(f"{spot['id']} has no selectable map pixels at {size}")
    # A black frame makes erosion honor the silhouette edges at crop borders.
    left,top,right,bottom = box
    crop = Image.new('L',(right-left+2,bottom-top+2))
    crop.paste(own.crop(box),(1,1))
    low,high,best = 0,min(crop.size)//2,crop
    while low < high:
        radius = (low+high+1)//2
        inset = crop.filter(ImageFilter.MinFilter(radius*2+1))
        if inset.getbbox():
            low,best = radius,inset
        else:
            high = radius-1
    # Select an actual surviving pixel rather than the possibly empty bbox center.
    pixels = best.load()
    bx,by,br,bb = best.getbbox()
    candidates = [(x,y) for y in range(by,bb) for x in range(bx,br) if pixels[x,y]]
    cx,cy = (bx+br-1)/2,(by+bb-1)/2
    x,y = min(candidates,key=lambda p:(p[0]-cx)**2+(p[1]-cy)**2)
    return ((left+x-2+.5)/scale,(top+y-2+.5)/scale,low)

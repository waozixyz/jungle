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


FOG_RIM = 110.0


def fog_alpha(world, areas, xx, yy):
    """host/jungle_title.zi TitleFogAlpha over numpy sample grids XX, YY:
    visited regions clear, routes clear between two visited neighbours,
    then a smoothstep rim of FOG_RIM map pixels."""
    import numpy as np
    nearest = np.full(xx.shape, FOG_RIM, dtype=np.float32)
    for place in world['exploration']:
        if place['area'] not in areas:
            continue
        for cx, cy, rx, ry in place['region']:
            nx, ny = (xx - cx) / rx, (yy - cy) / ry
            q = nx * nx + ny * ny
            s = np.sqrt(q)
            distance = np.where(q <= 1, 0, (s - 1) * s / np.sqrt((nx / rx) ** 2 + (ny / ry) ** 2 + 1e-30))
            nearest = np.minimum(nearest, distance)
    for route in world['exploration_routes']:
        if not set(route['areas']) <= set(areas):
            continue
        for (ax, ay), (bx, by) in zip(route['path'], route['path'][1:]):
            ux, uy = bx - ax, by - ay
            along = np.clip(((xx - ax) * ux + (yy - ay) * uy) / (ux * ux + uy * uy), 0, 1)
            distance = np.hypot(xx - ax - ux * along, yy - ay - uy * along) - route['radius']
            nearest = np.minimum(nearest, np.maximum(distance, 0))
    edge = np.clip(nearest / FOG_RIM, 0, 1)
    return (255 * edge * edge * (3 - 2 * edge) + .5).astype(np.uint8)

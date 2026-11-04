#!/usr/bin/env python3
"""Export the window's masked clean plates and seamless local motion atlases.

Generated inpainting is composited only inside the animal footprints. Leaves
and water retain their original watercolor pixels, displaced within soft masks.
All editable intermediates remain in ignored local/art-development/.
"""
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import map_coordinates
from image_exports import export_image
ROOT=Path(__file__).resolve().parents[1]
MASTERS=ROOT/'local/art-development/treehouse-window-animation'
OUT=ROOT/'assets/jungle/title/window-animation'
REGIONS={
 'landscape': [[(200,287),(493,287),(493,639),(200,639)],[(1078,198),(1220,198),(1220,270),(1078,270)],[(640,470),(747,470),(747,573),(640,573)],[(604,602),(684,602),(684,687),(604,687)]],
 'portrait': [[(641,546),(944,546),(944,854),(641,854)],[(243,351),(422,351),(422,453),(243,453)],[(149,799),(253,799),(253,909),(149,909)],[(228,900),(322,900),(322,992),(228,992)]]}
# Bounds enclose nearby and foreground leaf clusters; edges remain stationary.
LEAVES={'landscape':[(433,330,263,229),(1220,610,320,222),(321,12,302,200),(15,646,294,160)],
        'portrait':[(502,665,255,232),(682,378,287,178),(279,74,275,185),(0,1090,303,216)]}
WATER={'landscape':[(974,469),(1042,482),(1098,493),(1108,513),(1074,530),(1038,550),(1030,574),(985,598),(921,587),(898,571),(916,550),(965,535),(1007,523),(1015,504),(984,493)],
       'portrait':[(418,806),(469,811),(516,824),(516,842),(472,852),(458,868),(486,884),(513,893),(496,915),(440,914),(421,895),(398,889),(371,886),(366,869),(397,847),(436,838),(434,827),(408,821)]}

def save(image,name,role):
    source=MASTERS/(name+'.png'); image.save(source)
    target=OUT/(name+'.webp'); export_image(source,target,role)
    return target.relative_to(ROOT).as_posix()

def motion(image,rect,polygon,kind,name):
    x,y,w,h=rect
    patch=np.asarray(image.crop((x,y,x+w,y+h)).convert('RGB'),dtype=np.float32)
    yy,xx=np.mgrid[:h,:w].astype(float)
    if polygon:
        mask=Image.new('L',(w,h)); ImageDraw.Draw(mask).polygon([(px-x,py-y) for px,py in polygon],fill=255)
        mask=np.asarray(mask.filter(ImageFilter.GaussianBlur(1.2)),dtype=float)/255
    else:
        edge=np.minimum.reduce([xx/22,yy/22,(w-1-xx)/22,(h-1-yy)/22])
        mask=np.clip(edge,0,1)
    sheet=Image.new('RGBA',(w*24,h))
    for frame in range(24):
        phase=frame*2*np.pi/24
        if kind=='water':
            dx=1.7*np.sin(yy*.18-phase)*mask
            dy=1.3*np.cos(xx*.12+yy*.09-phase)*mask
        else:
            dx=1.8*np.sin(phase)*mask*(yy/h)
            dy=.8*np.sin(phase+.4)*mask
        rgb=np.stack([map_coordinates(patch[:,:,c],[yy+dy,xx+dx],order=1,mode='nearest') for c in range(3)],axis=2)
        if kind=='water':
            # Highlights travel downstream; periodic phase gives no seam jump.
            rgb+= (3.4*np.sin(yy*.21+xx*.05-phase)*mask)[:,:,None]
        rgba=np.dstack([np.clip(rgb,0,255),mask*255]).astype('uint8')
        rgba[rgba[:,:,3]==0,:3]=0
        sheet.paste(Image.fromarray(rgba),(frame*w,0))
    path=save(sheet,name,'exact')
    return {'scene':'window' if 'landscape' in name else 'window-portrait','path':path,'sheet':[24,24,w,h], 'rect':[x,y,w,h],'timing':[12 if kind=='water' else 6,4 if kind=='water' else 7,0], 'mode':0}

def main():
    OUT.mkdir(parents=True,exist_ok=True); MASTERS.mkdir(parents=True,exist_ok=True)
    layers=[]
    for orientation in REGIONS:
        stem='window' if orientation=='landscape' else 'window-portrait'
        original=Image.open(MASTERS/f'{orientation}-source.webp').convert('RGB')
        candidate=Image.open(MASTERS/f'{orientation}-clean-generated.png').convert('RGB')
        assert candidate.size==original.size
        mask=Image.new('L',original.size)
        for poly in REGIONS[orientation]: ImageDraw.Draw(mask).polygon(poly,fill=255)
        mask=mask.filter(ImageFilter.GaussianBlur(2))
        clean=Image.composite(candidate,original,mask)
        # Exact master proves pixels outside edit mask remain untouched.
        clean.save(MASTERS/f'{orientation}-clean-composited.png')
        export_image(MASTERS/f'{orientation}-clean-composited.png',ROOT/f'assets/jungle/title/{stem}.webp','title-background')
        export_image(MASTERS/f'{orientation}-clean-composited.png',ROOT/f'assets/jungle/title/{stem}-low.webp','title-background',size=(240,round(clean.height*240/clean.width)))
        for i,rect in enumerate(LEAVES[orientation]): layers.append(motion(clean,rect,None,'leaf',f'{orientation}-leaves-{i}'))
        poly=WATER[orientation]; xs,ys=zip(*poly); rect=(min(xs)-4,min(ys)-4,max(xs)-min(xs)+9,max(ys)-min(ys)+9)
        layers.append(motion(clean,rect,poly,'water',f'{orientation}-water'))
    (MASTERS/'environment-layers.json').write_text(json.dumps(layers,indent=2)+'\n')
if __name__=='__main__':main()

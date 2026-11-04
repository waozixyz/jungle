#!/usr/bin/env python3
"""Trim generated frames to one shared canvas, remove disconnected alpha dust,
and export exact WebP. Sources are private watercolor animation masters."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage
from image_exports import export_image
ROOT=Path(__file__).resolve().parents[1]
MASTER=ROOT/'local/art-development/treehouse-window-animation'
OUT=ROOT/'assets/jungle/title/window-animation'

def sheet(name,source,size):
    im=Image.open(MASTER/source).convert('RGBA')
    frames=[]
    cell=im.width//8
    for i in range(8):
        arr=np.array(im.crop((i*cell,0,(i+1)*cell,im.height)))
        alpha=arr[:,:,3]
        labels,n=ndimage.label(alpha>32)
        sizes=np.bincount(labels.ravel()); sizes[0]=0
        keep=labels==sizes.argmax()
        alpha[~ndimage.binary_dilation(keep,iterations=1)]=0
        alpha[alpha<20]=0
        arr[:,:,3]=alpha; arr[alpha==0,:3]=0
        frames.append(Image.fromarray(arr))
    boxes=[f.getbbox() for f in frames]
    top=min(b[1] for b in boxes); bottom=max(b[3] for b in boxes)
    atlas=Image.new('RGBA',(size[0]*8,size[1]))
    for i,f in enumerate(frames):
        f=f.crop((0,top,cell,bottom));f.thumbnail(size,Image.Resampling.LANCZOS)
        atlas.paste(f,(i*size[0]+(size[0]-f.width)//2,(size[1]-f.height)//2))
    master=MASTER/f'{name}-atlas.png';atlas.save(master)
    path=OUT/f'{name}.webp';export_image(master,path,'exact')
    return path.relative_to(ROOT).as_posix(),[8,8,*size]

def main():
    sheets={name:sheet(name,source,size) for name,source,size in [('toucan','toucan-clean.png',(192,224)),('bird','bird.png',(96,136)),('butterfly','butterfly-clean.png',(96,96))]}
    layers=json.loads((MASTER/'environment-layers.json').read_text())
    for scene,perch in [('window',[205,290,270,315]),('window-portrait',[590,530,270,315])]:
        path,shape=sheets['toucan'];layers.append(dict(scene=scene,path=path,sheet=shape,rect=perch,timing=[9,37,3],mode=2))
        for i,(y,offset,period) in enumerate([(220,0,23),(245,1.3,23.7),(210,2.8,24.4)]):
            path,shape=sheets['bird'];layers.append(dict(scene=scene,path=path,sheet=shape,rect=[0,y if scene=='window' else y+155,44,62],timing=[10,period,offset],mode=1))
        path,shape=sheets['butterfly'];layers.append(dict(scene=scene,path=path,sheet=shape,rect=[0,540 if scene=='window' else 900,65,65],timing=[11,29,9],mode=1))
    (ROOT/'tools/title_animations.json').write_text(json.dumps({'layers':layers},indent=2)+'\n')
if __name__=='__main__':main()

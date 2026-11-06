"""Export the stationary window frame and trim wildlife sprite padding."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from title_window_animation import *
from image_exports import export_image
# Inner wood edge, traced in the 240-pixel reference coordinates.
openings={'landscape':[(47,0),(204,0),(218,16),(227,40),(230,66),(227,91),(218,111),(200,120),(47,120),(25,113),(14,95),(9,70),(12,46),(23,22)],'portrait':[(0,101),(10,74),(34,44),(67,24),(103,13),(139,16),(173,31),(204,57),(224,90),(239,124),(239,208),(227,241),(209,266),(183,285),(151,298),(115,301),(79,294),(45,278),(22,251),(6,219),(0,197)]}
layers=json.loads((ROOT/'tools/title_animations.json').read_text())['layers']
for orientation in ('landscape', 'portrait'):
    clean=Image.open(MASTERS/f'{orientation}-clean-composited.png').convert('RGBA')
    # Stationary, exact watercolor frame occludes every wildlife layer.
    mask=Image.new('L',clean.size,255)
    scale=clean.width/240
    ImageDraw.Draw(mask).polygon([(round(x*scale),round(y*scale)) for x,y in openings[orientation]],fill=0)
    clean.putalpha(mask)
    save(clean,f'{orientation}-frame','cutout')
# Trim the shared frame canvas, keeping anchors and display scale unchanged.
from PIL import ImageChops
for path in {l['path'] for l in layers if l['mode'] > 0}:
    selected=[l for l in layers if l['path']==path]
    n,count,w,h=selected[0]['sheet']
    atlas=Image.open(ROOT/path).convert('RGBA')
    alpha=Image.new('L',(w,h))
    for i in range(count):
        alpha=ImageChops.lighter(alpha,atlas.crop((i*w,0,(i+1)*w,h)).getchannel('A'))
    left,top,right,bottom=alpha.getbbox()
    left=max(0,left-2);top=max(0,top-2);right=min(w,right+2);bottom=min(h,bottom+2)
    nw,nh=right-left,bottom-top
    trimmed=Image.new('RGBA',(n*nw,nh))
    for i in range(count):trimmed.paste(atlas.crop((i*w+left,top,i*w+right,bottom)),(i*nw,0))
    master=MASTERS/(Path(path).stem+'-trimmed.png')
    trimmed.save(master)
    export_image(master,ROOT/path,'cutout')
    for l in selected:
        x,y,dw,dh=l['rect']
        l['rect']=[x+left*dw/w,y+top*dh/h,nw*dw/w,nh*dh/h]
        l['sheet']=[n,count,nw,nh]

# Painter order: small flyers, then toucan; frame rendered after all atlases.
layers.sort(key=lambda l: 2 if l['mode']==2 else 1 if l['mode']==1 else 0)
(ROOT/'tools/title_animations.json').write_text(json.dumps({'layers':layers},indent=2)+'\n')

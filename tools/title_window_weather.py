"""Export weather from private masters (Pillow, NumPy, SciPy, OpenCV).

--prepare writes candidates privately; without it, exports runtime assets.
Run title_animations.py and title_scenes.py after updating scene preloads.
"""
import json
import sys
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from title_window_animation import ROOT, MASTERS, OUT, LEAVES, motion
from image_exports import export_image
P=MASTERS/'sky-clouds-twig'
PREPARE='--prepare' in sys.argv
if PREPARE:
    _export=export_image
    def export_image(src,dest,role,**kwargs):
        target=P/'prepared'/dest.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True)
        return _export(src,target,role,**kwargs)

# Traced envelopes around the existing branch, including its leaves. GrabCut
# resolves internal gaps from source colors; no generated sprite registration.
POLYS={
'landscape':[(80,510),(120,535),(220,510),(310,477),(337,452),(385,460),(414,445),(455,459),(479,441),(446,429),(445,409),(469,398),(496,388),(510,359),(547,366),(546,343),(565,333),(590,338),(607,351),(600,375),(631,368),(654,376),(675,379),(689,399),(660,399),(655,413),(683,425),(694,461),(668,453),(653,468),(626,450),(617,491),(595,510),(573,490),(574,518),(555,557),(535,537),(527,510),(505,520),(484,520),(459,539),(477,556),(480,590),(493,632),(479,652),(460,640),(437,645),(411,632),(393,647),(367,635),(354,618),(338,639),(321,616),(314,582),(322,555),(281,556),(218,578),(153,602),(82,650)],
'portrait':[(1000,710),(944,746),(919,766),(873,770),(826,783),(772,792),(738,789),(726,811),(706,822),(708,854),(691,887),(667,898),(650,887),(640,906),(616,894),(615,867),(597,883),(579,864),(582,830),(569,844),(547,831),(548,809),(530,805),(513,813),(500,787),(511,762),(487,769),(487,751),(501,730),(530,718),(558,709),(574,697),(556,691),(564,680),(597,674),(625,667),(653,674),(666,699),(685,698),(695,712),(724,717),(745,734),(765,759),(809,754),(847,740),(885,740),(925,749),(1010,810)]}

def emit(im,name,role='exact'):
    src=P/('runtime-'+name+'-master.png'); im.save(src)
    dest=OUT/(name+'.avif');export_image(src,dest,role)
    return dest.relative_to(ROOT).as_posix()

def main():
    data=json.loads((ROOT/'tools/title_animations.json').read_text())
    layers=[l for l in data['layers'] if not any(k in l['path'] for k in ('cloud','occluder','twig'))]
    # Branch sway replaces the old overlapping local leaf patch.
    layers=[l for l in layers if not l['path'].endswith(('landscape-leaves-0.avif','portrait-leaves-0.avif'))]
    weather=[]
    for orientation,poly in POLYS.items():
        scene='window' if orientation=='landscape' else 'window-portrait'
        original=Image.open(MASTERS/f'{orientation}-clean-composited.png').convert('RGB')
        sky=Image.open(P/f'{orientation}-sky-composited.png').convert('RGB')
        sky_mask=Image.open(P/f'{orientation}-sky-mask.png').convert('L')
        # Outside the sky mask the sky operation is exactly unchanged.
        outside=np.asarray(sky_mask)==0
        assert np.array_equal(np.asarray(sky)[outside],np.asarray(original)[outside])
        envelope=Image.new('L',original.size);ImageDraw.Draw(envelope).polygon(poly,fill=255)
        a=np.asarray(envelope)
        mask=np.full(a.shape,cv2.GC_BGD,np.uint8);mask[a>0]=cv2.GC_PR_FGD
        core=cv2.erode(a,np.ones((7,7),np.uint8)); mask[core>0]=cv2.GC_FGD
        cv2.grabCut(np.asarray(original),mask,None,np.zeros((1,65)),np.zeros((1,65)),4,cv2.GC_INIT_WITH_MASK)
        if orientation=='portrait':
            connector=Image.new('L',original.size)
            ImageDraw.Draw(connector).polygon([(900,765),(941,750),(977,728),(980,806),(940,801),(914,794)],fill=255)
            mask[np.asarray(connector)>0]=cv2.GC_FGD
        alpha=Image.fromarray((np.isin(mask,[1,3])*255).astype('uint8')).filter(ImageFilter.GaussianBlur(.45))
        rgba=original.convert('RGBA');rgba.putalpha(alpha)
        box=alpha.getbbox(); x,y,r,b=box
        # Inpaint only underneath the extracted pixels plus a two-pixel seam.
        clean_candidate=Image.open(P/f'{orientation}-twig-clean-generated.png').convert('RGB')
        crop=Image.open(P/f'{orientation}-twig-crop.png')
        # Crop bounds are located by exact source pixels, not feature matching.
        needle=np.asarray(crop.convert('RGB'))
        src=np.asarray(original)
        candidates=np.argwhere(np.all(src==needle[0,0],axis=2))
        origin=next((int(cx),int(cy)) for cy,cx in candidates if cy+needle.shape[0]<=src.shape[0] and cx+needle.shape[1]<=src.shape[1] and np.array_equal(src[cy:cy+needle.shape[0],cx:cx+needle.shape[1]],needle))
        patch=clean_candidate.resize(crop.size,Image.Resampling.LANCZOS)
        plate=original.copy();plate.paste(patch,origin)
        plate=Image.composite(sky,plate,sky_mask)
        removal=envelope.filter(ImageFilter.MaxFilter(31)).filter(ImageFilter.GaussianBlur(4))
        # Keep the attached trunk static beneath the branch's anchor overlap.
        rem=np.asarray(removal).copy()
        if orientation=='landscape': rem[:,:140]=0
        else: rem[:,935:]=0
        removal=Image.fromarray(rem)
        clean=Image.composite(plate,sky,removal)
        untouched=(np.asarray(sky_mask)==0)&(np.asarray(removal)==0)
        assert np.array_equal(np.asarray(clean)[untouched],np.asarray(original)[untouched])
        clean.save(P/f'{orientation}-final-background.png')
        if not PREPARE:
            for i,rect in enumerate(LEAVES[orientation]):
                if i: motion(clean,rect,f'{orientation}-leaves-{i}')
        stem='window' if orientation=='landscape' else 'window-portrait'
        export_image(P/f'{orientation}-final-background.png',ROOT/f'assets/jungle/title/{stem}.avif','title-background')
        export_image(P/f'{orientation}-final-background.png',ROOT/f'assets/jungle/title/{stem}-low.avif','title-background',size=(240,round(clean.height*240/clean.width)))
        frame=clean.convert('RGBA')
        frame.putalpha(Image.open(OUT/f'{orientation}-frame.avif').getchannel('A'))
        emit(frame,orientation+'-frame')
        # Only the sky band needs a depth mask; mountains and foliage occlude clouds.
        height=430 if orientation=='landscape' else 680
        occ=clean.crop((0,0,sky.width,height)).convert('RGBA')
        depth=255-np.asarray(sky_mask.crop((0,0,sky.width,height)))
        depth[np.asarray(frame.getchannel('A'))[:height,:]>0]=0
        # Only the vertical band traversed by clouds can occlude them.
        depth[:115 if orientation=='landscape' else 260]=0
        depth[330 if orientation=='landscape' else 500:]=0
        occ.putalpha(Image.fromarray(depth))
        def layer(path,rect,mode,timing=(1,1,0),sheet=None):
            return dict(scene=scene,path=path,rect=rect,mode=mode,timing=list(timing),sheet=sheet or [1,1,int(rect[2]),int(rect[3])])
        for i,cloud in enumerate(('cloud','cloud-wisp')):
            im=Image.open(P/f'{cloud}-master.png').convert('RGBA')
            im=im.crop(im.getchannel('A').getbbox());im.thumbnail((440 if i==0 else 330,150))
            im=im.crop(im.getchannel('A').point(lambda a:255 if a>8 else 0).getbbox())
            arr=np.asarray(im).copy();arr[arr[:,:,3]==0,:3]=0;im=Image.fromarray(arr)
            path=emit(im,cloud)
            weather.append(layer(path,[0,115+i*105 if orientation=='landscape' else 260+i*125,im.width,im.height],-1,(1,130+i*65,i*53)))
        weather.append(layer(emit(occ,orientation+'-sky-occluder'),[0,0,occ.width,occ.height],-2))
        twig=rgba.crop(box)
        # A snug 24-frame atlas, bending around the attached end by < 2 pixels.
        pad=3;w=twig.width+pad*2;h=twig.height+pad*2
        sheet=Image.new('RGBA',(24*w,h))
        for f in range(24):
            angle=.32*np.sin(f*2*np.pi/24)
            tile=Image.new('RGBA',(w,h));tile.paste(twig,(pad,pad))
            tile=tile.rotate(angle,Image.Resampling.BICUBIC,center=(0 if orientation=='landscape' else w,h/2))
            sheet.paste(tile,(f*w,0))
        nw,nh=round(w*.5),round(h*.5)
        compact=Image.new('RGBA',(24*nw,nh))
        for f in range(24): compact.paste(sheet.crop((f*w,0,(f+1)*w,h)).resize((nw,nh),Image.Resampling.LANCZOS),(f*nw,0))
        weather.append(layer(emit(compact,orientation+'-twig'),[x-pad,y-pad,w,h],-3,(6,4,0),[24,24,nw,nh]))
    data['layers']=weather+layers
    (P/'prepared-animations.json' if PREPARE else ROOT/'tools/title_animations.json').write_text(json.dumps(data,indent=2)+'\n')
if __name__=='__main__':main()

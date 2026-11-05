"""Export the Beach's clean plates and independently placed crab family.

Explicit art authoring only; ordinary builds use the committed AVIFs and JSON.
Masters stay in local/art-development/beach-port-split/.
"""
import json
from pathlib import Path
from PIL import Image
from image_exports import export_image, trim_cutout, check_cutout
from title_desert import outline
from title_places import Ledger

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT/'local/art-development/beach-port-split'
OBJECT = 'assets/jungle/title/objects/beach-crab-family.avif'
GLOW = 'assets/jungle/title/objects/beach-crab-family-glow.avif'


def main():
    original = Image.open(LOCAL/'crab-family-generated.png').convert('RGBA')
    picture, _ = trim_cutout(original, 650)
    master = LOCAL/'crab-family-overlay.png'
    picture.save(master)
    export_image(master, ROOT/OBJECT, 'cutout')
    light = Image.new('RGBA', picture.size, (255,249,222,0))
    light.putalpha(picture.getchannel('A'))
    glow_master = LOCAL/'crab-family-overlay-glow.png'
    light.save(glow_master)
    export_image(glow_master, ROOT/GLOW, 'cutout')
    for path in (OBJECT,GLOW):
        check_cutout(ROOT/path,650)
    manifest = ROOT/'tools/title_hotspots.json'
    data = json.loads(manifest.read_text())
    beach = next(s for s in data['scenes'] if s['name']=='beach')
    ledger = Ledger()
    for portrait in (False,True):
        orientation = 'portrait' if portrait else 'landscape'
        view = beach['portrait'] if portrait else beach
        source = ROOT/f'local/art-development/beach-port-redo/beach-{orientation}.png'
        ledger.plate(source,view['image'],view['low'])
        view.pop('background',None)
        view.pop('objects',None)
        x,y,width = (175,1110,650) if portrait else (490,620,600)
        height = round(width*picture.height/picture.width)
        rect = [x,y,width,height]
        hotspot = next(h for h in view['hotspots'] if h['id']=='crab-family')
        hotspot.pop('object',None)
        hotspot.update(rest=OBJECT,glow=GLOW,glow_rect=rect,
                       polygon=outline(picture.getchannel('A'),x,y,width/picture.width))
    manifest.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    ledger.save()


if __name__=='__main__':
    main()

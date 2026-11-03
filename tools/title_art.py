"""Explicit integration of the owner's approved Campus, Farm and Beach art.

This authoring command needs ignored originals; normal builds never run it.
"""
import hashlib
import json
from pathlib import Path
from PIL import Image
from image_exports import export_image

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT/'local/art-development'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    manifest = ROOT/'tools/title_hotspots.json'
    data = json.loads(manifest.read_text())
    campus = next(s for s in data['scenes'] if s['name'] == 'campus')
    mapping = json.loads((LOCAL/'campus-object-layers/mapping-portrait-v3.json').read_text())
    approved_path = ROOT/'tests/approved_title_webp.json'
    approved = json.loads(approved_path.read_text())

    def background(source, destination, size=None):
        source, destination = Path(source), ROOT/destination
        export_image(source, destination, 'title-background', size=size)
        with Image.open(destination) as im:
            row = dict(name=destination.stem, path=str(destination.relative_to(ROOT)),
                       bytes=destination.stat().st_size, sha256=digest(destination),
                       width=im.width, height=im.height,
                       decoded_rgba_sha256=hashlib.sha256(im.convert('RGBA').tobytes()).hexdigest(),
                       canonical_source=str(source.relative_to(ROOT)), canonical_bytes=source.stat().st_size,
                       canonical_sha256=digest(source))
        approved['images'] = [r for r in approved['images'] if r['path'] != row['path']] + [row]
        return str(destination.relative_to(ROOT))

    scratch = LOCAL/'title-runtime-exports'
    scratch.mkdir(exist_ok=True)

    def sprite(source, stem, bounds=None):
        with Image.open(source) as original:
            picture = original.convert('RGBA')
            if bounds: picture = picture.crop(bounds)
            raw = scratch/(stem+'.png')
            picture.save(raw)
            glow = Image.new('RGBA', picture.size, (255,249,222,0))
            glow.putalpha(picture.getchannel('A'))
            light = scratch/(stem+'-glow.png')
            glow.save(light)
        rest = 'assets/jungle/title/objects/'+stem+'.webp'
        highlighted = 'assets/jungle/title/objects/'+stem+'-glow.webp'
        export_image(raw, ROOT/rest, 'cutout')
        export_image(light, ROOT/highlighted, 'cutout')
        return rest, highlighted


    # Sideways planks only. Landscape Beach stands left of its uphill path and
    # points at it; portrait directions come from the portrait mapping.
    LANDSCAPE_SIGN_DIRECTIONS = {'Farm':'left','Beach':'right','Desert':'right'}

    def sign_hotspot(ident, label, target, rect):
        x,y,w,h = rect
        board = [round(150*w/1254), round(330*h/1254), round(950*w/1254), round(260*h/1254)]
        # Only the painted board is a semantic/pointer target, not empty alpha.
        bx,by,bw,bh = board
        # title_signs.apply_signs supplies the plank sprite, glow and outline.
        return dict(id=ident, target=target, glow_rect=rect, rest='', glow='',
                    polygon=[[x+bx-1,y+by-1],[x+bx+bw+1,y+by-1],
                             [x+bx+bw+1,y+by+bh+1],[x+bx-1,y+by+bh+1]],
                    sign=dict(label=label,label_rect=board,direction=LANDSCAPE_SIGN_DIRECTIONS[label]))

    for orientation, scene in [('landscape',campus),('portrait',campus['portrait'])]:
        plan = (json.loads((ROOT/'tools/art_provenance/campus-portrait-v3.json').read_text())
                if orientation=='portrait' else mapping['orientations'][orientation])
        source = LOCAL/'campus-object-layers'/('landscape-connected-no-stones-proposal.png' if orientation=='landscape' else plan['plate'])
        path = background(source, scene['background'])
        background(source, f'assets/jungle/title/campus{"-portrait" if orientation=="portrait" else ""}.webp')
        scene['image'] = f'assets/jungle/title/campus{"-portrait" if orientation=="portrait" else ""}.webp'
        with Image.open(source) as im:
            background(source, scene['low'], size=(240,round(im.height*240/im.width)))
        scene['hotspots'] = [h for h in scene['hotspots'] if h['id'] not in ('garden','beach-path','farm-path','desert-path')]
        by_id = {h['id']:h for h in scene['hotspots']}
        names = {'music':'music-hut','piano':'piano','picnic':'picnic','frogs':'frogs','hiding-tail':'hiding-bush'}
        scene['decorations'] = []
        for obj in plan['objects']:
            source = LOCAL/'campus-object-layers'/obj['file']
            rest, glow = sprite(source, orientation+'-'+source.stem,obj['source_content_bounds'])
            ident = next((v for k,v in names.items() if k in source.stem),None)
            x,y,w,h = obj['scene_rect']
            if ident:
                by_id[ident].update(rest=rest,glow=glow,glow_rect=[x,y,w,h],
                                   polygon=[[x,y],[x+w-1,y],[x+w-1,y+h-1],[x,y+h-1]],occlusion=[])
            else: scene['decorations'].append(dict(path=rest,rect=[x,y,w,h]))
        signs = dict(plan['signs'])
        if orientation=='landscape': signs['Farm'] = [130,490,240,240]
        if orientation=='landscape': signs['Desert'] = [1360,410,210,210]
        for label,target in [('Beach','scene:beach'),('Farm','game:Farm'),('Desert','scene:desert')]:
            hotspot = sign_hotspot(label.lower()+'-path',label,target,signs[label])
            if orientation=='portrait': hotspot['sign']['direction'] = plan['directions'][label]
            scene['hotspots'].append(hotspot)

    beach = next(s for s in data['scenes'] if s['name']=='beach')
    for orientation,scene in [('landscape',beach),('portrait',beach['portrait'])]:
        background(LOCAL/f'world-scene-refresh/beach-{orientation}-clean.png',scene['image'])
        with Image.open(ROOT/scene['image']) as im:
            background(LOCAL/f'world-scene-refresh/beach-{orientation}-clean.png', scene['low'],size=(240,round(im.height*240/im.width)))
        crab=next(h for h in scene['hotspots'] if h['id']=='crab-family')
        x,y,w,h=crab['glow_rect']
        nx,ny,nw,nh=[400,570,200,60] if orientation=='landscape' else [155,770,220,66]
        crab['polygon']=[[round(nx+(px-x)*nw/w),round(ny+(py-y)*nh/h)] for px,py in crab['polygon']]
        crab['glow_rect']=[nx,ny,nw,nh]
        old = next(i for i,h in enumerate(scene['hotspots']) if h['id']=='campus-path')
        scene['hotspots'][old] = sign_hotspot('campus-path','Campus','scene:campus',
                                             [555,710,220,220] if orientation=='landscape' else [210,980,220,220])

    farm = next(scene for scene in data['scenes'] if scene['name']=='farm')
    for orientation,scene,source_name in [('landscape',farm,'27.png'),('portrait',farm['portrait'],'19.png')]:
        source=LOCAL/'owner-farm-beach-source'/source_name
        background(source,scene['image'])
        with Image.open(source) as image:
            background(source,scene['low'],size=(240,round(image.height*240/image.width)))

    # Every image referenced by the title scene graph is app-ready WebP,
    # including utility glows. Existing lossy WebPs are reused unchanged.
    for base in data['scenes']:
        for view in (base, base.get('portrait', {})):
            for node, keys in [(view, ('image','low','background','foreground'))] + [(h,('glow','rest')) for h in view.get('hotspots',[])]:
                for key in keys:
                    name = node.get(key, '')
                    if name.endswith('.png'):
                        dest = str(Path(name).with_suffix('.webp'))
                        export_image(ROOT/name,ROOT/dest,'cutout')
                        node[key] = dest

    # Remove retired PNG runtime copies after preserving each original privately.
    import shutil
    ledger_path = ROOT/'tools/title_webp_layers.json'
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    referenced = {node.get(key) for base in data['scenes'] for view in (base,base.get('portrait',{}))
                  for node,keys in [(view,('image','low','background','foreground'))]+[(h,('glow','rest')) for h in view.get('hotspots',[])] for key in keys}
    for old in (ROOT/'assets/jungle/title').rglob('*.png'):
        target = old.with_suffix('.webp')
        name = str(old.relative_to(ROOT))
        row = dict(original_sha256=digest(old))
        if str(target.relative_to(ROOT)) in referenced or name.endswith('/guide/tiger.png'):
            export_image(old,target,'cutout')
            with Image.open(target) as im:
                row.update(path=str(target.relative_to(ROOT)),sha256=digest(target),
                           rgba_sha256=hashlib.sha256(im.convert('RGBA').tobytes()).hexdigest())
        else: row['retired'] = True
        archive = LOCAL/'title-png-originals'/old.relative_to(ROOT/'assets/jungle/title')
        archive.parent.mkdir(parents=True,exist_ok=True)
        if archive.exists(): assert digest(archive)==digest(old)
        else: shutil.copy2(old,archive)
        ledger[name]=row
        old.unlink()
    for original in (LOCAL/'retired-navigation').glob('*.png'):
        ledger['assets/jungle/title/navigation/'+original.name] = dict(original_sha256=digest(original),retired=True)
    ledger_path.write_text(json.dumps(ledger,indent=2)+'\n')

    provenance_path = ROOT/'assets/garden/scene-provenance.json'
    provenance = json.loads(provenance_path.read_text())
    for row in provenance['assets']:
        source = LOCAL/'owner-farm-beach-source'/('27.png' if 'landscape' in row['runtime'] else '19.png') if Path(row['runtime']).stem.startswith('scene-') else ROOT/row['source']
        row['source'] = str(source.relative_to(ROOT))
        target = Path(row['runtime']).with_suffix('.webp')
        if target.stem.startswith('scene-'): background(source,str(target))
        else: export_image(source,ROOT/target,'cutout')
        row['runtime'] = str(target)
        row['source_sha256'] = digest(source)
        row['sha256'] = digest(ROOT/target)
        (ROOT/target.with_suffix('.png')).unlink(missing_ok=True)
    provenance['destination'] = 'Farm / Bauernhof / Granja; painting only, existing jungle.garden saves untouched'
    provenance_path.write_text(json.dumps(provenance,indent=2)+'\n')
    approved['total_bytes'] = sum(r['bytes'] for r in approved['images'])
    approved_path.write_text(json.dumps(approved,indent=2)+'\n')
    from title_signs import apply_signs
    apply_signs(data)
    manifest.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print('Integrated approved Campus, Beach and v3 Farm WebPs; no private sources required by builds')


if __name__ == '__main__': main()

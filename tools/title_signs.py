"""Export the owner's wooden arrow boards and map their actual silhouettes."""
import hashlib
import json
from pathlib import Path
from PIL import Image
from image_exports import export_image

ROOT = Path(__file__).resolve().parents[1]
# Coordinates on the generated square canvases; posts deliberately do not hit.
# Every sign is a sideways plank: travel is always left or right along a path.
# The left board is the right one mirrored, so both share one clean outline.
BOARDS = {
    'right': ([100,330,650,280], [[55,282],[808,282],[808,175],[1205,480],[808,766],[808,668],[55,668]]),
    'left': ([504,330,650,280], [[1199,282],[446,282],[446,175],[49,480],[446,766],[446,668],[1199,668]]),
}


def apply_signs(data, export=False):
    receipts = []
    if export:
        for direction in BOARDS:
            source = ROOT/f'local/art-development/sign-reference/wood-arrow-{direction}.png'
            rest = ROOT/f'assets/jungle/title/objects/wood-arrow-{direction}.webp'
            glow = rest.with_stem(rest.stem+'-glow')
            export_image(source,rest,'cutout')
            with Image.open(source) as original:
                if original.size != (1254,1254):
                    raise ValueError('Arrow board mapping requires its original 1254 px canvas')
                alpha = original.convert('RGBA').getchannel('A')
                light = Image.new('RGBA',original.size,(255,249,222,0))
                light.putalpha(alpha)
                raw = source.with_stem(source.stem+'-glow')
                light.save(raw)
            export_image(raw,glow,'cutout')
            receipts.append(dict(direction=direction,source=str(source.relative_to(ROOT)),
                                 source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                                 runtime=str(rest.relative_to(ROOT)),sha256=hashlib.sha256(rest.read_bytes()).hexdigest(),
                                 label_rect=BOARDS[direction][0],polygon=BOARDS[direction][1]))
        (ROOT/'tools/art_provenance/title-arrow-signs.json').write_text(json.dumps(dict(
            owner_request='The sign itself is an arrow-shaped wooden plank; no arrow painted inside. '
                          'Sideways planks only, with clean intact ends (no snapped or splintered wood).',
            generator='built-in image_gen edit of the right plank; left is its exact mirror',assets=receipts),indent=2)+'\n')
    for base in data['scenes']:
        for scene in (base,base.get('portrait',{})):
            for hotspot in scene.get('hotspots',[]):
                sign = hotspot.get('sign')
                if not sign: continue
                direction = sign['direction']
                board,polygon = BOARDS[direction]
                x,y,w,h = hotspot['glow_rect']
                hotspot['rest'] = f'assets/jungle/title/objects/wood-arrow-{direction}.webp'
                hotspot['glow'] = f'assets/jungle/title/objects/wood-arrow-{direction}-glow.webp'
                sign['label_rect'] = [round(board[0]*w/1254),round(board[1]*h/1254),
                                      round(board[2]*w/1254),round(board[3]*h/1254)]
                hotspot['polygon'] = [[x+round(px*w/1254),y+round(py*h/1254)] for px,py in polygon]


if __name__ == '__main__':
    path = ROOT/'tools/title_hotspots.json'
    data = json.loads(path.read_text())
    apply_signs(data,export=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

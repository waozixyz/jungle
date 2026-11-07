"""Export the Beach crabs: every crab of the family is its own cut-out with its
own walk on the dry sand, and smaller crabs scuttle about further back.

The owner (2026-11-06): "the crabs shouldn't move all together, each crab
should be individual and more in the background beach walking around". The
family painting is split along its own silhouette: each crab grows from a seed
on its shell through the painted pixels, and thin joins (a claw tip touching an
eye) cost more to cross, so every leg stays with its own crab. The background
crabs are paler, mirrored babies. Tapping any crab opens Crab Family Counting.

Each placement is a rect (x, y, width) in scene pixels and a walk: stops
[dx, dy, pause seconds] from that rect, a speed in pixels per second and a
phase, so no two crabs step together (host/jungle_title.zi
TitleHotspotMotion). Walks stay on dry sand, clear of the signs.

Explicit art authoring only; ordinary builds use the committed AVIFs and JSON.
Masters stay in local/art-development/beach-port-split/.

    python3 tools/title_beach_crabs.py && python3 tools/title_scenes.py
"""
import heapq
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageOps
from scipy import ndimage
from image_exports import export_scaled_master, record_canonical_rows, trim_cutout
from title_desert import outline

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT/'local/art-development/beach-port-split'
FAMILY = LOCAL/'crab-family-generated.png'
OBJECTS = 'assets/jungle/title/objects/'
GAME = 'game:Crab Family Counting'
RETIRED = [OBJECTS+'beach-crab-family.avif', OBJECTS+'beach-crab-family-glow.avif']
# A seed on each crab's shell in the family painting, and how much dearer its
# growth is: the babies grow slower, so where a parent's claw tip touches a
# baby's eye the claw stays with the parent.
SEEDS = {'crab-big': ((520, 300), 1.0), 'crab-rosy': ((1240, 370), 1.0), 'crab-baby-wave': ((500, 690), 2.2),
         'crab-baby-step': ((870, 700), 2.2), 'crab-baby-peek': ((1250, 700), 2.2)}
# Background crabs: a baby mirrored and paled towards the sand.
BACKGROUND = {'crab-sand-1': 'crab-baby-step', 'crab-sand-2': 'crab-baby-wave', 'crab-sand-3': 'crab-baby-peek'}
PALE = 0.3
# Drawn in this order, back to front: the background crabs first.
PLACES = {
    'landscape': {
        'crab-sand-1': ([470, 548, 66], dict(stops=[[0, 0, 1.5], [150, 6, 3.0], [70, 18, 1.0]], speed=26, phase=0.0)),
        'crab-sand-2': ([1040, 532, 60], dict(stops=[[0, 0, 2.5], [-160, 12, 1.0], [-60, 4, 2.0]], speed=22, phase=4.0)),
        'crab-sand-3': ([740, 584, 70], dict(stops=[[0, 0, 0.8], [110, -8, 2.2], [210, 10, 1.4], [90, 16, 0.6]],
                                             speed=30, phase=2.5)),
        'crab-big': ([400, 642, 210], dict(stops=[[0, 0, 3.0], [110, 12, 2.0], [40, 34, 1.5]], speed=20, phase=1.0)),
        'crab-rosy': ([900, 640, 186], dict(stops=[[0, 0, 2.0], [-70, 22, 3.0], [70, 30, 1.5]], speed=18, phase=5.5)),
        'crab-baby-wave': ([640, 744, 96], dict(stops=[[0, 0, 1.0], [-60, 16, 0.8], [40, 22, 2.0]], speed=34, phase=0.6)),
        'crab-baby-step': ([800, 748, 92], dict(stops=[[0, 0, 1.8], [90, 8, 1.0], [150, 20, 0.7], [50, 16, 1.2]],
                                                speed=38, phase=3.1)),
        'crab-baby-peek': ([1080, 748, 94], dict(stops=[[0, 0, 0.6], [80, 22, 2.4], [-40, 14, 1.0]], speed=30, phase=1.9)),
    },
    'portrait': {
        'crab-sand-1': ([200, 590, 56], dict(stops=[[0, 0, 1.5], [150, 10, 3.0], [60, 22, 1.0]], speed=24, phase=0.0)),
        'crab-sand-2': ([330, 960, 58], dict(stops=[[0, 0, 2.5], [130, 20, 1.0], [40, 30, 2.0]], speed=22, phase=4.0)),
        'crab-sand-3': ([400, 640, 52], dict(stops=[[0, 0, 0.8], [-120, 12, 2.2], [20, 26, 1.4]], speed=26, phase=2.5)),
        'crab-big': ([196, 1190, 196], dict(stops=[[0, 0, 3.0], [60, 18, 2.0], [10, 40, 1.5]], speed=18, phase=1.0)),
        'crab-rosy': ([470, 1200, 176], dict(stops=[[0, 0, 2.0], [-60, 26, 3.0], [50, 36, 1.5]], speed=16, phase=5.5)),
        'crab-baby-wave': ([220, 1330, 88], dict(stops=[[0, 0, 1.0], [70, 12, 0.8], [20, 30, 2.0]], speed=30, phase=0.6)),
        'crab-baby-step': ([380, 1346, 86], dict(stops=[[0, 0, 1.8], [60, 10, 1.0], [-40, 22, 0.7]], speed=32, phase=3.1)),
        'crab-baby-peek': ([560, 1336, 88], dict(stops=[[0, 0, 0.6], [-60, 24, 2.4], [40, 14, 1.0]], speed=28, phase=1.9)),
    },
}


def split(family):
    """Each crab's own pixels: the cheapest path through painted pixels from
    its seed, where thin parts (legs, eye stalks) cost more to cross."""
    alpha = np.asarray(family.getchannel('A'))
    step = 2
    mask = alpha[::step, ::step] >= 20
    weight = 1.0 + 40.0 / (1.0 + ndimage.distance_transform_edt(mask))
    height, width = mask.shape
    best = np.full(mask.shape, np.inf)
    owner = np.zeros(mask.shape, np.int8)
    queue = []
    for label, ((x, y), _) in enumerate(SEEDS.values(), 1):
        best[y // step, x // step] = 0.0
        owner[y // step, x // step] = label
        queue.append((0.0, y // step, x // step, label))
    heapq.heapify(queue)
    cost = [0.0] + [dear for _, dear in SEEDS.values()]
    while queue:
        distance, y, x, label = heapq.heappop(queue)
        if distance > best[y, x]:
            continue
        for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= ny < height and 0 <= nx < width and mask[ny, nx]:
                through = distance + weight[ny, nx] * cost[label]
                if through < best[ny, nx]:
                    best[ny, nx], owner[ny, nx] = through, label
                    heapq.heappush(queue, (through, ny, nx, label))
    # Soft edge pixels outside the mask take their nearest painted neighbor.
    near = ndimage.distance_transform_edt(owner == 0, return_distances=False, return_indices=True)
    owner = owner[near[0], near[1]]
    owner = np.kron(owner, np.ones((step, step), np.int8))[:alpha.shape[0], :alpha.shape[1]]
    crabs = {}
    for label, name in enumerate(SEEDS, 1):
        picture = family.copy()
        picture.putalpha(Image.fromarray(np.where(owner == label, alpha, 0).astype(np.uint8)))
        crabs[name] = picture
    return crabs


def background(baby):
    """A distant crab: the baby mirrored and paled towards the sand."""
    alpha = baby.getchannel('A')
    pale = ImageEnhance.Color(baby.convert('RGB')).enhance(1.0 - PALE)
    pale = Image.blend(pale, Image.new('RGB', baby.size, (246, 236, 222)), PALE * 0.5)
    pale.putalpha(alpha)
    return ImageOps.mirror(pale)


def main():
    family = Image.open(FAMILY).convert('RGBA')
    crabs = split(family)
    crabs.update({name: background(crabs[baby]) for name, baby in BACKGROUND.items()})
    scratch = LOCAL/'crabs'
    scratch.mkdir(parents=True, exist_ok=True)
    rows, layers = {}, {}
    widest = {name: max(PLACES[o][name][0][2] for o in PLACES) for name in crabs}
    for name, picture in crabs.items():
        picture, _ = trim_cutout(picture, widest[name])
        master = scratch/f'beach-{name}.png'
        picture.save(master)
        light = Image.new('RGBA', picture.size, (255, 249, 222, 0))
        light.putalpha(picture.getchannel('A'))
        glow = scratch/f'beach-{name}-glow.png'
        light.save(glow)
        rest, highlight = OBJECTS+f'beach-{name}.avif', OBJECTS+f'beach-{name}-glow.avif'
        rows[rest] = export_scaled_master(master, ROOT/rest)
        rows[highlight] = export_scaled_master(glow, ROOT/highlight)
        layers[name] = (picture, rest, highlight)
    manifest = ROOT/'tools/title_hotspots.json'
    data = json.loads(manifest.read_text())
    beach = next(s for s in data['scenes'] if s['name'] == 'beach')
    for orientation, view in (('landscape', beach), ('portrait', beach['portrait'])):
        crab = lambda hotspot: hotspot['id'] == 'crab-family' or hotspot['id'].startswith('crab-')
        at = next(i for i, h in enumerate(view['hotspots']) if crab(h))
        kept = [h for h in view['hotspots'] if not crab(h)]
        crab_spots = []
        for name, ((x, y, width), walk) in PLACES[orientation].items():
            picture, rest, highlight = layers[name]
            height = round(width * picture.height / picture.width)
            crab_spots.append(dict(id=name, target=GAME, glow_rect=[x, y, width, height], rest=rest, glow=highlight,
                                   polygon=outline(picture.getchannel('A'), x, y, width / picture.width), walk=walk))
        # The crabs keep the family's place among the Beach hotspots.
        view['hotspots'] = kept[:at] + crab_spots + kept[at:]
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    canonical = json.loads((ROOT/'tools/canonical_avif.json').read_text())
    for name in RETIRED:
        (ROOT/name).unlink(missing_ok=True)
        canonical['files'].pop(name, None)
    (ROOT/'tools/canonical_avif.json').write_text(json.dumps(canonical, indent=2, ensure_ascii=False) + '\n')
    record_canonical_rows(rows)
    print('Exported the Beach crabs; run python3 tools/title_scenes.py next')


if __name__ == '__main__':
    main()

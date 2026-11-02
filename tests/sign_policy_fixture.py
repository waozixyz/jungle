"""Private three-sign fixture. Never changes production routes or artwork."""
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import title_scenes


def fixture():
    data = json.loads(title_scenes.SOURCE.read_text())
    campus = next(s for s in data['scenes'] if s['name'] == 'campus')
    sprite = next(h for h in campus['hotspots'] if h['id'] == 'beach-path')
    for scene, xs, y in ((campus, (150, 720, 1250), 400),
                         (campus['portrait'], (180, 420, 660), 600)):
        # The fixture draws signs above the existing approved full plate.
        # It does not propose or export replacement campus artwork.
        for key in ('background', 'foreground', 'paper'):
            scene.pop(key, None)
        for label, x in zip(('Beach', 'Farm', 'Desert'), xs):
            sign = copy.deepcopy(sprite)
            sign.update(id=label.lower()+'-policy-sign',
                        target='scene:beach' if label == 'Beach' else 'preview:'+label,
                        glow_rect=[x, y, 180, 160],
                        polygon=[[x+1,y+1],[x+179,y+1],[x+179,y+159],[x+1,y+159]],
                        occlusion=[], sign=dict(label=label, label_rect=[10,20,160,60], direction='left'))
            scene['hotspots'].append(sign)
    return data


def write(directory):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory/'fixture.json'
    path.write_text(json.dumps(fixture(), ensure_ascii=False))
    return title_scenes.Render(*title_scenes.Load(path))

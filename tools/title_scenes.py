#!/usr/bin/env python3
"""Generate host/jungle_title_data.zi from tools/title_hotspots.json.

The treehouse title screen (host/jungle_menu.zi) draws these scenes. Each
hotspot leads to another scene ("scene:NAME") or opens a catalog game
("game:TITLE"; the host finds the game by title at runtime). Escape returns
to the scene each scene is first reached from, starting at the first scene.

    python3 tools/title_scenes.py           write the data file
    python3 tools/title_scenes.py --check   fail when it is out of date
"""
from pathlib import Path
import argparse
import json
import math
import sys

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'tools/title_hotspots.json'
CATALOG = ROOT / 'games/catalog.txt'
OUTPUT = ROOT / 'host/jungle_title_data.zi'
DIALOGUE = ROOT / 'tools/title_dialogue.json'
LANGUAGES = ('en', 'de', 'es')
# Below Ziran's 4095-character file-scope initializer limit.
INITIALIZER_LIMIT = 3600
SIGN_LABELS = {'Port', 'Farm', 'Desert', 'Campus', 'Market', 'Aquarium', 'Beach'}
# Beach and Port are independent destinations.
SCENE_ALIASES = {}


def Inside(polygon, x, y):
    inside = False
    for (xi, yi), (xj, yj) in zip(polygon, polygon[-1:] + polygon[:-1]):
        if (yi > y) != (yj > y) and x < xi + (y - yi) * (xj - xi) / (yj - yi):
            inside = not inside
    return inside


def Rotation(layer):
    angle = layer.get('rotation', 0)
    if type(angle) not in (int, float) or not math.isfinite(angle) or not -180 <= angle < 180:
        raise SystemExit('title scenes: rotation must be finite clockwise degrees in [-180, 180)')
    return round(angle * 100)


def RotatePolygon(points, rect, angle):
    radians = math.radians(angle / 100)
    c, s = math.cos(radians), math.sin(radians)
    cx, cy = rect[0]+rect[2]/2, rect[1]+rect[3]/2
    return [(round(cx+(x-cx)*c-(y-cy)*s), round(cy+(x-cx)*s+(y-cy)*c)) for x,y in points]


def SignLabel(hotspot):
    sign = hotspot.get('sign')
    if sign is None:
        return ''
    if not isinstance(sign, dict) or not isinstance(sign.get('label'), str) or sign['label'] not in SIGN_LABELS:
        raise SystemExit('title scenes: invalid path sign label')
    return sign['label']


def SignTextLayout(hotspot, rect, board):
    """Local layout box plus clockwise hundredths of a degree.

    The diagonal sprites have seven outline vertices. Their parallel long
    edges (0–1 and 5–6) define the plank body, excluding the arrowhead.
    """
    direction = hotspot.get('sign', {}).get('direction', '')
    if not direction.startswith('diagonal-'):
        return board, 0
    points = hotspot['polygon']
    if len(points) != 7:
        raise SystemExit('title scenes: diagonal sign needs its seven board vertices')
    a, b, c, d = (points[i] for i in (0, 1, 5, 6))
    dx, dy = b[0]-a[0], b[1]-a[1]
    if dx < 0:
        dx, dy = -dx, -dy
    length = math.hypot(dx, dy)
    if length == 0:
        raise SystemExit('title scenes: diagonal sign has no board length')
    thickness = abs((d[0]-a[0])*dy-(d[1]-a[1])*dx)/length
    width, height = length*.84, thickness*.76
    cx = sum(p[0] for p in (a,b,c,d))/4-rect[0]
    cy = sum(p[1] for p in (a,b,c,d))/4-rect[1]
    return [round(cx-width/2),round(cy-height/2),round(width),round(height)], round(math.degrees(math.atan2(dy,dx))*100)


def Sign(hotspot, rect):
    """A label on a separate physical sprite, with board-local text bounds."""
    sign = hotspot.get('sign')
    if sign is None:
        return '', [0, 0, 0, 0]
    label = SignLabel(hotspot)
    # Owner: signs are planks pointing along the path, sideways by default.
    # Diagonal labels follow the board; flat coastal boards stay horizontal.
    if sign.get('direction') not in ('left','right','diagonal-left','diagonal-right'):
        raise SystemExit('title scenes: every sign needs a travel direction')
    board = sign.get('label_rect', [])
    if (not isinstance(board, list) or len(board) != 4 or
            any(type(v) is not int for v in board) or
            min(board[:2]) < 0 or min(board[2:]) <= 0 or
            board[0] + board[2] > rect[2] or board[1] + board[3] > rect[3]):
        raise SystemExit('title scenes: path sign label_rect must fit its separate sprite')
    if not hotspot.get('rest'):
        raise SystemExit('title scenes: path sign needs a separate resting sprite')
    if not hotspot['target'].startswith(('scene:', 'game:', 'book:', 'notice:')):
        raise SystemExit('title scenes: path sign needs an actual destination')
    if any(not (rect[0] <= x <= rect[0] + rect[2] and
                    rect[1] <= y <= rect[1] + rect[3]) for x, y in hotspot['polygon']):
        raise SystemExit('title scenes: path sign hit polygon must fit its sprite')
    # The semantic button covers the board only, so its complete rectangle
    # must be part of the physical hit shape and outside foreground animals.
    for u in (0.001, 0.5, 0.999):
        for v in (0.001, 0.5, 0.999):
            x, y = rect[0] + board[0] + u * board[2], rect[1] + board[1] + v * board[3]
            if (not Inside(hotspot['polygon'], x, y) or
                    Inside(hotspot.get('occlusion', []), x, y)):
                raise SystemExit('title scenes: path sign board must stay inside its physical hit area')
    return label, board


def Dialogues(source=DIALOGUE):
    """Tap-through speech bubbles, every line in English, German and Spanish.

    A voice clip is used only once it exists; until then the line is silent.
    """
    dialogues = json.loads(Path(source).read_text())['dialogues']
    ids = [d['id'] for d in dialogues]
    if len(set(ids)) != len(ids) or not all(isinstance(i, str) and i for i in ids):
        raise SystemExit('title scenes: dialogue IDs must be unique and present')
    for dialogue in dialogues:
        if not dialogue.get('lines') or len(dialogue['lines']) > 8:
            raise SystemExit(f'title scenes: dialogue {dialogue["id"]} needs one to eight lines')
        for line in dialogue['lines']:
            if set(line) != set(LANGUAGES) or not all(isinstance(line[l], str) and line[l].strip() and
                                                      '\n' not in line[l] and len(line[l]) <= 90 for l in LANGUAGES):
                raise SystemExit(f'title scenes: dialogue {dialogue["id"]} needs short EN/DE/ES lines')
        voices = []
        for number in range(len(dialogue['lines'])):
            for language in LANGUAGES:
                path = dialogue.get('voice', '').format(language=language, line=number)
                voices.append(path if path and (ROOT / path).is_file() else '')
        dialogue['voices'] = voices
        if not isinstance(dialogue.get('speaker_hotspot', ''), str):
            raise SystemExit(f'title scenes: dialogue {dialogue["id"]} speaker_hotspot must be a hotspot ID')
    return dialogues


def Objects(scene):
    """Validate a room's separate object layers, drawn in list order over its
    clean background plate. A hotspot with "object" belongs to that layer:
    its glow picture shares the layer's rect and its hit shape stays inside."""
    objects = scene.get('objects', [])
    if not isinstance(objects, list):
        raise SystemExit('title scenes: objects must be a list')
    # Rooms may have a clean plate; separate sign posts also overlay full scenes.
    ids = [layer.get('id') for layer in objects]
    if len(set(ids)) != len(ids) or not all(isinstance(i, str) and i for i in ids):
        raise SystemExit('title scenes: object IDs must be unique and present')
    for layer in objects:
        rect = layer.get('rect')
        Rotation(layer)
        if not {'id', 'image', 'rect'} <= set(layer) or set(layer) - {'id', 'image', 'rect', 'rotation', 'visible', 'locked'}:
            raise SystemExit(f'title scenes: object {layer["id"]} needs exactly id, image and rect')
        if (not isinstance(rect, list) or len(rect) != 4 or any(type(v) is not int for v in rect) or
                rect[0] < 0 or rect[1] < 0 or rect[2] <= 0 or rect[3] <= 0 or
                rect[0] + rect[2] > scene['width'] or rect[1] + rect[3] > scene['height']):
            raise SystemExit(f'title scenes: object {layer["id"]} rect must lie inside the scene')
        if not layer['image'].endswith('.avif') or not (ROOT / layer['image']).is_file():
            raise SystemExit(f'title scenes: object {layer["id"]} needs an existing AVIF image')
    by_id = {layer['id']: layer for layer in objects}
    for hotspot in scene['hotspots']:
        if 'object' not in hotspot:
            continue
        layer = by_id.get(hotspot['object'])
        if layer is None:
            raise SystemExit(f'title scenes: hotspot {hotspot["id"]} names a missing object')
        x, y, width, height = layer['rect']
        if hotspot['glow_rect'] != layer['rect'] or any(
                not (x <= px <= x + width and y <= py <= y + height) for px, py in hotspot['polygon']):
            raise SystemExit(f'title scenes: hotspot {hotspot["id"]} must follow its object; '
                             'run python3 tools/title_scenes.py')


def Follow(data):
    """Move and scale each object's hotspot with its layer. True when changed."""
    changed = False
    for base in data['scenes']:
        for scene, width, height in ((base, data['width'], data['height']),
                                     (base.get('portrait'), None, None)):
            if not scene:
                continue
            width = width or scene['width']
            height = height or scene['height']
            layers = {layer['id']: layer for layer in scene.get('objects', [])}
            for hotspot in scene['hotspots']:
                layer = layers.get(hotspot.get('object'))
                if layer is None or hotspot['glow_rect'] == layer['rect']:
                    continue
                (x, y, w, h), (nx, ny, nw, nh) = hotspot['glow_rect'], layer['rect']
                hotspot['polygon'] = [[min(width - 1, max(0, round(nx + (px - x) * nw / w))),
                                       min(height - 1, max(0, round(ny + (py - y) * nh / h)))]
                                      for px, py in hotspot['polygon']]
                hotspot['glow_rect'] = list(layer['rect'])
                changed = True
    return changed


# The world map (tools/title_world_map.py writes it from
# tools/title_world_map.json): every area is a painted landmark. It opens from
# each scene's map button, so no hotspot leads to it, and Back returns to
# where it was opened. Its "locked:" landmarks stay faded and answer "not yet".
MAP = 'map'


def MapSafe(scene, hotspots):
    """Keep the complete shared world painting visible; other scenes use cover."""
    if scene['name'] not in (MAP, MAP + '-portrait'):
        return [0, 0, 0, 0]
    return [0, 0, scene['width'], scene['height']]


def Load(source=SOURCE, catalog=CATALOG):
    """The validated scenes, their parents and the flattened hotspots."""
    data = json.loads(Path(source).read_text())
    scenes = [dict(scene, width=scene.get('width', data['width']), height=scene.get('height', data['height']), base=index)
              for index, scene in enumerate(data['scenes'])]
    # Variants share destinations and identity, but own every pixel coordinate.
    for index, scene in enumerate(data['scenes']):
        if 'portrait' not in scene:
            continue
        portrait = scene['portrait']
        if portrait['width'] <= 0 or portrait['height'] <= 0 or (scene['name'] != MAP and portrait['height'] <= portrait['width']):
            raise SystemExit('title scenes: portrait must have positive, taller dimensions')
        original = {h['id']: h['target'] for h in scene['hotspots']}
        alternate = {h['id']: h['target'] for h in portrait['hotspots']}
        if original != alternate or len(alternate) != len(portrait['hotspots']):
            raise SystemExit('title scenes: portrait hotspot IDs and targets must match landscape')
        labels = lambda items: {h['id']: SignLabel(h) for h in items}
        if labels(scene['hotspots']) != labels(portrait['hotspots']):
            raise SystemExit('title scenes: portrait path sign labels must match landscape')
        # A look-only view keeps its Back button when rotated.
        scenes.append(dict(portrait, name=scene['name'] + '-portrait', base=index,
                           **({'back': scene['back']} if 'back' in scene else {})))
    names = [scene['name'] for scene in scenes]
    if not scenes or len(set(names)) != len(names):
        raise SystemExit('title scenes: scene names must be unique and present')
    titles = [line.split('|')[1] for line in Path(catalog).read_text().splitlines() if '|' in line]
    dialogues = Dialogues()
    dialogue_ids = [d['id'] for d in dialogues]
    hotspots = []
    for scene in scenes:
        for hotspot in scene['hotspots']:
            kind, _, target = hotspot['target'].partition(':')
            if kind == 'scene' and target in SCENE_ALIASES:
                hotspot['target'] = 'scene:' + SCENE_ALIASES[target]
    for index, scene in enumerate(scenes):
        if scene['width'] <= 0 or scene['height'] <= 0:
            raise SystemExit('title scenes: dimensions must be positive')
        if len({h['id'] for h in scene['hotspots']}) != len(scene['hotspots']):
            raise SystemExit('title scenes: duplicate hotspot ID')
        # A look-only view (the window's outside view) needs its Back button.
        if not scene['hotspots'] and scene.get('back') is not True:
            raise SystemExit(f'title scenes: {scene["name"]} has no hotspots')
        if 'back' in scene and scene['back'] is not True:
            raise SystemExit('title scenes: back is either true or absent')
        Objects(scene)
        for hotspot in scene['hotspots']:
            kind, _, target = hotspot['target'].partition(':')
            if kind == 'scene':
                if target not in names:
                    raise SystemExit(f'title scenes: {hotspot["id"]} leads to unknown scene {target}')
                scene_target, game = names.index(target), ''
            elif kind == 'book' and target == 'sweet-porridge':
                scene_target, game = -1, 'Sweet Porridge'
            elif kind == 'game':
                if target not in titles:
                    raise SystemExit(f'title scenes: {hotspot["id"]} opens {target}, which is not in the catalog')
                scene_target, game = -1, target
            elif kind == 'guide' and target == 'tour':
                scene_target, game = -1, ''
            elif kind == 'locked' and target and scene['name'] in (MAP, MAP + '-portrait') and not hotspot.get('sign'):
                scene_target, game = -1, ''
            elif kind == 'notice' and target in ('Farm', 'Desert') and SignLabel(hotspot) == target and scene['name'] in ('campus', 'campus-portrait'):
                scene_target, game = -1, ''
            elif kind == 'dialogue' and target in dialogue_ids and not hotspot.get('sign'):
                scene_target, game = -1, ''
            elif kind == 'look' and target and not hotspot.get('sign'):
                # A decorative painted item: it glows on hover and tap, nothing opens.
                scene_target, game = -1, ''
            else:
                raise SystemExit(f'title scenes: {hotspot["id"]} has target {hotspot["target"]}')
            polygon = [(round(x), round(y)) for x, y in hotspot['polygon']]
            if any(x < 0 or y < 0 or x >= scene['width'] or y >= scene['height'] for x, y in polygon):
                raise SystemExit('title scenes: polygon outside scene')
            if len(polygon) < 3:
                raise SystemExit(f'title scenes: {hotspot["id"]} needs at least three points')
            occlusion = [(round(x), round(y)) for x, y in hotspot.get('occlusion', [])]
            if occlusion and (len(occlusion) < 3 or any(
                    x < 0 or y < 0 or x >= scene['width'] or y >= scene['height']
                    for x, y in occlusion)):
                raise SystemExit('title scenes: invalid foreground occlusion')
            rect = [round(value) for value in hotspot['glow_rect']]
            if len(rect) != 4 or rect[2] <= 0 or rect[3] <= 0:
                raise SystemExit(f'title scenes: {hotspot["id"]} has an empty glow_rect')
            label, board = Sign(hotspot, rect)
            board, rotation = SignTextLayout(hotspot, rect, board)
            angle = Rotation(hotspot)
            polygon = RotatePolygon(polygon, rect, angle)
            if hotspot.get('occlusion_object'):
                occluder = next((o for o in scene.get('objects',[]) if o['id']==hotspot['occlusion_object']),None)
                if occluder is None:
                    raise SystemExit('title scenes: missing occlusion object')
                occlusion = RotatePolygon(occlusion, occluder['rect'], Rotation(occluder))
            else:
                occlusion = RotatePolygon(occlusion, rect, angle)
            hotspots.append({'scene': index, 'id': hotspot['id'], 'scene_target': scene_target,
                             'game': game, 'glow': hotspot['glow'], 'rect': rect, 'polygon': polygon,
                             'rest': hotspot.get('rest', ''), 'occlusion': occlusion,
                             'sign_label': label, 'sign_rect': board, 'sign_rotation': rotation, 'rotation': angle,
                             'sign_direction': {'left':1,'right':2,'diagonal-left':3,'diagonal-right':4,'down':4}.get(hotspot.get('sign',{}).get('direction'),0),
                             'notice': {'Farm': 1, 'Desert': 2}.get(target, 0) if kind == 'notice' else 0,
                             'look': 1 if kind == 'look' else 0,
                             'dialogue': dialogue_ids.index(target) + 1 if kind == 'dialogue' else 0})
    # Whoever taps a figure in a conversation, its speaker's figure anchors the
    # bubble and glows: tapping the camel still lets the guide beside it talk.
    for hotspot in hotspots:
        hotspot['speaker'] = -1
        if hotspot['dialogue']:
            speaker = dialogues[hotspot['dialogue'] - 1].get('speaker_hotspot') or hotspot['id']
            found = [i for i, h in enumerate(hotspots) if h['scene'] == hotspot['scene'] and h['id'] == speaker]
            if not found or not hotspots[found[0]]['dialogue']:
                raise SystemExit(f'title scenes: {hotspot["id"]} has no speaker {speaker} in its scene')
            hotspot['speaker'] = found[0]
    # Parents: breadth first from the first scene, so Escape always climbs
    # back towards the treehouse.
    parents = [-1] * len(scenes)
    seen = {0}
    queue = [0]
    while queue:
        current = queue.pop(0)
        for hotspot in hotspots:
            if hotspot['scene'] == current and hotspot['scene_target'] >= 0 and hotspot['scene_target'] not in seen:
                seen.add(hotspot['scene_target'])
                parents[hotspot['scene_target']] = current
                queue.append(hotspot['scene_target'])
            # Retained chooser art belongs to its native catalog app.
            if hotspot['scene'] == current and hotspot['game']:
                for index, scene in enumerate(scenes):
                    if scene.get('subapp') == hotspot['game'] and index not in seen:
                        seen.add(index)
                        parents[index] = current
                        queue.append(index)
    # Coastal destinations have fixed Back routes, independent of discovery order.
    for child, parent in (('port', 'market'), ('aquarium', 'beach')):
        parents[names.index(child)] = names.index(parent)
    # Without a remembered origin, Back from the world map climbs to the treehouse.
    for index, scene in enumerate(scenes):
        if scene['name'] == MAP and index not in seen:
            if scene.get('back') is not True:
                raise SystemExit('title scenes: the world map needs its Back button')
            seen.add(index)
            parents[index] = 0
    for index, scene in enumerate(scenes):
        if scene['base'] != index:
            seen.add(index)
            parents[index] = parents[scene['base']]
    unreachable = [names[index] for index in range(len(scenes)) if index not in seen]
    if unreachable:
        raise SystemExit('title scenes: unreachable scenes ' + ', '.join(unreachable))
    missing = sorted(set(titles) - {hotspot['game'] for hotspot in hotspots})
    if missing:
        raise SystemExit('title scenes: catalog games without a hotspot: ' + ', '.join(missing))
    for scene in scenes:
        for key in ('image', 'low'):
            if not (ROOT / scene[key]).is_file():
                raise SystemExit(f'title scenes: missing {scene[key]}')
        for key in ('background', 'foreground'):
            if scene.get(key) and not (ROOT / scene[key]).is_file():
                raise SystemExit(f'title scenes: missing {scene[key]}')
        if scene.get('foreground') and not scene.get('background'):
            raise SystemExit('title scenes: a foreground needs its clean background')
        if scene.get('paper') and not (scene.get('foreground') or scene.get('objects')):
            raise SystemExit('title scenes: hidden paper needs a foreground layer')
        paper = scene.get('paper')
        if paper is not None and (len(paper) != 4 or any(type(v) is not int for v in paper) or
                not 0 <= paper[0] < scene['width'] or not 0 <= paper[1] < scene['height'] or
                paper[2] <= 0 or paper[3] <= 0):
            raise SystemExit('title scenes: invalid paper center, size or reveal travel')
    for hotspot in hotspots:
        if not hotspot['glow'] and hotspot['id'] == 'desert' and scenes[hotspot['scene']]['name'] in (MAP, MAP + '-portrait'):
            continue
        if not (ROOT / hotspot['glow']).is_file():
            raise SystemExit(f'title scenes: missing {hotspot["glow"]}')
        if hotspot['rest'] and not (ROOT / hotspot['rest']).is_file():
            raise SystemExit(f'title scenes: missing {hotspot["rest"]}')
    for scene in scenes:
        for layer in scene.get('decorations', []):
            Rotation(layer)
            if not (ROOT/layer['path']).is_file() or len(layer['rect']) != 4:
                raise SystemExit('title scenes: invalid decoration')
    return data, scenes, parents, hotspots


def Quoted(values):
    values = [json.dumps(value, ensure_ascii=False) for value in values]
    if sum(len(value) + 2 for value in values) < 200:
        return ', '.join(values)
    return '\n    ' + ',\n    '.join(values) + ',\n'


def ChunkedStrings(name, accessor, values):
    """A string table in pieces below INITIALIZER_LIMIT, read through ACCESSOR(index)."""
    chunks = [[]]
    for value in values:
        if chunks[-1] and len(Quoted(chunks[-1] + [value])) > INITIALIZER_LIMIT:
            chunks.append([])
        chunks[-1].append(value)
    lines, body, end = [], [], 0
    for index, chunk in enumerate(chunks):
        if len(Quoted(chunk)) > INITIALIZER_LIMIT:
            raise SystemExit(f'title scenes: one {name} entry is too long for a Ziran array')
        lines.append(f'{name}_{index}: [{len(chunk)}]string = .[{Quoted(chunk)}];')
        body.append(f'    if index < {end + len(chunk)} {{ return {name}_{index}[index - {end}] }}')
        end += len(chunk)
    return lines + [f'{accessor} :: (index: s32) -> string {{', *body, '    return ""', '}']


def Numbers(values):
    # Ziran source lines stay below 4096 characters.
    values = [str(value) for value in values]
    if len(values) <= 24:
        return ', '.join(values)
    rows = [', '.join(values[at:at + 24]) for at in range(0, len(values), 24)]
    return '\n    ' + ',\n    '.join(rows) + ',\n'


def QuotedBool(values):
    return Numbers('true' if value else 'false' for value in values)


def Render(data, scenes, parents, hotspots):
    first, counts = [], []
    for index in range(len(scenes)):
        own = [position for position, hotspot in enumerate(hotspots) if hotspot['scene'] == index]
        # A look-only view starts its empty range where the next scene begins.
        first.append(own[0] if own else sum(counts))
        counts.append(len(own))
    # Ziran limits a file-scope initializer to 4095 characters, so the points
    # are split into chunks, each holding whole polygons.
    chunks, polygon_chunk, polygon_first, polygon_count = [], [], [], []
    # Hit shapes and optional foreground exclusions use the same bounded
    # storage. The visible sprite and its interaction stop at the tiger.
    polygons = [h['polygon'] for h in hotspots] + [h['occlusion'] for h in hotspots]
    for polygon in polygons:
        xs = [x for x, _ in polygon]
        ys = [y for _, y in polygon]
        if not chunks or max(len(Numbers(chunks[-1][0] + xs)), len(Numbers(chunks[-1][1] + ys))) > INITIALIZER_LIMIT:
            chunks.append(([], []))
        if max(len(Numbers(xs)), len(Numbers(ys))) > INITIALIZER_LIMIT:
            raise SystemExit('title scenes: too many points for one Ziran array')
        polygon_chunk.append(len(chunks) - 1)
        polygon_first.append(len(chunks[-1][0]))
        polygon_count.append(len(xs))
        chunks[-1][0].extend(xs)
        chunks[-1][1].extend(ys)
    rects = [value for hotspot in hotspots for value in hotspot['rect']]
    scene_count, hotspot_count = len(scenes), len(hotspots)
    exploration = next((s.get('exploration', []) for s in scenes if s['name'] == MAP), [])
    decorations = [(i,layer) for i,scene in enumerate(scenes) for layer in scene.get("decorations", [])]
    portrait = [next((i for i, s in enumerate(scenes) if s['base'] == scene['base'] and i != s['base']), scene['base']) for scene in scenes]
    room_objects, object_first = [], []
    for scene in scenes:
        object_first.append(len(room_objects))
        room_objects += scene.get('objects', [])
    # Farm's native chooser consumes the same editable board/post layers.
    farm_scenes = [next(i for i, s in enumerate(scenes) if s['name'] == name)
                   for name in ('farm', 'farm-portrait')]
    farm_draw, farm_first, farm_counts = [], [], []
    for index in farm_scenes:
        scene = scenes[index]
        layers = {f'object:{o["id"]}': object_first[index] + n + 1
                  for n, o in enumerate(scene.get('objects', []))}
        layers.update({f'sprite:{h["id"]}': -n-1 for n, h in enumerate(hotspots)
                       if h['scene'] == index})
        order = scene.get('layer_order', list(layers))
        if not isinstance(order, list) or len(order) != len(layers) or set(order) != set(layers):
            raise SystemExit('title scenes: Farm layer_order must name each board/post exactly once')
        for layer in [*scene.get('objects', []), *scene['hotspots']]:
            for flag in ('visible', 'locked'):
                if type(layer.get(flag, True if flag == 'visible' else False)) is not bool:
                    raise SystemExit('title scenes: Farm layer flags must be boolean')
        farm_first.append(len(farm_draw))
        farm_counts.append(len(order))
        farm_draw.extend(layers[key] for key in order)
    lines = [
        '// Generated by tools/title_scenes.py from tools/title_hotspots.json; do not edit.',
        '// Scene pictures and hotspot polygons are in source pixels.',
        f'TITLE_SOURCE_WIDTH :: {data["width"]}',
        f'TITLE_SOURCE_HEIGHT :: {data["height"]}',
        f'TITLE_SCENE_COUNT :: {scene_count}',
        f'TITLE_HOTSPOT_COUNT :: {hotspot_count}',
        '// Farm layer entries: positive object index+1, negative hotspot index+1.',
        f'TITLE_FARM_SCENE: [2]s32 = .[{Numbers(farm_scenes)}];',
        f'TITLE_FARM_DRAW_FIRST: [2]s32 = .[{Numbers(farm_first)}];',
        f'TITLE_FARM_DRAW_COUNT: [2]s32 = .[{Numbers(farm_counts)}];',
        f'TITLE_FARM_DRAW: [{len(farm_draw)}]s32 = .[{Numbers(farm_draw)}];',
        f'TITLE_OBJECT_VISIBLE: [{len(room_objects)}]bool = .[{QuotedBool(o.get("visible", True) for o in room_objects)}];',
        f'TITLE_HOTSPOT_VISIBLE: [{hotspot_count}]bool = .[{QuotedBool(h.get("visible", True) for s in scenes for h in s["hotspots"])}];',
        '// Place centers on the approved full-size map, shared by both orientations.',
        f'TITLE_MAP_AREA_COUNT :: {len(exploration)}',
        f'TITLE_MAP_AREA: [{len(exploration)}]string = .[{Quoted(a["area"] for a in exploration)}];',
        f'TITLE_MAP_CENTER: [{len(exploration) * 2}]s32 = .[{Numbers(v for a in exploration for v in a["center"])}];',
        '',
        f'TITLE_DECORATION_COUNT :: {len(decorations)}',
        f'TITLE_DECORATION_ROTATION: [{len(decorations)}]s32 = .[{Numbers(Rotation(o) for _,o in decorations)}];',
        f'TITLE_DECORATION_SCENE: [{len(decorations)}]s32 = .[{Numbers(i for i,_ in decorations)}];',
        f'TITLE_DECORATION_PATH: [{len(decorations)}]string = .[{Quoted(layer["path"] for _,layer in decorations)}];',
        f'TITLE_DECORATION_RECT: [{len(decorations)*4}]s32 = .[{Numbers(v for _,layer in decorations for v in layer["rect"])}];',
        '// Separate room objects, drawn in this order over the clean background',
        '// plate. Each scene\'s layers are TITLE_SCENE_OBJECT_FIRST .. + TITLE_SCENE_OBJECTS - 1.',
        f'TITLE_OBJECT_COUNT :: {len(room_objects)}',
        f'TITLE_OBJECT_ROTATION: [{len(room_objects)}]s32 = .[{Numbers(Rotation(o) for o in room_objects)}];',
        f'TITLE_OBJECT_ID: [{len(room_objects)}]string = .[{Quoted(layer["id"] for layer in room_objects)}];',
        f'TITLE_OBJECT_PATH: [{len(room_objects)}]string = .[{Quoted(layer["image"] for layer in room_objects)}];',
        f'TITLE_OBJECT_RECT: [{len(room_objects) * 4}]s32 = .[{Numbers(v for layer in room_objects for v in layer["rect"])}];',
        f'TITLE_SCENE_OBJECT_FIRST: [{scene_count}]s32 = .[{Numbers(object_first)}];',
        f'TITLE_SCENE_OBJECTS: [{scene_count}]s32 = .[{Numbers(len(s.get("objects", [])) for s in scenes)}];',
        '// 1 where a look-only view shows the top-left Back button.',
        f'TITLE_SCENE_BACK: [{scene_count}]s32 = .[{Numbers(1 if s.get("back") else 0 for s in scenes)}];',
        f'TITLE_SCENE_NAME: [{scene_count}]string = .[{Quoted(scene["name"] for scene in scenes)}];',
        f'TITLE_SCENE_IMAGE: [{scene_count}]string = .[{Quoted(scene["image"] for scene in scenes)}];',
        f'TITLE_SCENE_LOW: [{scene_count}]string = .[{Quoted(scene["low"] for scene in scenes)}];',
        f'TITLE_SCENE_BACKGROUND: [{scene_count}]string = .[{Quoted(s.get("background", "") for s in scenes)}];',
        f'TITLE_SCENE_FOREGROUND: [{scene_count}]string = .[{Quoted(s.get("foreground", "") for s in scenes)}];',
        '// Paper center, edge and horizontal reveal travel, all in scene source pixels.',
        f'TITLE_SCENE_PAPER: [{scene_count * 4}]s32 = .[{Numbers(v for s in scenes for v in s.get("paper", [0, 0, 0, 0]))}];',
        f'TITLE_SCENE_WIDTH: [{scene_count}]s32 = .[{Numbers(s["width"] for s in scenes)}];',
        f'TITLE_SCENE_HEIGHT: [{scene_count}]s32 = .[{Numbers(s["height"] for s in scenes)}];',
        f'TITLE_SCENE_BASE: [{scene_count}]s32 = .[{Numbers(s["base"] for s in scenes)}];',
        f'TITLE_SCENE_PORTRAIT: [{scene_count}]s32 = .[{Numbers(portrait)}];',
        '// The scene Escape returns to; -1 for the first scene.',
        f'TITLE_SCENE_PARENT: [{scene_count}]s32 = .[{Numbers(parents)}];',
        '// Each scene\'s hotspots are TITLE_SCENE_FIRST .. + TITLE_SCENE_HOTSPOTS - 1, in reading order.',
        f'TITLE_SCENE_FIRST: [{scene_count}]s32 = .[{Numbers(first)}];',
        f'TITLE_SCENE_HOTSPOTS: [{scene_count}]s32 = .[{Numbers(counts)}];',
        '',
        f'TITLE_HOTSPOT_ID: [{hotspot_count}]string = .[{Quoted(hotspot["id"] for hotspot in hotspots)}];',
        f'TITLE_HOTSPOT_GUIDE: [{hotspot_count}]s32 = .[{Numbers(1 if h["game"] == "" and h["scene_target"] < 0 and not h["notice"] and not h["dialogue"] and not h["look"] else 0 for h in hotspots)}];',
        '// 1 for a decorative painted item that only glows (a Market shop, a parrot).',
        f'TITLE_HOTSPOT_LOOK: [{hotspot_count}]s32 = .[{Numbers(h["look"] for h in hotspots)}];',
        f'TITLE_HOTSPOT_NOTICE: [{hotspot_count}]s32 = .[{Numbers(h["notice"] for h in hotspots)}];',
        '// The speech bubble a hotspot opens: TITLE_DIALOGUE index + 1, or 0.',
        f'TITLE_HOTSPOT_DIALOGUE: [{hotspot_count}]s32 = .[{Numbers(h["dialogue"] for h in hotspots)}];',
        '// The hotspot whose figure speaks that bubble (its anchor and glow), or -1.',
        f'TITLE_HOTSPOT_SPEAKER: [{hotspot_count}]s32 = .[{Numbers(h["speaker"] for h in hotspots)}];',
        '// The scene a hotspot leads to, or -1 when it opens TITLE_HOTSPOT_GAME.',
        f'TITLE_HOTSPOT_TARGET: [{hotspot_count}]s32 = .[{Numbers(hotspot["scene_target"] for hotspot in hotspots)}];',
        f'TITLE_HOTSPOT_GAME: [{hotspot_count}]string = .[{Quoted(hotspot["game"] for hotspot in hotspots)}];',
        *ChunkedStrings('TITLE_HOTSPOT_GLOW', 'TitleHotspotGlow', (hotspot['glow'] for hotspot in hotspots)),
        '// Optional always-visible navigation art; shares the glow rectangle.',
        *ChunkedStrings('TITLE_HOTSPOT_REST', 'TitleHotspotRest', (hotspot['rest'] for hotspot in hotspots)),
        f'TITLE_SIGN_DIRECTION: [{hotspot_count}]s32 = .[{Numbers(h["sign_direction"] for h in hotspots)}];',
        f'TITLE_SIGN_ROTATION: [{hotspot_count}]s32 = .[{Numbers(h["sign_rotation"] for h in hotspots)}];',
        f'TITLE_HOTSPOT_ROTATION: [{hotspot_count}]s32 = .[{Numbers(h["rotation"] for h in hotspots)}];',
        '// Localized at runtime; the blank sign sprite never contains language-specific lettering.',
        f'TITLE_SIGN_LABEL: [{hotspot_count}]string = .[{Quoted(h["sign_label"] for h in hotspots)}];',
        '// Text board bounds relative to the hotspot sprite, in source pixels.',
        f'TITLE_SIGN_RECT: [{hotspot_count * 4}]s32 = .[{Numbers(v for h in hotspots for v in h["sign_rect"])}];',
        '// x, y, width, height of each glow picture.',
        f'TITLE_GLOW_RECT: [{hotspot_count * 4}]s32 = .[{Numbers(rects)}];',
        '// Each polygon is TITLE_POLYGON_COUNT points from TITLE_POLYGON_FIRST in',
        '// its chunk of TitlePointsX and TitlePointsY.',
        f'TITLE_POLYGON_CHUNK: [{hotspot_count}]s32 = .[{Numbers(polygon_chunk[:hotspot_count])}];',
        f'TITLE_POLYGON_FIRST: [{hotspot_count}]s32 = .[{Numbers(polygon_first[:hotspot_count])}];',
        f'TITLE_POLYGON_COUNT: [{hotspot_count}]s32 = .[{Numbers(polygon_count[:hotspot_count])}];',
        f'TITLE_OCCLUSION_CHUNK: [{hotspot_count}]s32 = .[{Numbers(polygon_chunk[hotspot_count:])}];',
        f'TITLE_OCCLUSION_FIRST: [{hotspot_count}]s32 = .[{Numbers(polygon_first[hotspot_count:])}];',
        f'TITLE_OCCLUSION_COUNT: [{hotspot_count}]s32 = .[{Numbers(polygon_count[hotspot_count:])}];',
    ]
    map_scene = next((i for i, s in enumerate(scenes) if s['name'] == MAP), -1)
    on_map = lambda h: scenes[h['scene']]['base'] == map_scene
    # A game opened from the map plays over the scene whose own sign opens it.
    homes = [next((other['scene'] for other in hotspots if not on_map(other) and other['game'] == h['game']), -1)
             if on_map(h) and h['game'] else -1 for h in hotspots]
    targets = {(s['name'], h['id']): h['target'] for s in scenes for h in s['hotspots']}
    locked = [1 if targets[(scenes[h['scene']]['name'], h['id'])].startswith('locked:') else 0 for h in hotspots]
    lines += [
        '',
        '// The world map (its landscape scene; -1 without one). Every other scene',
        '// shows its map button; Back returns to where the map was opened.',
        f'TITLE_MAP_SCENE :: {map_scene}',
        '// 1 for a landmark that is not open yet: faded, it answers with the "not yet" cue.',
        f'TITLE_HOTSPOT_LOCKED: [{hotspot_count}]s32 = .[{Numbers(locked)}];',
        '// The scene shown behind a game opened from the map, or -1.',
        f'TITLE_HOTSPOT_HOME: [{hotspot_count}]s32 = .[{Numbers(homes)}];',
        '// The map\'s landmark area (x, y, width, height), always kept in view; zeros elsewhere.',
        f'TITLE_SCENE_SAFE: [{scene_count * 4}]s32 = .[{Numbers(v for i, s in enumerate(scenes) for v in MapSafe(s, [h for h in hotspots if h["scene"] == i]))}];',
    ]
    dialogues = Dialogues()
    first_line, line_count = [], []
    for dialogue in dialogues:
        first_line.append(sum(line_count))
        line_count.append(len(dialogue['lines']))
    texts = [line[language] for d in dialogues for line in d['lines'] for language in LANGUAGES]
    voices = [voice for d in dialogues for voice in d['voices']]
    for values in (texts, voices):
        if len(Quoted(values)) > INITIALIZER_LIMIT:
            raise SystemExit('title scenes: dialogue text is too long for one Ziran array')
    lines += [
        '',
        '// Tap-through speech bubbles. Line L of dialogue D in language G (0 EN,',
        '// 1 DE, 2 ES) is entry (TITLE_DIALOGUE_FIRST[D] + L) * 3 + G.',
        f'TITLE_DIALOGUE_COUNT :: {len(dialogues)}',
        f'TITLE_DIALOGUE_ID: [{len(dialogues)}]string = .[{Quoted(d["id"] for d in dialogues)}];',
        f'TITLE_DIALOGUE_FIRST: [{len(dialogues)}]s32 = .[{Numbers(first_line)}];',
        f'TITLE_DIALOGUE_LINES: [{len(dialogues)}]s32 = .[{Numbers(line_count)}];',
        f'TITLE_DIALOGUE_TEXT: [{len(texts)}]string = .[{Quoted(texts)}];',
        '// Narration for each entry; empty until its recording exists.',
        f'TITLE_DIALOGUE_VOICE: [{len(voices)}]string = .[{Quoted(voices)}];',
    ]
    for index, (xs, ys) in enumerate(chunks):
        lines += ['', f'TITLE_POINT_X_{index}: [{len(xs)}]s32 = .[{Numbers(xs)}];',
                  f'TITLE_POINT_Y_{index}: [{len(ys)}]s32 = .[{Numbers(ys)}];']
    for axis in ('X', 'Y'):
        lines += ['', f'TitlePoints{axis} :: (chunk: s32) -> []s32 {{']
        for index in range(len(chunks)):
            lines.append(f'    if chunk == {index} {{ return TITLE_POINT_{axis}_{index}[:] }}')
        lines += [f'    return TITLE_POINT_{axis}_0[:0]', '}']
    return '\n'.join(lines) + '\n'


def ExportPort():
    """Export the new Port paintings: Market left and Beach right."""
    from PIL import Image, ImageDraw, ImageFilter
    from image_exports import export_image
    for orientation, stem in [('landscape', 'beach-port'), ('portrait', 'beach-portrait-port')]:
        source = ROOT / f'local/art-development/beach-port-redo/port-{orientation}.png'
        with Image.open(source) as image:
            image = image.convert('RGB')
            export_image(source, ROOT / f'assets/jungle/title/{stem}.avif', 'title-background')
            export_image(source, ROOT / f'assets/jungle/title/{stem}-low.avif',
                         'title-background', size=(240, round(image.height * 240 / image.width)))
    port = next(s for s in json.loads(SOURCE.read_text())['scenes'] if s['name'] == 'port')
    for scene in (port, port['portrait']):
        door = next((h for h in scene['hotspots'] if h['id'] == 'bunker-door'), None)
        if door is None:
            continue  # Aquarium entrance now belongs to the Beach.
        x, y, width, height = door['glow_rect']
        points = [(px-x, py-y) for px, py in door['polygon']]
        mask = Image.new('L', (width, height))
        ImageDraw.Draw(mask).line(points + points[:1], fill=210, width=9, joint='curve')
        glow = Image.new('RGBA', mask.size, (255, 220, 125, 0))
        glow.putalpha(mask.filter(ImageFilter.GaussianBlur(5)))
        if door['glow'].endswith('.avif'):
            from avif_codec import save_shipped_cutout
            save_shipped_cutout(glow, ROOT / door['glow'], door['glow'])
        else:
            glow.save(ROOT / door['glow'])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true', help='fail when the data file is out of date')
    parser.add_argument('--export-port', action='store_true', help='export approved Port plates with the title preset')
    arguments = parser.parse_args()
    if arguments.export_port:
        ExportPort()
    # Moving or resizing an object layer carries its hotspot along. --check
    # reports a stale hotspot instead of writing.
    data = json.loads(SOURCE.read_text())
    if not arguments.check and Follow(data):
        SOURCE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
        print(f'title scenes: moved object hotspots in {SOURCE.relative_to(ROOT)}')
    text = Render(*Load())
    if arguments.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != text:
            sys.exit(f'{OUTPUT.relative_to(ROOT)} is out of date; run python3 tools/title_scenes.py')
        print('title scenes: data file is current')
        return
    if not OUTPUT.exists() or OUTPUT.read_text() != text:
        if not OUTPUT.exists() or OUTPUT.read_text() != text:
            OUTPUT.write_text(text)
    print(f'title scenes: wrote {OUTPUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()

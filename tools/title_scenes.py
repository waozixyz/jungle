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
import sys

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'tools/title_hotspots.json'
CATALOG = ROOT / 'games/catalog.txt'
OUTPUT = ROOT / 'host/jungle_title_data.zi'
# Below Ziran's 4095-character file-scope initializer limit.
INITIALIZER_LIMIT = 3600
SIGN_LABELS = {'Beach', 'Farm', 'Desert', 'Campus'}


def Inside(polygon, x, y):
    inside = False
    for (xi, yi), (xj, yj) in zip(polygon, polygon[-1:] + polygon[:-1]):
        if (yi > y) != (yj > y) and x < xi + (y - yi) * (xj - xi) / (yj - yi):
            inside = not inside
    return inside


def SignLabel(hotspot):
    sign = hotspot.get('sign')
    if sign is None:
        return ''
    if not isinstance(sign, dict) or not isinstance(sign.get('label'), str) or sign['label'] not in SIGN_LABELS:
        raise SystemExit('title scenes: invalid path sign label')
    return sign['label']


def Sign(hotspot, rect):
    """A label on a separate physical sprite, with board-local text bounds."""
    sign = hotspot.get('sign')
    if sign is None:
        return '', [0, 0, 0, 0]
    label = SignLabel(hotspot)
    if sign.get('direction') not in ('left','right','up','down'):
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


def Load(source=SOURCE, catalog=CATALOG):
    """The validated scenes, their parents and the flattened hotspots."""
    data = json.loads(Path(source).read_text())
    scenes = [dict(scene, width=data['width'], height=data['height'], base=index)
              for index, scene in enumerate(data['scenes'])]
    # Variants share destinations and identity, but own every pixel coordinate.
    for index, scene in enumerate(data['scenes']):
        if 'portrait' not in scene:
            continue
        portrait = scene['portrait']
        if portrait['width'] <= 0 or portrait['height'] <= portrait['width']:
            raise SystemExit('title scenes: portrait must have positive, taller dimensions')
        original = {h['id']: h['target'] for h in scene['hotspots']}
        alternate = {h['id']: h['target'] for h in portrait['hotspots']}
        if original != alternate or len(alternate) != len(portrait['hotspots']):
            raise SystemExit('title scenes: portrait hotspot IDs and targets must match landscape')
        labels = lambda items: {h['id']: SignLabel(h) for h in items}
        if labels(scene['hotspots']) != labels(portrait['hotspots']):
            raise SystemExit('title scenes: portrait path sign labels must match landscape')
        scenes.append(dict(portrait, name=scene['name'] + '-portrait', base=index))
    names = [scene['name'] for scene in scenes]
    if not scenes or len(set(names)) != len(names):
        raise SystemExit('title scenes: scene names must be unique and present')
    titles = [line.split('|')[1] for line in Path(catalog).read_text().splitlines() if '|' in line]
    hotspots = []
    for index, scene in enumerate(scenes):
        if scene['width'] <= 0 or scene['height'] <= 0:
            raise SystemExit('title scenes: dimensions must be positive')
        if len({h['id'] for h in scene['hotspots']}) != len(scene['hotspots']):
            raise SystemExit('title scenes: duplicate hotspot ID')
        if not scene['hotspots']:
            raise SystemExit(f'title scenes: {scene["name"]} has no hotspots')
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
            elif kind == 'notice' and target in ('Farm', 'Desert') and SignLabel(hotspot) == target and scene['name'] in ('campus', 'campus-portrait'):
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
            hotspots.append({'scene': index, 'id': hotspot['id'], 'scene_target': scene_target,
                             'game': game, 'glow': hotspot['glow'], 'rect': rect, 'polygon': polygon,
                             'rest': hotspot.get('rest', ''), 'occlusion': occlusion,
                             'sign_label': label, 'sign_rect': board,
                             'sign_direction': {'left':1,'right':2,'up':3,'down':4}.get(hotspot.get('sign',{}).get('direction'),0),
                             'notice': {'Farm': 1, 'Desert': 2}.get(target, 0) if kind == 'notice' else 0})
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
    for index, scene in enumerate(scenes):
        if scene['base'] != index:
            seen.add(index)
            parents[index] = parents[scene['base']]
    unreachable = [names[index] for index in range(len(scenes)) if index not in seen]
    if unreachable:
        raise SystemExit('title scenes: unreachable scenes ' + ', '.join(unreachable))
    # Keep the legacy Farm bundle/save identity installed, without a game route.
    missing = sorted(set(titles) - {'Farm'} - {hotspot['game'] for hotspot in hotspots})
    if missing:
        raise SystemExit('title scenes: catalog games without a hotspot: ' + ', '.join(missing))
    for scene in scenes:
        for key in ('image', 'low'):
            if not (ROOT / scene[key]).is_file():
                raise SystemExit(f'title scenes: missing {scene[key]}')
        for key in ('background', 'foreground'):
            if scene.get(key) and not (ROOT / scene[key]).is_file():
                raise SystemExit(f'title scenes: missing {scene[key]}')
        if bool(scene.get('background')) != bool(scene.get('foreground')):
            raise SystemExit('title scenes: background and foreground must be paired')
        if scene.get('paper') and not scene.get('foreground'):
            raise SystemExit('title scenes: hidden paper needs a foreground layer')
        paper = scene.get('paper')
        if paper is not None and (len(paper) != 4 or any(type(v) is not int for v in paper) or
                not 0 <= paper[0] < scene['width'] or not 0 <= paper[1] < scene['height'] or
                paper[2] <= 0 or paper[3] <= 0):
            raise SystemExit('title scenes: invalid paper center, size or reveal travel')
    for hotspot in hotspots:
        if not (ROOT / hotspot['glow']).is_file():
            raise SystemExit(f'title scenes: missing {hotspot["glow"]}')
        if hotspot['rest'] and not (ROOT / hotspot['rest']).is_file():
            raise SystemExit(f'title scenes: missing {hotspot["rest"]}')
    for scene in scenes:
        for layer in scene.get('decorations', []):
            if not (ROOT/layer['path']).is_file() or len(layer['rect']) != 4:
                raise SystemExit('title scenes: invalid decoration')
    return data, scenes, parents, hotspots


def Quoted(values):
    values = [json.dumps(value, ensure_ascii=False) for value in values]
    if sum(len(value) + 2 for value in values) < 200:
        return ', '.join(values)
    return '\n    ' + ',\n    '.join(values) + ',\n'


def Numbers(values):
    # Ziran source lines stay below 4096 characters.
    values = [str(value) for value in values]
    if len(values) <= 24:
        return ', '.join(values)
    rows = [', '.join(values[at:at + 24]) for at in range(0, len(values), 24)]
    return '\n    ' + ',\n    '.join(rows) + ',\n'


def Render(data, scenes, parents, hotspots):
    first, counts = [], []
    for index in range(len(scenes)):
        own = [position for position, hotspot in enumerate(hotspots) if hotspot['scene'] == index]
        first.append(own[0])
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
    decorations = [(i,layer) for i,scene in enumerate(scenes) for layer in scene.get("decorations", [])]
    portrait = [next((i for i, s in enumerate(scenes) if s['base'] == scene['base'] and i != s['base']), scene['base']) for scene in scenes]
    lines = [
        '// Generated by tools/title_scenes.py from tools/title_hotspots.json; do not edit.',
        '// Scene pictures and hotspot polygons are in source pixels.',
        f'TITLE_SOURCE_WIDTH :: {data["width"]}',
        f'TITLE_SOURCE_HEIGHT :: {data["height"]}',
        f'TITLE_SCENE_COUNT :: {scene_count}',
        f'TITLE_HOTSPOT_COUNT :: {hotspot_count}',
        '',
        f'TITLE_DECORATION_COUNT :: {len(decorations)}',
        f'TITLE_DECORATION_SCENE: [{len(decorations)}]s32 = .[{Numbers(i for i,_ in decorations)}];',
        f'TITLE_DECORATION_PATH: [{len(decorations)}]string = .[{Quoted(layer["path"] for _,layer in decorations)}];',
        f'TITLE_DECORATION_RECT: [{len(decorations)*4}]s32 = .[{Numbers(v for _,layer in decorations for v in layer["rect"])}];',
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
        f'TITLE_HOTSPOT_GUIDE: [{hotspot_count}]s32 = .[{Numbers(1 if h["game"] == "" and h["scene_target"] < 0 and not h["notice"] else 0 for h in hotspots)}];',
        f'TITLE_HOTSPOT_NOTICE: [{hotspot_count}]s32 = .[{Numbers(h["notice"] for h in hotspots)}];',
        '// The scene a hotspot leads to, or -1 when it opens TITLE_HOTSPOT_GAME.',
        f'TITLE_HOTSPOT_TARGET: [{hotspot_count}]s32 = .[{Numbers(hotspot["scene_target"] for hotspot in hotspots)}];',
        f'TITLE_HOTSPOT_GAME: [{hotspot_count}]string = .[{Quoted(hotspot["game"] for hotspot in hotspots)}];',
        f'TITLE_HOTSPOT_GLOW: [{hotspot_count}]string = .[{Quoted(hotspot["glow"] for hotspot in hotspots)}];',
        '// Optional always-visible navigation art; shares the glow rectangle.',
        f'TITLE_HOTSPOT_REST: [{hotspot_count}]string = .[{Quoted(hotspot["rest"] for hotspot in hotspots)}];',
        f'TITLE_SIGN_DIRECTION: [{hotspot_count}]s32 = .[{Numbers(h["sign_direction"] for h in hotspots)}];',
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
    for index, (xs, ys) in enumerate(chunks):
        lines += ['', f'TITLE_POINT_X_{index}: [{len(xs)}]s32 = .[{Numbers(xs)}];',
                  f'TITLE_POINT_Y_{index}: [{len(ys)}]s32 = .[{Numbers(ys)}];']
    for axis in ('X', 'Y'):
        lines += ['', f'TitlePoints{axis} :: (chunk: s32) -> []s32 {{']
        for index in range(len(chunks)):
            lines.append(f'    if chunk == {index} {{ return TITLE_POINT_{axis}_{index}[:] }}')
        lines += [f'    return TITLE_POINT_{axis}_0[:0]', '}']
    return '\n'.join(lines) + '\n'


def ExportBeach():
    """Export the owner's approved, unchanged Beach plates at runtime sizes."""
    from PIL import Image, ImageDraw, ImageFilter
    from image_exports import export_image
    for orientation, stem in [('landscape', 'beach-port'), ('portrait', 'beach-portrait-port')]:
        source = ROOT / f'local/art-development/world-scene-refresh/beach-{orientation}-clean.png'
        with Image.open(source) as image:
            image = image.convert('RGB')
            export_image(source, ROOT / f'assets/jungle/title/{stem}.webp', 'title-background')
            export_image(source, ROOT / f'assets/jungle/title/{stem}-low.webp',
                         'title-background', size=(240, round(image.height * 240 / image.width)))
    beach = next(s for s in json.loads(SOURCE.read_text())['scenes'] if s['name'] == 'beach')
    for scene in (beach, beach['portrait']):
        door = next(h for h in scene['hotspots'] if h['id'] == 'bunker-door')
        x, y, width, height = door['glow_rect']
        points = [(px-x, py-y) for px, py in door['polygon']]
        mask = Image.new('L', (width, height))
        ImageDraw.Draw(mask).line(points + points[:1], fill=210, width=9, joint='curve')
        glow = Image.new('RGBA', mask.size, (255, 220, 125, 0))
        glow.putalpha(mask.filter(ImageFilter.GaussianBlur(5)))
        if door['glow'].endswith('.webp'):
            glow.save(ROOT / door['glow'], 'WEBP', lossless=True, exact=True, method=6)
        else:
            glow.save(ROOT / door['glow'])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true', help='fail when the data file is out of date')
    parser.add_argument('--export-beach', action='store_true', help='export approved Beach plates with the title preset')
    arguments = parser.parse_args()
    if arguments.export_beach:
        ExportBeach()
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

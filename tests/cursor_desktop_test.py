"""Native: Jungle's calm arrow and pointing hand on an owned private Xvfb.

Moves the real X pointer over the treehouse, the Farm and games in landscape
and portrait, and reads the server's cursor with XFixes. The pointing hand
shows only where a click does something: a title item, a corner button, a
Farm bed's painted soil, a toolbar button. Bare picture, the corners of a bed's
frame off its soil and empty soil show the painted arrow. Both are the 32-unit
bitmaps from host/jungle_cursor.zi, premultiplied with a dark soft edge (no
light fringe), and each is one X cursor object throughout: it never flickers,
is never re-created and only changes when the pointed target does. In the Farm
a chosen tool is one stable cursor across the crop field.
"""
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time

import runtime_test as rt

ROOT = rt.ROOT
PROPS = (r'\.width\s*=\s*(\d+)\s*,\s*\.height\s*=\s*(\d+)\s*,\s*'
         r'\.hotspot_x\s*=\s*(\d+)\s*,\s*\.hotspot_y\s*=\s*(\d+)')
SIZES = ((960, 600), (600, 960))
POINTS = ((.5, .5), (.2, .3), (.8, .7), (.1, .9), (.9, .12), (.5, .15), (.35, .8), (.65, .35))


def declared(path, name):
    """(width, height, hotspot x, hotspot y) of the CursorProps after NAME in PATH."""
    text = (ROOT / path).read_text()
    match = re.search(re.escape(name) + r'[\s\S]*?' + PROPS, text)
    assert match, (path, name)
    return tuple(map(int, match.groups()))


ARROW = declared('host/jungle_cursor.zi', 'JungleArrowCursor ::')
HAND = declared('host/jungle_cursor.zi', 'JungleHandCursor ::')
WATER = declared('games/garden/jungle_garden.zi', 'cursor-watering-can.avif"')
BASKET = declared('games/garden/jungle_garden.zi', 'cursor-harvest-basket.avif"')
NAMES = {ARROW: 'arrow', HAND: 'hand', WATER: 'watering can', BASKET: 'basket'}


class CursorImage(c.Structure):
    _fields_ = [('x', c.c_short), ('y', c.c_short), ('width', c.c_ushort), ('height', c.c_ushort),
                ('xhot', c.c_ushort), ('yhot', c.c_ushort), ('serial', c.c_ulong),
                ('pixels', c.POINTER(c.c_ulong)), ('atom', c.c_ulong), ('name', c.c_char_p)]


def cursor(desktop):
    """(width, height, hotspot x, hotspot y, serial, ARGB pixels) of the server cursor."""
    desktop.verify_server()
    x = c.CDLL('libX11.so.6')
    fixes = c.CDLL('libXfixes.so.3')
    x.XOpenDisplay.argtypes = [c.c_char_p]
    x.XOpenDisplay.restype = c.c_void_p
    x.XFree.argtypes = [c.c_void_p]
    x.XCloseDisplay.argtypes = [c.c_void_p]
    fixes.XFixesGetCursorImage.argtypes = [c.c_void_p]
    fixes.XFixesGetCursorImage.restype = c.POINTER(CursorImage)
    connection = x.XOpenDisplay(desktop.env['DISPLAY'].encode())
    assert connection
    try:
        image = fixes.XFixesGetCursorImage(connection)
        assert image
        try:
            v = image.contents
            pixels = tuple(int(v.pixels[i]) & 0xffffffff for i in range(v.width * v.height))
            return v.width, v.height, v.xhot, v.yhot, v.serial, pixels
        finally:
            x.XFree(image)
    finally:
        x.XCloseDisplay(connection)


def clean(pixels):
    """Premultiplied ARGB with a soft edge that is dark outline, not a light matte."""
    soft = 0
    for pixel in pixels:
        alpha, red, green, blue = pixel >> 24, (pixel >> 16) & 255, (pixel >> 8) & 255, pixel & 255
        assert red <= alpha and green <= alpha and blue <= alpha, 'cursor is not premultiplied'
        if 0 < alpha < 200:
            soft += 1
            assert (.299 * red + .587 * green + .114 * blue) * 255 / alpha <= 150, 'light fringe on the cursor edge'
    assert soft > 20, 'cursor has no antialiased edge'
    assert len(set(pixels)) > 40, 'cursor bitmap did not load'


def inside(polygon, x, y):
    hit = False
    j = len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            hit = not hit
        j = i
    return hit


def edge_distance(polygon, x, y):
    best = float('inf')
    for (ax, ay), (bx, by) in zip(polygon, polygon[1:] + polygon[:1]):
        dx, dy = bx - ax, by - ay
        t = 0 if dx == dy == 0 else max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
        best = min(best, ((ax + t * dx - x) ** 2 + (ay + t * dy - y) ** 2) ** .5)
    return best


class Run:
    def __init__(self, desktop):
        self.d = desktop
        self.serials = {}
        self.bitmaps = {}
        self.checked = []

    def at(self, x, y):
        rt.run(['xdotool', 'mousemove', '--window', self.d.window, str(round(x)), str(round(y))], self.d.env)

    def size(self):
        geometry = rt.run(['xdotool', 'getwindowgeometry', '--shell', self.d.window], self.d.env)
        fields = dict(line.split('=', 1) for line in geometry.splitlines() if '=' in line)
        return int(fields['WIDTH']), int(fields['HEIGHT'])

    def settle(self, shape, phase):
        end = time.monotonic() + 8
        while cursor(self.d)[:4] != shape:
            assert time.monotonic() < end, ('wrong cursor', phase, NAMES.get(shape, shape),
                                            NAMES.get(cursor(self.d)[:4], cursor(self.d)[:4]))
            time.sleep(.08)
        first = cursor(self.d)
        clean(first[5])
        digest = hashlib.sha256(b''.join(p.to_bytes(4, 'little') for p in first[5])).hexdigest()
        # The same bitmap and X cursor object every time this shape shows.
        assert self.bitmaps.setdefault(shape, digest) == digest, ('cursor bitmap changed', phase)
        assert self.serials.setdefault(shape, first[4]) == first[4], ('cursor was re-created', phase)
        return first

    def expect_at(self, shape, phase, points):
        """Window points that all show SHAPE: it settles once, then holds still
        while the pointer rests and moves among them, with no flicker."""
        self.at(*points[0])
        first = self.settle(shape, phase)
        for x, y in list(points[1:]) * 2 + [points[0]]:
            for dx in (0, 2, -2):
                self.at(x + dx, y + dx)
                time.sleep(.07)
                now = cursor(self.d)
                assert now[:5] == first[:5], ('cursor changed', phase, NAMES.get(now[:4], now[:4]))
        self.d.alive()
        self.checked.append(phase)

    def expect(self, shape, phase, points=POINTS):
        w, h = self.size()
        self.expect_at(shape, phase, [(w * fx, h * fy) for fx, fy in points])

    def application(self, phase):
        """Every point shows one of the application cursors, steadily."""
        w, h = self.size()
        for fx, fy in POINTS:
            self.at(w * fx, h * fy)
            time.sleep(.25)
            shape = cursor(self.d)[:4]
            assert shape in (ARROW, HAND), ('not an application cursor', phase, shape)
            first = self.settle(shape, phase)
            for _ in range(4):
                time.sleep(.06)
                assert cursor(self.d)[:5] == first[:5], ('cursor flickered at rest', phase)
        self.d.alive()
        self.checked.append(phase)

    def home(self, phase):
        for _ in range(4):
            if title_shown(self.d):
                break
            self.d.key('Escape')
            time.sleep(.6)
        assert title_shown(self.d), ('did not return to the title', phase)
        self.application(phase)


def title_shown(desktop):
    picture = desktop.capture_actual('cursor-title')
    unit = rt.title_unit(*picture.size)
    chip = picture.crop(tuple(round(v * unit) for v in (11, 11, 31, 23)))
    return (0, 0, 170) in [colour for _, colour in chip.getcolors(100000)]


def treehouse_targets(w, h):
    """For a W by H treehouse view: a deep painted point of every item in view,
    bare picture well away from every item and the paper, and the sound button."""
    data = json.loads((ROOT / 'tools/title_hotspots.json').read_text())
    scene = next(s for s in data['scenes'] if s['name'] == 'treehouse')
    view = scene['portrait'] if h > w else scene
    width, height = view.get('width', data['width']), view.get('height', data['height'])
    scale = max(w / width, h / height)
    ox, oy = (w - width * scale) / 2, (h - height * scale) / 2
    unit = rt.title_unit(w, h)
    top = 44 * unit
    spots = [s for s in view['hotspots'] if s.get('polygon')]
    shapes = [[tuple(p) for p in s['polygon']] for s in spots]
    occluded = [[tuple(p) for p in s.get('occlusion') or []] for s in spots]
    areas = [s['glow_rect'][2] * s['glow_rect'][3] for s in spots]

    def hit(x, y):
        found = -1
        for index, polygon in enumerate(shapes):
            if inside(polygon, x, y) and not (occluded[index] and inside(occluded[index], x, y)):
                if found < 0 or areas[index] < areas[found]:
                    found = index
        return found

    def window(x, y):
        return ox + x * scale, oy + y * scale

    usable = lambda x, y: 8 < x < w - 8 and top < y < h - 8
    pointing = []
    for index, polygon in enumerate(shapes):
        xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
        best = None
        for row in range(1, 30):
            for column in range(1, 30):
                x = min(xs) + (max(xs) - min(xs)) * column / 30
                y = min(ys) + (max(ys) - min(ys)) * row / 30
                if hit(x, y) != index or not usable(*window(x, y)):
                    continue
                depth = edge_distance(polygon, x, y)
                if best is None or depth > best[0]:
                    best = (depth, x, y)
        if best and best[0] * scale >= 12:
            pointing.append(window(best[1], best[2]))
    assert len(pointing) >= 3, ('too few title items in view', w, h, len(pointing))
    paper = view.get('paper') or scene.get('paper')
    calm = []
    for row in range(1, 16):
        for column in range(1, 16):
            x, y = w * column / 16, h * row / 16
            if not usable(x, y) or y < 60 * unit:
                continue
            sx, sy = (x - ox) / scale, (y - oy) / scale
            if hit(sx, sy) >= 0 or min(edge_distance(p, sx, sy) for p in shapes) * scale < 24:
                continue
            if paper:
                px, py, size, reveal = (v * scale for v in paper)
                reach = max(size * .55, 22) + 40
                if ox + px - reach <= x <= ox + px + reveal + reach and oy + py - reach <= y <= oy + py + reach:
                    continue
            calm.append((x, y))
    assert len(calm) >= 3, ('too little bare picture in view', w, h, len(calm))
    calm = calm[::max(1, len(calm) // 5)][:5]
    return pointing, calm, ((w / unit - 19) * unit, 17 * unit)


def treehouse(run, w, h):
    """Every item's painted interior points; bare picture away from them stays calm."""
    pointing, calm, sound = treehouse_targets(w, h)
    label = f'{w}x{h} treehouse'
    # Alternate so every switch is a change of the pointed target.
    run.expect_at(ARROW, f'{label}: bare picture', calm)
    run.expect_at(HAND, f'{label}: items', pointing)
    run.expect_at(ARROW, f'{label}: bare picture again', calm[::-1])
    run.expect_at(HAND, f'{label}: sound button', [sound])
    run.expect_at(ARROW, f'{label}: bare picture after the button', calm[:2])


def garden_fields():
    text = (ROOT / 'games/garden/garden_fields.zi').read_text()
    number = lambda name: [int(v) for v in re.search(name + r':[^=]*=\s*\.\[([^\]]*)\]', text)[1].split(',')]
    first, count = number('GARDEN_FIELD_FIRST'), number('GARDEN_FIELD_POINTS')
    xs, ys, glow = number('GARDEN_FIELD_X'), number('GARDEN_FIELD_Y'), number('GARDEN_FIELD_GLOW')
    fields = [list(zip(xs[f:f + n], ys[f:f + n])) for f, n in zip(first, count)]
    return fields, [glow[i * 4:i * 4 + 4] for i in range(8)]


def farm(run, state, w, h):
    """Bed soil points and the bed frames' bare corners stay calm; the chosen
    tool stays one cursor; the arrow returns after."""
    sys.path.insert(0, str(ROOT / 'tests'))
    import farm_smoke_test as farm_test
    d = run.d
    label = f'{w}x{h} farm'
    d.game('Farm')
    ui = farm_test.FarmUI(d, w, h)
    end = time.monotonic() + 20
    while not farm_test.save_path(state).exists():
        assert time.monotonic() < end, 'Farm never opened'
        time.sleep(.1)
    time.sleep(.7)
    # The chooser: GardenFieldAt's painted beds against their glow frames.
    portrait = h > w
    fields, rects = garden_fields()
    ui.layout(True)
    iw, ih = (1024, 1536) if portrait else (1671, 941)
    scale, cw, ch = farm_test.contain(ui.lw, ui.lh, iw, ih)
    window = lambda x, y: (((ui.lw - cw) // 2 + x * scale) * ui.scale, ((ui.lh - ch) // 2 + y * scale) * ui.scale)
    beds = fields[4:] if portrait else fields[:4]
    frames = rects[4:] if portrait else rects[:4]
    # The Campus and Market sign presses (Chooser), in logical pixels: they
    # point, so a bare corner must lie off them.
    left, top = (ui.lw - cw) // 2, (ui.lh - ch) // 2
    edge = max(cw * 240 // iw, 72)
    sign_x, sign_y = left + cw * (600 if portrait else 1260) // iw, top + ch * (300 if portrait else 90) // ih
    market = max(cw * 170 // iw, 64)
    market_y = top + ch * (383 if portrait else 278) // ih
    signs = ((sign_x, sign_y + edge // 5, edge, edge // 2), (left, market_y + market // 5, market, market // 2))

    def on_sign(x, y):
        lx, ly = left + x * scale, top + y * scale
        return any(sx - 6 <= lx <= sx + sw + 6 and sy - 6 <= ly <= sy + sh + 6 for sx, sy, sw, sh in signs)
    soil, corners = [], []
    for bed, (polygon, (gx, gy, gw, gh)) in enumerate(zip(beds, frames)):
        best, corner = None, None
        for row in range(1, 20):
            for column in range(1, 20):
                x, y = gx + gw * column / 20, gy + gh * row / 20
                on = [inside(p, x, y) for p in beds]
                near = min(edge_distance(p, x, y) for p in beds) * scale * ui.scale
                if on[bed] and not any(on[bed + 1:]) and not on_sign(x, y) and (best is None or near > best[0]):
                    best = (near, x, y)
                if not any(on) and near > 14 and not on_sign(x, y) and corner is None:
                    corner = (x, y)
        assert best and best[0] > 10, ('no bed soil to point at', bed)
        soil.append(window(best[1], best[2]))
        if corner:
            corners.append(window(*corner))
    assert corners, 'no bed frame corner off the painted beds'
    run.expect_at(HAND, f'{label}: bed soil', soil)
    run.expect_at(ARROW, f'{label}: bed frame corners off the soil', corners)
    run.expect_at(HAND, f'{label}: bed soil again', soil[::-1])
    ui.garden(0)
    time.sleep(.6)
    sx, sy, sw, sh = ui.soil_rect()
    field = tuple(((sx + sw * u) * ui.scale, ui.header + (sy + sh * v) * ui.scale)
                  for u, v in ((.5, .5), (.1, .1), (.9, .9), (.2, .8), (.8, .2), (.5, .05), (.05, .5), (.95, .5)))
    bag = ui.bag()
    toolbar = [(bag[0] * ui.scale, ui.header + bag[1] * ui.scale)]
    run.expect_at(ARROW, f'{label}: empty soil, hand', field)
    run.expect_at(HAND, f'{label}: seed bag', toolbar)
    ui.tool(1)
    run.expect_at(WATER, f'{label}: crop field, watering can', field)
    ui.tool(2)
    run.expect_at(BASKET, f'{label}: crop field, basket', field)
    ui.tool(0)
    run.expect_at(ARROW, f'{label}: empty soil, hand again', field)
    ui.tool(1)
    ui.sky()
    time.sleep(.5)
    ui.layout(True)
    run.expect_at(HAND, f'{label}: bed soil after the watering can', soil)


def main():
    for tool in ('Xvfb', 'xdotool', 'import'):
        assert shutil.which(tool), f'cursor test needs {tool}'
    assert len({ARROW, HAND}) == 2, 'the calm and pointing cursors must differ'
    binary = Path(os.environ.get('JUNGLE_TEST_BINARY', ROOT / 'build/app/jungle')).resolve()
    work = ROOT / 'work/runtime-tests'
    work.mkdir(parents=True, exist_ok=True)
    servers = []
    for w, h in SIZES:
        with tempfile.TemporaryDirectory(prefix='jungle-cursor-', dir=work) as folder:
            state = Path(folder)
            for name, value in (('guide-seen', 'yes'), ('guide-sound', 'off'), ('sound', 'off')):
                (state / f'{name}.txt').write_text(value + '\n')
            with rt.Desktop(binary, state, extra_env={'TMPDIR': str(state)}, screen_size='1400x2500') as d:
                d.resize(w, h)
                time.sleep(1.2)
                run = Run(d)
                treehouse(run, w, h)
                for title in ('Picture Book', 'Jigsaw Puzzles', 'Matching Pairs'):
                    keys = rt.title_keys(title)
                    for key in keys:
                        d.key(key)
                        time.sleep(.5)
                    time.sleep(1.5)
                    run.application(f'{w}x{h} {title}')
                    run.home(f'{w}x{h} back from {title}')
                if (ROOT / 'games/garden/farm.zi').exists():
                    farm(run, state, w, h)
                    run.home(f'{w}x{h} back from Farm')
                servers.append(d.server.pid)
            print(f'{w}x{h}: {len(run.checked)} views: ' + ', '.join(run.checked), flush=True)
    print(f'private Xvfb pids={servers}: the arrow over bare areas and the hand only over clickable targets, '
          'premultiplied with a dark edge, one X cursor each, never flickering', flush=True)


if __name__ == '__main__':
    main()

"""Native: Jungle's one hand cursor across the whole app on an owned private Xvfb.

Moves the real X pointer over title scenes, the bookshelf, books and games and
reads the server's cursor with XFixes. The hand must be the 32-unit bitmap
with its fingertip hotspot, premultiplied with a dark soft edge (no light
fringe), and the same X cursor object throughout: no flicker, re-creation or
swaps. In the Farm, a chosen tool is one stable cursor across the crop field.
"""
import ctypes as c
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

import runtime_test as rt

ROOT = rt.ROOT
HAND = (32, 32, 8, 1)
WATER = (32, 32, 2, 14)
BASKET = (32, 32, 16, 16)
POINTS = ((.5, .5), (.2, .3), (.8, .7), (.1, .9), (.9, .12), (.5, .15), (.35, .8), (.65, .35))


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


class Run:
    def __init__(self, desktop):
        self.d = desktop
        self.serials = {}
        self.bitmaps = {}
        self.checked = []

    def point(self, fx, fy):
        geometry = rt.run(['xdotool', 'getwindowgeometry', '--shell', self.d.window], self.d.env)
        fields = dict(line.split('=', 1) for line in geometry.splitlines() if '=' in line)
        x, y = round(int(fields['WIDTH']) * fx), round(int(fields['HEIGHT']) * fy)
        rt.run(['xdotool', 'mousemove', '--window', self.d.window, str(x), str(y)], self.d.env)

    def expect(self, shape, phase, points=POINTS):
        """The pointer shows SHAPE everywhere in PHASE, as one unchanging X cursor."""
        self.point(*points[0])
        end = time.monotonic() + 8
        while cursor(self.d)[:4] != shape:
            assert time.monotonic() < end, ('wrong cursor', phase, shape, cursor(self.d)[:4])
            time.sleep(.1)
        first = cursor(self.d)
        clean(first[5])
        digest = hashlib.sha256(b''.join(p.to_bytes(4, 'little') for p in first[5])).hexdigest()
        # The same bitmap and X cursor object every time this shape shows.
        assert self.bitmaps.setdefault(shape, digest) == digest, ('cursor bitmap changed', phase)
        assert self.serials.setdefault(shape, first[4]) == first[4], ('cursor was re-created', phase)
        for fx, fy in points[1:] * 2:
            self.point(fx, fy)
            time.sleep(.08)
            now = cursor(self.d)
            assert now[:5] == first[:5], ('cursor changed while moving', phase, now[:5], first[:5])
        self.d.alive()
        self.checked.append(phase)

    def home(self, phase):
        for _ in range(4):
            if title_shown(self.d):
                break
            self.d.key('Escape')
            time.sleep(.6)
        assert title_shown(self.d), ('did not return to the title', phase)
        self.expect(HAND, phase)


def title_shown(desktop):
    picture = desktop.capture_actual('cursor-title')
    unit = rt.title_unit(*picture.size)
    chip = picture.crop(tuple(round(v * unit) for v in (11, 11, 31, 23)))
    return (0, 0, 170) in [colour for _, colour in chip.getcolors(100000)]


def farm(run, state):
    """Crop fields: the chosen tool stays one cursor; the hand returns after."""
    sys.path.insert(0, str(ROOT / 'tests'))
    import farm_smoke_test as farm_test
    d = run.d
    d.game('Farm')
    ui = farm_test.FarmUI(d, 960, 600)
    end = time.monotonic() + 20
    while not farm_test.save_path(state).exists():
        assert time.monotonic() < end, 'Farm never opened'
        time.sleep(.1)
    time.sleep(.7)
    run.expect(HAND, 'farm sky')
    ui.garden(0)
    time.sleep(.5)
    run.expect(HAND, 'farm crop field, hand')
    sx, sy, sw, sh = ui.soil_rect()
    # Window fractions of soil points, the whole field corner to corner.
    field = tuple(((sx + sw * u) * ui.scale / ui.w, (ui.header + (sy + sh * v) * ui.scale) / ui.h)
                  for u, v in ((.5, .5), (.1, .1), (.9, .9), (.2, .8), (.8, .2), (.5, .05), (.05, .5), (.95, .5)))
    ui.tool(1)
    run.expect(WATER, 'farm crop field, watering can', field)
    ui.tool(2)
    run.expect(BASKET, 'farm crop field, basket', field)
    ui.tool(0)
    run.expect(HAND, 'farm crop field, hand again', field)
    ui.tool(1)
    ui.sky()
    time.sleep(.4)
    run.expect(HAND, 'farm sky after the watering can')


def main():
    for tool in ('Xvfb', 'xdotool', 'import'):
        assert shutil.which(tool), f'cursor test needs {tool}'
    binary = Path(os.environ.get('JUNGLE_TEST_BINARY', ROOT / 'build/app/jungle')).resolve()
    work = ROOT / 'work/runtime-tests'
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='jungle-cursor-', dir=work) as folder:
        state = Path(folder)
        for name, value in (('guide-seen', 'yes'), ('guide-sound', 'off'), ('sound', 'off')):
            (state / f'{name}.txt').write_text(value + '\n')
        with rt.Desktop(binary, state, extra_env={'TMPDIR': str(state)}, screen_size='1400x2500') as d:
            d.resize(960, 600)
            run = Run(d)
            d.key('Home')
            run.expect(HAND, 'treehouse')
            for title in ('Picture Book', 'ABC Book', 'Jigsaw Puzzles', 'Little Piano', 'Matching Pairs'):
                keys = rt.title_keys(title)
                for step, key in enumerate(keys):
                    d.key(key)
                    time.sleep(.5)
                    run.expect(HAND, f'{title}: title step {step + 1} of {len(keys)}')
                time.sleep(1.5)
                run.expect(HAND, title)
                run.home(f'back from {title}')
            if (ROOT / 'games/garden/farm.zi').exists():
                farm(run, state)
                run.home('back from Farm')
        print(f'private Xvfb pid={d.server.pid}: one hand cursor, premultiplied with a dark edge and never re-created, '
              f'across {len(run.checked)} views: ' + ', '.join(run.checked), flush=True)


if __name__ == '__main__':
    main()

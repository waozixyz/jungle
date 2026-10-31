#!/usr/bin/env python3
"""Exercise eight room instruments and actual native audio on private Xvfb.

--audio-only runs the deterministic sample suite without starting any UI.
The native probe observes SDL_QueueAudio and forwards to the real SDL backend;
it records only byte counts and hashes, not private audio or desktop pixels.
"""
import argparse
import importlib.util
import hashlib
import ctypes
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import time
import wave

from PIL import Image, ImageChops
import runtime_test as rt

TITLE = 'Music Room'
SOUNDS = ('big_drum', 'small_drum', 'shaker', 'bell', 'xylophone', 'guitar', 'cymbal', 'tambourine')
PICTURES = ('big-drum', 'little-drum', 'shaker', 'bell', 'xylophone', 'guitar', 'cymbal', 'tambourine')
BODY_FRACTIONS = ((.50, .52), (.50, .52), (.32, .52), (.50, .52),
                  (.50, .52), (.50, .60), (.50, .35), (.50, .52))
PRESERVED = {'assets/drums/pictures/bell.png': 'f14c6aebe01fc8453d646cb39cf132d0495b9ebbd6934590b5857a95c1d8856a',
 'assets/drums/pictures/big-drum.png': 'bf4d9d5498da047be39e448fd3950a0e6acf02f446f68848f9678b4bd00523d6',
 'assets/drums/pictures/cymbal.png': 'c8c20ce23156b3bf1892ffcb606ac1d36d6208c77a00352d6aa6890dbacbd338',
 'assets/drums/pictures/guitar.png': 'd72134bf42c860b1402959ff207c134314987907ba7bdf655ab7b08817e28009',
 'assets/drums/pictures/little-drum.png': '10b7b94c5f99c03771229bd6be3fe5c69a3940e04d361a21f58bb8967cb45ae3',
 'assets/drums/pictures/room.png': '325b08de4857a5cd09a982d7c956100792668b21dfbacb221b74bb719710964b',
 'assets/drums/pictures/shaker.png': 'd452203bead14dc3f6b2e2ab56389213e6d5a3d06de0d3fc3673e31fd79cb12c',
 'assets/drums/pictures/tambourine.png': 'f5ffec3fa0adc5dab4a64694c8054354b67347aa5b37429e567ab1984db3238b',
 'assets/drums/pictures/xylophone.png': '56e319a468ea65388aea3bc07a5d969b0d897e9f490a450c6c6ca97e8e367cdd',
 'assets/drums/sounds/bell.wav': 'cb68ccc0ecc4e016794a3795189cf1cf39fe549a21c961e55c2d1ee72f50ef22',
 'assets/drums/sounds/cymbal.wav': '4272a4c49c06ddbf64d55e6d5f72a03e3ce43eb608a88c1e9af7bb3ce42bc88b',
 'assets/drums/sounds/guitar.wav': 'ff189dc2a23ec021c7696b0a3f75e9c9989de29d138f208bbfff26dc8611a01b',
 'assets/drums/sounds/low_drum.wav': '76cd52a2f9b7552dc204cca91487b2632b8601b6498eed64fbc212887177f491',
 'assets/drums/sounds/shaker.wav': '0e028a0e36ca763fc9e19d76364bb278d27f47b7ca30eaeef7cc52a77a02d288',
 'assets/drums/sounds/small_drum.wav': '65b5b4c573a5a8cc29b7eeafb0ade57d4e2960982a42df7d8180098a9c8aeac8',
 'assets/drums/sounds/tambourine.wav': '5c79ad3e49a8bf17354bcdf50e7c80c37579a7f9d5856f8ea70e84871d2205bd',
 'assets/drums/sounds/xylophone.wav': 'ca96f37c0c6a2f0bf270775e21077c5561284e8805ab46f6ec7492ee4b77e9ec'}
VOICE_TEXT = {
    ('de', 'copy'): 'Hör zu und spiele die gleichen Klänge. Tippe auf Noch mal, um sie wieder zu hören.',
    ('de', 'free'): 'Tippe auf die Trommeln und mach Musik.',
    ('en', 'copy'): 'Listen, then play the same sounds. Tap replay to listen again.',
    ('en', 'free'): 'Tap the drums and make music.',
    ('es', 'copy'): 'Escucha y toca los mismos sonidos. Toca repetir para escuchar otra vez.',
    ('es', 'free'): 'Toca los tambores y haz música.',
}
MODEL = (rt.ROOT / 'games/drums/drums.zi').read_text()


def positions(name):
    return tuple(map(int, re.search(r'DRUMS_' + name + r': \[8\]s32 = \.\[([^]]+)\]', MODEL)[1].split(',')))


def geometry(width, height, copying=False):
    height -= 56
    scale = min(width / 400, height / 700) if width <= height else min(height / 520, width / 780)
    scale = max(.5, min(scale, 1.6))
    w, h = int(width / scale), int(height / scale)
    wide = w > h
    scene_width, scene_height = (800, 410) if wide else (400, 624)
    room_top = 112 if copying else 60
    available = h - room_top - (72 if copying else 8)
    fit = min((w - 24) * 1000 // scene_width, available * 1000 // scene_height)
    left = (w - scene_width * fit // 1000) // 2
    top = room_top + (available - scene_height * fit // 1000) // 2
    return scale, w, h, wide, fit, left, top


def instruments(size, copying=False):
    _, width, height, wide, fit, left, top = geometry(*size, copying=copying)
    prefix = 'LANDSCAPE' if wide else 'PORTRAIT'
    places = [(left + x * fit // 1000, top + y * fit // 1000, edge * fit // 1000)
              for x, y, edge in zip(positions(prefix + '_X'), positions(prefix + '_Y'), positions(prefix + '_EDGE'))]
    if not wide:
        room_top = 112 if copying else 60
        room_height = height - room_top - (72 if copying else 8)
        cover = max(width - 18, room_height - 2)
        art_fit = cover * 1000 // 1254
        art_y = room_top + 1 + (room_height - 2 - 1254 * art_fit // 1000) // 2
        window_bottom = min(room_top + room_height - 1,
                            art_y + 60 * art_fit // 1000 + 310 * art_fit // 1000)
        for pad, base in ((2, 91), (3, 95)):
            x, y, edge = places[pad]
            shelf_height = (edge * 8 // 10 + 10) // 3
            shelf_y = max(y + edge * base // 100,
                          window_bottom + 12 + shelf_height * 140 // 724)
            places[pad] = x, shelf_y - edge * base // 100, edge
    return places


def actual_point(size, x, y):
    scale = geometry(*size)[0]
    return round(x * scale), round(56 + y * scale)


def body_point(size, pad, copying=False):
    x, y, edge = instruments(size, copying)[pad]
    fx, fy = BODY_FRACTIONS[pad]
    return actual_point(size, x + edge * fx, y + edge * fy)


def changed(before, after):
    return ImageChops.difference(before.convert('RGB'), after.convert('RGB')).getbbox()


def art_box(size, pad, labels=False):
    x, y, edge = instruments(size)[pad]
    if labels and pad == 5: x -= edge // 4
    gap = 28 if labels and pad in (2, 3) else 0
    a = actual_point(size, x - (12 if labels else 0), y + (edge if labels else 0) + gap)
    b = actual_point(size, x + edge + (12 if labels else 0), y + edge + (22 if labels else 0) + gap)
    return *a, *b


def assert_room(picture, size, language):
    places = instruments(size)
    assert max(y for x, y, edge in places) - min(y for x, y, edge in places) > 110, 'instruments collapsed to a row'
    assert len({edge for x, y, edge in places}) >= 6, 'room became uniform tiles'
    assert len(picture.getcolors(2_000_000)) > 500, 'room illustration is missing'
    for pad in range(8):
        crop = picture.crop(art_box(size, pad)).convert('RGB')
        assert len(crop.getcolors(1_000_000)) > 200, (language, pad, 'instrument artwork missing')
        # Match opaque interior pixels against the actual shipped picture so
        # a detailed room background cannot masquerade as a missing overlay.
        with Image.open(rt.ROOT / 'assets/drums/pictures' / f'{PICTURES[pad]}.png') as source:
            expected = source.convert('RGBA').resize(crop.size, Image.Resampling.LANCZOS)
            if pad == 7: expected = expected.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        error = []
        stride = max(2, crop.width // 18)
        for py in range(stride, crop.height - stride, stride):
            for px in range(stride, crop.width - stride, stride):
                color = expected.getpixel((px, py))
                if color[3] > 250:
                    actual = crop.getpixel((px, py))
                    error.append(sum(abs(a - b) for a, b in zip(actual, color[:3])) / 3)
        assert len(error) > 8 and sum(error) / len(error) < 35, (language, pad, 'rendered picture differs or is missing', sum(error) / max(1, len(error)))
        label = picture.crop(art_box(size, pad, labels=True)).convert('RGB')
        pixels = label.get_flattened_data() if hasattr(label, 'get_flattened_data') else label.getdata()
        assert sum(max(color) < 190 for color in pixels) > 10, (language, pad, 'label unreadable')


PROBE = r'''
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
int SDL_QueueAudio(uint32_t device, const void *data, uint32_t length) {
    static int (*real_queue)(uint32_t, const void *, uint32_t);
    if (!real_queue) real_queue = dlsym(RTLD_NEXT, "SDL_QueueAudio");
    const unsigned char *bytes = data;
    uint64_t hash = UINT64_C(14695981039346656037);
    for (uint32_t i = 0; i < length; i++) { hash ^= bytes[i]; hash *= UINT64_C(1099511628211); }
    int result = real_queue ? real_queue(device, data, length) : -1;
    const char *path = getenv("JUNGLE_TEST_AUDIO_QUEUE");
    FILE *out = path ? fopen(path, "a") : NULL;
    if (out) { fprintf(out, "%u %016llx %d\n", length, (unsigned long long)hash, result); fclose(out); }
    return result;
}
'''


class NativeAudio:
    def __init__(self, directory, audio):
        source, self.library = directory / 'audio_probe.c', directory / 'audio_probe.so'
        source.write_text(PROBE)
        subprocess.run(['cc', '-shared', '-fPIC', '-O2', str(source), '-ldl', '-o', str(self.library)], check=True, capture_output=True, timeout=30)
        self.path = directory / 'queued-audio.txt'
        self.path.touch()
        self.offset = 0
        self.expected = {}
        for name in SOUNDS:
            raw = audio.read_pcm(rt.ROOT / 'assets/drums/sounds' / f'{name}.wav')
            samples = [value[0] for value in struct.iter_unpack('<h', raw)]
            mixed = bytearray()
            for i, value in enumerate(samples):
                value = int(value * 65 / 100)
                edge = min(i, len(samples) - 1 - i)
                if edge < 176:
                    value = int(value * edge / 176)
                mixed.extend(struct.pack('<h', value))
            hash_value = 14695981039346656037
            for byte in mixed:
                hash_value = ((hash_value ^ byte) * 1099511628211) & ((1 << 64) - 1)
            values = [value[0] / 32768 for value in struct.iter_unpack('<h', mixed)]
            rms = (sum(value * value for value in values) / len(values)) ** .5
            peak = max(map(abs, values))
            assert (.065 <= rms <= .09 and .48 < peak < .56 if name == 'big_drum' else rms >= .020 and .10 < peak < .35), (name, 'native instrument PCM level', rms, peak)
            print(f'Expected native {name}: RMS={rms:.4f} peak={peak:.3f}', flush=True)
            self.expected[name] = (len(mixed), f'{hash_value:016x}')

    def entries(self):
        with self.path.open() as source:
            source.seek(self.offset)
            lines = source.read(8192).splitlines()
            self.offset = source.tell()
        entries = []
        for line in lines:
            count, fingerprint, result = line.split()
            assert result == '0', ('SDL rejected queued audio', result)
            entries.append((int(count), fingerprint))
        return entries

    def expect(self, pad, context):
        entries = self.entries()
        assert entries == [self.expected[SOUNDS[pad]]], (context, SOUNDS[pad], 'actual queued PCM differs', entries)

    def silent(self, context):
        assert not self.entries(), (context, 'unexpected native sound')


def exercise_scene(desktop, probe, language, size):
    desktop.resize(*size)
    time.sleep(.8)
    label = f'{language}-{size[0]}x{size[1]}'
    picture = desktop.capture_actual(label)
    assert_room(picture, size, language)
    assert_supports(picture, size)
    probe.entries()
    for pad in range(8):
        time.sleep(.8)
        before = desktop.capture_actual('before')
        desktop.click_actual(*body_point(size, pad))
        after = desktop.capture_actual('after')
        probe.expect(pad, (label, 'pointer'))
        assert changed(before.crop(art_box(size, pad)), after.crop(art_box(size, pad))), (label, pad, 'no local hit feedback')
        # Click focus must also operate through the host's semantic keyboard
        # path. Tab and Shift+Tab make that focus visible on native providers.
        desktop.key('Tab'); desktop.key('Shift+Tab')
        for action in ('space', 'Return'):
            time.sleep(.8)
            desktop.key(action)
            probe.expect(pad, (label, action))
    time.sleep(.8)
    # Each transparent corner and the empty wall are harmless. They must
    # not merely play too quietly to notice.
    for pad, (x, y, edge) in enumerate(instruments(size)):
        desktop.click_actual(*actual_point(size, x + 1, y + 1))
        probe.silent((label, pad, 'transparent corner'))
    desktop.click_actual(*actual_point(size, geometry(*size)[1] - 15, 130))
    probe.silent((label, 'empty wall'))
    # The sound button stays in the host's shared titlebar in every locale.
    desktop.click_actual(size[0] - 34, 28)
    assert (desktop.data / 'sound.txt').read_text().strip() == 'off'
    for pad in range(8):
        desktop.click_actual(*body_point(size, pad))
        probe.silent((label, pad, 'muted instrument'))
    desktop.click_actual(size[0] - 34, 28)
    assert (desktop.data / 'sound.txt').read_text().strip() == 'quiet'
    desktop.click_actual(*body_point(size, 7))
    probe.expect(7, (label, 'unmuted'))
    if language == 'en' and size[0] > size[1]:
        exercise_shake(desktop, probe, size)
    time.sleep(.8)
    print(f'local native room scene: {label}; eight pointer/Space/Enter routes, alpha misses, mute and unmute passed', flush=True)
    return picture


def assert_supports(picture, size):
    def near(x, y, expected, tolerance=65):
        color = picture.getpixel(actual_point(size, x, y))
        assert sum(abs(a - b) for a, b in zip(color, expected)) < tolerance, ('support pixel', x, y, color, expected)
    for pad in (2, 3):
        x, y, edge = instruments(size)[pad]
        base = 95 if pad == 3 else 91
        shelf_y = y + edge * base // 100
        width = edge * 8 // 10 + 10
        height = width // 3
        left = x + edge // 10 - 5
        top = shelf_y - height * 140 // 724
        a = actual_point(size, left, top)
        b = actual_point(size, left + width, top + height)
        observed = picture.crop((*a, *b)).convert('RGB')
        with Image.open(rt.ROOT/'assets/drums/pictures/shelf.png') as asset:
            expected = asset.convert('RGBA').resize(observed.size, Image.Resampling.LANCZOS)
        errors = []
        for py in range(expected.height//2, expected.height):
            for px in range(expected.width):
                rgba = expected.getpixel((px,py))
                if rgba[3] > 250:
                    errors.append(sum(abs(a-b) for a,b in zip(observed.getpixel((px,py)),rgba[:3]))/3)
        assert len(errors) >= 2 and sum(errors)/len(errors) < 38, ('painted shelf brackets missing or mismatched',pad,errors)
    x, y, edge = instruments(size)[5]
    gx, gy = x + edge // 2, y + edge * 96 // 100
    # Splayed feet are outside the guitar body, visibly supporting it.
    visible_feet = 0
    for direction in (-1, 1):
        px = gx + direction * (edge * 30 // 128)
        py = gy - edge * 35 // 100 + edge * 30 // 90 + 2
        covered = False
        for pad in (6, 7):
            ox,oy,oe = instruments(size)[pad]
            if not (ox <= px < ox+oe and oy <= py < oy+oe): continue
            with Image.open(rt.ROOT/'assets/drums/pictures'/f'{PICTURES[pad]}.png') as asset:
                asset=asset.convert('RGBA')
                sx=min(asset.width-1,int((px-ox)*asset.width/oe))
                sy=min(asset.height-1,int((py-oy)*asset.height/oe))
                if pad==7: sx=asset.width-1-sx
                covered |= asset.getpixel((sx,sy))[3]>120
        if covered: continue  # A nearer floor instrument can cover one stand foot.
        near(px, py, (102,94,80));visible_feet+=1
    assert visible_feet >= 1, 'guitar stand has no visible supporting foot'
    assert instruments(size)[5][2] > instruments(size)[0][2] * 1.4
    assert instruments(size)[2][2] < instruments(size)[0][2] * .4


def exercise_shake(desktop, probe, size):
    # Bypass the normal screenshot helper's .25s settling delay: this is a
    # real rendered animation lasting only .30s, on this harness's own Xvfb.
    desktop.verify_server()
    class XImage(ctypes.Structure):
        _fields_ = [('width', ctypes.c_int), ('height', ctypes.c_int),
                   ('xoffset', ctypes.c_int), ('format', ctypes.c_int),
                   ('data', ctypes.c_void_p), ('byte_order', ctypes.c_int),
                   ('bitmap_unit', ctypes.c_int), ('bitmap_bit_order', ctypes.c_int),
                   ('bitmap_pad', ctypes.c_int), ('depth', ctypes.c_int),
                   ('bytes_per_line', ctypes.c_int), ('bits_per_pixel', ctypes.c_int)]
    xlib = ctypes.CDLL('libX11.so.6')
    xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    xlib.XOpenDisplay.restype = ctypes.c_void_p
    xlib.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                              ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int]
    xlib.XGetImage.restype = ctypes.POINTER(XImage)
    xlib.XDestroyImage.argtypes = [ctypes.POINTER(XImage)]
    xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = xlib.XOpenDisplay(desktop.env['DISPLAY'].encode())
    assert display
    def frame():
        # Read only our verified app window, avoiding process launch delays
        # that can miss a complete 300ms animation under software rendering.
        native = xlib.XGetImage(display, int(desktop.window), 0, 0, *size, ctypes.c_ulong(-1).value, 2)
        assert native
        try:
            info = native.contents
            assert info.bits_per_pixel == 32 and info.byte_order == 0
            raw = ctypes.string_at(info.data, info.bytes_per_line * info.height)
            return Image.frombytes('RGB', size, raw, 'raw', 'BGRX', info.bytes_per_line)
        finally:
            xlib.XDestroyImage(native)
    time.sleep(.8)
    before = frame()
    x, y, edge = instruments(size)[7]
    with Image.open(rt.ROOT / 'assets/drums/pictures/tambourine.png') as im:
        alpha = im.convert('RGBA').getchannel('A')
    points = []
    for py in range(25, 75, 5):
        for px in range(20, 80, 5):
            if alpha.getpixel((px * alpha.width // 100, py * alpha.height // 100)) > 250:
                points.append(actual_point(size, x + edge * px / 100, y + edge * py / 100))
    assert len(points) > 20, 'tambourine tracking mask has no interior points'
    px, py = body_point(size, 7)
    probe.entries()
    rt.run(['xdotool', 'mousemove', '--window', desktop.window, str(px), str(py), 'mousedown', '1'], desktop.env)
    time.sleep(.04)
    rt.run(['xdotool', 'mouseup', '1'], desktop.env)
    frames = []
    for _ in range(20):
        time.sleep(.02)
        frames.append(frame())
    probe.expect(7, 'anchored shake')
    radius = max(3, round(3 * geometry(*size)[0]))
    moved = []
    for im in frames:
        candidates = []
        for dy in range(-2, 3):
            for dx in range(-radius, radius + 1):
                error = sum(sum(abs(a - b) for a, b in zip(before.getpixel((px, py)), im.getpixel((px + dx, py + dy)))) for px, py in points)
                candidates.append((error, abs(dx) + abs(dy), dx, dy))
        _, _, dx, dy = min(candidates)
        assert dy == 0, ('tambourine lifted from ground', dx, dy)
        moved.append(dx)
    assert any(moved), ('tambourine did not shake', moved)
    time.sleep(.8)
    settled = frame()
    assert before.crop(art_box(size, 7)) == settled.crop(art_box(size, 7)), 'tambourine failed to settle exactly'
    # Anchor/shadow below the opaque base stays fixed across animation.
    a = actual_point(size, x + edge * .25, y + edge * .86 + 3)
    b = actual_point(size, x + edge * .75, y + edge * .86 + 6)
    moving_frames = [im for im, dx in zip(frames, moved) if dx]
    assert all(im.crop((*a, *b)) == moving_frames[0].crop((*a, *b)) for im in moving_frames[1:]), 'ground shadow moved'
    xlib.XCloseDisplay(display)
    print(f'local tambourine animation: shifts={sorted(set(moved))}, horizontal motion <=3 logical pixels, fixed ground, clean settle passed', flush=True)


def inspect_scene(desktop, probe, language, size):
    """Targeted rerun for decoration changes; hit bounds/audio stay unchanged."""
    desktop.resize(*size)
    time.sleep(.8)
    picture = desktop.capture_actual(f'visual-{language}-{size[0]}x{size[1]}')
    assert_room(picture, size, language)
    assert_supports(picture, size)
    probe.entries()
    for pad in range(8):
        desktop.click_actual(*body_point(size, pad))
        probe.expect(pad, (language, size, 'targeted pointer'))
        if language == 'en' and size[0] > size[1]:
            desktop.key('Tab'); desktop.key('Shift+Tab')
            for action in ('space', 'Return'):
                desktop.key(action)
                probe.expect(pad, (language, size, 'targeted new-level ' + action))
    if language == 'en' and size[0] > size[1]:
        exercise_shake(desktop, probe, size)
        desktop.click_actual(size[0] - 34, 28)
        for pad in range(8):
            desktop.click_actual(*body_point(size, pad))
            probe.silent(('targeted new-level mute', pad))
        desktop.click_actual(size[0] - 34, 28)
        desktop.click_actual(*body_point(size, 7))
        probe.expect(7, 'targeted new-level unmute')
        print('local targeted native level: 8 Space/Enter routes and mute/unmute passed', flush=True)
    print(f'local targeted room scene: {language} {size}; pictures, labels and 8 native sound routes passed', flush=True)
    return picture


def wait_copy_turn(desktop, probe, size):
    # Observe the actual phase instead of racing the automatic demonstration.
    scale, width, *_ = geometry(*size)
    path = probe.path.parent / 'copy-prompt.png'
    deadline = time.monotonic() + 25
    prompt = ''
    while time.monotonic() < deadline:
        image = desktop.capture_actual('copy-phase')
        image.crop((round(16 * scale), round(56 + 58 * scale),
                    round((width - 16) * scale), round(56 + 86 * scale))).save(path)
        result = subprocess.run(['tesseract', str(path), 'stdout', '--psm', '7'],
                                check=True, capture_output=True, text=True, timeout=10)
        prompt = re.sub('[^a-z]', '', result.stdout.lower())
        if prompt == 'yourturn':
            return
        time.sleep(.1)
    raise AssertionError(('copy did not reach the response phase', prompt))


def exercise_copy(desktop, probe, save, size, replay_delay=0):
    # Finish the muted automatic demonstration before unmuting. Otherwise its
    # first note can race the Replay click and be counted as part of Replay.
    _, width, height, *_ = geometry(*size)
    desktop.click_actual(size[0] - 34, 28)
    desktop.click_actual(*actual_point(size, width * 3 // 4, 30))
    assert save.read_text() == 'drums 1 5 1\n', 'copy reset legacy progress'
    wait_copy_turn(desktop, probe, size)
    desktop.click_actual(size[0] - 34, 28)
    probe.entries()
    time.sleep(replay_delay)
    desktop.click_actual(*actual_point(size, 60, height - 40))
    # Five demo notes followed by the final full quiet gap; timing is allowed
    # to slow down under Xvfb, but never to skip or duplicate an emission.
    entries = probe.entries()
    deadline = time.monotonic() + 15
    while len(entries) < 5 and time.monotonic() < deadline:
        time.sleep(.1)
        entries += probe.entries()
    assert len(entries) == 5, ('copy demo did not emit five notes', entries)
    reverse = {value: pad for pad, name in enumerate(SOUNDS) for value in [probe.expected[name]]}
    assert all(entry in reverse for entry in entries), ('copy queued non-instrument PCM', entries)
    pattern = [reverse[entry] for entry in entries]
    wait_copy_turn(desktop, probe, size)
    probe.silent('copy demonstration finished before response')
    for pad in pattern:
        desktop.click_actual(*body_point(size, pad, copying=True))
        probe.expect(pad, 'copy response')
    assert save.read_text() == 'drums 1 5 2\n', 'copy success did not persist wins'
    # Next keeps the existing maximum length and consumes the two wins.
    desktop.click_actual(*actual_point(size, width - 60, height - 40))
    assert save.read_text() == 'drums 1 5 0\n', 'next pattern lost progression'
    desktop.click_actual(*actual_point(size, width // 4, 30))
    probe.entries()
    desktop.click_actual(*body_point(size, 4))
    probe.expect(4, 'return to Free Play')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--audio-only', action='store_true')
    parser.add_argument('--binary', type=Path, default=rt.ROOT / 'build/app/jungle')
    parser.add_argument('--copy-only', action='store_true', help='exercise the copy response with delayed Replay input')
    parser.add_argument('--visual-only', action='store_true', help='targeted scene/8-pointer rerun after decoration-only changes')
    parser.add_argument('--keep-preview', action='store_true', help='keep one scene PNG for a final visual review; caller removes them')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('music_room_audio', rt.ROOT / 'tools/music_room_audio.py')
    audio = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audio)
    audio.validate()
    for path, expected in PRESERVED.items():
        assert hashlib.sha256((rt.ROOT / path).read_bytes()).hexdigest() == expected, (path, 'original bytes changed')
    for (language, cue), text in VOICE_TEXT.items():
        path = rt.ROOT / 'assets/drums/sounds' / language / (cue + '.wav')
        receipt = json.loads(path.with_suffix('.speech.json').read_text())
        assert receipt['text'] == text and receipt['speed'] == 1.0, (path, 'natural-speed words changed')
        assert hashlib.sha256(path.read_bytes()).hexdigest() == receipt['sha256'], (path, 'voice provenance differs')
        with wave.open(str(path), 'rb') as clip:
            assert (clip.getnchannels(), clip.getsampwidth(), clip.getframerate()) == (1, 2, 22050)
            assert abs(clip.getnframes() / clip.getframerate() - receipt['duration']) < 1 / 22050
    source = (rt.ROOT / 'games/drums/jungle_drums.zi').read_text()
    routes = re.search(r'drums_sounds:.*?= \.\[(.*?)\];', source, re.S)[1]
    assert tuple(re.findall(r'"([a-z_]+)"', routes)) == SOUNDS
    assert '"Hear"' not in source and 'Tap and make music' not in source
    work = rt.ROOT / 'work'
    work.mkdir(exist_ok=True)
    assert subprocess.run(['git', 'check-ignore', '-q', str(work)], cwd=rt.ROOT).returncode == 0
    # Verify the exact expected native mixer levels even with --audio-only.
    with tempfile.TemporaryDirectory(prefix='drums-pcm-', dir=rt.ROOT / 'work') as directory:
        NativeAudio(Path(directory), audio)
    if args.audio_only:
        return
    # This harness owns every save, probe, log, X display and image. Never
    # inherit desktop auth/session variables or write to the owner's saves.
    for name in ('xylophone', 'guitar', 'cymbal', 'tambourine'):
        text = re.search(r'DRUMS_' + name.upper() + r'_MASK: \[16\]u16 = \.\[(.*?)\];', MODEL, re.S)[1]
        actual_mask = [int(value.strip(), 16) for value in text.split(',') if value.strip()]
        with Image.open(rt.ROOT / 'assets/drums/pictures' / f'{name}.png') as image:
            alpha = image.convert('RGBA').getchannel('A').resize((16, 16), Image.Resampling.BOX)
        expected_mask = [sum(1 << (15 - x) for x in range(16) if alpha.getpixel((x, y)) > 20) for y in range(16)]
        assert actual_mask == expected_mask, (name, 'hit shape no longer follows actual picture')
    captures = {}
    if args.keep_preview:
        preview = work / 'drums-room-preview'
        preview.mkdir(exist_ok=True)
        capture_actual = rt.Desktop.capture_actual
        def capture_for_review(self, name):
            picture = capture_actual(self, name)
            picture.save(preview / 'current.png')
            return picture
        rt.Desktop.capture_actual = capture_for_review
    with tempfile.TemporaryDirectory(prefix='drums-room-test-', dir=work) as temporary:
        directory = Path(temporary)
        rt.OUTPUT = directory / 'captures'
        probe = NativeAudio(directory, audio)
        for language in ('en', 'de', 'es'):
            data = directory / language
            data.mkdir()
            (data / 'language.txt').write_text(language)
            save = data / 'games/jungle.drums/drums.txt'
            save.parent.mkdir(parents=True)
            save.write_text('drums 1 5 1\n')
            env = {'LD_PRELOAD': str(probe.library), 'JUNGLE_TEST_AUDIO_QUEUE': str(probe.path)}
            with rt.Desktop(args.binary.resolve(), data, extra_env=env, screen_size='1280x1100') as desktop:
                desktop.game(TITLE)
                # No unsolicited opening narration may block the first hit.
                probe.entries()
                if args.copy_only:
                    desktop.resize(960, 600)
                    exercise_copy(desktop, probe, save, (960, 600), replay_delay=.4)
                    print('local copy response: actual turn phase, delayed Replay and exact five-note PCM passed', flush=True)
                    return
                for size in ((400, 756), (960, 600)):
                    captures[language, size] = (inspect_scene if args.visual_only else exercise_scene)(desktop, probe, language, size)
                assert save.read_text() == 'drums 1 5 1\n', 'free hits changed legacy progress'
                if language == 'en' and not args.visual_only:
                    exercise_copy(desktop, probe, save, (960, 600))
                desktop.click_actual(28, 28)
                old = save.read_text()
                desktop.game(TITLE)
                desktop.resize(400, 756)
                probe.entries()
                desktop.click_actual(*body_point((400, 756), 5))
                probe.expect(5, (language, 'reopened directly playable'))
                assert save.read_text() == old, 'reopening changed progress'
        for size in ((400, 756), (960, 600)):
            assert changed(captures['en', size], captures['de', size]), ('German text missing', size)
            assert changed(captures['en', size], captures['es', size]), ('Spanish text missing', size)
        if args.keep_preview:
            preview = work / 'drums-room-preview'
            preview.mkdir(exist_ok=True)
            captures['en', (960, 600)].save(preview / 'current.png')
            print(f'Private scene previews for inspection: {preview}', flush=True)
    if args.visual_only:
        print('local targeted drums scene test: all 8 pictured bodies, labels and native PCM pointer routes in portrait/landscape EN/DE/ES passed', flush=True)
    else:
        print('local drums playground test: 8 pictured instruments; exact native PCM for pointer/Space/Enter; transparent misses; mute; old saves; Copy progression; portrait/landscape EN/DE/ES passed', flush=True)


if __name__ == '__main__':
    main()

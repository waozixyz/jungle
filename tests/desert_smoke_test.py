"""The Desert edge in the real app on an owned private Xvfb, both orientations.

Campus Desert sign -> the painted jungle edge with the guide and camel -> tap
the guide -> his speech bubble beside him in EN/DE/ES -> tap through every line
-> it closes -> the camel opens it too -> X and Escape close it -> Return
advances -> the Campus sign leads back. Captures stay in ignored backup/.
"""
import json
import os
from pathlib import Path
import tempfile
import time
from PIL import Image, ImageChops, ImageStat
import runtime_test as rt

SIZES = ((960, 600), (420, 900), (1080, 2340), (1280, 800))


def fit(view, w, h, contain=False):
    """host/jungle_title.zi TitleFit at the centered pan."""
    width, height = (1024, 1536) if 'width' in view else (1672, 941)
    scale = (min if contain else max)(w / width, h / height)
    return scale, (w - width * scale) / 2, (h - height * scale) / 2


def layout(w_units, h_units, anchor):
    """host/jungle_title.zi TitleDialogueLayout, in window units."""
    ax, ay, aw, ah = anchor
    bw = w_units - 12 if w_units < 200 else w_units - 24 if w_units < 340 else 300
    bh = 74
    x, y = ax + aw // 2 - bw // 2, ay - bh - 10
    if y < 40:
        y = ay + 8
        if ax - bw - 8 >= 6: x = ax - bw - 8
        elif ax + aw + 8 + bw <= w_units - 6: x = ax + aw + 8
        else: y = ay + ah + 10
    x = min(x, w_units - 6 - bw); x = max(x, 6)
    y = min(y, h_units - 8 - bh); y = max(y, 40)
    return (x, y, bw, bh), (x + 12, y + 6, bw - 44, bh - 20), (x + bw - 24, y + 6, 18, 18)


def difference(a, b, box):
    return max(ImageStat.Stat(ImageChops.difference(a.crop(box), b.crop(box))).mean)


def main():
    root = rt.ROOT
    scratch = root/'backup/desert-smoke'
    scratch.mkdir(parents=True, exist_ok=True)
    rt.OUTPUT = scratch/'captures'
    data = json.loads((root/'tools/title_hotspots.json').read_text())
    home = data['scenes'][0]
    campus = next(s for s in data['scenes'] if s['name'] == 'campus')
    desert = next(s for s in data['scenes'] if s['name'] == 'desert')
    lines = len(json.loads((root/'tools/title_dialogue.json').read_text())['dialogues'][0]['lines'])
    binary = Path(os.environ.get('JUNGLE_TEST_BINARY', root/'build/app/jungle'))
    campus_key = str(next(i + 1 for i, s in enumerate(home['hotspots']) if s['target'] == 'scene:campus'))
    for w, h in SIZES:
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            state = Path(folder)
            # One size plays the recorded lines through the dummy audio driver.
            (state/'sound.txt').write_text('on\n' if (w, h) == (960, 600) else 'off\n')
            (state/'guide.txt').write_text('seen\n')
            with rt.Desktop(binary, state, extra_env={'TMPDIR': str(state)}, screen_size='1400x2500') as d:
                def tap(x, y):
                    rt.run(['xdotool', 'mousemove', '--window', d.window, str(round(x)), str(round(y))], d.env)
                    time.sleep(.08)
                    rt.run(['xdotool', 'mousedown', '1'], d.env)
                    time.sleep(.12)
                    rt.run(['xdotool', 'mouseup', '1'], d.env)
                    time.sleep(.35)

                def hover(x, y):
                    rt.run(['xdotool', 'mousemove', '--window', d.window, str(round(x)), str(round(y))], d.env)
                    time.sleep(.3)

                def until(name, test, seconds=10):
                    deadline = time.monotonic() + seconds
                    while True:
                        picture = d.capture_actual(name)
                        if test(picture):
                            return picture
                        assert time.monotonic() < deadline, (w, h, name)
                        time.sleep(.15)

                d.resize(w, h)
                unit = rt.title_unit(w, h)
                w_units, h_units = int(w / unit), int(h / unit)
                view = desert['portrait'] if h > w else desert
                scale, ox, oy = fit(view, w, h)
                to_screen = lambda x, y: (ox + x * scale, oy + y * scale)
                by_id = {spot['id']: spot for spot in view['hotspots']}
                plate = Image.open(root/view['image']).convert('RGB').resize(
                    (round((1024 if h > w else 1672) * scale), round((1536 if h > w else 941) * scale)),
                    Image.Resampling.BILINEAR)
                sky = to_screen(*((700, 200) if h > w else (1350, 160)))
                bubbles = []
                for locale in range(3):
                    d.key('Home')
                    tap((21 + 34 * locale) * unit, 17 * unit)
                    d.key(campus_key)
                    time.sleep(.7)
                    campus_view = campus['portrait'] if h > w else campus
                    cs, cx, cy = fit(campus_view, w, h, contain=h > w)
                    sign = next(t for t in campus_view['hotspots'] if t['id'] == 'desert-path')
                    x, y, _, _ = sign['glow_rect']; bx, by, bw, bh = sign['sign']['label_rect']
                    hover(10 * unit, h - 10 * unit)
                    at_campus = d.capture_actual(f'{w}-{locale}-campus')
                    tap(cx + (x + bx + bw / 2) * cs, cy + (y + by + bh / 2) * cs)
                    # The painted Desert edge, not a notice: untouched sky and dunes match the plate.
                    hover(*sky)
                    box = tuple(round(v) for v in (*to_screen(*((560, 120) if h > w else (1180, 110))),
                                                   *to_screen(*((860, 360) if h > w else (1560, 330)))))
                    box = (max(box[0], 0), max(box[1], round(60 * unit)), min(box[2], w), min(box[3], h))
                    expected = plate.crop((box[0] - round(ox), box[1] - round(oy), box[2] - round(ox), box[3] - round(oy)))
                    rest = until(f'{w}-{locale}-desert', lambda p: max(ImageStat.Stat(ImageChops.difference(
                        p.crop(box).resize((32, 32)), expected.resize((32, 32)))).mean) < 10)
                    for ident in ('desert-guide', 'camel'):
                        gx, gy, gw, gh = by_id[ident]['glow_rect']
                        figure = tuple(round(v) for v in (*to_screen(gx + gw * .3, gy + gh * .3), *to_screen(gx + gw * .7, gy + gh * .7)))
                        ref = plate.crop((figure[0] - round(ox), figure[1] - round(oy), figure[2] - round(ox), figure[3] - round(oy)))
                        assert max(ImageStat.Stat(ImageChops.difference(rest.crop(figure), ref)).mean) > 12, (w, ident, 'layer missing')

                    def anchor(ident):
                        gx, gy, gw, gh = by_id[ident]['glow_rect']
                        return (int((ox + gx * scale) / unit), int((oy + gy * scale) / unit),
                                int(gw * scale / unit), int(gh * scale / unit))

                    def pixels(rect):
                        x, y, rw, rh = rect
                        return (round(x * unit), round(y * unit), round((x + rw) * unit), round((y + rh) * unit))

                    def opened(rect):
                        return lambda p: difference(p, rest, pixels(rect)) > 20

                    def closed(rect):
                        return lambda p: difference(p, rest, pixels(rect)) < 6

                    bubble, text, close = layout(w_units, h_units, anchor('desert-guide'))
                    gx, gy, gw, gh = by_id['desert-guide']['glow_rect']
                    # Beside the speaker, never a caption along the bottom edge.
                    assert bubble[1] + bubble[3] < (oy + (gy + gh) * scale) / unit, (w, h, bubble)
                    assert 6 <= bubble[0] and bubble[0] + bubble[2] <= w_units - 6 and bubble[1] >= 40
                    tap(*to_screen(gx + gw * .5, gy + gh * .3))
                    picture = until(f'{w}-{locale}-line0', opened(bubble))
                    words = picture.crop(pixels(text)).convert('L')
                    assert sum(words.histogram()[:110]) > 40, (w, locale, 'no bubble text')
                    bubbles.append(words)
                    page = words
                    for line in range(1, lines):
                        tap(*sky)
                        picture = until(f'{w}-{locale}-line{line}', lambda p: max(ImageStat.Stat(ImageChops.difference(
                            p.crop(pixels(text)).convert('L'), page)).mean) > 3)
                        page = picture.crop(pixels(text)).convert('L')
                    # The last tap closes it; the scene is unchanged underneath.
                    tap(*sky)
                    until(f'{w}-{locale}-closed', closed(bubble))
                    # The camel opens the same conversation, still spoken by the
                    # guide beside him; the X closes it.
                    camel_bubble, _, camel_close = bubble, text, close
                    cx_, cy_, cw_, ch_ = by_id['camel']['glow_rect']
                    tap(*to_screen(cx_ + cw_ * .7, cy_ + ch_ * .35))
                    until(f'{w}-{locale}-camel', opened(camel_bubble))
                    x, y, cw, ch = camel_close
                    tap((x + cw / 2) * unit, (y + ch / 2) * unit)
                    hover(*sky)
                    until(f'{w}-{locale}-camel-closed', closed(camel_bubble))
                    # Keyboard: Return advances, Escape closes only the bubble.
                    tap(*to_screen(gx + gw * .5, gy + gh * .3))
                    first = until(f'{w}-{locale}-key-open', opened(bubble)).crop(pixels(text)).convert('L')
                    d.key('Return')
                    until(f'{w}-{locale}-key-next', lambda p: max(ImageStat.Stat(ImageChops.difference(
                        p.crop(pixels(text)).convert('L'), first)).mean) > 3)
                    d.key('Escape')
                    hover(*sky)
                    until(f'{w}-{locale}-key-closed', closed(bubble))
                    assert difference(d.capture_actual(f'{w}-{locale}-still-desert'), rest, box) < 6, 'Escape left the Desert'
                    # The sideways Campus plank leads back.
                    sx, sy, _, _ = by_id['campus-path']['glow_rect']
                    bx, by, bw, bh = by_id['campus-path']['sign']['label_rect']
                    tap(*to_screen(sx + bx + bw / 2, sy + by + bh / 2))
                    hover(10 * unit, h - 10 * unit)
                    area = (10, round(60 * unit), w - 10, h - 10)
                    until(f'{w}-{locale}-back', lambda p: difference(p, at_campus, area) < 8)
                assert bubbles[0].tobytes() != bubbles[1].tobytes() != bubbles[2].tobytes(), 'one language for all'
                d.alive()
            print(f'local desert smoke: {w}x{h}, EN/DE/ES, guide and camel bubble, tap/X/Escape/Return, Campus return passed',
                  flush=True)


if __name__ == '__main__':
    main()

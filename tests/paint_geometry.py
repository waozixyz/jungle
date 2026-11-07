"""Coloring Book hit targets for private native UI tests. No numeric dependencies."""
import time

def scene_layout(desktop):
    """Scene content/viewport rectangles in window pixels at scroll zero."""
    width, total = desktop.actual_size
    height = max(300, total - 56)
    if total - 56 < 300:
        height = 500
    fit = max(1000, min(width * 1000 // 320, height * 1000 // 200))
    pad, top = 14 * fit // 1000 + 12, 12 * fit // 1000 + 12
    if width - pad * 2 > 1040:
        pad = (width - 1040) // 2
    gap = 6 if height < 440 else 10
    cols = 2 if width - pad * 2 < 600 else 3
    rows = 6 // cols
    tab_y = top + 30 + gap
    tab_cols = 2 if width - 2 * pad < 560 else 4
    tab_rows = (4 + tab_cols - 1) // tab_cols
    tab_w = (width - 2 * pad - gap * (tab_cols - 1)) // tab_cols
    grid_y = tab_y + tab_rows * (44 + gap) - gap
    footer_y = height - top - 44
    cw = (width - 2 * pad - gap * (cols - 1)) // cols
    available = (footer_y - gap - grid_y - gap * (rows - 1)) // rows
    ch = max(80, min(220, available))
    fw = (width - 2 * pad - 2 * gap) // 3
    grid_height = footer_y - gap - grid_y
    content_height = rows * (ch + gap) - gap
    viewport = (56 + grid_y, grid_height, width - pad * 2)
    return {
        'category': [(pad + i % tab_cols * (tab_w + gap), 56 + tab_y + i // tab_cols * (44 + gap), tab_w, 44)
                     for i in range(4)],
        'tile': [(pad + i % cols * (cw + gap), 56 + grid_y + i // cols * (ch + gap), cw, ch) for i in range(6)],
        'previous': [(pad, 56 + footer_y, fw, 44)],
        'next': [(width - pad - fw, 56 + footer_y, fw, 44)],
        'viewport': viewport,
        'scroll': {'max': max(0, content_height - grid_height),
                   'content_height': content_height},
        'page_scroll': {'max': max(0, 500 - (total - 56)) if total - 56 < 300 else 0,
                        'content_height': 500},
    }


def scene_click(desktop, kind='tile', index=0, scroll_offset=0):
    x, y, w, h = scene_layout(desktop)[kind][index]
    if kind == 'tile':
        y -= scroll_offset
        view_y, view_height, _ = scene_layout(desktop)['viewport']
        assert view_y <= y and y + h <= view_y + view_height, 'scene tile is not fully visible'
    desktop.click_actual(x + w // 2, y + h // 2)


def stencil_bounds(width, height):
    """Mirror of StencilPickerBounds in games/paint/paint_picker_layout.zi."""
    fit = max(1000, min(width * 1000 // 320, height * 1000 // 200))
    gap = 6 if height < 440 else 10
    pad, top = 14 * fit // 1000 + 12, 12 * fit // 1000 + 12
    usable = width - pad * 2
    tab_cols = 4 if usable >= 560 else 2
    tab_rows = (4 + tab_cols - 1) // tab_cols
    tab_y = top + 30 + gap
    tab_w = (usable - gap * (tab_cols - 1)) // tab_cols
    grid_y = tab_y + tab_rows * (44 + gap)
    footer_y = height - top - 44
    footer_w = min(240, (usable - gap * 2) // 3)
    grid_height = footer_y - gap - grid_y
    cols = max(2, min(8, (usable + gap) // (150 + gap)))
    if (usable - gap) // 2 < 120:
        cols = 1  # Too narrow for two tiles that hold any label at 12 px.
    card_w = (usable - gap * (cols - 1)) // cols
    rows = (grid_height + gap) // (120 + gap)
    if rows < 2:
        rows = (grid_height + gap) // (80 + gap)
    rows = max(1, min(4, rows))
    card_h = max(80, (grid_height - gap * (rows - 1)) // rows)
    content_height = rows * (card_h + gap) - gap
    return dict(pad=pad, top=top, gap=gap, tab_cols=tab_cols, tab_y=tab_y, tab_w=tab_w,
                grid_y=grid_y, grid_height=grid_height, footer_y=footer_y, footer_w=footer_w,
                cols=cols, rows=rows, capacity=cols * rows, card_w=card_w, card_h=card_h,
                content_height=content_height, scroll=content_height > grid_height)


def stencil_layout(desktop):
    """Stencil picker hit rectangles in actual window pixels at scroll zero."""
    width, total = desktop.actual_size
    height = total - 56 if total - 56 >= 300 else 500
    b = stencil_bounds(width, height)
    pad, gap, cols = b['pad'], b['gap'], b['cols']
    return {
        'category': [(pad + i % b['tab_cols'] * (b['tab_w'] + gap),
                      56 + b['tab_y'] + i // b['tab_cols'] * (44 + gap), b['tab_w'], 44) for i in range(4)],
        'tile': [(pad + i % cols * (b['card_w'] + gap), 56 + b['grid_y'] + i // cols * (b['card_h'] + gap),
                  b['card_w'], b['card_h']) for i in range(b['capacity'])],
        'previous': [(pad, 56 + b['footer_y'], b['footer_w'], 44)],
        'next': [(width - pad - b['footer_w'], 56 + b['footer_y'], b['footer_w'], 44)],
        'capacity': b['capacity'],
    }


def stencil_click(desktop, kind='tile', index=0):
    x, y, w, h = stencil_layout(desktop)[kind][index]
    desktop.click_actual(x + w / 2, y + h / 2)


def stencil_pick(desktop, position):
    """From a category's first page, open the page holding its item and tap it."""
    capacity = stencil_layout(desktop)['capacity']
    for _ in range(position // capacity):
        stencil_click(desktop, 'next')
    stencil_click(desktop, 'tile', position % capacity)


def stencil_order():
    """The generated catalog's picker order, category starts and category sizes."""
    import re
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / 'games/paint/paint_catalog.zi').read_text()
    array = lambda name: [int(v) for v in re.search(name + r':[^=]+=[^\[]*\[([^\]]+)', source)[1].split(',')]
    return tuple(array(n) for n in ('paint_stencil_order', 'paint_stencil_category_starts',
                                    'paint_stencil_category_counts'))


def stencil_catalog():
    """Category sizes and each category's final stencil (stable ID + 1, as saved)."""
    order, starts, counts = stencil_order()
    return counts, [order[start + count - 1] + 1 for start, count in zip(starts, counts)]


def stencil_position(index):
    """The category and category-relative picker position of stencil asset index."""
    order, starts, counts = stencil_order()
    at = order.index(index)
    category = max(c for c, start in enumerate(starts) if start <= at)
    return category, at - starts[category]


def label_fits(actual, rect):
    """A tile's label ink lies inside its 6 px text inset and is drawn at all."""
    x, y, w, h = rect
    ink = lambda px, py: sum(actual.getpixel((px, py))) < 360
    band = range(y + h - 40, y + h - 3)
    outside = [(px, py) for py in band for px in (*range(x + 3, x + 6), *range(x + w - 6, x + w - 3)) if ink(px, py)]
    inside = any(ink(px, py) for py in band for px in range(x + 6, x + w - 6))
    return not outside and inside


TOOL_COUNT = 11  # games/paint/dino_paint.zi


def paint_bounds(width, height, page=(960, 720)):
    """Mirror of PaintMainBounds (games/paint/paint_picker_layout.zi) for the
    game area below the game bar."""
    page_w, page_h = page
    shortest = min(width, height)
    pad = max(6, min(20, shortest // 40))
    gap = max(4, min(10, shortest // 80))
    l = dict(pad=pad, gap=gap, side=width >= height, compact=False)

    def fit(x, y, w, h):
        cw, ch = w, w * page_h // page_w
        if ch > h:
            ch, cw = h, h * page_w // page_h
        cw, ch = max(1, cw), max(1, ch)
        l.update(canvas=(x + (w - cw) // 2, y + (h - ch) // 2, cw, ch))

    if not l['side']:
        tw = (width - pad * 2 - gap * 2) // 3
        th = max(48, min(110, tw * 3 // 4))
        rows = (TOOL_COUNT + 2) // 3
        panel = rows * th + (rows - 1) * gap
        if (panel + pad) * 3 <= height:
            fit(pad, pad, width - pad * 2, height - pad * 3 - panel)
            cy, ch = l['canvas'][1], l['canvas'][3]
            l.update(columns=3, tool_w=tw, tool_h=th, tools_x=pad,
                     tools_y=cy + ch + pad + (height - pad - (cy + ch + pad) - panel) // 2)
            return l
    else:
        columns = 2 if height < 560 else 1
        rows = (TOOL_COUNT + columns - 1) // columns
        th = (height - pad * 2 - gap * (rows - 1)) // rows
        tw = max(64, min(th * 5 // 2, width // (8 if columns == 2 else 5)))
        rail = tw * columns + gap * (columns - 1)
        if th >= 48 and (rail + pad) * 3 <= width:
            fit(0, pad, width - pad * 3 - rail, height - pad * 2)
            _, cy, cw, ch = l['canvas']
            left = (width - rail - pad - cw) // 2
            l.update(canvas=(left + rail + pad, cy, cw, ch), columns=columns, tool_w=tw, tool_h=th,
                     tools_x=left, tools_y=max(pad, cy + (ch - th * rows - gap * (rows - 1)) // 2))
            return l
    # Compact: the picture keeps the room and the tools open from a drawer.
    l['compact'] = True
    bar = max(64, min(96, shortest // 5))
    rows = (TOOL_COUNT + 2) // 3
    if l['side']:
        l.update(bar=(pad, pad, bar, height - pad * 2), toggle=(pad, pad, bar, bar))
        fit(pad * 2 + bar, pad, width - pad * 3 - bar, height - pad * 2)
        drawer_x, drawer_y, drawer_h = pad * 2 + bar, pad, height - pad * 2
        th = max(1, min(110, (drawer_h - pad * 2 - gap * (rows - 1)) // rows))
        tw = max(1, min(th * 2, (width - drawer_x - pad * 3 - gap * 2) // 3))
    else:
        bar_y, bar_w = height - pad - bar, width - pad * 2
        l.update(bar=(pad, bar_y, bar_w, bar), toggle=(pad, bar_y, max(bar, min(bar_w // 2, bar * 2)), bar))
        fit(pad, pad, width - pad * 2, bar_y - pad * 2)
        drawer_x = 0
        tw = (width - pad * 2 - gap * 2) // 3
        th = max(56, min(110, tw * 3 // 4))
        drawer_y = max(0, bar_y - pad - (rows * th + (rows - 1) * gap + pad * 2))
    l.update(columns=3, tool_w=tw, tool_h=th, tools_x=drawer_x + pad, tools_y=drawer_y + pad)
    return l


def paint_main(desktop, page=(960, 720)):
    """The main screen's layout this window shows, in window pixels below the game bar."""
    width, height = desktop.actual_size
    return paint_bounds(width, height - 56, page)


def paint_layout(desktop, page=(960, 720)):
    """The picture rectangle below the game bar and every tool's center in window
    pixels (PaintToolRect); compact layouts show these tools once the drawer opens."""
    l = paint_main(desktop, page)
    tw, th, gap, columns = l['tool_w'], l['tool_h'], l['gap'], l['columns']
    tools = [(l['tools_x'] + i % columns * (tw + gap) + tw / 2, 56 + l['tools_y'] + i // columns * (th + gap) + th / 2)
             for i in range(TOOL_COUNT)]
    return l['canvas'], tools


def tool(desktop, index):
    """Taps a tool, opening the compact drawer first where the tools wait in it."""
    l = paint_main(desktop)
    if l['compact']:
        x, y, w, h = l['toggle']
        desktop.click_actual(x + w / 2, 56 + y + h / 2)
    desktop.click_actual(*paint_layout(desktop)[1][index])


def pixel_click(desktop, x, y):
    """Taps picture pixel x, y of the wide page at fit zoom."""
    left, top, width, height = paint_layout(desktop)[0]
    desktop.click_actual(left + (x + .5) * width / 960, 56 + top + (y + .5) * height / 720)


def placement_click(desktop, place=True):
    """Taps Place, or Cancel, below a pending stencil (PlacementView)."""
    x, y, w, h = paint_layout(desktop)[0]
    bw = max(44, min(140, (w - 18) // 2))
    left = x + (w - bw * 2 - 6) // 2
    desktop.click_actual(left + (bw + 6 if place else 0) + bw // 2, 56 + y + h - 26)


def open_slots(desktop):
    """Opens the gallery's save slots."""
    tool(desktop, 4)
    desktop.capture("paint-gallery", header=56)
    desktop.click(250, 38)
    desktop.capture("paint-slots", header=56)


def changed(path, before, timeout=10):
    """The file's new contents once they differ from BEFORE."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and path.read_bytes() != before:
            return path.read_bytes()
        time.sleep(.1)
    raise AssertionError(f"{path.name} did not change")

"""Responsive scene-picker hit targets for private native UI tests. No numeric dependencies."""

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
    tab_w = (width - 2 * pad - 2 * gap) // 3
    grid_y = tab_y + 44 + gap
    footer_y = height - top - 44
    cw = (width - 2 * pad - gap * (cols - 1)) // cols
    available = (footer_y - gap - grid_y - gap * (rows - 1)) // rows
    ch = max(80, min(220, available))
    fw = (width - 2 * pad - 2 * gap) // 3
    grid_height = footer_y - gap - grid_y
    content_height = rows * (ch + gap) - gap
    viewport = (56 + grid_y, grid_height, width - pad * 2)
    return {
        'category': [(pad + i * (tab_w + gap), 56 + tab_y, tab_w, 44) for i in range(3)],
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

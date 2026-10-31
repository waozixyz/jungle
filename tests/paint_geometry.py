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

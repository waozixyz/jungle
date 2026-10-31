"""Responsive scene-picker hit targets for private native UI tests. No numeric dependencies."""

def scene_layout(desktop):
    """Scene rectangles in window pixels; six stable slots at every width."""
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
    ch = max(80, min(220, (footer_y - gap - grid_y - gap * (rows - 1)) // rows))
    fw = (width - 2 * pad - 2 * gap) // 3
    return {
        'category': [(pad + i * (tab_w + gap), 56 + tab_y, tab_w, 44) for i in range(3)],
        'tile': [(pad + i % cols * (cw + gap), 56 + grid_y + i // cols * (ch + gap), cw, ch) for i in range(6)],
        'previous': [(pad, 56 + footer_y, fw, 44)],
        'next': [(width - pad - fw, 56 + footer_y, fw, 44)],
    }


def scene_click(desktop, kind='tile', index=0):
    x, y, w, h = scene_layout(desktop)[kind][index]
    desktop.click_actual(x + w // 2, y + h // 2)

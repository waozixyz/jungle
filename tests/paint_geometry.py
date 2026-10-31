"""Responsive scene-picker hit targets for private native UI tests. No numeric dependencies."""

def scene_layout(desktop):
    """Scene rectangles in window pixels; six stable slots at every width."""
    width, total = desktop.actual_size
    height = max(300, total - 56)
    if total - 56 < 300:
        height = 500
    pad, gap = (8, 6) if height < 440 else (16, 10)
    cols = 2 if width < 600 else 3
    rows = 6 // cols
    tab_y = pad + 30 + gap
    tab_w = (width - 2 * pad - 2 * gap) // 3
    grid_y = tab_y + 44 + gap
    footer_y = height - pad - 44
    cw = (width - 2 * pad - gap * (cols - 1)) // cols
    ch = max(80, (footer_y - gap - grid_y - gap * (rows - 1)) // rows)
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

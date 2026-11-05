"""Shipped pictures' design sizes. The owner's 75% standard ships a Lanczos
copy at 75% of the painting (tools/image_exports.py); layout, hotspots and
tests reason in the painting's own pixels, recorded in canonical_avif.json."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_ROWS = None


def _rows():
    global _ROWS
    if _ROWS is None:
        _ROWS = json.loads((ROOT/'tools/canonical_avif.json').read_text())['files']
    return _ROWS


def design_size(path, image=None):
    """The painting size of shipped PATH (absolute or repo-relative)."""
    path = Path(path)
    name = (path.relative_to(ROOT) if path.is_absolute() else path).as_posix()
    row = _rows().get(name)
    if row is None:
        return tuple(image.size) if image is not None else None
    return tuple(row.get('design_dimensions', row['dimensions']))

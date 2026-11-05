"""Compose the game awards from their ignored masters and export runtime AVIF.

Each award is the shared painted badge (local/art-development/awards/badge.png)
with its game's emblem (emblems/<name>.png) centered in the badge's cream
circle. The full-resolution compositions stay in composed/; the runtime badges
are exact lossless 384 px AVIF in assets/jungle/awards/, recorded with their
hashes in tools/art_provenance/game-awards.json. Builds need only the AVIF.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from image_exports import optimize_new_image_exports  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MASTERS = ROOT / 'local/art-development/awards'
RUNTIME = ROOT / 'assets/jungle/awards'
PROVENANCE = ROOT / 'tools/art_provenance/game-awards.json'
CACHE = ROOT / 'work/award-art-cache'
# The established runtime size: the celebration shows a badge at most 320 px.
RUNTIME_SIZE = (384, 384)
# The badge's empty cream circle, measured on the master and normalized.
CIRCLE_X, CIRCLE_Y, CIRCLE_RADIUS = 0.49, 0.47, 0.29
# In catalog order: each game's award, with the emblem it carries.
AWARDS = (
    ('jungle-book.zx', 'picture-book', 'An open picture book with a leaf bookmark'),
    ('jungle-abc.zx', 'abc', 'A wooden letter A block'),
    ('jungle-numbers.zx', '123', 'Wooden 1 2 3 blocks'),
    ('animal-count.zx', 'counting', 'A wooden abacus'),
    ('dino-paint.zx', 'coloring', 'A paint palette and brush'),
    ('jungle-jigsaw.zx', 'jigsaw', 'A green puzzle piece'),
    ('jungle-piano.zx', 'piano', 'A toy piano and a music note'),
    ('jungle-shapes.zx', 'shapes', 'A circle, square and triangle'),
    ('jungle-matching.zx', 'matching', 'Two matching butterfly cards'),
    ('jungle-hide-seek.zx', 'hide-seek', 'A bunny peeking from a bush'),
    ('jungle-drums.zx', 'music', 'Two maracas'),
    ('jungle-garden.zx', 'farm', 'A watering can and a seedling'),
    ('jungle-fishing.zx', 'fishing', 'A little sailboat'),
    ('jungle-beach-families.zx', 'beach', 'A seashell and a starfish'),
)


def digest(path: Path) -> str:
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def solid(picture: Image.Image) -> Image.Image:
    """PICTURE with the generator's nearly opaque paint (alpha 248-254) made
    fully opaque, so nothing behind a badge shows faintly through it."""
    picture = picture.copy()
    picture.putalpha(picture.getchannel('A').point(lambda value: 255 if value >= 248 else value))
    return picture


def compose(badge: Image.Image, emblem: Image.Image) -> Image.Image:
    """EMBLEM, trimmed to its painted pixels, centered in BADGE's circle."""
    badge, emblem = solid(badge), solid(emblem)
    box = emblem.getchannel('A').point(lambda value: 255 if value > 8 else 0).getbbox()
    if box is None:
        raise ValueError('emblem is empty')
    emblem = emblem.crop(box)
    width, height = badge.size
    radius = CIRCLE_RADIUS * width
    diagonal = (emblem.width ** 2 + emblem.height ** 2) ** 0.5
    scale = min(2.0 * radius * 0.9 / diagonal, 2.0 * radius * 0.8 / emblem.width, 2.0 * radius * 0.8 / emblem.height)
    size = (max(1, round(emblem.width * scale)), max(1, round(emblem.height * scale)))
    emblem = emblem.resize(size, Image.Resampling.LANCZOS)
    result = badge.copy()
    result.alpha_composite(emblem, (round(CIRCLE_X * width - size[0] / 2), round(CIRCLE_Y * height - size[1] / 2)))
    return result


def build() -> int:
    badge_path = MASTERS / 'badge.png'
    badge = Image.open(badge_path).convert('RGBA')
    (MASTERS / 'composed').mkdir(parents=True, exist_ok=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    records = []
    for bundle, name, emblem_text in AWARDS:
        emblem_path = MASTERS / 'emblems' / f'{name}.png'
        composed = MASTERS / 'composed' / f'{name}.png'
        compose(badge, Image.open(emblem_path).convert('RGBA')).save(composed)
        export = optimize_new_image_exports(composed, 'cutout', CACHE, size=RUNTIME_SIZE)
        runtime = RUNTIME / f'{name}.avif'
        shutil.copyfile(export.source, runtime)
        records.append({'game': bundle, 'award': f'award-{name}', 'emblem': emblem_text,
                        'emblem_master': emblem_path.relative_to(ROOT).as_posix(), 'emblem_sha256': digest(emblem_path),
                        'master': composed.relative_to(ROOT).as_posix(), 'master_sha256': digest(composed),
                        'runtime': runtime.relative_to(ROOT).as_posix(), 'sha256': digest(export.source),
                        'size': list(RUNTIME_SIZE)})
    provenance = {
        'owner_request': 'Each game we unlock should give us some award automatically.',
        'generator': 'Harmony generate_image (Codex built-in image generation); original Jungle watercolor',
        'style_reference': 'local/art-development/title-covers.png',
        'method': 'one shared empty badge and one transparent emblem per game, each generated alone; '
                  'tools/award_art.py centers the emblem in the badge circle and exports exact lossless AVIF',
        'badge_master': badge_path.relative_to(ROOT).as_posix(), 'badge_sha256': digest(badge_path),
        'prompts': 'local/art-development/awards/prompts.json',
        'awards': records,
    }
    PROVENANCE.write_text(json.dumps(provenance, indent=2) + '\n')
    return 0


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    return build()


if __name__ == '__main__':
    raise SystemExit(main())

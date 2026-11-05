"""Shared, bounded AVIF encoder. libavif's avifenc is an export-time tool.

Opaque paintings use the reviewed q35 tier at their original dimensions.
Cut-outs and layers keep every alpha value exactly (lossless alpha plane) with
high-quality 4:4:4 color, far smaller than lossless AVIF. Jigsaw paintings use q60 4:4:4 so fine puzzle detail keeps its color.
Only explicitly exact
artwork uses identity-matrix 4:4:4 lossless. No premultiplication or resize.
"""
from functools import lru_cache
import os
from pathlib import Path
import subprocess
import tempfile

QUALITY = 35
CUTOUT_QUALITY = 70
SPEED = 6


def has_alpha(picture):
    return picture.mode in ('RGBA', 'LA') and picture.getchannel('A').getextrema()[0] < 255


@lru_cache(maxsize=1)
def encoder_version():
    return subprocess.check_output([os.environ.get('AVIFENC', 'avifenc'), '--version'],
                                   text=True).strip()


def save_avif(picture, destination, *, lossless=False, quality=QUALITY, exact=False,
              cutout_quality=CUTOUT_QUALITY, alpha_quality=100, subsampling='420'):
    """LOSSLESS on a transparent picture means exact alpha with q70 4:4:4 color;
    EXACT (or an opaque LOSSLESS picture) keeps every RGB and alpha value."""
    destination = Path(destination)
    cutout = lossless and not exact and has_alpha(picture)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Keep intermediate pixels beside the owned output, never in global /tmp.
    with tempfile.TemporaryDirectory(prefix='avif-', dir=destination.parent) as folder:
        source = Path(folder) / 'input.png'
        output = Path(folder) / 'output.avif'
        picture.save(source, 'PNG', **({'icc_profile': picture.info['icc_profile']}
                                    if picture.info.get('icc_profile') else {}))
        command = [os.environ.get('AVIFENC', 'avifenc'), '--jobs', '1', '--speed', str(SPEED),
                   '--depth', '8', '--range', 'full',
                   '--qalpha', str(alpha_quality if cutout else 100)]
        if cutout:
            command += ['--qcolor', str(cutout_quality), '--yuv', '444', '--cicp', '1/13/6']
        elif lossless or exact:
            command += ['--lossless', '--yuv', '444', '--cicp', '1/13/0']
        else:
            command += ['--qcolor', str(quality), '--yuv', subsampling, '--cicp', '1/13/6']
        subprocess.run(command + [str(source), str(output)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        output.replace(destination)


@lru_cache(maxsize=1)
def _recorded_rows():
    import json
    receipt = Path(__file__).resolve().parents[1] / 'tools/canonical_avif.json'
    return json.loads(receipt.read_text())['files'] if receipt.exists() else {}


def save_shipped_cutout(picture, destination, name):
    """Encode generated transparent art (glows, layers) for shipped path NAME with
    the color/alpha quality its canonical_avif.json row records, so authoring
    tools reproduce the exact bytes that keep it smaller than its source."""
    row = _recorded_rows().get(name)
    if row and row.get('scale'):
        # Owner's 75% standard: authoring tools draw at painting size.
        from image_exports import save_scaled
        save_scaled(picture, destination)
        return
    settings = {}
    if row and row['alpha'] and not row['lossless']:
        settings = dict(cutout_quality=row['quality'], alpha_quality=row.get('alpha_quality', 100))
    save_avif(picture, destination, lossless=True, **settings)

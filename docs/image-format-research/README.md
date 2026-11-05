# Jungle image-format research

This folder records the original pre-migration comparison. Jungle now ships
AVIF at full dimensions, with exact lossless cutouts; see README.md and
`tools/canonical_avif.json` for the shipping policy. The shown 75% tier is
research evidence, not the final full-dimension migration setting. Generated bitstreams, model files, metrics,
and before/after cards are intentionally kept under the ignored
`local/image-format-research/` directory.

## Results

- Open `local/image-format-research/comparison.html` for the six before/after
  cards and all 90 sample measurements.
- Open `local/image-format-research/metrics/benchmark.csv` for raw codec metrics.
- Open `local/image-format-research/inventory/inventory-projection.csv` for the
  full 1,177-file AVIF inventory projection.
- Read [REPORT.md](REPORT.md) for the format/model comparison and recommendation.

## Reproduce

The scripts depend on system `magick` and `ffmpeg`, plus the Python packages
listed below. The benchmark downloads Qualcomm's BSD-3-Clause QuickSRNet Small
export and stores it only in the ignored local research directory.

```sh
python3 -m venv local/image-format-research/.venv
local/image-format-research/.venv/bin/pip install \
  'Pillow==12.3.0' 'numpy==2.2.4' 'scipy==1.15.3' 'onnxruntime==1.23.2'
local/image-format-research/.venv/bin/python docs/image-format-research/run_benchmark.py
python3 docs/image-format-research/project_inventory.py
```

`run_benchmark.py` measures current WebP, AVIF, JPEG XL, HEIC, lower-resolution
decoding plus Lanczos restoration, and a quarter-resolution QuickSRNet path.
`project_inventory.py` measures AVIF q35 at 100%, 75%, 50%, and 25% dimensions
for every WebP currently under `assets/`.

These scripts preserve the historical WebP benchmark and its original source
paths. After migration, its WebP inputs live under ignored
`backup/avif-migration/assets/`; they are not shipping artwork. Replaying this
research requires those archived inputs. Use `tools/image_exports.py` for
current AVIF exports and `tests/canonical_avif_test.py` for the current inventory.

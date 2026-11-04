# Jungle WebP compression and CPU enhancement research

Date: 2026-11-04  
Scope: research and local comparison only; no Jungle runtime assets or code were changed.

## Executive result

Jungle currently has **1,177 WebP files totaling 309.199 MiB**. The strongest
measured solution is:

> **AVIF quality 35, stored at 75% of runtime dimensions, decoded and restored
> to full size with Lanczos.**

Across every current WebP, that tier is **30.694 MiB, a 10.074× reduction
> (90.07% smaller)**. On six representative artwork classes its mean quality was
> **31.70 dB PSNR / 0.8968 SSIM**, versus **33.57 dB / 0.9229 SSIM** for
> full-resolution AVIF q35. This is the only tested uniform tier that clears the
> inventory-wide 10× target while retaining more fidelity than the 50% tier.

The experimental 25%-resolution QuickSRNet CPU model cleared the size target by
a wide margin but **did not consistently beat Lanczos** and often scored lower.
It is not recommended for Jungle in its exported form.

## Inventory-wide AVIF projection

Every current WebP was encoded with ImageMagick AVIF q35 at four scales. The
input files and generated outputs were not modified; all outputs are under
`local/image-format-research/inventory/`.

| Tier | Output size | Reduction | Savings | Interpretation |
|---|---:|---:|---:|---|
| 100% dimensions | 46.340 MiB | 6.672× | 85.01% | Best uniform fidelity, misses 10× |
| **75% dimensions** | **30.694 MiB** | **10.074×** | **90.07%** | **Meets target with least downsampling** |
| 50% dimensions | 16.889 MiB | 18.307× | 94.54% | Large extra quality penalty |
| 25% dimensions | 5.852 MiB | 52.840× | 98.11% | Research/model tier only; visibly fragile |

The bitstream split explains why this works: 519 files are lossless WebP
(109.500 MiB), mostly exact-alpha cut-outs/layers, while 658 are already lossy
(199.700 MiB). Lossless artwork has substantial headroom; already-compressed
pages/backgrounds constrain the full-resolution tier.

## Sample benchmark

`run_benchmark.py` tested six real Jungle cases:

- lossy full-scene book page (`tiger.webp`);
- exact-lossless alpha cut-out (`panda.webp`);
- q50 title background (`treehouse-background.webp`);
- lossless title animation frame (`portrait-frame.webp`);
- extreme-aspect animation strip (`portrait-leaves-3.webp`);
- flat vector-like scene (`sorter.webp`).

Averages across those cases were:

| Approach | Mean reduction | Mean PSNR | Mean SSIM | Verdict |
|---|---:|---:|---:|---|
| Full-res AVIF q50 | 18.55× | 36.56 dB | 0.9549 | High quality; misses target on already-lossy art |
| Full-res AVIF q35 | 33.97× | 33.57 dB | 0.9229 | Strong quality, but only 6.672× inventory-wide |
| **75% AVIF q35 + Lanczos** | **45.20×** | **31.70 dB** | **0.8968** | **Best target-meeting tradeoff** |
| 75% WebP q35 + Lanczos | 21.56× | 32.24 dB | 0.9066 | Better sample SSIM, but weaker compression |
| 50% AVIF q35 + Lanczos | 77.37× | 29.56 dB | 0.8516 | Useful only for low-detail layers after visual review |
| 25% AVIF q35 + Lanczos | 201.27× | 26.26 dB | 0.7508 | Too destructive for most full-screen artwork |
| 25% AVIF + QuickSRNet | 201.27× | 25.85 dB | 0.7451 | Model does not improve the measured frontier |
| 75% JPEG XL d2 + Lanczos | 10.88× | 34.81 dB | 0.9480 | Best measured fidelity, but fragile/poor size on some inputs |

Sample-specific values and all raw bitstreams are in
`local/image-format-research/metrics/benchmark.csv` and
`local/image-format-research/encoded/`.

## Codec findings

### AVIF

AVIF is the recommended format for further visual pilots. It supports alpha as
an auxiliary AV1 bitstream in the HEIF-based container
([AV1 Image File Format specification](https://aomediacodec.github.io/av1-avif/v1.2.0.html)).
AOMedia grants a no-charge, worldwide, royalty-free patent license for AV1
implementations under its patent license
([AOMedia Patent License 1.0](https://aomedia.org/license/patent/)).

Android's platform decoder supports 8-bit AVIF from Android 12, with optional
10-bit decoding; applications must query or test the device capability
([Android supported media formats](https://developer.android.com/media/platform/supported-formats)).
Jungle supports Android older than 12 (`droid/app/build.gradle:29`), and the USB
test Moto is Android 9 on `armeabi-v7a`. Therefore an AVIF rollout would need a
bundled native AVIF decoder plus a WebP fallback, or would need to raise the
minimum OS. Decoder speed and binary-size impact must be measured on that Moto
before implementation.

The local decoder averaged about 7.1 ms for 75%-scale representative files on
this desktop, but desktop decode timing is not a phone performance result.

### JPEG XL

JPEG XL has the best measured fidelity among the target-sized candidates. It
supports alpha, lossless, and progressive coding
([JPEG XL format overview](https://jpeg.org/jpegxl/)), and JPEG.org describes the
reference implementation as royalty-free
([JPEG XL software and licensing](https://jpeg.org/jpegxl/software.html)).
Chrome now ships JPEG XL decoding
([Chrome JPEG XL announcement](https://developer.chrome.com/blog/jpeg-xl-in-chrome/)),
but Android's platform image-format table does not provide a native JPEG XL
decoder. A native Jungle rollout would require bundling libjxl and preserving a
fallback. In this benchmark, FFmpeg/libjxl d2 was often much larger than AVIF
and made one already-low-bitrate title background larger than the source. It is
a quality fallback or archival format, not the best 10× runtime format.

### WebP lossy alpha

Staying with WebP avoids a new decoder and preserves the existing build. In the
sample test, 75% WebP q35 scored slightly higher SSIM than 75% AVIF q35, but its
reduction was much weaker and it still missed the target on already-compressed
full-screen artwork. This is the safest pilot format for selected exact-alpha
layers, but unlikely to deliver a robust 10× total by itself.

### HEIC/HEIF

HEIC q50 had the highest sample PSNR/SSIM but only 7.04× average reduction, a
more complicated patent/ecosystem story, and slower local decoding than AVIF.
Android exposes HEIF decoding, but support varies by profile and hardware. It is
not competitive here.

### Not recommended

- **WebP 2:** Google's libwebp2 repository says it is not finalized for general
  use and is an experiment rather than a released image format
  ([libwebp2 status](https://chromium.googlesource.com/codecs/libwebp2/)).
- **BPG/FLIF:** obsolete or nonstandard ecosystem and patent concerns.
- **QOI:** fast decoding, but normally much larger than modern lossy formats.
- **KTX2/Basis/ASTC:** useful for GPU-resident textures, but fixed-rate block
  compression does not approach the measured AVIF reduction for these still
  illustrations and requires a different rendering path.
- **ZIP/APK repacking or atlases:** compressed image bitstreams do not shrink
  again; atlases only remove per-file overhead and would complicate runtime
  loading.
- **Automatic raster-to-vector/SVG/Lottie conversion:** current converters are
  not reliable enough for watercolor artwork. Manual re-authoring of simple
  repeated shapes/window animations could exceed 10× and remain resolution
  independent, but it is an art project, not an automatic format conversion.

## Local enhancement models

### QuickSRNet Small

The exported Qualcomm model is deliberately small: 33.3K parameters, 133 KB
float ONNX, and a 128×128 RGB input with 512×512 output
([QuickSRNet Small model card](https://huggingface.co/qualcomm/QuickSRNetSmall)).
It has universal ONNX and TFLite exports, and Qualcomm describes it as designed
for mobile real-time sharpening. ONNX Runtime Mobile supports Android, CPU, and
the XNNPACK execution provider
([ONNX Runtime Mobile deployment](https://onnxruntime.ai/docs/tutorials/mobile/)).

The local test ran every 128×128 tile through CPU Execution Provider. Inference
took approximately 0.026–0.071 seconds per representative image on the desktop
CPU. It is architecturally plausible on a phone CPU, but this was **not** run on
the Moto and must not be treated as a phone-CPU performance result.

More importantly, quality did not justify deployment:

- on four of six samples, QuickSRNet scored lower PSNR and SSIM than plain
  Lanczos;
- its only small SSIM win was the title animation frame;
- it caused a large quality loss on the 7272×216 strip because fixed tiles are
  unsuitable for extreme aspect ratios;
- its 133 KB size does not include the ONNX/TFLite runtime or tiling/alpha code.

Therefore QuickSRNet Small is **phone-compatible in form, but not recommended**.
The 75% AVIF + Lanczos path needs no model runtime and already meets the target.

### Larger generative models

Real-ESRGAN anime/compact variants, SRVGGNetCompact, SwinIR-class models, and
similar restoration networks can look impressive on natural images or anime.
They are poor defaults for Jungle because:

- toddler artwork must remain faithful; generative models can alter eyes,
  outlines, and anatomy;
- full-screen inference is much heavier than the 33.3K-parameter QuickSRNet;
- many releases optimize GPU/Vulkan paths rather than low-end phone CPUs;
- transparent cut-outs need separate edge/alpha handling;
- caching restored images shifts storage cost back into the app.

Real-ESRGAN documents compact anime variants, but not a Jungle-phone CPU proof
([Real-ESRGAN model zoo](https://github.com/xinntao/Real-ESRGAN/blob/master/docs/model_zoo.md)).
If a model is revisited, train a Jungle-art-specific residual model and require
measured Moto CPU time, memory, visual before/afters, and no anatomy changes.

## Recommended next experiment

No Jungle behavior should change from this research. If the owner wants to
continue, use a staged visual pilot:

1. Select 20–30 images spanning book pages, exact-alpha cut-outs, title layers,
   extreme strips, awards, and small UI icons.
2. Generate only from source masters (not repeated lossy transcodes):
   full AVIF q35, 75% AVIF q35, 75% WebP q35, and current WebP.
3. Present same-size before/after cards and 1:1 crops, including zoomed alpha
   edges, eyes, hands/paws, text, and the 7272×216 strips.
4. Require owner approval per asset family. Keep current WebP as fallback.
5. Measure a bundled AVIF decoder on the Android 9 `armeabi-v7a` Moto before any
   packaging decision.
6. Do not replace exact-lossless cut-outs with lossy alpha unless the owner
   approves the actual edge quality.

The 75% tier leaves very little margin over 10× (10.074×). Any higher quality
setting should therefore use category-specific tuning rather than assuming the
same uniform setting remains above target.

## Evidence and reproduction

- Before/after cards: `local/image-format-research/comparison.html`
- Sample metrics: `local/image-format-research/metrics/benchmark.csv`
- Full inventory metrics: `local/image-format-research/inventory/inventory-projection.csv`
- Generated candidates: `local/image-format-research/encoded/`
- Benchmark source: `run_benchmark.py`
- Inventory projection source: `project_inventory.py`

All generated comparison material is ignored, as required by Jungle's art review
rules, and can be recreated with the commands in [README.md](README.md).

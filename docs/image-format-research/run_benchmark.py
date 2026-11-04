#!/usr/bin/env python3
"""Measure Jungle-format alternatives without modifying runtime assets.

Run with the research virtualenv documented in README.md. Inputs are decoded to
PNG, encoded with the local codec stack, decoded again, and compared with the
source WebP decode. Generated bitstreams and large previews stay under
local/image-format-research so this research does not change Jungle's asset set.
"""

from __future__ import annotations

import csv
import json
import math
import shutil
import subprocess
import time
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from html import escape
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import uniform_filter


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "local/image-format-research"
MODEL_ZIP = (
    "https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-models/"
    "models/quicksrnetsmall/releases/v0.65.0/quicksrnetsmall-onnx-float.zip"
)
MODEL_DIR = OUT / "models/quicksrnetsmall-onnx-float"
MODEL_PATH = MODEL_DIR / "quicksrnetsmall.onnx"
BACKGROUND = (247, 241, 229)

SAMPLES = [
    ("book-page", "assets/jungle-book/pages/tiger.webp"),
    ("lossless-cutout", "assets/jungle-book/items/panda.webp"),
    ("title-background", "assets/jungle/title/layers/treehouse-background.webp"),
    ("animation-layer", "assets/jungle/title/window-animation/portrait-frame.webp"),
    ("extreme-aspect-layer", "assets/jungle/title/window-animation/portrait-leaves-3.webp"),
    ("flat-vector-scene", "assets/shapes/wooden/sorter.webp"),
]


@dataclass
class Result:
    sample: str
    category: str
    source_path: str
    approach: str
    format: str
    source_bytes: int
    encoded_bytes: int
    reduction: float
    encode_seconds: float
    decode_seconds: float
    psnr_db: float
    ssim: float
    alpha_iou: float | None
    model_seconds: float | None
    notes: str
    encoded_path: str
    rendered_path: str


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def fetch_model() -> None:
    if MODEL_PATH.exists():
        return
    target = OUT / "models/quicksrnetsmall-onnx-float.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        urllib.request.urlretrieve(MODEL_ZIP, target)
    with zipfile.ZipFile(target) as archive:
        archive.extractall(target.parent)


def composite(image: Image.Image) -> np.ndarray:
    source = image.convert("RGBA")
    canvas = Image.new("RGBA", source.size, BACKGROUND + (255,))
    return np.asarray(Image.alpha_composite(canvas, source).convert("RGB"), dtype=np.float32)


def psnr(reference: np.ndarray, candidate: np.ndarray) -> float:
    mse = np.mean((reference - candidate) ** 2)
    return 99.0 if mse == 0 else 10 * math.log10(255.0 * 255.0 / mse)


def ssim(reference: np.ndarray, candidate: np.ndarray) -> float:
    # A standard 8x8-moving-window integer SSIM approximation. It is sufficient
    # for comparing codec families on the same artwork and avoids heavyweight
    # optional image-quality packages.
    first = reference.astype(np.float64)
    second = candidate.astype(np.float64)
    values = []
    for channel in range(3):
        left = first[..., channel]
        right = second[..., channel]
        left_mean = uniform_filter(left, 8)
        right_mean = uniform_filter(right, 8)
        left_square = uniform_filter(left * left, 8) - left_mean * left_mean
        right_square = uniform_filter(right * right, 8) - right_mean * right_mean
        covariance = uniform_filter(left * right, 8) - left_mean * right_mean
        c1 = (0.01 * 255) ** 2
        c2 = (0.03 * 255) ** 2
        numerator = (2 * left_mean * right_mean + c1) * (2 * covariance + c2)
        denominator = (left_mean * left_mean + right_mean * right_mean + c1) * (
            left_square + right_square + c2
        )
        values.append(float(np.mean(numerator / denominator)))
    return sum(values) / len(values)


def alpha_iou(reference: Image.Image, candidate: Image.Image) -> float | None:
    if "A" not in reference.getbands() or "A" not in candidate.getbands():
        return None
    left = np.asarray(reference.getchannel("A")) >= 128
    right = np.asarray(candidate.getchannel("A")) >= 128
    union = np.logical_or(left, right).sum()
    return float(np.logical_and(left, right).sum() / union) if union else 1.0


def image_with_suffix(path: Path, suffix: str) -> Path:
    return path.with_name(f"{path.stem}-{suffix}{path.suffix}")


def encode_webp(source: Path, target: Path, quality: int) -> float:
    started = time.perf_counter()
    with Image.open(source) as image:
        image.save(target, "WEBP", quality=quality, method=6, exact=True, alpha_quality=100)
    return time.perf_counter() - started


def encode_avif(source: Path, target: Path, quality: int) -> float:
    started = time.perf_counter()
    run(["magick", str(source), "-quality", str(quality), str(target)])
    return time.perf_counter() - started


def encode_heic(source: Path, target: Path, quality: int) -> float:
    started = time.perf_counter()
    run(["magick", str(source), "-quality", str(quality), str(target)])
    return time.perf_counter() - started


def encode_jxl(source: Path, target: Path, distance: float) -> float:
    started = time.perf_counter()
    run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
            "-frames:v", "1", "-c:v", "libjxl", "-effort", "7",
            "-distance", str(distance), str(target),
        ]
    )
    return time.perf_counter() - started


def decode(source: Path, target: Path) -> tuple[Image.Image, float]:
    started = time.perf_counter()
    if source.suffix in {".heic", ".jxl"}:
        if source.suffix == ".heic":
            run(["magick", str(source), str(target)])
        else:
            run(
                [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
                    "-frames:v", "1", "-plays", "1", str(target),
                ]
            )
        image = Image.open(target)
        image.load()
    else:
        image = Image.open(source)
        image.load()
    return image, time.perf_counter() - started


class QuickSRNet:
    def __init__(self) -> None:
        fetch_model()
        self.session = ort.InferenceSession(
            str(MODEL_PATH), providers=["CPUExecutionProvider"]
        )

    def upscale(self, source: Image.Image) -> tuple[Image.Image, float]:
        rgb = source.convert("RGBA")
        alpha = rgb.getchannel("A")
        visible = Image.new("RGBA", rgb.size, BACKGROUND + (255,))
        visible.alpha_composite(rgb)
        model_input = visible.convert("RGB")
        width, height = model_input.size
        padded_width = (width + 127) // 128 * 128
        padded_height = (height + 127) // 128 * 128
        padded = Image.new("RGB", (padded_width, padded_height), BACKGROUND)
        padded.paste(model_input, (0, 0))
        pixels = np.asarray(padded, dtype=np.float32).transpose(2, 0, 1) / 255.0
        restored = np.empty((3, padded_height * 4, padded_width * 4), dtype=np.float32)
        started = time.perf_counter()
        for top in range(0, padded_height, 128):
            for left in range(0, padded_width, 128):
                tile = pixels[None, :, top : top + 128, left : left + 128]
                output = self.session.run(None, {"image": tile})[0][0]
                restored[
                    :, top * 4 : (top + 128) * 4, left * 4 : (left + 128) * 4
                ] = output
        model_seconds = time.perf_counter() - started
        restored = np.clip(restored[:, : height * 4, : width * 4] * 255.0 + 0.5, 0, 255)
        restored = restored.astype(np.uint8).transpose(1, 2, 0)
        result = Image.fromarray(restored, "RGB")
        if alpha.getextrema()[0] < 255:
            result.putalpha(alpha.resize(result.size, Image.Resampling.LANCZOS))
        return result, model_seconds


def encode_pair(
    sample: str,
    source_path: str,
    source_image: Image.Image,
    prepared_png: Path,
    approach: str,
    format_name: str,
    target: Path,
    encode_seconds: float,
    render: Image.Image,
    decode_seconds: float,
    model_seconds: float | None = None,
    notes: str = "",
) -> Result:
    rendered_path = target.with_suffix(".render.png")
    render.save(rendered_path)
    reference = composite(source_image)
    candidate = composite(render)
    return Result(
        sample=sample,
        category=source_path.removeprefix("assets/").rsplit("/", 1)[0],
        source_path=source_path,
        approach=approach,
        format=format_name,
        source_bytes=Path(source_path).stat().st_size,
        encoded_bytes=target.stat().st_size,
        reduction=Path(source_path).stat().st_size / target.stat().st_size,
        encode_seconds=encode_seconds,
        decode_seconds=decode_seconds,
        psnr_db=psnr(reference, candidate),
        ssim=ssim(reference, candidate),
        alpha_iou=alpha_iou(source_image, render),
        model_seconds=model_seconds,
        notes=notes,
        encoded_path=str(target.relative_to(ROOT)),
        rendered_path=str(rendered_path.relative_to(ROOT)),
    )


def make_comparison_card(sample: str, source: Image.Image, candidates: list[tuple[str, Image.Image]]) -> Path:
    display_width = 520 if source.width >= source.height else 390
    scale = display_width / source.width
    display_height = max(1, round(source.height * scale))
    label_height = 32
    canvas = Image.new(
        "RGB",
        (display_width, (display_height + label_height) * (len(candidates) + 1)),
        (247, 241, 229),
    )
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(18)
    panels = [("Before: current WebP", source)] + candidates
    for index, (label, image) in enumerate(panels):
        y = index * (display_height + label_height)
        draw.text((8, y + 6), label, fill=(47, 60, 44), font=font)
        resized = image.convert("RGB").resize((display_width, display_height), Image.Resampling.LANCZOS)
        canvas.paste(resized, (0, y + label_height))
    target = OUT / "previews" / f"{sample}-before-after.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, optimize=True)
    return target


def write_results(results: list[Result], cards: dict[str, Path]) -> None:
    metrics = OUT / "metrics"
    metrics.mkdir(parents=True, exist_ok=True)
    with (metrics / "benchmark.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(asdict(results[0])))
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))
    with (metrics / "benchmark.json").open("w") as stream:
        json.dump([asdict(result) for result in results], stream, indent=2)

    rows = "\n".join(
        "<tr>"
        f"<td>{escape(result.sample)}</td><td>{escape(result.approach)}</td>"
        f"<td>{result.reduction:.2f}×</td><td>{result.encoded_bytes / 1024:.1f} KiB</td>"
        f"<td>{result.psnr_db:.2f}</td><td>{result.ssim:.4f}</td>"
        "<td>" + ("—" if result.alpha_iou is None else f"{result.alpha_iou:.4f}") + "</td>"
        f"<td>{result.encode_seconds:.3f}s</td>"
        f"<td>{'' if result.model_seconds is None else f'{result.model_seconds:.3f}s'}</td></tr>"
        for result in results
    )
    cards_html = "\n".join(
        f'<figure><img src="{escape(path.relative_to(OUT).as_posix())}">'
        f"<figcaption>{escape(sample)}</figcaption></figure>"
        for sample, path in cards.items()
    )
    document = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Jungle image format research</title>
<style>
body{{font-family:system-ui,sans-serif;margin:24px;color:#2f3c2c;background:#f7f1e5}}
table{{border-collapse:collapse;width:100%;font-size:13px;background:white}}
th,td{{border:1px solid #d8cdb8;padding:6px;text-align:right}} th:first-child,td:first-child{{text-align:left}}
img{{width:100%;display:block;border:1px solid #d8cdb8;background:white}} figure{{margin:0 0 28px}} figcaption{{font-weight:700;margin:6px 0}}
</style></head><body><h1>Jungle before/after comparison</h1>
<p>Each card shows the source WebP decode before full-resolution AVIF q35, the 75%-resolution
AVIF q35 + Lanczos tier that reaches the 10× inventory target, and the experimental
quarter-resolution AVIF q35 + QuickSRNet CPU path.</p>
{cards_html}<h2>Measured variants</h2><table><thead><tr>
<th>Sample</th><th>Approach</th><th>Reduction</th><th>Encoded</th><th>PSNR</th><th>SSIM</th><th>Alpha IoU</th><th>Encode</th><th>Model</th>
</tr></thead><tbody>{rows}</tbody></table></body></html>"""
    (OUT / "comparison.html").write_text(document)


def prepare(source_path: Path, name: str) -> tuple[Image.Image, Path, Path, Path, Path]:
    baseline = OUT / "baseline" / f"{name}.png"
    half = OUT / "baseline" / f"{name}-half.png"
    quarter = OUT / "baseline" / f"{name}-quarter.png"
    three_quarter = OUT / "baseline" / f"{name}-three-quarter.png"
    with Image.open(source_path) as image:
        image.load()
        source = image.convert("RGBA")
        source.save(baseline)
        source.resize(
            (max(1, source.width // 2), max(1, source.height // 2)),
            Image.Resampling.LANCZOS,
        ).save(half)
        source.resize(
            (max(1, source.width // 4), max(1, source.height // 4)),
            Image.Resampling.LANCZOS,
        ).save(quarter)
        source.resize(
            (max(1, round(source.width * 0.75)), max(1, round(source.height * 0.75))),
            Image.Resampling.LANCZOS,
        ).save(three_quarter)
    return source, baseline, three_quarter, half, quarter


def main() -> None:
    for folder in ("baseline", "encoded", "metrics", "models", "previews"):
        (OUT / folder).mkdir(parents=True, exist_ok=True)
    model = QuickSRNet()
    results: list[Result] = []
    cards: dict[str, Path] = {}
    for sample, relative_path in SAMPLES:
        source_path = ROOT / relative_path
        source, baseline, three_quarter, half, quarter = prepare(source_path, sample)

        direct_specs = [
            ("full-res AVIF q35", "AVIF", "avif", 35),
            ("full-res AVIF q50", "AVIF", "avif", 50),
            ("full-res JPEG XL d2", "JPEG XL", "jxl", 2.0),
            ("full-res HEIC q50", "HEIC", "heic", 50),
            ("full-res WebP q35", "WebP", "webp", 35),
        ]
        for approach, format_name, codec, quality in direct_specs:
            target = OUT / "encoded" / f"{sample}-full-{codec}.{'webp' if codec == 'webp' else codec}"
            if codec == "avif":
                seconds = encode_avif(baseline, target, quality)
            elif codec == "heic":
                seconds = encode_heic(baseline, target, quality)
            elif codec == "jxl":
                seconds = encode_jxl(baseline, target, quality)
            else:
                seconds = encode_webp(baseline, target, quality)
            decoded, decode_seconds = decode(target, target.with_suffix(".decode.png"))
            results.append(
                encode_pair(
                    sample, relative_path, source, baseline, approach, format_name, target,
                    seconds, decoded, decode_seconds,
                )
            )

        low_specs = [
            ("three-quarter", three_quarter, 4 / 3),
            ("half", half, 2),
            ("quarter", quarter, 4),
        ]
        for stage, prepared, divisor in low_specs:
            for codec, format_name, quality in (
                ("avif", "AVIF", 35),
                ("jxl", "JPEG XL", 2.0),
                ("webp", "WebP", 35),
            ):
                target = OUT / "encoded" / f"{sample}-{stage}-{codec}.{codec}"
                if codec == "avif":
                    seconds = encode_avif(prepared, target, quality)
                elif codec == "jxl":
                    seconds = encode_jxl(prepared, target, quality)
                else:
                    seconds = encode_webp(prepared, target, quality)
                decoded, decode_seconds = decode(target, target.with_suffix(".decode.png"))
                lanczos = decoded.resize(source.size, Image.Resampling.LANCZOS)
                results.append(
                    encode_pair(
                        sample, relative_path, source, baseline,
                        f"{stage}-res {format_name} + Lanczos", format_name, target,
                        seconds, lanczos, decode_seconds,
                        notes=f"decode is {divisor}x smaller than runtime, then Lanczos {divisor}x",
                    )
                )
                if codec == "avif" and stage == "quarter":
                    restored, model_seconds = model.upscale(decoded)
                    restored = restored.resize(source.size, Image.Resampling.LANCZOS)
                    results.append(
                        encode_pair(
                            sample, relative_path, source, baseline,
                            f"{stage}-res AVIF + QuickSRNet", "AVIF", target,
                            seconds, restored, decode_seconds, model_seconds,
                            notes="AVIF decode tiled through 133 KB QuickSRNet ONNX on CPU",
                        )
                    )

        selected = {
            result.approach: Image.open(ROOT / result.rendered_path)
            for result in results
            if result.approach in {
                "full-res AVIF q35",
                "three-quarter-res AVIF + Lanczos",
                "quarter-res AVIF + QuickSRNet",
            }
        }
        cards[sample] = make_comparison_card(
            sample,
            source,
            [(approach, image) for approach, image in selected.items()],
        )
    write_results(results, cards)
    print(f"wrote {len(results)} measurements to {OUT / 'metrics/benchmark.csv'}")
    print(f"wrote {OUT / 'comparison.html'}")


if __name__ == "__main__":
    main()

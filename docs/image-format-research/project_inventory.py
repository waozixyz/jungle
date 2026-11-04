#!/usr/bin/env python3
"""Encode an AVIF size projection for every runtime WebP without changing assets."""

from __future__ import annotations

import csv
import subprocess
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "local/image-format-research/inventory"
VARIANTS = {
    "full": [],
    "three-quarter": ["-resize", "75%"],
    "half": ["-resize", "50%"],
    "quarter": ["-resize", "25%"],
}


def encode(source: Path, variant: str, transforms: list[str]) -> dict[str, object]:
    target = OUT / variant / source.relative_to(ROOT / "assets")
    target = target.with_suffix(".avif")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or target.stat().st_size == 0:
        subprocess.run(
            ["magick", str(source), *transforms, "-quality", "35", str(target)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return {
        "source": str(source.relative_to(ROOT)),
        "category": str(source.relative_to(ROOT / "assets").parent),
        "variant": variant,
        "source_bytes": source.stat().st_size,
        "encoded_bytes": target.stat().st_size,
    }


def main() -> None:
    sources = sorted((ROOT / "assets").rglob("*.webp"))
    jobs = [(source, variant, transforms) for source in sources for variant, transforms in VARIANTS.items()]
    rows: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(encode, *job) for job in jobs]
        for index, future in enumerate(as_completed(futures), 1):
            rows.append(future.result())
            if index % 100 == 0:
                print(f"encoded {index}/{len(jobs)}")

    rows.sort(key=lambda row: (row["source"], row["variant"]))
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "inventory-projection.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary: dict[str, dict[str, int]] = defaultdict(
        lambda: {"source": 0, **{variant: 0 for variant in VARIANTS}}
    )
    for row in rows:
        if row["variant"] == "full":
            summary[row["category"]]["source"] += int(row["source_bytes"])
        summary[row["category"]][row["variant"]] += int(row["encoded_bytes"])
    print("category,count,current," + ",".join(VARIANTS) + "," + ",".join(f"{name}_x" for name in VARIANTS))
    for category, totals in sorted(summary.items(), key=lambda item: -item[1]["source"]):
        count = sum(row["category"] == category and row["variant"] == "full" for row in rows)
        print(
            category, count, totals["source"],
            *(totals[variant] for variant in VARIANTS),
            *(round(totals["source"] / totals[variant], 2) for variant in VARIANTS),
            sep=",",
        )


if __name__ == "__main__":
    main()

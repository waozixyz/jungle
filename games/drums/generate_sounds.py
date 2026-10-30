#!/usr/bin/env python3
"""Rebuild Little Drums' four quiet, deterministic percussion samples.

Only the Python standard library is needed. No recording or runtime network
dependency. Run from any directory: python3 games/drums/generate_sounds.py.
"""
import io
import math
from pathlib import Path
import random
import struct
import wave

RATE = 22050
KINDS = ("low_drum", "small_drum", "shaker", "bell")
OUTPUT = Path(__file__).resolve().parents[2] / "assets/drums/sounds"


def pcm(kind):
    """A membrane's modes, a seed shaker, or soft struck metal, at <= -14 dBFS."""
    rng = random.Random(407 + KINDS.index(kind))
    duration = 0.62 if kind == "bell" else 0.42
    count = round(duration * RATE)
    values = []
    low_noise = 0.0
    phase = 0.0
    for i in range(count):
        t = i / RATE
        noise = rng.uniform(-1.0, 1.0)
        low_noise += 0.14 * (noise - low_noise)
        if kind in ("low_drum", "small_drum"):
            base = 112 if kind == "low_drum" else 205
            # A small downward pitch bend with inharmonic membrane modes.
            phase += 2 * math.pi * (base + 58 * math.exp(-32 * t)) / RATE
            value = (math.sin(phase) * math.exp(-11 * t)
                     + 0.34 * math.sin(1.59 * phase) * math.exp(-18 * t)
                     + 0.18 * math.sin(2.14 * phase) * math.exp(-24 * t)
                     + 0.10 * low_noise * math.exp(-35 * t))
        elif kind == "shaker":
            # High-pass seed noise in two small swishes, not a sharp snare.
            swish = math.exp(-((t - 0.065) / 0.034) ** 2)
            swish += 0.60 * math.exp(-((t - 0.19) / 0.046) ** 2)
            value = (noise - low_noise) * swish
        else:
            value = (math.sin(2 * math.pi * 660 * t) * math.exp(-5.5 * t)
                     + 0.29 * math.sin(2 * math.pi * 990 * t) * math.exp(-8 * t)
                     + 0.13 * math.sin(2 * math.pi * 1778 * t) * math.exp(-12 * t))
        # Smooth, silent endpoints; no discontinuous attack or truncated tail.
        attack = 0.5 - 0.5 * math.cos(math.pi * min(1.0, t / 0.012))
        release = min(1.0, (count - 1 - i) / (RATE * 0.035))
        release = 0.5 - 0.5 * math.cos(math.pi * release)
        values.append(value * attack * release)
    peak = max(abs(value) for value in values)
    gain = 0.19 / peak
    return [round(value * gain * 32767) for value in values]


def wav_bytes(kind):
    samples = pcm(kind)
    out = io.BytesIO()
    with wave.open(out, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(RATE)
        audio.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return out.getvalue()


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for kind in KINDS:
        path = OUTPUT / f"{kind}.wav"
        data = wav_bytes(kind)
        path.write_bytes(data)
        print(f"{path.relative_to(OUTPUT.parents[2])}: {len(data)} bytes")


if __name__ == "__main__":
    main()

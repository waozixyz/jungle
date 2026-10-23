#!/usr/bin/env python3
"""Rebuild reference assets from Animal Math data and Bert voice files.

Usage: python3 tools/import_original.py --animal-dir PATH --bert-dir PATH
Data is decoded directly; this tool never captures a desktop or runs a game.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import wave

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
CGA = [(0, 0, 170, 255), (85, 255, 85, 255),
       (255, 85, 85, 255), (255, 255, 85, 255)]


def sprite(raw):
    rows, columns = struct.unpack_from("<HH", raw)
    width, height = (columns + 1) * 4, (rows + 1) * 2
    assert 1 <= width <= 24 and 1 <= height <= 20 and len(raw) == 128
    picture = Image.new("RGBA", (width, height))
    for y in range(height):
        for x in range(width):
            # The sprite structure reserves six bytes for each half-row,
            # even when the sprite's visible width is smaller.
            byte = raw[4 + (y // 2) * 6 + (60 if y % 2 else 0) + x // 4]
            color = (byte >> (6 - (x % 4) * 2)) & 3
            if color:
                picture.putpixel((x, y), CGA[color])
    return picture


def animal(source):
    output = ROOT / "assets/animal-count"
    items = output / "items"
    items.mkdir(parents=True, exist_ok=True)
    table = (source / "ANIMALS.TAB").read_bytes()
    assert len(table) == 24 * 128
    for index in range(24):
        picture = sprite(table[index * 128:(index + 1) * 128])
        assert picture.getbbox(), f"empty native sprite {index + 1}"
        picture.save(items / f"animal-{index + 1}.png")
    pascal = (source / "ANIMALS.PAS").read_text(errors="replace")
    for name, target in [("EqualSign", "equals"), ("QuestionMark", "question"), ("CheckMark", "check")]:
        body = re.search(r"const\s+" + name + r"\s*:.*?=\s*\((.*?)\);", pascal, re.S | re.I).group(1)
        body = re.sub(r"\{.*?\}", "", body, flags=re.S)
        raw = bytes(int(value) for value in re.findall(r"\d+", body))
        sprite(raw).save(items / (target + ".png"))
    screen = (source / "ANIMALS.__2").read_bytes()
    assert len(screen) == 16384
    picture = Image.new("RGB", (320, 200))
    for y in range(200):
        for x in range(320):
            byte = screen[(y // 2) * 80 + (8192 if y % 2 else 0) + x // 4]
            picture.putpixel((x, y), CGA[(byte >> (6 - (x % 4) * 2)) & 3][:3])
    picture.save(output / "background.png")


def font(binary):
    data = binary.read_bytes()
    # Verify adjacent A and B glyphs before using the BIOS font table.
    marker = bytes.fromhex("3078ccccfccccc00")
    start = data.index(marker) - 65 * 8
    assert data[start + 66 * 8:start + 67 * 8] == bytes.fromhex("fc66667c6666fc00")
    picture = Image.new("RGBA", (128, 48))
    for code in range(32, 127):
        for y in range(8):
            row = data[start + code * 8 + y]
            for x in range(8):
                if row & (128 >> x):
                    picture.putpixel((((code - 32) % 16) * 8 + x, ((code - 32) // 16) * 8 + y),
                                     (255, 255, 255, 255))
    picture.save(ROOT / "assets/animal-count/font.png")


def dinosaur_bodies(source):
    """Recover opaque bodies before reducing the original closed outlines.

    Flooding a reduced drawing can leak through raster gaps. The native DOT
    strokes form the actual boundary; everything enclosed by it covers older
    artwork, including the white spaces between interior detail lines.
    """
    output = ROOT / "assets/dino-paint/art"
    for index in range(12):
        raw = (source / f"BDA{300 + index}.DOT").read_bytes()
        commands = [(chr(raw[at]), *struct.unpack_from("<hh", raw, at + 1))
                    for at in range(72, len(raw) - 4, 5)]
        command, width, height = commands[0]
        assert command == "M" and 0 < width < 640 and 0 < height < 480
        native = Image.new("L", (width + 3, height + 3))
        draw = ImageDraw.Draw(native)
        point = (1, 1)
        for command, x, y in commands[1:]:
            next_point = (x + 1, y + 1)
            if command == "S":
                point = next_point
            elif command == "N":
                draw.line((point, next_point), fill=255)
                point = next_point
        ImageDraw.floodfill(native, (0, 0), 128)
        body = native.point(lambda value: 0 if value == 128 else 255)
        body = body.crop((1, 1, width + 1, height + 1))
        path = output / f"dino{index + 1}-s4.png"
        ink = Image.open(path).convert("RGBA")
        body = body.resize(ink.size, Image.Resampling.NEAREST)
        picture = Image.new("RGBA", ink.size)
        for y in range(ink.height):
            for x in range(ink.width):
                r, g, b, a = ink.getpixel((x, y))
                if a >= 128 and r + g + b < 384:
                    picture.putpixel((x, y), (0, 0, 0, 255))
                elif body.getpixel((x, y)):
                    picture.putpixel((x, y), (255, 255, 255, 255))
        picture.save(path)


def voices(source):
    output = ROOT / "assets/dino-paint/sounds"
    for index in range(12):
        raw = (source / f"BDS3{index:02}.V8").read_bytes()
        frames = bytearray()
        for frame in range(round(len(raw) * 22050 / 8000)):
            position = frame * 8000 / 22050
            left = int(position)
            fraction = position - left
            value = raw[left] * (1 - fraction) + raw[min(left + 1, len(raw) - 1)] * fraction
            frames.extend(struct.pack("<h", max(-32768, min(32767, round((value - 77) * 100)))))
        with wave.open(str(output / f"voice-{index + 1}.wav"), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(22050)
            audio.writeframes(frames)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--animal-dir", type=Path)
    parser.add_argument("--bert-dir", type=Path)
    parser.add_argument("--dosbox", type=Path)
    args = parser.parse_args()
    sources = []
    if args.animal_dir:
        animal(args.animal_dir)
        sources.extend(args.animal_dir / name for name in ["ANIMALS.TAB", "ANIMALS.PAS", "ANIMALS.__2"])
    if args.bert_dir:
        voices(args.bert_dir)
        dinosaur_bodies(args.bert_dir)
        sources.extend(args.bert_dir.glob("BDS3*.V8"))
        sources.extend(args.bert_dir.glob("BDA*.DOT"))
    if args.dosbox:
        font(args.dosbox)
    assert sources or args.dosbox, "select an input with --animal-dir, --bert-dir or --dosbox"
    receipt = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    output = ROOT / "backup/reference"
    output.mkdir(parents=True, exist_ok=True)
    (output / "asset-sources.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("Original assets decoded and written as binary PNG/WAV files.")


if __name__ == "__main__":
    main()

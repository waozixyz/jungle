"""Compare a returned bookshelf while allowing tiny compositor rounding noise."""
import argparse
import json

from PIL import Image, ImageChops


def compare(reference, current):
    with Image.open(reference) as first, Image.open(current) as second:
        if first.size != second.size:
            return {"equal": False, "reason": "different dimensions"}
        delta = ImageChops.difference(first.convert("RGBA"), second.convert("RGBA"))
        # CI's DOM compositor can round a few clipped edge channels by one.
        # A changed label, selection, picture or navigation destination must fail.
        changed = sum(any(pixel) for pixel in delta.getdata())
        maximum = max(channel for _, channel in delta.getextrema())
        return {"equal": changed <= 16 and maximum <= 1,
                "changed_pixels": changed, "maximum_channel_delta": maximum}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference")
    parser.add_argument("current")
    args = parser.parse_args()
    print(json.dumps(compare(args.reference, args.current)))

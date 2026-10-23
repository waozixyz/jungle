#!/usr/bin/env python3
"""Verify real exported files and printer delivery without using a printer."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="jungle-export-") as temporary:
        folder = Path(temporary)
        fake = folder / "bin"
        fake.mkdir()
        printer = fake / "lp"
        printer.write_text("#!/usr/bin/env python3\nimport json,os,sys\n"
                           "from pathlib import Path\n"
                           "p=Path(sys.argv[-1]);assert p.is_file()\n"
                           "Path(os.environ['JUNGLE_PRINTER_LOG']).write_text(json.dumps(sys.argv[1:]))\n")
        printer.chmod(0o700)
        env = os.environ.copy()
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS"):
            env.pop(key, None)
        env["PATH"] = str(fake) + os.pathsep + env["PATH"]
        env["JUNGLE_PRINTER_LOG"] = str(folder / "printer.json")
        subprocess.run([str(ROOT / "build/tests/printing"), str(folder / "data")], env=env, check=True)
        exported = folder / "data/exports"
        assert len(list(exported.glob("*.png"))) == 2
        assert len(list(exported.glob("*.txt"))) == 2
        for png in exported.glob("*.png"):
            with Image.open(png) as picture:
                assert picture.size == (240, 180)
                assert len(picture.convert("RGB").getcolors(500) or []) >= 15
            assert png.with_suffix(".txt").read_text().startswith("My dinosaur (and friend)\\hello\nSecond line")
        received = json.loads((folder / "printer.json").read_text())
        assert received[:2] == ["-t", "Jungle picture and story"]
        ps = Path(received[-1])
        content = ps.read_text()
        assert content.startswith("%!PS-Adobe-3.0\n"), repr(content[:80])
        assert "colorimage" in content and r"\(and friend\)\\hello" in content
        # Ghostscript validates the actual page, including escaped story text.
        subprocess.run(["gs", "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=png16m",
                        "-r72", "-sOutputFile=" + str(folder / "page.png"), str(ps)], check=True,
                       capture_output=True)
        with Image.open(folder / "page.png") as page:
            assert page.width >= 612 and page.height >= 792
        print("local export test: PNG, story, rendered color print page and printer submission passed")


if __name__ == "__main__":
    main()

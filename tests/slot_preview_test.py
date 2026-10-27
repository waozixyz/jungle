"""Saved pictures reappear after temporary canvas images have been evicted."""
from pathlib import Path
import tempfile

from PIL import Image
from runtime_test import Desktop, ROOT


with tempfile.TemporaryDirectory(prefix="jungle-slot-previews-") as temporary:
    data = Path(temporary)
    with Desktop(ROOT / "build/app/jungle", data) as desktop:
        desktop.capture("slot-preview-menu")
        desktop.game("Coloring Book")
        desktop.capture("slot-preview-paint")
        folder = data / "games/jungle.paint"
        assert not (folder / "working.txt").exists(), "A new picture unexpectedly has saved artwork"
        # A new picture opens the backgrounds directly, before any stencil.
        desktop.click(52, 58)
        assert (folder / "working.txt").exists(), "A new picture did not choose its background first"
        desktop.key("Escape")
        picture = (folder / "working.txt").read_bytes()
        for index in range(6):
            (folder / f"slot-{index}.txt").write_bytes(picture)
        desktop.click(30, 110)
        desktop.capture("slot-preview-save")
        previews = set(folder.glob("canvas-*.png"))
        assert len(previews) >= 7, "Save did not make all six picture previews"
        desktop.click(210, 38)
        desktop.capture("slot-preview-load")
        assert set(folder.glob("canvas-*.png")) == previews, "Switching tabs regenerated previews"
        desktop.key("Escape")
        # The host removes old temporary pictures as painting creates new ones.
        # Remove only files in this test's disposable game directory.
        for path in previews:
            path.unlink()
        desktop.click(30, 110)
        desktop.capture("slot-preview-reopened")
        refreshed = set(folder.glob("canvas-*.png"))
        assert len(refreshed) >= 6, "Reopening Save kept evicted preview filenames"
        assert not refreshed & previews, "Save reused an evicted preview"
        for path in refreshed:
            with Image.open(path) as preview:
                assert preview.size == (960, 720), "Preview lost its saved canvas"
        for index in range(6):
            assert (folder / f"slot-{index}.txt").read_bytes() == picture
    for path in folder.glob("canvas-*.png"):
        path.unlink()
    with Desktop(ROOT / "build/app/jungle", data) as desktop:
        desktop.capture("slot-preview-restart-menu")
        desktop.game("Coloring Book")
        desktop.capture("slot-preview-resume")
        desktop.click(30, 110)
        desktop.capture("slot-preview-resumed-save")
        assert (folder / "working.txt").read_bytes() == picture, "Reopening replaced the saved background"
        assert len(set(folder.glob("canvas-*.png"))) >= 7, "A saved picture reopened in the background chooser"
print("local UI test: six Save/Load previews, cache reuse and eviction recovery passed")

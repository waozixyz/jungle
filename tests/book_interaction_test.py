"""Picture Book narration, secondary Back, and page-edge pixel behavior."""
import os
import subprocess
import tempfile
import time
from pathlib import Path
from PIL import Image, ImageChops

from runtime_test import ROOT, Desktop, environment, run


OUTPUT = ROOT / "build/tests/ui"


def BuildBookTestApp() -> Path:
    override = os.environ.get("JUNGLE_TEST_BINARY")
    if override is not None:
        binary = (ROOT / override).resolve()
    else:
        build = subprocess.run(
            ["make", "-j1", "all"], cwd=ROOT, env=environment(),
            check=True, timeout=900)
        binary = (ROOT / "build/app/jungle").resolve()
    assert binary.exists(), f"Jungle test app does not exist: {binary}"
    assert binary.is_file(), f"Jungle test app is not a file: {binary}"
    return binary


BINARY = BuildBookTestApp()


def changed(first, second, box=None):
    if box:
        first, second = first.crop(box), second.crop(box)
    return ImageChops.difference(first, second).getbbox() is not None


def dark_page_edges(image, name):
    width, height = image.size
    columns = (int(width * .08), int(width * .28), width // 2,
               int(width * .72), int(width * .92))
    dark_rows = []
    for row in range(height):
        pixels = [image.getpixel((column, row)) for column in columns]
        if all(red < 70 and green < 70 and blue < 70 for red, green, blue in pixels):
            dark_rows.append(row)
    assert not dark_rows, f"{name} has cross-page dark lines at rows {dark_rows[:8]}"


def audio_size(path):
    return path.stat().st_size if path.exists() else 0


def audio_signal(path):
    if not path.exists():
        return 0
    signal = 0
    with path.open("rb") as narration:
        while chunk := narration.read(65536):
            signal += sum(byte != 0 for byte in chunk)
    return signal


def wait_for_finished_audio(path):
    previous = -1
    for _ in range(120):
        signal = audio_signal(path)
        if signal > 1000 and signal == previous:
            return signal
        previous = signal
        time.sleep(.1)
    raise AssertionError(f"narration audio did not finish: {audio_signal(path)} signal bytes")


def right_click(desktop, hold_seconds=.35):
    run(["xdotool", "mousemove", "--window", desktop.window, "640", "360"], desktop.env)
    run(["xdotool", "mousedown", "3"], desktop.env)
    try:
        time.sleep(hold_seconds)
    finally:
        run(["xdotool", "mouseup", "3"], desktop.env)
    time.sleep(.25)
    desktop.alive()


def control_point(image, right_button=False):
    width, height = image.size
    game_height = height - 56
    control_width = min(width - 32, 560)
    control_x = (width - control_width) // 2
    x = control_x + (control_width * 3 // 4 if right_button else control_width // 4)
    return x, 56 + game_height - 37


def manage_books_point(image):
    width, height = image.size
    game_height = height - 56
    fit = max(1.0, min(width / 320.0, game_height / 200.0))
    padding = int(14.0 * fit) + 12
    gap = 12 if width < 600 else 20
    button_width = (width - padding * 2 - gap * 2) // 3
    return (padding + (button_width + gap) * 2 + button_width // 2,
            56 + game_height - padding - 24)


for language in ("en", "de", "es"):
    for mode in ("simple", "spelling"):
        with tempfile.TemporaryDirectory(prefix=f"jungle-book-{language}-{mode}-") as temporary:
            data = Path(temporary)
            (data / "language.txt").write_text(language)
            (data / "games/jungle.book").mkdir(parents=True)
            (data / "games/jungle.book/mode.txt").write_text(mode)
            audio = data / "narration.raw"
            environment = {"SDL_AUDIODRIVER": "disk", "SDL_DISKAUDIOFILE": str(audio)}
            with Desktop(BINARY, data, extra_env=environment, screen_size="1280x1280") as desktop:
                desktop.resize(1280, 720)
                desktop.game("Picture Book")
                desktop.key("1")
                desktop.key("space")
                landscape = desktop.capture_actual(f"book-interaction-{language}-{mode}-landscape")
                dark_page_edges(landscape, f"{language}/{mode} landscape")
                desktop.resize(720, 1280)
                portrait = desktop.capture_actual(f"book-interaction-{language}-{mode}-portrait")
                dark_page_edges(portrait, f"{language}/{mode} portrait")

                time.sleep(.6)
                audio.write_bytes(b"")
                desktop.key("Right")
                time.sleep(.5)
                assert audio_signal(audio) > 1000, (
                    f"paused {language}/{mode} manual turn did not narrate")
                if language == "en" and mode == "simple":
                    wait_for_finished_audio(audio)
                after_voice = desktop.capture_actual(f"book-interaction-{language}-{mode}-after-voice")
                time.sleep(.7)
                held = desktop.capture_actual(f"book-interaction-{language}-{mode}-manual-held")
                assert not changed(after_voice, held), (
                    f"manual {language}/{mode} narration resumed automatic turning")

                if language == "en" and mode == "simple":
                    desktop.key("space")
                    resumed = None
                    for _ in range(100):
                        resumed = desktop.capture_actual("book-interaction-resumed")
                        if changed(after_voice, resumed):
                            break
                        time.sleep(.1)
                    assert resumed is not None and changed(after_voice, resumed), "resume did not restore autoplay"
                    desktop.key("space")

                    desktop.key("F10")
                    assert (data / "sound.txt").read_text() == "off\n", "F10 did not mute Jungle"
                    audio.write_bytes(b"")
                    desktop.click_actual(*control_point(portrait, True))
                    time.sleep(.5)
                    assert audio_signal(audio) == 0, "muted Hear word wrote narration audio"
                    desktop.key("F10")
                    audio.write_bytes(b"")
                    desktop.click_actual(*control_point(portrait, True))
                    time.sleep(.5)
                    assert audio_signal(audio) > 1000, "unmuted Hear word did not narrate"

                    desktop.resize(1280, 720)
                    page = desktop.capture_actual("book-interaction-before-right-back")
                    right_click(desktop)
                    shelf = desktop.capture_actual("book-interaction-right-page-to-shelf")
                    assert changed(page, shelf), "right-click Back did not leave a page"
                    desktop.click_actual(*manage_books_point(shelf))
                    management = desktop.capture_actual("book-interaction-management")
                    assert changed(shelf, management), "Manage books did not open"
                    right_click(desktop)
                    returned_shelf = desktop.capture_actual("book-interaction-management-to-shelf")
                    assert not changed(shelf, returned_shelf), "right-click did not leave book management"
                    right_click(desktop)
                    home = desktop.capture_actual("book-interaction-shelf-to-home")
                    assert changed(shelf, home), "right-click did not leave the Picture Book shelf"

                assert "portable execution failed" not in (OUTPUT / "jungle.log").read_text()

print("local book interaction test: manual narration, Back hierarchy, mute, and clean page edges passed")

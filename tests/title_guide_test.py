
import hashlib
import json
import sys
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = ("en", "de", "es")
TEXTS = {
    "en": ("Tap a toy.", "Drag to see more.", "Tap the speaker."),
    "de": ("Tippe auf ein Spielzeug.", "Ziehe, um mehr zu sehen.", "Tippe auf den Lautsprecher."),
    "es": ("Toca un juguete.", "Arrastra para ver más.", "Toca el altavoz."),
}


hotspots = json.loads((ROOT / "tools/title_hotspots.json").read_text())
for scene in hotspots["scenes"]:
    variants = [scene] + ([scene["portrait"]] if "portrait" in scene else [])
    for variant in variants:
        assert all(hotspot.get("id") != "tiger-guide" for hotspot in variant["hotspots"])
        assert all(hotspot.get("target") != "guide:tour" for hotspot in variant["hotspots"])

title_source = (ROOT / "host/jungle_title.zi").read_text()
assert "TITLE_GUIDE_STEP_COUNT :: 3" in title_source
assert '", name, ".wav"' in title_source

menu_source = (ROOT / "host/jungle_menu.zi").read_text()
assert 'RetroTap(711' in menu_source
assert "SoundOffIcon.Shape" in menu_source
assert "guide_mute_toggle" in menu_source
assert "(pointer.pressed && !guide_hover)" in menu_source
assert "if guide_hover && !title_state.guide_finished_reported" in menu_source
assert "skip_hit :=" in menu_source
assert "guide_sound_hit :=" in menu_source
assert "if skip_hit || skip.clicked" in menu_source
assert "if guide_sound_hit || guide_sound.clicked" in menu_source
assert "action.guide_mute_toggle && !title_guide_muted" in (ROOT / "host/jungle_host.zi").read_text()
assert "action.guide_mute_toggle && !web_title_guide_muted" in (ROOT / "web/jungle_web.zi").read_text()
for translated in ("Anleitung überspringen", "Anleitungston aus", "Saltar la guía", "Guía sin sonido"):
    assert translated in menu_source

for source_name, sound_write, seen_write in (
    ("host/jungle_host.zi", 'WriteEntireFile(guide_sound_setting', 'WriteEntireFile(guide_seen_setting'),
    ("web/jungle_web.zi", '"settings/guide-sound.txt"', '"settings/guide-seen.txt"'),
):
    source = (ROOT / source_name).read_text()
    assert sound_write in source
    assert seen_write in source

profiles = json.loads((ROOT / "assets/speech-profiles.json").read_text())
assert profiles["voice"] == "af_bella" and profiles["default"] == "normal"
speeds = {"slow": 0.65, "normal": 0.8, "fast": 1.0}
assert set(profiles["profiles"]) == set(speeds)


def verify_recording(path, text):
    receipt = json.loads(path.with_suffix(".speech.json").read_text())
    data = path.read_bytes()
    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE", path
    assert receipt["text"] == text
    assert receipt["sha256"] == hashlib.sha256(data).hexdigest(), path
    with wave.open(str(path)) as recording:
        assert recording.getnchannels() == 1 and recording.getsampwidth() == 2, path
        seconds = recording.getnframes() / recording.getframerate()
        assert 0 < seconds < 3.0, (path, seconds)
        assert abs(receipt["duration"] - seconds) < 1 / recording.getframerate(), path
    return receipt


for language in LANGUAGES:
    for step, text in enumerate(TEXTS[language]):
        path = ROOT / f"assets/jungle/title/guide/{language}/step{step}.wav"
        receipt = verify_recording(path, text)
        if language != "en":
            assert receipt["language"] == language
            narration = json.loads((ROOT / "speech.json").read_text())["narration"][language]
            assert receipt["speed"] == 1.0 and receipt["voice"] == narration["voice"]
            assert receipt["model"] == narration["model"]
            continue
        original = path.relative_to(ROOT).as_posix()
        for profile, speed in speeds.items():
            target = original if profile == "normal" else f"assets/speech-profiles/{profile}/" + original.removeprefix("assets/")
            assert profiles["profiles"][profile]["speed"] == speed
            assert profiles["profiles"][profile]["voices"][original] == target
            receipt = verify_recording(ROOT / target, text)
            assert receipt["voice"] == "af_bella" and receipt["language"] == "en"
            assert receipt["model"] == "kokoro-82m-uint8"
            assert receipt["profile"] == profile and receipt["speed"] == speed
            assert receipt["model_sha256"] == "6607a397d77b8514065420b7c1e7320117f7aabfdb45ce15f0050c5b0fe75aea"
            assert receipt["voices_sha256"] == "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"

if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
import shared_assets
voices = shared_assets.NarratedVoices()
assert {f"assets/jungle/title/guide/{language}/step{step}.wav"
        for language in LANGUAGES for step in range(3)} <= set(voices)
assert not list((ROOT / "assets/jungle/title/guide").glob("*/*.ogg"))
print("title guide assets and flow: passed")

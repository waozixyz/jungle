
import hashlib
import json
import sys
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

for language in LANGUAGES:
    for step, text in enumerate(TEXTS[language]):
        path = ROOT / f"assets/jungle/title/guide/{language}/step{step}.wav"
        receipt_path = path.with_suffix(".speech.json")
        receipt = json.loads(receipt_path.read_text())
        data = path.read_bytes()
        assert data[:4] == b"RIFF" and data[8:12] == b"WAVE", path
        assert receipt["path"].endswith(f"{language}/step{step}.wav")
        assert receipt["speed"] == 1.0
        assert receipt["text"] == text
        assert receipt["voice"] == "Kore"
        assert receipt["duration"] < 3.0, (path, receipt["duration"])
        assert receipt["sha256"] == hashlib.sha256(data).hexdigest()

if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
import shared_assets
voices = shared_assets.NarratedVoices()
assert {f"assets/jungle/title/guide/{language}/step{step}.wav"
        for language in LANGUAGES for step in range(3)} <= set(voices)
assert not list((ROOT / "assets/jungle/title/guide").glob("*/*.ogg"))
print("title guide assets and flow: passed")

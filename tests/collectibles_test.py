from __future__ import annotations

import copy
from pathlib import Path

import pytest

import tools.collectibles as collectibles
from tools.collectibles import ROOT, RegistryError, load_registry, render_catalog, validate_registry


def mutate(field: str, value):
    registry = load_registry()
    if field == "version":
        registry["version"] = value
    elif field == "duplicate-id":
        registry["collectibles"][1]["id"] = registry["collectibles"][0]["id"]
    elif field == "high-id":
        registry["collectibles"][0]["id"] = 252
    elif field == "missing-color":
        registry["collectibles"][0]["color"] = "assets/collectibles/missing.png"
    else:
        registry["collectibles"][0][field] = value
    return registry


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", 2),
        ("duplicate-id", None),
        ("high-id", None),
        ("missing-color", None),
        ("slug", "Invalid Slug"),
        ("source", {"kind": "book", "page": 7}),
        ("how", {"kind": "tap", "x": 0.5, "y": 0.55, "rx": 0.3, "ry": 2.0}),
        ("color", 7),
        ("paint", {"kind": "stencil", "category": "places", "art": None}),
    ],
)
def test_rejects_bad_registry_fields(field, value):
    with pytest.raises(RegistryError):
        validate_registry(mutate(field, value))


def test_allows_pending_color_to_be_missing(tmp_path: Path):
    registry = load_registry()
    for entry in registry["collectibles"]:
        entry["pending"] = True
        entry["color"] = f"assets/collectibles/{entry['slug']}.png"
    validate_registry(registry, ROOT)


def test_generated_catalog_matches_registry():
    assert render_catalog(validate_registry(load_registry())) == (ROOT / "retro/collectibles.zi").read_text()


def test_check_rejects_a_stale_generated_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    registry = load_registry()
    registry["collectibles"] = copy.deepcopy(registry["collectibles"][:1])
    monkeypatch.setattr(collectibles, "load_registry", lambda: registry)
    monkeypatch.setattr(collectibles, "OUTPUT_PATH", tmp_path / "collectibles.zi")
    assert collectibles.main(["--check"]) == 1


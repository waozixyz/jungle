"""Validate collectible registry data and generate its Ziran catalog."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "tools/collectibles.json"
OUTPUT_PATH = ROOT / "retro/collectibles.zi"
REGISTRY_VERSION = 1
MAX_ID = 251
SLUG_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?")
SOURCE_REF_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,126}")
SOURCE_KINDS = {
    "book": "COLLECTIBLE_SOURCE_BOOK",
    "story": "COLLECTIBLE_SOURCE_STORY",
    "game": "COLLECTIBLE_SOURCE_GAME",
    "title": "COLLECTIBLE_SOURCE_TITLE",
}
SOURCE_FIELDS = {
    "book": ("page",),
    "story": ("story", "page"),
    "game": ("game",),
    "title": ("scene",),
}
HOW_KINDS = {"tap": "COLLECTIBLE_HOW_TAP", "paper": "COLLECTIBLE_HOW_PAPER"}
PAINT_KINDS = {"stencil": "COLLECTIBLE_PAINT_STENCIL", "scene": "COLLECTIBLE_PAINT_SCENE"}
PAINT_CATEGORIES = {
    "animals": "COLLECTIBLE_CATEGORY_ANIMALS",
    "objects": "COLLECTIBLE_CATEGORY_OBJECTS",
    "places": "COLLECTIBLE_CATEGORY_PLACES",
}


class RegistryError(ValueError):
    pass


def _object(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RegistryError(f"{where} must be an object")
    return value


def _string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise RegistryError(f"{where} must be a nonempty string")
    return value


def _integer(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RegistryError(f"{where} must be an integer")
    return value


def _number(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RegistryError(f"{where} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise RegistryError(f"{where} must be finite")
    return number


def _unit(value: Any, where: str) -> float:
    number = _number(value, where)
    if number < 0.0 or number > 1.0:
        raise RegistryError(f"{where} must be normalized from 0 through 1")
    return number


def _asset(value: Any, where: str, root: Path, *, required: bool) -> str:
    path = _string(value, where)
    if not path.startswith("assets/") or path.endswith("/"):
        raise RegistryError(f"{where} must be an assets/ path")
    if required and not (root / path).is_file():
        raise RegistryError(f"{where} does not exist: {path}")
    return path


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RegistryError(f"cannot read {path}: {error}") from error
    return _object(value, "registry")


def validate_registry(registry: dict[str, Any], root: Path = ROOT) -> list[dict[str, Any]]:
    if registry.get("version") != REGISTRY_VERSION:
        raise RegistryError("registry version must be 1")
    entries = registry.get("collectibles")
    if not isinstance(entries, list) or not entries:
        raise RegistryError("registry collectibles must be a nonempty array")
    if len(entries) > MAX_ID + 1:
        raise RegistryError(f"registry may contain at most {MAX_ID + 1} collectibles")

    seen_ids: set[int] = set()
    seen_slugs: set[str] = set()
    seen_games: set[str] = set()
    seen_titles: set[str] = set()
    for offset, raw_entry in enumerate(entries):
        entry = _object(raw_entry, f"collectible {offset}")
        where = f"collectible {offset}"
        identifier = _integer(entry.get("id"), f"{where} id")
        if identifier < 0 or identifier > MAX_ID:
            raise RegistryError(f"{where} id must be from 0 through {MAX_ID}")
        if identifier in seen_ids:
            raise RegistryError(f"{where} reuses id {identifier}")
        seen_ids.add(identifier)

        slug = _string(entry.get("slug"), f"{where} slug")
        if not SLUG_PATTERN.fullmatch(slug):
            raise RegistryError(f"{where} slug is invalid: {slug}")
        if slug in seen_slugs:
            raise RegistryError(f"{where} reuses slug {slug}")
        seen_slugs.add(slug)

        source = _object(entry.get("source"), f"{where} source")
        source_kind = _string(source.get("kind"), f"{where} source.kind")
        if source_kind not in SOURCE_KINDS:
            raise RegistryError(f"{where} source.kind is unsupported: {source_kind}")
        expected_fields = SOURCE_FIELDS[source_kind]
        if set(source) != {"kind", *expected_fields}:
            raise RegistryError(f"{where} source fields do not match {source_kind}")
        if source_kind == "book":
            _asset(source["page"], f"{where} source.page", root, required=True)
        elif source_kind == "story":
            story = _string(source["story"], f"{where} source.story")
            page = _string(source["page"], f"{where} source.page")
            if not SLUG_PATTERN.fullmatch(story) or not SOURCE_REF_PATTERN.fullmatch(page):
                raise RegistryError(f"{where} story source references are invalid")
        elif source_kind == "game":
            game = _string(source["game"], f"{where} source.game")
            if not game.endswith(".zx") or game == ".zx":
                raise RegistryError(f"{where} source.game must be a .zx bundle")
            if game in seen_games:
                raise RegistryError(f"{where} reuses game bundle {game}")
            seen_games.add(game)
        else:
            scene = _string(source["scene"], f"{where} source.scene")
            if not SLUG_PATTERN.fullmatch(scene):
                raise RegistryError(f"{where} source.scene is invalid")
            if scene in seen_titles:
                raise RegistryError(f"{where} reuses title scene {scene}")
            seen_titles.add(scene)

        how = _object(entry.get("how"), f"{where} how")
        how_kind = _string(how.get("kind"), f"{where} how.kind")
        if how_kind not in HOW_KINDS:
            raise RegistryError(f"{where} how.kind is unsupported: {how_kind}")
        if how_kind == "tap":
            if set(how) != {"kind", "x", "y", "rx", "ry"}:
                raise RegistryError(f"{where} tap fields are invalid")
            x = _unit(how["x"], f"{where} how.x")
            y = _unit(how["y"], f"{where} how.y")
            rx = _unit(how["rx"], f"{where} how.rx")
            ry = _unit(how["ry"], f"{where} how.ry")
            if rx <= 0.0 or ry <= 0.0:
                raise RegistryError(f"{where} tap ellipse radii must be positive")
            if x - rx < 0.0 or x + rx > 1.0 or y - ry < 0.0 or y + ry > 1.0:
                raise RegistryError(f"{where} tap ellipse leaves the picture")
        else:
            # A title paper lies at x, y in the landscape picture and at portrait.x, portrait.y
            # in the portrait one, each normalized to its own picture.
            paper_fields = {"kind", "x", "y", "portrait"} if source_kind == "title" else {"kind"}
            if set(how) != paper_fields:
                raise RegistryError(f"{where} paper fields are invalid")
            if source_kind == "title":
                _unit(how["x"], f"{where} how.x")
                _unit(how["y"], f"{where} how.y")
                portrait = _object(how["portrait"], f"{where} how.portrait")
                if set(portrait) != {"x", "y"}:
                    raise RegistryError(f"{where} portrait paper fields are invalid")
                _unit(portrait["x"], f"{where} how.portrait.x")
                _unit(portrait["y"], f"{where} how.portrait.y")

        pending = entry.get("pending", False)
        if not isinstance(pending, bool):
            raise RegistryError(f"{where} pending must be boolean")
        _asset(entry.get("color"), f"{where} color", root, required=not pending)

        paint = _object(entry.get("paint"), f"{where} paint")
        paint_kind = _string(paint.get("kind"), f"{where} paint.kind")
        if paint_kind not in PAINT_KINDS:
            raise RegistryError(f"{where} paint.kind is unsupported: {paint_kind}")
        category = _string(paint.get("category"), f"{where} paint.category")
        if category not in PAINT_CATEGORIES:
            raise RegistryError(f"{where} paint.category is unsupported: {category}")
        if paint_kind == "scene" and category != "places":
            raise RegistryError(f"{where} scene paint category must be places")
        if paint_kind == "stencil" and category == "places":
            raise RegistryError(f"{where} stencil paint category must be animals or objects")
        if set(paint) != {"kind", "category", "art"}:
            raise RegistryError(f"{where} paint fields are invalid")
        art = paint.get("art")
        if art is not None:
            art = _integer(art, f"{where} paint.art")
            if art < 0:
                raise RegistryError(f"{where} paint.art must be null or nonnegative")

    return entries


def _source_ref(entry: dict[str, Any]) -> str:
    source = entry["source"]
    kind = source["kind"]
    if kind == "book":
        return source["page"]
    if kind == "game":
        return source["game"]
    if kind == "title":
        return source["scene"]
    return f"{source['story']}/{source['page']}"


def _floats(values: list[float]) -> str:
    return ", ".join(f"{value:.6f}" for value in values)


def _strings(values: list[str]) -> str:
    return ", ".join(json.dumps(value, ensure_ascii=False) for value in values)


def _ints(values: list[int]) -> str:
    return ", ".join(str(value) for value in values)


def render_catalog(entries: list[dict[str, Any]]) -> str:
    ordered = sorted(entries, key=lambda entry: entry["id"])
    count = len(ordered)
    source_kinds = [SOURCE_KINDS[entry["source"]["kind"]] for entry in ordered]
    how_kinds = [HOW_KINDS[entry["how"]["kind"]] for entry in ordered]
    paint_kinds = [PAINT_KINDS[entry["paint"]["kind"]] for entry in ordered]
    categories = [PAINT_CATEGORIES[entry["paint"]["category"]] for entry in ordered]
    arts = [-1 if entry["paint"]["art"] is None else entry["paint"]["art"] for entry in ordered]
    lines = [
        "// Generated by tools/collectibles.py from tools/collectibles.json.",
        "// Collectible IDs are stable and helper returns are zero-based array indices.",
        "",
        f"COLLECTIBLE_COUNT :: {count}",
        "COLLECTIBLE_SOURCE_BOOK :: 0",
        "COLLECTIBLE_SOURCE_STORY :: 1",
        "COLLECTIBLE_SOURCE_GAME :: 2",
        "COLLECTIBLE_SOURCE_TITLE :: 3",
        "COLLECTIBLE_HOW_TAP :: 0",
        "COLLECTIBLE_HOW_PAPER :: 1",
        "COLLECTIBLE_PAINT_STENCIL :: 0",
        "COLLECTIBLE_PAINT_SCENE :: 1",
        "COLLECTIBLE_CATEGORY_ANIMALS :: 0",
        "COLLECTIBLE_CATEGORY_OBJECTS :: 1",
        "COLLECTIBLE_CATEGORY_PLACES :: 2",
        "",
        f"collectible_slugs: [{count}]string = .[{_strings([entry['slug'] for entry in ordered])}];",
        f"collectible_ids: [{count}]s32 = .[{_ints([entry['id'] for entry in ordered])}];",
        f"collectible_source_kinds: [{count}]s32 = .[{_ints(source_kinds)}];",
        f"collectible_source_refs: [{count}]string = .[{_strings([_source_ref(entry) for entry in ordered])}];",
        f"collectible_how_kinds: [{count}]s32 = .[{_ints(how_kinds)}];",
        f"collectible_x: [{count}]float32 = .[{_floats([entry['how'].get('x', 0.0) for entry in ordered])}];",
        f"collectible_y: [{count}]float32 = .[{_floats([entry['how'].get('y', 0.0) for entry in ordered])}];",
        (
            f"collectible_rx: [{count}]float32 = .[{_floats([entry['how'].get('rx', 0.0) for entry in ordered])}];"
        ),
        (
            f"collectible_ry: [{count}]float32 = .[{_floats([entry['how'].get('ry', 0.0) for entry in ordered])}];"
        ),
        "// A title paper's place in the portrait picture; collectible_x/y hold the landscape one.",
        (
            f"collectible_portrait_x: [{count}]float32 = "
            f".[{_floats([entry['how'].get('portrait', {}).get('x', 0.0) for entry in ordered])}];"
        ),
        (
            f"collectible_portrait_y: [{count}]float32 = "
            f".[{_floats([entry['how'].get('portrait', {}).get('y', 0.0) for entry in ordered])}];"
        ),
        f"collectible_colors: [{count}]string = .[{_strings([entry['color'] for entry in ordered])}];",
        # A pending picture is not painted or bundled yet: show only a sparkle.
        f"collectible_color_ready: [{count}]bool = .[{', '.join('false' if entry['pending'] else 'true' for entry in ordered)}];",
        f"collectible_paint_kinds: [{count}]s32 = .[{_ints(paint_kinds)}];",
        f"collectible_paint_categories: [{count}]s32 = .[{_ints(categories)}];",
        f"collectible_paint_arts: [{count}]s32 = .[{_ints(arts)}];",
        "",
        "CollectibleBySlug :: (slug: string) -> s32 {",
        "    for index: cast(s32)0..COLLECTIBLE_COUNT - 1 {",
        "        if collectible_slugs[index] == slug { return index }",
        "    }",
        "    return -1",
        "}",
        "",
        "CollectibleById :: (id: s32) -> s32 {",
        "    for index: cast(s32)0..COLLECTIBLE_COUNT - 1 {",
        "        if collectible_ids[index] == id { return index }",
        "    }",
        "    return -1",
        "}",
        "",
        "CollectibleForPage :: (path: string) -> s32 {",
        "    for index: cast(s32)0..COLLECTIBLE_COUNT - 1 {",
        "        if collectible_source_kinds[index] == COLLECTIBLE_SOURCE_BOOK &&",
        "            collectible_source_refs[index] == path { return index }",
        "    }",
        "    return -1",
        "}",
        "",
        "CollectibleForStory :: (story: string, story_page: string) -> s32 {",
        "    length := story.count + 1 + story_page.count",
        "    for index: cast(s32)0..COLLECTIBLE_COUNT - 1 {",
        "        ref := collectible_source_refs[index]",
        "        if collectible_source_kinds[index] == COLLECTIBLE_SOURCE_STORY && ref.count == length &&",
        "            ref[:story.count] == story && ref[story.count] == #char \"/\" &&",
        "            ref[story.count + 1:] == story_page { return index }",
        "    }",
        "    return -1",
        "}",
        "",
        "// NX and NY are normalized to the picture holding the subject: a book page's whole",
        "// picture, or a story page's illustrated section above its paper.",
        "CollectibleTapHit :: (index: s32, nx: float32, ny: float32) -> bool {",
        "    if index < 0 || index >= COLLECTIBLE_COUNT || collectible_how_kinds[index] != COLLECTIBLE_HOW_TAP { return false }",
        "    dx := (nx - collectible_x[index]) / collectible_rx[index]",
        "    dy := (ny - collectible_y[index]) / collectible_ry[index]",
        "    return dx * dx + dy * dy <= 1.0",
        "}",
        "",
        "CollectibleForGame :: (bundle: string) -> s32 {",
        "    for index: cast(s32)0..COLLECTIBLE_COUNT - 1 {",
        "        if collectible_source_kinds[index] == COLLECTIBLE_SOURCE_GAME &&",
        "            collectible_source_refs[index] == bundle { return index }",
        "    }",
        "    return -1",
        "}",
        "",
        "CollectibleForTitle :: (scene: string) -> s32 {",
        "    for index: cast(s32)0..COLLECTIBLE_COUNT - 1 {",
        "        if collectible_source_kinds[index] == COLLECTIBLE_SOURCE_TITLE &&",
        "            collectible_source_refs[index] == scene { return index }",
        "    }",
        "    return -1",
        "}",
        "",
    ]
    return "\n".join(lines)


def write_catalog(text: str, path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate and compare the generated catalog")
    arguments = parser.parse_args(argv)
    try:
        entries = validate_registry(load_registry())
        text = render_catalog(entries)
        if arguments.check:
            try:
                current = OUTPUT_PATH.read_text(encoding="utf-8")
            except OSError as error:
                raise RegistryError(f"cannot read {OUTPUT_PATH}: {error}") from error
            if current != text:
                raise RegistryError(f"generated catalog is stale: {OUTPUT_PATH}")
        else:
            write_catalog(text)
    except RegistryError as error:
        print(f"collectibles: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

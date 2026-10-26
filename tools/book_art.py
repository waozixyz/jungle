"""Cut the generated watercolor atlas into the book's illustrated pages."""
from pathlib import Path
import json
from math import ceil
import sys
from PIL import Image
from book_cutout import illustration
from book_catalog import BOOKS, NAMES, ADDED, WORDS, LANGUAGES, narration, voice_path, EXPANSION, TITLES

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "art/generated/picture-book-watercolors.png"
EXTRA_SOURCE = ROOT / "art/generated/picture-book-more-animals.png"
ORIGINAL = ("tiger", "frog", "butterfly", "ladybug", "snail", "flower", "banana", "mango", "coconut", "rabbit", "cat", "mouse", "pig", "cow")
EXTRA = ("elephant", "giraffe", "monkey", "panda", "lion", "zebra", "crocodile", "parrot", "toucan", "dog", "horse", "sheep")
CROP_FIXED = ("panda", "crocodile", "parrot", "toucan")
FIXED_SOURCE = ROOT / "art/generated/picture-book-uncropped.png"
ADDED_SOURCE = ROOT / "art/generated/picture-book-fruits-farm.png"


def main():
    catalog_only = "--catalog-only" in sys.argv
    new_only = "--new-only" in sys.argv
    only = sys.argv[sys.argv.index("--only")+1] if "--only" in sys.argv else None
    source = Image.open(SOURCE).convert("RGBA")
    assert source.width == source.height and source.width >= 1024
    extra_source = Image.open(EXTRA_SOURCE).convert("RGBA")
    assert extra_source.width == extra_source.height and extra_source.width >= 1024
    added_source = Image.open(ADDED_SOURCE).convert("RGBA")
    fixed_source = Image.open(FIXED_SOURCE).convert("RGBA")
    output = ROOT / "assets/jungle-book/items"
    previews = ROOT / "assets/jungle-book/previews"
    output.mkdir(parents=True, exist_ok=True)
    previews.mkdir(parents=True, exist_ok=True)
    atlases = {slug: (ROOT / "art/generated" / (slug + ".png")) for slug in EXPANSION["atlases"]} if not catalog_only else {}
    isolated = json.loads((ROOT/"tools/book_isolated.json").read_text())
    atlases.update({slug:(ROOT/"art/generated"/(slug+".png")) for slug in isolated} if not catalog_only else {})
    atlas_names = {**EXPANSION["atlases"], **isolated}
    locations = {name: (atlases[slug], index, 1 if len(names) == 1 else 4) for slug, names in atlas_names.items() for index, name in enumerate(names)} if not catalog_only else {}
    pages = []
    for name in NAMES:
        if catalog_only:
            pages.append(None)
            continue
        if (new_only and (output / (name + ".png")).exists()) or (only and name != only):
            pages.append(Image.open(output / (name + ".png")).convert("RGBA"))
            continue
        if name in locations:
            atlas, index, columns = locations[name]
        elif name in CROP_FIXED:
            atlas, index, columns = fixed_source, CROP_FIXED.index(name), 2
        elif name in ORIGINAL:
            atlas, index, columns = source, ORIGINAL.index(name), 4
        elif name in EXTRA:
            atlas, index, columns = extra_source, EXTRA.index(name), 4
        else:
            atlas, index, columns = added_source, ADDED.index(name), 4
        if isinstance(atlas, Path): atlas = Image.open(atlas).convert("RGBA")
        if name in dict(BOOKS)["nature"]:
            row, column = divmod(index, columns)
            page = atlas.crop((round(column*atlas.width/columns)+3,round(row*atlas.height/columns)+3,
                               round((column+1)*atlas.width/columns)-3,round((row+1)*atlas.height/columns)-3)).resize((420,420),Image.Resampling.LANCZOS)
        else:
            page = illustration(atlas, index, columns, name)
        page.save(output / (name + ".png"), optimize=True)
        pages.append(page)
    starts = []
    index = 0
    for category, names in BOOKS:
        starts.append(index)
        if not catalog_only and not (new_only and (previews / (category + ".png")).exists()):
            preview = pages[NAMES.index("family")] if category == "family" else pages[index]
            if "cover-" + category in locations:
                atlas, cell, columns = locations["cover-" + category]
                if isinstance(atlas, Path): atlas = Image.open(atlas).convert("RGBA")
                row, column = divmod(cell, columns)
                preview = atlas.crop(tuple(round(v) for v in (column*atlas.width/4, row*atlas.height/4, (column+1)*atlas.width/4, (row+1)*atlas.height/4)))
            preview.resize((420, 420), Image.Resampling.LANCZOS).save(previews / (category + ".png"), optimize=True)
        index += len(names)
    if not catalog_only:
        pages[0].resize((64, 64), Image.Resampling.LANCZOS).save(ROOT / "assets/jungle/book.png", optimize=True)
        sheet = Image.new("RGB", (840, 210 * ceil(len(pages) / 4)), "#f9f6eb")
        for index, page in enumerate(pages):
            thumb = page.resize((210, 210), Image.Resampling.LANCZOS)
            sheet.paste(thumb, (index % 4 * 210, index // 4 * 210), thumb)
        sheet.save(ROOT / "art/generated/picture-book-preview.png", optimize=True)
    counts = ", ".join(str(len(names)) for _, names in BOOKS)
    catalog = "// Generated by tools/book_art.py from the illustrated books.\n"
    catalog += f"CATEGORY_COUNT :: {len(BOOKS)}\n"
    catalog += f"category_counts: [{len(BOOKS)}]s32 = .{{{counts}}};\n"
    catalog += f"category_starts: [{len(BOOKS)}]s32 = .[" + ", ".join(map(str, starts)) + "];\n"
    order = [c for c in ("jungle", "garden", "farm", "nature", "fruits", "vegetables", "breakfast", "lunch", "dinner", "kitchen", "bathroom", "bedroom", "living-room", "family", "body") if c in dict(BOOKS)]
    catalog += f"shelf_order: [{len(BOOKS)}]s32 = .[" + ", ".join(str([c for c, _ in BOOKS].index(c)) for c in order) + "];\n"
    groups = [("Nature", ["jungle","garden","farm","nature"]), ("Food", ["fruits","vegetables","breakfast","lunch","dinner"]), ("Home", ["kitchen","bathroom","bedroom","living-room"]), ("Family", ["family","body"])]
    catalog += 'book_groups: [4]string = .["Nature", "Food", "Home", "Family"];\n'
    catalog += 'group_starts: [4]s32 = .[0,4,9,13];\ngroup_counts: [4]s32 = .[4,5,4,2];\n'
    catalog += 'category_groups: [15]s32 = .[' + ','.join(str(next(i for i,(_,members) in enumerate(groups) if c in members)) for c,_ in BOOKS) + '];\n'
    backdrops = {c:('food' if c in groups[1][1] else 'family' if c == 'family' else c) for c,_ in BOOKS}
    catalog += 'category_backdrops: [15]string = .[' + ','.join(json.dumps('assets/jungle-book/backgrounds/'+backdrops[c]+'.png') for c,_ in BOOKS) + '];\n'
    catalog += f"category_names: [{len(BOOKS)}]string = .[" + ", ".join(json.dumps(TITLES[c][0]) for c, _ in BOOKS) + "];\n"
    catalog += f"category_previews: [{len(BOOKS)}]string = .[" + ", ".join(json.dumps("assets/jungle-book/previews/" + c + ".png") for c, _ in BOOKS) + "];\n"
    catalog += string_table("page_paths", [f"assets/jungle-book/items/{name}.png" for name in NAMES])
    for language_index, language in enumerate(LANGUAGES):
        catalog += string_table(f"page_names_{language}", [WORDS[name][language_index] for name in NAMES])
        catalog += string_table(f"page_spelling_{language}", [" ".join(WORDS[name][language_index].upper()) for name in NAMES])
    (ROOT / "games/book/book_pages.zi").write_text(catalog)
    voices = "// Generated from verified, measured recordings by tools/book_art.py.\n"
    for language in LANGUAGES:
        for simple in (False, True):
            suffix = language + ("_simple" if simple else "_spelling")
            paths = [voice_path(name, language, simple) for name in NAMES]
            durations = []
            for name, path in zip(NAMES, paths):
                receipt = json.loads((ROOT / path).with_suffix(".speech.json").read_text())
                assert receipt["text"] == narration(name, language, simple), (name, language, simple)
                durations.append(receipt["duration"])
            for start in range(0, len(paths), 48):
                chunk = paths[start:start+48]
                voices += f"voice_paths_{suffix}_{start}: [{len(chunk)}]string = .[\n"
                voices += "".join(f'    "{path}",\n' for path in chunk) + "];\n"
            voices += f"VoicePath_{suffix} :: (at: s32) -> string {{\n"
            for start in range(0, len(paths), 48):
                voices += f"    if at < {min(start+48,len(paths))} {{ return voice_paths_{suffix}_{start}[at - {start}] }}\n"
            voices += '    return ""\n}\n'
            for start in range(0, len(durations), 48):
                chunk = durations[start:start+48]
                voices += f"voice_seconds_{suffix}_{start}: [{len(chunk)}]float64 = .[\n" + "".join(f"    {duration:.6f},\n" for duration in chunk) + "];\n"
            voices += f"VoiceSeconds_{suffix} :: (at: s32) -> float64 {{\n"
            for start in range(0, len(durations), 48):
                voices += f"    if at < {min(start+48,len(durations))} {{ return voice_seconds_{suffix}_{start}[at - {start}] }}\n"
            voices += "    return 0.0\n}\n"
    (ROOT / "games/book/book_voice.zi").write_text(voices)
    print(f"Prepared {len(pages)} watercolor pages, category covers, word lists and narration timings")


def string_table(name, values):
    output = ""
    for start in range(0, len(values), 48):
        chunk = values[start:start+48]
        output += f"{name}_{start}: [{len(chunk)}]string = .[\n"
        output += "".join("    " + json.dumps(value, ensure_ascii=False) + ",\n" for value in chunk) + "];\n"
    output += f"{name} :: (at: s32) -> string {{\n"
    for start in range(0, len(values), 48):
        output += f"    if at < {min(start+48,len(values))} {{ return {name}_{start}[at - {start}] }}\n"
    return output + '    return ""\n}\n'


if __name__ == "__main__":
    main()

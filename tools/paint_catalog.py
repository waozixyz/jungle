#!/usr/bin/env python3
"""Generate the stable coloring library; validate its vector masters.

python3 tools/paint_catalog.py          # metadata -> paint_catalog.zi
python3 tools/paint_catalog.py --check  # verify reproducibility, without writes
python3 tools/paint_catalog.py --art    # also validate all SVG geometry

The committed JSON is the production source. Ignored generation jobs and raw
PNGs are unnecessary for catalog generation or tests. IDs are one-based asset
filenames; all generated indices and category order maps are zero-based.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / 'tools/coloring_catalog.json'
REGISTRY = ROOT / 'tools/collectibles.json'
GENERATED = ROOT / 'games/paint/paint_catalog.zi'
LANGUAGES = ('en', 'de', 'es')
ORIGINAL_COUNTS = {'stencil': 30, 'scene': 12}


def collectible_ids(metadata, registry):
    """Each entry's registry id (-1 for defaults), proving catalog and registry agree.

    The registry's paint.art is the one-based asset ID of the same stencil or scene.
    """
    rows = {row['slug']: row for row in registry['collectibles']}
    used = set()
    ids = {}
    for kind in ('stencil', 'scene'):
        ids[kind] = []
        for entry in metadata[kind + 's']:
            slug = entry.get('collectible')
            if slug is None:
                ids[kind].append(-1)
                continue
            row = rows.get(slug)
            if row is None:
                raise ValueError(f'Unknown collectible slug: {slug}')
            if slug in used:
                raise ValueError(f'Collectible used twice: {slug}')
            used.add(slug)
            paint = row['paint']
            if paint['kind'] != kind or paint['art'] != entry['asset_id']:
                raise ValueError(f'Collectible {slug} paint must be {kind} art {entry["asset_id"]}')
            if paint['category'] != entry['category']:
                raise ValueError(f'Collectible {slug} category differs: {paint["category"]}')
            ids[kind].append(row['id'])
    for slug, row in rows.items():
        if row['paint']['art'] is not None and slug not in used:
            raise ValueError(f'Collectible {slug} has art but no catalog entry')
    return ids


def BuildPaintCatalog(metadata=None, registry=None):
    """Validate metadata and derive category maps without changing asset IDs."""
    if metadata is None:
        metadata = json.loads(METADATA.read_text(encoding='utf-8'))
    if registry is None:
        registry = json.loads(REGISTRY.read_text(encoding='utf-8'))
    if metadata.get('version') != 1:
        raise ValueError('Unsupported coloring catalog version')
    catalog = {}

    def labels(row, field='labels'):
        values = row.get(field, {})
        if set(values) != set(LANGUAGES) or any(
                not isinstance(value, str) or not value.strip()
                for value in values.values()):
            raise ValueError(f'Missing localized {field}: {row}')
        if any(ord(char) >= 256 for value in values.values() for char in value):
            raise ValueError(f'Label outside the UI font: {values}')

    for kind in ('stencil', 'scene'):
        categories = metadata[kind + '_categories']
        keys = [row['key'] for row in categories]
        if not keys or len(keys) != len(set(keys)):
            raise ValueError(f'Duplicate or empty {kind} categories')
        for row in categories:
            labels(row)
        entries = metadata[kind + 's']
        if [row['asset_id'] for row in entries] != list(range(1, len(entries) + 1)):
            raise ValueError(f'{kind} asset IDs must stay in contiguous asset order')
        if len({row['slug'] for row in entries}) != len(entries):
            raise ValueError(f'Duplicate {kind} slugs')
        category_for_index = []
        for row in entries:
            labels(row)
            if kind == 'stencil':
                labels(row, 'short_labels')
            if row['category'] not in keys:
                raise ValueError(f'Unknown {kind} category: {row["category"]}')
            category_for_index.append(keys.index(row['category']))
            prefix = 'dino' if kind == 'stencil' else 'scene'
            expected = f'art/paint/{prefix}{row["asset_id"]}.svg'
            if row.get('source') != expected:
                raise ValueError(f'Invalid {kind} source; expected {expected}')
        order, starts, counts = [], [], []
        for category in range(len(keys)):
            members = [i for i, group in enumerate(category_for_index) if group == category]
            if not members:
                raise ValueError(f'Empty {kind} category: {keys[category]}')
            starts.append(len(order))
            counts.append(len(members))
            order.extend(members)
        catalog[kind + 's'] = entries
        catalog[kind + '_categories'] = categories
        catalog[kind + '_order'] = order
        catalog[kind + '_category_starts'] = starts
        catalog[kind + '_category_counts'] = counts
        catalog[kind + '_category_for_index'] = category_for_index
    ids = collectible_ids(metadata, registry)
    for kind in ('stencil', 'scene'):
        catalog[kind + '_collectibles'] = ids[kind]
    return catalog


def render_catalog(catalog=None):
    if catalog is None:
        catalog = BuildPaintCatalog()
    lines = [
        '// Generated by tools/paint_catalog.py from tools/coloring_catalog.json.',
        '// Asset IDs remain stable; order maps contain zero-based asset indices.',
        '#import, file "../../retro/language.zi";',
        '',
    ]

    def array(name, values, kind):
        encoded = [json.dumps(v, ensure_ascii=False) if kind == 'string' else str(v)
                   for v in values]
        lines.append(f'{name}: [{len(values)}]{kind} = .[' + ', '.join(encoded) + '];')

    for kind in ('stencil', 'scene'):
        upper, title = kind.upper(), kind.title()
        entries, categories = catalog[kind + 's'], catalog[kind + '_categories']
        lines.extend([f'PAINT_{upper}_COUNT :: {len(entries)}',
                      f'PAINT_{upper}_CATEGORY_COUNT :: {len(categories)}'])
        for field in ('order', 'category_starts', 'category_counts', 'category_for_index', 'collectibles'):
            array(f'paint_{kind}_{field}', catalog[f'{kind}_{field}'], 's32')
        fields = [('labels', '', entries), ('labels', '_category', categories)]
        if kind == 'stencil':
            fields.append(('short_labels', '_short', entries))
        for field, suffix, rows in fields:
            for language in LANGUAGES:
                array(f'paint_{kind}{suffix}_labels_{language}',
                      [row[field][language] for row in rows], 'string')
            label_kind = 'Category' if suffix == '_category' else 'Short' if suffix else ''
            limit = f'PAINT_{upper}_CATEGORY_COUNT' if suffix == '_category' else f'PAINT_{upper}_COUNT'
            lines.extend([
                '', f'Paint{title}{label_kind}Label :: (index: s32) -> string {{',
                f'    if index < 0 || index >= {limit} {{ return "" }}',
                '    code := LanguageCode()',
                f'    if code == "de" {{ return paint_{kind}{suffix}_labels_de[index] }}',
                f'    if code == "es" {{ return paint_{kind}{suffix}_labels_es[index] }}',
                f'    return paint_{kind}{suffix}_labels_en[index]', '}', '',
            ])
        lines.extend([
            f'Paint{title}Category :: (index: s32) -> s32 {{',
            f'    if index < 0 || index >= PAINT_{upper}_COUNT {{ return -1 }}',
            f'    return paint_{kind}_category_for_index[index]', '}', '',
            '// The registry id that unlocks this entry; -1 for a default.',
            f'Paint{title}Collectible :: (index: s32) -> s32 {{',
            f'    if index < 0 || index >= PAINT_{upper}_COUNT {{ return -1 }}',
            f'    return paint_{kind}_collectibles[index]', '}', '',
            f'Paint{title}At :: (category: s32, offset: s32) -> s32 {{',
            f'    if category < 0 || category >= PAINT_{upper}_CATEGORY_COUNT {{ return -1 }}',
            f'    if offset < 0 || offset >= paint_{kind}_category_counts[category] {{ return -1 }}',
            f'    return paint_{kind}_order[paint_{kind}_category_starts[category] + offset]',
            '}', '',
        ])
    return '\n'.join(lines)


def compile_new_art(catalog):
    """Validate committed vector masters; raster tracing is an explicit import.

    Source PNGs are private reference archives, never production dependencies.
    Rebuild previews/masks with paint_pages.py and KVP1 with paint_vectors.py.
    """
    sources = [row['source'] for kind in ('stencils', 'scenes') for row in catalog[kind]]
    missing = [source for source in sources if not (ROOT / source).is_file()]
    if missing:
        raise FileNotFoundError('Missing coloring SVG inputs:\n' + '\n'.join(missing))
    from paint_vectors import validate_source
    for source in sources:
        validate_source(ROOT / source)
    print(f'Validated {len(sources)} vector masters; no source artwork changed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='compare generated Ziran without writes')
    mode.add_argument('--art', action='store_true', help='validate production SVG masters without retracing artwork')
    args = parser.parse_args()
    try:
        catalog = BuildPaintCatalog()
        code = render_catalog(catalog)
        if args.check:
            if not GENERATED.is_file() or GENERATED.read_text(encoding='utf-8') != code:
                parser.exit(1, 'paint_catalog.zi differs; run python3 tools/paint_catalog.py\n')
        else:
            if args.art:
                compile_new_art(catalog)
            GENERATED.write_text(code, encoding='utf-8')
        print(f'Coloring catalog: {len(catalog["stencils"])} stencils, '
              f'{len(catalog["scenes"])} scenes, complete EN/DE/ES labels.')
    except (KeyError, ValueError, FileNotFoundError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()

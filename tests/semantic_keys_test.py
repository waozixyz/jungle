"""Semantic control keys never collide with the title path-sign key range.

Path signs press with TITLE_SIGN_KEY_BASE + hotspot (host/jungle_menu.zi).
Every other RetroTap id and Press/element key in the app is a literal, a named
literal constant, or a literal base plus an index. This fails when any of them
could reach the sign range (with a 65536-wide allowance for an index below
it), or when the hotspot table outgrows the reserved span.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('host', 'games', 'retro', 'web')
INDEX_ALLOWANCE = 65536
NUMBER = r'(0x[0-9a-fA-F_]+|\d+)'
CONSTANT = re.compile(r'^\s*([A-Z][A-Z0-9_]*)\s*::\s*' + NUMBER + r'\s*$', re.M)
# A RetroTap id, a .key/.id field, or an AlbumTapId-style "then/else N + i".
KEYED = re.compile(r'RetroTap\(\s*([^,]+),|\.(?:key|id)\s*=\s*([^,}]+)|(?:then|else)\s+(\d+)\s*\+')


def value(text):
    return int(text.replace('_', ''), 0)


def bases(expression, constants):
    """The literal or named base a key expression starts from, if any."""
    expression = re.sub(r'cast\(u64\)|[()\s]', '', expression)
    head = re.match(r'(' + NUMBER + r'|[A-Z][A-Z0-9_]*)', expression)
    if not head:
        return None
    token = head.group(1)
    if token in constants:
        return token, constants[token]
    if token[0].isdigit():
        return token, value(token)
    return None


def scan(texts):
    constants = {}
    for text in texts.values():
        constants.update({name: value(number) for name, number in CONSTANT.findall(text)})
    found = []
    for path, text in texts.items():
        for match in KEYED.finditer(text):
            expression = next(group for group in match.groups() if group)
            base = bases(expression, constants)
            if base:
                line = text.count('\n', 0, match.start()) + 1
                found.append((f'{path}:{line}', base[0], base[1]))
    return constants, found


def collisions(texts):
    constants, found = scan(texts)
    start, span = constants['TITLE_SIGN_KEY_BASE'], constants['TITLE_SIGN_KEY_SPAN']
    return [(where, name, key) for where, name, key in found if name != 'TITLE_SIGN_KEY_BASE'
            and key < start + span and key + INDEX_ALLOWANCE > start]


def main():
    texts = {str(p.relative_to(ROOT)): p.read_text() for folder in SOURCES
             for p in sorted((ROOT/folder).rglob('*.zi'))}
    constants, found = scan(texts)
    assert 'TITLE_SIGN_KEY_BASE' in constants and 'TITLE_SIGN_KEY_SPAN' in constants
    assert any(name == 'TITLE_SIGN_KEY_BASE' for _, name, _ in found), 'signs must press with TITLE_SIGN_KEY_BASE'
    assert len(found) > 50, f'only {len(found)} keys found; the scanner lost its patterns'
    hotspots = int(re.search(r'TITLE_HOTSPOT_COUNT :: (\d+)', texts['host/jungle_title_data.zi']).group(1))
    assert hotspots <= constants['TITLE_SIGN_KEY_SPAN'], (hotspots, 'hotspots outgrew the sign key span')
    bad = collisions(texts)
    assert not bad, f'keys inside the path-sign range: {bad}'
    # The old scheme (7400 + hotspot) reached the scene Back's RetroTap(7501).
    old = {'a.zi': 'TITLE_SIGN_KEY_BASE :: 7400\nTITLE_SIGN_KEY_SPAN :: 4096\n'
                   'back := RetroTap(7501, 6, 6, 44, 30, "Back")\n'
                   'Press(s, PressProps.{.key = cast(u64)(TITLE_SIGN_KEY_BASE + hotspot),'}
    assert collisions(old) == [('a.zi:3', '7501', 7501)], collisions(old)
    print(f'local semantic key test: {len(found)} keys stay clear of {hotspots} path-sign keys')


if __name__ == '__main__':
    sys.exit(main())

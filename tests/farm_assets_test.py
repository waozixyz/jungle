"""The new native farm has a complete, portable storybook art contract."""
from pathlib import Path
from PIL import Image
import json
import hashlib

ROOT = Path(__file__).resolve().parents[1]
CROPS = ('sunflower', 'tomato', 'carrot', 'strawberry', 'pumpkin', 'cabbage',
         'beans', 'corn', 'cucumber')
OBJECTS = CROPS + ('sprout', 'watering-can', 'harvest-basket', 'seed-pouch',
                   'compost-bag', 'sprinkler', 'market-stall', 'hand-cupped', 'goji',
                   'soil-mound', 'soil-mound-wet') + tuple('seed-'+crop for crop in CROPS)

def main():
    manifests=[json.loads((ROOT/'tools/art_provenance'/name).read_text())
               for name in ('four-gardens-play.json','four-gardens-extended.json','four-gardens-seeds.json')]
    expected=set(OBJECTS)|{'garden-landscape','garden-portrait'}
    rows=[row for manifest in manifests for row in manifest['assets']]
    assert {row['name'] for row in rows}==expected and len(rows)==31
    for row in rows:
        path=ROOT/row['runtime']
        assert path==ROOT/f"assets/garden/play/{row['name']}.webp"
        with path.open('rb') as stream:
            assert hashlib.file_digest(stream,'sha256').hexdigest()==row['sha256'],row['name']
        with Image.open(path) as picture:
            assert list(picture.size)==row['dimensions'],row['name']
        if row['name'] in OBJECTS:
            assert row['lossless'] is True and row['export_role']=='cutout'
        else:
            assert row['quality']==85 and row['export_role']=='scene'
    for name in OBJECTS:
        with Image.open(ROOT/f'assets/garden/play/{name}.webp') as picture:
            assert max(picture.size) >= 700, (name, picture.size)
            assert picture.mode == 'RGBA', name
            assert picture.getchannel('A').getextrema() == (0, 255), name
    for orientation, size in (('landscape', (1536, 1024)), ('portrait', (1024, 1536))):
        with Image.open(ROOT/f'assets/garden/play/garden-{orientation}.webp') as picture:
            assert picture.size == size
            assert 'A' not in picture.getbands() or picture.getchannel('A').getextrema() == (255, 255)
    source = (ROOT/'games/garden/jungle_garden.zi').read_text()
    assert 'GameSound(' not in source and 'jungle.voice' not in source
    assert 'DocumentRead("garden.txt")' not in source and 'DocumentWrite("garden.txt"' not in source
    assert 'AppIdentity("jungle.garden")' in source
    assert 'DocumentFlush()' in source
    assert 'FarmSow(' in source and 'FarmMove(' in source and 'FarmUnsow(' in source and 'CursorSet(' in source
    assert 'farm-four-gardens.backup' in source and 'farm-four-gardens.damaged' in source
    assert 'hand-cupped' in source and 'SeedArt(' in source and 'soil-mound' in source
    # No tutorial, tips or help screen: the farm is read from its pictures.
    for gone in ('Notice(', 'Help()', '"?"', 'How to grow', 'note_until'):
        assert gone not in source, gone
    host=(ROOT/'host/jungle_host.zi').read_text()
    assert 'jungle.farm-view' in host and 'FarmEntranceSound(' in host
    data = json.loads((ROOT/'tools/title_hotspots.json').read_text())
    campus = next(s for s in data['scenes'] if s['name'] == 'campus')
    for scene in (campus, campus['portrait']):
        assert next(h for h in scene['hotspots'] if h['id'] == 'farm-path')['target'] == 'game:Farm'
    print('local farm assets: 31 new images, alpha, sizes, native routes, silence, no tutorial text and save namespace passed')

if __name__ == '__main__':
    main()

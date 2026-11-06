"""Preload closure for every catalog game, locale and speech profile, and
Picture Book's separate shelves and books."""
from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from activity_assets import BOOK_MEDIA, book_pack_groups, build_activity_manifest, source_assets
from book_catalog import BOOKS, BOOK_GROUPS, voice_path
from shared_assets import GAMES

STORIES = {'sweet-porridge': 'sweet_porridge', 'town-musicians': 'town_musicians'}


def test_activity_manifest():
    # Use the actual build data with tiny clip metadata: no encoding or asset
    # reads are needed to prove every reachable file is in the manifest.
    paths={p.relative_to(ROOT).as_posix() for p in (ROOT/'assets').rglob('*') if p.is_file() and p.suffix in ('.avif','.png','.wav')}
    voices={}
    encoded={}
    for language in ('en','de','es'):
        for folder in ('jungle-book/sounds','jungle-book/story-sounds','abc/sounds','numbers/sounds',
                       'animal-count/sounds','drums/sounds','garden/sounds','hide_seek/sounds','shapes/sounds'):
            for profile in ('normal','slow','fast'):
                base=f'assets/{folder}/{language}/test.wav'
                voice=base if profile=='normal' else f'assets/speech-profiles/{profile}/'+base[7:]
                clip=f'assets/speech/{language}/{profile}-{folder.replace("/","-")}.ogg'
                voices[voice]=[{'clip':clip,'start':0,'frames':1}]
                encoded[clip]={'path':clip};paths.add(clip)
    languages={}
    # Every book page's narration in both modes, and every story page's.
    # Only English has its own slow and fast recordings.
    book_voices=[(voice_path(name,language,simple),language) for _,names in BOOKS for name in names
                 for language in ('en','de','es') for simple in (True,False)]
    for data in STORIES.values():
        for page in json.loads((ROOT/'tools'/f'{data}.json').read_text())['pages']:
            book_voices+=[(f'assets/jungle-book/story-sounds/{language}/{page["asset"]}.wav',language) for language in ('en','de','es')]
    for at,(base,language) in enumerate(book_voices):
        for profile in ('normal','slow','fast') if language=='en' else ('normal',):
            voice=base if profile=='normal' else f'assets/speech-profiles/{profile}/'+base[7:]
            clip=f'assets/speech/{language}/{profile}-book-{at}.ogg'
            voices[voice]=[{'clip':clip,'start':0,'frames':1}]
            encoded[clip]={'path':clip};paths.add(clip);languages[clip]={'language':language}
    legacy='assets/jungle-book/sounds/legacy.wav'
    clip='assets/speech/en/normal-legacy.ogg'
    voices[legacy]=[{'clip':clip,'start':0,'frames':1}]
    encoded[clip]={'path':clip};paths.add(clip)
    speech={'voices':voices,'encoded':encoded,'clips':{**languages,clip:{'language':'en'}}}
    manifest=build_activity_manifest(ROOT,paths,speech,GAMES)
    rows=[r.split('|') for r in (ROOT/'games/catalog.txt').read_text().splitlines() if '|' in r]
    assert len(manifest['activities'])==len(rows)
    for activity,row in zip(manifest['activities'],rows):
        assert activity['id']+'.zx'==row[0]
        assert activity['cover']==row[3] and activity['cover'] in activity['files']
        assert activity['files']==sorted(set(activity['files']))
        config=GAMES.get(activity['id'],{})
        for folder in config.get('folders',()) if activity['id']!='jungle-book' else ():
            expected={p for p in paths if p.startswith(folder+'/')}
            assert expected<=set(activity['files']), (activity['id'],expected-set(activity['files']))
        for lang,profiles in activity['speech'].items():
            for profile,clips in profiles.items():
                # German and Spanish book voices fall back to their normal recording.
                assert all('/'+lang+'/' in clip and ('/'+profile+'-' in clip or clip.endswith('normal-legacy.ogg')
                           or (lang!='en' and '/normal-book-' in clip)) for clip in clips), (activity['id'],lang,profile)
        assert clip not in activity['speech']['de']['normal'] and clip not in activity['speech']['es']['normal']
        assert set(activity['files'])<=paths
        # The toucan's pictures belong to the title; no game waits for them.
        assert not [p for p in activity['files'] if p.startswith('assets/jungle/treasure/')], activity['id']
    # Picture Book: the shelf holds only covers and shelf art; every page,
    # portrait, collectible and narration belongs to exactly its own book.
    book=manifest['activities'][0]
    assert book['id']=='jungle-book'
    assert not [p for p in book['files'] if p.startswith(BOOK_MEDIA)], book['files']
    narrated={clip for entry in book['books'] for profiles in entry['speech'].values() for clips in profiles.values() for clip in clips}
    assert not narrated&{clip for profiles in book['speech'].values() for clips in profiles.values() for clip in clips}
    assert book['shelves']['']==sorted(f'assets/jungle-book/previews/{c}.avif' for c,_ in BOOKS)
    stories={name:json.loads((ROOT/'tools'/f'{data}.json').read_text())['pages'] for name,data in STORIES.items()}
    assert book['shelves']['sweet-porridge']==sorted(f'assets/jungle-book/pages/{pages[0]["asset"]}.avif' for pages in stories.values())
    order=[c for _,members in BOOK_GROUPS for c in members]
    assert [entry['id'] for entry in book['books']]==order+list(STORIES)
    catalog=dict(BOOKS)
    collectibles=json.loads((ROOT/'tools/collectibles.json').read_text())['collectibles']
    owners={}
    for entry in book['books']:
        files=entry['files']
        if entry['id'] in STORIES:
            pages=stories[entry['id']]
            landscape={f'assets/jungle-book/pages/{page["asset"]}.avif' for page in pages}
            portrait={f'assets/jungle-book/portraits/{page["portrait_asset"]}.avif' for page in pages}|landscape
            offered={c['color'] for c in collectibles if c['source']['kind']=='story' and c['source']['story']==entry['id']}
            assert entry['cover']==f'assets/jungle-book/pages/{pages[0]["asset"]}.avif'
            voices=[f'assets/jungle-book/story-sounds/en/{page["asset"]}.wav' for page in pages]
        else:
            landscape=portrait={f'assets/jungle-book/pages/{name}.avif' for name in catalog[entry['id']]}
            offered={c['color'] for c in collectibles if c['source']['kind']=='book' and c['source']['page'] in landscape}
            assert entry['cover']==f'assets/jungle-book/previews/{entry["id"]}.avif'
            voices=[voice_path(name,'en',simple) for name in catalog[entry['id']] for simple in (True,False)]
        assert set(files['landscape'])==landscape|offered and set(files['portrait'])==portrait|offered, entry['id']
        for path in files['portrait']:
            assert owners.setdefault(path,entry['id'])==entry['id'], (path,owners[path],entry['id'])
        expected={segment['clip'] for path in voices for segment in speech['voices'][path]}
        assert set(entry['speech']['en']['normal'])==expected, entry['id']
        assert all(clip.startswith('assets/speech/en/slow-') for clip in entry['speech']['en']['slow'])
        for lang in ('de','es'):
            assert entry['speech'][lang]['normal'] and all('/'+lang+'/' in clip for clip in entry['speech'][lang]['normal'])
            assert 'slow' not in entry['speech'][lang] and 'fast' not in entry['speech'][lang], 'Duplicate profile list'
    assert {c['color'] for c in collectibles if c['source']['kind'] in ('book','story')}<=set(owners)
    # Packs follow books: nothing of another book or shelf shares a group.
    groups=book_pack_groups(manifest)
    for entry in book['books']:
        own={groups[path] for orientation in entry['files'].values() for path in orientation}
        own|={groups[clip] for profiles in entry['speech'].values() for clips in profiles.values() for clip in clips}
        assert all(group.startswith(('book-'+entry['id'],'speech-')) and (group.startswith('book-') or '-'+entry['id']+'-' in group)
                   or group=='shelf-sweet-porridge' for group in own), (entry['id'],own)
    assert {groups[path] for path in book['shelves']['']}=={'shelf-books'}
    assert {groups[path] for path in book['shelves']['sweet-porridge']}=={'shelf-sweet-porridge'}
    for scene,files in manifest['scenes'].items():
        assert scene in files
        assert all(path in paths for path in files)
    # A newly referenced asset is discovered without updating the loader.
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        source=Path(folder)/'future.zi';source.write_text('Picture :: "assets/future/"')
        assert source_assets(source)=={'assets/future/'}
    print('local preload manifest test: every catalog activity, Picture Book shelves with only covers, one book per download, stories per orientation, per-book packs, locale/profile clips and new source dependencies passed')


if __name__=='__main__':
    test_activity_manifest()

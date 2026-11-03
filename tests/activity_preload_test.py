"""Preload closure for every catalog game, locale and speech profile."""
from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from activity_assets import build_activity_manifest, source_assets
from shared_assets import GAMES


def test_activity_manifest():
    # Use the actual build data with tiny clip metadata: no encoding or asset
    # reads are needed to prove every reachable file is in the manifest.
    paths={p.relative_to(ROOT).as_posix() for p in (ROOT/'assets').rglob('*') if p.is_file() and p.suffix in ('.webp','.png','.wav')}
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
    legacy='assets/jungle-book/sounds/legacy.wav'
    clip='assets/speech/en/normal-legacy.ogg'
    voices[legacy]=[{'clip':clip,'start':0,'frames':1}]
    encoded[clip]={'path':clip};paths.add(clip)
    speech={'voices':voices,'encoded':encoded,'clips':{clip:{'language':'en'}}}
    manifest=build_activity_manifest(ROOT,paths,speech,GAMES)
    rows=[r.split('|') for r in (ROOT/'games/catalog.txt').read_text().splitlines() if '|' in r]
    assert len(manifest['activities'])==len(rows)
    for activity,row in zip(manifest['activities'],rows):
        assert activity['id']+'.zx'==row[0]
        assert activity['cover']==row[3] and activity['cover'] in activity['files']
        assert activity['files']==sorted(set(activity['files']))
        config=GAMES.get(activity['id'],{})
        for folder in config.get('folders',()):
            expected={p for p in paths if p.startswith(folder+'/')}
            assert expected<=set(activity['files']), (activity['id'],expected-set(activity['files']))
        for lang,profiles in activity['speech'].items():
            for profile,clips in profiles.items():
                assert all('/'+lang+'/' in clip and ('/'+profile+'-' in clip or clip.endswith('normal-legacy.ogg')) for clip in clips), (activity['id'],lang,profile)
        assert clip not in activity['speech']['de']['normal'] and clip not in activity['speech']['es']['normal']
        assert set(activity['files'])<=paths
    book=manifest['activities'][0]
    for folder in ('pages','portraits','items','previews'):
        expected={p for p in paths if p.startswith('assets/jungle-book/'+folder+'/')}
        assert expected<=set(book['files']), (folder,expected-set(book['files']))
    for story in ('sweet_porridge','town_musicians'):
        data=json.loads((ROOT/'tools'/f'{story}.json').read_text())
        for page in data['pages']:
            assert 'assets/jungle-book/pages/'+page['asset']+'.webp' in book['files'], page
    for lang in ('en','de','es'):
        for profile in ('normal','slow','fast'):
            assert len(book['speech'][lang][profile])>=2, (lang,profile)
    for scene,files in manifest['scenes'].items():
        assert scene in files
        assert all(path in paths for path in files)
    # A newly referenced asset is discovered without updating the loader.
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        source=Path(folder)/'future.zi';source.write_text('Picture :: "assets/future/"')
        assert source_assets(source)=={'assets/future/'}
    print('local preload manifest test: every catalog activity, both orientations, stories, locale/profile clips and new source dependencies passed')


if __name__=='__main__':
    test_activity_manifest()

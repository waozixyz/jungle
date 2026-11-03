"""Portable ZIP round trips, deduplication, reproducibility and upload gates."""
import hashlib
from pathlib import Path
import sys
import tempfile
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from asset_packs import pack_assets, validate_distribution

with tempfile.TemporaryDirectory(prefix='asset-pack-test-',dir=ROOT/'build') as temporary:
    root = Path(temporary)
    inputs = {}
    for name, data in {'images/a.png': b'\x89PNG'+bytes(range(256))*8,
                       'images/b.png': b'\x89PNG'+bytes(reversed(range(256)))*8,
                       'sounds/en/a.wav': b'RIFF'+b'hello world'*2048,
                       'sounds/es/a.wav': b'RIFF'+b'hola mundo'*2048,
                       'speech/es/a.ogg': b'OggS'+b'hola mundo'*2048,
                       'images/alias.png': b'\x89PNG'+bytes(range(256))*8,
                       'words/niño.txt': 'niño'.encode(),
                       'words/empty.txt': b''}.items():
        path=root/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        inputs[name]=path
    first=pack_assets(inputs, root/'one', max_bytes=24000)
    second=pack_assets(dict(reversed(list(inputs.items()))), root/'two', max_bytes=24000)
    assert first==second, 'Pack layout depends on source enumeration order'
    assert first['files']['images/a.png']==first['files']['images/alias.png']
    methods=set()
    for name, entry in first['files'].items():
        payload=(root/'one'/entry['pack']).read_bytes()
        assert payload==(root/'two'/entry['pack']).read_bytes()
        compressed=payload[entry['offset']:entry['offset']+entry['length']]
        data=zlib.decompress(compressed,-15) if entry['method']==8 else compressed
        assert data==inputs[name].read_bytes(), name
        assert hashlib.sha256(data).hexdigest()==entry['sha256']
        methods.add(entry['method'])
        with zipfile.ZipFile(root/'one'/entry['pack']) as archive:
            assert archive.testzip() is None
    assert methods=={0,8}
    # Encoded speech is stored as it is, yet still checked like every file.
    assert first['files']['speech/es/a.ogg']['method']==0 and first['files']['sounds/es/a.wav']['method']==8
    validate_distribution(root/'one')
    # Demand-loaded pictures never pull their neighbours into the same pack,
    # while aliases still refer to the original bytes only once.
    isolated=pack_assets(inputs, root/'isolated', max_bytes=100000,
                         single_files={'images/a.png'}, group_bytes={'sounds/en':1024})
    assert isolated['files']['images/a.png']==isolated['files']['images/alias.png']
    assert isolated['files']['images/a.png']['pack']!=isolated['files']['images/b.png']['pack']
    with zipfile.ZipFile(root/'isolated'/isolated['files']['images/a.png']['pack']) as archive:
        assert archive.namelist()==['images/a.png']
    samples={}
    for index in range(4):
        name=f'speech/en/{index}.ogg'
        path=root/'source'/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(b'OggS'+bytes([index])*1000);samples[name]=path
    bounded=pack_assets(samples,root/'bounded',group_bytes={'speech/en':2100})
    assert len(bounded['packs'])==2
    assert bounded['files']['speech/en/0.ogg']['pack']==bounded['files']['speech/en/1.ogg']['pack']
    assert bounded['files']['speech/en/1.ogg']['pack']!=bounded['files']['speech/en/2.ogg']['pack']
    for budget in (0,-1,True,1.5):
        try:
            pack_assets(inputs,root/'invalid-budget',group_bytes={'sounds/en':budget})
            raise AssertionError('Invalid pack budget was accepted')
        except ValueError:
            pass
    try:
        pack_assets({'../outside': inputs['images/a.png']}, root/'bad')
        raise AssertionError('Unsafe path was accepted')
    except ValueError:
        pass
    for index in range(1001):
        (root/'one'/str(index)).touch()
    try:
        validate_distribution(root/'one')
        raise AssertionError('Excess files passed the upload gate')
    except ValueError:
        pass
    # The expanded catalog must fit the host cap without downloading the
    # whole book directory at once. Exercise staging, including its pack policy.
    from unittest.mock import patch
    import build_web
    catalog_root=root/'expanded-catalog'
    pictures=catalog_root/'assets/jigsaw'
    pictures.mkdir(parents=True)
    for index in range(1001):
        (pictures/f'{index:04}.png').write_bytes(index.to_bytes(4,'little')+bytes(1020))
    site=root/'expanded-site';site.mkdir()
    with patch.multiple(build_web,create=True,ROOT=catalog_root,
                        Shipped=lambda name:True,WebAliases=lambda:{},WebFiles=lambda:({},{}),
                        Speech=lambda:({'clips':{},'voices':{}},{}),
                        SpeechIndexText=lambda speech:'',
                        write_previews=lambda files,out:None,
                        prepare_web_images=lambda files,cache,force_title=False:(files,{},{})):
        expanded=build_web.stage_assets(site)
    count,_=validate_distribution(site)
    assert count<20, count
    assert len([name for name in expanded['files'] if name.endswith('.png')])==1001
    for name,entry in expanded['files'].items():
        if not name.endswith('.png'): continue
        with zipfile.ZipFile(site/entry['pack']) as archive:
            assert sum(row.file_size for row in archive.infolist())<=1024*1024
            assert archive.read(name)==(catalog_root/name).read_bytes()
    # Every supported picture gets a few-KB preview at its own aspect ratio,
    # including jigsaw scenes and transparent cut-outs.
    import io, json
    from PIL import Image
    from web_images import PREVIEW_PIXELS, prepare_native_previews, prepare_previews, prepare_web_images
    from build_web import preview_groups, write_previews
    page=ROOT/'assets/jungle-book/pages/tiger.webp'
    wide=root/'source/wide.webp';Image.new('RGB',(900,300),(200,120,40)).save(wide,quality=90)
    sources={'assets/jungle-book/pages/tiger.webp':page,'assets/jungle-book/pages/tiger-again.webp':page,
             'assets/jungle-book/previews/wide.webp':wide,'assets/jigsaw/tiger.webp':page,
             'assets/jungle-book/items/tiger.webp':ROOT/'assets/jungle-book/items/tiger.webp'}
    made=prepare_previews(sources,root/'preview-cache')
    assert set(made)==set(sources),made
    assert made==prepare_previews(sources,root/'preview-cache'),'Cached previews changed'
    again=prepare_previews(sources,root/'fresh-cache')
    for name,path in made.items():
        data=path.read_bytes()
        assert data==again[name].read_bytes(),'Preview encoding is not reproducible: '+name
        with Image.open(io.BytesIO(data)) as preview, Image.open(sources[name]) as original:
            assert preview.format=='WEBP' and max(preview.size)==PREVIEW_PIXELS,(name,preview.size)
            # Aspect ratio within one rounded pixel.
            (w,h),(ow,oh)=preview.size,original.size
            assert abs(w*oh/ow-h)<=1 and abs(h*ow/oh-w)<=1,(name,preview.size)
            alpha = 'A' in original.getbands() and original.getchannel('A').getextrema()[0] < 255
            if alpha:
                expected = original.convert('RGBA')
                expected.thumbnail((PREVIEW_PIXELS, PREVIEW_PIXELS), Image.Resampling.LANCZOS)
                assert preview.convert('RGBA').tobytes() == expected.tobytes(), name
        # Lossless transparent previews retain RGB as well as alpha; opaque
        # photographic previews keep their established lossy size budget.
        assert len(data)<(40_000 if alpha else 6500),(name,len(data))
    assert len(made['assets/jungle-book/pages/tiger.webp'].read_bytes())*50<page.stat().st_size
    native=prepare_native_previews(sources,root/'native-preview-cache')
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    assert [digest(path) for path in native.values()]==[digest(path) for path in made.values()],\
        'browser and native preview bytes differ'

    # Browser staging reuses runtime exports unchanged and only caps its own title art.
    runtime_sources={'assets/jungle-book/pages/tiger.webp':page,
                     'assets/garden/art/bed.webp':ROOT/'assets/garden/art/bed.webp',
                     'assets/hide_seek/props/basket.webp':ROOT/'assets/hide_seek/props/basket.webp'}
    reused,names,info=prepare_web_images(runtime_sources,root/'runtime-reuse-cache')
    assert reused==runtime_sources and names=={} and info=={}
    title=root/'source/assets/jungle/title/guide.webp';title.parent.mkdir(parents=True,exist_ok=True)
    Image.new('RGB',(2500,1400),(80,120,180)).save(title,quality=95)
    title_before=title.read_bytes()
    converted,archive_names,encoded=prepare_web_images(
        {'assets/jungle/title/guide.webp':title},root/'browser-image-cache')
    assert set(encoded)=={'assets/jungle/title/guide.webp'}
    with Image.open(converted['assets/jungle/title/guide.webp']) as image:
        assert image.format=='WEBP' and image.size==(2048,1147),image.size
    assert archive_names['assets/jungle/title/guide.webp']=='assets/jungle/title/guide.webp'
    assert title.read_bytes()==title_before,'Canonical title art changed'
    # One pack per book's pages and one for the covers, in asset-packs.json's
    # format keyed by the logical paths; identical previews are stored once.
    groups={'assets/jungle-book/pages/tiger.webp':'jungle','assets/jungle-book/pages/tiger-again.webp':'jungle',
            'assets/jungle-book/previews/wide.webp':'covers'}
    (root/'site').mkdir()
    index=write_previews(sources,root/'site',groups)
    assert json.loads((root/'site/preview-images.json').read_text())==index
    # The jigsaw sample uses the same picture as the book page, so its
    # identical preview shares the same stored entry across groups.
    assert index['format']==1 and sorted(index['files'])==sorted(made) and len(index['packs'])==3
    files=index['files']
    assert files['assets/jungle-book/pages/tiger.webp']==files['assets/jungle-book/pages/tiger-again.webp']
    assert files['assets/jungle-book/pages/tiger.webp']==files['assets/jigsaw/tiger.webp']
    assert files['assets/jungle-book/pages/tiger.webp']['pack']!=files['assets/jungle-book/previews/wide.webp']['pack']
    for name,entry in files.items():
        pack=(root/'site'/entry['pack']).read_bytes()
        assert hashlib.sha256(pack).hexdigest()==index['packs'][entry['pack']]['sha256']
        data=pack[entry['offset']:entry['offset']+entry['length']]
        assert entry['method']==0 and data==made[name].read_bytes() and hashlib.sha256(data).hexdigest()==entry['sha256'],name
    assert sorted(path.name for path in (root/'site').iterdir())==['packs','preview-images.json'],'Preview staging was left behind'
    validate_distribution(root/'site')
    try:
        write_previews(sources,root/'unsafe',{'assets/jungle-book/pages/tiger.webp':'../up'})
        raise AssertionError('Unsafe preview group was accepted')
    except ValueError:
        pass
    # Every catalog book's pages share its own pack; covers share the shelf's.
    catalog=preview_groups()
    pages=[name for name in catalog if name.startswith('assets/jungle-book/pages/')]
    assert all((ROOT/name).is_file() for name in catalog),'Catalog names a missing picture'
    # The separately validated story keeps its own exact pages beside the books.
    story={row['asset'] for row in json.loads((ROOT/'tools/sweet_porridge.json').read_text())['pages']}
    story.update(row['asset'] for row in json.loads((ROOT/'tools/town_musicians.json').read_text())['pages'])
    assert len(pages)==len({path.stem for path in (ROOT/'assets/jungle-book/pages').glob('*.webp')}-story)
    assert {catalog[name] for name in catalog if '/previews/' in name}=={'covers'}

print('local asset pack test: lossless ZIP/seek round trips, aliases, Unicode, empty files, stable output, upload gates and reproducible content-addressed book previews passed')

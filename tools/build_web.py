"""Build Jungle's WebAssembly Canvas and DOM browser editions."""
import os
import argparse
import json
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from asset_packs import pack_assets, validate_distribution
from shared_assets import (PORT_FOLDERS, PortGamePreviews, SPEECH_INDEX, Shipped,
                           Speech, SpeechIndexText, WebFiles, WriteIfChanged)
from web_images import prepare_previews, prepare_web_images

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / 'build/web-c'


def run(args, **kwargs):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True, **kwargs)


def package(name):
    command = ['ziran','pkg','path',name]
    if not (ROOT/'ziran.local.toml').exists():command.append('--locked')
    return Path(subprocess.check_output(command,cwd=ROOT,text=True).strip())


def write_pages(out, revision):
    html=(ROOT/'web/index.html').read_text().replace('__JUNGLE_BUILD_REVISION__',revision)
    html=re.sub(r'((?:src|href)=\")(/?(?:assets/[^\"?]+|favicon\.ico|site\.webmanifest|(?:jungle(?:-dom)?|asset-packs)\.js))(\")',
                lambda match:match[1]+match[2]+'?v='+revision+match[3],html)
    html=re.sub(r'((?:src|href)=\")/(?!/)',r'\1',html)
    (out/'index.html').write_text(html)
    # Each explicit renderer URL keeps its identity when the default changes.
    for backend,runtime in (('dom','jungle-dom.js'),('canvas','jungle.js')):
        profile=re.sub(r' data-backend="(?:dom|canvas)"',f' data-backend="{backend}"',html,count=1)
        profile=re.sub(r'src="jungle(?:-dom)?\.js\?',f'src="{runtime}?',profile,count=1)
        (out/(backend+'.html')).write_text(profile)


def build(out):
    ziran = package('ziran')
    kryon = package('kryon')
    mingcute = package('mingcute')
    compiler = ziran/'build/bin/ziran'
    emcc = Path(os.environ.get('EMCC', shutil.which('emcc') or str(Path.home()/'emsdk/upstream/emscripten/emcc')))
    if not emcc.is_file():raise SystemExit('Emscripten is required: set EMCC to the installed emcc executable')
    shutil.rmtree(GEN,ignore_errors=True)
    GEN.mkdir(parents=True)
    out.mkdir(parents=True,exist_ok=True)
    modules=[]
    for path in [kryon/'src/ui',kryon/'src/backend',ziran/'std',ROOT/'web',ROOT/'host']:
        modules += ['--module-path',str(path)]
    modules += ['--module-path','kryon='+str(kryon/'src/ui'),'--module-path','kryon='+str(kryon/'src/backend'),'--module-path','mingcute='+str(mingcute/'src'),'--module-path','std='+str(ziran/'std')]
    bindings = {
        'canvas_app_run:CanvasAppMain':'jungle_web:JungleMain',
        'app_context:AppIdentityHost':'jungle_web:WebIdentity',
        'app_context:AppServiceHost':'jungle_web:WebService',
        'app_context:DocumentReadHost':'jungle_web:WebRead',
        'app_context:DocumentWriteHost':'jungle_web:WebWrite',
        'app_context:AppAssetPathHost':'jungle_web:WebAsset',
        'app_context:AppKeyboardHost':'jungle_web:WebKeyboard',
    }
    def compile_runtime(output,semantic_dom):
        entry='dom_app_run:main' if semantic_dom else 'canvas_app_run:main'
        sources=[kryon/'src/backend/canvas_app_run.zi',kryon/'src/backend/canvas_raster.zi']
        if semantic_dom:sources.append(kryon/'src/backend/dom_app_run.zi')
        sources.append(ROOT/'web/jungle_web.zi')
        args=[compiler,'build','--target=c','--entry',entry,'--define','PLATFORM_WEB','--root',ROOT/'web',*modules]
        for source,target in bindings.items():args += ['--bind',source+'='+target]
        args += ['-o',output,*sources]
        run(args)

    def link_runtime(output,generated):
        files=sorted(generated.rglob('*.c'))
        includes=[]
        for directory in sorted({path.parent for path in files}):includes += ['-iquote',directory]
        run([emcc,'-O2','-I'+str(ziran/'include'),*includes,*files,
             '--js-library',ziran/'web/ziran_web.js','--embed-file',str(kryon/'assets/fonts/LiberationSans-Regular.ttf')+'@/kryon-font.ttf',
             '--embed-file',str(ROOT/'assets/dino-paint/vector')+'@/assets/dino-paint/vector',
             '-sEXPORTED_RUNTIME_METHODS=FS,HEAPU8,addRunDependency,removeRunDependency','-sASYNCIFY','-sALLOW_MEMORY_GROWTH=1',
             '-sINITIAL_MEMORY=67108864','-sMAXIMUM_MEMORY=536870912','-sSTACK_SIZE=8388608','-sENVIRONMENT=web',
             '-sFORCE_FILESYSTEM=1','-lidbfs.js','-o',output],env=env)

    env=os.environ.copy();env['EM_CACHE']=str(ROOT/'build/emscripten-cache');env['EMCC_CORES']='2'
    compile_runtime(GEN,False)
    link_runtime(out/'jungle.js',GEN)
    dom_gen=ROOT/'build/web-dom-c'
    shutil.rmtree(dom_gen,ignore_errors=True)
    dom_gen.mkdir(parents=True)
    compile_runtime(dom_gen,True)
    link_runtime(out/'jungle-dom.js',dom_gen)
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    write_pages(out,revision)
    # Freeze actual compiled menu routes for repeatable input-driven benchmarks,
    # including a current checkout with unrelated uncommitted catalog entries.
    rows=[line.split('|') for line in (ROOT/'games/catalog.txt').read_text().splitlines() if '|' in line]
    (out/'benchmark-catalog.json').write_text(json.dumps({
        'games':[{'title':row[1],'age':int(row[4])} for row in rows],
        'titleScenes':json.loads((ROOT/'tools/title_hotspots.json').read_text()),
    },separators=(',',':'))+'\n')
    shutil.copy2(ROOT/'LICENSE',out/'LICENSE')
    for name in ('robots.txt','sitemap.xml','funding.json'):
        shutil.copy2(ROOT/'web'/name,out/name)
    manifest=json.loads((ROOT/'web/site.webmanifest').read_text())
    for name in ('id','start_url','scope'):manifest[name]='./'
    for icon in manifest['icons']:icon['src']=icon['src'].lstrip('/')+'?v='+revision
    (out/'site.webmanifest').write_text(json.dumps(manifest,indent=2)+'\n')
    shutil.copy2(ROOT/'assets/jungle/icons/favicon.ico',out/'favicon.ico')
    shutil.copy2(ROOT/'web/asset-packs.js',out/'asset-packs.js')
    manifest=stage_assets(out)
    (out/'version.json').write_text(json.dumps({'version':(ROOT/'VERSION').read_text().strip(),'revision':revision,
        'runtimes':{'canvas':(out/'jungle.js').stat().st_size,'dom':(out/'jungle-dom.js').stat().st_size}}))
    count,total=validate_distribution(out)
    print(f'Built {len(manifest["files"])} packed assets in {len(manifest["packs"])} ZIP packs; distribution: {count} files, {total/1_000_000:.1f} MB',flush=True)


def preview_groups():
    """{book picture: preview pack}: one pack per book's pages, one for the covers.

    Other pictures share one pack per folder (preview_group).
    """
    from book_catalog import BOOKS
    groups={}
    for category,names in BOOKS:
        groups.setdefault(f'assets/jungle-book/previews/{category}.webp','covers')
        for name in names:groups.setdefault(f'assets/jungle-book/pages/{name}.webp',category)
    return groups


def preview_group(name):
    """A folder's preview pack name, such as hide-seek-scenes."""
    return re.sub(r'[^a-z0-9]+','-',str(Path(name).parent).removeprefix('assets/').lower()).strip('-')


def write_previews(files, out, groups=None):
    """Pack each book picture's few-KB preview into the packs in OUT.

    Opening a book fetches one small pack holding all its page previews (the
    shelf one for all covers) instead of hundreds of tiny files. Its index,
    preview-images.json, has asset-packs.json's format keyed by the same
    logical paths, so the browser checks previews like every packed file.
    The menu never waits for it.
    """
    groups=preview_groups() if groups is None else groups
    stored,names={},{}
    previews=prepare_previews(files,ROOT/'work/web-image-cache')
    previews.update({name:path for name,path in PortGamePreviews().items() if name in files})
    for name,path in previews.items():
        group=groups.get(name) or preview_group(name)
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',group):raise ValueError('Unsafe preview group: '+group)
        key=f'previews/{group}/{Path(name).parent.name}/{Path(name).stem}.webp'
        stored[key]=path;names[key]=name
    with tempfile.TemporaryDirectory(prefix='preview-packs-',dir=out) as staging:
        manifest=pack_assets(stored,staging)
        (out/'packs').mkdir(exist_ok=True)
        for pack in manifest['packs']:
            target=out/pack
            if not target.exists():(Path(staging)/pack).replace(target)
    index={'format':1,'packs':manifest['packs'],'files':{names[key]:entry for key,entry in manifest['files'].items()}}
    (out/'preview-images.json').write_text(json.dumps(index,separators=(',',':'),sort_keys=True)+'\n')
    total=sum(pack['size'] for pack in manifest['packs'].values())
    print(f'Book previews: {len(index["files"])} pictures in {len(manifest["packs"])} packs, {total/1000:.0f} kB',flush=True)
    return index


def stage_assets(out):
    """Pack the game assets and write the browser's startup lists into OUT."""
    files = {}
    for name in ('jungle','jungle-book','abc','numbers','animal-count','dino-paint','jigsaw','piano','shapes','hide_seek','drums','garden',
                 *(Path(folder).name for folder in PORT_FOLDERS)):
        source=ROOT/'assets'/name
        for path in source.rglob('*'):
            # PaintViewWebRead uses the vectors embedded in the host above.
            # Do not download another copy in the activity asset packs.
            if path.parent == ROOT/'assets/dino-paint/vector':
                continue
            if any(path.parent == ROOT/folder/'previews' for folder in PORT_FOLDERS):
                continue
            if path.is_file() and Shipped(path.relative_to(ROOT).as_posix()) and not path.name.startswith('voice-'):
                files[path.relative_to(ROOT).as_posix()] = path
    # Runtime aliases supply the same optimized WebP bytes to native and web.
    runtime_files, runtime_encodings = WebFiles()
    files.update(runtime_files)
    # Narration ships as the native hosts' Ogg Vorbis clips and speech index,
    # never as the WAVs they compose.
    speech,speech_files=Speech()
    for name in set(speech['clips'])|set(speech['voices']):files.pop(name,None)
    files.update(speech_files)
    index=ROOT/'work/web-speech'/Path(SPEECH_INDEX).name
    WriteIfChanged(index,SpeechIndexText(speech))
    files[SPEECH_INDEX]=index
    files.pop('assets/jungle/covers/count.png', None)
    files,archive_names,encodings=prepare_web_images(
        files,ROOT/'work/web-image-cache',force_title=True)
    images=sorted(archive_names.get(name,name) for name in files
                  if Path(name).suffix in ('.png','.webp'))
    # Browser branding must work before the runtime starts. Keep the small
    # menu and its bitmap fonts directly addressable, so the menu opens
    # before the full pack index arrives; pack all game pictures and sounds.
    for name in list(files):
        if (name.startswith('assets/jungle/') and Path(name).suffix != '.wav') or name.endswith('/font.png'):
            target=out/archive_names.get(name,name)
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(files.pop(name),target)
    # On-demand pictures use bounded directory packs. Opening one picture never
    # fetches several megabytes of unrelated pages or a whole shelf of covers.
    runtime_group_bytes={parent:1024*1024 for parent in (
        'assets/jigsaw','assets/jungle-book/pages','assets/jungle-book/previews',
        'assets/jungle-book/items','assets/hide_seek/props','assets/hide_seek/scenes',
        'assets/drums/pictures') if any(str(Path(name).parent)==parent for name in files)}
    # Speech clips are content-addressed and small; bounded groups avoid a
    # whole-language download while keeping the distribution below host limits.
    speech_groups={str(Path(name).parent):128*1024 for name in files if name.startswith('assets/speech/')}
    write_previews(files,out)
    for name,encoding in runtime_encodings.items():
        archive_names[name]=str(Path(name).with_suffix('.webp'))
        encodings[name]=encoding
    manifest=pack_assets(files,out,archive_names=archive_names,
                         group_bytes={**speech_groups,**runtime_group_bytes})
    for name,encoding in encodings.items():
        if name in manifest['files']:
            manifest['files'][name]={**manifest['files'][name],**encoding}
    (out/'asset-packs.json').write_text(json.dumps(manifest,separators=(',',':'))+'\n')
    (out/'images.json').write_text(json.dumps(images))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output is not None:
        build(args.output)
        return
    # Fresh staging excludes obsolete assets; retain the last successful build.
    (ROOT/'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='web-stage-',dir=ROOT/'build') as stage:
        build(Path(stage))
        destination=ROOT/'build/web'
        if destination.exists():
            previous=ROOT/'backup/web-builds'/str(time.time_ns())
            previous.parent.mkdir(parents=True,exist_ok=True)
            destination.rename(previous)
        Path(stage).rename(destination)

if __name__=='__main__':main()

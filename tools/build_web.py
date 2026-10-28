"""Build Jungle's native DOM default and its Canvas comparison edition."""
import os
import json
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from asset_packs import pack_assets, validate_distribution
from web_images import prepare_web_images

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
    # Keep the old DOM URL and every renderer on the same canonical app URL.
    (out/'dom.html').write_text(html)
    canvas_html=html.replace(' data-backend="dom"',' data-backend="canvas"')
    canvas_html=canvas_html.replace('src="jungle-dom.js?','src="jungle.js?')
    (out/'canvas.html').write_text(canvas_html)


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
    shutil.copy2(ROOT/'LICENSE',out/'LICENSE')
    for name in ('robots.txt','sitemap.xml','funding.json'):
        shutil.copy2(ROOT/'web'/name,out/name)
    manifest=json.loads((ROOT/'web/site.webmanifest').read_text())
    for name in ('id','start_url','scope'):manifest[name]='./'
    for icon in manifest['icons']:icon['src']=icon['src'].lstrip('/')+'?v='+revision
    (out/'site.webmanifest').write_text(json.dumps(manifest,indent=2)+'\n')
    shutil.copy2(ROOT/'assets/jungle/icons/favicon.ico',out/'favicon.ico')
    shutil.copy2(ROOT/'web/asset-packs.js',out/'asset-packs.js')
    files = {}
    for name in ('jungle','jungle-book','abc','numbers','animal-count','dino-paint','jigsaw','piano'):
        source=ROOT/'assets'/name
        for path in source.rglob('*'):
            if path.is_file() and not path.name.endswith('.speech.json') and not path.name.startswith('voice-'):
                files[path.relative_to(ROOT).as_posix()] = path
    # Animal Counting reuses the book's corresponding watercolor pictures.
    animals=('tiger','frog','butterfly','ladybug','snail','elephant','giraffe','monkey','panda','lion','zebra','crocodile','parrot','toucan','rabbit','cat','dog','sheep')
    for name in animals:files[f'assets/animal-count/pictures/{name}.png']=ROOT/'assets/jungle-book/counting'/f'{name}.png'
    files.pop('assets/jungle/covers/count.png', None)
    images=sorted(name for name in files if Path(name).suffix in ('.png','.jpg'))
    # Browser branding must work before the runtime starts. Keep the small
    # menu directly addressable; pack all game pictures and sounds.
    for name in list(files):
        if name.startswith('assets/jungle/') and Path(name).suffix != '.wav':
            target=out/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(files.pop(name),target)
    single_files={name for name in files if str(Path(name).parent)=='assets/jigsaw'}
    files,archive_names,encodings=prepare_web_images(files,ROOT/'work/web-image-cache')
    manifest=pack_assets(files,out,archive_names=archive_names,single_files=single_files)
    for name,encoding in encodings.items():
        manifest['files'][name]={**manifest['files'][name],**encoding}
    (out/'asset-packs.json').write_text(json.dumps(manifest,separators=(',',':'))+'\n')
    (out/'images.json').write_text(json.dumps(images))
    (out/'version.json').write_text(json.dumps({'version':(ROOT/'VERSION').read_text().strip(),'revision':revision,
        'runtimes':{'canvas':(out/'jungle.js').stat().st_size,'dom':(out/'jungle-dom.js').stat().st_size}}))
    count,total=validate_distribution(out)
    print(f'Built {len(manifest["files"])} packed assets in {len(manifest["packs"])} ZIP packs; distribution: {count} files, {total/1_000_000:.1f} MB',flush=True)


def main():
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

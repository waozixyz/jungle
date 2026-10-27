"""Build the real Jungle game modules with Kryon's compiled Canvas host."""
import os
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/web'
GEN = ROOT / 'build/web-c'


def run(args, **kwargs):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True, **kwargs)


def package(name):
    command = ['ziran','pkg','path',name]
    if not (ROOT/'ziran.local.toml').exists():command.append('--locked')
    return Path(subprocess.check_output(command,cwd=ROOT,text=True).strip())


def main():
    ziran = package('ziran')
    kryon = package('kryon')
    mingcute = package('mingcute')
    compiler = ziran/'build/bin/ziran'
    emcc = Path(os.environ.get('EMCC', shutil.which('emcc') or str(Path.home()/'emsdk/upstream/emscripten/emcc')))
    if not emcc.is_file():raise SystemExit('Emscripten is required: set EMCC to the installed emcc executable')
    GEN.mkdir(parents=True,exist_ok=True)
    OUT.mkdir(parents=True,exist_ok=True)
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
    args=[compiler,'build','--target=c','--entry','canvas_app_run:main','--define','PLATFORM_WEB','--root',ROOT/'web',*modules]
    for source,target in bindings.items():args += ['--bind',source+'='+target]
    args += ['-o',GEN,kryon/'src/backend/canvas_app_run.zi',kryon/'src/backend/canvas_raster.zi',ROOT/'web/jungle_web.zi']
    run(args)
    env=os.environ.copy();env['EM_CACHE']=str(ROOT/'build/emscripten-cache');env['EMCC_CORES']='2'
    cfiles=sorted(GEN.rglob('*.c'))
    includes=[]
    for directory in sorted({p.parent for p in cfiles}):includes += ['-iquote',directory]
    run([emcc,'-O2','-I'+str(ziran/'include'),*includes,*cfiles,
         '--js-library',ziran/'web/ziran_web.js','--embed-file',str(kryon/'assets/fonts/LiberationSans-Regular.ttf')+'@/kryon-font.ttf',
         '-sEXPORTED_RUNTIME_METHODS=FS,addRunDependency,removeRunDependency','-sASYNCIFY','-sALLOW_MEMORY_GROWTH=1','-sINITIAL_MEMORY=67108864','-sMAXIMUM_MEMORY=536870912',
         '-sSTACK_SIZE=8388608','-sENVIRONMENT=web','-sFORCE_FILESYSTEM=1','-lidbfs.js','-o',OUT/'jungle.js'],env=env)
    shutil.copy2(ROOT/'web/index.html',OUT/'index.html')
    shutil.copy2(ROOT/'LICENSE',OUT/'LICENSE')
    for name in ('site.webmanifest','robots.txt','sitemap.xml'):
        shutil.copy2(ROOT/'web'/name,OUT/name)
    shutil.copy2(ROOT/'assets/jungle/icons/favicon.ico',OUT/'favicon.ico')
    for name in ('jungle','jungle-book','abc','numbers','animal-count','dino-paint','jigsaw'):
        source=ROOT/'assets'/name
        shutil.copytree(source,OUT/'assets'/name,dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('*.speech.json','voice-*'))
    # Animal Counting reuses the book's corresponding watercolor pictures.
    import sys
    sys.path.insert(0,str(ROOT/'tools'))
    from book_catalog import NAMES
    pictures=OUT/'assets/animal-count/pictures';pictures.mkdir(parents=True,exist_ok=True)
    animals=('tiger','frog','butterfly','ladybug','snail','elephant','giraffe','monkey','panda','lion','zebra','crocodile','parrot','toucan','rabbit','cat','dog','sheep')
    for name in animals:shutil.copy2(ROOT/'assets/jungle-book/items'/f'{name}.png',pictures/f'{name}.png')
    images=sorted(str(p.relative_to(OUT)) for p in (OUT/'assets').rglob('*') if p.suffix in ('.png','.jpg'))
    (OUT/'images.json').write_text(json.dumps(images))
    for path in OUT.rglob('*'):
        if path.is_file() and path.stat().st_size > 25*1024*1024:
            raise SystemExit('Cloudflare Pages asset exceeds 25 MiB: '+str(path.relative_to(OUT)))
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    (OUT/'version.json').write_text(json.dumps({'version':(ROOT/'VERSION').read_text().strip(),'revision':revision}))
    print('Built browser game and separate picture/audio assets in build/web',flush=True)

if __name__=='__main__':main()

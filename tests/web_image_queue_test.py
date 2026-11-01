"""Browser picture loading in web/index.html, run in headless Chromium.

The page's own script runs unchanged, without the wasm runtime: downloads,
the preview index and the clock are replaced by controllable fakes, so each
scenario decides when bytes arrive. Checks that the picture on screen loads
before prefetched pages, that its preview arrives before its full bytes, that a
preview never replaces a full picture, that a page flipped past leaves the
queue, and that a failed full picture is retried a bounded number of times.
Needs no display, Node or network; the profile is a private temporary folder.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

SCENARIOS = r"""
<script>
let clock=0;performance.now=()=>clock;
const fs=new Set(),started=[],deferred=new Map(),log=[];
Module.FS={analyzePath:path=>({exists:fs.has(path)}),mkdirTree(){},writeFile(path){fs.add(path)}};
function defer(key){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});deferred.set(key,{resolve,reject});started.push(key);return promise}
function assetBytes(path){return defer('full:'+path)}
let previewNames=new Set();
function previews(){return Promise.resolve({manifest:{files:Object.fromEntries([...previewNames].map(name=>[name,{}]))},read:path=>defer('preview:'+path)})}
const settle=async()=>{for(let at=0;at<20;at++)await Promise.resolve()};
const check=(name,ok,detail)=>{log.push({name,ok:Boolean(ok),detail});};
function reset(paths,withPreviews=paths){
 fs.clear();started.length=0;deferred.clear();imageLoads.clear();previewLoads.clear();fullQueue.clear();fullActive=0;
 // Names an older page lacks are skipped, so its behavior is still recorded.
 try{previewSettled.clear();fullFailures.clear();fullPrefetching=0}catch{}imagePaths=new Set(paths);previewNames=new Set(withPreviews);clock=0;
}
const fulls=()=>started.filter(key=>key.startsWith('full:')).map(key=>key.slice(5));
const page=name=>'assets/jungle-book/pages/'+name+'.jpg';
// One Picture Book frame: ReadingPage prefetches two pages, then draws its own.
const frame=(current,ahead)=>{for(const path of ahead)Module.jungleImageReady(path,true);return Module.jungleImageReady(current)};
(async()=>{
 // Cold first open: the current page's preview first, its full bytes next,
 // and the next pages never take both download slots.
 reset([page('a'),page('b'),page('c')]);
 frame(page('a'),[page('b'),page('c')]);await settle();
 check('prefetch uses at most one slot',fulls().length===1&&fulls()[0]===page('b'),fulls());
 check('current page waits for its preview',!fulls().includes(page('a')),fulls());
 check('previews requested',started.includes('preview:'+page('a')),started);
 deferred.get('preview:'+page('a')).resolve(new Uint8Array(1));await settle();
 check('preview written at its own path',fs.has('/assets/previews/jungle-book/pages/a.jpg')&&Module.junglePreviewReady(page('a')),[...fs]);
 check('full starts once preview is here',fulls().includes(page('a')),fulls());
 check('two at a time',fullActive===2,fullActive);
 deferred.get('full:'+page('a')).resolve(new Uint8Array(2));await settle();
 check('full picture ready',Module.jungleImageReady(page('a')),[...fs]);

 // A slow preview delays the full bytes by fullPreviewWait at most.
 reset([page('d')]);
 frame(page('d'),[]);await settle();
 clock=fullPreviewWait-1;frame(page('d'),[]);await settle();
 check('full waits for a slow preview',!fulls().includes(page('d')),fulls());
 clock=fullPreviewWait;frame(page('d'),[]);await settle();
 check('full starts after fullPreviewWait',fulls().includes(page('d')),fulls());
 // A picture without a preview starts its full bytes at once.
 reset([page('e')],[]);frame(page('e'),[]);await settle();
 check('no preview, full at once',fulls().includes(page('e')),fulls());

 // A preview never replaces a full picture that arrived first.
 reset([page('f')]);
 frame(page('f'),[]);await settle();clock=fullPreviewWait;frame(page('f'),[]);await settle();
 deferred.get('full:'+page('f')).resolve(new Uint8Array(2));await settle();
 deferred.get('preview:'+page('f')).resolve(new Uint8Array(1));await settle();
 check('late preview is not written',!fs.has('/assets/previews/jungle-book/pages/f.jpg'),[...fs]);

 // Drawn pictures beat queued prefetches, newest first; a page flipped past
 // leaves the queue.
 reset([page('g'),page('h'),page('i'),page('j')],[]);
 Module.jungleImageReady(page('g'),true);Module.jungleImageReady(page('h'),true);await settle();
 check('second prefetch queued, not started',fulls().length===1,fulls());
 Module.jungleImageReady(page('i'));await settle();
 check('drawn picture takes the free slot',fulls().includes(page('i')),fulls());
 clock=fullStale+1;Module.jungleImageReady(page('j'));
 deferred.get('full:'+page('g')).resolve(new Uint8Array(2));await settle();
 check('stale prefetch dropped',!fulls().includes(page('h'))&&fulls().includes(page('j')),fulls());

 // A failed full picture is asked for again, fullAttempts times in all.
 reset([page('k')],[]);
 frame(page('k'),[]);await settle();
 deferred.get('full:'+page('k')).reject(Error('offline'));await settle();
 frame(page('k'),[]);await settle();
 check('no retry before fullRetry',fulls().length===1,fulls());
 clock=fullRetry;frame(page('k'),[]);await settle();
 check('retried after fullRetry',fulls().length===2,fulls());
 deferred.get('full:'+page('k')).reject(Error('offline'));await settle();
 clock=fullRetry+fullRetry*2;frame(page('k'),[]);await settle();
 deferred.get('full:'+page('k')).reject(Error('offline'));await settle();
 clock=1e6;frame(page('k'),[]);await settle();
 check('gives up after fullAttempts',fulls().length===fullAttempts&&!imagePaths.has(page('k')),fulls());
})().catch(error=>log.push({name:'harness',ok:false,detail:String(error&&error.stack||error)}))
 .finally(()=>document.body.setAttribute('data-results',JSON.stringify(log)));
</script>
"""


def harness_html():
    # JUNGLE_INDEX checks another revision, such as the released page.
    page = Path(os.environ.get('JUNGLE_INDEX', ROOT/'web/index.html')).read_text()
    page = page.replace('<script src="asset-packs.js"></script>', '')
    page = page.replace('<script src="jungle.js" defer></script>', '')
    return page.replace('</body>', SCENARIOS + '</body>')


def main():
    browser = shutil.which('chromium') or shutil.which('chromium-browser')
    if not browser:
        print('web image queue test: chromium is not installed', file=sys.stderr)
        return 2
    work = ROOT/'work/web-image-queue-test'
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as scratch:
        page = Path(scratch)/'index.html'
        page.write_text(harness_html())
        env = {key: value for key, value in os.environ.items()
               if key not in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'SESSION_MANAGER')}
        env['YUE_DESKTOP_RECOVERY'] = '0'
        # Keep Chromium's Unix socket path relative to its private working
        # folder: the absolute GitHub checkout path can exceed sun_path.
        sockets = ROOT/'work/wq'
        sockets.mkdir(parents=True, exist_ok=True)
        env['TMPDIR'] = '.'
        result = subprocess.run([browser, '--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run',
                                 '--user-data-dir='+str(Path(scratch)/'profile'), '--virtual-time-budget=5000',
                                 '--dump-dom', page.as_uri()], capture_output=True, text=True, env=env, cwd=sockets, timeout=120)
    found = re.search(r'data-results="([^"]*)"', result.stdout)
    if not found:
        print(result.stdout[-2000:], result.stderr[-2000:], sep='\n', file=sys.stderr)
        print('web image queue test: no results', file=sys.stderr)
        return 1
    results = json.loads(found.group(1).replace('&quot;', '"').replace('&amp;', '&'))
    failed = [entry for entry in results if not entry['ok']]
    for entry in results:
        print(('ok   ' if entry['ok'] else 'FAIL ') + entry['name'] + ('' if entry['ok'] else ': ' + json.dumps(entry['detail'])))
    print(f'web image queue test: {len(results) - len(failed)}/{len(results)} passed')
    return 1 if failed or len(results) < 15 else 0


if __name__ == '__main__':
    sys.exit(main())

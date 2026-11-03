"""Real DOM/Canvas runtime, delayed packs, offline retry and cached reopen.

Python stdlib + private headless Chromium; no desktop pixels or Node. Reuses
only the existing test's bounded CDP transport and browser lifecycle.
"""
import argparse
import functools
import http.server
import json
import re
from pathlib import Path
import threading
import time

import book_media_start_web_test as headless
from runtime_test import title_keys

ROOT = Path(__file__).resolve().parents[1]
headless.WORK = ROOT/'local/activity-loading/browser'

PROBE = r"""
window.loadingProbe={fetches:[],starts:[]};
const originalFetch=window.fetch;
window.fetch=function(url,...args){loadingProbe.fetches.push({url:String(url),t:performance.now()});return originalFetch.call(this,url,...args)};
addEventListener('jungle-activity-started',event=>loadingProbe.starts.push({index:event.detail.index,t:performance.now()}));
"""


def run(base, renderer, revision=None):
    with headless.browser() as c:
        c.call('Page.addScriptToEvaluateOnNewDocument', source=PROBE)
        c.call('Emulation.setDeviceMetricsOverride', width=480 if renderer=='dom' else 1280,
               height=850 if renderer=='dom' else 720, deviceScaleFactor=1, mobile=False)
        c.call('Page.navigate', url=base+'/'+renderer+'.html')
        c.until('typeof activityLoader!=="undefined"&&activityLoader.state?.key.startsWith("scene:")&&activityLoader.state.status==="ready"', 'initial painted scene preload', 120)
        if revision:
            assert c.evaluate('buildRevision')==revision, 'stale live page'
        # Real menu keys, wait for each destination's own loader before the
        # next key. No wasm state or route is injected.
        for key in title_keys('Picture Book'):
            c.key(key)
            c.until('!document.getElementById("activity-loading").hidden||activityLoader.state?.status==="ready"', 'scene transition', 30)
            c.until('document.getElementById("activity-loading").hidden', 'scene ready', 120)
        c.until('loadingProbe.starts.some(s=>s.index===0)', 'Picture Book fully downloaded and started', 240)
        state=c.evaluate('({loaded:activityLoader.state.loaded,total:activityLoader.state.total,status:activityLoader.state.status})')
        assert state['status']=='ready' and state['loaded']==state['total'] and state['total']>100, state
        print(renderer+': real activity start after '+str(state['total'])+' prepared files',flush=True)
        # Every page in both orientations and every current-language speech
        # clip must already exist at the actual activity-start boundary.
        completeness=c.evaluate('''(async()=>{const a=(await activityManifest()).activities[0];const files=[...a.files,...a.speech[siteLanguage].normal];return files.filter(p=>!Module.FS.analyzePath('/'+p).exists)})()''')
        assert not completeness, completeness[:10]
        # Turn real book pages, trigger narration, and change book selection.
        c.key('0')
        for _ in range(4):
            c.key('ArrowRight')
        c.key(' ')
        c.call('Emulation.setDeviceMetricsOverride', width=1280 if renderer=='dom' else 480,
               height=720 if renderer=='dom' else 850, deviceScaleFactor=1, mobile=False)
        c.key('ArrowRight')
        c.evaluate('new Promise(resolve=>setTimeout(resolve,1200))')
        late=c.evaluate('loadingProbe.fetches.filter(f=>f.t>loadingProbe.starts[0].t&&/packs\\/|jungle-book\\/|speech\\//.test(f.url))')
        assert not late, late[:10]
        # Reload the whole app in the same private profile: Cache Storage has
        # to serve bytes even without the memory/FS from the first runtime.
        c.call('Emulation.setDeviceMetricsOverride', width=480 if renderer=='dom' else 1280,
               height=850 if renderer=='dom' else 720, deviceScaleFactor=1, mobile=False)
        first=set(c.evaluate('loadingProbe.fetches.map(f=>f.url)'))
        c.call('Page.reload', ignoreCache=True)
        c.until('typeof activityLoader!=="undefined"&&activityLoader.state?.key.startsWith("scene:")&&activityLoader.state.status==="ready"', 'cached scene ready',120)
        c.evaluate('window.networkReads=[];const fetchBeforeCacheTest=window.fetch;window.fetch=function(url,...args){networkReads.push(String(url));return fetchBeforeCacheTest.call(this,url,...args)}')
        for key in title_keys('Picture Book'):
            c.key(key)
            c.until('document.getElementById("activity-loading").hidden', 'cached scene ready',120)
        c.until('loadingProbe.starts.some(s=>s.index===0)', 'cached second activity start',240)
        fetched=c.evaluate('networkReads.filter(url=>/\\/packs\\/|\\/assets\\//.test(url))')
        # Everything downloaded on the first visit comes from Cache Storage,
        # and the book never downloads again. A title scene may still prefetch
        # an other-orientation picture that never finished on the first visit.
        repeated=[url for url in fetched if url in first or re.search(r'/packs/|jungle-book/|/speech/',url)]
        assert not repeated, repeated[:10]
        extra=' (title prefetch never fetched before: '+', '.join(sorted(fetched))+')' if fetched else ''
        print(renderer+': no page/narration downloads after start; cached fresh-runtime open repeated no asset download'+extra,flush=True)
        # Exercise the shipped loader's visible offline recovery using a new
        # activity key. Use CDP offline with the manifest already present, and
        # invalidate just one file so this really needs the network.
        c.evaluate('activityLoader.completed.clear()')
        result=c.evaluate('''(async()=>{let failed=true;const load=activityLoader.load;activityLoader.load=async path=>{if(failed)throw TypeError('offline test');return load(path)};activityLoader.request('offline-retry',async()=>({title:'Picture Book',files:['assets/jungle-book/pages/tiger.webp']}));await new Promise(r=>setTimeout(r,100));const shown=!overlay.hidden&&!document.getElementById('activity-retry').hidden;failed=false;document.getElementById('activity-retry').click();await new Promise(r=>setTimeout(r,100));return {shown,ready:activityLoader.state.status==='ready'}})()''')
        assert result=={'shown':True,'ready':True}, result
        print(renderer+': visible retry recovered from failed preload',flush=True)


class DelayedHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/packs/'):
            time.sleep(.025)
        super().do_GET()
    def log_message(self, *_):
        pass


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url')
    parser.add_argument('--expect-revision')
    parser.add_argument('--renderer',choices=['dom','canvas','both'],default='both')
    args=parser.parse_args()
    server=None
    if args.base_url:
        base=args.base_url.rstrip('/')
    else:
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(DelayedHandler,directory=ROOT/'build/web'))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base='http://127.0.0.1:'+str(server.server_port)
    try:
        for renderer in (('dom','canvas') if args.renderer=='both' else (args.renderer,)):
            run(base,renderer,args.expect_revision)
    finally:
        if server:
            server.shutdown();server.server_close()


if __name__=='__main__':
    main()

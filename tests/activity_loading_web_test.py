"""Real DOM/Canvas runtime on a delayed network: Picture Book downloads one
book at a time.

Opening a shelf fetches only its covers and shelf art. Clicking a book that is
not here shows the painted loading screen and fetches only that book's packs
(current orientation and language), then opens it; meanwhile nothing else
downloads. While it is read the next book downloads in the background at low
priority, and that book then opens with zero requests. Leaving the book pauses
the prefetch, Back on a book's download returns to the shelf, Try again
recovers a failed one, the fairy-tale shelf fetches only its two covers, and a
fresh runtime opens cached books from Cache Storage without the network.

Python stdlib + private headless Chromium; no desktop pixels or Node. Reuses
only the existing test's bounded CDP transport and browser lifecycle.
"""
import argparse
import functools
import http.server
from pathlib import Path
import threading
import time

import book_media_start_web_test as headless
from runtime_test import title_keys

ROOT = Path(__file__).resolve().parents[1]
headless.WORK = ROOT/'local/activity-loading/browser'

PROBE = r"""
window.loadingProbe={fetches:[],starts:[],overlay:[]};
const originalFetch=window.fetch;
window.fetch=function(url,...args){loadingProbe.fetches.push({url:String(url),t:performance.now(),priority:args[0]?.priority||'auto'});return originalFetch.call(this,url,...args)};
addEventListener('jungle-activity-started',event=>loadingProbe.starts.push({index:event.detail.index,t:performance.now()}));
addEventListener('DOMContentLoaded',()=>{
 const overlay=document.getElementById('activity-loading');
 new MutationObserver(()=>loadingProbe.overlay.push({shown:!overlay.hidden,title:document.getElementById('activity-title').textContent,t:performance.now()}))
  .observe(overlay,{attributes:true,attributeFilter:['hidden']});
});
"""
# After the page script: loader state changes, and the packs of logical files.
HELPERS = r"""
loadingProbe.states=[];
const probeChanged=activityLoader.changed;
activityLoader.changed=state=>{loadingProbe.states.push({key:state.key,status:state.status,t:performance.now()});probeChanged(state)};
// The title asks for its painted scene every frame it shows.
const probeScene=Module.jungleSceneReady;
Module.jungleSceneReady=(...args)=>{loadingProbe.title=performance.now();return probeScene(...args)};
window.probePacks=async files=>{const index=(await packIndex()).manifest.files;return [...new Set(files.filter(file=>Object.hasOwn(index,file)).map(file=>index[file].pack))].sort()};
window.probeBook=async(id,orientation)=>{const book=(await activityManifest()).activities[0].books.find(entry=>entry.id===id),speech=book.speech[siteLanguage];return probePacks([...book.files[orientation],...(speech.normal)])};
window.probeAllBooks=async()=>{const books=(await activityManifest()).activities[0].books;return probePacks(books.flatMap(book=>[...book.files.landscape,...book.files.portrait,...Object.values(book.speech).flatMap(profiles=>Object.values(profiles).flat())]))};
window.probeShelf=async start=>{const activity=(await activityManifest()).activities[0];return probePacks([...activity.files,...activity.shelves[start]])};
true
"""
PACK = r'(f.url.match(/packs\/[a-f0-9]{64}\.zip/)||[""])[0]'


class DelayedHandler(http.server.SimpleHTTPRequestHandler):
    """Every pack arrives after DELAY seconds; FAIL answers packs with 503."""
    delay = .025
    fail = False

    def do_GET(self):
        if self.path.startswith('/packs/'):
            if DelayedHandler.fail:
                self.send_error(503)
                return
            time.sleep(DelayedHandler.delay)
        super().do_GET()

    def log_message(self, *_):
        pass


def fetched(c, mark, condition='true'):
    """Pack paths fetched since fetch number MARK whose probe entry f passes CONDITION."""
    return c.evaluate(f'loadingProbe.fetches.slice({mark}).filter(f=>{condition}).map(f=>{PACK}).filter(Boolean)')


def mark(c):
    return c.evaluate('({fetches:loadingProbe.fetches.length,overlay:loadingProbe.overlay.length,'
                      'packs:[...new Set(loadingProbe.fetches.map(f=>'+PACK+').filter(Boolean))]})')


def shelf_fetches(c, mark):
    """Packs fetched since MARK once the Picture Book activity began loading,
    after the title's own guide narration."""
    begun = c.evaluate('loadingProbe.states.find(s=>s.key.startsWith("game:0:")&&s.status==="loading")?.t')
    assert begun is not None, 'Picture Book never loaded'
    return set(fetched(c, mark, f'f.t>={begun}'))


def open_book(c, key, book, wait=True):
    c.key(key)
    if wait:
        c.until(f'openBook?.id==="{book}"&&openBook.opened', 'book '+book+' open', 240)


def back_to_shelf(c):
    c.key('Escape')
    c.until('openBook===undefined', 'back on the shelf', 30)


def enter(c, title):
    """Real menu keys; wait for each destination's own loader before the next key."""
    for key in title_keys(title):
        c.key(key)
        c.until('!document.getElementById("activity-loading").hidden||activityLoader.state?.status==="ready"', 'scene transition', 30)
        c.until('document.getElementById("activity-loading").hidden', 'scene ready', 120)


def run(base, renderer, revision=None, controlled=True):
    portrait = renderer == 'dom'
    orientation = 'portrait' if portrait else 'landscape'
    size = dict(width=480, height=850) if portrait else dict(width=1280, height=720)
    with headless.browser() as c:
        c.call('Page.addScriptToEvaluateOnNewDocument', source=PROBE)
        c.call('Emulation.setDeviceMetricsOverride', **size, deviceScaleFactor=1, mobile=False)
        c.call('Page.navigate', url=base+'/'+renderer+'.html')
        c.until('typeof activityLoader!=="undefined"&&activityLoader.state?.key.startsWith("scene:")&&activityLoader.state.status==="ready"', 'initial painted scene preload', 120)
        c.evaluate(HELPERS)
        if revision:
            assert c.evaluate('buildRevision')==revision, 'stale live page'
        books = set(c.evaluate('probeAllBooks()'))

        # 1. The Picture Book shelf: its covers and shelf art, no book at all.
        before = mark(c)
        enter(c, 'Picture Book')
        c.until('loadingProbe.starts.some(s=>s.index===0)', 'Picture Book shelf started', 240)
        c.until('openBook===undefined&&activityLoader.state?.status==="ready"', 'shelf ready', 60)
        shelf = set(c.evaluate('probeShelf("")'))
        allowed = shelf | set(c.evaluate('probePacks(["assets/speech.txt","assets/jungle/sounds/select.wav","assets/jungle/sounds/start.wav"])'))
        got = shelf_fetches(c, before['fetches'])
        assert got <= allowed and not got & (books - shelf), sorted(got-allowed)[:10]
        assert shelf <= set(fetched(c, 0)), 'shelf covers missing'
        print(f'{renderer}: shelf fetched {len(got)} packs, only covers and shelf art, no book', flush=True)

        # 2. Book A downloads alone behind the painted loading screen.
        a, b = 'jungle', 'farm'
        start = mark(c)
        open_book(c, '1', a)
        state = c.evaluate(f'loadingProbe.states.filter(s=>s.key.startsWith("book:0:{a}:{orientation}:")&&s.status==="ready")[0]')
        assert state, 'book A never finished loading'
        own = set(c.evaluate(f'probeBook("{a}","{orientation}")'))
        during = set(fetched(c, start['fetches'], f'f.t<={state["t"]}'))
        assert during == own - set(start['packs']), (sorted(during ^ (own-set(start['packs'])))[:10])
        assert not fetched(c, start['fetches'], f'f.t<={state["t"]}&&f.priority==="low"'), 'book A was fetched at low priority'
        shown = c.evaluate(f'loadingProbe.overlay.slice({start["overlay"]}).filter(o=>o.shown).map(o=>o.title)')
        assert 'Wild animals' in shown, shown
        print(f'{renderer}: book A ({orientation}) loaded {len(during)} packs alone behind its loading screen', flush=True)

        # 3. The next book downloads in the background, low priority, after A.
        c.until(f'activityLoader.completed.has("book:0:{b}:{orientation}:en:normal")', 'next book prefetched', 240)
        after = fetched(c, start['fetches'], f'f.t>{state["t"]}')
        low = fetched(c, start['fetches'], f'f.t>{state["t"]}&&f.priority==="low"')
        nxt = set(c.evaluate(f'probeBook("{b}","{orientation}")'))
        assert after == low and set(after) == nxt - own - set(start['packs']), (sorted(set(after) ^ (nxt-own)))[:10]
        print(f'{renderer}: book B prefetched {len(after)} packs in the background at low priority', flush=True)

        # 4. B opens with zero requests; its own next book may prefetch.
        if controlled:
            DelayedHandler.delay = 2.0
        back_to_shelf(c)
        opened = mark(c)
        open_book(c, '4', b)
        c.evaluate('new Promise(resolve=>setTimeout(resolve,1500))')
        foreground = fetched(c, opened['fetches'], 'f.priority!=="low"')
        shown = c.evaluate(f'loadingProbe.overlay.slice({opened["overlay"]}).filter(o=>o.shown).length')
        assert not foreground and not shown, (foreground, shown)
        upcoming = c.evaluate('openBook.next')
        prefetch = set(fetched(c, opened['fetches']))
        assert prefetch <= set(c.evaluate(f'probeBook("{upcoming}","{orientation}")')), prefetch
        print(f'{renderer}: cached book B opened with zero requests and no loading screen', flush=True)
        if controlled:
            # 5. Leaving the book pauses the background download of the next.
            c.until(f'loadingProbe.fetches.slice({opened["fetches"]}).some(f=>f.priority==="low")', 'next prefetch started', 30)
            back_to_shelf(c)
            left = c.evaluate('loadingProbe.fetches.length')
            c.evaluate('new Promise(resolve=>setTimeout(resolve,3000))')
            assert c.evaluate('loadingProbe.fetches.length') == left, 'prefetch continued after the reader left'
            assert c.evaluate(f'activityLoader.background===undefined&&!activityLoader.completed.has("book:0:{upcoming}:{orientation}:en:normal")')
            print(f'{renderer}: leaving the book paused the next prefetch', flush=True)

            # 6. Back on a book's download returns to the Picture Book shelf.
            open_book(c, '2', 'garden', wait=False)
            c.until('!document.getElementById("activity-loading").hidden&&activityLoader.state?.key.includes(":garden:")', 'garden loading screen', 30)
            c.evaluate('document.getElementById("activity-back").click()')
            c.until('openBook===undefined&&document.getElementById("activity-loading").hidden', 'back to the shelf', 30)
            DelayedHandler.delay = .025
            open_book(c, '1', a)
            assert not c.evaluate(f'loadingProbe.starts.length>1'), 'Back left Picture Book'
            back_to_shelf(c)
            print(f'{renderer}: Back on a book download returned to the shelf', flush=True)

            # 7. Try again recovers a failed book download.
            DelayedHandler.fail = True
            open_book(c, '3', 'fruits', wait=False)
            c.until('activityLoader.state?.status==="error"&&!document.getElementById("activity-retry").hidden', 'visible Try again', 60)
            DelayedHandler.fail = False
            c.evaluate('document.getElementById("activity-retry").click()')
            c.until('openBook?.id==="fruits"&&openBook.opened&&document.getElementById("activity-loading").hidden', 'retried book open', 120)
            back_to_shelf(c)
            print(f'{renderer}: visible Try again recovered a failed book', flush=True)

        # 8. A fresh runtime in the same private profile: the fairy-tale shelf
        # fetches only its covers, a story only its orientation's pages; the
        # cached shelf and books open from Cache Storage without the network.
        c.call('Page.reload', ignoreCache=True)
        c.until('typeof activityLoader!=="undefined"&&activityLoader.state?.key.startsWith("scene:")&&activityLoader.state.status==="ready"', 'cached scene ready', 120)
        c.evaluate(HELPERS)
        before = mark(c)
        enter(c, 'Sweet Porridge')
        c.until('loadingProbe.starts.some(s=>s.index===0)', 'fairy-tale shelf started', 240)
        c.until('openBook===undefined&&activityLoader.state?.status==="ready"', 'fairy-tale shelf ready', 60)
        stories = set(c.evaluate('probeShelf("sweet-porridge")'))
        allowed = stories | set(c.evaluate('probePacks(["assets/speech.txt","assets/jungle/sounds/select.wav","assets/jungle/sounds/start.wav"])'))
        got = shelf_fetches(c, before['fetches'])
        # A story's cover is its first page, packed with the shelf.
        assert got <= allowed and not got & (books - stories), sorted(got-allowed)[:10]
        story = mark(c)
        open_book(c, '1', 'sweet-porridge')
        state = c.evaluate(f'loadingProbe.states.filter(s=>s.key.startsWith("book:0:sweet-porridge:{orientation}:")&&s.status==="ready")[0]')
        own = set(c.evaluate(f'probeBook("sweet-porridge","{orientation}")'))
        during = set(fetched(c, story['fetches'], f'f.t<={state["t"]}'))
        assert during == own - set(story['packs']), sorted(during ^ (own-set(story['packs'])))[:10]
        other = set(c.evaluate(f'probeBook("sweet-porridge","{"landscape" if portrait else "portrait"}")'))
        if not portrait:
            assert not during & (other - own), 'landscape story fetched portrait pages'
        c.until(f'activityLoader.completed.has("book:0:town-musicians:{orientation}:en:normal")', 'next story prefetched', 240)
        assert all(f == 'low' for f in c.evaluate(f'loadingProbe.fetches.slice({story["fetches"]}).filter(f=>f.t>{state["t"]}).map(f=>f.priority)'))
        print(f'{renderer}: fairy-tale shelf fetched only its covers; the {orientation} story only its own {len(during)} packs, the next one in the background', flush=True)
        back_to_shelf(c)
        left = c.evaluate('performance.now()')
        c.key('Escape')
        c.until(f'loadingProbe.title>{left}', 'left the stories', 30)
        cached = mark(c)
        enter(c, 'Picture Book')
        c.until('loadingProbe.starts.filter(s=>s.index===0).length>=2', 'cached Picture Book started', 240)
        c.until('openBook===undefined&&activityLoader.state?.status==="ready"', 'cached shelf ready', 60)
        open_book(c, '1', a)
        back_to_shelf(c)
        open_book(c, '4', b)
        assert not fetched(c, cached['fetches'], 'f.priority!=="low"'), fetched(c, cached['fetches'])
        print(f'{renderer}: fresh runtime opened the cached shelf and books A and B with zero requests', flush=True)


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
            run(base,renderer,args.expect_revision,controlled=server is not None)
    finally:
        if server:
            server.shutdown();server.server_close()


if __name__=='__main__':
    main()

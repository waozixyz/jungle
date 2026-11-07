"""Real wasm Book regression; Python stdlib + private headless Chromium only.

Local harness test (no wasm build):
  build-queue -- python3 tests/book_media_start_web_test.py --self-test
Official CI artifact, extracted without overlaying the owner's build outputs:
  build-queue -- python3 tests/book_media_start_web_test.py --web-root PATH --renderer both
Or an already served candidate:
  build-queue -- python3 tests/book_media_start_web_test.py --base-url https://jungle.waozi.xyz --renderer both
Use --expect-revision REV to reject stale artifacts. Receipts include version.json,
HTML/wasm SHA256 and individual observations. A failing baseline exits nonzero.
No production retry is implemented here: injected failures happen exactly once
at native play or soundBytes; subsequent calls use the original implementation.
Audible means unmuted media playing with advancing currentTime and decoded PCM
containing nonzero samples, not proof of physical speaker output in headless mode.
"""
import argparse
import base64
from contextlib import contextmanager
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

import runtime_test

ROOT = Path(__file__).resolve().parents[1]
WORK = runtime_test.run_folder('work/book-expansion-034/cold-start', create=False)


def require(value, message):
    if not value:
        raise AssertionError(message)


class CDP:
    """Small synchronous RFC6455 client, with bounded messages and CDP errors."""
    def __init__(self, url):
        parsed = urllib.parse.urlsplit(url)
        self.sock = socket.create_connection((parsed.hostname, parsed.port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        target=parsed.path+('?' + parsed.query if parsed.query else '')
        self.sock.sendall((f'GET {target} HTTP/1.1\r\nHost: {parsed.netloc}\r\n'
                           f'Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n'
                           'Sec-WebSocket-Version: 13\r\n\r\n').encode())
        header = b''
        while not header.endswith(b'\r\n\r\n'):
            header += self.exact(1)
            require(len(header) < 16384, 'oversized websocket handshake')
        accept = base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
        require(b' 101 ' in header and accept in header, 'websocket upgrade rejected: '+header[:500].decode(errors='replace'))
        self.sequence = 0

    def exact(self, length):
        result = bytearray()
        while len(result) < length:
            chunk = self.sock.recv(length-len(result))
            if not chunk:
                raise EOFError('CDP disconnected')
            result.extend(chunk)
        return bytes(result)

    def send(self, data, opcode=1):
        data = data if isinstance(data, bytes) else data.encode()
        length = len(data)
        header = bytes([128 | opcode])
        header += (bytes([128 | length]) if length < 126 else
                   bytes([254])+struct.pack('!H', length) if length < 65536 else
                   bytes([255])+struct.pack('!Q', length))
        mask = os.urandom(4)
        self.sock.sendall(header+mask+bytes(v ^ mask[i % 4] for i, v in enumerate(data)))

    def receive(self):
        chunks = bytearray()
        while True:
            first, second = self.exact(2)
            size = second & 127
            if size == 126:
                size = struct.unpack('!H', self.exact(2))[0]
            elif size == 127:
                size = struct.unpack('!Q', self.exact(8))[0]
            require(size + len(chunks) <= 32*1024*1024, 'oversized CDP frame')
            mask = self.exact(4) if second & 128 else None
            data = self.exact(size)
            if mask:
                data = bytes(v ^ mask[i % 4] for i, v in enumerate(data))
            opcode = first & 15
            if opcode == 8:
                raise EOFError('CDP closed websocket')
            if opcode == 9:
                self.send(data, 10)
                continue
            if opcode == 10:
                continue
            chunks.extend(data)
            if first & 128:
                return json.loads(chunks)

    def call(self, method, **params):
        self.sequence += 1
        self.send(json.dumps(dict(id=self.sequence, method=method, params=params)))
        deadline = time.monotonic()+35
        while time.monotonic() < deadline:
            reply = self.receive()
            if reply.get('id') == self.sequence:
                require('error' not in reply, f'{method}: {reply.get("error")}')
                return reply.get('result', {})
        raise TimeoutError(method)

    def evaluate(self, expression):
        reply = self.call('Runtime.evaluate', expression=expression, returnByValue=True, awaitPromise=True)
        require('exceptionDetails' not in reply, str(reply.get('exceptionDetails')))
        return reply['result'].get('value')

    def until(self, expression, description, seconds=25):
        end = time.monotonic()+seconds
        while time.monotonic() < end:
            value = self.evaluate(expression)
            if value:
                return value
            time.sleep(.05)
        raise AssertionError('Timed out: '+description)

    def key(self, key):
        code, vk = ('Digit'+key, ord(key)) if len(key)==1 and key.isdigit() else {'Home': ('Home',36), 'Enter': ('Enter',13),
                    ' ': ('Space',32), 'ArrowRight': ('ArrowRight',39),
                    'Escape': ('Escape',27)}[key]
        self.call('Input.dispatchKeyEvent', type='keyDown', key=key, code=code, windowsVirtualKeyCode=vk)
        time.sleep(.12)
        self.call('Input.dispatchKeyEvent', type='keyUp', key=key, code=code, windowsVirtualKeyCode=vk)
        time.sleep(.12)

    def click(self, x, y):
        for kind, buttons in [('mousePressed',1), ('mouseReleased',0)]:
            self.call('Input.dispatchMouseEvent', type=kind, x=x, y=y, button='left', buttons=buttons, clickCount=1)
            time.sleep(.12)


@contextmanager
def browser():
    runtime_test.claim(WORK)
    binary = os.environ.get('CHROMIUM') or shutil.which('chromium') or shutil.which('chromium-browser')
    require(binary, 'Chromium is required')
    # Chromium singleton sockets need a short TMPDIR (Unix path limit).
    # Chromium owns and removes its socket folder; profile/receipts stay here.
    with tempfile.TemporaryDirectory(prefix='b-', dir=WORK) as profile:
        env = {k:v for k,v in os.environ.items() if k not in (
            'DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','DBUS_SESSION_BUS_ADDRESS','SESSION_MANAGER')}
        env.update(YUE_DESKTOP_RECOVERY='0', TMPDIR=str(ROOT/'work'))
        with open(Path(profile)/'chromium.log', 'wb') as log:
            proc = subprocess.Popen([binary, '--headless=new', '--no-sandbox', '--disable-gpu',
                '--disable-dev-shm-usage', '--no-first-run', '--no-default-browser-check',
                '--remote-debugging-port=0', '--user-data-dir='+profile, 'about:blank'],
                env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
            client = None
            try:
                port_file = Path(profile)/'DevToolsActivePort'
                end = time.monotonic()+30
                while not port_file.exists() and proc.poll() is None and time.monotonic() < end:
                    time.sleep(.1)
                if not port_file.exists():
                    log.flush()
                    with open(Path(profile)/'chromium.log', 'rb') as diagnostic:
                        diagnostic.seek(max(0, diagnostic.seek(0, 2)-3000))
                        tail = diagnostic.read(3000).decode(errors='replace')
                    raise AssertionError('private Chromium startup failed: '+tail)
                port = port_file.read_text().splitlines()[0]
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list', timeout=10) as response:
                    pages = json.load(response)
                client = CDP(next(p['webSocketDebuggerUrl'] for p in pages if p['type']=='page'))
                client.call('Page.enable')
                client.call('Runtime.enable')
                client.call('Emulation.setDeviceMetricsOverride', width=1280, height=675, deviceScaleFactor=1, mobile=False)
                yield client
            except Exception:
                # Keep evidence outside the disposable profile, including when
                # CDP dies after startup. Read only a bounded diagnostic tail.
                log.flush()
                diagnostic_path = WORK / f'chromium-{proc.pid}.log'
                shutil.copyfile(Path(profile) / 'chromium.log', diagnostic_path)
                with diagnostic_path.open('rb') as diagnostic:
                    diagnostic.seek(max(0, diagnostic.seek(0, 2) - 4000))
                    tail = diagnostic.read(4000).decode(errors='replace')
                print(f'Private Chromium pid={proc.pid} exit={proc.poll()} '
                      f'profile={profile} log={diagnostic_path}\n{tail}', file=sys.stderr, flush=True)
                raise
            finally:
                if client:
                    try:
                        client.call('Browser.close')
                    except (OSError, EOFError, AssertionError):
                        pass
                    client.sock.close()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    # This session/process group belongs solely to this browser.
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait(timeout=5)
                # Chromium's profile writers may finish just after its parent.
                for attempt in range(20):
                    try:
                        shutil.rmtree(profile)
                        break
                    except FileNotFoundError:
                        break
                    except OSError:
                        if attempt==19:
                            raise
                        time.sleep(.15)


# Installed before page scripts; records real native play, never substitutes a
# successful promise or a fake playing state. Large pixel captures stay in-page.
PROBE = r"""
window.probe={events:[],media:[],captures:[],mode:'none',armed:false,used:false,current:'',asked:0,requests:new Map()};
const P=window.probe;
P.log=(type,extra={})=>{if(P.events.length<2000)P.events.push({type,t:performance.now(),...extra})};
P.visiblePictures=()=>[...document.querySelectorAll('#kryon-dom-paint img, #kryon-dom-root img')].filter(e=>{
 const r=e.getBoundingClientRect();
 if(r.width<=200||r.height<=200||!e.complete||!e.naturalWidth)return false;
 for(let parent=e;parent;parent=parent.parentElement){
  const s=getComputedStyle(parent);
  if(s.visibility==='hidden'||s.display==='none'||Number(s.opacity)===0)return false;
 }
 return true;
}).map(e=>({src:e.src,rect:e.getBoundingClientRect().toJSON()}));
const nativePlay=HTMLMediaElement.prototype.play;
HTMLMediaElement.prototype.play=function(){
 const path=this.junglePath||'';
 if(!path.includes('jungle-book/sounds/'))return nativePlay.apply(this,arguments);
 if(!P.media.includes(this)){
  P.media.push(this);
  this.addEventListener('playing',()=>P.log('playing',{path,muted:this.muted,volume:this.volume}));
  this.addEventListener('pause',()=>P.log('pause',{path}));
 }
 const image='assets/jungle-book/pages/'+path.split('/').at(-1).replace(/\.wav$/,'.avif');
 const capture={path,image,t:performance.now(),asked:P.requests.get(image)||P.opened||P.asked};
 // Capture actual framebuffer at the voice boundary, not loader readiness.
 const canvas=document.getElementById('canvas');
 capture.png=canvas.toDataURL();
 capture.dom=P.visiblePictures();
 P.captures.push(capture);P.log('play',{path,image:P.current,capture:P.captures.length-1});
 if(P.armed&&!P.used&&P.mode==='play-reject'){
  P.used=true;P.log('injected-play-rejection',{path});
  return Promise.reject(new DOMException('one injected native play failure','NotAllowedError'));
 }
 return nativePlay.apply(this,arguments);
};
P.install=()=>{
 const ready=Module.jungleImageReady;
 Module.jungleImageReady=function(path,prefetch){
  if(!prefetch&&path.includes('jungle-book/pages/')){P.current=path;if(!P.requests.has(path)){P.asked=performance.now();P.requests.set(path,P.asked);P.log('page',{path})}}
  const available=ready.apply(this,arguments);
  return P.armed&&P.mode==='image-timeout'&&path.includes('jungle-book/pages/')?false:available;
 };
 const preview=Module.junglePreviewReady;
 if(preview)Module.junglePreviewReady=function(path){return P.armed&&P.mode==='image-timeout'&&path.includes('jungle-book/pages/')?false:preview.apply(this,arguments)};
 const bytes=soundBytes;
 soundBytes=async function(path,current){
  if(P.armed&&path.includes('jungle-book/sounds/')&&!P.used&&P.mode==='loading-idle'){
   P.used=true;P.log('injected-loading',{path});await new Promise(r=>setTimeout(r,350));
   P.log('injected-idle',{path});throw Error('one injected soundBytes failure');
  }
  if(P.armed&&P.mode==='hold-navigation'&&path.includes('jungle-book/sounds/')&&!P.used){
   P.used=true;P.log('held',{path});await new Promise(r=>P.release=r);
  }
  return bytes.apply(this,arguments);
 };
};
P.summary=()=>({events:P.events,current:P.current,used:P.used,
 media:P.media.map(a=>({path:a.junglePath,time:a.currentTime,paused:a.paused,muted:a.muted,volume:a.volume,ready:a.readyState})),
 captures:P.captures.map(({png,dom,...c})=>({...c,domCount:dom.length}))});
P.checkPicture=async index=>{
 const c=P.captures[index],paths=[c.image,'assets/previews/'+c.image.slice(7)];
 const decode=async src=>{const i=new Image();i.src=src;await i.decode();return i};
 const pixels=i=>{const cv=document.createElement('canvas');cv.width=i.naturalWidth;cv.height=i.naturalHeight;
  const ctx=cv.getContext('2d');ctx.drawImage(i,0,0);return {data:ctx.getImageData(0,0,cv.width,cv.height).data,w:cv.width,h:cv.height}};
 const shot=pixels(await decode(c.png));
 let best={matches:0,total:0,path:'',method:''};
 for(const path of paths){
  if(!Module.FS.analyzePath('/'+path).exists)continue;
  const url=URL.createObjectURL(new Blob([Module.FS.readFile('/'+path)]));
  try{
   const reference=pixels(await decode(url));
   // The 619px square scene is centered below the shared 56px title bar.
   // Upper scene samples avoid caption/toolbar. Same geometry on both backends.
   const size=619,left=(1280-size)/2,top=56;
   let matches=0,total=0;
   for(let y=0.08;y<0.62;y+=.055)for(let x=.1;x<.9;x+=.075){
    const a=4*(Math.floor(y*reference.h)*reference.w+Math.floor(x*reference.w));
    const b=4*(Math.floor(top+y*size)*shot.w+Math.floor(left+x*size));
    const distance=[0,1,2].reduce((n,k)=>n+Math.abs(reference.data[a+k]-shot.data[b+k]),0);
    if(distance<65)matches++;total++;
   }
   if(matches>best.matches)best={matches,total,path,method:'framebuffer'};
   // DOM: decoded visible img must match the real page bytes and occupy scene.
   for(const item of c.dom){
    const r=item.rect;if(r.x>400||r.y>100||r.width<500||r.height<500)continue;
    const actual=pixels(await decode(item.src));let same=0,n=0;
    for(let y=.08;y<.62;y+=.055)for(let x=.1;x<.9;x+=.075){
     const a=4*(Math.floor(y*reference.h)*reference.w+Math.floor(x*reference.w));
     const b=4*(Math.floor(y*actual.h)*actual.w+Math.floor(x*actual.w));
     if([0,1,2].reduce((v,k)=>v+Math.abs(reference.data[a+k]-actual.data[b+k]),0)<65)same++;n++;
    }
    if(same>best.matches)best={matches:same,total:n,path,method:'visible-dom-image'};
   }
  }finally{URL.revokeObjectURL(url)}
 }
 return {...best,ok:best.total>0&&best.matches/best.total>.85};
};
"""


def fingerprint(base_url, renderer):
    result = {'base_url': base_url, 'renderer': renderer}
    for name in ['version.json', renderer+'.html', 'jungle-dom.wasm' if renderer=='dom' else 'jungle.wasm']:
        with urllib.request.urlopen(base_url.rstrip('/')+'/'+name, timeout=30) as response:
            digest = hashlib.sha256()
            version = b''
            while chunk := response.read(65536):
                digest.update(chunk)
                if name=='version.json':
                    version += chunk
                    require(len(version)<65536, 'oversized version.json')
        result[name] = json.loads(version) if version else {'sha256': digest.hexdigest()}
    return result


# settings/awards.txt in the page's app documents (/kryon-apps/<app id>/).
AWARDS = r"""(() => { try {
  for (const name of Module.FS.readdir('/kryon-apps')) {
    if (name[0] === '.') continue
    try { return Module.FS.readFile('/kryon-apps/' + name + '/settings/awards.txt', {encoding: 'utf8'}) } catch (e) {}
  }
} catch (e) {} return '' })()"""
# The whole award show (host/jungle_awards.zi AWARD_SHOW_SECONDS 2.95) plus a margin.
AWARD_SHOW_WAIT = 4


def open_picture_book(client):
    """Use the real title's keyboard route, including painted scene hotspots."""
    painted = client.evaluate('typeof imagePaths!=="undefined"&&[...imagePaths].some(p=>p.startsWith("assets/jungle/title/"))')
    if painted:
        import runtime_test
        keys = runtime_test.title_keys('Picture Book')
    else:
        keys = ['Home', 'Enter']
    # Each key changes scene; let its pictures decode before the next key.
    for key in keys:
        client.key(key)
        time.sleep(.6)


def test_first_book_media_start(base_url: str, renderer: str):
    """Return observations; any missing real-app evidence is a test failure."""
    result = fingerprint(base_url, renderer)
    result['scenarios'] = []
    for mode in ('none', 'play-reject', 'loading-idle', 'image-timeout', 'hold-navigation', 'paused-hear'):
        scenario = {'mode': mode}
        result['scenarios'].append(scenario)
        try:
            with browser() as c:
                try:
                    c.call('Page.addScriptToEvaluateOnNewDocument', source=PROBE)
                    c.call('Page.navigate', url=base_url.rstrip('/')+'/'+renderer+'.html')
                    c.until('typeof Module!=="undefined"&&!!Module.FS&&document.getElementById("loading").style.display==="none"', 'wasm startup', 90)
                    c.evaluate('probe.install()')
                    open_picture_book(c)
                    # A fresh profile's first Picture Book opening earns its award;
                    # let that badge finish before the first page's voice is judged.
                    c.until(AWARDS+'.includes("award-picture-book")', 'Picture Book award', 30)
                    time.sleep(AWARD_SHOW_WAIT)
                    # 0 opens saved category 9 independently of shelf geometry.
                    c.evaluate('probe.mode='+json.dumps(mode)+';probe.armed=true')
                    c.evaluate('probe.opened=performance.now()'); c.key('0')
                    c.until('probe.current', 'actual Book page image request')
                    if mode=='hold-navigation':
                        c.until('probe.release!==undefined', 'held original page voice')
                        old = c.evaluate('probe.events.find(e=>e.type==="held").path')
                        c.key('ArrowRight')
                        c.evaluate('probe.log("navigation-release");probe.release()')
                        c.until('probe.events.some(e=>e.type==="playing"&&e.path!=='+json.dumps(old)+')', 'new page plays')
                        time.sleep(1)
                        require(not c.evaluate('probe.events.some(e=>e.type==="playing"&&e.path==='+json.dumps(old)+')'), 'stale page voice played after navigation')
                    else:
                        c.until('probe.media.some(a=>!a.paused&&!a.muted&&a.volume>0&&a.currentTime>.05)', 'unmuted narration advances after '+mode)
                        require(mode in ('none','image-timeout','paused-hear') or c.evaluate('probe.used'), 'failure was never injected')
                        event = c.evaluate('probe.events.filter(e=>e.type==="play").at(-1)')
                        first = c.evaluate('probe.events.find(e=>e.type==="play"||e.type==="injected-loading").path')
                        require(event['path']==first, 'first page never recovered; later page played instead: '+event['path'])
                        picture = c.evaluate('probe.checkPicture('+str(event['capture'])+')')
                        scenario['picture'] = picture
                        if mode=='image-timeout':
                            capture = c.evaluate('probe.captures['+str(event['capture'])+'].t-probe.captures['+str(event['capture'])+'].asked')
                            scenario['image_wait_ms'] = capture
                            require(2350 <= capture < 6500, 'image timeout was unbounded or voice started early: '+str(capture))
                            require(not picture['ok'], 'withheld image unexpectedly visible')
                        elif mode!='paused-hear':
                            require(picture['ok'], 'no matching visible preview/full picture at voice start: '+str(picture))
                        if mode=='play-reject':
                            plays = c.evaluate('probe.events.filter(e=>e.type==="play")')
                            require(2 <= len(plays) <= 3 and len({e['path'] for e in plays})==1,
                                    'retry must target same first page, bounded to 3 attempts')
                        if mode=='loading-idle':
                            events = c.evaluate('probe.events')
                            idle = next(e['t'] for e in events if e['type']=='injected-idle')
                            require(event['t'] >= idle, 'play preceded injected loading-to-idle failure')
                        # Verify the actual synthesized PCM contains signal.
                        signal = c.evaluate('(async()=>{const a=probe.media.at(-1);const bytes=await (await fetch(a.src)).arrayBuffer();const d=await new OfflineAudioContext(1,1,48000).decodeAudioData(bytes);return d.getChannelData(0).some(v=>Math.abs(v)>.001)})()')
                        require(signal, 'decoded narration contains no audible signal')
                        # Explicit Pause then Hear word must play once while paused.
                        c.key(' ')
                        c.evaluate('probe.mark=probe.events.length;probe.used=false')
                        c.click(780,637)
                        c.until('probe.events.slice(probe.mark).some(e=>e.type==="playing")', 'paused Hear word')
                        time.sleep(7)
                        require(c.evaluate('probe.events.slice(probe.mark).filter(e=>e.type==="playing").length')==1, 'Hear word resumed autoplay or duplicated voice')
                        if mode in ('play-reject','loading-idle'):
                            require(c.evaluate('probe.used'), 'paused manual Hear word did not exercise retry')
                        require(c.evaluate('probe.events.slice(probe.mark).filter(e=>e.type==="playing").every(e=>e.path==='+json.dumps(event['path'])+')'), 'Hear word changed page')
                    scenario['ok'] = True
                finally:
                    scenario['observations'] = c.evaluate('probe.summary()')
        except Exception as error:
            scenario.update(ok=False, error=str(error))
            if 'Timed out: wasm startup' in str(error):
                result['limitation'] = 'Application startup failed; remaining fault scenarios not run.'
                break
    result['ok'] = all(s['ok'] for s in result['scenarios'])
    return result


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


@contextmanager
def serve(root):
    server = http.server.ThreadingHTTPServer(('127.0.0.1',0), functools.partial(QuietHandler, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown(); server.server_close(); thread.join()


def self_test():
    # Exercise the real CDP transport, JS exception propagation and injected
    # native play rejection in private Chromium, without pretending wasm ran.
    with browser() as c:
        require(c.evaluate('6*7')==42, 'CDP evaluation')
        try:
            c.evaluate('throw Error("expected self-test exception")')
        except AssertionError:
            pass
        else:
            raise AssertionError('JS exceptions silently ignored')
        c.evaluate('document.body.innerHTML=\'<canvas id="canvas"></canvas>\'')
        c.evaluate(PROBE)
        c.evaluate('probe.mode="play-reject";probe.armed=true;window.a=new Audio();a.junglePath="assets/jungle-book/sounds/test.wav"')
        value = c.evaluate('(async()=>{try{await a.play();return false}catch(e){return e.name==="NotAllowedError"}})()')
        require(value and c.evaluate('probe.used'), 'one-shot native play injection')
        require(c.evaluate('probe.events.filter(e=>e.type==="injected-play-rejection").length')==1, 'injection count')
        # Wrong/blank image cannot satisfy the visibility comparator.
        c.evaluate('window.Module={FS:{analyzePath:()=>({exists:false})}}')
        require(not c.evaluate('probe.checkPicture(0)')['ok'], 'blank picture accepted')
        c.evaluate('window.soundBytes=async()=>new Uint8Array([1]); Module.jungleImageReady=()=>true;probe.install();probe.mode="loading-idle";probe.used=false')
        require(c.evaluate('(async()=>{try{await soundBytes("assets/jungle-book/sounds/test.wav",()=>true);return false}catch{return true}})()'), 'loading failure did not reject')
        require(c.evaluate('(async()=>Array.from(await soundBytes("assets/jungle-book/sounds/test.wav",()=>true)))()')==[1], 'loading injection replaced production retry')
        require(c.evaluate('probe.events.some(e=>e.type==="injected-loading")&&probe.events.some(e=>e.type==="injected-idle")'), 'loading transition missing')
        # Positive and negative framebuffer comparisons use synthetic pixels only
        # to validate the comparator, never to substitute for an app scenario.
        c.evaluate('''(async()=>{
          const ref=document.createElement('canvas');ref.width=ref.height=64;
          const ctx=ref.getContext('2d');ctx.fillStyle='#d02040';ctx.fillRect(0,0,64,64);
          const bytes=new Uint8Array(await(await new Promise(r=>ref.toBlob(r))).arrayBuffer());
          Module.FS={analyzePath:p=>({exists:p==='/assets/jungle-book/pages/test.png'}),readFile:()=>bytes};
          const screen=document.getElementById('canvas');screen.width=1280;screen.height=675;
          screen.getContext('2d').drawImage(ref,330.5,56,619,619);
          probe.captures.push({image:'assets/jungle-book/pages/test.png',png:screen.toDataURL(),dom:[]});
        })()''')
        require(c.evaluate('probe.checkPicture(1)')['ok'], 'visible framebuffer rejected')
        c.evaluate('document.getElementById("canvas").getContext("2d").clearRect(0,0,1280,675);probe.captures[1].png=document.getElementById("canvas").toDataURL()')
        require(not c.evaluate('probe.checkPicture(1)')['ok'], 'blank framebuffer accepted against real reference')
        # Kryon's paint layer owns visible pictures; the semantic root may
        # contain deliberately transparent images for accessibility.
        c.evaluate('''(async()=>{
          const root=document.createElement('div');root.id='kryon-dom-paint';document.body.append(root);
          const image=document.createElement('img');image.style.cssText='position:absolute;left:330.5px;top:56px;width:619px;height:619px';
          image.src=URL.createObjectURL(new Blob([Module.FS.readFile('/assets/jungle-book/pages/test.png')]));
          await image.decode();root.append(image);
          probe.captures[1].dom=probe.visiblePictures();
        })()''')
        require(c.evaluate('probe.checkPicture(1)')['method']=='visible-dom-image', 'visible paint-layer picture rejected')
        c.evaluate('document.getElementById("kryon-dom-paint").style.opacity="0";probe.captures[1].dom=probe.visiblePictures()')
        require(not c.evaluate('probe.checkPicture(1)')['ok'], 'picture with invisible ancestor accepted')
    print('local harness self-test: CDP, JS errors, one-shot play/loading failures, positive/negative framebuffer comparisons passed (no wasm app tested)')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--base-url')
    parser.add_argument('--web-root', type=Path)
    parser.add_argument('--renderer', choices=['canvas','dom','both'], default='both')
    parser.add_argument('--expect-revision')
    args = parser.parse_args()
    require(subprocess.run(['git','check-ignore','-q',str(WORK/'receipt.json')],cwd=ROOT).returncode==0, 'receipt directory must be ignored')
    if args.self_test:
        self_test(); return 0
    require(bool(args.base_url) != bool(args.web_root), 'choose --base-url or --web-root')
    def run(url):
        results = []
        for renderer in (['canvas','dom'] if args.renderer=='both' else [args.renderer]):
            try:
                identity = fingerprint(url, renderer)
                if args.expect_revision:
                    require(identity['version.json']['revision']==args.expect_revision, 'candidate revision mismatch')
                result = test_first_book_media_start(url, renderer)
            except Exception as error:
                result = {'renderer':renderer,'ok':False,'error':str(error)}
            results.append(result)
            runtime_test.claim(WORK)
            (WORK/(renderer+'-receipt.json')).write_text(json.dumps(result, indent=2)+'\n')
            print(renderer+': '+('PASS' if result['ok'] else 'FAIL')+' '+json.dumps({k:v for k,v in result.items() if k not in ('scenarios',)}))
            for scenario in result.get('scenarios',[]):
                print('  '+scenario['mode']+': '+('PASS' if scenario['ok'] else scenario['error']))
        return 0 if all(r['ok'] for r in results) else 1
    if args.web_root:
        with serve(args.web_root.resolve()) as url:
            return run(url)
    return run(args.base_url)


if __name__=='__main__':
    raise SystemExit(main())

import {bookPosition} from './book_web_geometry.mjs';
// Private headless browser; never attaches to the owner's desktop/profile.
import {spawn} from 'node:child_process';
import {readFile,writeFile,mkdtemp,rm,mkdir} from 'node:fs/promises';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import {join,resolve,extname} from 'node:path';
import {tmpdir} from 'node:os';
import {setTimeout as delay} from 'node:timers/promises';
await mkdir('work/w',{recursive:true});await mkdir('work/b',{recursive:true});
const root=resolve(process.env.JUNGLE_WEB_ROOT||'build/web'),prefix='/embed/jungle/',profile=await mkdtemp(resolve('work/w/p-'));
const hasABC=(await readFile('games/catalog.txt','utf8')).includes('jungle-abc.zx|');
const hasNumbers=(await readFile('games/catalog.txt','utf8')).includes('jungle-numbers.zx|');
const mime={'.html':'text/html','.js':'text/javascript','.wasm':'application/wasm','.json':'application/json','.webmanifest':'application/manifest+json','.ico':'image/x-icon','.xml':'application/xml','.jpg':'image/jpeg','.png':'image/png','.wav':'audio/wav'};
let stalePictureRequests=0,transientPictureFailures=0,transientListFailures=0;
const server=createServer(async(req,res)=>{try{const request=new URL(req.url,'http://localhost');if(!request.pathname.startsWith(prefix))throw Error('Outside embed path');request.pathname=request.pathname.slice(prefix.length-1);let file=resolve(root,'.'+decodeURIComponent(request.pathname));if(!file.startsWith(root+'/')&&file!==root)throw Error();if(file===root||file.endsWith('/'))file=join(file,'index.html');
 // A brief CDN/network failure must recover while the opening screen stays up.
 if(request.pathname==='/images.json'&&transientListFailures++===0){res.writeHead(503);res.end('Temporary picture list failure');return}
 if(request.pathname==='/assets/jungle/covers/book.jpg'&&request.searchParams.has('v')&&transientPictureFailures++===0){res.writeHead(503);res.end('Temporary picture failure');return}
 // An old, cacheable URL deliberately serves a previous picture. A new
 // deployment must request its revision rather than reuse that cache entry.
 if(request.pathname==='/assets/jungle/covers/book.jpg'&&!request.searchParams.has('v')){file=join(root,'assets/jungle/covers/abc.jpg');stalePictureRequests++}
 const data=await readFile(file);res.writeHead(200,{'Content-Type':mime[extname(file)]||'application/octet-stream','Cache-Control':'public, max-age=14400'});res.end(data)}catch{res.writeHead(404);res.end()}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const url=process.argv[2]||'http://127.0.0.1:'+server.address().port+prefix+(process.env.JUNGLE_WEB_PAGE||'');
const env={...process.env};for(const name of ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','DBUS_SESSION_BUS_ADDRESS','SESSION_MANAGER'])delete env[name];env.YUE_DESKTOP_RECOVERY='0';env.TMPDIR=resolve('work/b');
const browser=spawn(process.env.CHROMIUM||'chromium',['--headless','--mute-audio','--no-sandbox','--disable-gpu','--disable-webgl','--disable-dev-shm-usage','--no-first-run','--no-default-browser-check','--window-size=960,600','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{env,stdio:['ignore','ignore','pipe']});
let stderr='',socket,diagnostics=[];browser.stderr.on('data',d=>stderr=(stderr+d).slice(-4000));
try{
 let port;const deadline=Date.now()+30000;
 while(Date.now()<deadline){try{port=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break}catch{}if(browser.exitCode!==null)throw Error(stderr);await delay(100)}
 if(!port)throw Error('Private Chromium did not expose a test port: '+stderr);
 const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
 socket=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j});
 let sequence=0;const pending=new Map();socket.onmessage=e=>{const m=JSON.parse(e.data);if(m.method==='Runtime.exceptionThrown')diagnostics.push(m.params);if(m.method==='Runtime.consoleAPICalled'&&m.params.type==='error')diagnostics.push(m.params.args.map(a=>a.value||a.description));if(pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id)}};
 async function command(method,params={}){const id=++sequence;const result=new Promise(r=>pending.set(id,r));socket.send(JSON.stringify({id,method,params}));return result}
 async function evaluate(expression){const r=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.result?.exceptionDetails)throw Error(JSON.stringify(r.result.exceptionDetails));return r.result?.result?.value}
 async function key(key,code=key){if(key==='Enter'||key===' ')await evaluate('if(document.documentElement.dataset.backend==="dom")document.activeElement?.blur()');await command('Input.dispatchKeyEvent',{type:'keyDown',key,code,windowsVirtualKeyCode:key==='Home'?36:key==='Enter'?13:key==='Escape'?27:key.startsWith('Arrow')?({ArrowLeft:37,ArrowUp:38,ArrowRight:39,ArrowDown:40}[key]):key.charCodeAt(0)});await delay(100);await command('Input.dispatchKeyEvent',{type:'keyUp',key,code});await delay(250)}
 async function click(x,y){const b=await evaluate('(()=>{let b=document.getElementById("canvas").getBoundingClientRect();return {x:b.x,y:b.y,w:b.width,h:b.height}})()');x=b.x+x*b.w/320;y=b.y+y*b.h/200;await command('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});await delay(80);await command('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',clickCount:1});await delay(400)}
 await command('Runtime.enable');await command('Network.enable');await command('Network.setBlockedURLs',{urls:['*/assets/jungle/covers/paint.jpg*']});await command('Page.enable');await command('Page.addScriptToEvaluateOnNewDocument',{source:'performance.setResourceTimingBufferSize(5000);window.jungleTestVoices=[];Object.defineProperty(HTMLMediaElement.prototype,"junglePath",{get(){return this.dataset.junglePath},set(path){this.dataset.junglePath=path;window.jungleTestRequestedAudio=this}});const jungleOriginalPlay=HTMLMediaElement.prototype.play;HTMLMediaElement.prototype.play=function(){window.jungleTestVoices.push(this.junglePath||this.src);window.jungleTestAudio=this;return jungleOriginalPlay.apply(this,arguments)}'});await command('Emulation.setDeviceMetricsOverride',{width:1280,height:800,deviceScaleFactor:1,mobile:false});await command('Page.navigate',{url});
 let ready=false;while(Date.now()<deadline){if(await evaluate('typeof Module!=="undefined"&&Module.FS&&document.getElementById("loading").style.display==="none"')){ready=true;break}if(diagnostics.length)throw Error(JSON.stringify(diagnostics));await delay(250)}
 if(!ready)throw Error('Browser startup timeout '+JSON.stringify(diagnostics)+' '+await evaluate('JSON.stringify({url:location.href,title:document.title,text:document.body?.innerText?.slice(0,500)})'));await delay(1000);
 if(!process.argv[2]&&(transientListFailures<2||transientPictureFailures<2))throw Error('Startup did not retry the temporary picture list/image failures');
 if(await evaluate('Module.FS.analyzePath("/assets/jungle/covers/paint.jpg").exists||imagePaths.has("assets/jungle/covers/paint.jpg")'))throw Error('The deliberately blocked optional cover was not skipped');
 if(!(await evaluate('Module.FS.analyzePath("/assets/jungle/covers/counting.jpg").exists'))||await evaluate('imagePaths.has("assets/jungle/covers/count.png")'))throw Error('Counting still uses the content-blocked cover filename');
 // Menu pictures and the tiny bitmap fonts load before opening. Other game
 // pictures stay lazy; Story must be able to paint its first typed letter.
 if(!await evaluate('Module.FS.analyzePath("/assets/dino-paint/font.png").exists'))throw Error('Story font was not loaded before typing');
 if(await evaluate('Module.FS.analyzePath("/assets/jigsaw/tiger-stream-8.png").exists||Module.FS.analyzePath("/assets/jungle-book/pages/tiger.jpg").exists'))throw Error('Startup downloaded game pictures before the menu needed them');
 const expectedTiger=createHash('sha256').update(await readFile(join(root,'assets/jungle/covers/book.jpg'))).digest('hex');
 const actualTiger=await evaluate('(async()=>Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",Module.FS.readFile("/assets/jungle/covers/book.jpg")))).map(byte=>byte.toString(16).padStart(2,"0")).join(""))()');
 if(actualTiger!==expectedTiger)throw Error('A cached picture from an earlier release replaced the current Picture Book cover');
 const revision=await evaluate('buildRevision');
 if(!/^[a-f0-9]{40}$/.test(revision))throw Error('Browser build revision is missing');
 const unversioned=await evaluate('performance.getEntriesByType("resource").map(entry=>new URL(entry.name)).filter(url=>(url.pathname.includes("/assets/")&&/\\.(png|jpg)$/.test(url.pathname)||["jungle.js","jungle.wasm","images.json","asset-packs.js","asset-packs.json"].some(name=>url.pathname.endsWith("/"+name)))&&url.searchParams.get("v")!=='+JSON.stringify(revision)+').map(url=>url.pathname)');
 if(unversioned.length||stalePictureRequests)throw Error('A deployment reused unversioned cached resources: '+JSON.stringify(unversioned));
 await mkdir('backup/catalog-ui-integration/web',{recursive:true});
 const captures=new Map();
 async function pagePixels(trimBottom=0){const {w,h}=await evaluate('({w:Module.canvas.clientWidth,h:Module.canvas.clientHeight})');return (await command('Page.captureScreenshot',{format:'png',clip:{x:0,y:56,width:w,height:h-56-trimBottom,scale:1}})).result.data}
 async function shot(name,pageOnly=false,trimBottom=0){const data=pageOnly?await pagePixels(trimBottom):(await command('Page.captureScreenshot',{format:'png'})).result.data;captures.set(name,data);await writeFile('backup/catalog-ui-integration/web/'+name+'.png',Buffer.from(data,'base64'));return data}
 async function pixelClick(x,y,touch=false){
  if(touch){await command('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});await delay(70);await command('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]})}
  else{await command('Input.dispatchMouseEvent',{type:'mouseMoved',x,y});await command('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});await delay(70);await command('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',clickCount:1})}
  await delay(250)
 }
 async function resize(width,height,mobile=false){await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile});await command('Emulation.setTouchEmulationEnabled',{enabled:mobile,maxTouchPoints:1});await delay(500);const box=await evaluate('({w:Module.canvas.clientWidth,h:Module.canvas.clientHeight})');if(box.w!==width||box.h!==height)throw Error('Canvas did not resize to the viewport '+JSON.stringify(box))}
 async function waitPage(name){const until=Date.now()+15000;const path='/assets/jungle-book/pages/'+name+'.jpg';while(Date.now()<until){if(await evaluate('Module.FS.analyzePath('+JSON.stringify(path)+').exists'))return;await delay(100)}throw Error('Page image did not load: '+name)}
 async function waitResource(fragment){const until=Date.now()+12000;while(Date.now()<until){if(await evaluate('[...imageLoads.keys(),...window.jungleTestVoices].some(name=>name.includes('+JSON.stringify(fragment)+'))'))return;await delay(100)}throw Error('Missing lesson audio/image resource: '+fragment)}
 async function waitSpoken(fragment){const until=Date.now()+12000;while(Date.now()<until){if(await evaluate('window.jungleTestVoices.some(path=>path.includes('+JSON.stringify(fragment)+'))'))return;await delay(100)}throw Error('Missing actual playback: '+fragment)}
 async function swipe(x,y,xx,yy){await command('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});for(let i=1;i<=6;i++){await delay(35);await command('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x+(xx-x)*i/6,y:y+(yy-y)*i/6}]})}await command('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await delay(350)}
 const rows=(await readFile('games/catalog.txt','utf8')).trim().split('\n').map(l=>l.split('|')).filter(r=>r[1]!=='123 Book').sort((a,b)=>Number(a[4])-Number(b[4]));
 async function openCatalog(title){const index=rows.findIndex(r=>r[1]===title);if(index<0)throw Error('Missing catalog game '+title);await key('Home');for(let i=0;i<index;i++)await key('ArrowDown');await key('Enter')}
 const missing=await evaluate('Array.from(imagePaths).filter(path=>/^assets\\/jungle\\/([^/]+|covers\\/[^/]+|branding\\/[^/]+)$/.test(path)&&!Module.FS.analyzePath("/"+path).exists).length');if(missing)throw Error('Opening screen cleared before the menu pictures loaded: '+missing);await shot('menu');
 await evaluate(`(()=>{const original=soundBytes;let holding=true,release;const released=new Promise(resolve=>release=resolve);const held=[];window.jungleTestHeldNarration=[];window.HoldNarrationForTest=()=>{soundBytes=async(path,current)=>{const index=await speech();if(!holding||!index.voices.has(path))return original(path,current);window.jungleTestHeldNarration.push(path);const request=(async()=>{await released;return current()?original(path,current):null})();held.push(request);return request};window.jungleTestReleaseNarration=async()=>{holding=false;release();await Promise.allSettled(held)}}})()`);
 await evaluate('window.HoldNarrationForTest()');
 await openCatalog('Picture Book');await shot('books');if(await evaluate('window.jungleTestHeldNarration.length'))throw Error('Opening Picture Book skipped the category list');await key('0','Digit0');await waitPage('carrot');await delay(300);const first=await shot('vegetables-desktop',true,64);
 const heldNarration=Date.now()+12000;while(Date.now()<heldNarration){if(await evaluate('window.jungleTestHeldNarration.length'))break;await delay(100)}
 if(!await evaluate('window.jungleTestHeldNarration.length'))throw Error('Picture Book narration did not reach the soundBytes boundary');
 await key(' ','Space');const pausedBook=await pagePixels();await delay(6500);if(pausedBook!==await pagePixels())throw Error('Space did not hold the picture book');
 await pixelClick(780,762);if(!await evaluate('window.jungleTestRequestedAudio?.jungleLoading||!window.jungleTestRequestedAudio?.paused'))throw Error('Hear word did not start while the book was paused');await key(' ','Space');
 // Compare page content independently of transport-button antialiasing.
 await pixelClick(1188,712);const second=await shot('vegetables-next',true,64);if(first===second)throw Error('Page navigation froze under stalled narration');
 await pixelClick(92,712);const restored=await shot('vegetables-restored',true,64);if(restored!==first)throw Error('Back page failed under stalled narration');
 await resize(390,844,true);const phoneFirst=await shot('vegetables-phone',true,64);
 await pixelClick(333,700,true);const phoneSecond=await shot('vegetables-phone-next',true,64);if(phoneFirst===phoneSecond)throw Error('Touch Next failed');
 await swipe(320,350,45,350);const swiped=await shot('vegetables-phone-swipe',true,64);if(swiped===phoneSecond)throw Error('Touch swipe did not turn the page');
 await swipe(45,350,320,350);const swipedBack=await pagePixels(64);if(swipedBack!==phoneSecond)throw Error('Reverse touch swipe lost its page');
 await evaluate('window.jungleTestReleaseNarration()');
 await pixelClick(34,28,true);await shot('books-phone');
 await pixelClick(195,343,true);const fromCover=await shot('vegetables-cover-touch',true);await pixelClick(34,28,true);await key('0','Digit0');const directCover=await pagePixels();if(fromCover!==directCover)throw Error('Vegetables cover opened the wrong book');await pixelClick(34,28,true);
 await swipe(90,620,90,160);await shot('books-touch-scroll');
 for(const [w,h,mobile] of [[320,568,true],[844,390,true],[768,1024,true],[1920,1080,false],[390,844,true]]){await resize(w,h,mobile);await shot('shelf-'+w+'-'+h)}
 async function selectBook(id){const {x,y,index}=bookPosition(id,390,844);await pixelClick(x,y,true);for(let i=0;i<index;i++)await key('ArrowRight','ArrowRight');await evaluate('window.jungleTestVoices=[]');await key('Enter','Enter')}
 for(const [id,image] of [['family','mother'],['body','head'],['clothing','shirt'],['seasons','spring'],['breakfast','bread'],['lunch','sandwich'],['dinner','roast_chicken']]){
  await selectBook(id);await waitPage(image);await shot(id+'-phone');await pixelClick(34,28,true);
 }
 for(const [name,voice] of [['toys','teddy'],['vehicles','car'],['bedtime','toothpaste'],['birds','owl']]){
  await selectBook(name);await waitSpoken('/simple/'+voice+'.wav');await shot('new-book-'+name);await pixelClick(34,28,true);
 }
 if(process.env.JUNGLE_BOOK_ONLY){if(diagnostics.length)throw Error(JSON.stringify(diagnostics));console.log('local browser Book-only test passed at '+url)}
 else {
 await pixelClick(34,28,true);await shot('restored-menu-phone');await pixelClick(325,102,true);if(await evaluate('Module.FS.readFile("/kryon-apps/jungle/settings/language.txt",{encoding:"utf8"})')!=="es")throw Error('Spanish flag did not persist');
 if(await evaluate('document.documentElement.lang')!=='es')throw Error('Website metadata did not follow the selected language');
 if(!(await evaluate('document.querySelector("meta[name=description]").content')).startsWith('Aprende'))throw Error('Spanish website description is missing');
 if(hasABC){
  const resources=()=>evaluate('[...imageLoads.keys(),...window.jungleTestVoices]');
  await openCatalog('ABC Book');await shot('letters-numbers-hub');await key('1');await shot('abc-letters-phone');
  await waitResource('/abc/sounds/es/letters/0061.wav');
  // Switch to a separate private tab: narration and progression must continue
  // when the lesson is hidden, not only after it regains focus.
  const originalTarget=pages.find(p=>p.type==='page').id;
  const other=await command('Target.createTarget',{url:'about:blank'});
  await command('Target.activateTarget',{targetId:other.result.targetId});
  await delay(300);
  if(!await evaluate('document.hidden'))throw Error('Private test did not hide the lesson tab');
  await waitResource('/abc/sounds/es/letters/0062.wav');
  await command('Target.activateTarget',{targetId:originalTarget});
  await command('Target.closeTarget',{targetId:other.result.targetId});
  const fasterAt=Date.now();
  await pixelClick(285,28,true); // Normal -> Fast.
  await waitResource('/abc/sounds/es/letters/0063.wav');
  if(Date.now()-fasterAt>3500)throw Error('Fast pace did not advance the alphabet sooner');
  await key('b','KeyB');const pausedAlphabet=await pagePixels();await delay(4500);
  if(pausedAlphabet!==await pagePixels())throw Error('Manual letter selection did not pause the sequence');
  if((await resources()).some(n=>n.includes('/jungle-book/sounds/es/simple/garlic.wav')))throw Error('Default alphabet spoke a word example');
  await key('a','KeyA');await pixelClick(195,101,true);
  await waitResource('/jungle-book/pages/garlic.jpg');await waitResource('/jungle-book/sounds/es/simple/garlic.wav');await shot('abc-example-phone');
  await pixelClick(200,562,true);await waitResource('/jungle-book/pages/water.jpg');await shot('abc-next-example-phone');
  await evaluate('window.jungleTestVoices=[]');await pixelClick(90,557,true);await waitSpoken('/abc/sounds/es/letters/0061.wav');await shot('abc-letter-only-example-phone');
  await evaluate('window.jungleTestVoices=[]');await key(' ','Space');await waitSpoken('/abc/sounds/es/letters/0062.wav');await shot('abc-examples-autoplay-phone');
  await key(' ','Space');await evaluate('window.jungleTestVoices=[]');await delay(2700);if(await evaluate('window.jungleTestVoices.length'))throw Error('Paused example autoplay kept speaking');
  await pixelClick(80,101,true);await key(' ','Space');await shot('abc-letters-return-phone');
  await pixelClick(34,28,true);await key('Escape');await shot('menu-after-abc-phone');
 }
 if(hasNumbers){
  await openCatalog('ABC Book');await key('2');const numbersLearn=await shot('numbers-learn-phone');await waitResource('/numbers/sounds/es/1.wav');
  await waitSpoken('/numbers/sounds/es/2.wav');
  const numberImages=await evaluate('[...imageLoads.keys(),...window.jungleTestVoices]');if(!numberImages.some(path=>path.includes('/jungle-book/counting/')))throw Error('123 did not load the small counting pictures');
  if(numberImages.some(path=>path.includes('/jungle-book/items/')))throw Error('123 loaded full-size counting pictures');
  await key('0');await waitResource('/numbers/sounds/es/10.wav');if(numbersLearn===await shot('numbers-ten-phone'))throw Error('123 did not open directly into learning');
  await waitSpoken('/numbers/sounds/es/11.wav');await key(' ','Space');await evaluate('window.jungleTestVoices=[]');await delay(4500);if(await evaluate('window.jungleTestVoices.length'))throw Error('Paused number autoplay kept speaking');await shot('numbers-autoplay-paused-phone');
  await key('0');await evaluate('window.jungleTestVoices=[]');await swipe(300,320,90,320);await waitSpoken('/numbers/sounds/es/11.wav');
  await evaluate('window.jungleTestVoices=[]');await swipe(90,320,300,320);await waitSpoken('/numbers/sounds/es/10.wav');
  for(let i=0;i<10;i++)await key('ArrowRight','ArrowRight');await waitSpoken('/numbers/sounds/es/20.wav');await shot('numbers-twenty-phone');
  await evaluate('window.jungleTestVoices=[]');await key(' ','Space');await waitSpoken('/numbers/sounds/es/1.wav');
  await pixelClick(34,28,true);await key('Escape');await shot('menu-after-numbers-phone');
 }
 await openCatalog('Animal Counting');await shot('counting-lessons-phone');
 await key('1','Digit1');await delay(450);await shot('counting-phone');
 const countScale=Math.min(390/320,788/540),countTop=56+(788-540*countScale)/2;
 async function countKey(index){await pixelClick((67+index%3*92)*countScale,countTop+(367+Math.floor(index/3)*40)*countScale,true)}
 let counted=false;for(let n=1;n<=4;n++){
  await countKey(9);await countKey(n-1);await countKey(11);
  const count=await evaluate('(()=>{try{return Number(Module.FS.readFile("/kryon-apps/jungle/jungle.animals/progress.txt",{encoding:"utf8"}).trim().split(" ")[2])}catch{return 0}})()');if(count>0){counted=true;break}
 }if(!counted)throw Error('Counting touch keypad did not submit an answer');
 await pixelClick(34,28,true);await pixelClick(34,28,true);await openCatalog('Coloring Book');await shot('paint-phone');
 // Paint mixes responsive screen coordinates with the book's virtual dialogs.
 const paintWidth=390,paintHeight=788,paintPad=9,paintGap=4;
 const paintToolWidth=121,paintToolHeight=90,paintCanvas={x:9,y:65,w:372,h:279};
 const paintTool=async index=>pixelClick(paintPad+index%3*(paintToolWidth+paintGap)+paintToolWidth/2,
  56+399+Math.floor(index/3)*(paintToolHeight+paintGap)+paintToolHeight/2,true);
 const paintPoint=(x,y)=>({x:paintCanvas.x+x*paintCanvas.w/960,y:paintCanvas.y+y*paintCanvas.h/720});
 const legacy=async(x,y)=>pixelClick(x*paintWidth/320,56+(paintHeight-paintWidth*200/320)/2+y*paintWidth/320,true);
 const stencilPad=16,stencilGap=10,stencilTabWidth=174,stencilCardHeight=178;
 const stencilCategory=async index=>pixelClick(stencilPad+index%2*(stencilTabWidth+stencilGap)+stencilTabWidth/2,
  56+56+Math.floor(index/2)*54+22,true);
 const stencilFirst=async()=>pixelClick(stencilPad+87,56+164+stencilCardHeight/2,true);
 const paintPath='/kryon-apps/jungle/jungle.paint/';
 const paintText=async name=>evaluate(`(()=>{const p=${JSON.stringify(paintPath)}+${JSON.stringify(name)};return Module.FS.analyzePath(p).exists?new TextDecoder('latin1').decode(Module.FS.readFile(p)):null})()`);
 async function paintChanged(before,what){const until=Date.now()+15000;while(Date.now()<until){const now=await paintText('working.txt');if(now&&now!==before)return now;await delay(100)}throw Error(what+' did not change the working picture')}
 async function placeStencil(name,dropX=220){
  const before=await paintText('working.txt');
  const start=paintPoint(480,360),end=paintPoint(dropX,180);
  await swipe(start.x,start.y,end.x,end.y);
  if(await paintText('working.txt')!==before)throw Error('Releasing the stencil committed it');
  await pixelClick(268,56+9+279-26,true);await paintChanged(before,name+' placement');await shot('placed-'+name);
 }
 // A new picture must choose its background before the first stencil.
 await pixelClick(103,56+110+106,true);await stencilFirst();await placeStencil('dinosaur');
 await paintTool(2);await legacy(10,36);
 if(await evaluate('document.activeElement.id')!=='mobile-input')throw Error('Story did not focus mobile text input');
 await command('Input.insertText',{text:'Niño, piña'});await delay(500);await shot('story-phone');await legacy(266,180);
 await paintTool(4);await legacy(253,38);await legacy(60,80);
 const story=await paintText('slot-0.txt');if(!story?.includes('Niño, piña'))throw Error('Mobile story lost accented text');
 // Desktop typing takes the canvas keypress route, without the phone editor.
 await resize(1280,800,false);await pixelClick(159,270);
 await pixelClick(82,56+54*3.72); // Start of the second story line.
 await evaluate('document.getElementById("mobile-input").blur();Module.canvas.focus()');
 for(const text of 'Desktop ñ'){
  await command('Input.dispatchKeyEvent',{type:'keyDown',key:text,text,unmodifiedText:text});await delay(80);
  await command('Input.dispatchKeyEvent',{type:'keyUp',key:text});
 }
 await delay(400);await shot('story-desktop');
 if(await evaluate('document.body.innerText.includes("Missing image")'))throw Error('Desktop story displayed missing-image placeholders');
 await key('Enter');
 if(!(await paintText('working.txt'))?.includes('Desktop ñ'))throw Error('Desktop story did not save typed letters');
 await resize(390,844,true);
 for(const [category,name,dropX] of [[1,'animals',310],[2,'people',430],[3,'objects',550]]){
  await paintTool(0);await stencilCategory(category);await shot('stencils-'+name);await stencilFirst();
  await placeStencil(name,dropX);
 }
 // Select changes no pixels; the above-centre handle turns the last object
 // through a non-right angle, and only its release commits one Undo step.
 const selectedText=await paintText('working.txt'),lines=selectedText.split('\n'),objectCount=Number(lines[12]);
 if(objectCount!==4)throw Error('Responsive stencil placement lost an object: '+objectCount);
 const [objectX,objectY,objectW,objectH]=lines[13+(objectCount-1)*2].split(' ').map(Number),encoded=lines[14+(objectCount-1)*2];
 const paintCodes='0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_',objectPixels=new Uint8Array(objectW*objectH);
 let runAt=0,pixelAt=0;
 while(pixelAt<objectPixels.length){const color=encoded[runAt]==='~'?255:paintCodes.indexOf(encoded[runAt]);runAt++;let count=0,shift=0,digit;do{digit=paintCodes.indexOf(encoded[runAt++]);count+=(digit&31)*2**shift;shift+=5}while(digit>=32);objectPixels.fill(color,pixelAt,pixelAt+count);pixelAt+=count}
 let x0=objectW,y0=objectH,x1=0,y1=0,hit,best=Infinity;
 for(let y=0;y<objectH;y++)for(let x=0;x<objectW;x++)if(objectPixels[y*objectW+x]!==255){x0=Math.min(x0,x);y0=Math.min(y0,y);x1=Math.max(x1,x+1);y1=Math.max(y1,y+1);const distance=(x-objectW/2)**2+(y-objectH/2)**2;if(distance<best){best=distance;hit={x:objectX+x+.5,y:objectY+y+.5}}}
 await paintTool(8);const objectHit=paintPoint(hit.x,hit.y);await pixelClick(objectHit.x,objectHit.y,true);await delay(900);
 if(await paintText('working.txt')!==selectedText)throw Error('Select changed the mobile picture');
 const historyBefore=await paintText('working-undo.txt'),center=paintPoint(objectX+x0+(x1-x0)/2,objectY+y0+(y1-y0)/2);
 const handle={x:center.x,y:Math.max(68,paintPoint(objectX+x0,objectY+y0).y-24)},radius=center.y-handle.y;
 await command('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[handle]});await delay(100);
 let end;
 for(let step=1;step<=6;step++){const angle=37*Math.PI/180*step/6;end={x:center.x+radius*Math.sin(angle),y:center.y-radius*Math.cos(angle)};await command('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[end]});await delay(70)}
 await shot('paint-phone-free-rotation-held');
 if(await paintText('working.txt')!==selectedText||await paintText('working-undo.txt')!==historyBefore)throw Error('Mobile rotation committed while held');
 await command('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 const rotatedText=await paintChanged(selectedText,'free handle rotation');
 const oldSteps=Number(historyBefore.split('\n')[2]),newSteps=Number((await paintText('working-undo.txt')).split('\n')[2]);
 if(newSteps!==Math.min(8,oldSteps+1))throw Error('Mobile rotation did not push one Undo');
 const rotatedBounds=rotatedText.split('\n')[13+(objectCount-1)*2].split(' ').map(Number);
 if(rotatedBounds[2]===objectH&&rotatedBounds[3]===objectW)throw Error('Mobile handle snapped to 90 degrees');
 await paintTool(6);await paintChanged(rotatedText,'rotation Undo');
 if(await paintText('working.txt')!==selectedText)throw Error('Mobile rotation Undo lost paint or layers');
 // Gallery Slots still reopen the accented picture and its saved preview.
 await paintTool(4);await legacy(253,38);await legacy(232,38);await legacy(60,80);
 await delay(500);if(!(await paintText('working.txt')).includes('Niño, piña'))throw Error('Slots Load lost accented story');
 await pixelClick(34,28,true);await shot('menu-after-paint-back');
 await delay(1200);await command('Page.reload');await delay(500);const reloaded=Date.now()+30000;while(Date.now()<reloaded){if(await evaluate('typeof Module!=="undefined"&&Module.FS&&document.getElementById("loading").style.display==="none"'))break;await delay(200)}await delay(500);
 if(await evaluate('Module.FS.readFile("/kryon-apps/jungle/settings/language.txt",{encoding:"utf8"})')!=="es")throw Error('Language did not survive reload');
 if(diagnostics.length)throw Error(JSON.stringify(diagnostics));
 console.log('local browser test: four new books, Space pause, letter-only examples and autoplay, number autoplay, category navigation, touch controls, stencils and accented saves passed at '+url);
 }
}finally{if(socket)socket.close();browser.kill('SIGTERM');await new Promise(r=>{if(browser.exitCode!==null||browser.signalCode!==null)r();else browser.once('exit',r)});await new Promise(r=>server.close(r));await rm(profile,{recursive:true,force:true,maxRetries:20,retryDelay:100})}

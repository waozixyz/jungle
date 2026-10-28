// Private headless browser; never attaches to the owner's desktop/profile.
import {spawn} from 'node:child_process';
import {readFile,writeFile,mkdtemp,rm,mkdir} from 'node:fs/promises';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import {join,resolve,extname} from 'node:path';
import {tmpdir} from 'node:os';
import {setTimeout as delay} from 'node:timers/promises';
const root=resolve(process.env.JUNGLE_WEB_ROOT||'build/web'),prefix='/embed/jungle/',profile=await mkdtemp('/tmp/jungle-web-');
const packManifest=JSON.parse(await readFile(join(root,'asset-packs.json'),'utf8'));
const bookSoundPacks=[...new Set(Object.entries(packManifest.files).filter(([path])=>path.startsWith('assets/jungle-book/sounds/')).map(([,entry])=>entry.pack))];
const catalog=(await readFile('games/catalog.txt','utf8')).split('\n').filter(l=>l.includes('|')).length;
const hasABC=(await readFile('games/catalog.txt','utf8')).includes('jungle-abc.zx|');
const hasNumbers=(await readFile('games/catalog.txt','utf8')).includes('jungle-numbers.zx|');
// Phone portrait menu row centers: rows begin at virtual 112 and share (693-164)/count.
const visibleGames=catalog-Number(hasABC&&hasNumbers);
const rowY=(i,count=visibleGames)=>Math.round((112+(693-164)/count*(i+0.5))*(844/693));
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
const env={...process.env};for(const name of ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','DBUS_SESSION_BUS_ADDRESS','SESSION_MANAGER'])delete env[name];env.YUE_DESKTOP_RECOVERY='0';env.TMPDIR='/tmp';
const browser=spawn(process.env.CHROMIUM||'chromium',['--headless','--no-sandbox','--disable-gpu','--disable-webgl','--disable-dev-shm-usage','--no-first-run','--no-default-browser-check','--window-size=960,600','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{env,stdio:['ignore','ignore','pipe']});
let stderr='',socket,diagnostics=[];browser.stderr.on('data',d=>stderr=(stderr+d).slice(-4000));
try{
 let port;const deadline=Date.now()+30000;
 while(Date.now()<deadline){try{port=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break}catch{}if(browser.exitCode!==null)throw Error(stderr);await delay(100)}
 if(!port)throw Error('Private Chromium did not expose a test port: '+stderr);
 const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
 socket=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j});
 let sequence=0;let holdAudio=false;const pausedAudio=[];const pending=new Map();socket.onmessage=e=>{const m=JSON.parse(e.data);if(m.method==='Fetch.requestPaused'){if(holdAudio)pausedAudio.push(m.params.requestId);else void command('Fetch.continueRequest',{requestId:m.params.requestId})}if(m.method==='Runtime.exceptionThrown')diagnostics.push(m.params);if(m.method==='Runtime.consoleAPICalled'&&m.params.type==='error')diagnostics.push(m.params.args.map(a=>a.value||a.description));if(pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id)}};
 async function command(method,params={}){const id=++sequence;const result=new Promise(r=>pending.set(id,r));socket.send(JSON.stringify({id,method,params}));return result}
 async function evaluate(expression){const r=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.result?.exceptionDetails)throw Error(JSON.stringify(r.result.exceptionDetails));return r.result?.result?.value}
 async function key(key,code=key){if(key==='Enter'||key===' ')await evaluate('if(document.documentElement.dataset.backend==="dom")document.activeElement?.blur()');await command('Input.dispatchKeyEvent',{type:'keyDown',key,code,windowsVirtualKeyCode:key==='Enter'?13:key==='Escape'?27:key.startsWith('Arrow')?({ArrowLeft:37,ArrowUp:38,ArrowRight:39,ArrowDown:40}[key]):key.charCodeAt(0)});await delay(100);await command('Input.dispatchKeyEvent',{type:'keyUp',key,code});await delay(250)}
 async function click(x,y){const b=await evaluate('(()=>{let b=document.getElementById("canvas").getBoundingClientRect();return {x:b.x,y:b.y,w:b.width,h:b.height}})()');x=b.x+x*b.w/320;y=b.y+y*b.h/200;await command('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});await delay(80);await command('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',clickCount:1});await delay(400)}
 await command('Runtime.enable');await command('Network.enable');await command('Network.setBlockedURLs',{urls:['*/assets/jungle/covers/paint.jpg*']});await command('Page.enable');await command('Page.addScriptToEvaluateOnNewDocument',{source:'performance.setResourceTimingBufferSize(5000);window.jungleTestVoices=[];Object.defineProperty(HTMLMediaElement.prototype,"junglePath",{get(){return this.dataset.junglePath},set(path){this.dataset.junglePath=path;window.jungleTestRequestedAudio=this}});const jungleOriginalPlay=HTMLMediaElement.prototype.play;HTMLMediaElement.prototype.play=function(){window.jungleTestVoices.push(this.junglePath||this.src);window.jungleTestAudio=this;return jungleOriginalPlay.apply(this,arguments)}'});await command('Emulation.setDeviceMetricsOverride',{width:1280,height:800,deviceScaleFactor:1,mobile:false});await command('Page.navigate',{url});
 let ready=false;while(Date.now()<deadline){if(await evaluate('typeof Module!=="undefined"&&Module.FS&&document.getElementById("loading").style.display==="none"')){ready=true;break}if(diagnostics.length)throw Error(JSON.stringify(diagnostics));await delay(250)}
 if(!ready)throw Error('Browser startup timeout '+JSON.stringify(diagnostics)+' '+await evaluate('JSON.stringify({url:location.href,title:document.title,text:document.body?.innerText?.slice(0,500)})'));await delay(1000);
 if(!process.argv[2]&&(transientListFailures<2||transientPictureFailures<2))throw Error('Startup did not retry the temporary picture list/image failures');
 if(await evaluate('Module.FS.analyzePath("/assets/jungle/covers/paint.jpg").exists||imagePaths.has("assets/jungle/covers/paint.jpg")'))throw Error('The deliberately blocked optional cover was not skipped');
 if(!(await evaluate('Module.FS.analyzePath("/assets/jungle/covers/counting.jpg").exists'))||await evaluate('imagePaths.has("assets/jungle/covers/count.png")'))throw Error('Counting still uses the content-blocked cover filename');
 // Only the menu's pictures load before opening; a game's load when it shows them.
 if(await evaluate('Module.FS.analyzePath("/assets/jigsaw/tiger-stream-8.png").exists||Module.FS.analyzePath("/assets/jungle-book/pages/tiger.jpg").exists'))throw Error('Startup downloaded game pictures before the menu needed them');
 const expectedTiger=createHash('sha256').update(await readFile(join(root,'assets/jungle/covers/book.jpg'))).digest('hex');
 const actualTiger=await evaluate('(async()=>Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",Module.FS.readFile("/assets/jungle/covers/book.jpg")))).map(byte=>byte.toString(16).padStart(2,"0")).join(""))()');
 if(actualTiger!==expectedTiger)throw Error('A cached picture from an earlier release replaced the current Picture Book cover');
 const revision=await evaluate('buildRevision');
 if(!/^[a-f0-9]{40}$/.test(revision))throw Error('Browser build revision is missing');
 const unversioned=await evaluate('performance.getEntriesByType("resource").map(entry=>new URL(entry.name)).filter(url=>(url.pathname.includes("/assets/")&&/\\.(png|jpg)$/.test(url.pathname)||["jungle.js","jungle.wasm","images.json","asset-packs.js","asset-packs.json"].some(name=>url.pathname.endsWith("/"+name)))&&url.searchParams.get("v")!=='+JSON.stringify(revision)+').map(url=>url.pathname)');
 if(unversioned.length||stalePictureRequests)throw Error('A deployment reused unversioned cached resources: '+JSON.stringify(unversioned));
 await mkdir('build/tests/web',{recursive:true});
 const captures=new Map();
 async function pagePixels(trimBottom=0){const {w,h}=await evaluate('({w:Module.canvas.clientWidth,h:Module.canvas.clientHeight})');return (await command('Page.captureScreenshot',{format:'png',clip:{x:0,y:56,width:w,height:h-56-trimBottom,scale:1}})).result.data}
 async function shot(name,pageOnly=false,trimBottom=0){const data=pageOnly?await pagePixels(trimBottom):(await command('Page.captureScreenshot',{format:'png'})).result.data;captures.set(name,data);await writeFile('build/tests/web/'+name+'.png',Buffer.from(data,'base64'));return data}
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
 const missing=await evaluate('Array.from(imagePaths).filter(path=>/^assets\\/jungle\\/([^/]+|covers\\/[^/]+|branding\\/[^/]+)$/.test(path)&&!Module.FS.analyzePath("/"+path).exists).length');if(missing)throw Error('Opening screen cleared before the menu pictures loaded: '+missing);await shot('menu');
 holdAudio=true;await command('Fetch.enable',{patterns:bookSoundPacks.map(pack=>({urlPattern:'*/'+pack+'*',requestStage:'Request'}))});
 await pixelClick(400,330);await shot('books');if(pausedAudio.length)throw Error('Opening Picture Book skipped the category list');await key('0','Digit0');await waitPage('carrot');await delay(300);const first=await shot('vegetables-desktop',true,64);
 await key(' ','Space');const pausedBook=await pagePixels();await delay(6500);if(pausedBook!==await pagePixels())throw Error('Space did not hold the picture book');
 await pixelClick(780,762);if(!await evaluate('window.jungleTestRequestedAudio?.jungleLoading||!window.jungleTestRequestedAudio?.paused'))throw Error('Hear word did not start while the book was paused');await key(' ','Space');
 // Compare page content independently of transport-button antialiasing.
 await pixelClick(1188,712);const second=await shot('vegetables-next',true,64);if(first===second)throw Error('Page navigation froze under stalled narration');
 await pixelClick(92,712);const restored=await shot('vegetables-restored',true,64);if(restored!==first)throw Error('Back page failed under stalled narration');
 await resize(390,844,true);const phoneFirst=await shot('vegetables-phone',true,64);
 await pixelClick(333,700,true);const phoneSecond=await shot('vegetables-phone-next',true,64);if(phoneFirst===phoneSecond)throw Error('Touch Next failed');
 await swipe(320,350,45,350);const swiped=await shot('vegetables-phone-swipe',true,64);if(swiped===phoneSecond)throw Error('Touch swipe did not turn the page');
 await swipe(45,350,320,350);const swipedBack=await pagePixels(64);if(swipedBack!==phoneSecond)throw Error('Reverse touch swipe lost its page');
 holdAudio=false;for(const requestId of pausedAudio)await command('Fetch.continueRequest',{requestId});await command('Fetch.disable');
 await pixelClick(34,28,true);await shot('books-phone');
 await pixelClick(195,343,true);const fromCover=await shot('vegetables-cover-touch',true);await pixelClick(34,28,true);await key('0','Digit0');const directCover=await pagePixels();if(fromCover!==directCover)throw Error('Vegetables cover opened the wrong book');await pixelClick(34,28,true);
 await swipe(90,620,90,160);await shot('books-touch-scroll');
 for(const [w,h,mobile] of [[320,568,true],[844,390,true],[768,1024,true],[1920,1080,false],[390,844,true]]){await resize(w,h,mobile);await shot('shelf-'+w+'-'+h)}
 await pixelClick(280,159,true);await shot('family-tab-phone');await pixelClick(195,239,true);await delay(500);await shot('family-book-phone');await waitPage('mother');await pixelClick(34,28,true);await pixelClick(195,343,true);await delay(500);await shot('body-parts-phone');
 await waitPage('head');
 await pixelClick(34,28,true);await pixelClick(195,447,true);await waitPage('shirt');await shot('clothing-phone');
 await pixelClick(34,28,true);await pixelClick(110,107,true);await pixelClick(195,655,true);await waitPage('spring');await shot('seasons-phone');
 await pixelClick(34,28,true);await pixelClick(280,107,true);
 for(const [name,y,image] of [['breakfast',447,'bread'],['lunch',551,'sandwich'],['dinner',655,'roast_chicken']]){
  await pixelClick(195,y,true);await delay(500);await shot(name+'-phone');
  await waitPage(image);
  await pixelClick(34,28,true);
 }
 for(const [slot,name,voice] of [[4,'toys','teddy'],[5,'vehicles','car'],[6,'bedtime','bed']]){
  await pixelClick(110,159,true);for(let i=0;i<slot;i++)await key('ArrowRight','ArrowRight');await evaluate('window.jungleTestVoices=[]');await key('Enter','Enter');await waitSpoken('/simple/'+voice+'.wav');await shot('new-book-'+name);await pixelClick(34,28,true);
 }
 await pixelClick(110,107,true);for(let i=0;i<5;i++)await key('ArrowRight','ArrowRight');await evaluate('window.jungleTestVoices=[]');await key('Enter','Enter');await waitSpoken('/simple/parrot.wav');await shot('new-book-birds');await pixelClick(34,28,true);
 await pixelClick(34,28,true);await shot('restored-menu-phone');await pixelClick(325,102,true);if(await evaluate('Module.FS.readFile("/kryon-apps/jungle/settings/language.txt",{encoding:"utf8"})')!=="es")throw Error('Spanish flag did not persist');
 if(await evaluate('document.documentElement.lang')!=='es')throw Error('Website metadata did not follow the selected language');
 if(!(await evaluate('document.querySelector("meta[name=description]").content')).startsWith('Aprende'))throw Error('Spanish website description is missing');
 if(hasABC){
  const resources=()=>evaluate('[...imageLoads.keys(),...window.jungleTestVoices]');
  await pixelClick(195,rowY(1),true);await shot('letters-numbers-hub');await pixelClick(195,rowY(0,2),true);await shot('abc-letters-phone');
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
  await pixelClick(195,rowY(1),true);await pixelClick(195,rowY(1,2),true);const numbersLearn=await shot('numbers-learn-phone');await waitResource('/numbers/sounds/es/1.wav');
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
 const countingRow=(await readFile('games/catalog.txt','utf8')).split('\n').filter(line=>line.includes('|'))
  .map(line=>line.split('|')).filter(row=>row[1]!=='123 Book').sort((a,b)=>Number(a[4])-Number(b[4])).findIndex(row=>row[1]==='Animal Counting');
 await pixelClick(195,rowY(countingRow),true);await shot('counting-phone');
 let counted=false;for(let n=1;n<=4;n++){
  await pixelClick(78,796,true);const index=n-1;await pixelClick(78+(index%3)*116,628+Math.floor(index/3)*56,true);await pixelClick(310,796,true);
  const count=await evaluate('(()=>{try{return Number(Module.FS.readFile("/kryon-apps/jungle/jungle.animals/progress.txt",{encoding:"utf8"}).trim().split(" ")[2])}catch{return 0}})()');if(count>0){counted=true;break}
 }if(!counted)throw Error('Counting touch keypad did not submit an answer');
 await pixelClick(34,28,true);await pixelClick(195,rowY(countingRow+1),true);await shot('paint-phone');
 const legacy=async(x,y)=>pixelClick(x*390/320,56+(788-390*200/320)/2+y*390/320,true);
 await pixelClick(54,559,true);await legacy(52,58);await legacy(52,58);await legacy(280,90);await pixelClick(242,559,true);await legacy(10,36);
 if(await evaluate('document.activeElement.id')!=='mobile-input')throw Error('Story did not focus mobile text input');
 await command('Input.insertText',{text:'Niño, piña'});await delay(500);await shot('story-phone');await legacy(266,180);await pixelClick(54,630,true);await legacy(50,80);
 const story=await evaluate('Array.from(Module.FS.readFile("/kryon-apps/jungle/jungle.paint/slot-0.txt")).map(b=>String.fromCharCode(b)).join("")');if(!story.includes('Niño, piña'))throw Error('Mobile story lost accented text');
 for(const [category,name,dropX] of [[124,'animals',95],[195,'people',155],[266,'objects',125]]){
  await pixelClick(54,559,true);await legacy(category,38);await shot('stencils-'+name);await legacy(52,76);await legacy(52,90);
  await evaluate('Module.stencilBefore=Module.FS.readFile("/kryon-apps/jungle/jungle.paint/working.txt").slice()');
  await swipe(35,90,dropX,140);await shot('placed-'+name);
  if(!await evaluate('(()=>{const after=Module.FS.readFile("/kryon-apps/jungle/jungle.paint/working.txt");return after.length!==Module.stencilBefore.length||after.some((b,i)=>b!==Module.stencilBefore[i])})()'))throw Error(name+' stencil did not place');
 }
 await pixelClick(34,28,true);await shot('menu-after-paint-back');
 await delay(1200);await command('Page.reload');await delay(500);const reloaded=Date.now()+30000;while(Date.now()<reloaded){if(await evaluate('typeof Module!=="undefined"&&Module.FS&&document.getElementById("loading").style.display==="none"'))break;await delay(200)}await delay(500);
 if(await evaluate('Module.FS.readFile("/kryon-apps/jungle/settings/language.txt",{encoding:"utf8"})')!=="es")throw Error('Language did not survive reload');
 if(diagnostics.length)throw Error(JSON.stringify(diagnostics));
 console.log('local browser test: four new books, Space pause, letter-only examples and autoplay, number autoplay, category navigation, touch controls, stencils and accented saves passed at '+url);
}finally{if(socket)socket.close();browser.kill('SIGTERM');await new Promise(r=>{if(browser.exitCode!==null||browser.signalCode!==null)r();else browser.once('exit',r)});await new Promise(r=>server.close(r));await rm(profile,{recursive:true,force:true,maxRetries:20,retryDelay:100})}

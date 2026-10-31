// Per-activity benchmarks in one private Chromium. Never attach to owner windows.
import {spawn,spawnSync} from 'node:child_process';
import {readFile,mkdtemp,rm,writeFile,mkdir} from 'node:fs/promises';
import {createServer} from 'node:http';
import {resolve,join,extname} from 'node:path';
import {cpus,platform,release,totalmem,loadavg} from 'node:os';
import {setTimeout as delay} from 'node:timers/promises';
const args=new Map();for(let i=2;i<process.argv.length;i++)if(process.argv[i].startsWith('--'))args.set(process.argv[i],process.argv[++i]);
const root=resolve(args.get('--root')||'build/web'),backend=args.get('--backend')||'canvas',seconds=Number(args.get('--seconds')||3);
const page=backend==='dom'?'dom.html':'canvas.html',output=resolve(args.get('--output')||'backup/browser-benchmarks');
const captures=args.get('--captures')==='true';
const build=JSON.parse(await readFile(join(root,'version.json'),'utf8'));
await mkdir(output,{recursive:true});
await mkdir('work/w',{recursive:true});await mkdir('work/b',{recursive:true});
const profile=await mkdtemp(resolve('work/w/p-'));
const mime={'.html':'text/html','.js':'text/javascript','.wasm':'application/wasm','.json':'application/json','.png':'image/png','.jpg':'image/jpeg','.wav':'audio/wav'};
let responseBytes=0,requests=0;
const server=createServer(async(req,res)=>{try{const f=resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));if(!f.startsWith(root+'/'))throw Error('path');const data=await readFile(f);responseBytes+=data.length;requests++;res.writeHead(200,{'Content-Type':mime[extname(f)]||'application/octet-stream','Cache-Control':'no-store'});res.end(data)}catch{res.writeHead(404);res.end()}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const env={...process.env,YUE_DESKTOP_RECOVERY:'0',TMPDIR:resolve('work/b')};
for(const k of ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','GDK_DISPLAY','DBUS_SESSION_BUS_ADDRESS','SESSION_MANAGER'])delete env[k];
const browserPath=process.env.CHROMIUM||'chromium';
const flags=['--headless','--mute-audio','--no-sandbox','--disable-gpu','--disable-webgl','--disable-dev-shm-usage','--no-first-run','--no-default-browser-check','--enable-precise-memory-info','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'];
const browser=spawn(browserPath,flags,{env,stdio:['ignore','ignore','pipe']});
let stderr='',pageRpc,browserRpc;const diagnostics=[];browser.stderr.on('data',d=>stderr=(stderr+d).slice(-3000));
async function rpc(url,onEvent=()=>{}){
 const socket=new WebSocket(url);await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j});let n=0;const pending=new Map();
 socket.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&pending.has(m.id)){const {resolve,reject,timer}=pending.get(m.id);pending.delete(m.id);clearTimeout(timer);m.error?reject(Error(JSON.stringify(m.error))):resolve(m.result)}else onEvent(m)};
 return {socket,call(method,params={}){return new Promise((resolve,reject)=>{const id=++n,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method))},30000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}))})}};
}
try{
 let port;for(let i=0;i<300;i++){try{port=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break}catch{}if(browser.exitCode!==null)throw Error(stderr);await delay(100)}
 if(!port)throw Error('Chromium startup timeout '+stderr);
 const version=await(await fetch(`http://127.0.0.1:${port}/json/version`)).json();
 browserRpc=await rpc(version.webSocketDebuggerUrl);
 const pages=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
 pageRpc=await rpc(pages.find(p=>p.type==='page').webSocketDebuggerUrl,m=>{if(m.method==='Runtime.exceptionThrown')diagnostics.push(m.params);if(m.method==='Runtime.consoleAPICalled'&&m.params.type==='error')diagnostics.push(m.params.args.map(v=>v.value||v.description))});
 const command=pageRpc.call;
 async function evaluate(expression){const r=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value}
 async function waitFor(expr,label){const end=Date.now()+Number(args.get('--timeout-ms')||45000);while(Date.now()<end){if(diagnostics.length)throw Error(JSON.stringify(diagnostics));if(await evaluate(expr))return;await delay(80)}throw Error(label+' '+await evaluate('JSON.stringify({text:document.body?.innerText?.slice(0,500),opened:window.bench?.opened?.slice(-12),location:location.href})'))}
 async function key(k){await evaluate(backend==='dom'?'document.activeElement?.blur()':'Module.canvas.focus()');const code=k==='Home'?36:k==='Enter'?13:k==='Escape'?27:k===' '?32:k.startsWith('Arrow')?({ArrowLeft:37,ArrowUp:38,ArrowRight:39,ArrowDown:40}[k]):k.toUpperCase().charCodeAt(0);await command('Input.dispatchKeyEvent',{type:'keyDown',key:k,code:k===' '?'Space':/^[0-9]$/.test(k)?'Digit'+k:k,windowsVirtualKeyCode:code});await delay(100);await command('Input.dispatchKeyEvent',{type:'keyUp',key:k,code:k===' '?'Space':/^[0-9]$/.test(k)?'Digit'+k:k,windowsVirtualKeyCode:code});await delay(100)}
 let touch=false;
 async function rendered(){await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>requestAnimationFrame(resolve))))')}
 async function click(x,y){
  if(touch){await command('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});await delay(70);await command('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]})}
  else{await command('Input.dispatchMouseEvent',{type:'mouseMoved',x,y});await command('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});await delay(70);await command('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',clickCount:1})}
  await rendered();
 }
 async function drag(x,y,tx,ty){
  if(touch){await command('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});for(let n=1;n<=6;n++){await command('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x+(tx-x)*n/6,y:y+(ty-y)*n/6}]});await delay(12)}await command('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});return}
  await command('Input.dispatchMouseEvent',{type:'mouseMoved',x,y});await command('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});for(let n=1;n<=6;n++){await command('Input.dispatchMouseEvent',{type:'mouseMoved',x:x+(tx-x)*n/6,y:y+(ty-y)*n/6,button:'left',buttons:1});await delay(12)}await command('Input.dispatchMouseEvent',{type:'mouseReleased',x:tx,y:ty,button:'left',clickCount:1})
 }
 await command('Runtime.enable');await command('Page.enable');await command('Network.enable');await command('Network.setCacheDisabled',{cacheDisabled:true});await command('Performance.enable');
 await command('Page.addScriptToEvaluateOnNewDocument',{source:`window.bench={frames:[],long:[],mutations:0};
 new PerformanceObserver(l=>bench.long.push(...l.getEntries().map(e=>e.duration))).observe({entryTypes:['longtask']});requestAnimationFrame(function frame(t){bench.frames.push(t);requestAnimationFrame(frame)});new MutationObserver(m=>bench.mutations+=m.filter(c=>!c.target.closest?.('#performance-panel')).length).observe(document,{subtree:true,childList:true,attributes:true});`});
 const cpuSeen=new Map();
 async function processSample(){
  const {processInfo}=await browserRpc.call('SystemInfo.getProcessInfo');let rss=0,pss=0,pssAvailable=true;
  for(const p of processInfo){if(p.id<=0)continue;cpuSeen.set(p.id,p.cpuTime);try{const s=await readFile(`/proc/${p.id}/status`,'utf8');rss+=Number(s.match(/^VmRSS:\s+(\d+)/m)?.[1]||0)/1024;try{const roll=await readFile(`/proc/${p.id}/smaps_rollup`,'utf8');pss+=Number(roll.match(/^Pss:\s+(\d+)/m)?.[1]||0)/1024}catch{pssAvailable=false}}catch{}}
  return {cpu:[...cpuSeen.values()].reduce((a,b)=>a+b,0),rss,pss:pssAvailable?pss:null};
 }
 async function metrics(){return Object.fromEntries((await command('Performance.getMetrics')).metrics.map(m=>[m.name,m.value]))}
 // A staged manifest also describes uncommitted builds; never read mutable source.
 let catalogGames;
 try{const catalog=JSON.parse(await readFile(join(root,'benchmark-catalog.json'),'utf8'));catalogGames=catalog.games;if(!Array.isArray(catalogGames)||!catalogGames.length||catalogGames.some(g=>typeof g.title!=='string'||!Number.isInteger(g.age)))throw Error('Invalid benchmark catalog manifest')}
 catch(error){if(error.code!=='ENOENT')throw error;const catalog=spawnSync('git',['show',build.revision+':games/catalog.txt'],{encoding:'utf8'});if(catalog.status!==0)throw Error('Cannot read catalog for tested build '+catalog.stderr);catalogGames=catalog.stdout.trim().split('\n').map(l=>l.split('|')).map(r=>({title:r[1],age:Number(r[4])}))}
 const menu=catalogGames.filter(g=>g.title!=='123 Book').sort((a,b)=>a.age-b.age);
 const entry=title=>{const index=menu.findIndex(g=>g.title===title);if(index<0)throw Error('Missing benchmark catalog entry '+title);return index};
 const allCases=[['menu',null],['picture-book',entry('Picture Book')],['abc',entry('ABC Book')],['numbers',entry('ABC Book')],['jigsaw',entry('Jigsaw Puzzles')],['piano',entry('Little Piano')],['counting',entry('Animal Counting')],['coloring',entry('Coloring Book')]];
 const cases=args.has('--activity')?allCases.filter(c=>c[0]===args.get('--activity')):allCases;
 const allViewports=[{name:'desktop',width:960,height:600},{name:'phone',width:390,height:844}];
 const viewports=args.has('--viewport')?allViewports.filter(v=>v.name===args.get('--viewport')):allViewports;
 const results=[];
 for(const viewport of viewports)for(const [activity,entry] of cases){
  touch=viewport.name==='phone';await command('Emulation.setTouchEmulationEnabled',{enabled:touch,maxTouchPoints:1});
  await command('Emulation.setDeviceMetricsOverride',{width:viewport.width,height:viewport.height,deviceScaleFactor:1,mobile:viewport.name==='phone'});
  const origin=`http://127.0.0.1:${server.address().port}`;
  await command('Page.navigate',{url:'about:blank'});
  await waitFor('location.href==="about:blank"','Previous benchmark page did not close');
  await command('Storage.clearDataForOrigin',{origin,storageTypes:'all'});
  responseBytes=0;requests=0;const navigation=performance.now();
  await command('Page.navigate',{url:origin+'/'+page});
  await waitFor('typeof Module!=="undefined"&&Module.FS&&document.getElementById("loading").style.display==="none"','Menu startup timeout');
  await evaluate('bench.opened=[];bench.audio=[];const open=Module.FS.open;Module.FS.open=function(path,...args){bench.opened.push(String(path));if(bench.opened.length>200)bench.opened.shift();return open.call(this,path,...args)};const audio=Module.jungleAudio;Module.jungleAudio=function(path,...args){bench.audio.push(path);return audio.call(this,path,...args)}');
 await waitFor(backend==='dom'?'document.querySelectorAll("[data-kryon-paint=span]").length>5':'bench.frames.length>=5','First rendered frame');
  const startupMs=performance.now()-navigation,startupBytes=responseBytes;await delay(250);
  const expectedTitle={ 'picture-book':'Picture Book',abc:'ABC Book',numbers:'123 Book',jigsaw:'Jigsaw Puzzles',piano:'Little Piano',counting:'Animal Counting',coloring:'Coloring Book'}[activity];
 const visibleTitle=title=>`[...document.querySelectorAll('[data-kryon-paint=span]')].some(e=>e.textContent.trim()===${JSON.stringify(title)}&&e.getBoundingClientRect().top<56)`;
  if(entry!==null){await key('Home');await delay(250);for(let n=0;n<entry;n++){await key('ArrowDown');await delay(250)}
   if(captures)await writeFile(join(output,`${backend}-${viewport.name}-before-${activity}.png`),Buffer.from((await command('Page.captureScreenshot',{format:'png'})).data,'base64'));
   await key('Enter');await delay(500)}
  if(activity==='picture-book'){await key('1');await waitFor('Module.FS.analyzePath("/assets/jungle-book/pages/tiger.jpg").exists','Book image missing');await key(' ')}
  if(activity==='abc'){await key('1');await delay(250);await key(' ')}
  if(activity==='numbers'){await key('2');await delay(250);await key(' ')}
  if(activity==='jigsaw'){await key('Enter');await waitFor('Module.FS.analyzePath("/kryon-apps/jungle/jungle.jigsaw/puzzle.txt").exists','Puzzle did not start')}
  if(activity==='piano'){await key('1');await waitFor('bench.audio.some(p=>p.startsWith("assets/piano/sounds/"))','Piano did not play')}
  if(activity==='coloring'){const scale=Math.min(viewport.width/320,(viewport.height-56)/200),offset=(viewport.height-56-200*scale)/2;
   if(captures)await writeFile(join(output,`${backend}-${viewport.name}-coloring-choice.png`),Buffer.from((await command('Page.captureScreenshot',{format:'png'})).data,'base64'));
   await click((viewport.width-320*scale)/2+52*scale,56+offset+58*scale);await waitFor('Module.FS.analyzePath("/kryon-apps/jungle/jungle.paint/working.txt").exists','Scene did not open');await key('Escape');await delay(250)}
  if(expectedTitle&&backend==='dom')await waitFor(visibleTitle(expectedTitle),'Wrong benchmark activity '+activity);
  // Canvas draws atlas glyphs, so verify real game reads rather than fillText.
  const documentGame={'picture-book':'book',abc:'abc',numbers:'numbers',counting:'animals',coloring:'paint',jigsaw:'jigsaw'}[activity];
  if(documentGame)await waitFor(`bench.opened.some(p=>p.includes('/jungle.${documentGame}/'))`,'Game document was not opened '+activity);
  const gameReadyMs=performance.now()-navigation;
  if(captures)await writeFile(join(output,`${backend}-${viewport.name}-${activity}.png`),Buffer.from((await command('Page.captureScreenshot',{format:'png'})).data,'base64'));
  if(backend==='dom'){
   const audit=await evaluate(`({text:document.querySelectorAll('[data-kryon-paint=span]').length,buttons:document.querySelectorAll('#kryon-dom-root button').length,images:document.querySelectorAll('#kryon-dom-paint img').length,tiles:[...document.querySelectorAll('#kryon-dom-paint canvas')].map(c=>({w:c.width,h:c.height})),canvasHidden:getComputedStyle(Module.canvas).visibility==='hidden',invalid:[...document.querySelectorAll('#kryon-dom-root button')].filter(b=>!b.style.width||!b.style.height).length})`);
   if(!audit.canvasHidden||!audit.text||audit.invalid)throw Error('Native DOM audit failed '+activity+' '+JSON.stringify(audit));
   await writeFile(join(output,`${backend}-${viewport.name}-${activity}-dom.json`),JSON.stringify(audit,null,2));
  }
  const w=viewport.width,h=viewport.height;const scale=Math.min(w/320,(h-56)/200),offset=(h-56-200*scale)/2,offsetX=(w-320*scale)/2;
  function paintGeometry(){
   const body=h-56,pad=Math.max(6,Math.min(20,Math.floor(Math.min(w,body)/40))),gap=Math.max(4,Math.min(10,Math.floor(Math.min(w,body)/80)));
   if(body>w){const toolW=Math.floor((w-pad*2-gap*2)/3),toolH=Math.max(44,Math.min(110,Math.floor(toolW*3/4)));let cw=w-pad*2,ch=Math.floor(cw*3/4);const room=body-pad*3-gap*2-toolH*3;if(ch>room){ch=room;cw=Math.floor(ch*4/3)}const cx=Math.floor((w-cw)/2),cy=pad,below=cy+ch+pad,top=below+Math.floor((body-pad-below-toolH*3-gap*2)/2);return {x:cx,y:56+cy,w:cw,h:ch,colorX:pad+toolW+gap+toolW/2,colorY:56+top+toolH/2}}
   const columns=body<440?2:1,rows=columns===2?5:9,toolH=Math.floor((body-pad*2-gap*(rows-1))/rows),toolW=Math.max(64,Math.min(Math.floor(w/(columns===2?8:5)),Math.floor(toolH*5/2))),railW=toolW*columns+gap*(columns-1),roomW=w-pad*3-railW,roomH=body-pad*2;let cw=roomW,ch=Math.floor(cw*3/4);if(ch>roomH){ch=roomH;cw=Math.floor(ch*4/3)}const left=Math.floor((w-railW-pad-cw)/2),cy=pad+Math.floor((roomH-ch)/2),top=cy+Math.floor((ch-toolH*rows-gap*(rows-1))/2);return {x:left+railW+pad,y:56+cy,w:cw,h:ch,colorX:left+(1%columns)*(toolW+gap)+toolW/2,colorY:56+top+Math.floor(1/columns)*(toolH+gap)+toolH/2};
  }
  async function action(n){
   if(activity==='menu')return key(n%2?'ArrowUp':'ArrowDown');
   if(activity==='picture-book'||activity==='abc'||activity==='numbers')return key(n%6===5?'ArrowLeft':'ArrowRight');
   if(activity==='piano')return key('1234556666566665'[n%16]);
   if(activity==='counting'){await key(String(n%4+1));return key('Enter')}
   if(activity==='coloring'){
    const a=paintGeometry();await click(a.colorX,a.colorY);await delay(50);
    const color=(n+2)%42;await click(offsetX+(20+(color%7)*41+18)*scale,56+offset+(31+Math.floor(color/7)*23+9)*scale);await delay(50);
    // Recolor the same broad interior region in both backends.
    return click(a.x+a.w*.5,a.y+a.h*.7);
   }
   if(activity==='jigsaw'){
    const values=await evaluate('Module.FS.readFile("/kryon-apps/jungle/jungle.jigsaw/puzzle.txt",{encoding:"utf8"}).trim().split(/\\s+/).map(Number)');
    const owners=values.slice(10,18).filter((_,i)=>i%2===0),order=values.slice(10,18).filter((_,i)=>i%2===1),piece=order.findLast(p=>owners[p]===0);
    if(piece===undefined)throw Error('No loose jigsaw piece for the workload');
    const s=Math.min(w/(w>h-56?780:400),(h-56)/(w>h-56?520:740),1.5),vw=Math.trunc(w/s),vh=Math.trunc((h-56)/s);
    const x=(16+(vw-32)*values[18+piece*2]/10000)*s,y=56+(72+(vh-144)*values[19+piece*2]/10000)*s;
    return drag(x,y,x+(n%2?-18:18),y+(n%2?-14:14));
   }
  }
  for(const phase of ['idle','active']){
   const paintModified=activity==='coloring'?await evaluate('Module.FS.analyzePath("/kryon-apps/jungle/jungle.paint/working.txt").exists?Number(Module.FS.stat("/kryon-apps/jungle/jungle.paint/working.txt").mtime):-1'):null;
   if(activity==='coloring')await evaluate('bench.paintPixels=()=>Module.FS.readFile("/kryon-apps/jungle/jungle.paint/working.txt",{encoding:"utf8"}).split("\\n").slice(10).join("\\n");bench.paintBefore=bench.paintPixels()');
   await evaluate('bench.frames=[];bench.long=[];bench.mutations=0');
   const first=await processSample(),before=await metrics(),start=performance.now(),samples=[];let n=0;
   const targetActions=Math.max(1,Math.floor(seconds)),cadence=seconds*1000/targetActions;
   while(performance.now()-start<seconds*1000){if(phase==='active'&&n<targetActions&&performance.now()-start>=n*cadence){await action(n++);if(performance.now()-start>n*cadence)throw Error('Workload exceeded fixed action cadence '+activity)}samples.push(await processSample());await delay(Math.min(100,Math.max(1,seconds*1000-(performance.now()-start))))}
   if(phase==='active'&&n!==targetActions)throw Error('Incomplete active workload '+activity);
   const elapsed=(performance.now()-start)/1000,last=await processSample(),after=await metrics();
   const data=await evaluate(`(()=>{const f=bench.frames,g=f.slice(1).map((t,i)=>t-f[i]).sort((a,b)=>a-b),p=q=>g.length?g[Math.floor((g.length-1)*q)]:null;return {raf_p50_ms:p(.5),raf_p95_ms:p(.95),raf_p99_ms:p(.99),raf_intervals:g.length,slow_raf_percent:g.length?g.filter(v=>v>25).length/g.length*100:null,long_tasks:bench.long.length,long_task_ms:bench.long.reduce((a,b)=>a+b,0),dom_mutations:bench.mutations,dom_nodes:document.getElementsByTagName('*').length,native_text_nodes:document.querySelectorAll('[data-kryon-paint=span]').length,native_buttons:document.querySelectorAll('#kryon-dom-root button').length,native_images:document.querySelectorAll('#kryon-dom-paint img').length,raster_tiles:document.querySelectorAll('#kryon-dom-paint canvas').length,js_heap_mib:(performance.memory?.usedJSHeapSize||0)/1048576,wasm_heap_mib:Module.HEAPU8.buffer.byteLength/1048576}})()`);
   const row={backend,viewport:viewport.name,width:w,height:h,activity,phase,sample_seconds:elapsed,actions:n,startup_ms:startupMs,activity_ready_ms:gameReadyMs,startup_bytes_mib:startupBytes/1048576,activity_bytes_mib:responseBytes/1048576,requests,cpu_percent:(last.cpu-first.cpu)/elapsed*100,renderer_task_cpu_percent:(after.TaskDuration-before.TaskDuration)/elapsed*100,script_ms:(after.ScriptDuration-before.ScriptDuration)*1000,layout_ms:(after.LayoutDuration-before.LayoutDuration)*1000,style_ms:(after.RecalcStyleDuration-before.RecalcStyleDuration)*1000,mean_rss_mib:samples.reduce((a,s)=>a+s.rss,0)/samples.length,peak_rss_mib:Math.max(last.rss,...samples.map(s=>s.rss)),mean_pss_mib:samples.every(s=>s.pss!==null)?samples.reduce((a,s)=>a+s.pss,0)/samples.length:null,...data};results.push(row);
   if(captures&&phase==='active')await writeFile(join(output,`${backend}-${viewport.name}-${activity}-active.png`),Buffer.from((await command('Page.captureScreenshot',{format:'png'})).data,'base64'));
   if(activity==='coloring'&&phase==='active'&&await evaluate('Module.FS.analyzePath("/kryon-apps/jungle/jungle.paint/working.txt").exists?Number(Module.FS.stat("/kryon-apps/jungle/jungle.paint/working.txt").mtime):-1')===paintModified)throw Error('Coloring workload did not edit its picture');
   if(activity==='coloring'&&phase==='active'){row.picture_pixels_changed=await evaluate('bench.paintBefore!==bench.paintPixels()');if(!row.picture_pixels_changed)throw Error('Coloring changed no picture pixels');row.input=touch?'CDP touch':'CDP mouse';row.picture_sha256=await evaluate('(async()=>Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",Module.FS.readFile("/kryon-apps/jungle/jungle.paint/working.txt")))).map(b=>b.toString(16).padStart(2,"0")).join(""))()')}
   if(diagnostics.length)throw Error(JSON.stringify(diagnostics));
   console.log(`${backend} ${viewport.name} ${activity} ${phase}: CPU ${row.cpu_percent.toFixed(1)}%, RSS ${row.mean_rss_mib.toFixed(1)} MiB, rAF p95 ${row.raf_p95_ms?.toFixed(1)} ms`);
  }
 }
 const runtime={js_bytes:(await readFile(join(root,backend==='dom'?'jungle-dom.js':'jungle.js'))).length,wasm_bytes:(await readFile(join(root,backend==='dom'?'jungle-dom.wasm':'jungle.wasm'))).length};
 const payload={backend,build,runtime,browser:version.Browser,os:platform()+' '+release(),cpu_model:cpus()[0]?.model,logical_cpus:cpus().length,host_ram_gib:totalmem()/1073741824,host_load:loadavg(),flags:flags.filter(f=>!f.startsWith('--user-data-dir')),method:'Sequential private headless Chromium, software graphics, fresh profile per backend run, cache-disabled page navigations, desktop mouse and emulated phone touch; One fixed action cycle per second in both backends (three cycles per active phase at the default duration); Coloring Book must change saved pixels and produce identical saved pictures in paired runs. Aggregates are medians across runs. CPU100%=one core; RSS sums processes and includes shared pages; PSS apportions shared pages; rAF is callback cadence, not application render FPS.',results};
 await writeFile(join(output,`performance-${backend}.json`),JSON.stringify(payload,null,2)+'\n');
}finally{
 try{await browserRpc?.call('Browser.close')}catch{}
 pageRpc?.socket.close();browserRpc?.socket.close();
 if(browser.exitCode===null)browser.kill('SIGTERM');
 await new Promise(r=>{if(browser.exitCode!==null)r();else browser.once('exit',r)});
 await new Promise(r=>server.close(r));await rm(profile,{recursive:true,force:true,maxRetries:20,retryDelay:150});
}

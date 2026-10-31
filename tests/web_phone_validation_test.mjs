// USB Moto only. Owns one new Chrome tab and its own ADB mappings, never a profile.
import {spawnSync} from 'node:child_process';
import {createReadStream} from 'node:fs';
import {readFile,mkdir,writeFile,stat} from 'node:fs/promises';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import {resolve,join,extname} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';

const args=new Map();for(let i=2;i<process.argv.length;i+=2)args.set(process.argv[i],process.argv[i+1]);
const serial=args.get('--serial');
if(!serial||serial.includes(':'))throw Error('Select an explicit USB Moto serial with --serial; wireless targets are not allowed');
const root=resolve(args.get('--root')||'build/web'),output=resolve(args.get('--output')||'backup/paint-refresh/phone-validation');
const connectionOnly=args.get('--connection-only')==='true';
const runs=Number(args.get('--runs')||3),seconds=Number(args.get('--seconds')||6),cycles=3;
if(!Number.isInteger(runs)||runs<1||seconds<6)throw Error('Use at least one run and six seconds per phase');
const working='/kryon-apps/jungle/jungle.paint/working.txt';
function adb(...command){const r=spawnSync('adb',['-s',serial,...command],{encoding:'utf8',timeout:20000});if(r.status!==0)throw Error('ADB '+command[0]+': '+(r.stderr||r.stdout||r.error));return r.stdout.trim()}
const deviceList=spawnSync('adb',['devices','-l'],{encoding:'utf8',timeout:10000});
if(!deviceList.stdout?.split('\n').some(l=>l.startsWith(serial+' ')&&l.includes('device usb:')))throw Error('The designated Moto is not connected over USB');
if(adb('shell','getprop','ro.product.manufacturer').toLowerCase()!=='motorola')throw Error('The explicit USB test device must be the development Moto');
await mkdir(output,{recursive:true});
const catalog=connectionOnly?{games:[]}:JSON.parse(await readFile(join(root,'benchmark-catalog.json'),'utf8'));
const menu=catalog.games.filter(g=>g.title!=='123 Book').sort((a,b)=>a.age-b.age),entry=menu.findIndex(g=>g.title==='Coloring Book');
if(entry<0&&!connectionOnly)throw Error('Frozen build catalog is missing Coloring Book');
const build=JSON.parse(await readFile(join(root,'version.json'),'utf8'));
async function fingerprints(){const result={};for(const name of ['version.json','benchmark-catalog.json','canvas.html','dom.html','jungle.js','jungle-dom.js','jungle.wasm','jungle-dom.wasm']){const hash=createHash('sha256');for await(const chunk of createReadStream(join(root,name)))hash.update(chunk);result[name]=hash.digest('hex')}return result}
const artifacts=connectionOnly?{}:await fingerprints();
const mime={'.html':'text/html','.js':'text/javascript','.wasm':'application/wasm','.json':'application/json','.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp','.wav':'audio/wav','.zip':'application/zip'};
const server=createServer(async(req,res)=>{try{
 const url=new URL(req.url,'http://localhost');
 if(url.pathname==='/phone-benchmark-ready'){res.writeHead(200,{'Content-Type':'text/html'});res.end('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>Jungle USB web validation</title>Jungle test connection');return}
 const file=resolve(root,'.'+decodeURIComponent(url.pathname));if(!file.startsWith(root+'/'))throw Error('path');await stat(file);
 res.writeHead(200,{'Content-Type':mime[extname(file)]||'application/octet-stream','Cache-Control':'no-store'});createReadStream(file).on('error',()=>res.destroy()).pipe(res);
}catch{res.writeHead(404);res.end()}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const port=server.address().port,origin='http://127.0.0.1:'+port,readyUrl=origin+'/phone-benchmark-ready';
let reverse=false,forwardPort,pageRpc,targetId,browserVersion,endpoint;
async function rpc(url){const socket=new WebSocket(url);await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j});let sequence=0;const pending=new Map(),errors=[];
 socket.onmessage=e=>{const m=JSON.parse(e.data);if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails?.exception?.description||m.params.exceptionDetails?.text);if(pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result)}};
 return {socket,errors,call(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method))},30000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}))})}};
}
try{
 if(adb('reverse','--list').split('\n').some(l=>l.split(/\s+/).includes('tcp:'+port)))throw Error('Refusing to replace an existing USB reverse mapping');
 adb('reverse','tcp:'+port,'tcp:'+port);reverse=true;
 // A unique localhost origin opens a new test tab, preserving existing tabs.
 adb('shell','am','start','-W','-a','android.intent.action.VIEW','-d',readyUrl,'-p','com.android.chrome');
 forwardPort=adb('forward','tcp:0','localabstract:chrome_devtools_remote');
 endpoint='http://127.0.0.1:'+forwardPort;
 let connectionError;for(let n=0;n<150;n++){try{browserVersion=await(await fetch(endpoint+'/json/version',{signal:AbortSignal.timeout(2000)})).json();break}catch(error){connectionError=error;await delay(200)}}
 if(!browserVersion)throw Error('Moto Chrome debugging socket did not become ready: '+connectionError?.message);
 let target;for(let n=0;n<100;n++){const tabs=await(await fetch(endpoint+'/json/list')).json();target=tabs.find(t=>t.type==='page'&&t.url===readyUrl);if(target)break;await delay(200)}
 if(!target)throw Error('Chrome did not expose the new test tab; a first-run or unlock screen may need attention');
 targetId=target.id;const debuggerUrl=new URL(target.webSocketDebuggerUrl);debuggerUrl.host='127.0.0.1:'+forwardPort;pageRpc=await rpc(debuggerUrl.href);
 const command=pageRpc.call;
 async function evaluate(expression){const r=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value}
 async function until(expression,label){const end=Date.now()+Number(args.get('--timeout-ms')||90000);while(Date.now()<end){if(pageRpc.errors.length)throw Error(pageRpc.errors.join('\n'));if(await evaluate(expression))return;await delay(120)}if(args.get('--captures')==='true')await writeFile(join(output,'phone-timeout.png'),Buffer.from((await command('Page.captureScreenshot',{format:'png'})).data,'base64'));throw Error(label+' '+await evaluate('JSON.stringify({text:document.body?.innerText?.slice(0,700),opened:window.bench?.opened?.slice(-12)})'))}
 async function rendered(){await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>requestAnimationFrame(resolve))))')}
 async function key(key){await evaluate('document.documentElement.dataset.backend==="canvas"?Module.canvas.focus():document.activeElement?.blur()');const code=key==='Home'?36:key==='ArrowDown'?40:key==='Enter'?13:key==='Escape'?27:0;await command('Input.dispatchKeyEvent',{type:'keyDown',key,code:key,windowsVirtualKeyCode:code});await delay(160);await command('Input.dispatchKeyEvent',{type:'keyUp',key,code:key,windowsVirtualKeyCode:code});await rendered();await delay(350)}
 async function tap(x,y){await command('Input.synthesizeTapGesture',{x,y,duration:100,tapCount:1,gestureSourceType:'touch'});await rendered()}
 async function metrics(){return Object.fromEntries((await command('Performance.getMetrics')).metrics.map(m=>[m.name,m.value]))}
 async function picture(){return evaluate(`(async()=>{const bytes=Module.FS.readFile(${JSON.stringify(working)}),text=new TextDecoder().decode(bytes),pixels=text.split('\\n').slice(10).join('\\n');const hash=async b=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',b))).map(v=>v.toString(16).padStart(2,'0')).join('');return {mtime:Number(Module.FS.stat(${JSON.stringify(working)}).mtime),sha256:await hash(bytes),pixels:await hash(new TextEncoder().encode(pixels))}})()`)}
 if(connectionOnly){
  await evaluate('window.jungleTestTouches=[];for(const type of ["touchstart","touchend"])window.addEventListener(type,()=>jungleTestTouches.push(type))');
  await tap(80,80);const touches=await evaluate('jungleTestTouches');if(touches.join(',')!=='touchstart,touchend')throw Error('Actual Moto CDP touch dispatch did not reach the test tab');
  const device={serial,model:adb('shell','getprop','ro.product.model'),browser:browserVersion.Browser,viewport:await evaluate('({width:innerWidth,height:innerHeight,dpr:devicePixelRatio})'),touch_events:touches};
  await writeFile(join(output,'phone-connection.json'),JSON.stringify(device,null,2)+'\n');console.log('USB Moto Chrome connection validated: '+device.browser+' '+JSON.stringify(device.viewport));
 }else{
 await command('Runtime.enable');await command('Page.enable');await command('Network.enable');await command('Network.setCacheDisabled',{cacheDisabled:true});await command('Performance.enable');
 await command('Page.addScriptToEvaluateOnNewDocument',{source:'window.bench={frames:[],opened:[]};requestAnimationFrame(function frame(t){bench.frames.push(t);requestAnimationFrame(frame)})'});
 const results=[];
 for(let run=1;run<=runs;run++)for(const backend of(args.has('--backend')?[args.get('--backend')]:(run%2?['canvas','dom']:['dom','canvas']))){
  await command('Page.navigate',{url:'about:blank'});await until('location.href==="about:blank"','Previous test page did not close');
  await command('Storage.clearDataForOrigin',{origin,storageTypes:'all'});
  const start=performance.now();await command('Page.navigate',{url:origin+'/'+backend+'.html'});
  await until('typeof Module!=="undefined"&&Module.FS&&document.getElementById("loading").style.display==="none"','Phone startup timeout');await rendered();
  await until(backend==='dom'?'document.querySelectorAll("[data-kryon-paint=span]").length>5':'bench.frames.length>10','First phone app frame did not render');
  await delay(1000); // Let the real phone finish its first menu/image layout.
  await evaluate('const open=Module.FS.open;Module.FS.open=function(path,...args){bench.opened.push(String(path));if(bench.opened.length>200)bench.opened.shift();return open.call(this,path,...args)}');
  const viewport=await evaluate('({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,canvasWidth:Module.canvas.width,canvasHeight:Module.canvas.height,clientWidth:Module.canvas.clientWidth,clientHeight:Module.canvas.clientHeight})');
  // PageDimension uses CSS client sizes; only the raster backing is DPR-scaled.
  if(viewport.width!==viewport.clientWidth||viewport.height!==viewport.clientHeight||Math.abs(viewport.canvasWidth/viewport.clientWidth-viewport.dpr)>.02||Math.abs(viewport.canvasHeight/viewport.clientHeight-viewport.dpr)>.02)throw Error('Unexpected phone CSS/backing scale: '+JSON.stringify(viewport));
  await key('Home');for(let n=0;n<entry;n++)await key('ArrowDown');await key('Enter');
  await until('bench.opened.some(p=>p.includes("/jungle.paint/"))','Coloring Book did not open');
  const w=viewport.width,h=viewport.height,body=h-56,scale=Math.min(w/320,body/200),dx=Math.trunc((w-320*scale)/2),dy=56+Math.trunc((body-200*scale)/2);
  const dialog=(x,y)=>tap(dx+x*scale,dy+y*scale);
  const scene=firstScene(w,h);await tap(scene.x,scene.y);await until(`Module.FS.analyzePath(${JSON.stringify(working)}).exists`,'Scene did not open');await key('Escape');await rendered();
  if(backend==='dom')await until('[...document.querySelectorAll("[data-kryon-paint=span]")].some(e=>e.textContent.trim()==="Coloring Book"&&e.getBoundingClientRect().top<56)','Wrong phone activity');
  const geometry=paintGeometry(w,h),readyMs=performance.now()-start;
  if(args.get('--trace')==='true')await evaluate('bench.events=[];for(const type of ["pointerdown","pointerup","touchstart","touchend","click"])window.addEventListener(type,e=>{const b=e.target.closest?.("button");bench.events.push({type,target:e.target.tagName,label:b?.getAttribute("aria-label"),disabled:b?.disabled,x:e.clientX??e.touches?.[0]?.clientX,y:e.clientY??e.touches?.[0]?.clientY,time:performance.now()});if(bench.events.length>100)bench.events.shift()},true)');
  if(args.get('--trace')==='true')await writeFile(join(output,'phone-geometry.json'),JSON.stringify({viewport,geometry,controls:await evaluate('[...document.querySelectorAll("#kryon-dom-root button")].map(b=>({label:b.getAttribute("aria-label"),text:b.textContent,rect:{x:b.getBoundingClientRect().x,y:b.getBoundingClientRect().y,w:b.getBoundingClientRect().width,h:b.getBoundingClientRect().height}}))')},null,2)+'\n');
  for(const phase of ['idle','active']){
   const beforePicture=await picture();await evaluate('bench.frames=[]');const before=await metrics(),start=performance.now(),latencies=[];
   if(phase==='active')for(let n=0;n<cycles;n++){
    const due=start+n*seconds*1000/cycles;await delay(Math.max(0,due-performance.now()));const began=performance.now(),old=await picture();
    const trace=async label=>{if(args.get('--trace')==='true'){await delay(500);await writeFile(join(output,'phone-'+n+'-'+label+'.png'),Buffer.from((await command('Page.captureScreenshot',{format:'png'})).data,'base64'));await writeFile(join(output,'phone-events.json'),JSON.stringify(await evaluate('({events:bench.events,body:{w:innerWidth,h:innerHeight},atColor:document.elementFromPoint('+geometry.colorX+','+geometry.colorY+')?.closest("button")?.getAttribute("aria-label")})'),null,2)+'\n')}};
    await tap(geometry.colorX,geometry.colorY);await trace('color');await dialog(38+((n+2)%7)*41,40+Math.floor((n+2)/7)*23);await trace('crayon');await tap(geometry.x+geometry.w*.5,geometry.y+geometry.h*.7);await trace('fill');
    await until(`Number(Module.FS.stat(${JSON.stringify(working)}).mtime)>${old.mtime}`,'Touch cycle did not save');
    const changed=await picture();if(changed.pixels===old.pixels)throw Error('Touch cycle changed no pixels');latencies.push(performance.now()-began);
   }
   await delay(Math.max(0,seconds*1000-(performance.now()-start)));const elapsed=(performance.now()-start)/1000,after=await metrics(),saved=await picture();
   const frame=await evaluate('(()=>{const f=bench.frames,g=f.slice(1).map((t,i)=>t-f[i]).sort((a,b)=>a-b);return {raf_intervals:g.length,raf_p95_ms:g[Math.floor((g.length-1)*.95)]??null,raf_p99_ms:g[Math.floor((g.length-1)*.99)]??null,raf_max_ms:g.at(-1)??null,slow_raf_percent:g.length?g.filter(t=>t>25).length/g.length*100:null,wasm_heap_mib:Module.HEAPU8.buffer.byteLength/1048576}})()');
   const row={run,backend,activity:'coloring',phase,viewport,activity_ready_ms:readyMs,sample_seconds:elapsed,actions:latencies.length,touch_cycle_ms:latencies,renderer_task_cpu_percent:(after.TaskDuration-before.TaskDuration)/elapsed*100,renderer_task_ms:(after.TaskDuration-before.TaskDuration)*1000,js_heap_mib:after.JSHeapUsedSize/1048576,picture_pixels_changed:saved.pixels!==beforePicture.pixels,picture_sha256:saved.sha256,...frame};
   if(phase==='active'&&(!row.picture_pixels_changed||row.actions!==cycles))throw Error('Incomplete real-phone touch workload');
   results.push(row);console.log(`Moto ${run} ${backend} ${phase}: ${row.actions} real touch cycles, renderer task CPU ${row.renderer_task_cpu_percent.toFixed(1)}%, rAF p95 ${row.raf_p95_ms?.toFixed(1)} ms`);
  }
  if(JSON.stringify(artifacts)!==JSON.stringify(await fingerprints()))throw Error('Phone tested build changed');
  await writeFile(join(output,'phone-validation-partial.json'),JSON.stringify({build,results},null,2)+'\n');
 }
 if(!args.has('--backend'))for(let run=1;run<=runs;run++){const pair=results.filter(r=>r.run===run&&r.phase==='active');if(pair.length!==2||pair[0].picture_sha256!==pair[1].picture_sha256)throw Error('Canvas and DOM produced different real-phone pictures')}
 const payload={build,build_artifacts_sha256:artifacts,paired:!args.has('--backend'),input_method:'CDP Input.synthesizeTapGesture, touch source, 100ms duration',device:{serial,model:adb('shell','getprop','ro.product.model'),browser:browserVersion.Browser,user_agent:browserVersion['User-Agent']},method:'Actual USB Moto Chrome; one newly opened test tab, default hardware configuration, real CDP touch gestures, no device emulation or profile changes. Three identical recolors per active phase, alternating backend order. CPU is own renderer main-thread task time, not total browser/process CPU or PSS. Touch-cycle times include USB/CDP and settling. rAF is browser callback cadence.',results};
 await writeFile(join(output,'phone-validation.json'),JSON.stringify(payload,null,2)+'\n');console.log(`Completed ${runs} actual-phone ${args.has('--backend')?'diagnostic backend runs':'paired validations'}; ${results.length} samples`);
 }
}finally{
 const cleanupErrors=[];
 if(pageRpc){try{await pageRpc.call('Page.navigate',{url:'about:blank'});await pageRpc.call('Storage.clearDataForOrigin',{origin,storageTypes:'all'})}catch(error){cleanupErrors.push('Test-origin cleanup: '+error.message)}pageRpc.socket.close()}
 if(targetId&&endpoint){try{
  // Android closes the page socket before a page-scoped Target.closeTarget reply.
  await fetch(endpoint+'/json/close/'+encodeURIComponent(targetId),{signal:AbortSignal.timeout(5000)});
  let closed=false;for(let n=0;n<20;n++){const tabs=await(await fetch(endpoint+'/json/list',{signal:AbortSignal.timeout(5000)})).json();if(!tabs.some(t=>t.id===targetId)){closed=true;break}await delay(100)}
  if(!closed)throw Error('Owned Chrome tab is still open');
 }catch(error){cleanupErrors.push('Test-tab cleanup: '+error.message)}}
 if(forwardPort)try{adb('forward','--remove','tcp:'+forwardPort)}catch(error){cleanupErrors.push(error.message)}
 if(reverse)try{adb('reverse','--remove','tcp:'+port)}catch(error){cleanupErrors.push(error.message)}
 server.closeAllConnections();await new Promise(r=>server.close(r));
 await writeFile(join(output,'phone-cleanup.json'),JSON.stringify({target:targetId||null,closed:!!targetId&&!cleanupErrors.length,usb_mappings_removed:!cleanupErrors.length,errors:cleanupErrors},null,2)+'\n');
 if(cleanupErrors.length)throw Error(cleanupErrors.join('\n'));
}

// Mirrors the nine-tool app layout; all coordinates are CSS pixels.
function paintGeometry(w,h){
 const body=h-56,pad=Math.max(6,Math.min(20,Math.floor(Math.min(w,body)/40))),gap=Math.max(4,Math.min(10,Math.floor(Math.min(w,body)/80)));
 if(body>w){const toolW=Math.floor((w-pad*2-gap*2)/3),toolH=Math.max(44,Math.min(110,Math.floor(toolW*3/4)));let cw=w-pad*2,ch=Math.floor(cw*3/4);const room=body-pad*3-gap*2-toolH*3;if(ch>room){ch=room;cw=Math.floor(ch*4/3)}const cx=Math.floor((w-cw)/2),below=pad+ch+pad,top=below+Math.floor((body-pad-below-toolH*3-gap*2)/2);return {x:cx,y:56+pad,w:cw,h:ch,colorX:pad+toolW+gap+toolW/2,colorY:56+top+toolH/2}}
 const columns=body<440?2:1,rows=columns===2?5:9,toolH=Math.floor((body-pad*2-gap*(rows-1))/rows),toolW=Math.max(64,Math.min(Math.floor(w/(columns===2?8:5)),Math.floor(toolH*5/2))),railW=toolW*columns+gap*(columns-1),roomH=body-pad*2;let cw=w-pad*3-railW,ch=Math.floor(cw*3/4);if(ch>roomH){ch=roomH;cw=Math.floor(ch*4/3)}const left=Math.floor((w-railW-pad-cw)/2),cy=pad+Math.floor((roomH-ch)/2),top=cy+Math.floor((ch-toolH*rows-gap*(rows-1))/2);return {x:left+railW+pad,y:56+cy,w:cw,h:ch,colorX:left+(1%columns)*(toolW+gap)+toolW/2,colorY:56+top+Math.floor(1/columns)*(toolH+gap)+toolH/2};
}

function firstScene(width,total){
 const height=total-56<300?500:Math.max(300,total-56),pad=height<440?8:16,gap=height<440?6:10;
 const columns=width<600?2:3,rows=6/columns,grid=pad+30+gap+44+gap,footer=height-pad-44;
 const cardWidth=Math.floor((width-pad*2-gap*(columns-1))/columns),cardHeight=Math.max(80,Math.floor((footer-gap-grid-gap*(rows-1))/rows));
 return {x:pad+Math.floor(cardWidth/2),y:56+grid+Math.floor(cardHeight/2)};
}

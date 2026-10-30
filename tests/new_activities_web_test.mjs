// Exercise catalog activities in a private headless browser and profile.
import {spawn,spawnSync} from 'node:child_process';
import {readFile,writeFile,mkdtemp,rm,mkdir} from 'node:fs/promises';
import {createServer} from 'node:http';
import {resolve,join,extname} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';

await mkdir('work/w',{recursive:true});await mkdir('work/b',{recursive:true});
const root=resolve(process.env.JUNGLE_WEB_ROOT||'build/web');
const page=process.env.JUNGLE_WEB_PAGE||'dom.html';
const language=process.env.JUNGLE_TEST_LANG||'en';
await mkdir('backup/new-activities-web',{recursive:true});
const profile=await mkdtemp(resolve('work/w/p-'));
const mime={'.html':'text/html','.js':'text/javascript','.wasm':'application/wasm','.json':'application/json','.png':'image/png','.jpg':'image/jpeg','.wav':'audio/wav'};
const server=createServer(async(req,res)=>{
 try{
  const file=resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
  if(!file.startsWith(root+'/'))throw Error('path');
  res.writeHead(200,{'Content-Type':mime[extname(file)]||'application/octet-stream'});
  res.end(await readFile(file));
 }catch{res.writeHead(404);res.end()}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const env={...process.env,YUE_DESKTOP_RECOVERY:'0',TMPDIR:resolve('work/b')};
for(const key of ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','DBUS_SESSION_BUS_ADDRESS','SESSION_MANAGER'])delete env[key];
const browser=spawn(process.env.CHROMIUM||'chromium',['--headless','--mute-audio','--no-sandbox','--disable-gpu','--disable-webgl','--disable-dev-shm-usage','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{env,stdio:['ignore','ignore','pipe']});
let socket,stderr='',errors=[];
browser.stderr.on('data',data=>stderr=(stderr+data).slice(-3000));
try{
 let port;
 const until=Date.now()+30000;
 while(Date.now()<until){
  try{port=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break}catch{}
  if(browser.exitCode!==null)throw Error(stderr);
  await delay(100);
 }
 if(!port)throw Error('Private browser failed: '+stderr);
 const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
 socket=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject});
 let sequence=0;const pending=new Map();
 socket.onmessage=event=>{
  const message=JSON.parse(event.data);
  if(message.method==='Runtime.exceptionThrown')errors.push(message.params);
  if(pending.has(message.id)){pending.get(message.id)(message);pending.delete(message.id)}
 };
 async function command(method,params={}){
  const id=++sequence,promise=new Promise(resolve=>pending.set(id,resolve));
  socket.send(JSON.stringify({id,method,params}));
  let timer;const deadline=new Promise((_,reject)=>timer=setTimeout(()=>reject(Error('CDP timed out '+method)),15000));
  let reply;try{reply=await Promise.race([promise,deadline])}finally{clearTimeout(timer);pending.delete(id)}if(reply.error)throw Error(JSON.stringify(reply.error));return reply.result;
 }
 async function evaluate(expression){
  const result=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;
 }
 async function key(key){
  // App-level shortcuts are tested with no native control holding focus.
  if(key==='Enter'||key===' ')await evaluate('if(document.documentElement.dataset.backend==="dom")document.activeElement?.blur()');
  const code=key==='Home'?36:key==='End'?35:key==='Enter'?13:key==='Escape'?27:key===' '?32:key.startsWith('Arrow')?({ArrowLeft:37,ArrowUp:38,ArrowRight:39,ArrowDown:40}[key]):key.toUpperCase().charCodeAt(0);
  await command('Input.dispatchKeyEvent',{type:'keyDown',key,windowsVirtualKeyCode:code});
  await delay(80);
  await command('Input.dispatchKeyEvent',{type:'keyUp',key,windowsVirtualKeyCode:code});await delay(180);
 }
 async function controlKey(key){
  const code=key==='Enter'?13:32,name=key==='Enter'?'Enter':'Space',text=key==='Enter'?'\r':'';
  await command('Input.dispatchKeyEvent',{type:'keyDown',key,code:name,windowsVirtualKeyCode:code,text});await delay(80);
  await command('Input.dispatchKeyEvent',{type:'keyUp',key,code:name,windowsVirtualKeyCode:code});await delay(180);
 }
 async function click(x,y){
  await command('Input.dispatchMouseEvent',{type:'mouseMoved',x,y});await delay(100);
  await command('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});await delay(80);
  await command('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',clickCount:1});await delay(180);
 }
 async function waitFor(expression,description,timeout=30000){
  const end=Date.now()+timeout;
  while(Date.now()<end){if(errors.length)throw Error(JSON.stringify(errors));if(await evaluate(expression))return;await delay(100)}
  throw Error(description);
 }
 await command('Runtime.enable');await command('Page.enable');
 await command('Page.addScriptToEvaluateOnNewDocument',{source:`window.drumsAudio=[];window.drumsClicks=[];document.addEventListener('click',event=>{const label=event.target.getAttribute?.('aria-label');if(label)window.drumsClicks.push({label,detail:event.detail})},true);const originalPlay=HTMLMediaElement.prototype.play;HTMLMediaElement.prototype.play=function(){if(this.junglePath?.startsWith('assets/drums/sounds/'))window.drumsAudio.push(this.junglePath);return originalPlay.apply(this,arguments)}`});
 await command('Emulation.setDeviceMetricsOverride',{width:400,height:756,deviceScaleFactor:1,mobile:false});
 await command('Page.navigate',{url:'http://127.0.0.1:'+server.address().port+'/'+page});
 await waitFor('typeof Module!=="undefined"&&Module.FS&&document.getElementById("loading").style.display==="none"','Startup timed out');
 await delay(800);
 await click((22+94*['en','de','es'].indexOf(language)+44)*1.25,84*1.25);
 const rows=(await readFile('games/catalog.txt','utf8')).trim().split('\n').map(x=>x.split('|')).sort((a,b)=>Number(a[4])-Number(b[4])).filter(x=>x[1]!=='123 Book');
 async function open(title){const index=rows.findIndex(r=>r[1]===title);if(index<0)throw Error('Missing required activity '+title);await key('Home');for(let i=0;i<index;i++)await key('ArrowDown');await key('Enter');await delay(500)}
 async function saved(name){return evaluate(`(()=>{const fs=Module.FS;const paths=[];function scan(p){for(const n of fs.readdir(p)){if(n==='.'||n==='..')continue;const a=p+'/'+n;try{if(fs.isDir(fs.stat(a).mode))scan(a);else if(a.endsWith('/${name}.txt')&&a.includes('jungle.${name}'))paths.push(a)}catch{}}}scan('/kryon-apps/jungle');return paths.map(p=>fs.readFile(p,{encoding:'utf8'}))})()`)}
 async function shot(name){await writeFile('backup/new-activities-web/'+page+'-'+language+'-'+name+'.png',Buffer.from((await command('Page.captureScreenshot',{format:'png'})).data,'base64'))}
 const wanted=process.env.JUNGLE_WEB_ACTIVITY||'';
 const activities=[['shapes','Shapes & Sorting'],['matching','Matching Pairs'],['hide_seek','Hide & Seek'],['drums','Little Drums'],['garden','Grow a Garden']].filter(([name,title])=>(name!=='garden'||rows.some(r=>r[1]===title))&&(!wanted||name===wanted));
 for(const [name,title] of activities){
  await open(title);await shot(name+'-phone');
  if(page!=='canvas.html'){
   const labels=await evaluate(`[...document.querySelectorAll('#kryon-dom-root button')].map(e=>e.getAttribute('aria-label'))`);
   if(labels.length<3)throw Error('No native controls '+name+JSON.stringify(labels));
  }
  // Genuine touches exercise mode/action dispatch on the same 400x700 content.
  if(name==='shapes'){
   const phaseWords={en:['Watch','Press','Drag','Drag','Let go','Let go','Your turn'],de:['Schau zu','Drücken','Ziehen','Ziehen','Loslassen','Loslassen','Du bist dran'],es:['Mira','Presiona','Arrastra','Arrastra','Suelta','Suelta','Tu turno']}[language];
   async function touch(type,x,y){await command('Input.dispatchTouchEvent',{type,touchPoints:type==='touchEnd'?[]:[{x,y,id:1}]});await delay(100)}
   // Both orientations, every mode: let one complete example play without
   // giving it input, then cancel Show me with real mouse/key/touch contacts.
   for(const width of [400,960]){
    const height=width===400?756:600;
    await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await delay(300);
    const scale=width===400?Math.min(width/360,(height-56)/640):Math.min(width/720,(height-56)/420,1.6);
    const w=Math.floor(width/scale),button=Math.min(84,Math.floor((w-76)/5)),left=Math.floor((w-5*button-48)/2);
    const point=(index)=>[(left+index*(button+12)+button/2)*scale,56+44*scale];
    for(let mode=0;mode<3;mode++){
     await click(...point(mode));
     await key('Escape');const beforeDemo=await saved(name);await open(title);
     await click(...point(4));const started=Date.now();
     const times=[350,850,1450,2350,4050,4850,5600];
     for(let phase=0;phase<times.length;phase++){
      await delay(Math.max(0,started+times[phase]-Date.now()));
      if(page==='dom.html'&&!await evaluate(`document.getElementById('kryon-dom-root').textContent.includes(${JSON.stringify(phaseWords[phase])})`))throw Error('Missing sorting tutorial phase '+phaseWords[phase]);
      await shot(`tutorial-${width}-${mode}-${phase}`);
     }
     await key('Escape');
     if(JSON.stringify(await saved(name))!==JSON.stringify(beforeDemo))throw Error('Tutorial advanced real progress');
     await open(title);await click(...point(4));await key('a');await shot(`tutorial-key-cancel-${width}-${mode}`);
     await click(...point(4));await touch('touchStart',8,height-8);await shot(`tutorial-touch-cancel-${width}-${mode}`);await touch('touchEnd',8,height-8);
     if(page==='dom.html'&&!await evaluate(`document.getElementById('kryon-dom-root').textContent.includes(${JSON.stringify(phaseWords[6])})`))throw Error('Touch did not cancel demonstration');
     await click(...point(4));
     await command('Input.dispatchMouseEvent',{type:'mousePressed',x:8,y:height-8,button:'left',clickCount:1});await delay(100);
     await shot(`tutorial-mouse-cancel-${width}-${mode}`);
     await command('Input.dispatchMouseEvent',{type:'mouseReleased',x:8,y:height-8,button:'left',clickCount:1});
     // Pixel assertions cover Canvas as well as DOM semantics. The playing
     // area must be identical to the quiet child turn for every cancellation;
     // a moving hand must actually change that area during demonstration.
     const prefix=`backup/new-activities-web/${page}-${language}-`;
     const visual=spawnSync('python3',['-c',`
import sys
from PIL import Image, ImageChops
prefix,width,mode=sys.argv[1],int(sys.argv[2]),sys.argv[3]
def board(suffix):
 p=Image.open(prefix+suffix+'.png').convert('RGB')
 return p.crop((0,210,p.width,p.height))
turn=board(f'tutorial-{width}-{mode}-6')
for kind in ['key','touch','mouse']:
 difference=ImageChops.difference(turn,board(f'tutorial-{kind}-cancel-{width}-{mode}'))
 # Subpixel rounded-edge antialiasing may differ by up to 8/255.
 samples=difference.get_flattened_data() if hasattr(difference,'get_flattened_data') else difference.getdata()
 assert not any(max(pixel)>8 for pixel in samples), f'{kind} left the tutorial visible'
assert ImageChops.difference(board(f'tutorial-{width}-{mode}-1'),board(f'tutorial-{width}-{mode}-3')).getbbox(), 'No visible hand movement'
`,prefix,String(width),String(mode)],{encoding:'utf8',timeout:15000});
     if(visual.status!==0)throw Error('Tutorial rendering/cancellation '+visual.stderr);
     console.log(`local ${page} ${language} tutorial ${width} mode=${mode}: phases, no progress, input cancellation`);
    }
   }
   await command('Emulation.setDeviceMetricsOverride',{width:400,height:756,deviceScaleFactor:1,mobile:false});await delay(300);
   await click(200,56+44);
   // Finish the two-item size round through actual pointer contacts.
   // A gentle miss is allowed; try both homes for each remaining item.
   for(let item=0;item<2;item++){
    if(item===0){await click(112,56+235);await click(112,56+530);await click(288,56+530)}
    else {
     // Try both homes with a held drag: the first may be a gentle miss.
     for(const home of [112,288]){
      await touch('touchStart',288,56+235);
      for(let step=1;step<=6;step++)await touch('touchMove',288+(home-288)*step/6,56+235+295*step/6);
      await touch('touchEnd',home,56+530);await delay(180);
     }
    }
   }
   await delay(2900);
  }
  if(name==='matching'){
   await key('Escape');const board=(await saved(name))[0].trim().split(' ');await open(title);
   const animals=board.slice(5,9);const pair=animals.map((a,i)=>a===animals[0]?i:-1).filter(i=>i>=0);
   for(const i of pair)await click(i%2?296:104,i<2?300:491);
  }
  if(name==='hide_seek'){await click(70,400);await click(200,56+593)}
  if(name==='drums'){
   await click(100,350);await click(300,92);await click(100,92);
   if(page==='dom.html'){
    await evaluate('drumsAudio=[];drumsClicks=[]');
    const names={en:['Big drum','Little drum','Shaker','Bell'],de:['Große Trommel','Kleine Trommel','Rassel','Glocke'],es:['Tambor grande','Tambor pequeño','Sonajero','Campana']}[language],sounds=['low_drum','small_drum','shaker','bell'];
    for(let pad=0;pad<4;pad++){
     if(!await evaluate(`(()=>{const button=[...document.querySelectorAll('#kryon-dom-root button')].find(button=>button.getAttribute('aria-label')==='${names[pad]}');button.focus();return document.activeElement===button})()`))throw Error('Drum button did not take focus '+names[pad]);
     await shot('keyboard-'+pad+'-space-before');await controlKey(' ');await shot('keyboard-'+pad+'-space-after');
     let hits=await evaluate('drumsAudio');
     const clicks=await evaluate('drumsClicks');await evaluate('drumsClicks=[]');
     if(clicks.length!==1||hits.length!==1||hits[0]!=='assets/drums/sounds/'+sounds[pad]+'.wav')throw Error('Space did not hit '+names[pad]+' once '+JSON.stringify({clicks,hits}));
     if(!await evaluate(`document.activeElement?.getAttribute('aria-label')==='${names[pad]}'`))throw Error('Space blurred '+names[pad]);
     await evaluate('drumsAudio=[];drumsClicks=[]');await controlKey('Enter');await shot('keyboard-'+pad+'-enter-after');
     hits=await evaluate('drumsAudio');
     const enterClicks=await evaluate('drumsClicks');
     if(enterClicks.length!==1||hits.length!==1||hits[0]!=='assets/drums/sounds/'+sounds[pad]+'.wav')throw Error('Enter did not hit '+names[pad]+' once '+JSON.stringify({clicks:enterClicks,hits}));
     await evaluate('drumsAudio=[];drumsClicks=[]');
    }
   }
  }
  if(name==='garden'){await click(100,56+572);for(let i=0;i<4;i++)await click(200,56+572)}
  await shot(name+'-played');
  await click(372,28);await click(372,28);await click(28,28);
  const before=await saved(name);if(!before.length)throw Error('Missing browser save '+name);
  if(name==='matching'&&before[0].trim().split(' ').slice(9,13).filter(x=>x==='1').length!==2)throw Error('Matching pair failed '+before);
  if(name==='garden'&&!before[0].startsWith('garden 1 5 '))throw Error('Garden touches failed '+before);
  if(name==='shapes'&&(!before[0].startsWith('shapes 1 2 ')||Number(before[0].trim().split(' ')[8])<=1))throw Error('Shapes mode failed '+before);
  if(name==='hide_seek'&&!before[0].startsWith('hideseek 2 1 '))throw Error('Hide mode failed '+before);
  await open(title);await key('Escape');
  if(JSON.stringify(await saved(name))!==JSON.stringify(before))throw Error('Browser resume changed '+name);
  await open(title);
  await command('Emulation.setDeviceMetricsOverride',{width:960,height:600,deviceScaleFactor:1,mobile:false});await delay(400);await shot(name+'-desktop');
  await key('Escape');await command('Emulation.setDeviceMetricsOverride',{width:400,height:756,deviceScaleFactor:1,mobile:false});await delay(300);
  console.log('local '+page+' activity interaction/save/resume: '+name);
 }
 await key('End');await shot('menu-end');await key('Enter');await key('Escape');
 if(errors.length)throw Error(JSON.stringify(errors));
 console.log('local browser activities test passed: '+page);
}finally{
 if(socket)socket.close();browser.kill('SIGTERM');
 await new Promise(resolve=>{if(browser.exitCode!==null)resolve();else browser.once('exit',resolve)});
 server.close();await rm(profile,{recursive:true,force:true,maxRetries:8,retryDelay:250});
}

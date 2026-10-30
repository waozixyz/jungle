// Private headless browser check for compressed narration playback.
import {spawn} from 'node:child_process';
import {readFile,mkdtemp,rm} from 'node:fs/promises';
import {createServer} from 'node:http';
import {extname,join,resolve} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';

const root=resolve(process.env.JUNGLE_WEB_ROOT||'build/web');
const page=process.env.JUNGLE_WEB_PAGE||'index.html';
const profile=await mkdtemp('/tmp/jungle-speech-web-');
const mime={'.html':'text/html','.js':'text/javascript','.wasm':'application/wasm','.json':'application/json',
  '.png':'image/png','.jpg':'image/jpeg','.wav':'audio/wav','.ogg':'audio/ogg'};
const requested=[];
const server=createServer(async(request,response)=>{
  try{
    const path=decodeURIComponent(new URL(request.url,'http://localhost').pathname);
    const file=resolve(root,'.'+path);
    if(!file.startsWith(root+'/'))throw Error('path');
    requested.push(path);
    response.writeHead(200,{'Content-Type':mime[extname(file)]||'application/octet-stream'});
    response.end(await readFile(file));
  }catch{
    response.writeHead(404);response.end();
  }
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const env={...process.env,YUE_DESKTOP_RECOVERY:'0',TMPDIR:'/tmp'};
for(const name of ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','DBUS_SESSION_BUS_ADDRESS','SESSION_MANAGER'])delete env[name];
const browser=spawn(process.env.CHROMIUM||'chromium',['--headless','--no-sandbox','--disable-gpu','--disable-webgl',
  '--disable-dev-shm-usage','--mute-audio','--autoplay-policy=no-user-gesture-required','--no-first-run','--no-default-browser-check','--remote-debugging-port=0',
  '--user-data-dir='+profile,'about:blank'],{env,stdio:['ignore','ignore','pipe']});
let socket,stderr='';
const diagnostics=[];
browser.stderr.on('data',data=>stderr=(stderr+data).slice(-3000));
try{
  let port;
  const deadline=Date.now()+30000;
  while(Date.now()<deadline){
    try{port=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break}catch{}
    if(browser.exitCode!==null)throw Error(stderr);
    await delay(100);
  }
  if(!port)throw Error('Private Chromium did not start: '+stderr);
  const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
  socket=new WebSocket(pages.find(entry=>entry.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject});
  let sequence=0;
  const pending=new Map();
  socket.onmessage=event=>{
    const message=JSON.parse(event.data);
    if(message.method==='Runtime.exceptionThrown')diagnostics.push(message.params);
    if(message.method==='Runtime.consoleAPICalled'&&message.params.type==='error')diagnostics.push(message.params.args);
    if(pending.has(message.id)){pending.get(message.id)(message);pending.delete(message.id)}
  };
  async function command(method,params={}){
    const id=++sequence;
    const reply=new Promise(resolve=>pending.set(id,resolve));
    socket.send(JSON.stringify({id,method,params}));
    const result=await reply;
    if(result.error)throw Error(JSON.stringify(result.error));
    return result.result;
  }
  async function evaluate(expression){
    const result=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
    if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  }
  async function key(name,code=name){
    const virtualKey=name==='F10'?121:name.charCodeAt(0);
    await command('Input.dispatchKeyEvent',{type:'keyDown',key:name,code,windowsVirtualKeyCode:virtualKey});
    await delay(80);
    await command('Input.dispatchKeyEvent',{type:'keyUp',key:name,code,windowsVirtualKeyCode:name.charCodeAt(0)});
    await delay(250);
  }
  async function click(x,y){
    const box=await evaluate('(()=>{const box=document.getElementById("canvas").getBoundingClientRect();return {x:box.x,y:box.y,width:box.width,height:box.height}})()');
    const actualX=box.x+x*box.width/320,actualY=box.y+y*box.height/200;
    await command('Input.dispatchMouseEvent',{type:'mouseMoved',x:actualX,y:actualY});
    await command('Input.dispatchMouseEvent',{type:'mousePressed',x:actualX,y:actualY,button:'left',clickCount:1});
    await delay(80);
    await command('Input.dispatchMouseEvent',{type:'mouseReleased',x:actualX,y:actualY,button:'left',clickCount:1});
    await delay(400);
  }
  async function waitFor(expression,description,timeout=15000){
    const end=Date.now()+timeout;
    while(Date.now()<end){
      if(diagnostics.length)throw Error(JSON.stringify(diagnostics));
      if(await evaluate(expression))return;
      await delay(100);
    }
    throw Error(description);
  }
  await command('Runtime.enable');
  await command('Page.enable');
  await command('Page.addScriptToEvaluateOnNewDocument',{source:`
window.speechTest={events:[],elements:[],decoded:0,created:0,revoked:0};
Object.defineProperty(HTMLMediaElement.prototype,'junglePath',{
 configurable:true,
 get(){return this.dataset.junglePath},
 set(path){
  this.dataset.junglePath=path;
  if(!this.dataset.speechInstrumented){
   this.dataset.speechInstrumented='1';window.speechTest.elements.push(this);
   const play=this.play.bind(this),pause=this.pause.bind(this),remove=this.removeAttribute.bind(this);
   this.play=()=>{window.speechTest.events.push('play');return play()};
   this.pause=()=>{window.speechTest.events.push('pause');return pause()};
   this.removeAttribute=name=>{if(name==='src')window.speechTest.events.push('cancel');return remove(name)};
  }
 }
});
const decodeAudioData=OfflineAudioContext.prototype.decodeAudioData;
OfflineAudioContext.prototype.decodeAudioData=function(...args){
 window.speechTest.decoded++;
 return decodeAudioData.apply(this,args);
};
const createObjectURL=URL.createObjectURL.bind(URL);
URL.createObjectURL=blob=>{window.speechTest.created++;return createObjectURL(blob)};
const revokeObjectURL=URL.revokeObjectURL.bind(URL);
URL.revokeObjectURL=url=>{window.speechTest.revoked++;return revokeObjectURL(url)};
`});
  await command('Emulation.setDeviceMetricsOverride',{width:960,height:600,deviceScaleFactor:1,mobile:false});
  await command('Page.navigate',{url:'http://127.0.0.1:'+server.address().port+'/'+page});
  await waitFor('typeof Module!=="undefined"&&Module.FS&&document.getElementById("loading").style.display==="none"','Startup timed out');

  const index=await evaluate('(async()=>await (await fetch("asset-packs.json")).json())()');
  const speechEntry=index.files['assets/speech.txt'];
  const lesson='assets/jungle-book/sounds/airplane.wav';
  if(!speechEntry||!Object.keys(index.files).some(path=>path.startsWith('assets/speech/')&&path.endsWith('.ogg')))
    throw Error('Web distribution omitted compressed speech');
  const composed=await evaluate(`(async()=>{
   const index=await speech();
   const bytes=await soundBytes(${JSON.stringify(lesson)},()=>true);
   const view=new DataView(bytes.buffer);
   const expectedFrames=index.voices.get(${JSON.stringify(lesson)}).reduce((total,segment)=>total+segment.frames,0);
   return {bytes:bytes.length,channels:view.getUint16(22,true),rate:view.getUint32(24,true),
     frames:view.getUint32(40,true)/2,expectedFrames,nonzero:bytes.slice(44).some(byte=>byte!==0)};
  })()`);
  if(composed.channels!==1||composed.rate!==22050||composed.frames!==composed.expectedFrames||!composed.nonzero||
    composed.bytes!==44+composed.expectedFrames*2)
    throw Error('Browser composed the wrong lesson: '+JSON.stringify(composed));

  const transport=await evaluate(`(async()=>{
   const audio=packedAudio(${JSON.stringify(lesson)});
   await audio.play();
   const started=audio.currentTime;
   await new Promise(resolve=>setTimeout(resolve,250));
   const playing=!audio.paused&&audio.currentTime>started;
   audio.pause();
   const heldAt=audio.currentTime;
   await new Promise(resolve=>setTimeout(resolve,200));
   const held=audio.paused&&Math.abs(audio.currentTime-heldAt)<.002;
   await audio.play();
   const resumedAt=audio.currentTime;
   await new Promise(resolve=>setTimeout(resolve,250));
   const resumed=!audio.paused&&audio.currentTime>resumedAt;
   audio.pause();audio.removeAttribute('src');audio.load();
   return {playing,held,resumed,started,heldAt,resumedAt,final:audio.currentTime};
  })()`);
  if(!transport.playing||!transport.held||!transport.resumed)
    throw Error('Browser Audio position/pause/resume failed: '+JSON.stringify(transport));

  const catalog=(await readFile('games/catalog.txt','utf8')).trim().split('\n').map(line=>line.split('|'))
    .filter(row=>row[1]!=='123 Book').sort((left,right)=>Number(left[4])-Number(right[4]));
  const abcEntry=String(catalog.findIndex(row=>row[1]==='ABC Book')+1);
  await key(abcEntry);
  await key('1');
  await waitFor('speechTest.elements.length>0&&speechTest.decoded>0&&!speechTest.elements.at(-1).jungleLoading',
    'Alphabet narration did not decode through the Audio transport');
  const element=await evaluate('(()=>{const audio=speechTest.elements.at(-1);return {path:audio.junglePath,volume:audio.volume}})()');
  if(!element.path.startsWith('assets/abc/sounds/en/letters/')||element.volume!==0.45)
    throw Error('Wrong browser narration transport: '+JSON.stringify(element));

  await evaluate('speechTest.events=[]');
  await key(' ','Space');
  let events=await evaluate('speechTest.events');
  if(events.at(-1)!=='pause'){
    if(events.at(-1)!=='play')throw Error('Alphabet play/pause control did not reach Audio: '+JSON.stringify(events));
    await key(' ','Space');
  }
  events=await evaluate('speechTest.events');
  if(events.at(-1)!=='pause')throw Error('Space did not pause narration: '+JSON.stringify(events));
  await evaluate('speechTest.events=[]');
  await key(' ','Space');
  events=await evaluate('speechTest.events');
  if(events.at(-1)!=='play')throw Error('Space did not resume narration: '+JSON.stringify(events));

  await evaluate('speechTest.events=[];speechTest.elements=[]');
  await key('F10');
  await waitFor('speechTest.events.includes("cancel")&&speechTest.revoked>0','Mute did not cancel browser narration');
  const mutedCount=await evaluate('speechTest.elements.length');
  await key('b','KeyB');
  await delay(500);
  if(await evaluate('speechTest.elements.length')!==mutedCount)
    throw Error('Muted alphabet still created an Audio element');

  await key('F10');
  await key('b','KeyB');
  await waitFor('speechTest.elements.length>0&&speechTest.decoded>0','Unmuted letter did not speak');
  await evaluate('speechTest.events=[]');
  await key('Escape');
  await waitFor('speechTest.events.includes("cancel")&&speechTest.elements.at(-1).src===""',
    'Leaving the lesson did not cancel narration');

  const cancelled=await evaluate(`(async()=>{
   const audio=packedAudio(${JSON.stringify(lesson)});
   const pendingPlay=audio.play();
   audio.pause();
   try{await pendingPlay}catch(error){if(error.name!=='AbortError')throw error}
   return {loading:audio.jungleLoading,src:audio.src};
  })()`);
  if(cancelled.loading||cancelled.src)throw Error('Pause did not cancel an in-flight decode: '+JSON.stringify(cancelled));
  if(diagnostics.length)throw Error(JSON.stringify(diagnostics));
  if(requested.some(path=>path.includes('/sounds/')&&path.endsWith('.wav')))
    throw Error('Browser fetched a narration WAV: '+JSON.stringify(requested.filter(path=>path.endsWith('.wav'))));
  console.log('local speech browser test: 20-clip lesson decoded in memory; sequence, pause, mute, navigation and decode cancellation passed');
}finally{
  if(socket)socket.close();
  browser.kill('SIGTERM');
  await new Promise(resolve=>{if(browser.exitCode!==null)resolve();else browser.once('exit',resolve)});
  server.close();
  await rm(profile,{recursive:true,force:true,maxRetries:8,retryDelay:250});
}

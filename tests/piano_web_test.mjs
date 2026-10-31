// Exercise the compiled piano in a private headless browser and profile.
import {spawn} from 'node:child_process';
import {readFile,writeFile,mkdtemp,rm,mkdir} from 'node:fs/promises';
import {createServer} from 'node:http';
import {resolve,join,extname} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';

await mkdir('work/w',{recursive:true});await mkdir('work/b',{recursive:true});
const root=resolve(process.env.JUNGLE_WEB_ROOT||'build/web');
const page=process.env.JUNGLE_WEB_PAGE||'index.html';
const menu=(await readFile('games/catalog.txt','utf8')).trim().split('\n').map(l=>l.split('|')).filter(r=>r[1]!=='123 Book').sort((a,b)=>Number(a[4])-Number(b[4]));
const pianoEntry=menu.findIndex(r=>r[1]==='Little Piano');
if(pianoEntry<0)throw Error('Little Piano missing from catalog');
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
  const reply=await promise;if(reply.error)throw Error(JSON.stringify(reply.error));return reply.result;
 }
 async function evaluate(expression){
  const result=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;
 }
 async function key(key){
  // App-level shortcuts are tested with no native control holding focus.
  if(key==='Enter'||key===' ')await evaluate('if(document.documentElement.dataset.backend==="dom")document.activeElement?.blur()');
  const code=key==='Home'?36:key==='ArrowDown'?40:key==='Enter'?13:key==='Escape'?27:key===' '?32:key.toUpperCase().charCodeAt(0);
  await command('Input.dispatchKeyEvent',{type:'keyDown',key,windowsVirtualKeyCode:code});
  await delay(80);
  await command('Input.dispatchKeyEvent',{type:'keyUp',key,windowsVirtualKeyCode:code});await delay(180);
 }
 async function click(x,y){
  await command('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});await delay(80);
  await command('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',clickCount:1});await delay(180);
 }
 async function waitFor(expression,description,timeout=30000){
  const end=Date.now()+timeout;
  while(Date.now()<end){if(errors.length)throw Error(JSON.stringify(errors));if(await evaluate(expression))return;await delay(100)}
  throw Error(description);
 }
 await command('Runtime.enable');await command('Page.enable');
 await command('Page.addScriptToEvaluateOnNewDocument',{source:`
  window.pianoAudio=[];window.pianoElement=null;
  const originalPlay=HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play=function(){
   if(this.junglePath?.startsWith('assets/piano/')){
    window.pianoAudio.push({path:this.junglePath,time:performance.now(),volume:this.volume});window.pianoElement=this;
   }
   return originalPlay.apply(this,arguments);
  };
 `});
 await command('Emulation.setDeviceMetricsOverride',{width:960,height:600,deviceScaleFactor:1,mobile:false});
 await command('Page.navigate',{url:'http://127.0.0.1:'+server.address().port+'/'+page});
 await waitFor('typeof Module!=="undefined"&&Module.FS&&document.getElementById("loading").style.display==="none"','Startup timed out');
 function layout(width,height){
  height-=56;
  const pad=Math.max(8,Math.min(28,Math.floor(width/24),Math.floor(height/24)));
  const w=Math.min(width-2*pad,1000),h=Math.min(height-2*pad,660),left=Math.floor((width-w)/2),top=Math.floor((height-h)/2),rail=Math.max(12,Math.floor(w/30));
  const x=left+rail,kw=w-rail*2,keyWidth=Math.max(36,Math.floor(kw/22));
  let kh=Math.min(230,Math.floor(h*.36));if(width<500&&h<560)kh=Math.floor(h*.29);if(h<360)kh=Math.floor(h*.26);
  const y=top+h-22-kh,cw=Math.min(kw,620),rh=h<360?30:40,controls=y-(cw<500?rh*2+6:rh)-12;
  return {x,y:y+56,kh,keyWidth,controls:controls+56,top:top+56,h,title:top+8+56};
 }
 await key('Home');for(let i=0;i<pianoEntry;i++)await key('ArrowDown');await key('Enter');await key('1');await key('w');await key('2');
 let notes=await evaluate('pianoAudio.map(note=>note.path)');
 if(JSON.stringify(notes)!==JSON.stringify([60,61,62].map(p=>'assets/piano/sounds/'+p+'.wav')))throw Error('Wrong fixed shortcut pitches: '+JSON.stringify(notes));
 if(await evaluate('pianoAudio.some(note=>note.volume!==.25)'))throw Error('Piano bypassed quiet gain');
 const p=layout(960,600);
 const white=[48,50,52,53,55,57,59,60,62,64,65,67,69,71,72,74,76,77,79,81,83,84];
 const black=[49,51,54,56,58,61,63,66,68,70,73,75,78,80,82];
 const after=[0,1,3,4,5,7,8,10,11,12,14,15,17,18,19];
 // Every physical white and black key plays its own absolute MIDI pitch.
 await evaluate('pianoAudio=[]');
 for(let n=0;n<white.length;n++)await click(p.x+(n+.5)*p.keyWidth,p.y+p.kh*.85);
 for(let n=0;n<black.length;n++)await click(p.x+(after[n]+1)*p.keyWidth,p.y+20);
 notes=await evaluate('pianoAudio.map(note=>Number(note.path.match(/(\\d+)\\.wav$/)[1]))');
 if(JSON.stringify(notes)!==JSON.stringify([...white,...black]))throw Error('37-key geometry/audio mismatch '+JSON.stringify(notes));
 await mkdir('backup/catalog-ui-integration/web',{recursive:true});
 // Optional phrase lessons demonstrate before accepting input. A short tap
 // retries the same note; a complete hold/release moves to the next pitch.
 await evaluate('pianoAudio=[]');await click(370,p.controls+20);
 await waitFor('pianoAudio.length===6','Lesson did not demonstrate its first phrase',10000);
 await waitFor('pianoElement.paused','Lesson demonstration did not release its last note');await delay(350);
 await evaluate('pianoAudio=[]');await key('2');
 if(await evaluate('pianoAudio.length'))throw Error('Lesson accepted the wrong first pitch');
 await key('1');await key('2');
 if(await evaluate('pianoAudio.length!==1'))throw Error('An early release passed the lesson note');
 const domLesson=await evaluate('document.documentElement.dataset.backend==="dom"');
 await command('Input.dispatchKeyEvent',{type:'keyDown',key:'1',code:'Digit1',windowsVirtualKeyCode:49});
 if(domLesson){
  await waitFor('document.body.innerText.includes("Let go now")','Missing exact release cue');
  await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve(true))))');
  if(!await evaluate('document.body.innerText.includes("Let go now")'))throw Error('Release cue did not remain visible for two frames');
 }else await delay(420);
 await writeFile('backup/catalog-ui-integration/web/piano-lesson-release-'+page+'.png',Buffer.from((await command('Page.captureScreenshot',{format:'png'})).data,'base64'));
 await command('Input.dispatchKeyEvent',{type:'keyUp',key:'1',code:'Digit1',windowsVirtualKeyCode:49});
 if(domLesson)await waitFor('document.body.innerText.includes("Your turn: press the lit key")','The valid hold did not reach the next lesson note');
 else await delay(100);
 await key('2');
 if(await evaluate('!pianoAudio.at(-1)?.path.endsWith("/62.wav")'))throw Error('Holding and releasing did not advance the lesson '+JSON.stringify(await evaluate('({audio:pianoAudio,text:document.body.innerText})')));
 await click(480,p.title+16);await evaluate('pianoAudio=[]');await key('Escape');
 await waitFor('pianoAudio.length>0','Cancelling the song chooser stranded the lesson');
 await key('Enter');

 for(let song=0;song<5;song++){
  await click(480,p.title+16);
  if(song===0)await writeFile('backup/catalog-ui-integration/web/piano-chooser-'+page+'.png',Buffer.from((await command('Page.captureScreenshot',{format:'png'})).data,'base64'));
  const row=Math.min(64,Math.floor((p.h-118)/5));
  await click(480,p.top+70+song*row+(row-6)/2);
  await evaluate('pianoAudio=[]');await click(p.x+7.5*p.keyWidth,p.y+p.kh*.85);
  if(await evaluate('pianoAudio.length!==1||pianoAudio[0].path!=="assets/piano/sounds/60.wav"'))throw Error('Selecting song '+song+' changed middle C');
 }
 // A complete public-domain melody follows the selected score and held notes.
 await key('Enter');await evaluate('pianoAudio=[]');
 await click(760,p.controls+20); // Normal -> Fast
 await key(' ');
 await waitFor('pianoAudio.length===17','Selected song did not play to its end',20000);
 await delay(1500);
 const played=await evaluate('pianoAudio');
 const expected=[64,62,60,64,62,60,60,60,60,60,62,62,62,62,64,62,60];
 if(JSON.stringify(played.map(n=>Number(n.path.match(/(\d+)\.wav$/)[1])))!==JSON.stringify(expected))throw Error('Selected melody changed '+JSON.stringify(played));
 if(played[3].time-played[2].time<1100)throw Error('Half note ended early');
 if(!(await evaluate('pianoElement.paused')))throw Error('Last note never stopped');
 await writeFile('backup/catalog-ui-integration/web/piano-score-'+page+'.png',Buffer.from((await command('Page.captureScreenshot',{format:'png'})).data,'base64'));
 await click(930,25);await evaluate('pianoAudio=[]');await key('3');
 if(await evaluate('pianoAudio.length'))throw Error('Muted piano played audio');
 await click(930,25);await key('3');await waitFor('pianoAudio.length===1','Unmuting did not restore audio');
 await key('Escape');if(!(await evaluate('pianoElement.paused')))throw Error('Leaving piano did not stop audio');
 await key('Home');for(let i=0;i<pianoEntry;i++)await key('ArrowDown');await key('Enter');
 await command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await delay(500);
 const phone=layout(390,844);
 await evaluate('pianoAudio=[]');
 await command('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:phone.x+phone.keyWidth,y:phone.y+20}]});await delay(80);
 await command('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 await waitFor('pianoAudio.length===1','Touch key never played');
 if(await evaluate('pianoAudio[0].path')!=='assets/piano/sounds/61.wav')throw Error('Black touch key activated another pitch');
 // Scrolling reveals both ends of the same fixed keyboard on a phone.
 await command('Input.dispatchMouseEvent',{type:'mouseWheel',x:phone.x+100,y:phone.y+30,deltaX:0,deltaY:3000});await delay(800);
 await evaluate('pianoAudio=[]');await click(344,phone.y+phone.kh*.85);
 if(await evaluate('pianoAudio.at(-1)?.path')!=='assets/piano/sounds/84.wav')throw Error('Phone cannot reach fixed high C6');
 await click(195,phone.title+16);await click(195,phone.top+70+64+(64-6)/2);
 await evaluate('pianoAudio=[]');await click(344,phone.y+phone.kh*.85);
 if(await evaluate('pianoAudio.at(-1)?.path')!=='assets/piano/sounds/84.wav')throw Error('Song selection moved phone keyboard viewport');
 await command('Input.dispatchMouseEvent',{type:'mouseWheel',x:phone.x+100,y:phone.y+30,deltaX:0,deltaY:-3000});await delay(800);
 await evaluate('pianoAudio=[]');await click(phone.x+18,phone.y+phone.kh*.85);
 if(await evaluate('pianoAudio.at(-1)?.path')!=='assets/piano/sounds/48.wav')throw Error('Phone cannot reach fixed low C3');
 await writeFile('backup/catalog-ui-integration/web/piano-'+page+'.png',Buffer.from((await command('Page.captureScreenshot',{format:'png'})).data,'base64'));
 if(errors.length)throw Error(JSON.stringify(errors));
 console.log('local piano browser test ('+page+'): 37 accurate physical keys, five-song selection without remapping, complete selected melody, held notes, quiet gain, touch, mute and back passed');
}finally{
 if(socket)socket.close();browser.kill('SIGTERM');
 await new Promise(resolve=>{if(browser.exitCode!==null)resolve();else browser.once('exit',resolve)});
 server.close();await rm(profile,{recursive:true,force:true,maxRetries:8,retryDelay:250});
}

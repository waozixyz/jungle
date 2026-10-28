// Exercise the compiled piano in a private headless browser and profile.
import {spawn,spawnSync} from 'node:child_process';
import {readFile,writeFile,mkdtemp,rm,mkdir} from 'node:fs/promises';
import {createServer} from 'node:http';
import {resolve,join,extname} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';

const root=resolve(process.env.JUNGLE_WEB_ROOT||'build/web');
const page=process.env.JUNGLE_WEB_PAGE||'dom.html';
const profile=await mkdtemp('/tmp/jungle-piano-web-');
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
const env={...process.env,YUE_DESKTOP_RECOVERY:'0',TMPDIR:'/tmp'};
for(const key of ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','DBUS_SESSION_BUS_ADDRESS','SESSION_MANAGER'])delete env[key];
const browser=spawn(process.env.CHROMIUM||'chromium',['--headless','--no-sandbox','--disable-gpu','--disable-webgl','--disable-dev-shm-usage','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{env,stdio:['ignore','ignore','pipe']});
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
  if(page==='dom.html'&&(key==='Enter'||key===' '))await evaluate('document.activeElement?.blur()');
  const code=key==='Enter'?13:key==='Escape'?27:key===' '?32:key.startsWith('Arrow')?({ArrowLeft:37,ArrowUp:38,ArrowRight:39,ArrowDown:40}[key]):key.toUpperCase().charCodeAt(0);
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
 await delay(600);
 const audit=await evaluate(`({native:document.querySelectorAll('[data-kryon-paint=span]').length,buttons:document.querySelectorAll('#kryon-dom-root button').length,images:document.querySelectorAll('#kryon-dom-paint img').length,tiles:document.querySelectorAll('#kryon-dom-paint canvas').length,visibleCanvas:getComputedStyle(Module.canvas).visibility,invalid:[...document.querySelectorAll('#kryon-dom-root button')].some(b=>!b.style.width||!b.style.height)})`);
 if(!audit.native||!audit.buttons||!audit.images||audit.visibleCanvas!=='hidden'||audit.invalid)throw Error('Native DOM output is missing '+JSON.stringify(audit));
 const catalog=JSON.parse(spawnSync('python3',['-c',`import sys,json;sys.path.insert(0,'tools');from book_catalog import BOOKS,BOOK_GROUPS,WORDS,TITLES;print(json.dumps({'books':dict(BOOKS),'groups':BOOK_GROUPS,'titles':{k:TITLES.get(k,[{'jungle':'Wild animals','garden':'Garden','fruits':'Fruits','farm':'Farm'}.get(k,k)])[0] for k,_ in BOOKS},'words':{k:v[0] for k,v in WORDS.items()}}))`],{encoding:'utf8'}).stdout);
 await key('1');await key('s');
 const receipts=[];
 async function groupTab(label){
  const point=await evaluate(`(()=>{const b=[...document.querySelectorAll('#kryon-dom-root button')].filter(e=>e.getAttribute('aria-label')===${JSON.stringify(label)}&&e.getBoundingClientRect().height<60).map(e=>e.getBoundingClientRect()).sort((a,b)=>a.y-b.y)[0];return b&&{x:b.x+b.width/2,y:b.y+b.height/2}})()`);
  if(!point)throw Error('Missing book group '+label);await click(point.x,point.y);
 }
 for(const [group,names] of catalog.groups)for(const [slot,name] of names.entries()){
  await groupTab(group);for(let i=0;i<slot;i++)await key('ArrowRight');
  const card=await evaluate(`(()=>{const e=[...document.querySelectorAll('#kryon-dom-root button')].find(e=>e.getAttribute('aria-label')===${JSON.stringify(catalog.titles[name])}&&e.getBoundingClientRect().height>70);if(!e)return null;const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);
  if(!card){await writeFile('backup/dom-visual/crawl-failure.png',Buffer.from((await command('Page.captureScreenshot',{format:'png'})).data,'base64'));throw Error('Book card unavailable '+name);}await click(card.x,card.y);
  await delay(100);await key(' ');
  for(const [index,word] of catalog.books[name].entries()){
   const label=catalog.words[word];
   await waitFor(`([...document.querySelectorAll('[data-kryon-paint=span]')].some(e=>e.textContent===${JSON.stringify(label)})&&[...document.querySelectorAll('#kryon-dom-paint img')].some(e=>e.complete&&e.naturalWidth>500&&e.getBoundingClientRect().height>180))`,'Book page missing '+name+'/'+word);
   if(index===0||index===catalog.books[name].length-1)await writeFile('backup/dom-visual/'+name+'-'+index+'.png',Buffer.from((await command('Page.captureScreenshot',{format:'png'})).data,'base64'));
   receipts.push({book:name,page:index,word,label});
   if(index<catalog.books[name].length-1)await key('ArrowRight');
  }
  await key('Escape');console.log('native DOM every page: '+name+' ('+catalog.books[name].length+')');
 }
 await writeFile('backup/dom-visual/book-crawl.json',JSON.stringify({audit,pages:receipts},null,2)+'\n');
 console.log('local native DOM test: real text/buttons/images, valid bounds and all '+receipts.length+' picture-book pages passed');
}finally{
 if(socket)socket.close();browser.kill('SIGTERM');
 await new Promise(resolve=>{if(browser.exitCode!==null)resolve();else browser.once('exit',resolve)});
 server.close();await rm(profile,{recursive:true,force:true,maxRetries:8,retryDelay:250});
}

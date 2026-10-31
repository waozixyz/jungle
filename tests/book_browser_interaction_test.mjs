import {bookIds,pageCounts,bookPosition} from './book_web_geometry.mjs';
// Private CDP scaffolding shared with paint_layers_web_test.mjs.
import {spawn} from 'node:child_process';
import {readFile,writeFile,mkdtemp,rm,mkdir} from 'node:fs/promises';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import {resolve,join,extname} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';

const root=resolve(process.env.JUNGLE_WEB_ROOT||'build/web'),page=process.env.JUNGLE_WEB_PAGE||'dom.html';
const inputs=['mouse','touch'];
await mkdir('work/w',{recursive:true});await mkdir('work/b',{recursive:true});await mkdir('backup/book-browser-controls',{recursive:true});
const vegetableCount=pageCounts[bookIds.indexOf('vegetables')];
const mime={'.html':'text/html','.js':'text/javascript','.wasm':'application/wasm','.json':'application/json','.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp','.wav':'audio/wav','.zip':'application/zip'};
const server=createServer(async(req,res)=>{
 try{let file=resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
  if(file!==root&&!file.startsWith(root+'/'))throw Error('path');if(file===root)file=join(root,'index.html');
  const data=await readFile(file);res.writeHead(200,{'Content-Type':mime[extname(file)]||'application/octet-stream'});res.end(data);
 }catch{res.writeHead(404);res.end()}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const env={...process.env,YUE_DESKTOP_RECOVERY:'0',TMPDIR:resolve('work/b')};
for(const k of ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','DBUS_SESSION_BUS_ADDRESS','SESSION_MANAGER'])delete env[k];
const menu=(await readFile('games/catalog.txt','utf8')).trim().split('\n').map(x=>x.split('|')).filter(x=>x[1]!=='123 Book').sort((a,b)=>Number(a[4])-Number(b[4]));
const bookIndex=menu.findIndex(x=>x[1]==='Picture Book');
if(bookIndex<0)throw Error('No Picture Book in this build');

async function run(input){
 const touch=input==='touch',profile=await mkdtemp(resolve('work/w/p-'));
 const browser=spawn(process.env.CHROMIUM||'chromium',['--headless','--no-sandbox','--disable-gpu','--disable-webgl','--disable-dev-shm-usage','--mute-audio','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{env,stdio:['ignore','ignore','pipe']});
 let socket,stderr='';const errors=[];
 browser.stderr.on('data',d=>stderr=(stderr+d).slice(-3000));
 const label=(page||'index.html')+' '+input;
 try{
  let port;const started=Date.now()+30000;
  while(Date.now()<started){try{port=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break}catch{}if((browser.exitCode!==null||browser.signalCode!==null))throw Error(stderr);await delay(100)}
  if(!port)throw Error('Private browser failed: '+stderr);
  const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
  socket=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);
  await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j});
  let sequence=0;const pending=new Map();
  socket.onmessage=e=>{const m=JSON.parse(e.data);if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails?.exception?.description||m.params.exceptionDetails?.text);if(m.method==='Runtime.consoleAPICalled'&&m.params.type==='error')errors.push(m.params.args.map(v=>v.value||v.description).join(' '));if(pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id)}};
  async function command(method,params={}){const id=++sequence;const p=new Promise(r=>pending.set(id,r));socket.send(JSON.stringify({id,method,params}));let timer;const reply=await Promise.race([p,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('CDP timeout '+method)),30000)})]).finally(()=>clearTimeout(timer));if(reply.error)throw Error(method+': '+JSON.stringify(reply.error));return reply.result}
  async function evaluate(expression){const result=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value}
  async function until(test,what,limit=20000){const end=Date.now()+limit;while(Date.now()<end){if(errors.length)throw Error(JSON.stringify(errors));if(await test())return;await delay(50)}throw Error(label+': '+what)}
  const frames=()=>delay(160);
  async function key(key,code=key){
   const vk=({Enter:13,' ':32,Escape:27,Home:36,ArrowDown:40,ArrowRight:39,F10:121})[key]||key.charCodeAt(0);
   await command('Input.dispatchKeyEvent',{type:'keyDown',key,code,windowsVirtualKeyCode:vk,...(key==='Enter'?{text:'\r'}:{})});await frames();
   await command('Input.dispatchKeyEvent',{type:'keyUp',key,code,windowsVirtualKeyCode:vk});await frames();
  }
  async function click(x,y,button='left',asTouch=touch){
   if(asTouch){await command('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});await frames();await command('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]})}
   else{await command('Input.dispatchMouseEvent',{type:'mouseMoved',x,y});await command('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button,buttons:({left:1,right:2,middle:4})[button],clickCount:1});await frames();await command('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button,buttons:0,clickCount:1})}
   await frames();
  }
  async function shot(name){await writeFile(`backup/book-browser-controls/${page}-${input}-${name}.png`,Buffer.from((await command('Page.captureScreenshot',{format:'png'})).data,'base64'))}
  const transport=async()=>createHash('sha1').update((await command('Page.captureScreenshot',{format:'png',clip:{x:460,y:625,width:80,height:25,scale:1}})).data).digest('hex');
  const voices=()=>evaluate('window.jungleTestVoices');
  const clear=()=>evaluate('window.jungleTestVoices=[]');
  const last=()=>evaluate('window.jungleTestVoices.at(-1)');
  async function spoken(what){await until(async()=>(await voices()).length>0,what);return last()}
  const screen=async()=>createHash('sha1').update((await command('Page.captureScreenshot',{format:'png',clip:{x:0,y:56,width:1280,height:560,scale:1}})).data).digest('hex');
  await command('Runtime.enable');await command('Page.enable');
  await command('Page.addScriptToEvaluateOnNewDocument',{source:'window.jungleTestVoices=[];Object.defineProperty(HTMLMediaElement.prototype,"junglePath",{get(){return this.dataset.junglePath},set(path){this.dataset.junglePath=path;window.jungleTestRequestedAudio=this}});const play=HTMLMediaElement.prototype.play;HTMLMediaElement.prototype.play=function(){window.jungleTestVoices.push(this.junglePath||this.src);return play.apply(this,arguments)}'});
  await command('Emulation.setDeviceMetricsOverride',{width:1280,height:675,deviceScaleFactor:1,mobile:false});
  if(touch)await command('Emulation.setTouchEmulationEnabled',{enabled:true,maxTouchPoints:1});
  await command('Page.navigate',{url:'http://127.0.0.1:'+server.address().port+'/'+page});
  await until(()=>evaluate('typeof Module!=="undefined"&&!!Module.FS&&document.getElementById("loading").style.display==="none"'),'startup',45000);
  console.log(label+': startup');await key('Home');for(let n=0;n<bookIndex;n++)await key('ArrowDown');await key('Enter');
  // Stall real canonical Ogg lookup at the existing logical voice boundary.
  // Only the newest manual turn may play when these requests are released.
  await evaluate(`(()=>{const original=soundBytes;let release;const released=new Promise(r=>release=r);window.held=[];let holding=true;soundBytes=async(path,current)=>{const index=await speech();if(!holding||!index.voices.has(path))return original(path,current);window.held.push(path);await released;return current()?original(path,current):null};window.releaseHeld=()=>{holding=false;release()}})()`);
  // Category shortcut is independent of the changing game/book catalog layout.
  await key('0','Digit0');await until(()=>evaluate('held.length>0'),'held opening narration');
  await key(' ','Space');await clear();
  await click(1150,400);await until(()=>evaluate('held.length>=2'),'held manual narration');
  const selected=await evaluate('held.at(-1)');await evaluate('releaseHeld()');
  const second=await spoken('paused manual turn narration');if(second!==selected)throw Error('Cancelled old voice replayed');
  await until(()=>evaluate('window.jungleTestRequestedAudio?.readyState>0 && window.jungleTestRequestedAudio.currentTime>0.05'),'canonical Ogg audio never decoded/advanced');
  await delay(7000);if((await voices()).length!==1)throw Error('Manual turn resumed autoplay or replayed cancelled narration');await shot('manual');
  const focused=await evaluate('document.activeElement?.getAttribute("aria-label")');
  if(!touch&&page==='dom.html'&&focused!=='Swipe to turn the page')throw Error('Mouse turn did not focus the page: '+focused);
  const pausedTransport=await transport();const secondPixels=await screen();await clear();await key(' ','Space');await frames();
  await shot('focused-space');
  if(await transport()===pausedTransport)throw Error('Focused Space did not change Play to Pause');
  console.log(label+': focused page style '+JSON.stringify(await evaluate(`(()=>{const e=document.activeElement,s=getComputedStyle(e),r=e.getBoundingClientRect();return {label:e.getAttribute('aria-label'),outline:s.outline,border:s.border,bounds:{x:r.x,y:r.y,w:r.width,h:r.height}}})()`)));
  if(await screen()!==secondPixels)throw Error('Focused Space changed the page');
  if((await voices()).some(p=>p!==second))throw Error('Focused Space turned backward: '+JSON.stringify(await voices()));
  await key(' ','Space');await clear();
  if(await transport()!==pausedTransport)throw Error('Focused Space did not restore Play');
  await delay(7000);
  if(await screen()!==secondPixels||(await voices()).length)throw Error('Focused Space failed to pause on the current page');
  await key('Enter');
  const third=await spoken('focused Enter narration');if(third===second)throw Error('Focused Enter did not advance');
  await delay(600);if((await voices()).length!==1)throw Error('Focused Enter activated more than once: '+JSON.stringify(await voices()));
  await clear();await click(90,400);if(await spoken('left-side turn')!==second)throw Error('Left turn did not restore second page');
  await clear();await click(780,637);if(await spoken('Hear word')!==second)throw Error('Hear word chose a different page');
  await clear();await key('F10');await click(1150,400);await delay(500);if((await voices()).length)throw Error('Muted turn played audio');
  await key('F10');await click(90,400);await spoken('unmuted narration');
  const beforeMiddle=await screen();await clear();await click(640,350,'middle',false);await delay(250);if((await voices()).length||await screen()!==beforeMiddle)throw Error('Middle click activated Book');
  await click(640,350,'right',false);await shot('shelf');const shelf=await screen();
  if(page==='dom.html'&&!await evaluate('[...document.querySelectorAll("[aria-label]")].some(e=>e.getAttribute("aria-label")==="Manage books")'))throw Error('Right click did not reach shelf');
  // Finish the current dynamic category with pointer turns while paused.
  await key('0','Digit0');await spoken('reopening');
  for(let n=0;n<vegetableCount;n++)await click(1150,400);
  await shot('end');const endPage=await screen();await click(1150,400);
  if(await screen()!==endPage)throw Error('Category did not reach its end page');
  await click(640,350,'right',false);
  if(await screen()!==shelf)throw Error('End Back did not restore shelf');
  // Ordinary Shelf/Manage controls must pass secondary input to the page too.
  await click(1000,597,'left',false);await shot('manage');
  if(await screen()===shelf)throw Error('Manage did not open');
  const manage=await screen();await click(1000,597,'middle',false);
  if(await screen()!==manage)throw Error('Middle click left Manage');
  await click(1000,597,'right',false);await shot('manage-back');
  if(await screen()!==shelf)throw Error('Secondary Back stayed in Manage');
  await click(1000,597,'right',false);await shot('home');
  if(await screen()===shelf)throw Error('Secondary Back stayed on Shelf');
  // Exercise new catalog pages through real selection and decoded narration.
  const menuScale=Math.min(1280/320,675/200);await click(Math.trunc((1280-320*menuScale)/2)+254*menuScale,54*menuScale);
  if(await evaluate('document.documentElement.lang')!=='es')throw Error('Spanish flag did not select es');
  await evaluate('document.activeElement?.blur()');await key('Home');for(let n=0;n<bookIndex;n++)await key('ArrowDown');await key('Enter');
  async function category(id){const {x,y,index}=bookPosition(id,1280,675);await click(x,y);await evaluate('document.activeElement?.blur()');for(let n=0;n<index;n++)await key('ArrowRight');await clear();await key('Enter');await spoken('category opening');await until(()=>evaluate('window.jungleTestRequestedAudio?.currentTime>0.05'),'decoded category opening '+id);await key(' ','Space')}
  async function expectVoice(fragment){await until(async()=>(await voices()).some(p=>p.includes(fragment)),fragment);await until(()=>evaluate('window.jungleTestRequestedAudio?.currentTime>0.05'),'decoded '+fragment)}
  await category('actions');
  const actions=['cooking','cleaning','reading','drawing','singing','washing_hands','brushing_teeth','watering_plants'];
  for(let n=0;n<actions.length;n++){if(n){await clear();await key('ArrowRight')}await expectVoice('/es/simple/'+actions[n]+'.wav');await shot('actions-'+n)}
  await key('Escape');await category('sports');for(let n=0;n<6;n++){await clear();await key('ArrowRight')}await expectVoice('/es/simple/badminton.wav');await shot('badminton');
  await key('Escape');await category('birds');await clear();await key('ArrowRight');await key('ArrowRight');await expectVoice('/es/simple/penguin.wav');await shot('pinguino');
  await key('Escape');await key('d');await category('birds');await clear();await key('ArrowRight');await key('ArrowRight');await expectVoice('/es/spelling/penguin.wav');await shot('pinguino-spelling');
  await key('Escape');await key('Escape');
  console.log('local Book '+label+': manual narration, focused keyboard, Hear word/mute, secondary hierarchy passed');
 }catch(error){
  if(socket?.readyState===WebSocket.OPEN){
   await mkdir('backup/book-browser-controls',{recursive:true});
   const id=Math.floor(Math.random()*1e8);socket.send(JSON.stringify({id,method:'Page.captureScreenshot',params:{format:'png'}}));
   const shot=await Promise.race([new Promise(r=>socket.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.id===id)r(m.result?.data)})),delay(3000)]);
   if(shot)await writeFile(`backup/book-browser-controls/book-failure-${(page||'index').replace('.html','')}-${input}.png`,Buffer.from(shot,'base64'));
  }
  throw error;
 }finally{
  if(socket)socket.close();browser.kill('SIGTERM');await new Promise(r=>{if((browser.exitCode!==null||browser.signalCode!==null))r();else browser.once('exit',r)});
  await rm(profile,{recursive:true,force:true,maxRetries:20,retryDelay:150});
 }
}

try{for(const input of inputs)await run(input)}finally{server.close()}

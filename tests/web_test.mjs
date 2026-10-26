// Private headless browser; never attaches to the owner's desktop/profile.
import {spawn} from 'node:child_process';
import {readFile,writeFile,mkdtemp,rm,mkdir} from 'node:fs/promises';
import {createServer} from 'node:http';
import {join,resolve,extname} from 'node:path';
import {tmpdir} from 'node:os';
import {setTimeout as delay} from 'node:timers/promises';
const root=resolve('build/web'),profile=await mkdtemp('/tmp/jungle-web-');
const mime={'.html':'text/html','.js':'text/javascript','.wasm':'application/wasm','.json':'application/json','.png':'image/png','.wav':'audio/wav'};
const server=createServer(async(req,res)=>{try{let file=resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));if(!file.startsWith(root+'/')&&file!==root)throw Error();if(file===root||file.endsWith('/'))file=join(file,'index.html');const data=await readFile(file);res.writeHead(200,{'Content-Type':mime[extname(file)]||'application/octet-stream'});res.end(data)}catch{res.writeHead(404);res.end()}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const url=process.argv[2]||'http://127.0.0.1:'+server.address().port;
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
 async function key(key,code=key){await command('Input.dispatchKeyEvent',{type:'keyDown',key,code,windowsVirtualKeyCode:key==='Enter'?13:key==='Escape'?27:key.startsWith('Arrow')?({ArrowLeft:37,ArrowUp:38,ArrowRight:39,ArrowDown:40}[key]):key.charCodeAt(0)});await delay(100);await command('Input.dispatchKeyEvent',{type:'keyUp',key,code});await delay(250)}
 async function click(x,y){const b=await evaluate('(()=>{let b=document.getElementById("canvas").getBoundingClientRect();return {x:b.x,y:b.y,w:b.width,h:b.height}})()');x=b.x+x*b.w/320;y=b.y+y*b.h/200;await command('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});await delay(80);await command('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',clickCount:1});await delay(400)}
 await command('Runtime.enable');await command('Page.enable');await command('Emulation.setDeviceMetricsOverride',{width:1280,height:800,deviceScaleFactor:1,mobile:false});await command('Page.navigate',{url});
 let ready=false;while(Date.now()<deadline){if(await evaluate('typeof Module!=="undefined"&&Module.FS&&document.getElementById("loading").style.display==="none"')){ready=true;break}if(diagnostics.length)throw Error(JSON.stringify(diagnostics));await delay(250)}
 if(!ready)throw Error('Browser startup timeout '+JSON.stringify(diagnostics)+' '+await evaluate('JSON.stringify({url:location.href,title:document.title,text:document.body?.innerText?.slice(0,500)})'));await delay(1000);
 await mkdir('build/tests/web',{recursive:true});
 const captures=new Map();
 async function shot(name){const r=await command('Page.captureScreenshot',{format:'png'});captures.set(name,r.result.data);await writeFile('build/tests/web/'+name+'.png',Buffer.from(r.result.data,'base64'));return r.result.data}
 async function pixelClick(x,y,touch=false){
  if(touch){await command('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});await delay(70);await command('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]})}
  else{await command('Input.dispatchMouseEvent',{type:'mouseMoved',x,y});await command('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});await delay(70);await command('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',clickCount:1})}
  await delay(250)
 }
 async function resize(width,height,mobile=false){await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile});await command('Emulation.setTouchEmulationEnabled',{enabled:mobile,maxTouchPoints:1});await delay(500);const box=await evaluate('({w:Module.canvas.clientWidth,h:Module.canvas.clientHeight})');if(box.w!==width||box.h!==height)throw Error('Canvas did not resize to the viewport '+JSON.stringify(box))}
 async function swipe(x,y,xx,yy){await command('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});for(let i=1;i<=6;i++){await delay(35);await command('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x+(xx-x)*i/6,y:y+(yy-y)*i/6}]})}await command('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await delay(350)}
 await shot('menu');
 holdAudio=true;await command('Fetch.enable',{patterns:[{urlPattern:'*.wav*',requestStage:'Request'}]});
 await key('1','Digit1');await shot('books');await key('0','Digit0');const first=await shot('vegetables-desktop');
 await pixelClick(1228,752);const second=await shot('vegetables-next');if(first===second)throw Error('Page navigation froze under stalled narration');
 await pixelClick(52,752);const restored=await command('Page.captureScreenshot',{format:'png'});if(restored.result.data!==first)throw Error('Back page failed under stalled narration');
 await resize(390,844,true);const phoneFirst=await shot('vegetables-phone');
 await pixelClick(350,808,true);const phoneSecond=await shot('vegetables-phone-next');if(phoneFirst===phoneSecond)throw Error('Touch Next failed');
 await swipe(320,350,45,350);const swiped=await shot('vegetables-phone-swipe');if(swiped===phoneSecond)throw Error('Touch swipe did not turn the page');
 await swipe(45,350,320,350);const swipedBack=await command('Page.captureScreenshot',{format:'png'});if(swipedBack.result.data!==phoneSecond)throw Error('Reverse touch swipe lost its page');
 holdAudio=false;for(const requestId of pausedAudio)await command('Fetch.continueRequest',{requestId});await command('Fetch.disable');
 await pixelClick(195,808,true);await shot('books-phone');
 await pixelClick(292,555,true);const fromCover=await shot('vegetables-cover-touch');await pixelClick(195,808,true);await key('0','Digit0');const directCover=await command('Page.captureScreenshot',{format:'png'});if(fromCover!==directCover.result.data)throw Error('Vegetables cover opened the wrong book');await pixelClick(195,808,true);
 await swipe(90,620,90,160);await shot('books-touch-scroll');
 for(const [w,h,mobile] of [[320,568,true],[844,390,true],[768,1024,true],[1920,1080,false],[390,844,true]]){await resize(w,h,mobile);await shot('shelf-'+w+'-'+h)}
 await pixelClick(36,808,true);await pixelClick(325,36,true);if(await evaluate('Module.FS.readFile("/kryon-apps/jungle/settings/language.txt",{encoding:"utf8"})')!=="es")throw Error('Spanish flag did not persist');
 await pixelClick(195,420,true);await shot('counting-phone');
 let counted=false;for(let n=1;n<=4;n++){
  await pixelClick(70,808,true);const index=n-1;await pixelClick(70+(index%3)*125,640+Math.floor(index/3)*56,true);await pixelClick(320,808,true);
  const count=await evaluate('(()=>{try{return Number(Module.FS.readFile("/kryon-apps/jungle/jungle.animals/progress.txt",{encoding:"utf8"}).trim().split(" ")[2])}catch{return 0}})()');if(count>0){counted=true;break}
 }if(!counted)throw Error('Counting touch keypad did not submit an answer');
 await pixelClick(42,34,true);await pixelClick(195,650,true);await shot('paint-phone');
 const legacy=async(x,y)=>pixelClick(x*390/320,(844-390*200/320)/2+y*390/320,true);
 await pixelClick(54,530,true);await legacy(52,58);await legacy(52,58);await legacy(280,90);await pixelClick(242,530,true);await legacy(10,36);
 if(await evaluate('document.activeElement.id')!=='mobile-input')throw Error('Story did not focus mobile text input');
 await command('Input.insertText',{text:'Niño, piña'});await delay(500);await shot('story-phone');await legacy(266,180);await pixelClick(54,602,true);await legacy(50,80);
 const story=await evaluate('Array.from(Module.FS.readFile("/kryon-apps/jungle/jungle.paint/slot-0.txt")).map(b=>String.fromCharCode(b)).join("")');if(!story.includes('Niño, piña'))throw Error('Mobile story lost accented text');
 await delay(1200);await command('Page.reload');await delay(500);const reloaded=Date.now()+30000;while(Date.now()<reloaded){if(await evaluate('typeof Module!=="undefined"&&Module.FS&&document.getElementById("loading").style.display==="none"'))break;await delay(200)}await delay(500);
 if(await evaluate('Module.FS.readFile("/kryon-apps/jungle/settings/language.txt",{encoding:"utf8"})')!=="es")throw Error('Language did not survive reload');
 if(diagnostics.length)throw Error(JSON.stringify(diagnostics));
 console.log('local browser test: responsive books, vegetables, stalled audio, mobile swipes, counting keypad and accented story saves passed at '+url);
}finally{if(socket)socket.close();browser.kill('SIGTERM');await new Promise(r=>{if(browser.exitCode!==null||browser.signalCode!==null)r();else browser.once('exit',r)});await new Promise(r=>server.close(r));await rm(profile,{recursive:true,force:true,maxRetries:20,retryDelay:100})}

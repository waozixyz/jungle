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
 await shot('menu');
 holdAudio=true;await command('Fetch.enable',{patterns:[{urlPattern:'*.wav*',requestStage:'Request'}]});
 await key('1','Digit1');await shot('books');await key('1','Digit1');const firstPage=await shot('first-page');
 await click(274,178);const secondPage=await shot('second-page');if(firstPage===secondPage)throw Error('Next click froze while audio was downloading');
 await click(45,178);const back=await command('Page.captureScreenshot',{format:'png'});if(back.result.data!==firstPage)throw Error('Back click did not restore the first page while audio was downloading');
 holdAudio=false;for(const requestId of pausedAudio)await command('Fetch.continueRequest',{requestId});await command('Fetch.disable');
 await key('Escape');
 await command('Input.dispatchMouseEvent',{type:'mouseMoved',x:640,y:400});await delay(100);await command('Input.dispatchMouseEvent',{type:'mouseWheel',x:640,y:400,deltaY:800,deltaX:0});await delay(500);await shot('scrolled-shelf');
 await click(225,123);const room=await shot('room-from-scroll');captures.delete('room-from-scroll');await key('Escape');await key('8','Digit8');const directRoom=await command('Page.captureScreenshot',{format:'png'});if(room!==directRoom.result.data)throw Error('Scrolled room card opened the wrong book');await key('Escape');
 for(let index=5;index<=9;index++){await key(String(index),'Digit'+index);await shot('book-'+index);await key('Escape')}
 await click(225,160);await key('2','Digit2');await shot('spelling');await key('Escape');await key('Escape');
 await click(155,51);if(await evaluate('Module.FS.readFile("/kryon-apps/jungle/settings/language.txt",{encoding:"utf8"})')!=="de")throw Error('German flag did not persist');
 await key('2','Digit2');await shot('counting');await key('Escape');
 await key('3','Digit3');await shot('paint');await click(32,14);await shot('scenes');
 await click(52,58);await shot('dinosaurs');await click(52,58);await click(280,90);
 await click(30,65);
 for(const text of 'Grüße'){await command('Input.dispatchKeyEvent',{type:'char',key:text,text,unmodifiedText:text});await delay(90)}
 await shot('story');await key('Enter');await click(30,110);await click(50,80);
 const story=await evaluate('Array.from(Module.FS.readFile("/kryon-apps/jungle/jungle.paint/slot-0.txt")).map(b=>String.fromCharCode(b)).join("")');
 if(!story.includes('Grüße'))throw Error('Browser save lost the accented story');
 await delay(1200);await command('Page.reload');await delay(500);
 const reloaded=Date.now()+30000;while(Date.now()<reloaded){if(await evaluate('typeof Module!=="undefined"&&Module.FS&&document.getElementById("loading").style.display==="none"'))break;await delay(200)}await delay(500);
 const saved=await evaluate('Module.FS.readFile("/kryon-apps/jungle/settings/language.txt",{encoding:"utf8"})');if(saved!=="de")throw Error('Language did not survive page reload');
 if(new Set(captures.values()).size!==captures.size)throw Error('A game route did not change the visible screen');
 if(diagnostics.length)throw Error(JSON.stringify(diagnostics));
 console.log('local browser test: website opened and all three game routes exercised at '+url);
}finally{if(socket)socket.close();browser.kill('SIGTERM');await new Promise(r=>{if(browser.exitCode!==null||browser.signalCode!==null)r();else browser.once('exit',r)});await new Promise(r=>server.close(r));await rm(profile,{recursive:true,force:true,maxRetries:20,retryDelay:100})}

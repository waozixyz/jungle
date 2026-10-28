// A private browser/profile exercises the real compiled game and IndexedDB.
import {spawn} from 'node:child_process';
import {readFile,writeFile,mkdtemp,rm,mkdir} from 'node:fs/promises';
import {createServer} from 'node:http';
import {resolve,join,extname} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';

const root=resolve(process.env.JUNGLE_WEB_ROOT||'build/web'),profile=await mkdtemp('/tmp/jungle-jigsaw-web-');
const mime={'.html':'text/html','.js':'text/javascript','.wasm':'application/wasm','.json':'application/json','.png':'image/png','.jpg':'image/jpeg','.wav':'audio/wav'};
const server=createServer(async(req,res)=>{
 try{let file=resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
  if(file!==root&&!file.startsWith(root+'/'))throw Error('path');if(file===root)file=join(root,'index.html');
  res.writeHead(200,{'Content-Type':mime[extname(file)]||'application/octet-stream'});res.end(await readFile(file));
 }catch{res.writeHead(404);res.end()}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const env={...process.env,YUE_DESKTOP_RECOVERY:'0',TMPDIR:'/tmp'};
for(const k of ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','DBUS_SESSION_BUS_ADDRESS','SESSION_MANAGER'])delete env[k];
const browser=spawn(process.env.CHROMIUM||'chromium',['--headless','--no-sandbox','--disable-gpu','--disable-webgl','--disable-dev-shm-usage','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{env,stdio:['ignore','ignore','pipe']});
let socket,stderr='',errors=[];
browser.stderr.on('data',d=>stderr=(stderr+d).slice(-3000));
try{
 let port;const until=Date.now()+30000;
 while(Date.now()<until){try{port=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break}catch{}if(browser.exitCode!==null)throw Error(stderr);await delay(100)}
 if(!port)throw Error('Private browser failed: '+stderr);
 const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
 socket=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);
 await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j});
 let sequence=0;const pending=new Map();
 socket.onmessage=e=>{const m=JSON.parse(e.data);if(m.method==='Runtime.exceptionThrown')errors.push(m.params);if(m.method==='Runtime.consoleAPICalled'&&m.params.type==='error')errors.push(m.params.args.map(v=>v.value||v.description));if(pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id)}};
 async function command(method,params={}){const id=++sequence;const p=new Promise(r=>pending.set(id,r));socket.send(JSON.stringify({id,method,params}));const reply=await p;if(reply.error)throw Error(JSON.stringify(reply.error));return reply.result}
 async function evaluate(expression){const result=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value}
 async function key(key){const code=key==='Enter'?13:key==='Escape'?27:key.charCodeAt(0);await command('Input.dispatchKeyEvent',{type:'keyDown',key,windowsVirtualKeyCode:code});await delay(90);await command('Input.dispatchKeyEvent',{type:'keyUp',key,windowsVirtualKeyCode:code});await delay(350)}
 async function click(x,y){await command('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});await delay(90);await command('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',clickCount:1});await delay(350)}
 async function ready(previousDocument=null,expectedFile=null){
  const end=Date.now()+45000;
  while(Date.now()<end){
   if(errors.length)throw Error(JSON.stringify(errors));
   const loaded=await evaluate('window.jungleTestDocument&&window.jungleTestDocument!=='+JSON.stringify(previousDocument)+'&&typeof Module!=="undefined"&&Module.FS&&document.getElementById("loading").style.display==="none"');
   if(loaded&&(!expectedFile||await evaluate('Module.FS.analyzePath('+JSON.stringify(expectedFile)+').exists')))return;
   await delay(150);
  }
  throw Error(expectedFile?'Reload did not restore the saved puzzle':'Startup timed out');
 }
 const savePath='/kryon-apps/jungle/jungle.jigsaw/puzzle.txt';
 async function saved(){return evaluate('Module.FS.readFile('+JSON.stringify(savePath)+',{encoding:"utf8"})')}
 function fields(text){return text.trim().split(/\s+/).map(v=>Number(v))}
 await command('Runtime.enable');await command('Page.enable');
 await command('Page.addScriptToEvaluateOnNewDocument',{source:'window.jungleTestDocument=crypto.randomUUID()'});
 await command('Emulation.setDeviceMetricsOverride',{width:960,height:600,deviceScaleFactor:1,mobile:false});
 await command('Page.navigate',{url:'http://127.0.0.1:'+server.address().port});await ready();
 // Wheel the age-ordered list to the 5+ coloring entry, with header fixed.
 await command('Input.dispatchMouseEvent',{type:'mouseWheel',x:500,y:350,deltaX:0,deltaY:900});await delay(500);
 await click(450,440);await key('Escape');
 await command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await delay(500);
 await key('3');await key('Enter');
 let values=fields(await saved());
 if(values[3]!==0)throw Error('Wrong initial piece count');
 const scale=Math.min(390/400,788/740,1.5),w=Math.trunc(390/scale),h=Math.trunc(788/scale);
 const size=Math.floor(Math.min(w-48,Math.trunc((h-180)*45/100))/2)*2,bx=(w-size)/2,by=80,tx=24,ty=by+size+24,tw=w-48,th=h-ty-96;
 const xy=(x,y)=>({x:x*scale,y:56+y*scale});
 for(let placed=0;placed<4;placed++){
  values=fields(await saved());const owners=values.slice(10,18).filter((_,i)=>i%2===0),order=values.slice(10,18).filter((_,i)=>i%2===1);
  const piece=order.findLast(p=>owners[p]===0),start=xy(16+(w-32)*values[18+piece*2]/10000,72+(h-144)*values[19+piece*2]/10000),end=xy(bx+(piece%2+.5)*size/2,by+(Math.floor(piece/2)+.5)*size/2);
  // Alternate finger drags with select-and-place taps.
  if(placed%2===0){
   await command('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[start]});
   for(let i=1;i<=6;i++){await delay(45);await command('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:start.x+(end.x-start.x)*i/6,y:start.y+(end.y-start.y)*i/6}]})}
   await command('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await delay(450);
  }else{await click(start.x,start.y);await click(end.x,end.y)}
  values=fields(await saved());if(values[10+piece*2]===0)throw Error('Browser placement failed: '+piece+' at '+placed);
 }
 await mkdir('build/tests/web',{recursive:true});
 await writeFile('build/tests/web/jigsaw-phone.png',Buffer.from((await command('Page.captureScreenshot',{format:'png'})).data,'base64'));
 await key('Escape');await key('Escape');
 await delay(1200);const before=await saved(),previousDocument=await evaluate('window.jungleTestDocument');await command('Page.reload');await ready(previousDocument,savePath);
 if(await saved()!==before)throw Error('Reload lost puzzle progress');
 await key('3');
 const picture=Math.min(w-48,Math.trunc(h*35/100)),resume=xy(w/2,108+picture+114+44+30+48+52+20);
 await click(resume.x,resume.y);
 await writeFile('build/tests/web/jigsaw-resumed.png',Buffer.from((await command('Page.captureScreenshot',{format:'png'})).data,'base64'));
 if(errors.length)throw Error(JSON.stringify(errors));
 console.log('local jigsaw browser test: real touch drags, taps, completion, IndexedDB reload and resume passed');
}finally{
 if(socket)socket.close();browser.kill('SIGTERM');await new Promise(r=>{if(browser.exitCode!==null)r();else browser.once('exit',r)});server.close();await rm(profile,{recursive:true,force:true});
}

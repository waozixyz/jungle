// A private browser and profile color a picture through the page's real mouse
// or touch input: two overlapping stencils dragged into place, a fill, the
// upper object erased without touching the one below or the paper, and Undo
// across hard reloads. Never attaches to the owner's desktop or profile.
import {spawn} from 'node:child_process';
import {readFile,writeFile,mkdtemp,rm,mkdir} from 'node:fs/promises';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import {resolve,join,extname} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';

await mkdir('work/w',{recursive:true});await mkdir('work/b',{recursive:true});
const root=resolve(process.env.JUNGLE_WEB_ROOT||'build/web'),page=process.env.JUNGLE_WEB_PAGE||'';
const inputs=(process.env.JUNGLE_PAINT_INPUT||'mouse,touch').split(',');
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
const paintIndex=menu.findIndex(x=>x[1]==='Coloring Book');
if(paintIndex<0)throw Error('No Coloring Book in this build');

const WORKING='/kryon-apps/jungle/jungle.paint/working.txt',HISTORY='/kryon-apps/jungle/jungle.paint/working-undo.txt';
const CODES='0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_',W=960,H=720,PAPER=15,CLEAR=255;
const TOOLS=['Image','Color','Story','Erase','Save','Print','Undo','New picture'];
// The saved picture: crayon, composed pixels, scene below the objects and
// the objects from the bottom up.
function picture(text){
 let at=0;
 const line=()=>{const end=text.indexOf('\n',at);if(end<0)throw Error('Bad picture line');const value=text.slice(at,end);at=end+1;return value};
 const header=line();if(header!=='JUNGLE PICTURE 2'&&header!=='JUNGLE PICTURE 3')throw Error('Bad picture header');
 const crayon=CODES.indexOf(line()[1]);for(let row=0;row<8;row++)line();
 const runs=count=>{
  const pixels=new Uint8Array(count);let used=0;
  while(used<count){
   const color=text[at]==='~'?CLEAR:CODES.indexOf(text[at]);at++;if(color<0)throw Error('Bad saved color');
   let length=0,shift=0,digit;
   do{digit=CODES.indexOf(text[at++]);if(digit<0||shift>30)throw Error('Bad saved run');length+=(digit&31)*2**shift;shift+=5}while(digit>=32);
   if(!length||used+length>count)throw Error('Bad saved run length');pixels.fill(color,used,used+length);used+=length;
  }
  if(text[at++]!=='\n')throw Error('Bad saved run end');return pixels;
 };
 const canvas=runs(W*H),objects=[];let base=canvas;
 if(header.endsWith('3')){
  base=runs(W*H);const count=Number(line());
  for(let n=0;n<count;n++){const [x,y,w,h]=line().split(' ').map(Number);objects.push({x,y,w,h,pixels:runs(w*h)})}
 }
 if(at!==text.length)throw Error('Trailing picture data');
 return {crayon,canvas,base,objects};
}
const digest=p=>{const hash=createHash('sha256').update(p.canvas).update(p.base);for(const o of p.objects)hash.update(`${o.x} ${o.y} ${o.w} ${o.h}\n`).update(o.pixels);return hash.digest('hex')};
// The object owning a pixel: the topmost one not clear there.
function ownerAt(p,x,y){for(let n=p.objects.length-1;n>=0;n--){const o=p.objects[n];if(x>=o.x&&y>=o.y&&x<o.x+o.w&&y<o.y+o.h&&o.pixels[(y-o.y)*o.w+x-o.x]!==CLEAR)return n}return -1}
// A pixel whose whole neighborhood passes, so the page's rounding cannot
// move a tap off it.
function find(test,left=0,top=0,right=W,bottom=H){
 for(let y=top+4;y<bottom-4;y++)for(let x=left+4;x<right-4;x++){
  let fits=true;for(let dy=-4;dy<=4&&fits;dy++)for(let dx=-4;dx<=4&&fits;dx++)fits=test(x+dx,y+dy);
  if(fits)return {x,y};
 }
 throw Error('No pixel fits');
}
// Paint's landscape layout in a 960 by 600 page whose title bar is 56 high.
const layout=(()=>{
 const width=960,height=544,pad=Math.min(20,Math.max(6,Math.floor(height/40))),gap=Math.min(10,Math.max(4,Math.floor(height/80)));
 const toolH=Math.floor((height-pad*2-gap*7)/8),toolW=Math.min(Math.floor(width/5),Math.max(64,Math.floor(toolH*5/2)));
 let cw=width-pad*3-toolW,ch=Math.floor(cw*3/4);if(ch>height-pad*2){ch=height-pad*2;cw=Math.floor(ch*4/3)}
 const left=Math.floor((width-toolW-pad-cw)/2),cx=left+toolW+pad,cy=pad+Math.floor((height-pad*2-ch)/2);
 const scale=Math.min(960/320,544/200),rx=Math.trunc((960-scale*320)/2),ry=56+Math.trunc((544-scale*200)/2);
 return {
  canvas:{x:cx,y:56+cy,w:cw,h:ch},
  toolWidth:toolW,toolHeight:toolH,
  point:(x,y)=>({x:cx+(x+0.5)*cw/W,y:56+cy+(y+0.5)*ch/H}),
  tool:index=>({x:left+toolW/2,y:56+cy+Math.floor((ch-toolH*8-gap*7)/2)+index*(toolH+gap)+toolH/2}),
  dialog:(x,y,w,h)=>({x:rx+(x+w/2)*scale,y:ry+(y+h/2)*scale})
 };
})();

async function run(input){
 const touch=input==='touch',profile=await mkdtemp(resolve('work/w/p-'));
 const browser=spawn(process.env.CHROMIUM||'chromium',['--headless','--no-sandbox','--disable-gpu','--disable-webgl','--disable-dev-shm-usage','--mute-audio','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{env,stdio:['ignore','ignore','pipe']});
 let socket,stderr='';const errors=[];let navigations=0;
 browser.stderr.on('data',d=>stderr=(stderr+d).slice(-3000));
 const label=(page||'index.html')+' '+input;
 try{
  let port;const started=Date.now()+30000;
  while(Date.now()<started){try{port=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break}catch{}if(browser.exitCode!==null)throw Error(stderr);await delay(100)}
  if(!port)throw Error('Private browser failed: '+stderr);
  const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
  socket=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);
  await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j});
  let sequence=0;const pending=new Map();
 socket.onmessage=e=>{const m=JSON.parse(e.data);if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails?.exception?.description||m.params.exceptionDetails?.text);if(m.method==='Runtime.consoleAPICalled'&&m.params.type==='error')errors.push(m.params.args.map(v=>v.value||v.description).join(' '));if(m.method==='Page.frameNavigated'&&!m.params.frame.parentId)navigations++;if(pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id)}};
  async function command(method,params={}){const id=++sequence;const p=new Promise(r=>pending.set(id,r));socket.send(JSON.stringify({id,method,params}));const reply=await p;if(reply.error)throw Error(method+': '+JSON.stringify(reply.error));return reply.result}
  async function evaluate(expression){const result=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value}
  async function until(test,what,limit=20000){const end=Date.now()+limit;while(Date.now()<end){if(errors.length)throw Error(JSON.stringify(errors));if(await test())return;await delay(50)}throw Error(label+': '+what)}
  // The app draws and reads input once per animation frame.
  const frames=count=>evaluate(`new Promise(r=>{let n=0;const f=()=>++n>=${count}?r():requestAnimationFrame(f);requestAnimationFrame(f)})`);
  const screen=async()=>createHash('sha1').update((await command('Page.captureScreenshot',{format:'png',clip:{x:0,y:56,width:960,height:544,scale:1}})).data).digest('hex');
  const area=async(point,size=20)=>createHash('sha1').update((await command('Page.captureScreenshot',{format:'png',clip:{x:point.x-size/2,y:point.y-size/2,width:size,height:size,scale:1}})).data).digest('hex');
  // The app's next screen: changed from before, then the same two frames on.
  async function settled(before,what){
   await until(async()=>{const now=await screen();if(now===before)return false;await frames(2);return now===await screen()},what);
   return screen();
  }
  const stable=what=>until(async()=>{const now=await screen();await frames(2);return now===await screen()},what);
 let paintSentinel=null;
 async function observe(what,action){
  if(!paintSentinel)throw Error(label+': no paint sentinel before '+what);
  const beforeNavigations=navigations,beforeDocument=await evaluate('window.jungleTestDocument');
  await evaluate(`(()=>{window.junglePaintWatch={frames:[],stop:false};
   const semantic=${dom},required=${JSON.stringify(TOOLS.slice(0,6).concat(TOOLS.slice(7)))},point=${JSON.stringify(layout.point(paintSentinel.x,paintSentinel.y))},controlPoints=${JSON.stringify(TOOLS.map((name,index)=>layout.tool(index)))},toolWidth=${layout.toolWidth},toolHeight=${layout.toolHeight};
   const sample=()=>{
    if(!window.junglePaintWatch||window.junglePaintWatch.stop)return;
    const root=document.querySelector('#kryon-dom-root'),labels=new Set([...(root?.querySelectorAll('[aria-label]')||[])].map(e=>e.getAttribute('aria-label')));
   let pictureLoaded=false,ink=false,kind=semantic?'image':'pixels',controls=false;
   if(semantic){
    const picture=root?.querySelector('[aria-label="Picture"]');
    if(picture){
     const box=picture.getBoundingClientRect();
     const image=[...document.images].find(element=>{
      const rect=element.getBoundingClientRect();
      return element.complete&&element.naturalWidth>0&&getComputedStyle(element).opacity>0&&rect.left<box.right&&rect.right>box.left&&rect.top<box.bottom&&rect.bottom>box.top&&rect.width&&rect.height;
     });
     pictureLoaded=!!image&&image.complete&&image.naturalWidth>0;
    }
    ink=pictureLoaded;controls=required.every(name=>labels.has(name));
   }
    const canvas=document.querySelector('#canvas-frame canvas');
    if(canvas&&!semantic){
     kind='pixels';const rect=canvas.getBoundingClientRect(),x=Math.floor((point.x-rect.left)*canvas.width/rect.width),y=Math.floor((point.y-rect.top)*canvas.height/rect.height),context=canvas.getContext('2d');
     const dark=at=>{
      const sx=canvas.width/rect.width,sy=canvas.height/rect.height;
      const left=Math.max(0,Math.ceil((at.x-toolWidth/2+3-rect.left)*sx)),top=Math.max(0,Math.ceil((at.y-toolHeight/2+3-rect.top)*sy));
      const width=Math.min(canvas.width-left,Math.floor((toolWidth-6)*sx)),height=Math.min(canvas.height-top,Math.floor((toolHeight-6)*sy));
      const pixels=context.getImageData(left,top,width,height).data;
      for(let i=0;i<pixels.length;i+=4)if(pixels[i+3]>0&&pixels[i]+pixels[i+1]+pixels[i+2]<450)return true;
      return false;
     };
     ink=false;
     for(let dy=-2;dy<=2&&!ink;dy++)for(let dx=-2;dx<=2&&!ink;dx++){
      const px=x+dx,py=y+dy;if(px<0||py<0||px>=canvas.width||py>=canvas.height)continue;
      const [red,green,blue,alpha]=context.getImageData(px,py,1,1).data;
      ink=alpha>0&&red+green+blue<300;
     }
     pictureLoaded=ink;controls=controlPoints.every(dark);
    }
    window.junglePaintWatch.frames.push({controls,picture:pictureLoaded,ink,kind});
    requestAnimationFrame(sample);
   };
   requestAnimationFrame(sample);
  })()`);
  try{await action()}finally{
   const observed=await evaluate(`(()=>{const watch=window.junglePaintWatch;watch.stop=true;const frames=watch.frames;window.junglePaintWatch=null;return frames})()`);
   const missing=observed.filter(frame=>!frame.controls||!frame.picture||!frame.ink);
   if(!observed.length)throw Error(label+': '+what+' observed no animation frames');
   if(missing.length)throw Error(label+': '+what+' disappeared in '+missing.length+'/'+observed.length+' frames '+JSON.stringify(missing.slice(0,4)));
   if(navigations!==beforeNavigations||await evaluate('window.jungleTestDocument')!==beforeDocument)throw Error(label+': '+what+' navigated or replaced the browser document');
  }
 }
  async function text(path,limit=0){return evaluate(`(()=>{if(!Module.FS.analyzePath(${JSON.stringify(path)}).exists)return null;const bytes=Module.FS.readFile(${JSON.stringify(path)});return new TextDecoder('latin1').decode(${limit?`bytes.subarray(0,${limit})`:'bytes'})})()`)}
  // A document as the page's database holds it for the next load.
  async function stored(path,limit=0){return evaluate(`new Promise((resolve,reject)=>{const open=indexedDB.open('/kryon-apps');open.onerror=()=>reject(open.error);open.onsuccess=()=>{const db=open.result;if(!db.objectStoreNames.contains('FILE_DATA')){db.close();resolve(null);return}const get=db.transaction('FILE_DATA').objectStore('FILE_DATA').get(${JSON.stringify(path)});get.onerror=()=>{db.close();reject(get.error)};get.onsuccess=()=>{db.close();const bytes=get.result?.contents;resolve(bytes?new TextDecoder('latin1').decode(${limit?`bytes.subarray(0,${limit})`:'bytes'}):null)}}})`)}
  const count=head=>head===null?-1:Number(head.split('\n')[2]);
  const steps=async()=>count(await text(HISTORY,96));
  async function saved(){const value=await text(WORKING);return value===null?null:picture(value)}
  // The picture and its history as saved, then as kept for a reload.
  async function persisted(want,length,what){
   await until(async()=>{const now=await saved();return now&&digest(now)===want&&await steps()===length},what+' was not saved');
   await until(async()=>{const now=await stored(WORKING);return now!==null&&digest(picture(now))===want&&count(await stored(HISTORY,96))===length},what+' was not stored');
  }
  async function press(point){
   if(touch)await command('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[point]});
   else{await command('Input.dispatchMouseEvent',{type:'mouseMoved',...point});await command('Input.dispatchMouseEvent',{type:'mousePressed',...point,button:'left',buttons:1,clickCount:1})}
   await frames(2);
  }
  async function move(point){
   if(touch)await command('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[point]});
   else await command('Input.dispatchMouseEvent',{type:'mouseMoved',...point,button:'left',buttons:1});
   await frames(1);
  }
  async function lift(point){
   if(touch)await command('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
   else await command('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'left',buttons:0,clickCount:1});
   await frames(2);
  }
  const tap=async point=>{await press(point);await lift(point)};
  let dom=false;
  // On the DOM page each target must be the labeled control the canvas
  // page draws at the same place.
  async function control(name,point){
   if(!dom)return point;
   await until(()=>evaluate(`[...document.querySelectorAll('#kryon-dom-root [aria-label]')].some(e=>{const r=e.getBoundingClientRect();return e.getAttribute('aria-label')===${JSON.stringify(name)}&&${point.x}>=r.left&&${point.x}<r.right&&${point.y}>=r.top&&${point.y}<r.bottom})`),'no '+name+' control at '+JSON.stringify(point));
   return point;
  }
  const toolLabels=()=>evaluate(`[...document.querySelectorAll('#kryon-dom-root button')].map(e=>e.getAttribute('aria-label')).filter(n=>${JSON.stringify(TOOLS.concat('Mirror'))}.includes(n))`);
  async function tool(index,name=TOOLS[index]){await tap(await control(name,layout.tool(index)))}
  async function key(name){
   const code={Home:36,ArrowDown:40,Enter:13,Escape:27}[name];await evaluate('document.activeElement?.blur()');
   await command('Input.dispatchKeyEvent',{type:'keyDown',key:name,windowsVirtualKeyCode:code});await frames(2);
   await command('Input.dispatchKeyEvent',{type:'keyUp',key:name,windowsVirtualKeyCode:code});await frames(4);
  }
  async function ready(previous=null){
   await until(()=>evaluate(`window.jungleTestDocument&&window.jungleTestDocument!==${JSON.stringify(previous)}&&typeof Module!=="undefined"&&!!Module.FS&&document.getElementById("loading").style.display==="none"`),'startup',45000);
  }
  async function openPaint(){
   await stable('the menu kept changing');
   const before=await screen();await key('Home');for(let n=0;n<paintIndex;n++)await key('ArrowDown');await key('Enter');
   await settled(before,'Coloring Book did not open');
   dom=await evaluate('!!document.querySelector("#kryon-dom-root button")');
   if(dom!==await evaluate('document.documentElement.dataset.backend==="dom"'))throw Error(label+': wrong renderer');
  }
  async function reload(){
   const previous=await evaluate('window.jungleTestDocument');
   await command('Page.reload',{ignoreCache:true});await ready(previous);await openPaint();
  }
  // A placement through the real picker, which a new scene opens itself: the
  // stencil starts in the upper left, follows the pointer while held and
  // lands where it is let go. A secondary mouse click during the drag
  // leaves the drag to the primary button and the stencil unmirrored.
 async function place(at,{picking=false,mirror=false,secondary=false,watch=false}={}){
   let before=await screen();
   if(!picking){await tool(0);before=await settled(before,'stencil picker')}
   // The picker keeps the last category, so choosing it again may change nothing.
   await tap(await control('Objects',layout.dialog(233,30,67,17)));await stable('Objects');before=await screen();
   await tap(await control('Crate',layout.dialog(20,51,90,56)));before=await settled(before,'size picker');
   await tap(await control('Small',layout.dialog(24,40,64,120)));await settled(before,'placement');
   if(dom){
    if((await toolLabels())[6]!=='Mirror')throw Error(label+': Undo is not Mirror while placing');
    const box=await evaluate(`(()=>{const r=document.querySelector('#kryon-dom-root [aria-label="Picture"]').getBoundingClientRect();return {x:r.left,y:r.top,w:r.width,h:r.height}})()`),want=layout.canvas;
    if(Math.abs(box.x-want.x)>1||Math.abs(box.y-want.y)>1||Math.abs(box.w-want.w)>1||Math.abs(box.h-want.h)>1)throw Error(label+': layout differs from the page '+JSON.stringify(box));
   }
   const stepsBefore=await steps(),pictureBefore=await saved();
   if(mirror){await tool(6,'Mirror');await frames(4);if(!touch){await tool(6,'Mirror');await frames(4)}}
   if(await steps()!==stepsBefore||digest(await saved())!==digest(pictureBefore))throw Error(label+': Mirror changed the picture');
   // The Small crate's size, grabbed inside its box.
   const grab={x:40,y:40},w=232,h=180,center=(x,y)=>layout.point(x+w/2,y+h/2);
   const from=center(0,0),to=center(at.x,at.y),oldFrom=await area(from),oldTo=await area(to);
   await press(layout.point(grab.x,grab.y));
   for(let step=1;step<=8;step++){
    const point=layout.point(grab.x+at.x*step/8,grab.y+at.y*step/8);await move(point);
    if(step===4&&secondary&&!touch){
     await command('Input.dispatchMouseEvent',{type:'mousePressed',...point,button:'right',buttons:3,clickCount:1});await frames(3);
     await command('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'right',buttons:1,clickCount:1});await frames(2);
    }
   }
   await until(async()=>await area(from)!==oldFrom&&await area(to)!==oldTo,'the stencil did not follow the drag');
   const drop=layout.point(grab.x+at.x,grab.y+at.y);
  const placeEdit=async()=>{
   if(mirror&&!touch){await command('Input.dispatchMouseEvent',{type:'mousePressed',...drop,button:'right',buttons:3,clickCount:1});await frames(3);await command('Input.dispatchMouseEvent',{type:'mouseReleased',...drop,button:'left',buttons:2,clickCount:1});await frames(3);await command('Input.dispatchMouseEvent',{type:'mouseReleased',...drop,button:'right',buttons:0,clickCount:1});await frames(2)}
   else await lift(drop);
   await until(async()=>(await saved()).objects.length===pictureBefore.objects.length+1&&await steps()===stepsBefore+1,'the stencil was not placed');
  };
  if(watch)await observe('stencil placement',placeEdit);else await placeEdit();
   const after=await saved(),object=after.objects.at(-1);
   if(Math.abs(object.x-at.x)>1||Math.abs(object.y-at.y)>1||object.w!==w||object.h!==h)throw Error(label+': stencil landed at '+object.x+','+object.y);
   if(dom&&(await toolLabels())[6]!=='Undo')throw Error(label+': Mirror stayed after placing');
   return after;
  }

  await command('Runtime.enable');await command('Page.enable');
  await command('Page.addScriptToEvaluateOnNewDocument',{source:'window.jungleTestDocuments=[];window.jungleTestDocument=crypto.randomUUID();window.jungleTestDocuments.push(window.jungleTestDocument)'});
  await command('Emulation.setDeviceMetricsOverride',{width:960,height:600,deviceScaleFactor:1,mobile:false});
  if(touch)await command('Emulation.setTouchEmulationEnabled',{enabled:true,maxTouchPoints:1});
  await command('Page.navigate',{url:'http://127.0.0.1:'+server.address().port+(page?'/'+page:'')});await ready();
  await openPaint();
  // A fresh picture: the first scene, which opens the stencil picker.
  const opening=await screen();
  await tap(await control('Scene 1',layout.dialog(20,30,90,64)));
  await until(async()=>(await saved())!==null&&await steps()===0,'the scene did not open');
  await settled(opening,'stencil picker');
  const blank=await saved();if(blank.objects.length)throw Error(label+': new scene has objects');
  paintSentinel=find((x,y)=>blank.base[y*W+x]===0,20,20,940,700);

  // Pagination describes a real destination, including after changing category.
  const galleryPages=async expected=>{
   if(!dom)return;
   const actual=await evaluate(`[...document.querySelectorAll('#kryon-dom-root button')].map(e=>e.getAttribute('aria-label')).filter(name=>name==='Previous'||name==='Next')`);
   if(JSON.stringify(actual)!==JSON.stringify(expected))throw Error(label+': stencil pagination '+JSON.stringify(actual)+' expected '+JSON.stringify(expected));
  };
  await galleryPages(['Next']);
  let gallery=await screen();
  await tap(await control('Next',layout.dialog(106,173,78,14)));
  await settled(gallery,'second dinosaur page');await galleryPages(['Previous']);
  gallery=await screen();
  await tap(await control('Previous',layout.dialog(22,173,78,14)));
  await settled(gallery,'first dinosaur page');await galleryPages(['Next']);
  for(const [name,x] of [['Animals',91],['People',162],['Objects',233]]){
   await tap(await control(name,layout.dialog(x,30,67,17)));
   await stable(name+' gallery');await galleryPages([]);
  }
  if(digest(await saved())!==digest(blank)||await steps()!==0)throw Error(label+': browsing stencils changed the picture');

  // Object A, then a fill on its own body.
  const a=await place({x:300,y:260},{picking:true,secondary:true}),A=a.objects[0];
  await observe('idle picture',()=>frames(6));
  const crate=A.pixels.slice(),mirrored=p=>p.map((v,i)=>p[Math.floor(i/A.w)*A.w+A.w-1-i%A.w]);
  if(mirrored(crate).every((v,i)=>v===crate[i]))throw Error(label+': the stencil looks the same mirrored');
  const fillAt=find((x,y)=>ownerAt(a,x,y)===0&&a.canvas[y*W+x]===PAPER,A.x,A.y,410,345);
  const color=16+a.crayon;let before=await steps();
  await observe('fill',async()=>{
   await tap(layout.point(fillAt.x,fillAt.y));
   await until(async()=>(await saved()).canvas[fillAt.y*W+fillAt.x]===color&&await steps()===before+1,'fill did not color the object');
  });
  const filled=await saved();
  for(let at=0;at<W*H;at++){
   if(filled.canvas[at]===a.canvas[at])continue;
   if(filled.canvas[at]!==color||ownerAt(a,at%W,Math.floor(at/W))!==0)throw Error(label+': fill left its object');
  }
  if(digest({...filled,objects:[]})===digest({...a,objects:[]})||filled.base.some((v,i)=>v!==a.base[i]))throw Error(label+': fill changed the scene below');

  // Object B overlaps A, mirrored by right held through the mouse drop,
  // or by the toolbar with touch. Mouse also toggles the toolbar twice.
  const b=await place({x:416,y:350},{mirror:true,watch:true}),B=b.objects[1];
  // Mirror flips B, so A, the same stencil the other way, was not left
  // mirrored by the secondary click during its drag.
  const flipped=mirrored(crate);
  if(b.objects.length!==2||B.pixels.some((v,i)=>v!==flipped[i]))throw Error(label+': Mirror did not flip the stencil');
  if(b.objects[0].pixels.some((v,i)=>v!==filled.objects[0].pixels[i]))throw Error(label+': placing over an object changed it');

  // The eraser removes only the upper object where they overlap.
  const eraseAt=find((x,y)=>ownerAt(b,x,y)===1&&A.pixels[(y-A.y)*A.w+x-A.x]!==CLEAR,B.x,B.y,A.x+A.w,A.y+A.h);
  const emptyAt=find((x,y)=>ownerAt(b,x,y)<0,700,20,950,240);
  before=await steps();await tool(3);
  await observe('erase',async()=>{
   await tap(layout.point(eraseAt.x,eraseAt.y));
   await until(async()=>(await saved()).objects.length===1&&await steps()===before+1,'the upper object was not erased');
  });
  const erased=await saved();
  if(digest(erased)!==digest(filled))throw Error(label+': erasing the upper object changed the object below or the paper');
  // An eraser tap on bare paper changes nothing and keeps no step.
  await tap(layout.point(emptyAt.x,emptyAt.y));await frames(12);
  if(digest(await saved())!==digest(erased)||await steps()!==before+1)throw Error(label+': erasing bare paper changed the picture');
  await observe('erase persistence',()=>persisted(digest(erased),4,'the erased picture'));

  // Re-entering the compiled game in the same document must recreate its
  // picture resource and preserve the existing history without a page reload.
  await key('Escape');await stable('return to menu');await openPaint();await frames(16);
  await observe('same-document reopen',async()=>{
   await persisted(digest(erased),4,'the reopened picture');await frames(6);
  });

  // After a hard reload Undo brings the erased object back.
  await reload();
  await observe('history restore and Undo',async()=>{
   await persisted(digest(erased),4,'the reloaded picture');
   if(dom&&JSON.stringify(await toolLabels())!==JSON.stringify(TOOLS))throw Error(label+': reloaded toolbar '+JSON.stringify(await toolLabels()));
   // History records are checked one frame at a time while the page stays open.
   await tool(6);
   await until(async()=>digest(await saved())===digest(b)&&await steps()===3,'Undo after reload did not restore the erased object');
   await persisted(digest(b),3,'the undone picture');
  });

  // The step Undo used stays used after another reload; the rest remain.
  await reload();
  await observe('second history restore',()=>persisted(digest(b),3,'the picture after a second reload'));
  for(const [want,remaining,what] of [[filled,2,'the second object'],[a,1,'the fill'],[blank,0,'the first object']]){
   await observe('Undo '+what,async()=>{
    await tool(6);
    await until(async()=>digest(await saved())===digest(want)&&await steps()===remaining,'Undo did not remove '+what);
   });
  }
  // With no history left Undo and an eraser tap on paper change nothing.
  const done=digest(await saved());
  await tool(6);await frames(12);
  await tool(3);await tap(layout.point(emptyAt.x,emptyAt.y));await frames(12);
  if(digest(await saved())!==done||await steps()!==0)throw Error(label+': an empty Undo or erase changed the picture');
  await persisted(done,0,'the restored scene');
  if(errors.length)throw Error(JSON.stringify(errors));
  console.log(`local paint layers ${label}: dragged placement with preview,${touch?'':' secondary click while dragging,'} Mirror, fill, overlap erase, empty erase, Undo after two hard reloads and exhausted Undo passed`);
 }catch(error){
  if(socket?.readyState===WebSocket.OPEN){
   await mkdir('build/tests/web',{recursive:true});
   const id=Math.random();socket.send(JSON.stringify({id,method:'Page.captureScreenshot',params:{format:'png'}}));
   const shot=await Promise.race([new Promise(r=>socket.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.id===id)r(m.result?.data)})),delay(3000)]);
   if(shot)await writeFile(`build/tests/web/paint-layers-failure-${(page||'index').replace('.html','')}-${input}.png`,Buffer.from(shot,'base64'));
  }
  throw error;
 }finally{
  if(socket)socket.close();browser.kill('SIGTERM');await new Promise(r=>{if(browser.exitCode!==null)r();else browser.once('exit',r)});
  await rm(profile,{recursive:true,force:true,maxRetries:20,retryDelay:150});
 }
}

try{for(const input of inputs)await run(input)}finally{server.close()}

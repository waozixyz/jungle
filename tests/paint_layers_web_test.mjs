// A private browser and profile color a picture through the page's real mouse
// or touch input: two overlapping stencils dragged into place, a fill, the
// upper object erased without touching the one below or the paper, and Undo
// across hard reloads. Never attaches to the owner's desktop or profile.
import {spawn} from 'node:child_process';
import {readFile,writeFile,mkdtemp,rm,mkdir,open} from 'node:fs/promises';
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
const TOOLS=['Image','Color','Story','Erase','Gallery','Print','Undo','New picture','Select'];
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
// Actual AppBounds pixels for the responsive stencil picker only.
function stencilLayout(width=960,totalHeight=600){
 const height=totalHeight-56,pad=height<440?8:16,gap=height<440?6:10,cols=width<600?2:3,tabCols=width<600?2:4;
 const tabY=pad+30+gap,tabW=Math.floor((width-pad*2-gap*(tabCols-1))/tabCols),gridY=tabY+4/tabCols*(44+gap),footerY=height-pad-44;
 const cardW=Math.floor((width-pad*2-gap*(cols-1))/cols),cardH=Math.floor((footerY-gap-gridY-gap*(6/cols-1))/(6/cols)),footerW=Math.floor((width-pad*2-gap*2)/3);
 const center=(x,y,w,h)=>({x:x+w/2,y:56+y+h/2});
 return {category:i=>center(pad+i%tabCols*(tabW+gap),tabY+Math.floor(i/tabCols)*(44+gap),tabW,44),
  tile:i=>center(pad+i%cols*(cardW+gap),gridY+Math.floor(i/cols)*(cardH+gap),cardW,cardH),
  next:center(width-pad-footerW,footerY,footerW,44),previous:center(pad,footerY,footerW,44)};
}
const stencil=stencilLayout();
// Main's toolbar changes to three columns below the picture in portrait,
// and two columns on short landscape screens. Match native LayoutMain.
function toolbarPoint(index,width,totalHeight){
 const height=totalHeight-56,pad=Math.max(6,Math.min(20,Math.floor(Math.min(width,height)/40))),gap=Math.max(4,Math.min(10,Math.floor(Math.min(width,height)/80)));
 let tw,th,columns,left,top;
 if(height>width){
  columns=3;left=pad;tw=Math.floor((width-pad*2-gap*2)/3);th=Math.max(44,Math.min(110,Math.floor(tw*3/4)));
  let cw=width-pad*2,ch=Math.floor(cw*3/4);const room=height-pad*3-gap*2-th*3;
  if(ch>room){ch=room;cw=Math.floor(room*4/3)}
  const below=pad+ch+pad;
  top=below+Math.floor((height-pad-below-th*3-gap*2)/2);
 }else{
  columns=height<440?2:1;const rows=columns===2?5:9;
  th=Math.floor((height-pad*2-gap*(rows-1))/rows);tw=Math.max(64,Math.min(Math.floor(th*5/2),Math.floor(width/(columns===2?8:5))));
  const rail=tw*columns+gap*(columns-1),room=height-pad*2;
  let cw=width-pad*3-rail,ch=Math.floor(cw*3/4);
  if(ch>room){ch=room;cw=Math.floor(room*4/3)}
  left=Math.floor((width-rail-pad-cw)/2);
  const cy=pad+Math.floor((room-ch)/2);
  top=cy+Math.floor((ch-th*rows-gap*(rows-1))/2);
 }
 return {x:left+index%columns*(tw+gap)+tw/2,y:56+top+Math.floor(index/columns)*(th+gap)+th/2};
}
// Paint's landscape layout in a 960 by 600 page whose title bar is 56 high.
const layout=(()=>{
 const width=960,height=544,pad=Math.min(20,Math.max(6,Math.floor(height/40))),gap=Math.min(10,Math.max(4,Math.floor(height/80)));
 const toolH=Math.floor((height-pad*2-gap*8)/9),toolW=Math.min(Math.floor(width/5),Math.max(64,Math.floor(toolH*5/2)));
 let cw=width-pad*3-toolW,ch=Math.floor(cw*3/4);if(ch>height-pad*2){ch=height-pad*2;cw=Math.floor(ch*4/3)}
 const left=Math.floor((width-toolW-pad-cw)/2),cx=left+toolW+pad,cy=pad+Math.floor((height-pad*2-ch)/2);
 const scale=Math.min(960/320,544/200),rx=Math.trunc((960-scale*320)/2),ry=56+Math.trunc((544-scale*200)/2);
 return {
  canvas:{x:cx,y:56+cy,w:cw,h:ch},
  toolWidth:toolW,toolHeight:toolH,
  point:(x,y)=>({x:cx+(x+0.5)*cw/W,y:56+cy+(y+0.5)*ch/H}),
  tool:index=>({x:left+toolW/2,y:56+cy+Math.floor((ch-toolH*9-gap*8)/2)+index*(toolH+gap)+toolH/2}),
  dialog:(x,y,w,h)=>({x:rx+(x+w/2)*scale,y:ry+(y+h/2)*scale})
 };
})();

// Only the small dimension header is needed, never the embedded mask bodies.
const dimensionsFile=await open('games/paint/paint_pages.zi','r'),dimensionBytes=Buffer.alloc(4096);
await dimensionsFile.read(dimensionBytes,0,4096,0);await dimensionsFile.close();
const dimensions=name=>dimensionBytes.toString().match(new RegExp(name+':[^=]+=[^\\[]*\\[([^\\]]+)'))[1].split(',').map(Number);
const stencilWidths=dimensions('DINO_WIDTH'),stencilHeights=dimensions('DINO_HEIGHT');
function sceneFirst(index=0,width=960,total=600){
 const h=total-56,fit=Math.max(1000,Math.min(Math.floor(width*1000/320),Math.floor(h*1000/200)));
 let p=Math.floor(14*fit/1000)+12;
 if(width-2*p>1040)p=Math.floor((width-1040)/2);
 const top=Math.floor(12*fit/1000)+12,g=h<440?6:10,c=width-2*p<600?2:3,rows=6/c;
 const gy=top+30+g+44+g,fy=h-top-44,cw=Math.floor((width-2*p-g*(c-1))/c);
 const ch=Math.max(80,Math.min(220,Math.floor((fy-g-gy-g*(rows-1))/rows)));
 return {x:p+index%c*(cw+g)+cw/2,y:56+gy+Math.floor(index/c)*(ch+g)+ch/2}
}

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
  async function tool(index,name=TOOLS[index]){
   const size=await evaluate('({width:innerWidth,height:innerHeight})');
   await tap(await control(name,toolbarPoint(index,size.width,size.height)));
  }
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
   const selection=await evaluate(`({editor:getComputedStyle(document.querySelector('#mobile-input')).userSelect,
    labels:[...document.querySelectorAll('#kryon-dom-paint span,#kryon-dom-root button,#loading p')].filter(e=>e.textContent).map(e=>getComputedStyle(e).userSelect)})`);
   if(selection.editor!=='text'||selection.labels.some(value=>value!=='none'))throw Error(label+': accidental label selection or blocked editor '+JSON.stringify(selection));
  }
  async function reload(){
   const previous=await evaluate('window.jungleTestDocument');
   await command('Page.reload',{ignoreCache:true});await ready(previous);await openPaint();
  }
  const pendingButton=place=>{const c=layout.canvas,bw=Math.min(140,Math.max(44,Math.floor((c.w-18)/2))),x=c.x+Math.floor((c.w-bw*2-6)/2);return {x:x+(place?bw+6:0)+bw/2,y:c.y+c.h-26}};
  async function resizePending(index,target,{exact=true}={}){
   const values=(await text('/kryon-apps/jungle/jungle.paint/choices.txt')).split('\n')[1];
   const width=stencilWidths[index*4+CODES.indexOf(values[3])-1],fullW=stencilWidths[index*4+3],fullH=stencilHeights[index*4+3],c=layout.canvas;
   if(width===target)return;
   // PlacementView uses the bounds' center (half a pixel for odd dimensions)
   // and an integer handle. Choose an integer pointer endpoint in the middle
   // of the target width's truncation interval, not on its rounding boundary.
   const height=Math.ceil(width*fullH/fullW-.0001);
   const center={x:c.x+(480+width%2/2)*c.w/W,y:c.y+(360+height%2/2)*c.h/H};
   const corner={x:Math.floor(Math.max(c.x+22,Math.min(c.x+c.w-22,center.x+width*c.w/W/2))),y:Math.floor(Math.max(c.y+22,Math.min(c.y+c.h-74,center.y+width*fullH/fullW*c.h/H/2)))};
   const distance=Math.hypot(corner.x-center.x,corner.y-center.y),ratio=(target+.5)/width;
   const goal={x:center.x+(corner.x-center.x)*ratio,y:center.y+(corner.y-center.y)*ratio};
   let end,score=Infinity;
   for(let dy=-4;dy<=4;dy++)for(let dx=-4;dx<=4;dx++){
    const point={x:Math.round(goal.x)+dx,y:Math.round(goal.y)+dy};
    const resized=width*Math.hypot(point.x-center.x,point.y-center.y)/distance;
    if((!exact||Math.floor(resized)===target)&&Math.abs(resized-target-.5)<score){end=point;score=Math.abs(resized-target-.5)}
   }
   if(!end)throw Error(label+': no integer resize endpoint for width '+target);
   if(dom){
    await control('Resize stencil',corner);
    await evaluate('window.junglePaintPointerTrace=[]');
   }
   await press(corner);await move(end);await lift(end);await frames(4);
   if(dom)console.log(label+': resize pointer delivery '+JSON.stringify({index,width,target,corner,end,trace:await evaluate('window.junglePaintPointerTrace')}));
  }
  // Every pointer release keeps the new stencil outside the saved document.
  async function place(at,{picking=false,mirror=false,secondary=false,watch=false}={}){
   if(!picking){await tool(0);await stable('stencil picker')}
   await tap(await control('Objects',stencil.category(3)));await stable('Objects');
   await tap(await control('Crate',stencil.tile(0)));await stable('in-scene placement');
   await resizePending(24,232);
   const stepsBefore=await steps(),pictureBefore=await saved();
   const values=(await text('/kryon-apps/jungle/jungle.paint/choices.txt')).split('\n')[1];
   if(Boolean(CODES.indexOf(values[4]))!==mirror){await tool(6,'Mirror');await frames(4)}
   const w=232,h=Math.ceil(232*stencilHeights[24*4+3]/stencilWidths[24*4+3]-.0001),start=layout.point(480,360),drop=layout.point(at.x+Math.floor(w/2),at.y+Math.floor(h/2));
   await press(start);
   for(let step=1;step<=8;step++)await move({x:start.x+(drop.x-start.x)*step/8,y:start.y+(drop.y-start.y)*step/8});
   if(secondary&&!touch){await command('Input.dispatchMouseEvent',{type:'mousePressed',...drop,button:'right',buttons:3,clickCount:1});await frames(3);await command('Input.dispatchMouseEvent',{type:'mouseReleased',...drop,button:'right',buttons:1,clickCount:1})}
   if(await steps()!==stepsBefore||digest(await saved())!==digest(pictureBefore))throw Error(label+': preview changed the picture');
   const placeEdit=async()=>{
    await lift(drop);await frames(4);
    if(await steps()!==stepsBefore||digest(await saved())!==digest(pictureBefore))throw Error(label+': pointer release placed the stencil');
    await tap(await control('Place',pendingButton(true)));
    await until(async()=>(await saved()).objects.length===pictureBefore.objects.length+1&&await steps()===stepsBefore+1,'Place did not commit one stencil');
   };
   if(watch)await observe('stencil placement',placeEdit);else await placeEdit();
   const after=await saved(),object=after.objects.at(-1);
   if(Math.abs(object.x-at.x)>1||Math.abs(object.y-at.y)>1||object.w!==w||object.h!==h)throw Error(label+': stencil bounds '+JSON.stringify({x:object.x,y:object.y,w:object.w,h:object.h}));
   return after;
  }

  await command('Runtime.enable');await command('Page.enable');
  await command('Page.addScriptToEvaluateOnNewDocument',{source:`window.jungleTestDocuments=[];window.jungleTestDocument=crypto.randomUUID();window.jungleTestDocuments.push(window.jungleTestDocument);
   window.junglePaintPointerTrace=[];
   for(const type of ['mousedown','mousemove','mouseup','touchstart','touchmove','touchend'])document.addEventListener(type,event=>{
    const p=event.touches?.[0]||event.changedTouches?.[0]||event;
    junglePaintPointerTrace.push({type,x:p.clientX,y:p.clientY,buttons:event.buttons,label:event.target.closest?.('[aria-label]')?.getAttribute('aria-label')});
    if(junglePaintPointerTrace.length>16)junglePaintPointerTrace.shift();
   },true);`});
  await command('Emulation.setDeviceMetricsOverride',{width:960,height:600,deviceScaleFactor:1,mobile:false});
  if(touch)await command('Emulation.setTouchEmulationEnabled',{enabled:true,maxTouchPoints:1});
  await command('Page.navigate',{url:'http://127.0.0.1:'+server.address().port+(page?'/'+page:'')});await ready();
  await openPaint();
  // A fresh picture: the first scene, which opens the stencil picker.
  const opening=await screen();
  await tap(await control('Jungle clearing',sceneFirst()));
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
  // Real mouse/touch selection at phone and landscape sizes. DOM geometry is
  // read from the rendered controls; Canvas uses the same hit points and proves
  // each hit by the independently persisted stencil/category/page choices.
  const pickerChoices=()=>text('/kryon-apps/jungle/jungle.paint/choices.txt');
  for(const [n,[width,height]] of [[390,844],[400,756],[420,700],[844,390],[960,600]].entries()){
   await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await frames(8);
   const points=stencilLayout(width,height),category=n%4;
   await tap(await control(['Dinosaurs','Animals','People','Objects'][category],points.category(category)));await frames(4);
   if(dom){
    const boxes=await evaluate(`[...document.querySelectorAll('#kryon-dom-root button')].map(e=>{const r=e.getBoundingClientRect();return {name:e.getAttribute('aria-label'),x:r.x,y:r.y,w:r.width,h:r.height}}).filter(r=>r.y>=56)`);
    if(boxes.length!==11)throw Error(label+': missing responsive picker controls '+JSON.stringify(boxes));
    for(const [i,r] of boxes.entries()){
     if(r.w<44||r.h<44||r.x<0||r.y<56||r.x+r.w>width+1||r.y+r.h>height+1)throw Error(label+': mobile control bounds '+JSON.stringify(r));
     for(const b of boxes.slice(i+1))if(r.x<b.x+b.w&&b.x<r.x+r.w&&r.y<b.y+b.h&&b.y<r.y+r.h)throw Error(label+': overlapping mobile controls');
    }
   }
   for(let page=0;page<(category===0?2:1);page++){await tap(await control('Next',points.next));await frames(4)}
   await galleryPages(['Previous']);
   const partial=await pickerChoices();
   await tap(points.next);await tap(points.tile(5));await frames(4);
   if(await pickerChoices()!==partial)throw Error(label+': nonexistent destination/item changed choices');
   await tap(points.tile(3));await frames(4);
   const selected=await pickerChoices(),values=selected?.split('\n')[1];
   if(CODES.indexOf(values?.[0])!==[34,38,42,46][category]||CODES.indexOf(values?.[1])!==category||CODES.indexOf(values?.[2])!==(category===0?2:1))throw Error(label+': mobile partial-page selection failed '+JSON.stringify({width,height,category,values}));
   await key('Escape');await tool(0);await stable('reopened stencil picker');
   const wide=width<600?960:390,tall=width<600?600:844;
   await command('Emulation.setDeviceMetricsOverride',{width:wide,height:tall,deviceScaleFactor:1,mobile:false});await frames(8);
   if(await pickerChoices()!==selected)throw Error(label+': resize changed selected stencil/page');
   await tap(stencilLayout(wide,tall).tile(3));await frames(4);
   if(await pickerChoices()!==selected)throw Error(label+': resized tile selected another stencil');
   await key('Escape');await tool(0);await stable('same stencil page');
  }
  await command('Emulation.setDeviceMetricsOverride',{width:960,height:600,deviceScaleFactor:1,mobile:false});await frames(8);
  await tap(await control('Dinosaurs',stencil.category(0)));await frames(4);
  if(digest(await saved())!==digest(blank)||await steps()!==0)throw Error(label+': responsive browsing changed picture');
  await galleryPages(['Next']);
  let gallery=await screen();
  await tap(await control('Next',stencil.next));
  await settled(gallery,'second dinosaur page');await galleryPages(['Previous','Next']);
  gallery=await screen();
  await tap(await control('Next',stencil.next));
  await settled(gallery,'last dinosaur page');await galleryPages(['Previous']);
  gallery=await screen();
  await tap(await control('Previous',stencil.previous));
  await settled(gallery,'middle dinosaur page');
  gallery=await screen();
  await tap(await control('Previous',stencil.previous));
  await settled(gallery,'first dinosaur page');await galleryPages(['Next']);
  for(const [name,index] of [['Animals',1],['People',2],['Objects',3]]){
   await tap(await control(name,stencil.category(index)));
   await stable(name+' gallery');await galleryPages(['Next']);
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

  // Select is a no-op; dragging the above-center handle rotates freely.
  const rotateAt=find((x,y)=>ownerAt(b,x,y)===1,B.x,B.y,B.x+B.w,B.y+B.h);
  const bareAt=find((x,y)=>ownerAt(b,x,y)<0,700,20,950,240);
  await tool(8);await tap(layout.point(bareAt.x,bareAt.y));await frames(12);
  if(digest(await saved())!==digest(b)||await steps()!==3)throw Error(label+': selecting bare paper changed the picture');
  await tap(layout.point(rotateAt.x,rotateAt.y));await frames(10);
  if(digest(await saved())!==digest(b)||await steps()!==3)throw Error(label+': selecting an object changed its pixels or Undo');
  let lx=B.w,ly=B.h,rx=0,by=0;
  for(let y=0;y<B.h;y++)for(let x=0;x<B.w;x++)if(B.pixels[y*B.w+x]!==CLEAR){lx=Math.min(lx,x);ly=Math.min(ly,y);rx=Math.max(rx,x+1);by=Math.max(by,y+1)}
  const bounds={x:B.x+lx,y:B.y+ly,w:rx-lx,h:by-ly};
  const sx=layout.canvas.w/W,sy=layout.canvas.h/H;
  const center={x:layout.canvas.x+(bounds.x+bounds.w/2)*sx,y:layout.canvas.y+(bounds.y+bounds.h/2)*sy};
  const handle={x:center.x,y:Math.max(68,layout.canvas.y+bounds.y*sy-24)},radius=center.y-handle.y;
  await observe('free rotate preview and release',async()=>{
   await press(handle);
   for(let n=1;n<=8;n++){
    const angle=37*n/8*Math.PI/180;
    await move({x:center.x+radius*Math.sin(angle),y:center.y-radius*Math.cos(angle)});
    if(digest(await saved())!==digest(b)||await steps()!==3)throw Error(label+': held preview changed saved pixels or Undo');
   }
   const angle=37*Math.PI/180;
   await lift({x:center.x+radius*Math.sin(angle),y:center.y-radius*Math.cos(angle)});
   await until(async()=>digest(await saved())!==digest(b)&&await steps()===4,'Handle release did not rotate the selected object');
  });
  const rotated=await saved(),R=rotated.objects[1];
  const theta=37*Math.PI/180,expectedW=bounds.w*Math.cos(theta)+bounds.h*Math.sin(theta),expectedH=bounds.w*Math.sin(theta)+bounds.h*Math.cos(theta);
  if(Math.abs(R.w-expectedW)>4||Math.abs(R.h-expectedH)>4||R.w===B.h&&R.h===B.w)throw Error(label+': free rotation snapped or warped its bounds');
  if(rotated.base.some((v,i)=>v!==b.base[i])||rotated.objects[0].pixels.some((v,i)=>v!==b.objects[0].pixels[i]))throw Error(label+': free rotation changed another layer');
  if(!R.pixels.includes(CLEAR)||R.pixels.some(value=>value!==CLEAR&&!B.pixels.includes(value)))throw Error(label+': rotation lost alpha or invented paint colors');
  await persisted(digest(rotated),4,'the rotated picture');await reload();
  await persisted(digest(rotated),4,'rotation after reload');await tool(6);
  await until(async()=>digest(await saved())===digest(b)&&await steps()===3,'Undo did not restore the rotated object');

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

  const namespace='/kryon-apps/jungle/jungle.paint/';
  const galleryIndex=async()=>{
   const raw=await text(namespace+'gallery.txt');if(!raw)return null;
   const lines=raw.trimEnd().split('\n');
   if(lines[0]!=='JUNGLE GALLERY1')throw Error('Bad gallery header');
   const [count,next,selected]=lines[1].split(' ').map(Number);
   const files=lines.slice(2).map(row=>row.slice(row.indexOf(' ')+1));
   if(files.length!==count)throw Error('Bad gallery count');return {raw,count,next,selected,files};
  };
  await until(async()=>(await galleryIndex())?.count===1,'autosave did not create a gallery picture');
  const originalGallery=await galleryIndex(),firstFile=originalGallery.files[0],firstBytes=await text(namespace+firstFile);
  if(digest(picture(firstBytes))!==done)throw Error(label+': gallery did not update the active picture');
  await tool(4);await stable('gallery previews');
  await tap(await control('Save a copy',layout.dialog(20,29,176,18)));
  await until(async()=>(await galleryIndex())?.count===2,'gallery copy was not saved');
  const copyGallery=await galleryIndex(),copyFile=copyGallery.files[1],copyBytes=await text(namespace+copyFile);
  if(copyBytes!==firstBytes||copyFile===firstFile)throw Error(label+': copy replaced the original');
  await until(async()=>await stored(namespace+'gallery.txt')===(await galleryIndex()).raw,'gallery index was not stored');
  await key('Escape');await stable('leave gallery');
  await tool(7);await stable('New confirmation');
  await tap(await control('Yes',layout.dialog(40,50,80,120)));await stable('scene categories');
  await tap(await control('Waterfall',sceneFirst(1)));
  await until(async()=>(await galleryIndex())?.count===3,'New picture did not create a new gallery entry');
  await key('Escape');await stable('new scene');
  const newPicture=await saved();if(digest(newPicture)===done)throw Error(label+': new scene did not open');
  if(await text(namespace+firstFile)!==firstBytes||await text(namespace+copyFile)!==copyBytes)throw Error(label+': New overwrote previous gallery pictures');
  await tool(4);await stable('three gallery previews');
  await tap(await control('Picture 1',layout.dialog(20,51,90,56)));
  await persisted(done,0,'picture reopened from gallery');
  if((await galleryIndex()).count!==3)throw Error(label+': opening a gallery picture duplicated it');

  // A category's second page, selected stencil, size and mirror choice survive
  // reload independently of the saved picture and its background.
  await tool(0);await stable('remembered stencil picker');
  await tap(await control('Objects',stencil.category(3)));await stable('Objects');
  await tap(await control('Next',stencil.next));await stable('new object stencils');
  await tap(await control('Ball',stencil.tile(0)));await stable('Ball placement');
  // This case checks the remembered Huge preset; no object is committed.
  await resizePending(42,stencilWidths[42*4+3],{exact:false});
  await tool(6,'Mirror');await frames(8);
  const choiceFile=namespace+'choices.txt',choices=await text(choiceFile),values=choices?.split('\n')[1];
  if(!values||CODES.indexOf(values[0])!==43||CODES.indexOf(values[1])!==3||CODES.indexOf(values[2])!==1||CODES.indexOf(values[3])!==4)throw Error(label+': stencil choices were not saved');
  await until(async()=>await stored(choiceFile)===choices,'stencil choices were not stored');
  await reload();await persisted(done,0,'gallery picture after choices reload');
  if(await text(choiceFile)!==choices)throw Error(label+': reload changed choices');
  await tool(0);await stable('restored stencil page');
  await tap(await control('Ball',stencil.tile(0)));await stable('restored selected stencil');
  await key('Escape');await stable('cancel restored pending stencil');
  if(errors.length)throw Error(JSON.stringify(errors));
  console.log(`local paint layers ${label}: continuous rendering, placement, Mirror, fill, overlap erase, rotation and Undo across reloads, gallery copies/New/open, and remembered stencil choices passed`);
 }catch(error){
  if(socket?.readyState===WebSocket.OPEN){
   await mkdir('build/tests/web',{recursive:true});
   const id=2147483647;socket.send(JSON.stringify({id,method:'Page.captureScreenshot',params:{format:'png'}}));
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

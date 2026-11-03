// A request downloads behind the painted loading screen. File progress counts
// only complete, verified and prepared assets. A failed attempt never
// advances it. Back invalidates the request before any callback.
// One prefetch at a time, such as the next book, loads its files one by one,
// low priority, and only while no request is loading and idle() allows it,
// so it never competes with what is being read. pausePrefetch stops it before
// its next file. A file loaded once is never loaded again.
class JungleActivityLoader {
 constructor(load,changed,idle=()=>true){this.load=load;this.changed=changed;this.idle=idle;this.generation=0;this.prefetchGeneration=0;this.completed=new Set();this.loaded=new Set()}
 // TITLE, when known before the definition, names the loading screen at once.
 request(key,definition,title){
  if(this.completed.has(key))return 'ready';
  if(this.state?.key===key)return this.state.status;
  this.cancel();
  // A request takes over its own prefetch; files already here count at once.
  if(this.background?.key===key)this.pausePrefetch();
  const state=this.state={key,status:'loading',loaded:0,total:0,definition,title};
  this.run(state);return 'loading';
 }
 async run(state){
  const generation=++this.generation,current=()=>generation===this.generation;
  state.status='loading';state.loaded=0;this.changed(state);
  try{
   const {files,title,cover}=await state.definition();
   if(!current())return;
   state.files=[...new Set(files)];state.total=state.files.length;state.title=title||state.title;state.cover=cover;
   this.changed(state);let next=0;
   await Promise.all(Array.from({length:4},async()=>{
    while(current()&&state.status==='loading'&&next<state.files.length){
     const path=state.files[next++];
     if(!this.loaded.has(path)){await this.load(path,false);this.loaded.add(path)}
     if(!current()||state.status!=='loading')return;
     state.loaded++;this.changed(state);
    }
   }));
   if(!current())return;
   state.status='ready';this.completed.add(state.key);this.changed(state);
  }catch(error){if(current()){state.status='error';state.error=error;this.changed(state)}}
 }
 retry(){if(this.state?.status==='error')this.run(this.state)}
 cancel(){this.generation++;if(this.state){this.state.status='cancelled';this.changed(this.state)}this.state=undefined}
 back(){if(this.state){this.generation++;this.state.status='cancelled';this.changed(this.state)}}
 prefetch(key,definition){
  if(this.completed.has(key)||this.state?.key===key||this.background?.key===key)return;
  const generation=++this.prefetchGeneration,current=()=>generation===this.prefetchGeneration;
  const background=this.background={key,loaded:0,total:0};
  (async()=>{
   try{
    const {files}=await definition();
    background.files=[...new Set(files)];background.total=background.files.length;
    for(const path of background.files){
     while(current()&&(this.state?.status==='loading'||!this.idle()))await new Promise(resolve=>setTimeout(resolve,100));
     if(!current())return;
     if(!this.loaded.has(path)){await this.load(path,true);this.loaded.add(path)}
     background.loaded++;
    }
    if(current()){this.completed.add(key);this.background=undefined}
   }catch(error){
    // The request that later needs these files shows Try again.
    if(current()){this.background=undefined;console.warn('Prefetch stopped:',key,error)}
   }
  })();
 }
 pausePrefetch(){this.prefetchGeneration++;this.background=undefined}
}

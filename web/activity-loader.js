// File progress counts only complete, verified and prepared assets. A failed
// attempt never advances it. Back invalidates the request before any callback.
class JungleActivityLoader {
 constructor(load,changed){this.load=load;this.changed=changed;this.generation=0;this.completed=new Set()}
 request(key,definition){
  if(this.completed.has(key))return 'ready';
  if(this.state?.key===key)return this.state.status;
  this.cancel();
  const state=this.state={key,status:'loading',loaded:0,total:0,definition};
  this.run(state);return 'loading';
 }
 async run(state){
  const generation=++this.generation,current=()=>generation===this.generation;
  state.status='loading';state.loaded=0;this.changed(state);
  try{
   const {files,title,cover}=await state.definition();
   if(!current())return;
   state.files=[...new Set(files)];state.total=state.files.length;state.title=title;state.cover=cover;
   this.changed(state);let next=0;
   await Promise.all(Array.from({length:4},async()=>{
    while(current()&&state.status==='loading'&&next<state.files.length){
     await this.load(state.files[next++]);
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
}

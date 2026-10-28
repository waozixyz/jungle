// Standard ZIP asset packs, with a build-time index instead of a ZIP parser.
// Works under any static host/subdirectory; no service worker, Range or CDN API.
class JungleAssetPacks {
 constructor(manifest, fetchBytes, cacheBytes=16*1024*1024){
  if(manifest.format!==1)throw Error('Unsupported asset pack format');
  this.manifest=manifest;this.fetchBytes=fetchBytes;this.cacheBytes=cacheBytes;
  this.cache=new Map();this.pending=new Map();this.bytes=0;
 }
 async pack(path){
  if(this.cache.has(path)){
   const bytes=this.cache.get(path);this.cache.delete(path);this.cache.set(path,bytes);return bytes;
  }
  if(this.pending.has(path))return this.pending.get(path);
  const request=(async()=>{
   const bytes=new Uint8Array(await this.fetchBytes(path));
   const expected=this.manifest.packs[path];
   if(bytes.length!==expected.size||await JungleAssetPacks.hash(bytes)!==expected.sha256)throw Error('Damaged asset pack: '+path);
   while(this.bytes+bytes.length>this.cacheBytes&&this.cache.size){
    const oldest=this.cache.keys().next().value;this.bytes-=this.cache.get(oldest).length;this.cache.delete(oldest);
   }
   if(bytes.length<=this.cacheBytes){this.cache.set(path,bytes);this.bytes+=bytes.length}
   return bytes;
  })();
  this.pending.set(path,request);
  try{return await request}finally{this.pending.delete(path)}
 }
 static async hash(bytes){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('')}
 async read(path){
  const entry=this.manifest.files[path];if(!entry)throw Error('Unknown asset: '+path);
  const pack=await this.pack(entry.pack);
  if(entry.offset<0||entry.length<0||entry.offset+entry.length>pack.length)throw Error('Invalid asset bounds: '+path);
  const compressed=pack.subarray(entry.offset,entry.offset+entry.length);
  let bytes;
  if(entry.method===0)bytes=compressed;
  else if(entry.method===8)bytes=new Uint8Array(await new Response(new Blob([compressed]).stream().pipeThrough(new DecompressionStream('deflate-raw'))).arrayBuffer());
  else throw Error('Unsupported ZIP compression: '+entry.method);
  if(bytes.length!==entry.size||await JungleAssetPacks.hash(bytes)!==entry.sha256)throw Error('Damaged asset: '+path);
  return bytes;
 }
}

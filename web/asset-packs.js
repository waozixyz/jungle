// Standard ZIP asset packs, with a build-time index instead of a ZIP parser.
// Works under any static host/subdirectory; no service worker, Range or CDN API.
class JungleAssetPacks {
 constructor(manifest, fetchBytes, cacheBytes=16*1024*1024){
  if(manifest.format!==1)throw Error('Unsupported asset pack format');
  this.manifest=manifest;this.fetchBytes=fetchBytes;this.cacheBytes=cacheBytes;
  this.cache=new Map();this.pending=new Map();this.bytes=0;this.zipIndexes=new WeakMap();
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
 // The index intentionally stays compatible with existing packs. CRC and ZIP
 // sizes come from their central directory, never from guessed payload bytes.
 zipEntry(pack,entry){
  let index=this.zipIndexes.get(pack);
  if(!index){
   const view=new DataView(pack.buffer,pack.byteOffset,pack.byteLength);
   const bad=()=>{throw Error('Invalid ZIP metadata')};
   let end=-1;
   for(let p=pack.length-22;p>=Math.max(0,pack.length-65557);p--){
    if(view.getUint32(p,true)===0x06054b50&&p+22+view.getUint16(p+20,true)===pack.length){end=p;break}
   }
   if(end<0)bad();
   const count=view.getUint16(end+10,true),start=view.getUint32(end+16,true),length=view.getUint32(end+12,true);
   if(view.getUint16(end+4,true)||view.getUint16(end+6,true)||view.getUint16(end+8,true)!==count||start+length!==end)bad();
   index=new Map();let p=start;
   for(let n=0;n<count;n++){
    if(p+46>end||view.getUint32(p,true)!==0x02014b50)bad();
    const flags=view.getUint16(p+8,true),method=view.getUint16(p+10,true),crc=view.getUint32(p+16,true),compressed=view.getUint32(p+20,true),size=view.getUint32(p+24,true);
    const name=view.getUint16(p+28,true),extra=view.getUint16(p+30,true),comment=view.getUint16(p+32,true),local=view.getUint32(p+42,true);
    if(flags&1||view.getUint16(p+34,true)||p+46+name+extra+comment>end||local+30>start||view.getUint32(local,true)!==0x04034b50)bad();
    const offset=local+30+view.getUint16(local+26,true)+view.getUint16(local+28,true);
    if(view.getUint16(local+8,true)!==method||offset+compressed>start||index.has(offset))bad();
    index.set(offset,{method,crc,length:compressed,size});p+=46+name+extra+comment;
   }
   if(p!==end)bad();this.zipIndexes.set(pack,index);
  }
  const meta=index.get(entry.offset);
  if(!meta||meta.method!==entry.method||meta.length!==entry.length||meta.size!==entry.size)throw Error('Invalid ZIP entry metadata');
  return meta;
 }
 static crc32(bytes){
  if(!this.crcTable)this.crcTable=Uint32Array.from({length:256},(_,n)=>{for(let k=0;k<8;k++)n=n&1?0xedb88320^(n>>>1):n>>>1;return n>>>0});
  let crc=0xffffffff;for(const byte of bytes)crc=this.crcTable[(crc^byte)&255]^(crc>>>8);
  return (crc^0xffffffff)>>>0;
 }
 static decompressor(){
  // Older Chrome exposes the constructor but only implements gzip/deflate.
  try{return {stream:new DecompressionStream('deflate-raw'),gzip:false}}
  catch{return {stream:new DecompressionStream('gzip'),gzip:true}}
 }
 async read(path){
  const entry=this.manifest.files[path];if(!entry)throw Error('Unknown asset: '+path);
  const pack=await this.pack(entry.pack);
  if(entry.offset<0||entry.length<0||entry.offset+entry.length>pack.length)throw Error('Invalid asset bounds: '+path);
  const compressed=pack.subarray(entry.offset,entry.offset+entry.length);
  let bytes;
  if(entry.method===0)bytes=compressed;
  else if(entry.method===8){
   const meta=this.zipEntry(pack,entry),decoder=JungleAssetPacks.decompressor();
   let parts=[compressed];
   if(decoder.gzip){
    const footer=new Uint8Array(8),view=new DataView(footer.buffer);
    view.setUint32(0,meta.crc,true);view.setUint32(4,meta.size,true);
    parts=[new Uint8Array([31,139,8,0,0,0,0,0,0,3]),compressed,footer];
   }
   bytes=new Uint8Array(await new Response(new Blob(parts).stream().pipeThrough(decoder.stream)).arrayBuffer());
   if(JungleAssetPacks.crc32(bytes)!==meta.crc)throw Error('Damaged ZIP CRC: '+path);
  }
  else throw Error('Unsupported ZIP compression: '+entry.method);
  if(bytes.length!==entry.size||await JungleAssetPacks.hash(bytes)!==entry.sha256)throw Error('Damaged asset: '+path);
  return bytes;
 }
}

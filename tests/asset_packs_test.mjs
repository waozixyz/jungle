// Exercise the shipped reader on every real asset, including malformed data,
// concurrent fetches, failed-fetch retry and bounded cache eviction.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {deflateRawSync} from 'node:zlib';
import {resolve,join} from 'node:path';
const root=resolve(process.env.JUNGLE_WEB_ROOT||'build/web');
vm.runInThisContext(await readFile('web/asset-packs.js','utf8'));
// Tiny ordinary ZIP fixture: exercise both native formats independently of the
// existing distribution, including Chrome 101's constructor-present rejection.
const nativeDecompressionStream=globalThis.DecompressionStream;
const sample=Buffer.from('Jungle music '.repeat(300));
function fixture({crc=JungleAssetPacks.crc32(sample),size=sample.length,truncate=0}={}){
 const data=deflateRawSync(sample).subarray(0,deflateRawSync(sample).length-truncate),name=Buffer.from('clip.wav');
 const local=Buffer.alloc(30);local.writeUInt32LE(0x04034b50);local.writeUInt16LE(8,8);local.writeUInt32LE(crc,14);local.writeUInt32LE(data.length,18);local.writeUInt32LE(size,22);local.writeUInt16LE(name.length,26);
 const central=Buffer.alloc(46);central.writeUInt32LE(0x02014b50);central.writeUInt16LE(8,10);central.writeUInt32LE(crc,16);central.writeUInt32LE(data.length,20);central.writeUInt32LE(size,24);central.writeUInt16LE(name.length,28);
 const end=Buffer.alloc(22);end.writeUInt32LE(0x06054b50);end.writeUInt16LE(1,8);end.writeUInt16LE(1,10);end.writeUInt32LE(central.length+name.length,12);end.writeUInt32LE(local.length+name.length+data.length,16);
 return {pack:Buffer.concat([local,name,data,central,name,end]),entry:{pack:'fixture.zip',offset:local.length+name.length,length:data.length,size,method:8}};
}
async function readFixture(f){
 const manifest={format:1,packs:{'fixture.zip':{size:f.pack.length,sha256:await JungleAssetPacks.hash(f.pack)}},files:{clip:{...f.entry,sha256:await JungleAssetPacks.hash(sample)}}};
 return new JungleAssetPacks(manifest,async()=>f.pack).read('clip');
}
for(const fallback of [false,true]){
 const formats=[];
 globalThis.DecompressionStream=class {
  constructor(format){formats.push(format);if(fallback&&format==='deflate-raw')throw TypeError('unsupported deflate-raw');return new nativeDecompressionStream(format)}
 };
 assert.deepEqual(Buffer.from(await readFixture(fixture())),sample);
 assert.deepEqual(formats,fallback?['deflate-raw','gzip']:['deflate-raw']);
 await assert.rejects(readFixture(fixture({crc:0})),undefined,'Corrupt CRC accepted');
 await assert.rejects(readFixture(fixture({size:sample.length+1})),undefined,'Corrupt size accepted');
 await assert.rejects(readFixture(fixture({truncate:3})),undefined,'Truncated deflate accepted');
 const truncated=fixture();truncated.pack=truncated.pack.subarray(0,truncated.pack.length-1);
 await assert.rejects(readFixture(truncated),/Invalid ZIP/);
 const mismatch=fixture();mismatch.entry.size++;
 await assert.rejects(readFixture(mismatch),/Invalid ZIP entry/);
}
globalThis.DecompressionStream=nativeDecompressionStream;
const manifest=JSON.parse(await readFile(join(root,'asset-packs.json'),'utf8'));
let fetches=0;
const loader=new JungleAssetPacks(manifest,async path=>{fetches++;return readFile(join(root,path))});
const paths=Object.keys(manifest.files);
for(const path of paths){
 const actual=await loader.read(path);
 let source=path;
 if(path.startsWith('assets/animal-count/pictures/'))source=path.replace('assets/animal-count/pictures/','assets/jungle-book/counting/');
 else if(path==='assets/speech.txt')source='work/web-speech/speech.txt';
 else if(path.startsWith('assets/speech/')){
  assert.match(path,/^assets\/speech\/(?:en|de|es)\/[0-9a-f]{64}\.ogg$/);
  source=path.replace('assets/speech/','work/speech-codec/');
 }
 const entry=manifest.files[path],original=await readFile(source);
 if(entry.encoding==='webp'){
  assert.equal(await JungleAssetPacks.hash(original),entry.source_sha256,path);
  assert.equal(Buffer.from(actual).subarray(0,4).toString(),'RIFF',path);
  assert.equal(Buffer.from(actual).subarray(8,12).toString(),'WEBP',path);
  assert.equal(entry.quality,90);assert.ok(actual.length<original.length);
 }else assert.deepEqual(Buffer.from(actual),original,path);
 assert.ok(loader.bytes<=loader.cacheBytes);
}
loader.cache.clear();loader.bytes=0;
let before=fetches;
await Promise.all([loader.read(paths[0]),loader.read(paths[0])]);
assert.equal(fetches-before,1,'Concurrent asset requests fetched the pack twice');
let attempts=0;
const retry=new JungleAssetPacks(manifest,async path=>{
 if(attempts++===0)throw Error('temporary network failure');return readFile(join(root,path));
});
await assert.rejects(retry.read(paths[0]),/temporary network/);
await retry.read(paths[0]);assert.equal(attempts,2);
const corrupt=new JungleAssetPacks(manifest,async path=>{
 const data=await readFile(join(root,path));data[0]^=1;return data;
});
await assert.rejects(corrupt.read(paths[0]),/Damaged asset pack/);
const bounded=new JungleAssetPacks(manifest,path=>readFile(join(root,path)),1);
await bounded.read(paths[0]);assert.equal(bounded.bytes,0);
const invalid=structuredClone(manifest);invalid.files[paths[0]].offset=Number.MAX_SAFE_INTEGER;
await assert.rejects(new JungleAssetPacks(invalid,path=>readFile(join(root,path))).read(paths[0]),/Invalid asset bounds/);

// Stopping or replacing a clip while its pack is in flight must prevent late
// playback. Exercise the shipped adapter with a deliberately stalled source.
const html=await readFile('web/index.html','utf8');
vm.runInThisContext(html.slice(html.indexOf('function packedAudio('),html.indexOf('function unavailableImage(')));
globalThis.Audio=class {
 constructor(){this.paused=true;this.plays=0}
 async play(){this.paused=false;this.plays++}
 pause(){this.paused=true}
 removeAttribute(name){delete this[name]}
};
let release;
 globalThis.soundBytes=()=>new Promise(resolve=>{release=resolve});
const stopped=packedAudio('stopped.wav'),playing=stopped.play();
assert.equal(stopped.jungleLoading,true);
stopped.pause();stopped.removeAttribute('src');release(new Uint8Array([1,2,3]));await playing;
assert.equal(stopped.plays,0,'A stopped clip played when its download finished');
 globalThis.soundBytes=async()=>new Uint8Array([1,2,3]);
const resumed=packedAudio('resumed.wav');await resumed.play();resumed.pause();await resumed.play();
assert.equal(resumed.plays,2);assert.equal(resumed.jungleLoading,false);resumed.removeAttribute('src');
console.log(`local asset reader test: all ${paths.length} original, generated speech or reviewed WebP assets verified; integrity, retry, concurrent fetches and memory cap passed`);

// Exercise the shipped reader on every real asset, including malformed data,
// concurrent fetches, failed-fetch retry and bounded cache eviction.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {resolve,join} from 'node:path';
const root=resolve(process.env.JUNGLE_WEB_ROOT||'build/web');
vm.runInThisContext(await readFile('web/asset-packs.js','utf8'));
const manifest=JSON.parse(await readFile(join(root,'asset-packs.json'),'utf8'));
let fetches=0;
const loader=new JungleAssetPacks(manifest,async path=>{fetches++;return readFile(join(root,path))});
const paths=Object.keys(manifest.files);
for(const path of paths){
 const actual=await loader.read(path);
 let source=path;
 if(path.startsWith('assets/animal-count/pictures/'))source=path.replace('assets/animal-count/pictures/','assets/jungle-book/counting/');
 assert.deepEqual(Buffer.from(actual),await readFile(source),path);
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
globalThis.assetBytes=()=>new Promise(resolve=>{release=resolve});
const stopped=packedAudio('stopped.wav'),playing=stopped.play();
assert.equal(stopped.jungleLoading,true);
stopped.pause();stopped.removeAttribute('src');release(new Uint8Array([1,2,3]));await playing;
assert.equal(stopped.plays,0,'A stopped clip played when its download finished');
globalThis.assetBytes=async()=>new Uint8Array([1,2,3]);
const resumed=packedAudio('resumed.wav');await resumed.play();resumed.pause();await resumed.play();
assert.equal(resumed.plays,2);assert.equal(resumed.jungleLoading,false);resumed.removeAttribute('src');
console.log(`local asset reader test: all ${paths.length} assets match source bytes; integrity, retry, concurrent fetches and memory cap passed`);

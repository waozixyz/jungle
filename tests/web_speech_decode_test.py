"""Narration clip decoding in web/index.html, run in headless Chromium.

Older Chrome (101 on Android 9) decodes an Ogg Vorbis clip past its last
granule, up to one Vorbis block of padding: 45696 frames for a 45629-frame
clip. The loader rejected those clips, so an activity's loading screen stopped
at "58 / 62" on that phone. The page's own decodeSpeechClip runs here against a
decoder that pads like that Chrome, and must keep exactly the clip's frames,
while short, overlong, stereo or resampled decodes are still refused.
Needs no display, Node or network.
"""
import sys

from web_image_queue_test import run

SCENARIOS = r"""
<script>
const log=[],check=(name,ok,detail)=>log.push({name,ok:Boolean(ok),detail});
// The clip bytes and their Ogg check are not under test here.
assetBytes=async()=>new Uint8Array(8);speechPreflight=()=>true;
let decoded;
window.OfflineAudioContext=class{decodeAudioData(){
 const samples=Float32Array.from({length:decoded.length},(_,frame)=>frame<decoded.frames?(frame+1)/65536:0.5);
 return Promise.resolve({sampleRate:decoded.rate??speechRate,numberOfChannels:decoded.channels??1,length:decoded.length,getChannelData:()=>samples});
}};
async function decode(frames,length,extra={}){
 decoded={frames,length,...extra};
 try{return await decodeSpeechClip({path:'assets/speech/en/clip.ogg',frames})}catch(error){return error}
}
(async()=>{
 const exact=await decode(45629,45629);
 check('exact decode keeps every frame',exact.length===45629&&exact[45628]===45629/65536,String(exact));
 for(const [frames,length] of [[45629,45696],[30576,30848],[71972,72320],[17876,18048]]){
  const padded=await decode(frames,length);
  check('Chrome 101 padding '+length+' trims to '+frames,padded instanceof Float32Array&&padded.length===frames&&padded[frames-1]===frames/65536,String(padded));
 }
 check('one block of padding is accepted',(await decode(1000,1000+speechBlock)).length===1000);
 check('a short decode is refused',(await decode(1000,999)) instanceof Error);
 check('more than a block of padding is refused',(await decode(1000,1001+speechBlock)) instanceof Error);
 check('a stereo decode is refused',(await decode(1000,1000,{channels:2})) instanceof Error);
 check('a resampled decode is refused',(await decode(1000,1000,{rate:44100})) instanceof Error);
})().catch(error=>log.push({name:'harness',ok:false,detail:String(error&&error.stack||error)}))
 .finally(()=>document.body.setAttribute('data-results',JSON.stringify(log)));
</script>
"""


if __name__ == '__main__':
    sys.exit(run(SCENARIOS, 'web speech decode test', 10))

"""The web loading screen names exactly what is loading, run in headless Chromium.

web/index.html's own script runs unchanged, without the wasm runtime, with
controllable downloads (as tests/web_image_queue_test.py). For each language:
a title scene loads quietly and, only when slow, names that scene's place
(never the books); an activity names itself; a Picture Book names the book.
A scene whose pictures are already here changes without any loading screen;
a failed scene shows the screen at once with Try again; a request without a
name shows no heading. Needs no display, Node or network.
"""
import sys

import web_image_queue_test as harness

SCENARIOS = r"""
<script>
const fs=new Set(),deferred=new Map(),log=[];
Module.FS={analyzePath:path=>({exists:fs.has(path)}),mkdirTree(){},writeFile(path){fs.add(path)},readFile:()=>new Uint8Array(1)};
function defer(key){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});deferred.set(key,{resolve,reject});return promise}
function assetBytes(path){return defer(path)}
// Cache Storage never settles on this file page.
async function forgetResource(path){}
async function decodeImage(bytes){}
function speech(){return Promise.resolve({clips:[]})}
const settle=async()=>{for(let at=0;at<40;at++)await Promise.resolve()};
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const check=(name,ok,detail)=>{log.push({name,ok:Boolean(ok),detail});};
// The page already names its own overlay; these are the test's views of it.
const loadingScreen=document.getElementById('activity-loading'),loadingHeading=document.getElementById('activity-title');
const shownLog=[];
new MutationObserver(()=>shownLog.push({shown:!loadingScreen.hidden,title:loadingHeading.textContent})).observe(loadingScreen,{attributes:true,attributeFilter:['hidden']});
const screen=()=>({shown:!loadingScreen.hidden,title:loadingHeading.textContent,headed:!loadingHeading.hidden,retry:!document.getElementById('activity-retry').hidden});
const books=/books|bücher|libros/i;
// What the game passes for each destination (host/jungle_title.zi
// TitleScenePlace, the catalog title, games/book BookDownload).
const PLACE={en:'Campus',de:'Hafen',es:'Casa del árbol'};
const GAME={en:'Picture Book',de:'Bilderbuch',es:'Libro ilustrado'};
const BOOK={en:'Fruits',de:'Früchte',es:'Frutas'};
function reset(){
 Module.junglePreloadReset();activityLoader.completed.clear();activityLoader.loaded.clear();
 fs.clear();deferred.clear();imageLoads.clear();shownLog.length=0;
}
(async()=>{
 const scene=language=>'assets/jungle/title/scene-'+language+'.webp',cover='assets/jungle/covers/picture-book.webp';
 const page=language=>'assets/jungle-book/pages/fruits-'+language+'.webp';
 activityIndex=Promise.resolve({activities:{0:{files:[cover],cover,speech:{en:{normal:[]},de:{normal:[]},es:{normal:[]}},
  books:['en','de','es'].map(language=>({id:'fruits-'+language,cover,files:{landscape:[page(language)],portrait:[page(language)]},speech:{[language]:{normal:[]}}}))}}});
 sceneIndex=Promise.resolve({[scene('en')]:[scene('en')],[scene('de')]:[scene('de')],[scene('es')]:[scene('es')],
  'assets/jungle/title/here.webp':['assets/jungle/title/here.webp'],'assets/jungle/title/broken.webp':['assets/jungle/title/broken.webp'],
  'assets/jungle/title/nameless.webp':['assets/jungle/title/nameless.webp']});
 for(const language of ['en','de','es']){
  reset();Module.jungleLanguage(language);
  const opening=siteCopy[language].opening;
  // Title scene: quiet at first, then its place once the download is slow.
  check(language+' scene request waits',Module.jungleSceneReady(scene(language),PLACE[language])===0);await settle();
  check(language+' scene starts without a loading screen',!screen().shown,screen());
  await pause(JungleActivityLoader.quietDelay+50);
  const slow=screen();
  check(language+' slow scene names its place, never the books',slow.shown&&slow.headed&&slow.title===PLACE[language]&&slow.title!==opening&&!books.test(slow.title),slow);
  deferred.get(scene(language)).resolve(new Uint8Array(1));await settle();
  check(language+' scene ready closes the screen',Module.jungleSceneReady(scene(language),PLACE[language])===1&&!screen().shown,screen());
  // Activity: its own name at once.
  check(language+' activity request waits',Module.jungleActivityReady(0,language,'normal',GAME[language],'')===0);await settle();
  check(language+' activity names itself',screen().shown&&screen().title===GAME[language],screen());
  deferred.get(cover).resolve(new Uint8Array(1));await settle();
  check(language+' activity ready',Module.jungleActivityReady(0,language,'normal',GAME[language],'')===1&&!screen().shown,screen());
  // Picture Book: the open book's own title.
  check(language+' book opens',Module.jungleBookOpen(0,'fruits-'+language+'||landscape|'+BOOK[language])===false);
  check(language+' book request waits',Module.jungleActivityReady(0,language,'normal',GAME[language],'')===0);await settle();
  check(language+' book names its title',screen().shown&&screen().title===BOOK[language],screen());
  deferred.get(page(language)).resolve(new Uint8Array(1));await settle();
  check(language+' book ready',Module.jungleActivityReady(0,language,'normal',GAME[language],'')===1&&!screen().shown,screen());
 }
 // A scene whose pictures are already here never shows the loading screen.
 reset();Module.jungleLanguage('en');fs.add('/assets/jungle/title/here.webp');
 Module.jungleSceneReady('assets/jungle/title/here.webp','Campus');await settle();await pause(JungleActivityLoader.quietDelay+50);
 check('scene already here changes without a loading screen',Module.jungleSceneReady('assets/jungle/title/here.webp','Campus')===1&&!shownLog.some(entry=>entry.shown),shownLog);
 // A failed scene shows the screen at once, named, with Try again: never
 // waiting for quietDelay, which is too long to pass here.
 const quietDelay=JungleActivityLoader.quietDelay;JungleActivityLoader.quietDelay=1e9;
 reset();Module.jungleSceneReady('assets/jungle/title/broken.webp','Market');await settle();
 deferred.get('assets/jungle/title/broken.webp').reject(Error('offline'));await settle();
 check('failed scene shows Try again at once',activityLoader.state?.status==='error'&&screen().shown&&screen().retry&&screen().title==='Market',[screen(),activityLoader.state?.status]);
 JungleActivityLoader.quietDelay=quietDelay;
 // A scene without a name shows no heading at all.
 reset();Module.jungleSceneReady('assets/jungle/title/nameless.webp','');await settle();await pause(JungleActivityLoader.quietDelay+50);
 check('nameless scene shows no heading',screen().shown&&!screen().headed&&screen().title==='',screen());
})().catch(error=>log.push({name:'harness',ok:false,detail:String(error&&error.stack||error)}))
 .finally(()=>document.body.setAttribute('data-results',JSON.stringify(log)));
</script>
"""


if __name__ == '__main__':
    sys.exit(harness.run(SCENARIOS, 'loader label test', 36))

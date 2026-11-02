"""Decode real packed runtime WebP in private Chromium without Node."""
import argparse
import base64
import io
from pathlib import Path
import sys

from PIL import Image

from book_media_start_web_test import browser, serve

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))

REPRESENTATIVES = (
    'assets/jungle-book/pages/tiger.jpg',
    'assets/garden/art/bed.png',
    'assets/hide_seek/props/basket.png',
    'assets/shapes/wooden/backdrop.png',
    'assets/drums/pictures/room.png',
)
DIRECT_TITLE = 'assets/jungle/title/beach.jpg'

CHECK = r'''
(async()=>{
 const manifest=await (await fetch('asset-packs.json')).json();
 const packs=new JungleAssetPacks(manifest,async path=>new Uint8Array(await (await fetch(path)).arrayBuffer()));
 const results=[];
 for(const name of %s){
  const entry=manifest.files[name];
  if(!entry||entry.encoding!=='webp')throw Error('missing runtime WebP index entry: '+name);
  const bytes=await packs.read(name);
  if(bytes[0]!==82||bytes[1]!==73||bytes[2]!==70||bytes[3]!==70||bytes[8]!==87||bytes[9]!==69||bytes[10]!==66||bytes[11]!==80)
   throw Error('bad WebP magic: '+name);
  const bitmap=await createImageBitmap(new Blob([bytes],{type:'image/webp'}));
  const width=bitmap.width,height=bitmap.height;
  if(width!==entry.runtime_width||height!==entry.runtime_height)
   throw Error(`${name}: ${width}x${height}, expected ${entry.runtime_width}x${entry.runtime_height}`);
  const canvas=document.createElement('canvas');canvas.width=bitmap.width;canvas.height=bitmap.height;
  const context=canvas.getContext('2d');context.drawImage(bitmap,0,0);bitmap.close();
  const pixels=context.getImageData(0,0,canvas.width,canvas.height).data;
  let minimum=255,maximum=0;
  for(let index=3;index<pixels.length;index+=4){minimum=Math.min(minimum,pixels[index]);maximum=Math.max(maximum,pixels[index])}
  results.push({name,width,height,minimumAlpha:minimum,maximumAlpha:maximum});
 }
 const titleBytes=new Uint8Array(await (await fetch('assets/jungle/title/beach.webp')).arrayBuffer());
 if(titleBytes[0]!==82||titleBytes[1]!==73||titleBytes[2]!==70||titleBytes[3]!==70||titleBytes[8]!==87||titleBytes[9]!==69||titleBytes[10]!==66||titleBytes[11]!==80)
  throw Error('bad direct title WebP magic');
 const titleBitmap=await createImageBitmap(new Blob([titleBytes],{type:'image/webp'}));
 results.push({name:%s,width:titleBitmap.width,height:titleBitmap.height,minimumAlpha:255,maximumAlpha:255});
 titleBitmap.close();
 return results;
})()
''' % (repr(list(REPRESENTATIVES)), repr(DIRECT_TITLE))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--web-root', type=Path, default=ROOT / 'build/web')
    args = parser.parse_args()
    require_root = args.web_root if args.web_root.is_absolute() else ROOT / args.web_root
    index = require_root / 'asset-packs.json'
    if not index.is_file():
        raise SystemExit('build first; missing ' + str(index))
    with serve(require_root) as base_url, browser() as client:
        client.call('Page.navigate', url=base_url + '/dom.html')
        client.until("document.readyState === 'complete'", 'private Chromium page load')
        client.until('typeof JungleAssetPacks === "function"', 'asset pack runtime')
        results = client.evaluate(CHECK)
        client.until('document.getElementById("loading").style.display === "none"', 'title frame startup')
        startup = client.evaluate(r'''
(()=>performance.getEntriesByType('resource')
  .filter(entry=>entry.name.includes('/assets/jungle/title/'))
  .map(entry=>({name:entry.name.split('/assets/jungle/title/')[1].split('?')[0],
                status:entry.responseStatus,bytes:entry.transferSize})))()
''')
        screenshot = client.call('Page.captureScreenshot', format='png')
        with Image.open(io.BytesIO(base64.b64decode(screenshot['data']))) as frame:
            observed_colors = frame.convert('RGB').getcolors(100)
            frame_colors = 101 if observed_colors is None else len(observed_colors)
    by_name = {row['name']: row for row in results}
    assert set(by_name) == set(REPRESENTATIVES) | {DIRECT_TITLE}, results
    assert by_name['assets/jungle-book/pages/tiger.jpg']['width'] == 1024
    assert by_name['assets/garden/art/bed.png']['width'] == 1024
    assert by_name[DIRECT_TITLE]['width'] == 1672, by_name[DIRECT_TITLE]
    low_titles = [row for row in startup if '-low.webp' in row['name']]
    assert any(row['name'] == 'treehouse-portrait-low.webp' and row['bytes'] > 0 for row in low_titles), startup
    assert not any(row['name'].endswith('.jpg') for row in startup), startup
    assert frame_colors > 100, frame_colors
    basket = by_name['assets/hide_seek/props/basket.png']
    assert basket['minimumAlpha'] == 0 and basket['maximumAlpha'] == 255, basket
    print('local runtime browser test: private Chromium decoded packed WebP, preserved alpha and rendered the title frame')


if __name__ == '__main__':
    main()

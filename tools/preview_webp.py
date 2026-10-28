#!/usr/bin/env python3
"""Build review-only WebP candidates without changing shipped artwork."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'work/webp-review'
FOLDERS = ('jungle-book/pages', 'jungle-book/previews', 'jigsaw')


def convert(path):
    name = path.relative_to(ROOT).as_posix()
    key = hashlib.sha256(name.encode()).hexdigest()[:20]
    folder = OUTPUT / 'images' / key
    folder.mkdir(parents=True, exist_ok=True)
    original = folder / ('original' + path.suffix.lower())
    shutil.copy2(path, original)
    size = path.stat().st_size
    with Image.open(path) as source:
        source.load()
        image = source.convert('RGBA' if path.suffix.lower() == '.png' else 'RGB')
        options = []
        for quality in ((100,) if path.suffix.lower() == '.png' else (90, 85, 80)):
            candidate = folder / f'q{quality}.webp'
            image.save(candidate, 'WEBP', quality=quality, lossless=quality == 100,
                       exact=True, method=4)
            with Image.open(candidate) as decoded:
                decoded = decoded.convert(image.mode)
                exact = decoded.tobytes() == image.tobytes()
                if quality == 100 and not exact:
                    raise ValueError('Lossless candidate changed pixels: ' + name)
                rms = ImageStat.Stat(ImageChops.difference(image, decoded)).rms
            options.append({'quality': quality, 'url': candidate.relative_to(OUTPUT).as_posix(),
                            'bytes': candidate.stat().st_size, 'exact_pixels': exact,
                            'rms': round(sum(rms) / len(rms), 3)})
    return {'name': name, 'category': path.parent.relative_to(ROOT/'assets').as_posix(),
            'original': original.relative_to(OUTPUT).as_posix(), 'bytes': size,
            'width': image.width, 'height': image.height, 'options': options}


HTML = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jungle · WebP before and after</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f6f3e9;color:#283b31;font:16px/1.5 system-ui,sans-serif}
header{position:sticky;top:0;background:#f6f3e9f5;padding:16px 4vw;z-index:2;border-bottom:1px solid #d3d9cb}
h1{margin:0;font-size:24px}p{margin:6px 0}button,select,input{font:inherit;padding:6px 10px;border:1px solid #b9c6b4;border-radius:6px;background:white;color:inherit}
nav{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:12px}main{max-width:1500px;margin:auto;padding:24px}
article{margin-bottom:32px;background:white;border:1px solid #d3d9cb;border-radius:12px;padding:16px}h2{font-size:17px;margin:0 0 8px;overflow-wrap:anywhere}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}.picture{overflow:auto;max-height:75vh;background:repeating-conic-gradient(#eee 0% 25%,#fff 0% 50%) 50%/20px 20px}
img{display:block;width:100%;height:auto;object-fit:contain}.pixel img{width:auto;max-width:none}.meta{margin:8px 0;color:#4b604e}label{display:inline-flex;align-items:center;gap:6px}
small{display:block}a{color:#32624a}@media(max-width:650px){.pair{grid-template-columns:1fr}}
</style><header><h1>Jungle · WebP before and after</h1>
<p>Current Picture Book and Jigsaw artwork only. Originals on the left, compressed candidates on the right. Nothing here replaces published artwork.</p>
<nav><label>Quality <select id="quality"><option value="90">90 · recommended</option><option value="85">85 · smaller</option><option value="80">80 · smallest</option></select></label>
<label>Folder <select id="category"><option value="">All images</option></select></label>
<label>Find <input id="search" placeholder="tiger, family, piano…"></label>
<label><input type="checkbox" id="pixels">Full-size pixels</label>
<button id="previous">Previous</button><span id="page"></span><button id="next">Next</button></nav>
<p id="total"></p><small>PNG candidates use verified lossless WebP, preserving every RGBA pixel. JPEG candidates keep the original dimensions; lossy quality still needs your visual approval. Larger candidates would keep the original.</small></header>
<main id="images"></main><script>
const bytes=n=>n>1048576?(n/1048576).toFixed(2)+' MiB':(n/1024).toFixed(1)+' KiB';
let data=[],offset=0;const size=8,quality=document.getElementById('quality'),category=document.getElementById('category'),search=document.getElementById('search'),pixels=document.getElementById('pixels'),container=document.getElementById('images');
const choice=item=>item.options.find(o=>o.quality===Number(quality.value))||item.options[0];
function image(url,label){const box=document.createElement('div'),caption=document.createElement('p'),frame=document.createElement('div'),img=document.createElement('img');caption.className='meta';caption.textContent=label;frame.className='picture';img.src=url;img.alt=label;img.loading='lazy';frame.append(img);box.append(caption,frame);return box}
function draw(){const q=search.value.toLowerCase(),filtered=data.filter(i=>(!category.value||i.category===category.value)&&i.name.toLowerCase().includes(q));
 const before=data.reduce((s,i)=>s+i.bytes,0),after=data.reduce((s,i)=>s+Math.min(i.bytes,choice(i).bytes),0);
 document.getElementById('total').textContent=data.length+' images · '+bytes(before)+' → '+bytes(after)+' · '+((1-after/before)*100).toFixed(1)+'% smaller (image payload only; includes duplicate paths)';
 document.getElementById('page').textContent=(filtered.length?Math.floor(offset/size)+1:0)+' / '+Math.ceil(filtered.length/size);
 document.getElementById('previous').disabled=offset===0;document.getElementById('next').disabled=offset+size>=filtered.length;
 container.classList.toggle('pixel',pixels.checked);container.replaceChildren();
 for(const item of filtered.slice(offset,offset+size)){const option=choice(item),article=document.createElement('article'),title=document.createElement('h2'),pair=document.createElement('div');title.textContent=item.name+' · '+item.width+' × '+item.height;pair.className='pair';
 const label=option.quality===100?'Lossless · exact pixels':'Quality '+option.quality;
 pair.append(image(item.original,'Original · '+bytes(item.bytes)),image(option.url,label+' · '+bytes(option.bytes)+' · '+((1-option.bytes/item.bytes)*100).toFixed(1)+'% smaller'+(option.bytes>=item.bytes?' · keep original':'')));article.append(title,pair);container.append(article)}
}
for(const el of [quality,category,search])el.oninput=()=>{offset=0;draw()};pixels.onchange=draw;
document.getElementById('previous').onclick=()=>{offset=Math.max(0,offset-size);draw();scrollTo(0,0)};
document.getElementById('next').onclick=()=>{offset+=size;draw();scrollTo(0,0)};
fetch('review.json').then(r=>r.json()).then(json=>{data=json.images;for(const name of [...new Set(data.map(i=>i.category))].sort()){const o=document.createElement('option');o.value=o.textContent=name;category.append(o)}draw()});
</script></html>'''


def main():
    files = sorted({p for folder in FOLDERS for p in (ROOT/'assets'/folder).rglob('*')
                    if p.is_file() and p.suffix.lower() in ('.jpg', '.jpeg', '.png')})
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for index, row in enumerate(pool.map(convert, files), 1):
            rows.append(row)
            if index % 40 == 0:
                print(f'Review candidates: {index}/{len(files)}', flush=True)
    (OUTPUT/'review.json').write_text(json.dumps({'images': rows}, indent=2)+'\n')
    (OUTPUT/'index.html').write_text(HTML)
    for quality in (90, 85, 80):
        before = sum(row['bytes'] for row in rows)
        after = sum(min(row['bytes'], next((o for o in row['options'] if o['quality'] == quality),
                                          row['options'][0])['bytes']) for row in rows)
        print(f'Quality {quality}: {before:,} → {after:,} bytes ({100*(1-after/before):.1f}% smaller)')
    print('Review only: '+str(OUTPUT/'index.html'), flush=True)


if __name__ == '__main__':
    main()

"""Explicit shelf hover geometry and procedural feedback exports; no generation."""
from pathlib import Path
import json,sys,copy
sys.path.insert(0,'tools')
from title_glow import glow
from image_exports import export_image
p=Path('tools/title_hotspots.json');d=json.loads(p.read_text());s=next(s for s in d['scenes'] if s['name']=='bookshelf')
for portrait,v in [(False,s),(True,s['portrait'])]:
 stem='bookshelf'+('-portrait' if portrait else '')
 v['hotspots']=[h for h in v['hotspots'] if not h['id'].startswith('book-cover-')]
 top=v['hotspots'][0]
 covers=([[330,88],[609,102],[610,344],[330,334]],[[630,110],[864,122],[865,358],[630,350]],[[888,127],[1124,143],[1128,372],[888,360]]) if not portrait else ([[133,248],[347,256],[348,515],[133,504]],[[411,264],[604,272],[605,529],[411,521]],[[656,279],[848,288],[854,540],[656,531]])
 # Simple row polygon covers book spines and shelf gaps; smaller covers win.
 def box(h,rect):
  x,y,w,ht=rect;h.update(glow_rect=rect,polygon=[[x,y],[x+w-1,y],[x+w-1,y+ht-1],[x,y+ht-1]])
 box(top,[320,85,820,295] if not portrait else [125,240,735,310])
 story=next(h for h in v['hotspots'] if h['id']=='fairy-tale')
 box(story,[345,625,995,230] if not portrait else [125,965,740,335])
 for name,polygon in zip(('tiger','frogs','rabbit'),covers):
  x=min(a[0] for a in polygon);y=min(a[1] for a in polygon);w=max(a[0] for a in polygon)-x+1;ht=max(a[1] for a in polygon)-y+1
  v['hotspots'].append(dict(id='book-cover-'+name,target='game:Picture Book',polygon=polygon,glow_rect=[x,y,w,ht],glow=''))
 for h in [top,story]+v['hotspots'][-3:]:
  h['glow']=f'assets/jungle/title/glow/{stem}-{h["id"]}-hover.webp'
  scratch=Path('local/art-development/title-runtime-exports')
  scratch.mkdir(parents=True,exist_ok=True)
  original=scratch/(Path(h['glow']).stem+'.png')
  glow(h).save(original)
  export_image(original,h['glow'],'cutout')
p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')

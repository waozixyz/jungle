"""Explicit Stories-row hover geometry and procedural feedback export; no generation.

The first row keeps its original traced whole-row hotspot and glow."""
from pathlib import Path
import json,sys
sys.path.insert(0,'tools')
from title_glow import glow
from image_exports import export_image
p=Path('tools/title_hotspots.json');d=json.loads(p.read_text());s=next(s for s in d['scenes'] if s['name']=='bookshelf')
for portrait,v in [(False,s),(True,s['portrait'])]:
 stem='bookshelf'+('-portrait' if portrait else '')
 # One simple row polygon covers every Stories book and the gaps between them.
 x,y,w,ht=[345,625,995,230] if not portrait else [125,965,740,335]
 story=next(h for h in v['hotspots'] if h['id']=='fairy-tale')
 story.update(glow_rect=[x,y,w,ht],polygon=[[x,y],[x+w-1,y],[x+w-1,y+ht-1],[x,y+ht-1]])
 story['glow']=f'assets/jungle/title/glow/{stem}-fairy-tale-hover.webp'
 scratch=Path('local/art-development/title-runtime-exports')
 scratch.mkdir(parents=True,exist_ok=True)
 original=scratch/(Path(story['glow']).stem+'.png')
 glow(story).save(original)
 export_image(original,story['glow'],'cutout')
p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')

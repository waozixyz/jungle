"""Keep watercolor scene layers separate from the centered picture-book cutouts."""
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'assets/jungle-book/backgrounds'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    sources={name:ROOT/f'art/generated/book-background-{name}.png' for name in ['jungle','garden','farm','food','family','body']}
    sources.update({name:ROOT/f'assets/jungle-book/previews/{name}.png' for name in ['kitchen','bathroom','bedroom','living-room']})
    sources['nature']=ROOT/'assets/jungle-book/items/tree.png'
    for name,path in sources.items():
        with Image.open(path) as picture:
            picture.convert('RGBA').resize((420,420),Image.Resampling.LANCZOS).save(OUT/(name+'.png'),optimize=True)
    print(f'Prepared {len(sources)} separate watercolor backgrounds.')

if __name__=='__main__':main()

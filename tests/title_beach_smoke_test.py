"""Walk the Beach/Port/Aquarium routes on an owned private display."""
import json
from pathlib import Path
import tempfile
import time
from PIL import Image, ImageChops, ImageStat
import runtime_test as rt


def main():
    data=json.loads((rt.ROOT/'tools/title_hotspots.json').read_text())
    scenes={s['name']:s for s in data['scenes']}
    scratch=rt.run_folder('backup/beach-port-smoke')
    rt.OUTPUT=scratch/'captures'
    legs=[('campus','jungle-path'),('jungle-path','beach'),('beach','port'),
          ('port','market'),('market','port'),('port','beach'),
          ('beach','aquarium'),('aquarium','beach'),('beach','jungle-path'),
          ('jungle-path','campus')]
    for width,height in ((960,600),(420,900)):
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            state=Path(folder)
            (state/'sound.txt').write_text('off\n')
            (state/'guide-seen.txt').write_text('yes\n')
            with rt.Desktop(rt.ROOT/'build/app/jungle',state,screen_size='1100x1100') as desktop:
                desktop.resize(width,height)
                desktop.key('Home')
                home=data['scenes'][0]
                desktop.key(str(next(i+1 for i,h in enumerate(home['hotspots']) if h['target']=='scene:campus')))
                time.sleep(.5)
                for index,(origin,destination) in enumerate(legs):
                    before=desktop.capture_actual(f'{width}-{index}-before')
                    view=scenes[origin]['portrait'] if height>width else scenes[origin]
                    key=next(i+1 for i,h in enumerate(view['hotspots']) if h['target']=='scene:'+destination)
                    desktop.key(str(key))
                    time.sleep(.65)
                    after=desktop.capture_actual(f'{width}-{index}-{destination}')
                    difference=max(ImageStat.Stat(ImageChops.difference(before.convert('RGB'),after.convert('RGB'))).mean)
                    assert difference>4,(width,origin,destination,difference)
                    if destination=='beach':
                        beach=scenes['beach']['portrait'] if height>width else scenes['beach']
                        with Image.open(rt.ROOT/beach['image']) as clean:
                            scale=max(width/clean.width,height/clean.height)
                            ox=(width-clean.width*scale)/2
                            oy=(height-clean.height*scale)/2
                            crab=next(h for h in beach['hotspots'] if h['id']=='crab-family')
                            x,y,w,h=crab['glow_rect']
                            region=(round(ox+x*scale),round(oy+y*scale),round(ox+(x+w)*scale),round(oy+(y+h)*scale))
                            expected=clean.convert('RGB').resize((round(clean.width*scale),round(clean.height*scale)),Image.Resampling.BILINEAR)
                            local=tuple(round(v-(ox if i%2==0 else oy)) for i,v in enumerate(region))
                            reference=expected.crop(local).resize((80,40))
                            visible=after.convert('RGB').crop(region).resize((80,40))
                            assert max(ImageStat.Stat(ImageChops.difference(reference,visible)).mean)>8,('crab overlay missing',width)

                print(f'private route walk {width}x{height}: Campus → Jungle Path → Beach → Port → Market and back, Aquarium round trip passed')


if __name__=='__main__':
    main()

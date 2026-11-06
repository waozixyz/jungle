"""Native board+label rotation leaves its post fixed, on an owned Xvfb only."""
from pathlib import Path
import tempfile
import time
import math
from PIL import ImageChops, ImageDraw, ImageStat
import runtime_test as rt


class TransformDesktop(rt.Desktop):
    def wait_menu(self,name):
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            self.alive()
            picture=self.capture_actual(name)
            if min(ImageStat.Stat(picture.crop((300,180,450,250))).mean)<230:
                return picture
            time.sleep(.1)
        raise AssertionError('native transform test board did not load')


def main():
    scratch=rt.run_folder('editor/test-output/native-transforms')
    rt.OUTPUT=scratch/'captures'
    with tempfile.TemporaryDirectory(dir=scratch) as folder:
        state=Path(folder)
        (state/'guide-seen.txt').write_text('yes\n')
        (state/'sound.txt').write_text('off\n')
        with TransformDesktop(rt.ROOT/'build/tests/title_transform',state) as d:
            d.resize(760,600)
            time.sleep(.8)
            before=d.capture_actual('board-unrotated')
            d.key('1');time.sleep(.3)
            turned=d.capture_actual('board-rotated-35')
            diff=ImageChops.difference(before,turned)
            assert max(ImageStat.Stat(diff.crop((130,70,650,430))).mean)>10,'board did not visibly rotate'
            assert max(ImageStat.Stat(diff.crop((325,440,373,535))).mean)<.1,'board rotation moved its independent post'
            # Rigid rotation must cover pixels beyond the original axis-aligned
            # image bounds, rather than clipping to the old rectangle.
            assert max(ImageStat.Stat(diff.crop((180,70,560,135))).mean)>1,'rotated corners clipped'
            d.key('2');time.sleep(.3)
            restored=d.capture_actual('board-restored')
            assert max(ImageStat.Stat(ImageChops.difference(before,restored)).mean)<.2,'restoring zero angle did not restore the board and lettering'
    print('local native transform test: actual app Image mesh and localized Text rotate35°, full corner coverage, fixed independent post, zero-angle restoration passed')
    farm_proof(scratch)


def farm_proof(scratch):
    class FarmDesktop(rt.Desktop):
        def wait_menu(self, name):
            time.sleep(.5)
            return self.capture_actual(name)
    with tempfile.TemporaryDirectory(dir=scratch) as folder:
        old=Path(folder)/'games/jungle.garden/garden.txt'
        old.parent.mkdir(parents=True)
        legacy='garden 2 6\n1 100 100 3700 3600 0\n'+'0 0 0 0 0 0\n'*5
        old.write_text(legacy)
        with FarmDesktop(rt.ROOT/'build/tests/farm_transform', Path(folder),screen_size='1280x1100') as d:
          for w,h in ((960,600),(420,900)):
            d.resize(w,h)
            capture=lambda name: d.capture_actual(f'{w}x{h}-{name}')
            rt.run(['xdotool','mousemove','--window',d.window,'0','0'],d.env)
            d.key('r'); time.sleep(1.0)
            baseline=capture('farm-baseline')
            portrait=h>w
            iw,ih=(1024,1536) if portrait else (1672,941)
            base=(530,200,360,190) if portrait else (700,70,400,210)
            moved=(160,240,500,250) if portrait else (300,80,520,260)
            post=(600,500,50,210) if portrait else (800,300,55,220)
            scale=max(w/iw,h/ih)
            ox=(w-int(iw*scale))//2; oy=(h-int(ih*scale))//2
            def region(rect, pad=4):
                x,y,w,h=rect
                return (round(ox+x*scale-pad),round(oy+y*scale-pad),round(ox+(x+w)*scale+pad),round(oy+(y+h)*scale+pad))
            def tap(x,y):
                rt.run(['xdotool','mousemove','--window',d.window,str(round(ox+x*scale)),str(round(oy+y*scale))],d.env)
                # Let the retained polygon-refined Press observe the hover
                # before pressing; a synthetic teleport+down can share a frame.
                time.sleep(.25)
                rt.run(['xdotool','mousedown','1'],d.env); time.sleep(.2)
                rt.run(['xdotool','mouseup','1'],d.env); time.sleep(.3)
            def clicked():
                pixel=capture('farm-hit-state').getpixel((25,h-25))
                return pixel[1]>180 and pixel[0]<50
            post_region=region((post[0]+5,post[1]+60,post[2]-10,post[3]-65))
            d.key('b'); turned=capture('farm-board-moved-resized-35')
            diff=ImageChops.difference(baseline,turned)
            assert max(ImageStat.Stat(diff).mean)>2,'Farm board did not move/resize/rotate'
            assert max(ImageStat.Stat(diff.crop(post_region)).mean)<.1,'Farm board moved its independent post'
            # Old plank centre and an empty corner inside the new AABB both
            # reject clicks. The transformed board's new label centre accepts.
            tap(base[0]+base[2]/2,base[1]+base[3]/2); assert not clicked(),'old Farm board location stayed active'
            corner=(moved[0]+80,moved[1]-100) if portrait else (moved[0]-20,moved[1]-30)
            tap(*corner); assert not clicked(),'empty rotated AABB corner accepted a click'
            angle=math.radians(35); cx,cy=moved[0]+moved[2]/2,moved[1]+moved[3]/2
            x,y=moved[0]+moved[2]*(10+124/2)/223,moved[1]+moved[3]*(32+54/2)/118
            hit=(cx+(x-cx)*math.cos(angle)-(y-cy)*math.sin(angle),cy+(x-cx)*math.sin(angle)+(y-cy)*math.cos(angle))
            tap(*hit); assert clicked(),'moved rotated Farm board did not accept its new hit'
            d.key('r'); d.key('b'); board_only=capture('farm-board-before-post-change')
            d.key('n'); bare=capture('farm-rotated-board-without-label')
            letters=ImageChops.difference(board_only,bare).convert('RGB')
            points=[(x,y) for y in range(h-45) for x in range(w)
                    if max(letters.getpixel((x,y)))>30]
            assert len(points)>30,'Farm localized text did not render'
            lx=sum(x for x,y in points)/len(points); ly=sum(y for x,y in points)/len(points)
            assert abs(lx-(ox+hit[0]*scale))<30 and abs(ly-(oy+hit[1]*scale))<20,'Farm label did not follow board centre'
            xx=sum((x-lx)**2 for x,y in points); yy=sum((y-ly)**2 for x,y in points)
            xy=sum((x-lx)*(y-ly) for x,y in points)
            tilt=math.degrees(.5*math.atan2(2*xy,xx-yy))
            assert abs(tilt-35)<12,('Farm label did not rotate with board',tilt)
            d.key('n')
            d.key('p'); both=capture('farm-post-moved-resized-minus28')
            post_diff=ImageChops.difference(board_only,both)
            assert max(ImageStat.Stat(post_diff).mean)>.5,'Farm post transform had no visible effect'
            # The old post overlaps part of the moved board. Exclude only the
            # old/new post extents, then require every other pixel to stay put.
            untouched=post_diff.copy(); mask=ImageDraw.Draw(untouched)
            mask.rectangle(region(post),fill=0)
            px,py,pw,ph=(790,620,70,280) if portrait else (1180,180,90,300)
            theta=math.radians(-28)
            rotated_w=abs(pw*math.cos(theta))+abs(ph*math.sin(theta))
            rotated_h=abs(pw*math.sin(theta))+abs(ph*math.cos(theta))
            mask.rectangle(region((px+(pw-rotated_w)/2,py+(ph-rotated_h)/2,rotated_w,rotated_h)),fill=0)
            assert max(ImageStat.Stat(untouched).mean)<.1,'post change moved pixels outside the independent post'
            d.key('h'); hidden_board=capture('farm-board-hidden')
            tap(*hit); assert not clicked(),'hidden Farm board retained its hit target'
            d.key('j'); hidden_both=capture('farm-both-hidden')
            assert max(ImageStat.Stat(ImageChops.difference(hidden_board,hidden_both)).mean)>.1,'hidden Farm post stayed visible'
            d.key('r')
            rt.run(['xdotool','mousemove','--window',d.window,'0','0'],d.env)
            time.sleep(.2)
            restored=capture('farm-restored')
            assert max(ImageStat.Stat(ImageChops.difference(baseline,restored)).mean)<.2,'Farm baseline was not restored'
            d.key('l'); german=capture('farm-german-label')
            d.key('l'); spanish=capture('farm-spanish-label')
            # Campus is spelled identically in all three current locales.
            assert max(ImageStat.Stat(ImageChops.difference(german,spanish)).mean)<.2,'Farm Campus label changed across identical localized names'
            d.key('k'); behind=capture('farm-post-behind-board')
            d.key('o'); front=capture('farm-post-in-front-of-board')
            assert max(ImageStat.Stat(ImageChops.difference(behind,front)).mean)>.05,'Farm board/post draw order did not change overlap pixels'
        assert old.read_text()==legacy,'Farm transform proof changed legacy garden.txt'
    print('local native Farm proof: board/post independent move, resize, rotation, hidden pixels/hit target, old/corner rejection and localized label passed',flush=True)


if __name__=='__main__': main()

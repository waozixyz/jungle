#!/usr/bin/env python3
"""One held seed, continuous placement, care and old saves on owned Xvfb."""
from pathlib import Path
import tempfile
import time
import os
from PIL import ImageChops, ImageFilter
import runtime_test as rt
from new_activities_ui_test import geometry
from garden_scene_layout import soil_point

SCRATCH = rt.ROOT/'work/garden-redesign/ui'
SCRATCH.mkdir(parents=True, exist_ok=True)
rt.OUTPUT = SCRATCH/'captures'


def main():
    for language in ('en', 'de', 'es'):
        for size in ((400, 756), (960, 600), (1200, 900)):
            with tempfile.TemporaryDirectory(dir=SCRATCH) as temporary:
                data = Path(temporary)
                (data/'language.txt').write_text(language)
                (data/'sound.txt').write_text('off\n')
                path = data/'games/jungle.garden/garden.txt'
                path.parent.mkdir(parents=True)
                now = int(time.time())
                # Version 2 keeps the original growth/care fields when migrated.
                path.write_text(f'garden 2 0\n6 {now-120000} {now-100000} {now-100000} 20000 0\n2 {now-400000} {now-300000} {now-300000} 100000 0\n'+'0 0 0 0 0 0\n'*4)
                with rt.Desktop(Path(os.environ.get('JUNGLE_TEST_BINARY', rt.ROOT/'build/app/jungle')), data, screen_size='1280x1100') as d:
                    d.game('Grow a Garden')
                    d.resize(*size)
                    s, w, h = geometry('garden', *size)
                    tray = 180 if w < 600 else 94
                    columns = 4 if w < 600 else 7
                    rows = 2 if columns == 4 else 1
                    cw, ch = (w-16)//columns, (tray-16)//rows

                    def tool(index):
                        return (round((8+(index%columns+.5)*cw)*s), round(56+(8+(index//columns+.5)*ch)*s))

                    def soil(x, y):
                        px,py = soil_point(w,h,x,y)
                        return round(px*s), round(56+py*s)

                    def move(point):
                        rt.run(['xdotool', 'mousemove', '--window', d.window, *map(str, point)], d.env)
                        time.sleep(.16)

                    def tap(point):
                        move(point)
                        rt.run(['xdotool', 'mousedown', '1'], d.env)
                        time.sleep(.12)
                        rt.run(['xdotool', 'mouseup', '1'], d.env)
                        time.sleep(.2)
                        d.alive()

                    def drag(start, end):
                        move(start)
                        rt.run(['xdotool', 'mousedown', '1'], d.env)
                        time.sleep(.15)
                        move(end)
                        rt.run(['xdotool', 'mouseup', '1'], d.env)
                        time.sleep(.3)
                        d.alive()

                    def saved():
                        assert path.read_text().splitlines()[0].startswith('garden 3 ')
                        return [list(map(int, line.split())) for line in path.read_text().splitlines()[1:]]

                    def count():
                        return sum(p[0] != 0 for p in saved())

                    def capture(label):
                        # Prefix identifies the initial case. Later resize captures
                        # intentionally use the opposite viewport; PNG dimensions
                        # record its actual size (the case tests both orientations).
                        return d.capture_actual(f'{language}-{size[0]}-{label}')

                    def assert_position(kind, position):
                        p = next(p for p in saved() if p[0] == kind)
                        assert abs(p[6]-position[0]) <= 30 and abs(p[7]-position[1]) <= 30, p
                        assert max(abs(a-b) for a,b in zip(soil(p[6],p[7]),soil(*position))) <= 3, (p,position)
                        return p

                    assert saved()[1][5] == 1, 'Offline death not reconciled'
                    assert saved()[0][0] == 6 and saved()[0][4] >= 20000
                    # Water and clear use actual plant anchors after migration.
                    tap(tool(6)); tap(soil(260, 570))
                    watering = capture('watering')
                    move((8, 8)); time.sleep(1.3)
                    settled = capture('water-settled')
                    assert ImageChops.difference(watering, settled).getbbox()
                    assert int(time.time())-saved()[0][2] < 15
                    tap(soil(500, 570))
                    assert saved()[1] == [0]*8, 'Withered plant did not clear'
                    assert count() == 1

                    target = (623, 489)  # deliberately between the former slots
                    point = soil(*target)
                    move(point)
                    unselected = capture('unselected')
                    tap(tool(4))
                    move(point)
                    selected = capture('held-seed')
                    # A single seed at the ground marker, never a cursor packet.
                    box = (point[0]-round(40*s), point[1]-round(75*s), point[0]+round(40*s), point[1]+round(15*s))
                    change = ImageChops.difference(unselected.crop(box), selected.crop(box)).getbbox()
                    assert change and change[2]-change[0] <= 70*s, 'Held seed preview missing'
                    move(soil(720, 650))
                    moved = capture('moved')
                    assert ImageChops.difference(selected.crop(box), moved.crop(box)).getbbox(), 'Seed did not follow pointer'
                    # Outside soil and near an existing root both retain the seed.
                    tap((round(w*.98*s), round((h-10)*s+56))); tap(soil(265, 570))
                    assert count() == 1, 'Invalid placement consumed/overwrote a seed'
                    move((8, 8)); before = capture('before-placement')
                    planted_at = int(time.time())
                    tap(point)
                    p = assert_position(5, target)
                    assert count() == 2 and 0 <= p[1]-planted_at <= 3 and p[4] < 3600
                    move((8, 8)); falling = capture('falling')
                    time.sleep(1); dropped = capture('planted')
                    ground = (point[0]-round(25*s), point[1]-round(65*s), point[0]+round(25*s), point[1]+round(8*s))
                    change = ImageChops.difference(before.crop(ground), dropped.crop(ground)).getbbox()
                    assert change and change[2]-change[0] <= 24*s and change[3]-change[1] <= 24*s, 'Seed did not land at preview position'
                    fall = ImageChops.difference(before.crop(ground), falling.crop(ground)).getbbox()
                    assert fall and fall[1] < change[1], 'Seed did not fall toward chosen soil'
                    # A packet supplies exactly one seed, requiring another pickup.
                    tap(soil(800, 670)); assert count() == 2
                    tap(tool(1)); tap(tool(0))  # switch the held kind
                    tap(soil(800, 670))
                    assert_position(1, (800, 670)); assert count() == 3
                    drag(tool(1), soil(440, 710))
                    assert_position(2, (440, 710)); assert count() == 4
                    move((8, 8)); capture('free-plants-different-depths')
                    # Cancel with the same packet, Water and secondary pointer.
                    tap(tool(2)); tap(tool(2)); tap(soil(190, 710))
                    assert count() == 4
                    tap(tool(2)); tap(tool(6)); tap(soil(190, 710))
                    assert count() == 4
                    tap(tool(2)); move(soil(190, 710))
                    rt.run(['xdotool', 'click', '3'], d.env); time.sleep(.2)
                    tap(soil(190, 710)); assert count() == 4
                    # Reopen preserves chosen world coordinates and care/growth.
                    checkpoint = saved()
                    d.key('Escape'); d.game('Grow a Garden')
                    for old, new in zip(checkpoint, saved()):
                        assert [new[i] for i in (0, 1, 2, 5, 6, 7)] == [old[i] for i in (0, 1, 2, 5, 6, 7)]
                        assert old[4] <= new[4] <= old[4]+60
                    # The same saved anchors stay under input after resizing.
                    new_size = (960, 600) if size[0] == 400 else (400, 756)
                    d.resize(*new_size)
                    s, w, h = geometry('garden', *new_size)
                    tray = 180 if w < 600 else 94
                    columns = 4 if w < 600 else 7
                    rows = 2 if columns == 4 else 1
                    cw, ch = (w-16)//columns, (tray-16)//rows
                    # Campus board is a separate responsive layer. Its real press
                    # returns through the same route as the shared Back control.
                    d.key('Escape')
                    move((8,8)); campus = capture('campus-reference')
                    d.game('Grow a Garden')
                    portrait = w < h
                    aw, ah = (1024,1536) if portrait else (1671,941)
                    sw, sh = w, w*ah//aw
                    if sh > h-tray: sh=h-tray; sw=sh*aw//ah
                    ox,oy=(w-sw)//2,tray+(h-tray-sh)//2
                    nx,ny,edge=(680,320,180) if portrait else (1400,80,210)
                    signpoint=(round((ox+(nx+edge*.5)*sw/aw)*s),round(56+(oy+(ny+edge*.4)*sh/ah)*s))
                    move((8,8)); board = capture('separate-campus-board')
                    move(signpoint); hover = capture('campus-hover')
                    assert ImageChops.difference(board,hover).getbbox(), 'Board has no hover response'
                    checkpoint = saved()
                    tap(signpoint); time.sleep(.3)
                    move((8,8)); returned = capture('campus-return')
                    # Compare static interior away from title flags and secret paper.
                    region=(20,100,returned.width//2,returned.height//2)
                    assert ImageChops.difference(campus.crop(region),returned.crop(region)).convert('L').getextrema()[1] < 12, 'Sign did not return to Campus'
                    for old,new in zip(checkpoint,saved()):
                        assert [new[i] for i in (0,1,2,5,6,7)] == [old[i] for i in (0,1,2,5,6,7)], 'Return changed plant records'
                        assert old[4] <= new[4] <= old[4]+60
                    d.game('Grow a Garden')
                    was_watered = next(p[2] for p in saved() if p[0] == 5)
                    tap(tool(6)); tap(soil(*target))
                    wet = assert_position(5, target)
                    assert wet[2] > was_watered, 'Resized plant hit missed its saved anchor'
                    # Held picks are transient, so reopen cannot silently plant.
                    tap(tool(3)); d.key('Escape')
                    tap(soil(190, 710)); assert count() == 4
                    d.key('Escape')
                    # All six storage slots remain playable across four beds;
                    # multiple free plants can occupy the same painted bed.
                    path.write_text('garden 3 0\n'+'0 0 0 0 0 0 0 0\n'*6)
                    d.game('Grow a Garden')
                    for kind,position in enumerate(((260,490),(440,490),(700,490),(260,650),(440,710),(800,670))):
                        tap(tool(kind)); tap(soil(*position))
                        assert count() == kind+1, ('six-plant capacity',kind,saved())
                    tap(tool(0)); tap(soil(650,710)); assert count() == 6
                    rt.run(['xdotool','click','3'],d.env); time.sleep(.2)
                    d.key('Escape'); d.game('Grow a Garden'); assert count() == 6
                    move((8,8)); capture('six-plants-four-beds'); d.key('Escape')
                    if language == 'en' and size[0] in (400, 960):
                        # Front plant is deliberately in slot 0, back plant in 1.
                        # Render each alone to establish independent overlap pixels.
                        stamp = int(time.time())
                        front = f'1 {stamp-259300} {stamp-20} {stamp-20} 259200 0 750 550\n'
                        back = f'2 {stamp-345700} {stamp-20} {stamp-20} 345600 0 750 470\n'
                        empty = '0 0 0 0 0 0 0 0\n'

                        def show(rows, label):
                            path.write_text('garden 3 0\n'+''.join(rows)+empty*(6-len(rows)))
                            d.game('Grow a Garden')
                            move((8, 8))
                            picture = capture(label)
                            d.key('Escape')
                            return picture

                        bare = show([], 'depth-empty')
                        front_only = show([front], 'depth-front')
                        back_only = show([empty, back], 'depth-back')
                        together = show([front, back], 'depth-both')
                        def changed(picture):
                            return ImageChops.difference(bare, picture).convert('L').point(lambda x: 255 if x > 20 else 0).filter(ImageFilter.MinFilter(3))
                        overlap = ImageChops.multiply(changed(front_only), changed(back_only))
                        front_pixels = back_pixels = 0
                        for mask, f, b, actual in zip(overlap.getdata(), front_only.getdata(), back_only.getdata(), together.getdata()):
                            if mask and max(abs(x-y) for x, y in zip(f, b)) > 30:
                                front_pixels += max(abs(x-y) for x, y in zip(f, actual)) < 6
                                back_pixels += max(abs(x-y) for x, y in zip(b, actual)) < 6
                        assert front_pixels > 20 and front_pixels > back_pixels*2, (front_pixels, back_pixels, 'Depth paint order reversed')
                        # Both rectangles contain this point; frontmost owns care.
                        path.write_text('garden 3 0\n'+front+back+empty*4)
                        d.game('Grow a Garden')
                        def plant_box(x,y):
                            bx,by=soil(x,y)
                            portrait=w<h
                            aw,ah=(1024,1536) if portrait else (1671,941)
                            sw,sh=w,w*ah//aw
                            if sh>h-tray: sh=h-tray; sw=sh*aw//ah
                            edge=min(sw*20//100,sh*24//100)*(80+(y-410)*20//320)//100
                            edge=max(36,edge)*s
                            return bx-edge/2,by-edge,bx+edge/2,by+10*s
                        f=plant_box(750,550); b=plant_box(750,470)
                        left,top,right,bottom=max(f[0],b[0]),max(f[1],b[1]),min(f[2],b[2]),min(f[3],b[3])
                        assert right-left>4 and bottom-top>4, ('Projected plant boxes do not overlap',f,b)
                        tap((round((left+right)/2),round((top+bottom)/2)))
                        assert saved()[0][2] > stamp-20 and saved()[1][2] == stamp-20, 'Hit order disagrees with paint depth'
                        d.key('Escape')
            print(f'local garden UI: {language}, {size}, held seed/free placement/cancel/care/reopen passed', flush=True)


if __name__ == '__main__':
    main()

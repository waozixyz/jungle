"""Play actual jigsaws with mouse input on an owned private display."""
import os
from pathlib import Path
import tempfile
import time
from runtime_test import Desktop, ROOT, OUTPUT, run


def saved(path):
    values = path.read_text().split()
    assert values[:2] == ['jigsaw', '2']
    count = (2,3,4,5,6,8)[int(values[3])]**2
    owners = list(map(int, values[10:10+count*2:2]))
    order = list(map(int, values[11:10+count*2:2]))
    positions = list(zip(map(int, values[10+count*2::2]), map(int, values[11+count*2::2])))
    return values, owners, order, positions


def geometry(width, height):
    height -= 56
    scale = min(width/400, height/740, 1.5)
    if width > height:
        scale = min(height/520, width/780, 1.5)
    w, h = int(width/scale), int(height/scale)
    if w > h:
        size = min(h-180, w*64//100)//2*2
        bx, by = 24, 80
        tx, ty, tw, th = bx+size+24, by, w-(bx+size+24)-24, size
    else:
        size = min(w-48, (h-180)*45//100)//2*2
        bx, by = (w-size)//2, 80
        tx, ty, tw = 24, by+size+24, w-48
        th = h-ty-72
    return scale, w, h, bx, by, size, tx, ty, tw, th


for language in ('en', 'de', 'es'):
    with tempfile.TemporaryDirectory(prefix='jungle-jigsaw-') as temporary:
        data = Path(temporary)
        (data/'language.txt').write_text(language)
        progress = data/'games/jungle.jigsaw/puzzle.txt'
        with Desktop(Path(os.environ.get('JUNGLE_TEST_BINARY', ROOT/'build/app/jungle')), data, screen_size='1280x1100') as desktop:
            desktop.resize(960,600)
            desktop.game('Jigsaw Puzzles')
            desktop.wait_jigsaw_setup('jigsaw-setup-'+language)
            desktop.key('Return')
            deadline = time.monotonic()+20
            ready = False
            while time.monotonic() < deadline:
                if progress.exists():
                    try:
                        ready = all(x > 0 and y > 0 for x,y in saved(progress)[3])
                    except (ValueError,AssertionError):
                        ready = False
                    if ready: break
                desktop.alive(); time.sleep(.1)
            assert ready, 'Puzzle did not reach its scattered table and save'
            # A loose drop stays where it was left and retains the grab offset.
            s,w,h,bx,by,size,tx,ty,tw,th = geometry(960,600)
            values,owners,order,positions = saved(progress)
            piece = order[-1]
            nx,ny = positions[piece]
            cx,cy = 16+(w-32)*nx/10000,72+(h-144)*ny/10000
            start=(round((cx+18)*s),round(56+cy*s))
            end=(round(w*.72*s),round(56+h*.61*s))
            run(['xdotool','mousemove','--window',desktop.window,str(start[0]),str(start[1])],desktop.env)
            run(['xdotool','mousedown','1'],desktop.env)
            try:
                time.sleep(.15)
                run(['xdotool','mousemove','--window',desktop.window,str(end[0]),str(end[1])],desktop.env)
                time.sleep(.2)
                desktop.capture('jigsaw-free-drag-'+language)
            finally:
                run(['xdotool','mouseup','1'],desktop.env)
            time.sleep(.3)
            _,owners,order,moved = saved(progress)
            assert not any(owners) and moved[piece] != positions[piece], 'Free drop returned to the tray'
            mx,my = 16+(w-32)*moved[piece][0]/10000,72+(h-144)*moved[piece][1]/10000
            assert abs(mx-(w*.72-18))<4 and abs(my-h*.61)<4, 'Drag lost the pickup offset'
            desktop.capture('jigsaw-free-table-'+language)
            for width,height in ((960,600),(390,844),(320,568),(844,390)):
                desktop.resize(width,height)
                picture = desktop.capture_actual(f'jigsaw-{language}-{width}-{height}')
                s,w,h,bx,by,size,tx,ty,tw,th = geometry(width,height)
                # Layout coordinates come from the game's independent view transform.
                def xy(x,y): return round(x*s), round(56+y*s)
                values,owners,order,positions = saved(progress)
                remaining = [piece for piece in reversed(order) if not owners[piece]]
                piece = remaining[0]
                nx,ny = positions[piece]
                cx,cy = 16+(w-32)*nx/10000,72+(h-144)*ny/10000
                px,py = bx+(piece%2+.5)*size/2, by+(piece//2+.5)*size/2
                start,end = xy(cx,cy),xy(px,py)
                # A free piece may cover a destination after resizing. Drag
                # across it rather than treating that piece as an empty slot.
                run(['xdotool','mousemove','--window',desktop.window,str(start[0]),str(start[1])],desktop.env)
                run(['xdotool','mousedown','1'],desktop.env)
                try:
                    time.sleep(.15)
                    run(['xdotool','mousemove','--window',desktop.window,str(end[0]),str(end[1])],desktop.env)
                    time.sleep(.2)
                    desktop.capture(f'jigsaw-selected-{language}-{width}-{height}')
                finally:
                    run(['xdotool','mouseup','1'],desktop.env)
                time.sleep(.3)
                _,after,_,_ = saved(progress)
                if after[piece] == 0:
                    desktop.capture(f'jigsaw-failed-{language}-{width}-{height}')
                    print('placement diagnostic',start,end,values,after,flush=True)
                assert after[piece] > 0, ('drag placement failed',language,width,height,piece)
                if sum(owner > 0 for owner in after) == 4: break
            assert sum(owner > 0 for owner in after) == 4, 'Puzzle did not complete'
            desktop.capture('jigsaw-complete-'+language)
            desktop.key('Escape')
            desktop.capture('jigsaw-resume-'+language)
            # Resume survives leaving the bundle and reopening it.
            desktop.key('Escape'); desktop.game('Jigsaw Puzzles')
            desktop.wait_jigsaw_setup('jigsaw-reopened-'+language)
            assert sum(owner > 0 for owner in saved(progress)[1]) == 4
            if language == 'en':
                # Exercise the largest hosted frame and the optional rules.
                for _ in range(5): desktop.key('Down')
                s,w,h,*_ = geometry(844,390)
                x,wc = w//2+12,w-(w//2+12)-24
                desktop.click_actual(round((x+wc*5/6)*s),round(56+194*s))
                desktop.click_actual(round((x+wc/4)*s),round(56+268*s))
                desktop.click_actual(round((x+wc*3/4)*s),round(56+268*s))
                desktop.key('Return')
                values,owners,order,positions = saved(progress)
                assert values[3:5] == ['5','2'] and values[8:10] == ['0','0'],values
                assert len(owners) == 64 and not any(owners)
                desktop.capture('jigsaw-64-competition')
                button=(w-64)//4
                desktop.click_actual(round((44+button*3+button/2)*s),round(56+(h-28)*s))
                assert saved(progress)[0][5] == '1','Next player did not pass the turn'
            log = (OUTPUT/'jungle.log').read_text()
            assert 'portable execution failed' not in log and 'cannot run' not in log, log
print('local jigsaw UI test: free drops, drag placements, completion, all three languages, four layouts and saved progress passed')

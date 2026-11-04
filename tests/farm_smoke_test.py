"""Full native Farm input, cursor, persistence and art on an owned private Xvfb."""
import os
import re
import ctypes as c
import hashlib
import json
from pathlib import Path
import tempfile
import time
from PIL import Image, ImageChops, ImageStat
import runtime_test as rt

ROOT=rt.ROOT
SCRATCH=ROOT/'local/art-development/four-gardens/qa'
EXPECTED_BINARY=None
PROCESSES=[]
CURSORS=[]
CROPS=('sunflower','tomato','carrot','strawberry','pumpkin','cabbage','beans','corn','cucumber')
DURATIONS=(24000,32000,18000,28000,45000,36000,24000,36000,28000)
# games/garden/farm.zi: a loose seed sows itself after FARM_REST ms untouched,
# then its sapling rises for FARM_RISE ms.
FARM_REST=3000;FARM_SOWN=4200
# Native cursor shapes (width, height, hotspot x, hotspot y) set in Farm's Hand().
HAND_CURSOR=(32,32,8,1);WATER_CURSOR=(32,28,2,12);BASKET_CURSOR=(30,32,15,16)

def f32(value): return c.c_float(value).value

def contain(width,height,iw,ih):
    scale=min(f32(f32(width)/f32(iw)),f32(f32(height)/f32(ih)))
    return scale,int(f32(f32(iw)*scale)),int(f32(f32(ih)*scale))

def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def checksum(data):
    total=0
    for byte in data: total=(total*131+byte)%1000000007
    return total

def save_path(state): return state/'games/jungle.garden/farm-four-gardens.txt'

def read_save(state):
    data=save_path(state).read_bytes(); lines=data.splitlines()
    assert lines[0]==b'farm-four 3' and len(lines)==268, (lines[0],len(lines))
    body=data[:data.rfind(b'\n',0,len(data)-1)+1]
    assert checksum(body)==int(lines[-1]),'Invalid native save checksum'
    return dict(economy=list(map(int,lines[1].split())),
                stock=[list(map(int,row.split())) for row in lines[2:11]],
                plots=[list(map(int,row.split())) for row in lines[11:-1]])

def fixture(state,*,coins=240,ripe=False,legacy=False):
    if legacy:
        rows=['farm-four 1','30 0 0 0 3']+['3 0']*6
        rows += ['3 1000 5000' if i%6==5 else '0 0 0' for i in range(24)]
        save_path(state).write_text('\n'.join(rows)+'\n'); return
    rows=['farm-four 3',f'{coins} 0 0 0 3']+['9 0']*9
    for i in range(256):
        if ripe and i<9:
            rows.append(f'{i+1} {DURATIONS[i]} 0 {1000+(i%3)*3500} {1000+(i//3)*3500} {FARM_SOWN}')
        else: rows.append('0 0 0 0 0 0')
    body=('\n'.join(rows)+'\n').encode()
    save_path(state).write_bytes(body+str(checksum(body)).encode()+b'\n')

def until(check,message,seconds=15):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if check(): return
        time.sleep(.10)
    raise AssertionError(message)

class CursorImage(c.Structure):
    _fields_=[('x',c.c_short),('y',c.c_short),('width',c.c_ushort),('height',c.c_ushort),
              ('xhot',c.c_ushort),('yhot',c.c_ushort),('serial',c.c_ulong),
              ('pixels',c.POINTER(c.c_ulong)),('atom',c.c_ulong),('name',c.c_char_p)]

def cursor(desktop):
    desktop.verify_server()
    x=c.CDLL('libX11.so.6');fix=c.CDLL('libXfixes.so.3')
    x.XOpenDisplay.argtypes=[c.c_char_p];x.XOpenDisplay.restype=c.c_void_p
    x.XFree.argtypes=[c.c_void_p];x.XCloseDisplay.argtypes=[c.c_void_p]
    fix.XFixesGetCursorImage.argtypes=[c.c_void_p];fix.XFixesGetCursorImage.restype=c.POINTER(CursorImage)
    connection=x.XOpenDisplay(desktop.env['DISPLAY'].encode());assert connection
    try:
        pointer=fix.XFixesGetCursorImage(connection);assert pointer
        try:
            v=pointer.contents
            pixels=tuple(int(v.pixels[i])&0xffffffff for i in range(v.width*v.height))
            result=(v.width,v.height,v.xhot,v.yhot,pixels)
        finally:x.XFree(pointer)
    finally:x.XCloseDisplay(connection)
    return result

def assert_cursor(desktop,shape,phase=''):
    # The app's default/pointing cursor may change independently of Farm art.
    # Tool cursors still require their exact trimmed shape and hotspot.
    expected={shape}
    if shape==HAND_CURSOR:
        expected={tuple(map(int,values)) for values in re.findall(
            r'\.width\s*=\s*(\d+),\s*\.height\s*=\s*(\d+),\s*'
            r'\.hotspot_x\s*=\s*(\d+),\s*\.hotspot_y\s*=\s*(\d+)',
            (ROOT/'host/jungle_cursor.zi').read_text())}
        assert expected, 'No application cursor declared'
    try:
        until(lambda:cursor(desktop)[:4] in expected,('Wrong native cursor',phase,expected,cursor(desktop)[:4]))
    except AssertionError:
        desktop.capture_actual('cursor-failure')
        raise
    value=cursor(desktop)
    assert any(pixel>>24 for pixel in value[4]),'Custom cursor is transparent'
    assert len(set(value[4]))>20,'Cursor bitmap did not load'
    CURSORS.append(dict(shape=value[:4],bitmap_sha256=hashlib.sha256(bytes().join(p.to_bytes(4,'little') for p in value[4])).hexdigest()))

class FarmUI:
    def __init__(self,desktop,width,height):
        self.d=desktop;self.w=width;self.h=height;self.layout(False);self.current=0
    def layout(self,entrance):
        self.header=0 if entrance else 56
        self.scale=min(f32(f32(min(self.w,self.h-self.header))/f32(400)),f32(1.8))
        self.lw=int(f32(f32(self.w)/self.scale));self.lh=int(f32(f32(self.h-self.header)/self.scale))
    def tap(self,x,y,pause=.3):
        rt.run(['xdotool','mousemove','--window',self.d.window,str(round(x)),str(round(y))],self.d.env)
        rt.run(['xdotool','mousedown','1'],self.d.env);time.sleep(.12)
        rt.run(['xdotool','mouseup','1'],self.d.env);time.sleep(pause);self.d.alive()
    def move(self,x,y):
        rt.run(['xdotool','mousemove','--window',self.d.window,str(round(x)),str(round(y))],self.d.env);time.sleep(.2)
    def logical(self,x,y,pause=.3):self.tap(x*self.scale,self.header+y*self.scale,pause)
    def logical_move(self,x,y):self.move(x*self.scale,self.header+y*self.scale)
    def garden(self,index):
        self.layout(True);self.current=0
        iw,ih=(1024,1536) if self.h>self.w else (1671,941)
        points=((260,530),(789,578),(238,798),(738,939)) if self.h>self.w else ((508,352),(1250,395),(361,511),(1183,618))
        scale,w,h=contain(self.lw,self.lh,iw,ih)
        x,y=points[index];self.logical((self.lw-w)//2+x*scale,(self.lh-h)//2+y*scale)
        self.layout(False);time.sleep(.2)
    def back(self):self.tap(25,27)
    def sky(self):self.d.key('Escape');self.layout(True)
    def bag(self):
        cell=(self.lw-24)//4;return 12+(cell-4)/2,self.lh-45
    def seeds(self):
        self.logical(*self.bag());self.current=0
    def choose(self,kind,shop=False):
        cell=(self.lw-32)//3;row=min(150,(self.lh-180)//3)
        self.logical(8+(kind-1)%3*(cell+8)+cell/2,52+(kind-1)//3*(row+4)+row/2)
    def cell(self,index):
        cell=(self.lw-24)//4;self.logical(12+index*cell+(cell-4)/2,self.lh-45)
    def tool(self,index):
        """Water (1) and basket (2) toggle; tapping the chosen one returns to the hand (0)."""
        if index==self.current:return
        if self.current:self.cell(self.current)
        if index:self.cell(index)
        self.current=index
    def soil_rect(self):
        iw,ih=(1024,1536) if self.lh>self.lw else (1536,1024)
        scale,w,h=contain(self.lw,self.lh,iw,ih)
        sx=(self.lw-w)//2+w*15//100;sw=w*70//100
        sy=(self.lh-h)//2+h*(36 if self.lh>self.lw else 43)//100
        sh=h*(39 if self.lh>self.lw else 32)//100
        return sx,sy,sw,sh
    def point(self,u,v,lift=0):
        sx,sy,sw,sh=self.soil_rect()
        return sx+u*sw/10000,sy+v*sh/10000-lift
    def observed(self,x,y):
        # Decode the actual integer X11 event using the app's float32 scale
        # and logical-pixel truncation, rather than weakening a UV tolerance.
        sx,sy,sw,sh=self.soil_rect()
        observed_x=int(f32(f32(round(x*self.scale))/self.scale))
        observed_y=int(f32(f32(round(self.header+y*self.scale)-self.header)/self.scale))
        return ((observed_x-sx)*10000//sw,(observed_y-sy)*10000//sh)
    def soil(self,u,v,pause=.3,move=False,lift=0):
        x,y=self.point(u,v,lift)
        if move:self.logical_move(x,y)
        else:self.logical(x,y,pause)
        return self.observed(x,y)
    def seed_lift(self):
        # A loose seed is drawn a quarter of its size above its soil point.
        sx,sy,sw,sh=self.soil_rect()
        return min(68,max(32,sw//10))//4
    def drag(self,start,end,capture=None,steps=10):
        """Press, slide in small steps like a finger, and let go; logical points."""
        (x0,y0),(x1,y1)=start,end
        self.logical_move(x0,y0)
        rt.run(['xdotool','mousedown','1'],self.d.env);time.sleep(.15)
        try:
            for i in range(1,steps+1):
                x=x0+(x1-x0)*i/steps;y=y0+(y1-y0)*i/steps
                rt.run(['xdotool','mousemove','--window',self.d.window,str(round(x*self.scale)),str(round(self.header+y*self.scale))],self.d.env)
                time.sleep(.04)
            time.sleep(.2)
            if capture:self.d.capture_actual(capture)
        finally:
            rt.run(['xdotool','mouseup','1'],self.d.env)
        time.sleep(.3);self.d.alive()
        return self.observed(x1,y1)
    def sow(self,u,v,capture=None):
        """Drag a new seed from the bag to a soil point; returns the observed u,v."""
        return self.drag(self.bag(),self.point(u,v),capture)
    def move_seed(self,start,end):
        return self.drag(self.point(*start,lift=self.seed_lift()),self.point(*end))
    def unsow(self,start):
        """Drag a loose seed back into the bag."""
        self.drag(self.point(*start,lift=self.seed_lift()),self.bag())
    def market(self):self.logical(self.lw-48,25)
    def buy(self):self.logical(8+(self.lw-24)//4,self.lh-32)
    def sell(self):self.logical(16+(self.lw-24)//2+(self.lw-24)//4,self.lh-32)
    def helpers(self):self.cell(3)
    def upgrade(self,index):
        w=(self.lw-36)//2;self.logical(12+index*(w+12)+w/2,self.lh//2-125+207)
    def menu(self):self.logical(44,25)
    def menu_item(self,index):
        row=min(62,(self.lh-70)//5);self.logical(self.lw/2,54+index*row+(row-7)/2)

def assert_paint(desktop,ui,entrance=False):
    ui.layout(entrance)
    portrait=ui.lh>ui.lw
    name=('assets/garden/art/scene-' if entrance else 'assets/garden/play/garden-')+('portrait' if portrait else 'landscape')+'.webp'
    source=Image.open(ROOT/name).convert('RGB')
    scale,w,h=contain(ui.lw,ui.lh,source.width,source.height)
    ox=(ui.lw-w)//2;oy=(ui.lh-h)//2
    # Compare low-frequency paint in independent areas; two-stage native
    # downsampling otherwise aliases individual watercolor leaf details.
    boxes=((15,220,90,350),(30,1300,120,1400)) if entrance and portrait else ((30,600,150,720),(1450,300,1530,380)) if entrance else ((1300,280,1380,350),(700,560,820,640)) if not portrait else ((580,180,680,250),(410,800,500,850))
    actual=desktop.capture_actual(f'{ui.w}-'+('chooser' if entrance else 'garden-background'))
    assert actual.size==(ui.w,ui.h)
    for box in boxes:
        region=tuple(round((ox if i%2==0 else oy)*ui.scale+ui.header*(i%2)+v*scale*ui.scale) for i,v in enumerate(box))
        expected=source.crop(box).resize((8,8),Image.Resampling.BILINEAR)
        got=actual.crop(region).resize((8,8),Image.Resampling.BILINEAR)
        difference=max(ImageStat.Stat(ImageChops.difference(expected,got)).mean)
        assert difference<10,('Native Farm paint/aspect/full viewport',name,box,difference)

def wait_farm(desktop,state,ui):
    desktop.verify_server()
    actual=digest(Path(f'/proc/{desktop.app.pid}/exe'))
    assert actual==(EXPECTED_BINARY or digest(desktop.binary)),'Running binary changed'
    PROCESSES.append(dict(pid=desktop.app.pid,private_xvfb_pid=desktop.server.pid,binary_sha256=actual))
    until(lambda:save_path(state).exists(),'Native Farm never saved')
    # A restart over an existing (even damaged) save finds the file at once,
    # so wait for the painted Farm itself, not a fixed delay.
    deadline=time.monotonic()+20
    while True:
        time.sleep(.7)
        try:assert_paint(desktop,ui,True);break
        except AssertionError:
            if time.monotonic()>deadline:raise
    ui.move(90,90);assert_cursor(desktop,HAND_CURSOR)

def start_state(path):
    path.mkdir(parents=True,exist_ok=True)
    for name in ('guide-seen','guide-sound','sound'):(path/(name+'.txt')).write_text('yes\n' if name=='guide-seen' else 'on\n')
    old=path/'games/jungle.garden/garden.txt';old.parent.mkdir(parents=True,exist_ok=True)
    old.write_text('garden 3 0\n'+'0 0 0 0 0 0 0 0\n'*6)
    return old,old.read_bytes()

def preserved(state,old,original):
    assert old.read_bytes()==original,'Legacy garden changed'
    assert (state/'sound.txt').read_text()=='on\n','Global audio changed'
    assert (state/'guide-sound.txt').read_text()=='on\n','Guide audio changed'
    assert not (state/'games/jungle.farm').exists(),'Duplicate Farm identity'


def run_orientation(binary,size,locale):
    w,h=size
    with tempfile.TemporaryDirectory(dir=SCRATCH,prefix=f'{w}-') as folder:
        state=Path(folder);old,original=start_state(state)
        with rt.Desktop(binary,state,extra_env={'TMPDIR':str(state)},screen_size='1400x2500') as d:
            d.resize(w,h);d.select_language(locale);d.game('Farm');ui=FarmUI(d,w,h);wait_farm(d,state,ui)
            positions=[(1234+i*1647,2468+i*1234) for i in range(4)]
            for garden,(u,v) in enumerate(positions):
                ui.garden(garden)
                if garden==0:
                    assert_paint(d,ui)
                    ui.move(25,27);assert_cursor(d,HAND_CURSOR)
                    ui.move(w-34,27);assert_cursor(d,HAND_CURSOR)
                ui.seeds()
                if garden==0:
                    d.capture_actual(f'{w}-owned-seed-inventory')
                    # Corn's bottom-row card overlays real soil in BOTH layouts
                    # and has owned stock, making a click-through observable.
                    ui.choose(8)
                    assert all(p[0]==0 for p in read_save(state)['plots']),'Inventory selection planted through'
                    assert read_save(state)['stock'][7][0]==1
                    ui.seeds()
                ui.choose(3)
                assert sum(p[0]!=0 for p in read_save(state)['plots'])==garden,'Seed drawer planted through on selection'
                stock=read_save(state)['stock'][2][0]
                # Drag a seed out of the bag and drop it anywhere on the soil.
                dropped=ui.sow(u,v,capture=f'{w}-seed-in-hand' if garden==0 else None)
                saved=read_save(state);p=saved['plots'][garden*64]
                assert p[0]==3 and p[3:5]==list(dropped) and p[5]<FARM_REST,('Free drop position lost',p,dropped,u,v)
                assert saved['stock'][2][0]==stock-1,'Seed not taken from the bag'
                if garden==0:
                    d.capture_actual(f'{w}-seed-resting-loose')
                    # Pick the loose seed up and move it; its rest starts over.
                    moved=ui.move_seed(dropped,(u+2500,v+1500))
                    p=read_save(state)['plots'][0]
                    assert p[3:5]==list(moved) and p[5]<FARM_REST,('Loose seed did not move',p,moved)
                    # Dragged back into the bag, it is a seed in the bag again.
                    ui.unsow(moved)
                    saved=read_save(state)
                    assert saved['plots'][0][0]==0 and saved['stock'][2][0]==stock,'Seed did not return to the bag'
                    dropped=ui.sow(u,v)
                    # Seeds never land on top of each other: a second drop on the
                    # same spot rolls beside it, then goes back to the bag.
                    ui.sow(u,v);saved=read_save(state);a,b=saved['plots'][0],saved['plots'][1]
                    assert a[3:5]==list(dropped) and b[0]==3 and (a[3]-b[3])**2+(a[4]-b[4])**2>=1000**2,('Overlapping seed accepted',a,b)
                    ui.unsow(tuple(b[3:5]))
                    assert read_save(state)['plots'][1][0]==0
                if garden==1:
                    # Left alone for a while, the seed sinks in and its sapling rises.
                    time.sleep((FARM_SOWN+600)/1000)
                    d.capture_actual(f'{w}-sapling-after-rest')
                    ui.sky();p=read_save(state)['plots'][64]
                    assert p[5]>=FARM_REST and p[1]==0 and p[2]==0,('Rest timer did not sow the seed',p)
                    ui.garden(garden)
                    ui.tool(1);ui.soil(*dropped,pause=.02)
                else:
                    # Water on a loose seed sows it at once.
                    ui.tool(1);ui.soil(dropped[0],dropped[1],pause=.02,lift=ui.seed_lift())
                    if garden==0:
                        d.capture_actual(f'{w}-water-sinks-seed');time.sleep(.5)
                        d.capture_actual(f'{w}-sapling-rising');time.sleep(1.0)
                        d.capture_actual(f'{w}-sapling-up')
                ui.soil(*dropped,move=True,lift=8);assert_cursor(d,WATER_CURSOR,f'{w} garden {garden+1} watered')
                saved=read_save(state);p=saved['plots'][garden*64]
                assert p[0]==3 and p[3:5]==list(dropped) and p[5]>=FARM_REST and p[2]>0,('Watering did not sow the seed',p,dropped)
                ui.tool(0);ui.sky()
            print(f'local Farm {w}x{h}: free drops, pick up and move, back to the bag, spacing, rest timer, water sowing, sapling rise and native cursor passed',flush=True)
            ui.garden(0)
            # A paused menu must not consume moisture or growing time.
            ui.menu();before=read_save(state);time.sleep(5.2)
            paused=read_save(state);assert paused['plots']==before['plots'],'Menu did not pause growth'
            d.capture_actual(f'{w}-menu-without-help')
            ui.menu_item(0)
            # First garden's real carrot finishes within one 20-second drink.
            # Visitors are active only in their currently open garden. The
            # first garden had the long drag checks, so its Goji is nearly due:
            # grow while the three lightly used gardens are open.
            deadline=time.monotonic()+45
            cycle=0
            while time.monotonic()<deadline:
                d.alive()
                # Return to the sky to flush, then inspect actual persisted time.
                ui.sky();saved=read_save(state)
                if all(saved['plots'][g*64][1]>=18000 for g in range(4)):break
                cycle+=1;ui.garden(1+cycle%3);time.sleep(.6)
            else:raise AssertionError(('Real crop growth never matured',[(g,saved['plots'][g*64]) for g in range(4)]))
            for garden,(u,v) in enumerate(positions):
                ui.garden(garden);ui.tool(2);ui.soil(u,v,move=True,lift=20);assert_cursor(d,BASKET_CURSOR)
                ui.soil(u,v,pause=.02,lift=20)
                if garden==0:
                    d.capture_actual(f'{w}-pluck-animation')
                    time.sleep(.30);d.capture_actual(f'{w}-crop-travels-to-basket')
                ui.sky()
            saved=read_save(state)
            assert saved['economy'][1]==4 and all(p[0]==0 for p in saved['plots']),(saved['economy'],[(i,p) for i,p in enumerate(saved['plots']) if p[0]])
            ui.garden(2);ui.market();before=saved['economy'][0];ui.sell()
            d.capture_actual(f'{w}-market-sale-animation')
            assert read_save(state)['economy'][0]==before+24
            ui.choose(9,True);ui.buy();assert read_save(state)['stock'][8][0]==1
            ui.back();ui.seeds();ui.choose(9);ui.sow(7654,4321);ui.sky()
            # Reopen with four simultaneously occupied, distinct gardens.
            for garden,kind in ((0,1),(1,2),(3,4)):
                ui.garden(garden);d.key(str(kind))
                ui.sow(1111+garden*1777,2222+garden*1333);ui.sky()
            saved=read_save(state)
            assert [saved['plots'][g*64][0] for g in range(4)]==[1,2,9,4]

            # Resize with planted arbitrary positions, then enter the same bed.
            resized=(420,900) if w>h else (960,600)
            d.resize(*resized);other=FarmUI(d,*resized);wait_farm(d,state,other);other.garden(2)
            assert read_save(state)['plots'][128][3:]==saved['plots'][128][3:]
            d.capture_actual(f'{w}-resized-preserved-position');other.sky();d.key('Escape')
            ui.move(100,100);assert_cursor(d,HAND_CURSOR,'no Farm tool cursor outside the Farm')
            preserved(state,old,original)
        with rt.Desktop(binary,state,extra_env={'TMPDIR':str(state)},screen_size='1400x2500') as d:
            d.resize(w,h);d.game('Farm');ui=FarmUI(d,w,h);wait_farm(d,state,ui)
            for garden in range(4):
                ui.garden(garden);restored=read_save(state)
                assert [(p[0],p[3],p[4]) for p in restored['plots']]==[(p[0],p[3],p[4]) for p in saved['plots']]
                ui.sky()
            d.key('Escape')
        preserved(state,old,original)
        print(f'local Farm {w}x{h}: real watered growth, four harvests, trade, new seed, resize, restart and data/audio preservation passed',flush=True)


def run_parity(binary):
    with tempfile.TemporaryDirectory(dir=SCRATCH,prefix='parity-') as folder:
        state=Path(folder);old,original=start_state(state);fixture(state,ripe=True)
        with rt.Desktop(binary,state,extra_env={'TMPDIR':str(state)},screen_size='1400x2500') as d:
            d.resize(960,600);d.game('Farm');ui=FarmUI(d,960,600);wait_farm(d,state,ui);ui.garden(0)
            d.capture_actual('all-nine-mature-crops');ui.tool(2)
            # The upper front crop overlaps the rear crop's base. The last
            # painted (front) crop owns the tap, regardless of its slot number.
            ui.soil(1000,1000,lift=-8)
            overlap=read_save(state)['plots']
            assert overlap[3][0]==0 and overlap[0][0]==1,'Picking ignored visual depth'
            for i in range(9):
                if i!=3:ui.soil(1000+i%3*3500,1000+i//3*3500,lift=20)
            assert read_save(state)['economy'][1]==9
            ui.market();ui.sell();assert read_save(state)['economy'][0]==360
            ui.back();ui.helpers();ui.upgrade(0);ui.upgrade(1)
            assert read_save(state)['economy'][0:4]==[210,9,1,1]
            d.capture_actual('helpers-purchased');ui.back()
            # Keyboard selection complements the already-tested seed drawer.
            for kind in range(1,10):
                d.key(str(kind));ui.current=0;ui.sow(1000+(kind-1)%3*3500,1000+(kind-1)//3*3500)
            planted=read_save(state)
            assert [p[0] for p in planted['plots'][:9]]==list(range(1,10))
            ui.sky();d.key('Escape')
        # Reopening resets the transient visitor clock, while all plant data
        # and purchased helpers must survive unchanged.
        with rt.Desktop(binary,state,extra_env={'TMPDIR':str(state)},screen_size='1400x2500') as d:
            d.resize(960,600);d.game('Farm');ui=FarmUI(d,960,600);wait_farm(d,state,ui);ui.garden(0)
            assert sum(p[0]!=0 for p in read_save(state)['plots'])==9
            # Observe one actual 18-frame Goji visit, not just a static image.
            time.sleep(21)
            d.capture_actual('goji-visit-early');time.sleep(.7);d.capture_actual('goji-visit-late')
            time.sleep(3);ui.sky();taken=read_save(state)
            assert sum(p[0]!=0 for p in taken['plots'])==8,'Goji did not take exactly one planted crop'
            assert sum(p[1]>0 for p in taken['plots'])==8,'Sprinkler did not grow plants'
            ui.garden(0);ui.menu();ui.menu_item(4)
            assert_cursor(d,HAND_CURSOR,'no Farm tool cursor after save and return')
        preserved(state,old,original)
        # Save corruption recovers a valid previous generation and preserves bytes.
        primary=save_path(state);bad=b'farm-four 2\ntruncated damaged save\n';primary.write_bytes(bad)
        with rt.Desktop(binary,state,extra_env={'TMPDIR':str(state)},screen_size='1400x2500') as d:
            d.resize(960,600);d.game('Farm');ui=FarmUI(d,960,600);wait_farm(d,state,ui)
            assert primary.with_suffix('.damaged').read_bytes()==bad
            read_save(state);d.key('Escape')
        preserved(state,old,original)
        # A second damaged generation must be protected, not overwrite evidence.
        primary.write_bytes(bad+b'2')
        before=primary.read_bytes()
        with rt.Desktop(binary,state,extra_env={'TMPDIR':str(state)},screen_size='1400x2500') as d:
            d.resize(960,600);d.game('Farm');time.sleep(1)
            ui=FarmUI(d,960,600);ui.move(90,90);assert_cursor(d,HAND_CURSOR)
            assert primary.read_bytes()==before
            d.capture_actual('damaged-save-protected');d.key('Escape')
        assert primary.read_bytes()==before
    print('local Farm: nine-crop art/actions, original upgrade economy, sprinkler, Goji, safe return and corruption recovery passed',flush=True)


def main():
    SCRATCH.mkdir(parents=True,exist_ok=True);rt.OUTPUT=SCRATCH/'captures'
    binary=Path(os.environ.get('JUNGLE_TEST_BINARY',ROOT/'build/app/jungle'))
    for size,locale in (((960,600),0),((420,900),1)):run_orientation(binary,size,locale)
    run_parity(binary)
    # A real failed backup rename must keep the primary and the in-memory
    # garden open. Removing only this test's obstruction permits a safe retry.
    with tempfile.TemporaryDirectory(dir=SCRATCH,prefix='failed-save-') as folder:
        state=Path(folder);old,original=start_state(state);fixture(state)
        primary=save_path(state);before=primary.read_bytes()
        obstruction=primary.with_suffix('.backup');obstruction.mkdir()
        with rt.Desktop(binary,state,extra_env={'TMPDIR':str(state)},screen_size='1400x2500') as d:
            d.resize(960,600);d.game('Farm');ui=FarmUI(d,960,600);wait_farm(d,state,ui)
            ui.garden(0);ui.sow(3141,5926)
            assert primary.read_bytes()==before,'Failed backup changed primary save'
            d.capture_actual('failed-save-garden-kept-open');ui.menu()
            row=min(62,(ui.lh-115)//5)
            ui.logical(ui.lw/2,54+4*row+(row-7)/2)
            assert primary.read_bytes()==before
            ui.move(90,90);assert_cursor(d,HAND_CURSOR)
            obstruction.rmdir();d.key('Escape');ui.sky()
            assert read_save(state)['plots'][0][0]==3,'Failed save did not retry'
            d.key('Escape')
        preserved(state,old,original)
    with tempfile.TemporaryDirectory(dir=SCRATCH,prefix='spanish-migration-') as folder:
        state=Path(folder);old,original=start_state(state);fixture(state,legacy=True)
        with rt.Desktop(binary,state,extra_env={'TMPDIR':str(state)},screen_size='1400x2500') as d:
            d.resize(420,900);d.select_language(2);d.game('Farm');ui=FarmUI(d,420,900);wait_farm(d,state,ui)
            restored=read_save(state)
            assert (state/'language.txt').read_text().strip()=='es'
            for garden in range(4):
                assert restored['plots'][garden*64+5][0]==3
                ui.garden(garden);ui.seeds();d.capture_actual(f'es-seeds-garden-{garden+1}');ui.back();ui.sky()
            d.key('Escape')
        preserved(state,old,original)
    print('local Farm integrated native tests: EN/DE/ES, orientations, free positions, full gameplay and persistence passed',flush=True)

def checked_main():
    global EXPECTED_BINARY
    binary=Path(os.environ.get('JUNGLE_TEST_BINARY',ROOT/'build/app/jungle')).resolve()
    paths={binary,binary.parent/'games/jungle-garden.zx',binary.parent/'assets/shared-assets.txt',
           ROOT/'tools/title_hotspots.json',ROOT/'tools/title_scenes.py',ROOT/'ziran.lock',
           Path(__file__).resolve()}
    for pattern in ('host/*.zi','retro/*.zi','games/garden/*.zi','assets/garden/play/*.webp'):
        paths.update(ROOT.glob(pattern))
    kryon=ROOT.parents[2]/'kryonlabs/kryon'
    for name in ('src/ui/cursor.zi','src/ui/tree.zi','src/ui/tree_input.zi',
                 'src/backend/desktop_runtime.zi','src/backend/widget_host.zi',
                 'src/backend/cairo_raster.zi'):
        paths.add(kryon/name)
    for name in ('wood-arrow-right.webp','wood-arrow-right-glow.webp'):
        paths.add(binary.parent/'assets/jungle/title/objects'/name)
    before={str(p):digest(p) for p in sorted(paths)}
    EXPECTED_BINARY=before[str(binary)]
    success=False
    started=time.time()
    SCRATCH.mkdir(parents=True,exist_ok=True)
    try:
        main()
        success=True
    finally:
        after={str(p):digest(p) if p.exists() else None for p in sorted(paths)}
        changed=[p for p in before if before[p]!=after[p]]
        receipt={'command':'python3 tests/farm_smoke_test.py','started':started,'finished':time.time(),
                 'result':'PASS' if success and not changed else 'FAIL','before':before,'after':after,
                 'changed_during_test':changed,'private_processes':PROCESSES,'native_cursors':CURSORS}
        (SCRATCH/'native-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        if success: assert not changed, ('Source/build changed during native test',changed)

if __name__=='__main__':checked_main()

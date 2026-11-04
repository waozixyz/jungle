"""Measure presented frames on diagonal-sign scenes without capturing pixels."""
import json
from pathlib import Path
import subprocess
import tempfile
import time
import runtime_test as rt
from title_window_smoke_test import PROBE


class FrameDesktop(rt.Desktop):
    def wait_menu(self, name):
        # The shared helper normally checks a startup image. FPS tests only
        # need a live window presenting frames and must never capture pixels.
        frames = Path(self.env['JUNGLE_FRAME_LOG'])
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            self.alive()
            self.verify_server()
            if frames.exists():
                with frames.open() as stream:
                    if stream.readline() and stream.readline():
                        return
            time.sleep(.1)
        raise AssertionError('Private app did not present startup frames')

    def capture(self, *args, **kwargs):
        raise AssertionError('Pixel capture is disabled for FPS tests')


def main():
    scratch=rt.ROOT/'local/art-development/rotated-text/fps'
    scratch.mkdir(parents=True,exist_ok=True)
    rt.OUTPUT=scratch/'runtime'
    probe=scratch/'frame-probe.so'
    subprocess.run(['cc','-shared','-fPIC','-O2','-x','c','-','-ldl','-o',str(probe)],
                   input=PROBE,text=True,check=True)
    data=json.loads((rt.ROOT/'tools/title_hotspots.json').read_text())
    results=[]
    for name in ('campus','jungle-path'):
        route=[]
        current='treehouse'
        for target in (('campus',) if name=='campus' else ('campus','jungle-path')):
            source=next(s for s in data['scenes'] if s['name']==current)
            route.append(str(next(i for i,h in enumerate(source['hotspots']) if h['target']=='scene:'+target)+1))
            current=target
        for width,height in ((960,600),(420,900)):
            with tempfile.TemporaryDirectory(dir=scratch) as folder:
                state=Path(folder)
                (state/'sound.txt').write_text('off\n')
                (state/'guide-seen.txt').write_text('yes\n')
                frames=state/'frames.txt'
                with FrameDesktop(rt.ROOT/'build/app/jungle',state,
                                extra_env={'LD_PRELOAD':str(probe),'JUNGLE_FRAME_LOG':str(frames)},
                                screen_size='1200x1600') as desktop:
                    desktop.resize(width,height)
                    time.sleep(3)
                    desktop.key('Home')
                    time.sleep(.3)
                    for key in route:
                        desktop.key(key)
                        time.sleep(.8)
                    time.sleep(10)
                    start=time.monotonic();time.sleep(5);end=time.monotonic()
                    desktop.alive();desktop.verify_server()
                    with frames.open() as stream:
                        times=[float(line) for line in stream if start<float(line)<end]
                    assert len(times)>2,(name,width,height,len(times))
                    intervals=[b-a for a,b in zip(times,times[1:])]
                    fps=(len(times)-1)/(times[-1]-times[0])
                    p95=sorted(intervals)[int(len(intervals)*.95)]*1000
                    print(f'local diagonal signs {name} {width}x{height}: {fps:.1f} FPS, p95 {p95:.1f} ms',flush=True)
                    results.append(dict(scene=name,size=[width,height],fps=round(fps,1),p95_ms=round(p95,1)))
                    (scratch/'result.json').write_text(json.dumps(results,indent=2)+'\n')
    (scratch/'result.json').write_text(json.dumps(results,indent=2)+'\n')
    assert all(item['fps']>=55 for item in results),results

if __name__=='__main__':
    main()

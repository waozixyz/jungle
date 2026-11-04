"""Owned-Xvfb window route, swaying leaves and still painted water, Back, and presented frame rate."""
import json
from pathlib import Path
import subprocess
import tempfile
import time
from PIL import ImageChops, ImageStat
import runtime_test as rt

PROBE = r'''
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
void SDL_RenderPresent(void *renderer) {
    static void (*present)(void*);
    static FILE *output;
    if (!present) present = dlsym(RTLD_NEXT, "SDL_RenderPresent");
    present(renderer);
    if (!output) output = fopen(getenv("JUNGLE_FRAME_LOG"), "a");
    if (output) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
        fprintf(output, "%.9f\n", t.tv_sec + t.tv_nsec / 1e9); fflush(output); }
}
'''

def main():
    scratch=rt.ROOT/'backup/title-window-smoke';scratch.mkdir(parents=True,exist_ok=True)
    source=scratch/'frame-probe.c'
    probe=scratch/'frame-probe.so'
    if not probe.exists() or not source.exists() or source.read_text()!=PROBE:
        source.write_text(PROBE)
        subprocess.run(['build-queue','--','cc','-shared','-fPIC','-O2',str(source),'-ldl','-o',str(probe)],check=True)
    rt.OUTPUT=scratch/'captures'
    data=json.loads((rt.ROOT/'tools/title_hotspots.json').read_text())
    window=next(i for i,h in enumerate(data['scenes'][0]['hotspots']) if h['id']=='window')+1
    results=[]
    for w,h in [(960,600),(420,900)]:
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            state=Path(folder)
            (state/'sound.txt').write_text('off\n');(state/'guide-seen.txt').write_text('yes\n')
            frames=state/'frames.txt'
            with rt.Desktop(rt.ROOT/'build/app/jungle',state,extra_env={'LD_PRELOAD':str(probe),'JUNGLE_FRAME_LOG':str(frames)},screen_size='1200x1600') as d:
                d.resize(w,h);d.key('Home');d.key(str(window));time.sleep(3)
                start=time.monotonic()
                first=d.capture_actual(f'window-{w}-first')
                time.sleep(3.2)
                last=d.capture_actual(f'window-{w}-last')
                end=time.monotonic()
                times=[float(t) for t in frames.read_text().splitlines() if start<float(t)<end]
                intervals=[b-a for a,b in zip(times,times[1:])]
                fps=(len(times)-1)/(times[-1]-times[0])
                p95=sorted(intervals)[int(len(intervals)*.95)]*1000
                print(f"local presented frames {w}x{h}: {fps:.1f} fps, p95 {p95:.1f} ms", flush=True)
                assert fps>=55,(w,h,fps,p95)
                scene=next(s for s in data['scenes'] if s['name']=='window')
                sw,sh=(1024,1536) if h>w else (1672,941)
                scale=max(w/sw,h/sh);dx=(w-sw*scale)/2;dy=(h-sh*scale)/2
                layers=json.loads((rt.ROOT/'tools/title_animations.json').read_text())['layers']
                name='window-portrait' if h>w else 'window'
                for layer in layers:
                    if layer['scene']!=name or layer['mode']!=0:continue
                    x,y,bw,bh=layer['rect'];box=tuple(map(round,(dx+x*scale,dy+y*scale,dx+(x+bw)*scale,dy+(y+bh)*scale)))
                    difference=ImageStat.Stat(ImageChops.difference(first.crop(box),last.crop(box))).mean
                    assert max(difference)>.03,(layer['path'],difference)
                d.key('Escape');time.sleep(.6)
                returned=d.capture_actual(f'window-{w}-back')
                assert max(ImageStat.Stat(ImageChops.difference(last,returned)).mean)>8
                results.append(dict(size=[w,h],fps=round(fps,1),p95_ms=round(p95,1),back=True))
    (scratch/'result.json').write_text(json.dumps(results,indent=2)+'\n')
    print('local window animation smoke:',json.dumps(results))
if __name__=='__main__':main()

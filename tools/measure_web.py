#!/usr/bin/env python3
"""Measure every Jungle activity in Canvas and native DOM, sequentially."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def browser_environment():
    env = dict(os.environ)
    for key in ('DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','GDK_DISPLAY','DBUS_SESSION_BUS_ADDRESS','SESSION_MANAGER'):
        env.pop(key, None)
    env.update(YUE_DESKTOP_RECOVERY='0', TMPDIR='/tmp')
    return env


def aggregate(runs):
    groups = defaultdict(list)
    for run in runs:
        for row in run['results']:
            groups[(row['backend'], row['viewport'], row['activity'], row['phase'])].append(row)
    rows = []
    for identity, samples in sorted(groups.items()):
        row = dict(zip(('backend','viewport','activity','phase'), identity))
        row['runs'] = len(samples)
        for key, value in samples[0].items():
            values = [sample[key] for sample in samples]
            if isinstance(value, (int,float)) and all(v is not None for v in values):
                row[key] = statistics.mean(values)
                if key in ('cpu_percent','mean_rss_mib','raf_p95_ms'):
                    row[key+'_min'] = min(values)
                    row[key+'_max'] = max(values)
                    row[key+'_stdev'] = statistics.stdev(values) if len(values)>1 else 0
            elif key not in row and value is None:
                row[key] = None
        rows.append(row)
    return rows


def markdown_report(payload):
    lines = ['# Jungle Canvas / DOM performance', '',
        f"{payload['runs_per_backend']} runs per backend, {payload['seconds_per_phase']} seconds per phase, desktop 960×600 and phone 390×844. Every activity has idle and active samples.", '',
        payload['method'], '', 'CPU is percent of one logical core; 100% means one full core. Aggregate RSS includes shared pages once per process; PSS apportions shared pages. rAF p95 measures browser animation callback cadence, not application rendering FPS.', '',
        '| Viewport | Activity | Phase | Backend | CPU % | RSS MiB | PSS MiB | JS heap MiB | rAF p95 ms | Long tasks |',
        '|---|---|---|---|---:|---:|---:|---:|---:|---:|']
    for row in payload['results']:
        f=lambda k: 'unknown' if row.get(k) is None else f"{row[k]:.1f}"
        lines.append('| '+' | '.join((row['viewport'],row['activity'],row['phase'],row['backend'],*(f(k) for k in ('cpu_percent','mean_rss_mib','mean_pss_mib','js_heap_mib','raf_p95_ms','long_tasks'))))+' |')
    means={backend:statistics.mean(r['cpu_percent'] for r in payload['results'] if r['backend']==backend and r['phase']=='active') for backend in ('canvas','dom')}
    lines += ['',f"CPU ratio DOM/Canvas (mean across active activities and viewports): {means['dom']/max(means['canvas'],.01):.2f}×.",'','The DOM edition uses native positioned HTML text, buttons, images and CSS. Canvas tiles are reserved for custom drawing, texture effects and icons. Both editions run the same Jungle app logic. The complete raw results, sample ranges, browser version and machine details are in performance.json.','']
    return '\n'.join(lines)


def html_report(payload):
    data=json.dumps(payload, ensure_ascii=False).replace('</','<\\/')
    return '''<!doctype html><meta charset="utf-8"><title>Jungle browser benchmarks</title>
<style>body{font:15px/1.5 system-ui,sans-serif;color:#263b31;background:#f7f8f4;max-width:1400px;margin:32px auto;padding:0 24px}h1{font-size:28px}h2{font-size:19px;margin-top:32px}p{max-width:1000px}select{font:inherit;margin:0 20px 14px 8px;padding:6px}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{border-bottom:1px solid #ccd4cc;padding:10px;text-align:right}th:first-child,td:first-child{text-align:left}thead{background:#e6ece3}small{color:#4c6154}a{color:#315f49}#summary{font-weight:600}.wrap{overflow:auto}code{font-size:13px}details{margin-top:24px}</style>
<h1>Jungle · Canvas and native DOM</h1><p><a id="source">Tested source revision</a></p><p id="method"></p><p id="summary"></p>
<label>Viewport<select id="viewport"><option>desktop</option><option>phone</option></select></label>
<label>Workload<select id="phase"><option>active</option><option>idle</option></select></label>
<div class="wrap"><table><thead><tr><th>Activity</th><th>Canvas CPU %</th><th>DOM CPU %</th><th>Canvas RSS MiB</th><th>DOM RSS MiB</th><th>Canvas rAF p95 ms</th><th>DOM rAF p95 ms</th><th>DOM native text / buttons / images</th></tr></thead><tbody id="rows"></tbody></table></div>
<p><small>CPU100% = one logical core. RSS sums the isolated browser's processes, including shared pages; the JSON also includes PSS when available. rAF is browser callback cadence, not actual application render FPS. Values are means; JSON includes run ranges and standard deviations. Software graphics in private headless Chromium do not predict hardware-accelerated phone performance.</small></p>
<details><summary>Method, environment and raw results</summary><pre id="environment"></pre><p><a href="performance.json">Download complete JSON</a> · <a href="performance-report.md">Markdown report</a></p></details>
<script>const data='''+data+''';source.href='https://github.com/waozixyz/jungle/commit/'+data.build.revision;source.textContent='Jungle '+data.build.version+' · tested source revision';method.textContent=data.method;summary.textContent=data.runs_per_backend+' runs per backend · '+data.seconds_per_phase+' seconds per phase · '+data.results.length+' activity / viewport / phase / backend comparisons';environment.textContent=JSON.stringify(data.environment,null,2);function render(){const subset=data.results.filter(r=>r.viewport===viewport.value&&r.phase===phase.value);rows.replaceChildren();for(const name of [...new Set(subset.map(r=>r.activity))]){const c=subset.find(r=>r.activity===name&&r.backend==='canvas'),d=subset.find(r=>r.activity===name&&r.backend==='dom');if(!c||!d)continue;const tr=document.createElement('tr');for(const value of [name,c.cpu_percent.toFixed(1),d.cpu_percent.toFixed(1),c.mean_rss_mib.toFixed(1),d.mean_rss_mib.toFixed(1),c.raf_p95_ms?.toFixed(1),d.raf_p95_ms?.toFixed(1),[d.native_text_nodes,d.native_buttons,d.native_images].map(Math.round).join(' / ')]){const td=document.createElement('td');td.textContent=value??'unknown';tr.append(td)}rows.append(tr)}}viewport.onchange=phase.onchange=render;render();</script>'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=float,default=3)
    parser.add_argument('--runs',type=int,default=3)
    parser.add_argument('--root',type=Path,default=ROOT/'build/web')
    parser.add_argument('--output',type=Path,default=ROOT/'backup/browser-benchmarks')
    args=parser.parse_args()
    assert args.runs>=1 and args.seconds>=1
    args.output.mkdir(parents=True,exist_ok=True)
    runs=[]
    for index in range(args.runs):
        # Alternate the backend order to reduce warm-up and order bias.
        for backend in (('canvas','dom') if index%2==0 else ('dom','canvas')):
            subprocess.run(['node','tests/web_performance_test.mjs','--root',str(args.root),'--backend',backend,'--seconds',str(args.seconds),'--output',str(args.output)],cwd=ROOT,env=browser_environment(),check=True)
            run=json.loads((args.output/f'performance-{backend}.json').read_text())
            (args.output/f'performance-{backend}-run-{index+1}.json').write_text(json.dumps(run,indent=2)+'\n')
            runs.append(run)
    first=runs[0]
    payload={'build':first['build'],'runtime_sizes':{r['backend']:r['runtime'] for r in runs},'generated_utc':datetime.now(timezone.utc).isoformat(),'generated_unix':time.time(),'runs_per_backend':args.runs,'seconds_per_phase':args.seconds,'method':first['method'],'environment':{k:first[k] for k in ('browser','os','cpu_model','logical_cpus','host_ram_gib','flags')},'results':aggregate(runs)}
    for directory in (args.output,args.root):
        (directory/'performance.json').write_text(json.dumps(payload,indent=2)+'\n')
        (directory/'performance-report.md').write_text(markdown_report(payload))
        (directory/'performance.html').write_text(html_report(payload))
    print(f"Completed {len(payload['results'])} comparisons; report: {args.output/'performance.html'}")


if __name__=='__main__':main()

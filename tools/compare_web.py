#!/usr/bin/env python3
"""Open the local Canvas and DOM editions in two owner-requested windows.

The supervisor, HTTP server and isolated browser profiles belong to this
launch. It never attaches to, captures or sends input to existing windows.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    web = ROOT / 'build/web'
    assert (web / 'dom.html').is_file(), 'Build both web editions first'
    browser = shutil.which('chromium') or shutil.which('google-chrome')
    assert browser, 'Chromium is required for the live comparison'
    work = ROOT / 'work/web-comparison'
    work.mkdir(parents=True, exist_ok=True)
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(web)))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    width, height, x, y = 1920, 1080, 0, 0
    bounds = subprocess.run(['xrandr', '--current'], capture_output=True, text=True)
    match = re.search(r' connected primary (\d+)x(\d+)\+(\d+)\+(\d+)', bounds.stdout)
    if not match:
        match = re.search(r' connected (\d+)x(\d+)\+(\d+)\+(\d+)', bounds.stdout)
    if match:
        width, height, x, y = map(int, match.groups())
    children = []
    receipts = []
    try:
        for index, (backend, page) in enumerate((('canvas', 'index.html'), ('dom', 'dom.html'))):
            url = f'http://127.0.0.1:{server.server_port}/{page}?metrics=1'
            profile = work / backend
            child = subprocess.Popen([browser, '--no-first-run', '--no-default-browser-check',
                '--disable-extensions', '--renderer-process-limit=2',
                '--user-data-dir=' + str(profile), '--new-window',
                f'--window-position={x + index * (width // 2)},{y + 28}',
                f'--window-size={width // 2},{height - 60}', url])
            children.append(child)
            receipts.append({'backend': backend, 'url': url, 'pid': child.pid})
            time.sleep(1)
        (work / 'live.json').write_text(json.dumps(receipts, indent=2) + '\n')
        print(json.dumps({'windows': receipts}), flush=True)
        while any(child.poll() is None for child in children):
            time.sleep(1)
    finally:
        server.shutdown()
        for child in children:
            if child.poll() is None:
                child.terminate()


if __name__ == '__main__':
    main()

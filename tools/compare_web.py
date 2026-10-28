#!/usr/bin/env python3
"""Keep a local server alive for two owner-requested comparison windows.

Browser launchers can hand off to an existing Chromium process and exit.
Their exit must never stop the server or close an owner's comparison window.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


def windows_for(class_name):
    try:
        result = subprocess.run(['xdotool', 'search', '--onlyvisible', '--class', class_name],
                                capture_output=True, text=True, timeout=3)
        return result.stdout.split() if result.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired):
        return []


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
    receipts = []
    for index, (backend, page) in enumerate((('canvas', 'index.html'), ('dom', 'dom.html'))):
        url = f'http://127.0.0.1:{server.server_port}/{page}?metrics=1'
        profile = work / (backend + '-live')
        class_name = 'JungleCanvasComparison' if backend == 'canvas' else 'JungleDomComparison'
        try:
            child = subprocess.Popen([browser, '--no-first-run', '--no-default-browser-check',
                '--disable-extensions', '--renderer-process-limit=2',
                '--user-data-dir=' + str(profile), '--class=' + class_name, '--new-window',
                f'--window-position={x + index * (width // 2)},{y + 28}',
                f'--window-size={width // 2},{height - 60}', url])
            time.sleep(1)
            receipts.append({'backend': backend, 'url': url, 'launcher_pid': child.pid,
                             'class': class_name, 'windows': windows_for(class_name)})
        except OSError as error:
            print(backend + ' launch failed: ' + str(error), flush=True)
    try:
        (work / 'live.json').write_text(json.dumps(receipts, indent=2) + '\n')
    except OSError as error:
        print('Could not save comparison receipt: ' + str(error), flush=True)
    print(json.dumps({'windows': receipts}), flush=True)
    # Keep this supervised app and its server alive independently of browser
    # wrapper PIDs. Do not terminate or send input to any browser window.
    threading.Event().wait()


if __name__ == '__main__':
    main()

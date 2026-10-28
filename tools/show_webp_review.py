#!/usr/bin/env python3
"""Open the owner's local before/after gallery without touching other windows."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import threading

ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = ROOT / 'work/webp-review'
    assert (folder/'review.json').is_file(), 'Run tools/preview_webp.py first'
    browser = shutil.which('chromium') or shutil.which('google-chrome')
    assert browser, 'Chromium is required'

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(folder)))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}/index.html'
    child = subprocess.Popen([browser, '--no-first-run', '--no-default-browser-check',
        '--disable-extensions', '--user-data-dir='+str(ROOT/'work/webp-review-browser'),
        '--class=JungleWebPReview', '--new-window', url])
    (folder/'live.json').write_text(json.dumps({'url': url, 'launcher_pid': child.pid})+'\n')
    print('WebP before/after review: '+url, flush=True)
    threading.Event().wait()


if __name__ == '__main__':
    main()

"""Exercise the packaged game at a nested URL in the existing private browser test."""
import functools
import http.server
import os
import subprocess
import threading
from pathlib import Path


class Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        return super().translate_path(path.removeprefix('/itch'))

    def log_message(self, *args):
        pass


def main():
    root = Path('build/itch-web').resolve()
    handler = functools.partial(Handler, directory=str(root))
    with http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            environment = dict(os.environ)
            for name in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY',
                         'DBUS_SESSION_BUS_ADDRESS', 'SESSION_MANAGER', 'GDK_DISPLAY'):
                environment.pop(name, None)
            environment['YUE_DESKTOP_RECOVERY'] = '0'
            url = f'http://127.0.0.1:{server.server_port}/itch/'
            subprocess.run(['node', 'tests/web_test.mjs', url],
                           env=environment, check=True)
        finally:
            server.shutdown()
            thread.join()


if __name__ == '__main__':
    main()

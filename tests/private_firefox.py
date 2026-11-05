"""Private headless Firefox transport for the map's existing browser assertions.

Python stdlib Marionette, following Kryon's avif_firefox_test.py. Profiles,
screenshots and logs belong to the caller's ignored output directory.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

from book_media_start_web_test import CDP, require


class Firefox(CDP):
    """Adapt only the browser operations used by world_map_web_test."""
    def __init__(self, connection):
        self.sock = connection
        self.sequence = 0
        greeting = self.receive()
        require(greeting.get('marionetteProtocol') == 3, str(greeting))
        self.command('WebDriver:NewSession', capabilities={})
        self.command('WebDriver:SetTimeouts', pageLoad=90000, script=30000, implicit=0)

    def exact(self, length):
        result = bytearray()
        while len(result) < length:
            chunk = self.sock.recv(length - len(result))
            if not chunk:
                raise EOFError('Firefox Marionette disconnected')
            result.extend(chunk)
        return bytes(result)

    def receive(self):
        header = bytearray()
        while True:
            byte = self.exact(1)
            if byte == b':':
                break
            require(byte.isdigit() and len(header) < 10, 'Invalid Marionette frame')
            header.extend(byte)
        size = int(header)
        require(size <= 32 * 1024 * 1024, 'Oversized Marionette frame')
        return json.loads(self.exact(size))

    def command(self, method, **params):
        self.sequence += 1
        payload = json.dumps([0, self.sequence, method, params]).encode()
        self.sock.sendall(str(len(payload)).encode() + b':' + payload)
        reply = self.receive()
        require(reply[:2] == [1, self.sequence] and reply[2] is None,
                f'{method}: response header={reply[:2]}, error={reply[2]}')
        return reply[3] or {}

    def evaluate(self, expression):
        result = self.command('WebDriver:ExecuteScript', script=f'return ({expression});',
                              args=[], newSandbox=False, sandbox=None,
                              line=1, filename='world-map-web-test')
        return result.get('value')

    def frame(self):
        # Keep a press visible to the app's frame loop before releasing it.
        # Software rendering can take longer than CDP's fixed 120 ms pause.
        self.command('WebDriver:ExecuteAsyncScript',
            script='const done=arguments[arguments.length-1]; '
                   'requestAnimationFrame(() => requestAnimationFrame(() => done(true)));',
            args=[], newSandbox=False, sandbox=None, line=1, filename='world-map-web-test')

    def call(self, method, **params):
        if method == 'Emulation.setDeviceMetricsOverride':
            width, height = params['width'], params['height']
            self.command('WebDriver:SetWindowRect', width=width, height=height)
            dw, dh = self.evaluate('[outerWidth-innerWidth, outerHeight-innerHeight]')
            self.command('WebDriver:SetWindowRect', width=width+dw, height=height+dh)
            require(self.evaluate('[innerWidth,innerHeight,devicePixelRatio]') == [width, height, 1],
                    'Firefox viewport differs from requested test dimensions')
            return {}
        if method == 'Page.navigate':
            return self.command('WebDriver:Navigate', url=params['url'])
        if method == 'Page.reload':
            return self.command('WebDriver:Refresh')
        if method == 'Page.captureScreenshot':
            return {'data': self.command('WebDriver:TakeScreenshot', full=False)['value']}
        if method == 'Input.dispatchMouseEvent':
            kind = params['type']
            actions = [dict(type='pointerMove', x=round(params['x']), y=round(params['y']),
                            duration=0, origin='viewport')]
            if kind != 'mouseMoved':
                require(kind in ('mousePressed', 'mouseReleased'), f'Unsupported pointer event: {kind}')
                actions.append(dict(type='pointerDown' if kind == 'mousePressed' else 'pointerUp', button=0))
            result = self.command('WebDriver:PerformActions', actions=[dict(type='pointer', id='map-pointer',
                                  parameters={'pointerType': 'mouse'}, actions=actions)])
            if kind != 'mouseMoved':
                self.frame()
            return result
        if method == 'Input.dispatchKeyEvent':
            key = {'Home': '\ue011', 'Enter': '\ue007', 'Escape': '\ue00c',
                   'ArrowRight': '\ue014'}.get(params['key'], params['key'])
            result = self.command('WebDriver:PerformActions', actions=[dict(type='key', id='map-keyboard',
                                  actions=[dict(type=params['type'], value=key)])])
            self.frame()
            return result
        raise AssertionError(f'Unsupported browser operation: {method}')


@contextmanager
def browser(work):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    binary = os.environ.get('FIREFOX') or shutil.which('firefox') or shutil.which('firefox-esr')
    require(binary, 'Firefox is required for --browser firefox')
    with socket.socket() as reserve:
        reserve.bind(('127.0.0.1', 0))
        port = reserve.getsockname()[1]
    environment = {k: v for k, v in os.environ.items() if k not in (
        'DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'SESSION_MANAGER')}
    environment.update(MOZ_HEADLESS='1', LIBGL_ALWAYS_SOFTWARE='1', YUE_DESKTOP_RECOVERY='0', TMPDIR=str(work))
    with tempfile.TemporaryDirectory(prefix='firefox-', dir=work) as temporary:
        profile = Path(temporary)
        (profile / 'user.js').write_text(f'user_pref("marionette.port", {port});\n'
            'user_pref("gfx.webrender.software", true);\n'
            'user_pref("layout.css.devPixelsPerPx", "1.0");\n'
            'user_pref("browser.shell.checkDefaultBrowser", false);\n')
        with (profile / 'firefox.log').open('wb') as log:
            process = subprocess.Popen([binary, '--headless', '--marionette', '--no-remote',
                '--profile', str(profile), 'about:blank'], env=environment,
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
            client = None
            connection = None
            diagnostic_path = work / f'firefox-{process.pid}.log'
            try:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline and process.poll() is None:
                    try:
                        connection = socket.create_connection(('127.0.0.1', port), timeout=1)
                        break
                    except OSError:
                        time.sleep(.1)
                require(connection is not None, f'Private Firefox startup failed; exit={process.poll()}')
                connection.settimeout(100)
                client = Firefox(connection)
                yield client
            except Exception:
                log.flush()
                with (profile / 'firefox.log').open('rb') as diagnostic:
                    diagnostic.seek(max(0, diagnostic.seek(0, 2) - 4000))
                    tail = diagnostic.read(4000).decode(errors='replace')
                print(f'Private Firefox pid={process.pid} exit={process.poll()} '
                      f'profile={profile} log={diagnostic_path}\n{tail}', file=sys.stderr, flush=True)
                raise
            finally:
                if client:
                    try:
                        client.command('WebDriver:DeleteSession')
                    except (OSError, EOFError, AssertionError):
                        pass
                if connection:
                    connection.close()
                # Only the process group created for this disposable profile.
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                log.flush()
                shutil.copyfile(profile / 'firefox.log', diagnostic_path)

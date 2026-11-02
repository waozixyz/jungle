"""Profile staging and browser recipe selection, without a live desktop or Node."""
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import wave

BROWSER = os.environ.get('CHROMIUM') or shutil.which('chromium') or shutil.which('google-chrome') or shutil.which('google-chrome-stable')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from speech_manifest import AddSpeechProfiles, ValidateSpeechManifest, FORMAT, PCM_FORMAT
from shared_assets import SpeechIndexText


def staging_test():
    with tempfile.TemporaryDirectory(dir=ROOT / 'work', prefix='speech-profiles-') as folder:
        root = Path(folder)
        voices = {}
        clips = {}
        profiles = {}
        for profile, speed, frames in [('normal', .8, 4000), ('slow', .65, 6000), ('fast', 1., 2000)]:
            name = 'assets/en/demo.wav' if profile == 'normal' else f'assets/speech-profiles/{profile}/en/demo.wav'
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(path), 'wb') as wav:
                wav.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
                wav.writeframes(b'\x10\x10' * frames)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            path.with_suffix('.speech.json').write_text(json.dumps({'sha256': digest}))
            profiles[profile] = {'speed': speed, 'voices': {'assets/en/demo.wav': name}}
            if profile == 'normal':
                clips[name] = dict(source=name, language='en', start_frame=0, frame_count=frames, sha256=digest)
                voices[name] = [dict(clip=name, start=0, frames=frames)]
        inventory = dict(format='jungle-speech-profiles-1', language='en', voice='af_bella', default='normal', profiles=profiles)
        (root / 'assets/speech-profiles.json').write_text(json.dumps(inventory))
        manifest = dict(format=FORMAT, audio=PCM_FORMAT, clips=clips, voices=voices, counts={})
        AddSpeechProfiles(manifest, root)
        ValidateSpeechManifest(manifest, root)
        assert [manifest['voices'][profiles[p]['voices']['assets/en/demo.wav']][0]['frames'] for p in profiles] == [4000, 6000, 2000]
        manifest['encoded'] = {name: {'path': f'assets/speech/{index}.ogg'} for index, name in enumerate(clips)}
        text = SpeechIndexText(manifest)
        assert 'voice|assets/speech-profiles/slow/en/demo.wav|' in text
        inventory['profiles']['slow']['voices']['assets/en/demo.wav'] = 'assets/../escape.wav'
        (root / 'assets/speech-profiles.json').write_text(json.dumps(inventory))
        try:
            AddSpeechProfiles(manifest, root)
        except ValueError:
            pass
        else:
            raise AssertionError('unsafe profile accepted')


def browser_test():
    assert BROWSER, 'speech profile browser test needs Chromium or Google Chrome (CHROMIUM)'
    source = (ROOT / 'web/index.html').read_text()
    script = source[source.index('const speechRate='):source.index('function packedAudio(')]
    test = r'''
const text='#jungle-speech-1\nvoice|assets/de/demo.wav|5\nvoice|assets/demo.wav|4\nvoice|assets/speech-profiles/fast/demo.wav|2\nvoice|assets/speech-profiles/slow/demo.wav|6\n';
speechResolved=parseSpeech(text);speechIndex=Promise.resolve(speechResolved);
(async()=>{
for(const [profile,expected] of [['normal',4],['slow',6],['fast',2],['invalid',4]]){
 if(speechVoiceFrames('assets/demo.wav',profile)!==expected)throw Error('frames '+profile);
 const bytes=await soundBytes('assets/demo.wav',()=>true,profile);
 if(bytes.length!==44+expected*2)throw Error('composition '+profile);
 if(speechVoiceFrames('assets/de/demo.wav',profile)!==5)throw Error('non-English fallback');
}
if(speechVoiceFrames('assets/missing.wav','slow')!==0)throw Error('missing voice');
document.body.textContent='PASS';
})().catch(error=>document.body.textContent='FAIL '+error.stack);
'''
    with tempfile.TemporaryDirectory(dir=ROOT / 'work', prefix='speech-browser-') as folder:
        path = Path(folder)
        page = path / 'test.html'
        page.write_text('<body>pending<script>' + script + test + '</script>')
        env = dict(os.environ, YUE_DESKTOP_RECOVERY='0')
        for key in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'SESSION_MANAGER']:
            env.pop(key, None)
        result = subprocess.run([BROWSER, '--headless', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage',
                                 '--no-first-run', '--no-default-browser-check', '--user-data-dir=' + str(path / 'profile'),
                                 '--dump-dom', '--virtual-time-budget=3000', page.as_uri()], env=env,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30)
        assert result.returncode == 0 and '<body>PASS' in result.stdout, result.stdout[:700]


if __name__ == '__main__':
    staging_test()
    browser_test()
    print('local speech profile tests: staging validation, exact frames, normal/slow/fast composition and fallback passed')


def installed_test(app):
    """Decode real staged Bella clips through native and browser composition."""
    import functools
    import http.server
    import threading
    app = Path(app).resolve()
    lines = (app / 'assets/speech.txt').read_text()
    paths = ['assets/jungle-book/sounds/en/simple/tiger.wav', 'assets/jungle-book/sounds/tiger.wav',
             'assets/jungle-book/story-sounds/en/porridge_00_cover.wav']
    specs = {row.split('|')[1]: row.split('|')[2] for row in lines.splitlines() if row.startswith('voice|')}
    for profile in ('normal', 'slow', 'fast'):
        for path in paths:
            selected = path if profile == 'normal' else 'assets/speech-profiles/' + profile + '/' + path[7:]
            frames = sum(int(token.split(':')[-1]) for token in specs[selected].split())
            with tempfile.TemporaryDirectory(dir=ROOT / 'work', prefix='speech-native-') as folder:
                output = Path(folder) / 'samples.pcm'
                subprocess.run([str(ROOT / 'build/tests/voice'), path, str(output), profile], cwd=app,
                               env={**os.environ, 'SDL_AUDIODRIVER': 'dummy'}, check=True)
                assert output.stat().st_size == frames * 2, (profile, path)
    source = (ROOT / 'web/index.html').read_text()
    script = source[source.index('const speechRate='):source.index('function packedAudio(')]
    script += '\nspeechResolved=parseSpeech(' + json.dumps(lines) + ');speechIndex=Promise.resolve(speechResolved);\n'
    script += 'const paths=' + json.dumps(paths) + ';const assetBytes=async path=>new Uint8Array(await(await fetch(path)).arrayBuffer());\n'
    script += '''
(async()=>{
for(const profile of ['normal','slow','fast'])for(const path of paths){
 const frames=speechVoiceFrames(path,profile);
 const wave=await soundBytes(path,()=>true,profile);
 if(wave.length!==44+frames*2||!frames)throw Error('actual composition '+profile+' '+path);
}
fetch('/__result',{method:'POST',body:'PASS actual Bella profiles'});
})().catch(error=>fetch('/__result',{method:'POST',body:'FAIL '+error.stack}));
'''
    page = ('<body><script>window.onerror=error=>fetch("/__result",{method:"POST",body:String(error)});</script><script>' + script + '</script>').encode()
    completed = threading.Event()
    outcome = []

    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_POST(self):
            outcome.append(self.rfile.read(min(2000, int(self.headers.get('Content-Length', 0)))).decode())
            self.send_response(200)
            self.end_headers()
            completed.set()

        def do_GET(self):
            if self.path == '/__profile_test.html':
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(page)
            else:
                super().do_GET()

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(app)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(dir=ROOT / 'work', prefix='bella-browser-') as folder:
            env = dict(os.environ, YUE_DESKTOP_RECOVERY='0')
            for name in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'SESSION_MANAGER']:
                env.pop(name, None)
            with (Path(folder) / 'chromium.log').open('w') as log:
                browser = subprocess.Popen([BROWSER, '--headless', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage',
                                            '--no-first-run', '--no-default-browser-check', '--user-data-dir=' + folder,
                                            f'http://127.0.0.1:{server.server_port}/__profile_test.html'], env=env,
                                           stdout=subprocess.DEVNULL, stderr=log)
                try:
                    assert completed.wait(30), 'browser did not finish real clip decoding'
                    assert outcome == ['PASS actual Bella profiles'], outcome
                finally:
                    browser.terminate()
                    browser.wait(timeout=10)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    print('local actual Bella playback: normal/slow/fast words, composed spelling and story decode at exact frames in native and Chromium')


if __name__ == '__main__' and len(sys.argv) == 3 and sys.argv[1] == '--installed':
    installed_test(sys.argv[2])

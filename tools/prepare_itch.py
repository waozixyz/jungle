"""Package Jungle's tested runtime, sharing media with its deployed website."""
import json
import re
import shutil
from pathlib import Path


def prepare(source=Path('build/web'), destination=Path('build/itch-web')):
    media = 'https://jungle.waozi.xyz/'
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns('assets'))
    index = destination / 'index.html'
    html = index.read_text()
    resolver = 'const url=new URL(path,location.href);'
    assert html.count(resolver) == 1, 'The browser asset resolver changed'
    html = html.replace(resolver,
        "const url=new URL(path,path.startsWith('assets/')?'" + media + "':location.href);")
    # Audio elements also resolve their relative paths against this base.
    # Load the runtime by an explicit page-relative URL so JS/Wasm stay on itch.
    html = html.replace('</head>', '<base href="' + media + '">\n</head>')
    runtime = r'<script src="jungle\.js(?:\?[^\"]*)?" defer></script>'
    assert len(re.findall(runtime, html)) == 1, 'The browser runtime entry changed'
    loader = "<script>const jungleRuntime=document.createElement('script');jungleRuntime.src=new URL('jungle.js?v='+buildRevision,location.href).href;document.body.appendChild(jungleRuntime);</script>"
    html = re.sub(runtime, lambda _: loader, html)
    html = re.sub(r'((?:src|href)=")/?(assets/[^\"]+)',
                  lambda match: match[1] + media + match[2], html)
    html = re.sub(r'((?:src|href)=")/(?!/)', r'\1', html)
    index.write_text(html)
    manifest_path = destination / 'site.webmanifest'
    manifest = json.loads(manifest_path.read_text())
    for name in ('id', 'start_url', 'scope'):
        manifest[name] = './'
    for icon in manifest['icons']:
        icon['src'] = media + icon['src'].lstrip('/')
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    for name in re.findall(r'(?:src|href)="([^"?#]+)', html):
        if name.startswith(media):
            assert (source / name[len(media):]).is_file() or name == media
        elif ':' not in name and not name.startswith('#'):
            assert not name.startswith('/'), f'Root-relative embed asset: {name}'
            assert (destination / name).is_file(), f'Missing embed asset: {name}'
    files = [path for path in destination.rglob('*') if path.is_file()]
    assert len(files) <= 1000, 'itch.io permits at most 1,000 browser files'
    assert sum(path.stat().st_size for path in files) <= 500_000_000
    assert all(path.stat().st_size <= 200_000_000 for path in files)
    print(f'Prepared {len(files)} browser files; media loads from jungle.waozi.xyz')


if __name__ == '__main__':
    prepare()

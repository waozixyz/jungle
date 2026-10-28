"""Prepare the same tested browser build for any embedded static host."""
import json
from pathlib import Path
import re
import shutil
import tempfile
import time
import zipfile

from asset_packs import validate_distribution

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='itch-stage-', dir=ROOT/'build') as stage:
        output = Path(stage)
        shutil.copytree(ROOT/'build/web', output, dirs_exist_ok=True)
        index = output/'index.html'
        html = re.sub(r'((?:src|href)=")/(?!/)', r'\1', index.read_text())
        index.write_text(html)
        manifest_path = output/'site.webmanifest'
        manifest = json.loads(manifest_path.read_text())
        for name in ('id', 'start_url', 'scope'):
            manifest[name] = './'
        for icon in manifest['icons']:
            icon['src'] = icon['src'].lstrip('/')
        manifest_path.write_text(json.dumps(manifest, indent=2)+'\n')
        for name in re.findall(r'(?:src|href)="([^"?#]+)', html):
            if ':' not in name and not name.startswith('#'):
                assert not name.startswith('/'), f'Root-relative embed asset: {name}'
                assert (output/name).is_file(), f'Missing embed asset: {name}'
        count, total = validate_distribution(output)
        # Include a ready-to-upload ZIP as well as Butler's directory. Inner
        # ZIP packs are assets, so the host sees only the outer ZIP's entries.
        archive_path = ROOT/'build/jungle-html5.zip'
        temporary = ROOT/'build/jungle-html5.zip.tmp'
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_STORED) as archive:
            for path in sorted(output.rglob('*')):
                if path.is_file():
                    archive.write(path, path.relative_to(output).as_posix())
        temporary.replace(archive_path)
        destination = ROOT/'build/itch-web'
        if destination.exists():
            previous = ROOT/'backup/web-builds'/('itch-'+str(time.time_ns()))
            previous.parent.mkdir(parents=True, exist_ok=True)
            destination.rename(previous)
        output.rename(destination)
        print(f'Embed distribution: {count} files, {total/1_000_000:.1f} MB; ZIP: {archive_path.relative_to(ROOT)}')


if __name__ == '__main__':
    main()

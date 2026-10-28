"""Render every picture/size from full-photo pieces on an owned private Xvfb."""
import json
from pathlib import Path
import shutil
import tempfile
import time

from runtime_test import Desktop, ROOT

sizes = (2, 3, 4, 5, 6, 8)
output = ROOT/'backup/jigsaw-runtime'
output.mkdir(parents=True, exist_ok=True)
receipts = []
with tempfile.TemporaryDirectory(prefix='jungle-jigsaw-sizes-') as temporary:
    data = Path(temporary)
    progress = data/'games/jungle.jigsaw/puzzle.txt'
    with Desktop(ROOT/'build/app/jungle', data) as desktop:
        desktop.resize(960, 600)
        desktop.game('Jigsaw Puzzles')
        for scene in range(3):
            for level, n in enumerate(sizes):
                desktop.key('Return')
                time.sleep(.3)
                values = progress.read_text().split()
                assert values[:4] == ['jigsaw', '2', str(scene), str(level)], values[:4]
                assert len(values) == 10+n*n*4, (scene, level, len(values))
                name = f'jigsaw-runtime-{scene}-{n}'
                picture = desktop.capture_actual(name)
                colors = picture.crop((12, 100, 948, 520)).getcolors(960*600)
                vivid = sum(count for count, color in colors or []
                            if max(color)-min(color)>45)
                assert vivid > 1000, (scene, n, 'Pieces did not show the full-color source picture')
                shutil.copy2(ROOT/'build/tests/ui'/f'{name}.png', output/f'{scene}-{n}.png')
                receipts.append({'scene': scene, 'grid': n, 'pieces': n*n, 'vivid_pixels': vivid})
                desktop.key('Escape')
                desktop.key('Down')
            desktop.key('Right')
(output/'all-sizes.json').write_text(json.dumps(receipts, indent=2)+'\n')
print('local jigsaw runtime test: all 462 pieces across three pictures and six sizes rendered from full photos')

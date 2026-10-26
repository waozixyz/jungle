#!/usr/bin/env python3
"""Install Jungle's launcher with a direct icon path, independent of shared icon caches."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
app = Path(sys.argv[1]).resolve()
data = Path(sys.argv[2]).resolve()
icon = app / 'assets/jungle/icons/icon-512.png'
assert icon.is_file(), icon
text = (ROOT / 'packaging/xyz.waozi.jungle.desktop').read_text()
text = text.replace('Icon=xyz.waozi.jungle\n', 'Icon=' + str(icon) + '\n')
entry = data / 'applications/xyz.waozi.jungle.desktop'
entry.parent.mkdir(parents=True, exist_ok=True)
new = entry.with_suffix('.desktop.new')
new.write_text(text)
new.chmod(0o644)
new.replace(entry)
print('Installed Jungle launcher with its own high-resolution icon')

#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 - <<'PY'
from pathlib import Path
import re
text=Path('CHANGELOG.md').read_text()
version=re.search(r'^## (\d+\.\d+\.\d+)\s*$',text,re.M)
if not version:raise SystemExit('Add a numeric release to CHANGELOG.md first')
Path('VERSION').write_text(version[1]+'\n')
print('Jungle Academy '+version[1])
PY

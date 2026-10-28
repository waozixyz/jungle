"""Test the complete upload at a nested URL using a private browser/profile."""
import os
import subprocess
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ)
    for name in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY',
                 'DBUS_SESSION_BUS_ADDRESS', 'SESSION_MANAGER', 'GDK_DISPLAY'):
        environment.pop(name, None)
    environment['YUE_DESKTOP_RECOVERY'] = '0'
    environment['JUNGLE_WEB_ROOT'] = str(root/'build/itch-web')
    subprocess.run(['node', 'tests/web_test.mjs'], cwd=root,
                   env=environment, check=True)


if __name__ == '__main__':
    main()

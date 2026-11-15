"""Runtime configuration shared by the native controller and client."""
import json
import os
from pathlib import Path

PREFIX = Path(os.environ.get('PREFIX', '/data/data/com.termux/files/usr'))
HOME = Path.home()
STATE = HOME / '.local/state/tablet-desktop'
CONFIG_FILE = HOME / '.config/tablet-desktop/config.json'
CONFIG = {'container': 'desktop', 'user': 'developer', 'display': ':1'}
if CONFIG_FILE.exists():
    CONFIG.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
CONTAINER, USER, DISPLAY = CONFIG['container'], CONFIG['user'], CONFIG['display']
DISPLAY_NUMBER = DISPLAY.removeprefix(':')
GUEST = PREFIX / 'var/lib/proot-distro/containers' / CONTAINER / 'rootfs'
if not GUEST.exists() and (PREFIX / 'var/lib/proot-distro/installed-rootfs' / CONTAINER).exists():
    GUEST = PREFIX / 'var/lib/proot-distro/installed-rootfs' / CONTAINER

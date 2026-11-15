"""Native GTK3 LibreOffice with a separate, initially copied user profile."""
import os
import shutil
import sys
from xml.sax.saxutils import escape
from desktop_config import PREFIX, HOME, GUEST, STATE, CONFIG, DISPLAY, USER

if len(sys.argv) < 2 or sys.argv[1] not in ('writer', 'calc', 'impress'):
    raise SystemExit('Unsupported office mode')
if any(not value.startswith(('https://', 'http://', 'file://')) for value in sys.argv[2:]):
    raise SystemExit('Office accepts validated URLs only')
profile = HOME / '.config/libreoffice-native'
if not profile.exists():
    original = GUEST / 'home' / USER / '.config/libreoffice/4'
    if original.is_dir():
        shutil.copytree(original, profile, ignore=shutil.ignore_patterns('.lock'))
    else:
        profile.mkdir(parents=True, mode=0o700)
profile.chmod(0o700)
for name, target in ((HOME / '.themes' / CONFIG['theme'], GUEST / 'usr/share/themes' / CONFIG['theme']),
                     (HOME / '.icons' / CONFIG.get('cursor_theme', 'Adwaita'), GUEST / 'usr/share/icons' / CONFIG.get('cursor_theme', 'Adwaita'))):
    if not name.exists() and not name.is_symlink() and target.is_dir():
        name.parent.mkdir(parents=True, exist_ok=True)
        name.symlink_to(target)
fonts = STATE / 'native-fonts.conf'
fonts.write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd"><fontconfig>'
                 '<include>' + escape(str(PREFIX / 'etc/fonts/fonts.conf')) + '</include>'
                 '<dir>' + escape(str(GUEST / 'usr/share/fonts')) + '</dir>'
                 '<dir>' + escape(str(GUEST / 'home' / USER / '.local/share/fonts')) + '</dir>'
                 '<cachedir>' + escape(str(HOME / '.cache/fontconfig-native-office')) + '</cachedir></fontconfig>', encoding='utf-8')
fonts.chmod(0o600)
for name in ('LIBGL_ALWAYS_SOFTWARE', 'LIBGL_ALWAYS_INDIRECT', 'LIBGL_DRI3_DISABLE', 'GALLIUM_DRIVER',
             'MESA_LOADER_DRIVER_OVERRIDE', 'VTEST_SOCKET_NAME', 'LD_PRELOAD', 'LD_LIBRARY_PATH', 'DBUS_SESSION_BUS_ADDRESS'):
    os.environ.pop(name, None)
os.environ.update(DISPLAY=DISPLAY, GDK_SCALE=str(CONFIG['scale']), GDK_DPI_SCALE='1',
                  GTK_THEME=CONFIG['theme'], GDK_GL='disable', NO_AT_BRIDGE='1',
                  SAL_USE_VCLPLUGIN='gtk3', SAL_DISABLE_OPENCL='1',
                  FONTCONFIG_FILE=str(fonts), XDG_DATA_DIRS=str(PREFIX / 'share') + ':' + str(GUEST / 'usr/share'),
                  XCURSOR_THEME=CONFIG.get('cursor_theme', 'Adwaita'), XCURSOR_SIZE=str(CONFIG.get('cursor_size', 48)),
                  XCURSOR_PATH=str(HOME / '.icons') + ':' + str(GUEST / 'usr/share/icons'),
                  PULSE_SERVER='127.0.0.1')
command = [str(PREFIX / 'lib/libreoffice/program/oosplash'), '-env:UserInstallation=' + profile.as_uri(),
           '--' + sys.argv[1], *sys.argv[2:]]
os.execv(command[0], command)

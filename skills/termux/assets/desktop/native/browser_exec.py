"""Fixed native Chromium environment; invoked by the same-UID desktop controller."""
import os
import re
import sys
from desktop_config import PREFIX, HOME, GUEST, CONFIG, DISPLAY

icd_name = CONFIG.get('native_browser_icd', '')
if not re.fullmatch(r'[A-Za-z0-9_.-]+\.json', icd_name):
    raise SystemExit('Invalid native browser Vulkan ICD filename')
present_mode = CONFIG.get('native_browser_present_mode', 'default')
if present_mode not in ('default', 'mailbox'):
    raise SystemExit('Invalid native browser present mode')
if any(not value.startswith(('https://', 'http://', 'file://', 'chrome:', 'about:')) for value in sys.argv[1:]):
    raise SystemExit('Native browser accepts validated URLs only')
icd = PREFIX / 'share/vulkan/icd.d' / icd_name
runtime = PREFIX / 'tmp/tablet-native-runtime'
runtime.mkdir(mode=0o700, exist_ok=True)
runtime.chmod(0o700)
for name in ('LIBGL_ALWAYS_SOFTWARE', 'LIBGL_ALWAYS_INDIRECT', 'LIBGL_DRI3_DISABLE', 'VTEST_SOCKET_NAME',
             'GDK_GL', 'LD_PRELOAD', 'DBUS_SESSION_BUS_ADDRESS', 'GDK_CORE_DEVICE_EVENTS'):
    os.environ.pop(name, None)
os.environ.update(DISPLAY=DISPLAY, GALLIUM_DRIVER='zink', MESA_LOADER_DRIVER_OVERRIDE='zink',
                  VK_DRIVER_FILES=str(icd), VK_ICD_FILENAMES=str(icd),
                  GDK_SCALE=str(CONFIG['scale']), GDK_DPI_SCALE='1', GTK_THEME='Adwaita:dark',
                  NO_AT_BRIDGE='1', XDG_RUNTIME_DIR=str(runtime), PULSE_SERVER='127.0.0.1')
os.environ.update(XCURSOR_THEME=CONFIG.get('cursor_theme', 'Adwaita'), XCURSOR_SIZE=str(CONFIG.get('cursor_size', 48)),
                  XCURSOR_PATH=str(HOME / '.icons') + ':' + str(GUEST / 'usr/share/icons') + ':' + str(PREFIX / 'share/icons'))
if present_mode == 'mailbox':
    os.environ['MESA_VK_WSI_PRESENT_MODE'] = 'mailbox'
command = [str(PREFIX / 'bin/chromium-browser'), '--no-sandbox', '--disable-dev-shm-usage',
           '--ozone-platform=x11', '--force-device-scale-factor=' + str(CONFIG['scale']),
           '--no-first-run', '--no-default-browser-check', '--force-dark-mode',
           '--disable-background-mode', '--use-gl=angle', '--use-angle=gles',
           '--user-data-dir=' + str(HOME / '.config/chromium-native')]
command += ['--', *sys.argv[1:]] if sys.argv[1:] else ['--restore-last-session']
os.execv(command[0], command)

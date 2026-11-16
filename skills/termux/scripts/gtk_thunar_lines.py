#!/usr/bin/env python3
"""Clone a GTK theme with Thunar-only thin toolbar separators, including dark variants."""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

from xfce_input import query, save, value


def patch_variants(target, rules):
    changed = {}
    for name in ('gtk.css', 'gtk-dark.css'):
        path = target / 'gtk-3.0' / name
        if not path.is_file():
            continue
        if path.is_symlink():
            raise ValueError('Review theme symlinks before patching')
        path.write_bytes(path.read_bytes() + b'\n' + rules)
        changed[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not changed:
        raise ValueError('Selected theme has no GTK 3 CSS files')
    return changed


def apply(args):
    old = value('xsettings', '/Net/ThemeName')
    if not old or not re.fullmatch(r'[\w .-]+', old):
        raise ValueError('Review the selected GTK theme name')
    source = next((p for p in (Path.home() / '.themes' / old, Path('/usr/share/themes') / old) if (p / 'gtk-3.0').is_dir()), None)
    if source is None:
        raise ValueError('Selected GTK 3 theme is not installed')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,70}', args.name):
        raise ValueError('Invalid derived theme name')
    target = Path.home() / '.themes' / args.name
    if target.exists() or target.is_symlink():
        raise ValueError('Choose an unused derived theme name')
    css = args.css or Path(__file__).resolve().parents[1] / 'assets/desktop/theme/thunar-thin-lines.css'
    rules = css.read_bytes()
    state = {'schema': 1, 'home': str(Path.home()), 'status': 'planned', 'theme_before': old,
             'theme_after': args.name, 'source': str(source), 'target': str(target)}
    if not args.apply:
        return state
    if args.state.exists():
        raise ValueError('State already exists; preserve the previous backup')
    args.state.parent.mkdir(parents=True, exist_ok=True)
    state['status'] = 'preparing'
    save(args.state, state)
    # Copying resolves the system theme's CSS links into independent user files.
    shutil.copytree(source, target)
    state['css_hashes'] = patch_variants(target, rules)
    if value('xsettings', '/Net/ThemeName') != old:
        raise ValueError('Theme changed during preparation; selection retained')
    query('-c', 'xsettings', '-p', '/Net/ThemeName', '-s', args.name)
    if value('xsettings', '/Net/ThemeName') != args.name:
        raise RuntimeError('GTK theme readback differs')
    state['status'] = 'passed'
    save(args.state, state)
    return state


def restore(args):
    state = json.loads(args.state.read_text(encoding='utf-8'))
    if state.get('schema') != 1 or state['home'] != str(Path.home()):
        raise ValueError('State belongs to another home or schema')
    current = value('xsettings', '/Net/ThemeName')
    if current not in (state['theme_before'], state['theme_after']):
        raise ValueError('GTK theme changed after apply; review before restoring')
    if args.apply:
        query('-c', 'xsettings', '-p', '/Net/ThemeName', '-s', state['theme_before'])
        if value('xsettings', '/Net/ThemeName') != state['theme_before']:
            raise RuntimeError('GTK theme restore readback differs')
        state['status'] = 'restored'
        save(args.state, state)
    return {'status': 'restored' if args.apply else 'planned', 'theme': state['theme_before']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('apply', 'restore'))
    parser.add_argument('--name', default='Greybird-dark-ThunarThin')
    parser.add_argument('--css', type=Path)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        if not shutil.which('xfconf-query'):
            raise RuntimeError('Install guest dependency: apt-get install xfconf')
        print(json.dumps(apply(args) if args.action == 'apply' else restore(args), ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

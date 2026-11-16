#!/usr/bin/env python3
"""Derive a flat Xfwm palette without changing frame geometry, or restore selection."""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

from xfce_input import query, save, value


def recolor(directory, background, text, inactive):
    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError('Install guest dependency: apt-get install python3-pil') from error
    # This workflow supports the XPM glyphs plus monochrome gradient overlays
    # used by Default-xhdpi derivatives. Reject other artwork before writing.
    overlays = []
    for path in directory.glob('*.png'):
        with Image.open(path) as original:
            image = original.convert('RGBA')
            if any(a and (r, g, b) not in ((0, 0, 0), (255, 255, 255)) for r, g, b, a in image.getdata()):
                raise ValueError(f'Review non-gradient overlay before recoloring: {path.name}')
            if not path.with_suffix('.xpm').is_file():
                raise ValueError(f'Missing XPM base for overlay: {path.name}')
            overlays.append((path, image.size))
    for path in directory.glob('*.xpm'):
        hover = 'prelight' in path.stem
        pressed = 'pressed' in path.stem
        fill = ('#c42b1c' if hover else '#b0271c') if path.name.startswith('close-') and (hover or pressed) else ('#454751' if pressed else '#3b3d44' if hover else background)

        def replace(match):
            slot = match.group(2)
            color = (inactive if slot.startswith('inactive') else text) if 'text_color' in slot else '#202126' if 'shadow' in slot else fill
            return match.group(1) + color

        data = path.read_text(encoding='utf-8')
        data = re.sub(r'(\bc\s+)#[0-9a-fA-F]{6}\s+s\s+([a-zA-Z0-9_]+)', replace, data)
        path.write_text(data, encoding='utf-8')
    # XPM already supplies the glyph and hit area. Remove only the validated
    # relief overlays, retaining every PNG's original canvas dimensions.
    for path, size in overlays:
        Image.new('RGBA', size, (0, 0, 0, 0)).save(path)
    merc = directory / 'themerc'
    data = merc.read_text(encoding='utf-8')
    for key, color in [('active_text_color', text), ('inactive_text_color', inactive)]:
        data = re.sub(rf'(?m)^{key}=.*$', key + '=' + color, data)
    merc.write_text(data, encoding='utf-8')


def apply(args):
    old = value('xfwm4', '/general/theme')
    if not old or not re.fullmatch(r'[\w .-]+', old):
        raise ValueError('Review the selected Xfwm theme')
    source = next((p / old / 'xfwm4' for p in (Path.home() / '.themes', Path('/usr/share/themes')) if (p / old / 'xfwm4').is_dir()), None)
    if source is None:
        raise ValueError('Current Xfwm theme is not installed')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,70}', args.name):
        raise ValueError('Invalid derived theme name')
    for color in (args.background, args.text, args.inactive):
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            raise ValueError('Colors must use #RRGGBB')
    target = Path.home() / '.themes' / args.name
    if target.exists() or target.is_symlink():
        raise ValueError('Choose an unused derived theme name')
    state = {'schema': 1, 'home': str(Path.home()), 'theme_before': old, 'theme_after': args.name,
             'source': str(source), 'target': str(target), 'status': 'planned'}
    if not args.apply:
        return state
    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError('Install guest dependency: apt-get install python3-pil') from error
    if args.state.exists():
        raise ValueError('State exists; preserve the previous backup')
    state['status'] = 'preparing'
    save(args.state, state)
    shutil.copytree(source, target / 'xfwm4')
    recolor(target / 'xfwm4', args.background, args.text, args.inactive)
    state['hashes'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (target / 'xfwm4').iterdir() if p.is_file()}
    if value('xfwm4', '/general/theme') != old:
        raise ValueError('Theme changed during preparation; selection retained')
    query('-c', 'xfwm4', '-p', '/general/theme', '-s', args.name)
    if value('xfwm4', '/general/theme') != args.name:
        raise RuntimeError('Xfwm theme readback differs')
    state['status'] = 'passed'
    save(args.state, state)
    return state


def restore(args):
    state = json.loads(args.state.read_text(encoding='utf-8'))
    if state.get('schema') != 1 or state.get('home') != str(Path.home()):
        raise ValueError('State belongs to another home or schema')
    current = value('xfwm4', '/general/theme')
    if current not in (state['theme_before'], state['theme_after']):
        raise ValueError('Theme changed after apply; review before restoring')
    if args.apply:
        query('-c', 'xfwm4', '-p', '/general/theme', '-s', state['theme_before'])
        if value('xfwm4', '/general/theme') != state['theme_before']:
            raise RuntimeError('Xfwm theme restore readback differs')
        state['status'] = 'restored'
        save(args.state, state)
    return {'status': 'restored' if args.apply else 'planned', 'theme': state['theme_before']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('apply', 'restore'))
    parser.add_argument('--name', default='Tablet-Chromium-Line')
    parser.add_argument('--background', default='#26282e')
    parser.add_argument('--text', default='#dadbe5')
    parser.add_argument('--inactive', default='#9699a3')
    parser.add_argument('--state', required=True, type=Path)
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

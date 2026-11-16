#!/usr/bin/env python3
"""Clone the selected Xfwm theme with one-pixel sides/bottom; preserve titlebar and buttons."""
import argparse
import hashlib
import json
import re
import shutil
import struct
from pathlib import Path

from xfce_input import query, save, value


def solid_xpm(width, height, color):
    rows = [f'"{width} {height} 1 1"', f'". c {color}"'] + ['"' + '.' * width + '"'] * height
    return '/* XPM */\nstatic char * image[] = {\n' + ',\n'.join(rows) + '\n};\n'


def normalize_overlays(folder, apply=False):
    """Xfwm composes PNG over XPM at 1:1; mismatched sizes leave rectangular seams."""
    changes = []
    for png in sorted(folder.glob('*.png')):
        xpm = png.with_suffix('.xpm')
        if not xpm.is_file():
            continue
        found = re.search(r'"(\d+)\s+(\d+)\s+\d+\s+\d+"', xpm.read_text(encoding='utf-8'))
        data = png.read_bytes()
        if found is None or data[:8] != b'\x89PNG\r\n\x1a\n' or len(data) < 24:
            raise ValueError('Unrecognized theme image: ' + png.name)
        canvas = tuple(map(int, found.groups()))
        size = struct.unpack('>II', data[16:24])
        if canvas == size:
            continue
        changes.append({'file': png.name, 'before': list(size), 'after': list(canvas)})
    if apply and changes:
        try:
            from PIL import Image
        except ImportError as error:
            raise RuntimeError('Install overlay repair dependency: python3 -m pip install Pillow (or apt-get install python3-pil)') from error
        for item in changes:
            path = folder / item['file']
            with Image.open(path) as image:
                image.resize(tuple(item['after']), Image.Resampling.NEAREST).save(path)
    return changes


def apply(args):
    old = value('xfwm4', '/general/theme')
    if not old or not re.fullmatch(r'[\w .-]+', old):
        raise ValueError('Review the current Xfwm theme name')
    sources = [Path.home() / '.themes' / old, Path('/usr/share/themes') / old]
    source = next((p for p in sources if (p / 'xfwm4/themerc').is_file()), None)
    if source is None:
        raise ValueError('Current theme files are unavailable; supply an installed Xfwm theme first')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,70}', args.name):
        raise ValueError('Invalid derived theme name')
    target = Path.home() / '.themes' / args.name
    if target.exists() or target.is_symlink() or target.resolve().parent != (Path.home() / '.themes').resolve():
        raise ValueError('Choose an unused theme name within ~/.themes')
    if any(p.is_symlink() for p in source.rglob('*')):
        raise ValueError('Review source theme symlinks before cloning')
    state = {'schema': 1, 'home': str(Path.home()), 'before': old, 'after': args.name, 'source': str(source), 'target': str(target), 'status': 'planned'}
    if not args.apply:
        return state
    if args.state.exists():
        raise ValueError('State exists; use a new file or restore it first')
    args.state.parent.mkdir(parents=True, exist_ok=True)
    state['status'] = 'preparing'
    save(args.state, state)
    shutil.copytree(source, target)
    for activity in ('active', 'inactive'):
        color = '#202024' if activity == 'active' else '#44444a'
        for part, width, height in [('left', 1, 48), ('right', 1, 48), ('bottom', 48, 1), ('bottom-left', 1, 1), ('bottom-right', 1, 1), ('top-left', 1, None), ('top-right', 1, None)]:
            path = target / 'xfwm4' / (part + '-' + activity + '.xpm')
            if height is None:
                text = path.read_text(encoding='utf-8')
                found = re.search(r'"\d+\s+(\d+)\s+\d+\s+\d+"', text)
                if found is None:
                    raise ValueError('Unrecognized titlebar cap format: ' + path.name)
                height = int(found.group(1))
            path.write_text(solid_xpm(width, height, color), encoding='utf-8')
            # Xfwm layers PNG over XPM at 1:1; an old overlay must not cover the new tile.
            path.with_suffix('.png').unlink(missing_ok=True)
    if getattr(args, 'normalize_overlays', False):
        state['normalized_overlays'] = normalize_overlays(target / 'xfwm4', apply=True)
    state['files'] = {str(p.relative_to(target)): hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob('*') if p.is_file()}
    if value('xfwm4', '/general/theme') != old:
        raise ValueError('Theme changed during preparation; original selection retained')
    query('-c', 'xfwm4', '-p', '/general/theme', '-s', args.name)
    if value('xfwm4', '/general/theme') != args.name:
        raise RuntimeError('Theme selection readback differs')
    state['status'] = 'passed'
    save(args.state, state)
    return state


def restore(args):
    state = json.loads(args.state.read_text(encoding='utf-8'))
    if state.get('schema') != 1 or state.get('home') != str(Path.home()):
        raise ValueError('State belongs to another schema or home')
    current = value('xfwm4', '/general/theme')
    if current not in (state['before'], state['after']):
        raise ValueError('Theme was changed after apply; review before restoring')
    if args.apply:
        query('-c', 'xfwm4', '-p', '/general/theme', '-s', state['before'])
        if value('xfwm4', '/general/theme') != state['before']:
            raise RuntimeError('Theme restore readback differs')
        state['status'] = 'restored'
        save(args.state, state)
    return {'status': 'restored' if args.apply else 'planned', 'theme': state['before']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('apply', 'restore'))
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--name', default='Tablet-Touch-Line')
    parser.add_argument('--normalize-overlays', action='store_true', help='Repair PNG/XPM size mismatches in the clone; needs Pillow only when mismatches exist')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(apply(args) if args.action == 'apply' else restore(args), ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

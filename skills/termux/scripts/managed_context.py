#!/usr/bin/env python3
"""Replace one reviewed AGENTS block from a UTF-8 file, with backup and readback."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
import uuid
from pathlib import Path


LEGACY_SSH_RULE = '- 日常管理必须通过设备自身的 SSH/IP 完成；ADB 只可用于用户授权的一次性安装、Android 权限配置或诊断。'
NATIVE_EXECUTION_RULES = '''- 按问题所属环境操作：Xfce 菜单、桌面设置和 guest 应用直接在当前 Xfce 界面或终端处理；原生 Termux 服务才使用 native 环境；Android 系统设置使用已有 ADB/系统界面。
- 沿用用户指定且已确认的设备和通道。USB/ADB 已连接时不额外尝试 LAN SSH、主机密钥登记或网络配置；只有任务明确涉及 SSH，或当前通道存在已核实的必要能力缺口时才处理相应连接需求。
- 用户纠正执行环境或通道后立即按纠正路径继续；ADB shell 不能读取 Termux 私有目录，不构成跳离可用 Xfce 终端的理由。'''
LEGACY_SSH_RECHECK = '- 改变应用、端口、能力或保活策略后，运行 `update-termux-agents` 刷新本节，并重新做纯局域网息屏验收。'
NATIVE_RECHECK_RULE = '- 改变应用、端口、能力或保活策略后，运行 `update-termux-agents` 刷新本节并验收本次相关功能；仅任务涉及 SSH/后台保活时才重做对应的纯局域网息屏验收。'


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replace_block(original: str, replacement: str, name: str, *, append=False) -> str:
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _-]{0,79}', name):
        raise ValueError('Invalid managed block name')
    begin, end = f'<!-- BEGIN {name} -->', f'<!-- END {name} -->'
    replacement = replacement.removeprefix('\ufeff').replace('\r\n', '\n').strip()
    if '\ufffd' in replacement or re.search(r'\?{3,}', replacement):
        raise ValueError('Replacement contains damaged text; supply a reviewed UTF-8 block file')
    if (not replacement.startswith(begin) or not replacement.endswith(end)
            or replacement.count(begin) != 1 or replacement.count(end) != 1):
        raise ValueError('Replacement must contain exactly the named block, including its markers')
    if original.count(begin) != original.count(end) or original.count(begin) > 1:
        raise ValueError('Incomplete or duplicate original markers')
    if begin not in original:
        if not append:
            raise ValueError('Original block missing; appending requires --append')
        return original + ('\n\n' if original and not original.endswith('\n\n') else '') + replacement + '\n'
    start, stop = original.index(begin), original.index(end)
    if start >= stop:
        raise ValueError('Original markers are reversed')
    return original[:start] + replacement + original[stop + len(end):]


def migrate_legacy_ssh_rule(original: str) -> str:
    """Repair only the known generated native block; leave user policies outside it intact."""
    name = 'android-termux-ssh managed context'
    begin, end = f'<!-- BEGIN {name} -->', f'<!-- END {name} -->'
    if begin not in original and end not in original:
        return original
    if original.count(begin) != 1 or original.count(end) != 1 or original.index(begin) >= original.index(end):
        raise ValueError('Incomplete or duplicate native context markers')
    block = original[original.index(begin):original.index(end) + len(end)]
    updated = block.replace(LEGACY_SSH_RULE, NATIVE_EXECUTION_RULES).replace(LEGACY_SSH_RECHECK, NATIVE_RECHECK_RULE)
    return replace_block(original, updated, name) if updated != block else original


def update_file(path: Path, block_file: Path, name: str, *, expected_sha256: str,
                backup_dir: Path | None = None, apply=False, append=False) -> dict:
    path, block_file = Path(path), Path(block_file)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Target must be an existing regular file, not a symlink')
    old = path.read_bytes()
    if digest(old) != expected_sha256:
        raise ValueError('Target changed since review; read the current file before retrying')
    block = block_file.read_bytes()
    new = replace_block(old.decode('utf-8'), block.decode('utf-8'), name, append=append).encode('utf-8')
    result = {'status': 'skipped', 'changed': new != old, 'before_sha256': digest(old),
              'block_sha256': digest(block), 'after_sha256': digest(new), 'name': name}
    if not apply:
        return result
    if new == old:
        return dict(result, status='passed', readback_verified=True)
    if backup_dir is None:
        raise ValueError('--backup-dir is required with --apply')
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f'{path.name}.{uuid.uuid4().hex}.bak'
    with backup.open('xb') as stream:
        stream.write(old)
        stream.flush()
        os.fsync(stream.fileno())
    backup.chmod(0o600)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name + '.', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(new)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(stat.S_IMODE(path.stat().st_mode))
        if path.is_symlink() or path.read_bytes() != old:
            raise ValueError('Target changed during preparation; backup retained, target not replaced')
        os.replace(temporary, path)
        if path.read_bytes() != new:
            raise RuntimeError(f'Readback differs; inspect the target and backup at {backup}')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return dict(result, status='passed', readback_verified=True, backup=str(backup))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--block-file', type=Path, required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--backup-dir', type=Path)
    parser.add_argument('--append', action='store_true')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = update_file(args.file, args.block_file, args.name, expected_sha256=args.expected_sha256,
                             backup_dir=args.backup_dir, apply=args.apply, append=args.append)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result['status'] == 'passed' else 4
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error),
                          'name': args.name, 'expected_sha256': args.expected_sha256}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

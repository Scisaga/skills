#!/usr/bin/env python3
from __future__ import annotations

import platform
import sys

from runtime_utils import BUNDLED_FONT_PATH, REQUIREMENTS_PATH, SKILL_ROOT, WORKFLOW_DEPENDENCIES, find_missing_dependencies


def main() -> int:
    print(f"Skill root: {SKILL_ROOT}")
    print(f"Python: {sys.executable}")
    print(f"Python version: {platform.python_version()}")
    print(f"requirements.txt: {'ok' if REQUIREMENTS_PATH.is_file() else 'missing'} -> {REQUIREMENTS_PATH}")
    print(f"Bundled font: {'ok' if BUNDLED_FONT_PATH.is_file() else 'missing'} -> {BUNDLED_FONT_PATH}")
    print("")

    all_ok = True
    for workflow, specs in WORKFLOW_DEPENDENCIES.items():
        missing = find_missing_dependencies(specs)
        if missing:
            all_ok = False
            packages = ", ".join(f"{package} (import {module})" for module, package in missing)
            print(f"[missing] {workflow}: {packages}")
        else:
            print(f"[ok] {workflow}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

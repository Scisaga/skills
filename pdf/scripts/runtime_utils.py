from __future__ import annotations

import importlib
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_PATH = SKILL_ROOT / "bootstrap.sh"
REQUIREMENTS_PATH = SKILL_ROOT / "requirements.txt"
BUNDLED_FONT_PATH = SKILL_ROOT / "assets" / "fonts" / "Consolas-with-Yahei.ttf"

WORKFLOW_DEPENDENCIES: dict[str, list[tuple[str, str]]] = {
    "replace-page": [("fitz", "PyMuPDF")],
    "watermark": [("fitz", "PyMuPDF"), ("PIL", "Pillow")],
    "seam-seal": [("PyPDF2", "PyPDF2"), ("reportlab", "reportlab"), ("PIL", "Pillow")],
    "overlay-watermark": [("PyPDF2", "PyPDF2"), ("reportlab", "reportlab"), ("PIL", "Pillow")],
    "page-ops": [("PyPDF2", "PyPDF2")],
    "image-convert": [("fitz", "PyMuPDF"), ("PIL", "Pillow")],
    "batch": [
        ("fitz", "PyMuPDF"),
        ("PIL", "Pillow"),
        ("PyPDF2", "PyPDF2"),
        ("reportlab", "reportlab"),
    ],
}


def dedupe_dependencies(specs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    ordered: list[tuple[str, str]] = []
    for item in specs:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def find_missing_dependencies(specs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    missing: list[tuple[str, str]] = []
    for module_name, package_name in dedupe_dependencies(specs):
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing.append((module_name, package_name))
    return missing


def format_missing_dependency_message(specs: list[tuple[str, str]]) -> str:
    missing = find_missing_dependencies(specs)
    if not missing:
        return ""

    lines = ["检测到缺失依赖："]
    for module_name, package_name in missing:
        lines.append(f"- {package_name}（import {module_name}）")

    lines.append("")
    lines.append(f"请先运行：bash {BOOTSTRAP_PATH}")
    lines.append(f"或手动执行：python3 -m pip install -r {REQUIREMENTS_PATH}")
    return "\n".join(lines)


def ensure_dependencies(specs: list[tuple[str, str]]) -> None:
    message = format_missing_dependency_message(specs)
    if message:
        raise RuntimeError(message)

#!/usr/bin/env python3
"""Install, resolve and embed the fonts used by an offline presentation."""

from __future__ import annotations

import argparse
import base64
import io
import json
import shutil
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen

from production_common import file_hash


ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "assets" / "html" / "fonts.json"
CACHE = ROOT / ".cache" / "fonts"
SANS = ("Inter", "Source Han Sans SC")
SERIF = ("Source Han Serif SC",)
MONO = ("JetBrains Mono", "Source Han Sans SC")
ALIASES = {
    "arial": SANS,
    "sans-serif": SANS,
    "system-ui": SANS,
    "serif": SERIF,
    "monospace": MONO,
    "consolas": MONO,
    "times new roman": SERIF,
    "microsoft yahei": ("Source Han Sans SC",),
    "微软雅黑": ("Source Han Sans SC",),
    "noto sans cjk sc": ("Source Han Sans SC",),
    "pingfang sc": ("Source Han Sans SC",),
    "simsun": SERIF,
    "宋体": SERIF,
}
INTERNAL_NAMES = {
    "Source Han Sans SC": "Slides CJK Sans",
    "Source Han Serif SC": "Slides CJK Serif",
}


def catalog() -> list[dict]:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def source_path(asset: dict) -> Path:
    return CACHE / asset["file"]


def check_font(asset: dict) -> Path:
    path = source_path(asset)
    if not path.is_file() or file_hash(path) != asset["sha256"]:
        raise RuntimeError(f"缺少或损坏的内置字体资源 {path.name}，请运行 bootstrap --stage static")
    return path


def catalog_files() -> dict[str, dict]:
    return {
        asset["file"]: asset
        for family in catalog()
        for asset in (family["license"], *family["faces"].values())
    }


def install_fonts() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    for asset in catalog_files().values():
        path = source_path(asset)
        if path.is_file() and file_hash(path) == asset["sha256"]:
            continue
        with tempfile.TemporaryDirectory(dir=CACHE) as work:
            incoming = Path(work) / path.name
            with urlopen(asset["url"], timeout=90) as response, incoming.open("wb") as out:
                shutil.copyfileobj(response, out)
            if file_hash(incoming) != asset["sha256"]:
                raise ValueError(f"字体 SHA-256 不匹配 {path.name}")
            incoming.replace(path)
        print(f"OK  font: {path.name}")


def embed_data(payload: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(payload).decode("ascii")


@dataclass(frozen=True)
class Face:
    family: str
    weight: tuple[int, int]
    style: str
    path: Path
    license: Path
    asset: str | None = None


def family_list(value: str) -> list[str]:
    from tinycss2 import parse_component_value_list, serialize

    families = []
    group = []
    for token in parse_component_value_list(value):
        if token.type == "literal" and token.value == ",":
            families.append(serialize(group).strip().strip("\"'"))
            group = []
        else:
            group.append(token)
    return [name for name in (*families, serialize(group).strip().strip("\"'")) if name]


def font_weight(value: str) -> tuple[int, int]:
    if value in ("normal", "bold"):
        weight = 400 if value == "normal" else 700
        return weight, weight
    weights = [int(item) for item in value.split()]
    if len(weights) not in (1, 2) or not 1 <= weights[0] <= weights[-1] <= 1000:
        raise ValueError(f"无效的字体字重 {value!r}")
    return weights[0], weights[-1]


def choose_face(faces: list[Face], weight: int, style: str) -> Face:
    styled = [face for face in faces if face.style == style]
    variants = styled or [face for face in faces if face.style == "normal"] or faces

    def distance(face: Face) -> tuple[int, int]:
        low, high = face.weight
        if low <= weight <= high:
            return 0, 0
        if 400 <= weight <= 500:
            if weight < low <= 500:
                return 1, low - weight
            if high < weight:
                return 2, weight - high
            return 3, low - weight
        if weight < 400:
            return (1, weight - high) if high < weight else (2, low - weight)
        return (1, low - weight) if low > weight else (2, weight - high)

    return min(variants, key=distance)


class Fonts:
    def __init__(self) -> None:
        self.assets = catalog_files()
        self.builtin = {
            family["family"].casefold(): [
                Face(
                    family["family"], (int(weight), int(weight)), "normal",
                    source_path(asset), source_path(family["license"]), asset["file"],
                )
                for weight, asset in family["faces"].items()
            ]
            for family in catalog()
        }
        self.project_faces: dict[str, list[Face]] = {}
        self.cmaps: dict[Path, set[int]] = {}
        self.used: dict[Face, set[int]] = {}
        self.substitutions: dict[str, set[str]] = {}

    def add(self, face: Face) -> None:
        self.project_faces.setdefault(face.family.casefold(), []).append(face)

    def cmap(self, face: Face) -> set[int]:
        from fontTools.ttLib import TTFont

        if face.path not in self.cmaps:
            if face.asset:
                check_font(self.assets[face.asset])
            with TTFont(face.path, lazy=True) as font:
                self.cmaps[face.path] = set(font.getBestCmap() or {})
        return self.cmaps[face.path]

    def select(self, run: dict) -> str:
        faces = []
        names = family_list(run["family"])
        for name in names:
            key = name.casefold()
            if key in self.project_faces:
                groups = [self.project_faces[key]]
            else:
                groups = [self.builtin[alias.casefold()] for alias in ALIASES.get(key, ())]
                if key in self.builtin:
                    groups = [self.builtin[key]]
                elif groups and key not in {"sans-serif", "serif", "monospace", "system-ui"}:
                    mapped = " + ".join(group[0].family for group in groups)
                    self.substitutions.setdefault(f"{name} → {mapped}", set()).add(run["page"])
            for group in groups:
                face = choose_face(group, round(float(run["weight"])), run["style"])
                if face not in faces:
                    faces.append(face)

        characters = {
            ord(char) for char in run["text"]
            if char not in "\n\r\t" and unicodedata.category(char) != "Cf"
            and not 0xFE00 <= ord(char) <= 0xFE0F
        }
        selected = []
        remaining = set(characters)
        for face in faces:
            # Retain the shaping characters and spaces covered by the chosen face.
            covered = remaining & self.cmap(face)
            if covered or not characters:
                self.used.setdefault(face, set()).update(covered | {32})
                selected.append(face)
                remaining -= covered
            if not remaining:
                break
        if not selected or remaining:
            missing = " ".join(f"{chr(cp)} (U+{cp:04X})" for cp in sorted(remaining)[:12])
            raise ValueError(f"{run['page']} 字体 {run['family']} 缺少所需字形或字体文件 {missing}")

        return ", ".join(json.dumps(self.display_name(face), ensure_ascii=False) for face in selected)

    @staticmethod
    def display_name(face: Face) -> str:
        return INTERNAL_NAMES.get(face.family, face.family) if face.asset else face.family

    def styles(self) -> tuple[str, dict[str, Path], list[dict]]:
        from fontTools import subset
        from fontTools.ttLib import TTFont
        from fontTools.varLib.instancer import instantiateVariableFont

        rules = []
        licenses = {}
        inputs = []
        for face, characters in self.used.items():
            name = self.display_name(face)
            weight = " ".join(map(str, dict.fromkeys(face.weight)))
            if face.asset:
                license_asset = self.assets[face.license.name]
                check_font(license_asset)
                options = subset.Options()
                options.layout_features = ["*"]
                with TTFont(face.path, recalcTimestamp=False) as font:
                    if "fvar" in font:
                        axes = {axis.axisTag: axis.defaultValue for axis in font["fvar"].axes}
                        axes["wght"] = face.weight[0]
                        instantiateVariableFont(font, axes, inplace=True)
                    subsetter = subset.Subsetter(options=options)
                    subsetter.populate(unicodes=characters)
                    subsetter.subset(font)
                    if face.family in INTERNAL_NAMES:
                        rename(font, name, face.weight[0])
                    font.flavor = "woff2"
                    output = io.BytesIO()
                    font.save(output)
                data = output.getvalue()
                mime = "font/woff2"
            else:
                data = face.path.read_bytes()
                mime = "font/" + face.path.suffix.lstrip(".").lower()
            licenses[f"{name}.txt"] = face.license
            source = embed_data(data, mime)
            family_css = json.dumps(name, ensure_ascii=False)
            rules.append(
                f'@font-face{{font-family:{family_css};font-weight:{weight};'
                f'font-style:{face.style};src:url("{source}");font-display:block}}'
            )
            inputs.append({
                "family": face.family,
                "embedded_family": name,
                "weight": weight,
                "file": face.path.name,
                "sha256": file_hash(face.path),
                "glyph_count": len(characters),
            })
        return "\n".join(rules), licenses, inputs


def rename(font, family: str, weight: int) -> None:
    style = {400: "Regular", 500: "Medium", 700: "Bold"}[weight]
    full = f"{family} {style}"
    ps = family.replace(" ", "") + "-" + style
    names = {1: family, 2: style, 3: ps, 4: full, 6: ps, 16: family, 17: style, 18: full}
    for row in font["name"].names:
        if row.nameID in names:
            row.string = names[row.nameID]
    if "CFF " in font:
        cff = font["CFF "].cff
        cff.fontNames[0] = ps
        top = cff.topDictIndex[0]
        top.FullName = full
        top.FamilyName = family


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        install_fonts()
    except (OSError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)

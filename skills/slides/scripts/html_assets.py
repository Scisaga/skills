"""Collect project-local assets and prepare SVGs for inline browser rendering."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

from html_fonts import Face, Fonts, embed_data, family_list, font_weight
from production_common import file_hash


SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")


def local_asset(project: Path, base: Path, value: str) -> Path:
    url = urlsplit(value)
    if url.scheme or url.netloc or url.query or url.fragment:
        raise ValueError(f"离线资源须使用项目内文件 {value!r}")
    path = (base / unquote(url.path)).resolve()
    if not path.is_relative_to(project) or not path.is_file():
        raise ValueError(f"项目内资源缺失或路径无效 {value!r}（{base}）")
    return path


def url_value(token) -> str | None:
    if token.type == "url":
        return token.value
    if token.type == "function" and token.lower_name == "url":
        args = [arg for arg in token.arguments if arg.type not in {"whitespace", "comment"}]
        if len(args) == 1 and args[0].type == "string":
            return args[0].value
        raise ValueError("CSS url() 须包含单个有效路径")
    return None


class Assets:
    def __init__(self, project: Path) -> None:
        try:
            import tinycss2
        except ImportError as exc:
            raise RuntimeError("缺少 tinycss2，请运行 bootstrap --stage static") from exc
        self.parser = tinycss2
        self.project = project
        self.files: dict[str, str] = {}
        self.images: dict[Path, str] = {}
        self.fonts = Fonts()

    def track(self, path: Path) -> None:
        self.files[str(path.relative_to(self.project))] = file_hash(path)

    def resource(self, value: str, base: Path, ids: dict[str, str]) -> str:
        if value.startswith("#"):
            identifier = unquote(value[1:])
            if identifier not in ids:
                raise ValueError(f"SVG 引用不存在的 ID {value!r}（{base}）")
            return "#" + ids[identifier]
        if value.startswith("data:image/"):
            return value
        path = local_asset(self.project, base, value)
        if path not in self.images:
            mime = mimetypes.guess_type(path.name)[0]
            if not mime or not mime.startswith("image/"):
                raise ValueError(f"离线图像格式无效 {path}")
            self.track(path)
            self.images[path] = embed_data(path.read_bytes(), mime)
        return self.images[path]

    def tokens(self, tokens, base: Path, ids: dict[str, str], *, selector: bool = False):
        for token in tokens:
            url = url_value(token)
            if url is not None:
                value = self.resource(url, base, ids)
                yield from self.parser.parse_component_value_list(f"url({json.dumps(value)})")
                continue
            if selector and token.type == "hash" and token.is_identifier and token.value in ids:
                token.value = ids[token.value]
            child_attr = "arguments" if token.type == "function" else "content"
            child = getattr(token, child_attr, None)
            if child is not None:
                setattr(token, child_attr, list(self.tokens(child, base, ids, selector=selector)))
            if token.type == "error":
                raise ValueError(f"无法解析 CSS 资源（{base}）")
            yield token

    def font_face(self, body, base: Path) -> None:
        fields = {
            node.lower_name: node.value
            for node in self.parser.parse_declaration_list(body, skip_whitespace=True, skip_comments=True)
            if node.type == "declaration"
        }
        names = family_list(self.parser.serialize(fields.get("font-family", [])))
        urls = [url for token in fields.get("src", []) if (url := url_value(token)) is not None]
        if len(names) != 1 or len(urls) != 1:
            raise ValueError("@font-face 须声明一个字体族和一个项目内字体文件")
        path = local_asset(self.project, base, urls[0])
        if path.suffix.lower() not in {".otf", ".ttf", ".woff2"}:
            raise ValueError(f"自带字体须为 OTF、TTF 或 WOFF2 {path}")
        license = path.parent / "LICENSE.txt"
        if not license.is_file():
            raise ValueError(f"字体目录缺少分发授权说明 {license}")
        license = local_asset(self.project, path.parent, "LICENSE.txt")
        weight = self.parser.serialize(fields.get("font-weight", [])).strip() or "400"
        style = self.parser.serialize(fields.get("font-style", [])).strip() or "normal"
        if style not in {"normal", "italic", "oblique"}:
            raise ValueError(f"字体样式无效 {style}")
        self.track(path)
        self.track(license)
        self.fonts.add(Face(names[0], font_weight(weight), style, path, license))

    def stylesheet(self, rules, base: Path, ids: dict[str, str]) -> str:
        result = []
        for rule in rules:
            if rule.type == "error":
                raise ValueError(f"无法解析 CSS（{base}）")
            if rule.type not in {"at-rule", "qualified-rule"}:
                result.append(self.parser.serialize([rule]))
                continue
            if rule.type == "at-rule":
                if rule.lower_at_keyword == "import":
                    raise ValueError("离线模板请将 @import 的样式合并到 CSS")
                if rule.lower_at_keyword == "font-face":
                    if rule.content is None:
                        raise ValueError("无效的 @font-face")
                    self.font_face(rule.content, base)
                    continue
                if rule.lower_at_keyword in {"media", "supports", "layer", "container", "scope"} and rule.content:
                    children = self.parser.parse_rule_list(rule.content)
                    prelude = self.parser.serialize(list(self.tokens(rule.prelude, base, ids, selector=True)))
                    contents = self.stylesheet(children, base, ids)
                    result.append(f"@{rule.at_keyword}{prelude}{{{contents}}}")
                    continue
            rule.prelude = list(self.tokens(rule.prelude, base, ids, selector=rule.type == "qualified-rule"))
            if rule.content is not None:
                rule.content = list(self.tokens(rule.content, base, ids))
            result.append(self.parser.serialize([rule]))
        return "".join(result)

    def css(self, text: str, base: Path, ids: dict[str, str] | None = None) -> str:
        return self.stylesheet(self.parser.parse_stylesheet(text), base, ids or {})

    def svg(self, path: Path, prefix: str, targets: set[str]) -> str:
        self.track(path)
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            raise ValueError(f"无效 SVG {path}: {exc}") from exc
        if root.tag != f"{{{SVG}}}svg" or root.get("viewBox", "").replace(",", " ").split() != ["0", "0", "1600", "900"]:
            raise ValueError(f"SVG 画布须为 viewBox='0 0 1600 900' {path}")

        nodes = list(root.iter())
        ids = {}
        for element in nodes:
            identifier = element.get("id")
            if identifier:
                if identifier in ids:
                    raise ValueError(f"SVG 包含重复 ID {identifier!r}（{path}）")
                ids[identifier] = f"{prefix}-id{len(ids)}"
        groups = {element.get("id") for element in nodes if element.tag == f"{{{SVG}}}g"}
        missing = targets - groups
        if missing:
            raise ValueError(f"{path.name} 缺少动画分组 {', '.join(sorted(missing))}")

        root_id = ids.get(root.get("id"), prefix)
        for element in nodes:
            name = element.tag.rsplit("}", 1)[-1]
            if name in {"script", "animate", "animateMotion", "animateTransform", "set", "foreignObject", "iframe"}:
                raise ValueError(f"请使用静态 SVG 元素，发现 {name}（{path}）")
            element.attrib.pop("data-beat", None)
            identifier = element.get("id")
            if identifier:
                element.set("id", ids[identifier])
                if identifier in targets:
                    element.set("data-beat", identifier)
            if element is root:
                element.set("id", root_id)
            if name == "style":
                css = self.css(element.text or "", path.parent, ids)
                element.text = f"@scope (#{root_id}) {{ {css} }}"
            for attr, value in list(element.attrib.items()):
                local = attr.rsplit("}", 1)[-1]
                if local.lower().startswith("on") or local in {"data-beat", "id"} and attr != local:
                    raise ValueError(f"SVG 属性不适用于离线演示 {attr}（{path}）")
                if local == "href":
                    element.set(attr, self.resource(value, path.parent, ids))
                elif local == "style" or "url(" in value.lower():
                    tokens = self.parser.parse_component_value_list(value)
                    element.set(attr, self.parser.serialize(list(self.tokens(tokens, path.parent, ids))))
        return ET.tostring(root, encoding="unicode")

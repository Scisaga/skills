#!/usr/bin/env python3
"""Inspect and gate Markdown inputs before presentation production starts."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

from contract_versions import INPUT_CONTRACT_VERSION
from page_script_contract import PAGE_HEADING_RE, RENDER_MARKER_RE, audit_page_script


PROFILES = (
    "auto",
    "narrative-plan",
    "execution-plan",
    "page-narration",
    "presentation-source",
)
FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.S)
HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.M)
LINK_RE = re.compile(r"!?\[[^\]]*]\(([^)\r\n]+)\)")
IMAGE_RE = re.compile(r"!\[[^\]]*]\(([^)\r\n]+)\)")
PAGE_RE = re.compile(
    r"^##[ \t]+PAGE[ \t]+(\d+)/(\d+)[ \t]*[｜|][ \t]*(.+?)[ \t]*$",
    re.M,
)
PLACEHOLDER_RE = re.compile(
    r"\b(?:TODO|TBD|FIXME)\b|\?{3,}|\{\{[^{}\r\n]+\}\}",
    re.I,
)

SEMANTIC_CATEGORIES = {
    "narrative-plan": [
        "audience_and_goal",
        "narrative_and_completeness",
        "fact_and_evidence",
        "presentation_fit",
    ],
    "execution-plan": [
        "scope_and_ownership",
        "acceptance_and_risk",
        "fact_and_status",
        "presentation_fit",
    ],
    "presentation-source": [
        "page_narrative_quality",
        "fact_and_evidence",
        "visual_communication_quality",
        "narration_quality",
    ],
    "page-narration": [
        "page_narrative",
        "fact_evidence_integrity",
        "page_completeness",
        "narration_readiness",
        "language_clarity",
    ],
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if (
        len(value) >= 2
        and value[0] == value[-1]
        and value[0] in {"'", '"'}
    ):
        return value[1:-1]
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if value.startswith("[") and value.endswith("]"):
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            parsed = [
                item.strip().strip("'\"")
                for item in value[1:-1].split(",")
                if item.strip()
            ]
        if isinstance(parsed, list):
            return parsed
    return value


def masked(value: str) -> str:
    return "".join(char if char in "\r\n" else " " for char in value)


def strip_fenced_code(text: str) -> str:
    lines = text.splitlines(keepends=True)
    result: list[str] = []
    marker_char = ""
    marker_length = 0
    for line in lines:
        match = re.match(r"^[ \t]*(`{3,}|~{3,})", line)
        if not marker_char and match:
            marker = match.group(1)
            marker_char = marker[0]
            marker_length = len(marker)
            result.append(masked(line))
            continue
        if marker_char:
            result.append(masked(line))
            if re.match(
                rf"^[ \t]*{re.escape(marker_char)}{{{marker_length},}}"
                r"[ \t]*(?:\r?\n)?$",
                line,
            ):
                marker_char = ""
                marker_length = 0
            continue
        result.append(line)
    return "".join(result)


def strip_html_comments(text: str) -> str:
    return re.sub(
        r"<!--.*?-->",
        lambda match: masked(match.group(0)),
        text,
        flags=re.S,
    )


@lru_cache(maxsize=16)
def git_sparse_paths(repository: str) -> frozenset[str]:
    try:
        result = subprocess.run(
            ["git", "-C", repository, "ls-files", "-v", "-z"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return frozenset()
    return frozenset(
        item[2:].decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item.startswith(b"S ")
    )


def repository_root(path: Path) -> Path | None:
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def path_available(document: Path, target: Path) -> bool:
    if target.exists():
        return True
    repository = repository_root(document.parent)
    if repository is None:
        return False
    try:
        relative = target.relative_to(repository).as_posix()
    except ValueError:
        return False
    return relative in git_sparse_paths(str(repository))


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    result: dict[str, Any] = {}
    active_list: str | None = None
    for raw_line in match.group(1).splitlines():
        list_match = re.match(r"^[ \t]+-[ \t]+(.+?)\s*$", raw_line)
        if list_match and active_list:
            current = result.get(active_list)
            if not isinstance(current, list):
                current = []
                result[active_list] = current
            current.append(scalar(list_match.group(1)))
            continue
        field_match = re.match(r"^([A-Za-z0-9_-]+):(?:[ \t]*(.*))?$", raw_line)
        if not field_match:
            active_list = None
            continue
        key, raw_value = field_match.groups()
        value = scalar(raw_value or "")
        result[key] = value
        active_list = key if value == "" else None
    return result, text[match.end():]


def has_value(frontmatter: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        value = frontmatter.get(key)
        if value not in (None, "", [], {}):
            return True
    return False


def finding(
    code: str,
    severity: str,
    message: str,
    required_change: str,
    *,
    location: str = "",
) -> dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "location": location,
        "message": message,
        "required_change": required_change,
    }


def add_missing_field(
    findings: list[dict[str, str]],
    frontmatter: dict[str, Any],
    code: str,
    *keys: str,
) -> None:
    if not has_value(frontmatter, *keys):
        findings.append(
            finding(
                code,
                "blocking",
                f"frontmatter 缺少字段：{' / '.join(keys)}",
                f"在 frontmatter 中补充 {' / '.join(keys)}，并填写真实值。",
                location="frontmatter",
            )
        )


def normalize_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        return target[1:target.index(">")]
    quoted_title = re.match(r"^(\S+)[ \t]+(?:\"[^\"]*\"|'[^']*')$", target)
    return quoted_title.group(1) if quoted_title else target


def check_local_links(
    document: Path,
    body: str,
    findings: list[dict[str, str]],
) -> tuple[int, int]:
    local_count = 0
    external_count = 0
    seen: set[str] = set()
    for match in LINK_RE.finditer(body):
        target = normalize_target(match.group(1))
        if target in seen:
            continue
        seen.add(target)
        parsed = urlsplit(target)
        if parsed.scheme in {"http", "https"}:
            external_count += 1
            continue
        if parsed.scheme or target.startswith(("#", "data:")):
            continue
        local_count += 1
        relative = unquote(parsed.path)
        if not relative:
            continue
        resolved = (document.parent / relative).resolve()
        if not path_available(document, resolved):
            findings.append(
                finding(
                    "DOC006",
                    "blocking",
                    f"本地引用不存在：{target}",
                    "修复引用路径或补齐被引用的文件。",
                    location=target,
                )
            )
    return local_count, external_count


def detect_profile(document: Path, text: str, frontmatter: dict[str, Any]) -> str:
    declared = str(
        frontmatter.get("document_type")
        or frontmatter.get("profile")
        or ""
    ).strip().lower()
    declared_profiles = {
        "page-narration": "page-narration",
        "presentation-source": "presentation-source",
        "narrative-plan": "narrative-plan",
        "execution-plan": "execution-plan",
    }
    if declared in declared_profiles:
        return declared_profiles[declared]
    presentation_metadata = (
        any(key in frontmatter for key in ("target_pages", "page_target"))
        and "canvas" in frontmatter
    )
    render_signal = RENDER_MARKER_RE.search(text)
    if PAGE_RE.search(text) and (render_signal or presentation_metadata):
        return "presentation-source"
    if PAGE_HEADING_RE.search(text):
        return "page-narration"
    if PAGE_RE.search(text):
        return "presentation-source"
    identity = " ".join(
        str(frontmatter.get(key, ""))
        for key in ("title", "document_type")
    )
    identity = f"{document.stem} {identity}"
    if re.search(r"执行|实施|迭代|操作手册|execution|iteration", identity, re.I):
        return "execution-plan"
    return "narrative-plan"


def check_common(
    document: Path,
    text: str,
    body: str,
    frontmatter: dict[str, Any],
    profile: str,
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    headings = [
        {"level": len(marker), "title": title.strip()}
        for marker, title in HEADING_RE.findall(body)
    ]
    if profile in {"page-narration", "presentation-source"}:
        # A prepared page script has its own small, deterministic contract.
        # Product-plan frontmatter, minimum document length, link crawling, and
        # heading-style opinions are intentionally outside that contract.
        return {
            "characters": len(body),
            "headings": len(headings),
            "h2_sections": sum(row["level"] == 2 for row in headings),
            "local_links": 0,
            "external_links": 0,
            "images": len(IMAGE_RE.findall(body)),
            "placeholders": 0,
        }
    if profile in {"narrative-plan", "execution-plan"} and len(
        body.strip()
    ) < 200:
        findings.append(
            finding(
                "DOC004",
                "blocking",
                "正文少于 200 字符，无法进行可靠的全文语义复核。",
                "补充实际计划内容；逐页口述稿请使用 page-narration profile。",
                location="body",
            )
        )

    placeholders = list(PLACEHOLDER_RE.finditer(body))
    for index, match in enumerate(placeholders[:20], 1):
        line = body.count("\n", 0, match.start()) + 1
        findings.append(
            finding(
                f"DOC005-{index:02d}",
                "warning",
                f"存在未关闭占位符：{match.group(0)}",
                "替换为真实内容，或改成有 owner、状态与处理条件的显式待办。",
                location=f"line {line}",
            )
        )

    local_links, external_links = check_local_links(document, body, findings)
    for key in (
        "source_baseline",
        "source_document",
        "source_documents",
        "related_document",
        "related_documents",
    ):
        value = frontmatter.get(key)
        targets = value if isinstance(value, list) else [value]
        for target_value in targets:
            if not isinstance(target_value, str) or not target_value.strip():
                continue
            parsed = urlsplit(target_value)
            if parsed.scheme in {"http", "https"}:
                external_links += 1
                continue
            if parsed.scheme:
                continue
            target = (document.parent / unquote(parsed.path)).resolve()
            if not path_available(document, target):
                findings.append(
                    finding(
                        "DOC010",
                        "blocking",
                        f"frontmatter 引用不存在：{target_value}",
                        "修复来源/关联文档路径，或删除不再适用的引用。",
                        location=f"frontmatter.{key}",
                    )
                )

    return {
        "characters": len(body),
        "headings": len(headings),
        "h2_sections": sum(row["level"] == 2 for row in headings),
        "local_links": local_links,
        "external_links": external_links,
        "images": len(IMAGE_RE.findall(body)),
        "placeholders": len(placeholders),
    }


def check_page_narration(
    document: Path,
    metrics: dict[str, Any],
    findings: list[dict[str, str]],
) -> None:
    audit = audit_page_script(document)
    metrics["pages"] = audit["page_count"]
    metrics["pages_with_target_seconds"] = sum(
        row.get("target_seconds") is not None for row in audit["pages"]
    )
    metrics["engineering_numeric_items"] = sum(
        len(row.get("engineering_numbers", [])) for row in audit["pages"]
    )
    for index, message in enumerate(audit["errors"], 1):
        findings.append(
            finding(
                f"PGN{index:03d}",
                "blocking",
                message,
                "直接修复对应页面的页码、标题或完整口述正文；不要另建摘要文件。",
                location="page narration",
            )
        )


def frontmatter_int(frontmatter: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = frontmatter.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def check_presentation_source(
    document: Path,
    text: str,
    frontmatter: dict[str, Any],
    metrics: dict[str, Any],
    findings: list[dict[str, str]],
) -> None:
    add_missing_field(
        findings,
        frontmatter,
        "PRS001",
        "target_pages",
        "page_target",
    )
    add_missing_field(findings, frontmatter, "PRS002", "canvas")
    add_missing_field(
        findings,
        frontmatter,
        "PRS003",
        "fact_policy",
        "status_legend",
    )
    canvas = str(frontmatter.get("canvas", "")).lower().replace(" ", "")
    if canvas and canvas not in {"1600×900", "1600x900", "16:9"}:
        findings.append(
            finding(
                "PRS003A",
                "blocking",
                f"不支持的画布：{frontmatter.get('canvas')!r}",
                "把画布统一为 1600×900。",
                location="frontmatter.canvas",
            )
        )
    expected = frontmatter_int(frontmatter, "target_pages", "page_target")
    visible_text = strip_html_comments(text)
    matches = list(PAGE_RE.finditer(visible_text))
    metrics["pages"] = len(matches)
    metrics["declared_pages"] = expected
    if not matches:
        findings.append(
            finding(
                "PRS004",
                "blocking",
                "没有识别到 `## PAGE N/T｜标题` 页面。",
                "按连续页码建立逐页源稿。",
                location="pages",
            )
        )
        return
    pages = [int(match.group(1)) for match in matches]
    totals = [int(match.group(2)) for match in matches]
    expected_sequence = list(range(1, len(matches) + 1))
    if pages != expected_sequence:
        findings.append(
            finding(
                "PRS005",
                "blocking",
                f"页码不连续：{pages}",
                f"把页码整理为 {expected_sequence}。",
                location="pages",
            )
        )
    if len(set(totals)) != 1 or totals[0] != len(matches):
        findings.append(
            finding(
                "PRS006",
                "blocking",
                f"PAGE 总页数标记与实际页数不一致：{totals}",
                f"把每页总数统一为 {len(matches)}。",
                location="pages",
            )
        )
    if expected is not None and expected != len(matches):
        findings.append(
            finding(
                "PRS007",
                "blocking",
                f"frontmatter 声明 {expected} 页，实际为 {len(matches)} 页。",
                "统一 target_pages/page_target 与逐页源稿。",
                location="frontmatter",
            )
        )

    for index, match in enumerate(matches):
        page = int(match.group(1))
        title = match.group(3).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        page_body = text[start:end]
        page_visible = strip_html_comments(page_body)
        if not title:
            findings.append(
                finding(
                    f"PRS008-{page:02d}",
                    "blocking",
                    f"第 {page} 页没有标题。",
                    "补充表达单一主判断的页面标题。",
                    location=f"page {page}",
                )
            )
        layout_markers = re.findall(
            r"<!--\s*layout\s*:\s*visual\s*-->",
            page_body,
            re.I,
        )
        if len(layout_markers) != 1:
            findings.append(
                finding(
                    f"PRS009-{page:02d}",
                    "blocking",
                    f"第 {page} 页必须恰好有一个 `layout: visual` 标记，"
                    f"当前为 {len(layout_markers)} 个。",
                    "为视觉页保留一个确定性的布局标记。",
                    location=f"page {page}",
                )
            )
        images = IMAGE_RE.findall(page_visible)
        if len(images) != 1:
            findings.append(
                finding(
                    f"PRS010-{page:02d}",
                    "blocking",
                    f"第 {page} 页必须恰好引用一张完整页 SVG，当前为 {len(images)} 张。",
                    "保留一张自包含、完整画布的 SVG。",
                    location=f"page {page}",
                )
            )
        elif not normalize_target(images[0]).lower().endswith(".svg"):
            findings.append(
                finding(
                    f"PRS011-{page:02d}",
                    "blocking",
                    f"第 {page} 页视觉资源不是 SVG。",
                    "改为一张可独立打开的完整页 SVG。",
                    location=f"page {page}",
                )
            )
        elif images:
            target_value = normalize_target(images[0])
            parsed = urlsplit(target_value)
            svg_path = (document.parent / unquote(parsed.path)).resolve()
            if parsed.scheme or not svg_path.is_file():
                findings.append(
                    finding(
                        f"PRS011A-{page:02d}",
                        "blocking",
                        f"第 {page} 页 SVG 不存在或不是本地文件：{target_value}",
                        "修复 SVG 本地路径并确保文件实际存在。",
                        location=target_value,
                    )
                )
            else:
                try:
                    root = ET.parse(svg_path).getroot()
                except (ET.ParseError, OSError) as exc:
                    findings.append(
                        finding(
                            f"PRS011A-{page:02d}",
                            "blocking",
                            f"第 {page} 页 SVG 无法解析：{exc}",
                            "修复 SVG XML，使其可独立打开。",
                            location=target_value,
                        )
                    )
                else:
                    view_box = root.get("viewBox", "").replace(",", " ").split()
                    if view_box != ["0", "0", "1600", "900"]:
                        findings.append(
                            finding(
                                f"PRS011B-{page:02d}",
                                "blocking",
                                f"第 {page} 页 SVG viewBox 不是 0 0 1600 900。",
                                "把完整页 SVG 统一为 1600×900 画布。",
                                location=target_value,
                            )
                        )
                    unresolved_refs = []
                    for element in root.iter():
                        for attribute, value in element.attrib.items():
                            if attribute.endswith("href") and not value.startswith(
                                ("#", "data:")
                            ):
                                parsed_ref = urlsplit(value)
                                if parsed_ref.scheme in {"http", "https"}:
                                    unresolved_refs.append(value)
                                elif parsed_ref.scheme:
                                    unresolved_refs.append(value)
                                else:
                                    reference_path = (
                                        svg_path.parent / unquote(parsed_ref.path)
                                    ).resolve()
                                    if not path_available(document, reference_path):
                                        unresolved_refs.append(value)
                    if unresolved_refs:
                        findings.append(
                            finding(
                                f"PRS011C-{page:02d}",
                                "blocking",
                                f"第 {page} 页 SVG 包含不可解析资源：{unresolved_refs}",
                                "修复资源路径；进入 PPTX 装配前再把本地资源内嵌。",
                                location=target_value,
                            )
                        )
        notes = re.findall(
            r"<!--\s*speaker-notes\s*:\s*(.*?)-->",
            page_body,
            re.I | re.S,
        )
        if len(notes) != 1 or not notes[0].strip():
            findings.append(
                finding(
                    f"PRS012-{page:02d}",
                    "blocking",
                    f"第 {page} 页必须恰好有一段非空且闭合的 speaker-notes。",
                    "补充该页的判断、证据和过渡，不要只复述画面文字。",
                    location=f"page {page}",
                )
            )


def inspect_document(document: Path, requested_profile: str = "auto") -> dict[str, Any]:
    document = document.expanduser().resolve()
    if not document.is_file():
        raise FileNotFoundError(document)
    try:
        text = document.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{document} must be UTF-8 Markdown") from exc
    contract_text = strip_fenced_code(text)
    visible_text = strip_html_comments(contract_text)
    frontmatter, body = parse_frontmatter(visible_text)
    profile = (
        detect_profile(document, contract_text, frontmatter)
        if requested_profile == "auto"
        else requested_profile
    )
    findings: list[dict[str, str]] = []
    metrics = check_common(
        document,
        text,
        body,
        frontmatter,
        profile,
        findings,
    )
    if profile in {"narrative-plan", "execution-plan"}:
        metrics["plan_semantics_deferred_to_review"] = True
    elif profile == "page-narration":
        check_page_narration(document, metrics, findings)
    elif profile == "presentation-source":
        check_presentation_source(
            document,
            contract_text,
            frontmatter,
            metrics,
            findings,
        )
    blockers = [row for row in findings if row["severity"] == "blocking"]
    return {
        "schema_version": 1,
        "contract_version": INPUT_CONTRACT_VERSION,
        "kind": "input-preflight",
        "document": str(document),
        "document_sha256": sha256(document),
        "profile": profile,
        "passed": not blockers,
        "metrics": metrics,
        "required_semantic_categories": SEMANTIC_CATEGORIES[profile],
        "semantic_review_required": profile != "page-narration",
        "findings": findings,
    }


def validate_evidence(
    evidence: object,
    document_lines: list[str],
    headings: list[tuple[int, str]],
) -> tuple[bool, str, int | None]:
    if not isinstance(evidence, dict):
        return False, "证据必须是包含 heading、line、quote 的对象。", None
    heading = evidence.get("heading")
    line = evidence.get("line")
    quote = evidence.get("quote")
    if heading is not None and not isinstance(heading, str):
        return False, "证据 heading 必须是字符串或 null。", None
    if isinstance(line, bool) or not isinstance(line, int):
        return False, "证据 line 必须是整数。", None
    if not 1 <= line <= len(document_lines):
        return False, f"证据 line 超出文档范围：{line}。", line
    if not isinstance(quote, str) or len(quote.strip()) < 8:
        return False, "证据 quote 至少包含 8 个非空字符。", line

    if isinstance(heading, str) and heading.strip():
        normalized_heading = re.sub(r"^#{1,6}[ \t]+", "", heading.strip())
        preceding = [row for row in headings if row[0] <= line]
        if not preceding:
            return False, f"第 {line} 行之前没有可核验标题。", line
        actual_heading = preceding[-1][1]
        if (
            normalized_heading not in actual_heading
            and actual_heading not in normalized_heading
        ):
            return (
                False,
                f"heading 与第 {line} 行所属章节不一致：{actual_heading!r}。",
                line,
            )

    window_start = max(0, line - 3)
    window_end = min(len(document_lines), line + 2)
    window = "\n".join(document_lines[window_start:window_end])
    if quote.strip() not in window:
        return False, "quote 未出现在指定行附近。", line
    return True, "", line


def semantic_findings(
    preflight: dict[str, Any],
    review_path: Path | None,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    findings: list[dict[str, str]] = []
    if review_path is None:
        return None, [
            finding(
                "SEM001",
                "blocking",
                "缺少语义复核文件。",
                "生成复核模板，由智能体逐项给出证据、问题和返工要求。",
                location="review",
            )
        ]
    review_path = review_path.expanduser().resolve()
    try:
        review = json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [
            finding(
                "SEM002",
                "blocking",
                f"无法读取语义复核文件：{exc}",
                "修复 JSON 后重新复核。",
                location=str(review_path),
            )
        ]
    if not isinstance(review, dict):
        return None, [
            finding(
                "SEM003",
                "blocking",
                "语义复核根节点必须是对象。",
                "使用 prepare-input-review 重新生成模板。",
                location=str(review_path),
            )
        ]
    if review.get("schema_version") != 1:
        findings.append(
            finding(
                "SEM003A",
                "blocking",
                f"不支持的语义复核 schema_version：{review.get('schema_version')!r}",
                "使用当前 prepare-input-review 命令重新生成模板。",
                location=str(review_path),
            )
        )
    if review.get("contract_version") != INPUT_CONTRACT_VERSION:
        findings.append(
            finding(
                "SEM003C",
                "blocking",
                f"语义复核 contract_version 不是当前版本 "
                f"{INPUT_CONTRACT_VERSION}。",
                "使用当前 prepare-input-review 命令重新生成并完成复核。",
                location=str(review_path),
            )
        )
    reviewer = review.get("reviewer")
    reviewer_valid = (
        isinstance(reviewer, dict)
        and isinstance(reviewer.get("name"), str)
        and bool(reviewer["name"].strip())
        and reviewer.get("kind") in {"ai-agent", "human", "hybrid"}
        and reviewer.get("method") == "full-document-review"
        and reviewer.get("attestation") is True
    )
    if not reviewer_valid:
        findings.append(
            finding(
                "SEM003B",
                "blocking",
                "reviewer 必须记录 name、kind、full-document-review 方法和完整声明。",
                "由实际完成全文复核的智能体/复核者填写 attestation。",
                location="reviewer",
            )
        )
    if review.get("document_sha256") != preflight["document_sha256"]:
        findings.append(
            finding(
                "SEM004",
                "blocking",
                "语义复核与当前输入文档 SHA-256 不匹配。",
                "文档改动后必须重新复核，不能复用旧结论。",
                location=str(review_path),
            )
        )
    if review.get("profile") != preflight["profile"]:
        findings.append(
            finding(
                "SEM005",
                "blocking",
                "语义复核 profile 与自动识别结果不一致。",
                "使用同一 profile 重新生成复核模板。",
                location=str(review_path),
            )
        )
    categories = review.get("categories")
    if not isinstance(categories, dict):
        categories = {}
        findings.append(
            finding(
                "SEM006",
                "blocking",
                "语义复核缺少 categories 对象。",
                "逐项复核所有必需维度。",
                location=str(review_path),
            )
        )
    document_text = Path(preflight["document"]).read_text(encoding="utf-8")
    document_lines = document_text.splitlines()
    visible_document = strip_html_comments(strip_fenced_code(document_text))
    headings = [
        (
            visible_document.count("\n", 0, match.start()) + 1,
            match.group(2).strip(),
        )
        for match in HEADING_RE.finditer(visible_document)
    ]
    for category in preflight["required_semantic_categories"]:
        row = categories.get(category)
        if not isinstance(row, dict):
            findings.append(
                finding(
                    f"SEM007-{category}",
                    "blocking",
                    f"缺少语义复核维度：{category}",
                    "补充 status、evidence、issues 和 required_changes。",
                    location=category,
                )
            )
            continue
        status = row.get("status")
        if status not in {"pass", "revise", "block"}:
            findings.append(
                finding(
                    f"SEM008-{category}",
                    "blocking",
                    f"{category} 的 status 无效：{status!r}",
                    "status 只能是 pass、revise 或 block。",
                    location=category,
                )
            )
        elif status != "pass":
            raw_issues = row.get("issues")
            issues = (
                [item for item in raw_issues if isinstance(item, str) and item.strip()]
                if isinstance(raw_issues, list)
                else []
            )
            raw_changes = row.get("required_changes")
            required_changes = (
                [
                    item
                    for item in raw_changes
                    if isinstance(item, str) and item.strip()
                ]
                if isinstance(raw_changes, list)
                else []
            )
            issue_suffix = f"；问题：{'；'.join(issues)}" if issues else ""
            findings.append(
                finding(
                    f"SEM009-{category}",
                    "blocking",
                    f"{category} 尚未通过：{status}{issue_suffix}",
                    "；".join(required_changes)
                    or "补充该维度的具体 required_changes，并返工输入文档。",
                    location=category,
                )
            )
        evidence = row.get("evidence")
        if status == "pass":
            if not isinstance(evidence, list) or not evidence:
                findings.append(
                    finding(
                        f"SEM010-{category}",
                        "blocking",
                        f"{category} 标记通过但没有结构化文档证据。",
                        "至少记录一条 heading、line、quote 均可核验的证据。",
                        location=category,
                    )
                )
            else:
                category_has_valid_evidence = False
                for evidence_index, item in enumerate(evidence, 1):
                    valid, reason, _ = validate_evidence(
                        item,
                        document_lines,
                        headings,
                    )
                    if not valid:
                        findings.append(
                            finding(
                                f"SEM010-{category}-{evidence_index:02d}",
                                "blocking",
                                f"{category} 的证据无效：{reason}",
                                "重新定位当前文档中的真实行号和短摘录；heading 可选。",
                                location=category,
                            )
                        )
                    else:
                        category_has_valid_evidence = True
                if not category_has_valid_evidence:
                    findings.append(
                        finding(
                            f"SEM010B-{category}",
                            "blocking",
                            f"{category} 没有任何有效证据。",
                            "至少增加一条能在当前文档定位的结构化证据。",
                            location=category,
                        )
                    )
        if status == "pass":
            unresolved_issues = row.get("issues")
            unresolved_changes = row.get("required_changes")
            if unresolved_issues not in (None, []) or unresolved_changes not in (
                None,
                [],
            ):
                findings.append(
                    finding(
                        f"SEM010A-{category}",
                        "blocking",
                        f"{category} 标记通过，但仍记录未关闭问题或返工项。",
                        "关闭问题并清空 issues/required_changes，或把状态改为 revise。",
                        location=category,
                    )
                )
    if review.get("decision") != "pass":
        findings.append(
            finding(
                "SEM011",
                "blocking",
                f"语义复核总决策不是 pass：{review.get('decision')!r}",
                "完成返工并重新复核；不得手工绕过总决策。",
                location="decision",
            )
        )
    return review, findings


def gate_document(
    document: Path,
    requested_profile: str,
    review_path: Path | None,
) -> dict[str, Any]:
    preflight = inspect_document(document, requested_profile)
    semantic_review_required = preflight["profile"] != "page-narration"
    if preflight["passed"]:
        if not semantic_review_required:
            review = None
            review_findings = (
                [
                    finding(
                        "SEM012",
                        "info",
                        "page-narration 不使用计划类语义复核；已忽略传入的 review。",
                        "直接审阅逐页正文，并在项目内执行 content 审批。",
                        location="review",
                    )
                ]
                if review_path is not None
                else []
            )
        else:
            review, review_findings = semantic_findings(preflight, review_path)
    else:
        review = None
        review_findings = [
            finding(
                "SEM000",
                "info",
                "自动预检未通过，本轮未执行语义复核。",
                "先关闭自动预检阻断项，再重新生成复核模板并完成全文复核。",
                location="semantic review",
            )
        ]
    findings = [*preflight["findings"], *review_findings]
    blockers = [row for row in findings if row["severity"] == "blocking"]
    return {
        "schema_version": 1,
        "contract_version": INPUT_CONTRACT_VERSION,
        "kind": "input-quality-gate",
        "document": preflight["document"],
        "document_sha256": preflight["document_sha256"],
        "profile": preflight["profile"],
        "passed": not blockers,
        "preflight_passed": preflight["passed"],
        "semantic_review_passed": (
            None if not semantic_review_required else not review_findings
        ),
        "semantic_review_required": semantic_review_required,
        "metrics": preflight["metrics"],
        "required_semantic_categories": preflight["required_semantic_categories"],
        "review": (
            str(review_path.expanduser().resolve())
            if semantic_review_required and review_path
            else None
        ),
        "reviewer": review.get("reviewer") if review else None,
        "findings": findings,
    }


def review_template(preflight: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract_version": INPUT_CONTRACT_VERSION,
        "document": preflight["document"],
        "document_sha256": preflight["document_sha256"],
        "profile": preflight["profile"],
        "reviewer": {
            "name": "",
            "kind": "ai-agent",
            "method": "full-document-review",
            "attestation": False,
        },
        "decision": "revise",
        "categories": {
            category: {
                "status": "revise",
                "evidence": [
                    {
                        "heading": "",
                        "line": 0,
                        "quote": "",
                    }
                ],
                "issues": [],
                "required_changes": [],
            }
            for category in preflight["required_semantic_categories"]
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    preflight_only = report.get("kind") == "input-preflight"
    verdict = (
        "PRECHECK PASS"
        if preflight_only and report["passed"]
        else "PASS"
        if report["passed"]
        else "BLOCKED"
    )
    lines = [
        "# 输入文档自动预检报告"
        if preflight_only
        else "# 输入文档质量门禁报告",
        "",
        f"- 结论：**{verdict}**",
        f"- 文档：`{report['document']}`",
        f"- SHA-256：`{report['document_sha256']}`",
        f"- Profile：`{report['profile']}`",
        "",
        "## 指标",
        "",
    ]
    for key, value in report.get("metrics", {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## 检查结果", ""])
    findings = report.get("findings", [])
    if not findings:
        lines.append("- 无阻断项或警告。")
    else:
        for row in findings:
            location = f"；位置：{row['location']}" if row.get("location") else ""
            lines.extend(
                [
                    f"### {row['severity'].upper()} {row['code']}",
                    "",
                    f"{row['message']}{location}",
                    "",
                    f"返工要求：{row['required_change']}",
                    "",
                ]
            )
    if not report["passed"]:
        lines.extend(
            [
                "",
                "## 门禁动作",
                "",
                (
                    "停止生成 SVG、PPTX、动画、旁白和视频。先修复当前报告中的"
                    "机械阻断项；需要语义复核的 profile 再重新完成复核。"
                ),
                "",
            ]
        )
    elif preflight_only and not report.get("semantic_review_required", True):
        lines.extend(
            [
                "",
                "## 下一步",
                "",
                "该输入满足逐页稿的机械契约，不需要产品计划式语义门禁。"
                "可直接初始化，并在内容审批时确认讲述质量。",
                "",
            ]
        )
    elif preflight_only:
        lines.extend(
            [
                "",
                "## 下一步",
                "",
                "自动预检通过不等于完整门禁通过。填写全文语义复核后，"
                "正常流程直接运行 `init`；只有项目外诊断才单独运行 `validate-input`。",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_json(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_markdown(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(payload), encoding="utf-8")


def add_document_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--document", type=Path, required=True)
    parser.add_argument("--profile", choices=PROFILES, default="auto")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    inspect_parser = commands.add_parser("inspect", help="Run deterministic preflight")
    add_document_args(inspect_parser)
    inspect_parser.add_argument("--json-output", type=Path)
    inspect_parser.add_argument("--markdown-output", type=Path)

    template_parser = commands.add_parser(
        "template",
        help="Create a SHA-bound semantic review template",
    )
    add_document_args(template_parser)
    template_parser.add_argument("--output", type=Path, required=True)

    gate_parser = commands.add_parser("gate", help="Enforce the complete input gate")
    add_document_args(gate_parser)
    gate_parser.add_argument(
        "--review",
        type=Path,
        help="Required only for profiles whose semantic review is required",
    )
    gate_parser.add_argument("--json-output", type=Path)
    gate_parser.add_argument("--markdown-output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            report = inspect_document(args.document, args.profile)
            write_json(args.json_output, report)
            write_markdown(args.markdown_output, report)
        elif args.command == "template":
            report = inspect_document(args.document, args.profile)
            if not report["passed"]:
                blockers = [
                    row
                    for row in report["findings"]
                    if row["severity"] == "blocking"
                ]
                print(
                    "BLOCKED automatic preflight failed; "
                    "semantic review template was not created"
                )
                for row in blockers:
                    print(
                        f"ERROR {row['code']} [{row['location']}]: "
                        f"{row['message']} 返工要求：{row['required_change']}"
                    )
                return 1
            if not report["semantic_review_required"]:
                print(
                    "SKIP semantic review template: page-narration uses "
                    "content approval instead; no file was written"
                )
                return 0
            template = review_template(report)
            write_json(args.output, template)
            print(
                f"OK  semantic review template: "
                f"{args.output.expanduser().resolve()}"
            )
            return 0
        else:
            report = gate_document(args.document, args.profile, args.review)
            write_json(args.json_output, report)
            write_markdown(args.markdown_output, report)
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2

    blockers = sum(
        row["severity"] == "blocking" for row in report.get("findings", [])
    )
    warnings = sum(
        row["severity"] == "warning" for row in report.get("findings", [])
    )
    verdict = (
        "PRECHECK PASS"
        if report.get("kind") == "input-preflight" and report["passed"]
        else "PASS"
        if report["passed"]
        else "BLOCKED"
    )
    print(
        f"{verdict} {report['document']} "
        f"(profile={report['profile']}, blockers={blockers}, warnings={warnings})"
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

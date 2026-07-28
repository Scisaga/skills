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
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET


PROFILES = ("auto", "narrative-plan", "execution-plan", "presentation-source")
REVIEW_ATTESTATION = (
    "I reviewed the entire current document and the cited evidence supports "
    "each assigned category."
)
FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.S)
HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.M)
LINK_RE = re.compile(r"!?\[[^\]]*]\(([^)\r\n]+)\)")
IMAGE_RE = re.compile(r"!\[[^\]]*]\(([^)\r\n]+)\)")
PAGE_RE = re.compile(r"^##[ \t]+PAGE[ \t]+(\d+)/(\d+)[｜|][ \t]*(.+?)[ \t]*$", re.M)
PLACEHOLDER_RE = re.compile(
    r"\b(?:TODO|TBD|FIXME)\b|\?{3,}|\{\{[^{}\r\n]+\}\}",
    re.I,
)

SEMANTIC_CATEGORIES = {
    "narrative-plan": [
        "purpose_audience",
        "narrative_coherence",
        "fact_evidence_integrity",
        "content_completeness",
        "presentation_readiness",
        "language_clarity",
    ],
    "execution-plan": [
        "purpose_scope",
        "fact_status_integrity",
        "deliverables_ownership",
        "acceptance_readiness",
        "risk_feasibility",
        "presentation_readiness",
    ],
    "presentation-source": [
        "page_narrative",
        "fact_evidence_integrity",
        "page_completeness",
        "visual_readiness",
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
    if not frontmatter:
        findings.append(
            finding(
                "DOC001",
                "blocking",
                "缺少 Markdown frontmatter。",
                "在文档开头补充 title、status 及对应类型要求的元数据。",
                location="document start",
            )
        )
    add_missing_field(findings, frontmatter, "DOC002", "title")

    headings = [
        {"level": len(marker), "title": title.strip()}
        for marker, title in HEADING_RE.findall(body)
    ]
    if profile != "presentation-source":
        h1_count = sum(row["level"] == 1 for row in headings)
        if h1_count != 1:
            findings.append(
                finding(
                    "DOC003",
                    "blocking",
                    f"正文必须恰好有一个 H1，当前为 {h1_count} 个。",
                    "保留一个与文档身份一致的一级标题。",
                    location="headings",
                )
            )
    if len(body.strip()) < (2000 if profile != "presentation-source" else 200):
        findings.append(
            finding(
                "DOC004",
                "blocking",
                "正文内容过少，无法支撑演示制作。",
                "补齐问题、判断、证据、行动或逐页内容后重新检查。",
                location="body",
            )
        )

    placeholders = list(PLACEHOLDER_RE.finditer(body))
    for index, match in enumerate(placeholders[:20], 1):
        line = body.count("\n", 0, match.start()) + 1
        findings.append(
            finding(
                f"DOC005-{index:02d}",
                "blocking",
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

    last_level = 0
    for row in headings:
        if last_level and row["level"] > last_level + 1:
            findings.append(
                finding(
                    "DOC007",
                    "warning",
                    f"标题层级从 H{last_level} 跳到 H{row['level']}：{row['title']}",
                    "检查标题层级，确保阅读结构没有断层。",
                    location=row["title"],
                )
            )
        last_level = row["level"]
    duplicates = [
        title
        for title, count in Counter(row["title"] for row in headings).items()
        if count > 1
    ]
    for title in duplicates:
        findings.append(
            finding(
                "DOC008",
                "warning",
                f"标题重复：{title}",
                "确认重复章节是否应合并或改名。",
                location=title,
            )
        )

    long_paragraphs = [
        paragraph
        for paragraph in re.split(r"\n[ \t]*\n", body)
        if len(paragraph.strip()) > 900
        and not all(
            not line.strip() or line.lstrip().startswith("|")
            for line in paragraph.splitlines()
        )
    ]
    if long_paragraphs:
        findings.append(
            finding(
                "DOC009",
                "warning",
                f"有 {len(long_paragraphs)} 个段落超过 900 字符。",
                "拆分论点并增加可用于分页的层次或小结。",
                location="body",
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


def require_pattern(
    findings: list[dict[str, str]],
    body: str,
    code: str,
    label: str,
    pattern: str,
    required_change: str,
    *,
    severity: str = "blocking",
) -> None:
    if not re.search(pattern, body, re.I | re.M):
        findings.append(
            finding(
                code,
                severity,
                f"未识别到{label}。",
                required_change,
                location="body",
            )
        )


def check_narrative(
    body: str,
    frontmatter: dict[str, Any],
    metrics: dict[str, Any],
    findings: list[dict[str, str]],
) -> None:
    add_missing_field(findings, frontmatter, "NAR001", "status")
    add_missing_field(findings, frontmatter, "NAR002", "audience")
    add_missing_field(
        findings,
        frontmatter,
        "NAR003",
        "evidence_policy",
        "fact_policy",
    )
    if metrics["h2_sections"] < 5:
        findings.append(
            finding(
                "NAR004",
                "blocking",
                f"二级章节只有 {metrics['h2_sections']} 个，叙事结构不足。",
                "至少形成问题、对象、方案、证据/边界、行动或路线等稳定章节。",
                location="headings",
            )
        )
    if not re.search(r"^>[ \t]+\S", body[:6000], re.M):
        findings.append(
            finding(
                "NAR005",
                "warning",
                "文档前部没有可识别的核心判断或一句话主张。",
                "在开头明确受众应记住的核心判断，避免从背景材料开始堆叠。",
                location="opening",
            )
        )
    required_patterns = [
        ("NAR006", "目标受众或首批用户", r"目标用户|首批用户|谁会先使用|客户|受众"),
        ("NAR007", "具体问题或痛点", r"问题|痛点|卡在哪里|为什么.*难|断点"),
        ("NAR008", "产品答案或解决路径", r"产品答案|解决方案|产品路径|如何解决|工作流"),
        ("NAR009", "具体案例、任务或使用场景", r"具体任务|案例|场景|用户旅程|体验路径"),
        ("NAR010", "事实、证据或待验证边界", r"证据|事实|已具备|仍需证明|待验证|假设"),
    ]
    for code, label, pattern in required_patterns:
        require_pattern(
            findings,
            body,
            code,
            label,
            pattern,
            f"新增明确的{label}章节，并区分已证实内容与假设。",
        )
    require_pattern(
        findings,
        body,
        "NAR011",
        "演示分页映射",
        r"^#{2,4}[ \t]+.*(?:PPT|演示).*(?:页|映射|结构)|^#{2,4}[ \t]+.*(?:逐页|页映射)",
        "增加逐页演示映射，说明每页标题、主判断、证据和视觉意图。",
    )
    mapping_heading = re.search(
        r"^#{2,4}[ \t]+.*(?:PPT|演示).*(?:页|映射|结构)|"
        r"^#{2,4}[ \t]+.*(?:逐页|页映射)",
        body,
        re.I | re.M,
    )
    if mapping_heading:
        next_heading = re.search(
            r"^#{1,2}[ \t]+",
            body[mapping_heading.end():],
            re.M,
        )
        mapping_end = (
            mapping_heading.end() + next_heading.start()
            if next_heading
            else len(body)
        )
        mapping_body = body[mapping_heading.end():mapping_end]
        table_rows = [
            [cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in mapping_body.splitlines()
            if line.strip().startswith("|")
        ]
        header_index = next(
            (
                index
                for index, row in enumerate(table_rows)
                if len(row) >= 3
                and "页码" in row[0]
                and "标题" in row[1]
                and re.search(r"核心结论|主判断", row[2])
            ),
            None,
        )
        page_rows: list[tuple[int, str, str]] = []
        if header_index is not None:
            for row in table_rows[header_index + 1:]:
                if len(row) < 3 or re.fullmatch(r":?-+:?", row[0]):
                    continue
                page_match = re.fullmatch(r"(?:第[ \t]*)?(\d+)(?:[ \t]*页)?", row[0])
                if not page_match:
                    continue
                page_rows.append((int(page_match.group(1)), row[1], row[2]))
        mapped_pages = len(page_rows)
        metrics["mapped_pages"] = mapped_pages
        if header_index is None:
            findings.append(
                finding(
                    "NAR011A",
                    "blocking",
                    "逐页映射缺少“页码 / 标题 / 核心结论（或主判断）”表头。",
                    "使用明确表头建立逐页映射表。",
                    location="presentation mapping",
                )
            )
        elif mapped_pages < 5:
            findings.append(
                finding(
                    "NAR011B",
                    "blocking",
                    f"逐页映射只有 {mapped_pages} 个可识别页面。",
                    "至少给出 5 页，并为每页填写标题和核心结论。",
                    location="presentation mapping",
                )
            )
        else:
            page_numbers = [row[0] for row in page_rows]
            expected_pages = list(range(1, mapped_pages + 1))
            if page_numbers != expected_pages:
                findings.append(
                    finding(
                        "NAR011C",
                        "blocking",
                        f"逐页映射页码不连续：{page_numbers}",
                        f"把页码整理为 {expected_pages}。",
                        location="presentation mapping",
                    )
                )
            weak_rows = [
                page
                for page, title, conclusion in page_rows
                if len(title.strip()) < 4 or len(conclusion.strip()) < 8
            ]
            if weak_rows:
                findings.append(
                    finding(
                        "NAR011D",
                        "blocking",
                        f"以下页面的标题或核心结论过于空洞：{weak_rows}",
                        "为每页写出可独立理解的标题和具体核心结论。",
                        location="presentation mapping",
                    )
                )
    require_pattern(
        findings,
        body,
        "NAR012",
        "价值、商业或采用逻辑",
        r"商业|付费|价值|收入|购买|采用",
        "补充目标受众为什么会采用、付费或采取行动。",
        severity="warning",
    )
    require_pattern(
        findings,
        body,
        "NAR013",
        "风险、边界或下一步",
        r"风险|边界|路线图|下一步|阶段目标|结语|行动",
        "补充风险边界和演示结束后的明确行动。",
        severity="warning",
    )
    numeric_pattern = re.compile(
        r"(?<!\w)\d+(?:\.\d+)?\s*(?:%|万|亿|元|美元|人|家|个月|年)"
    )
    numeric_claims = len(numeric_pattern.findall(body))
    metrics["numeric_claims"] = numeric_claims
    unsupported_numeric_claims = 0
    for match in numeric_pattern.finditer(body):
        current_start = body.rfind("\n", 0, match.start())
        previous_start = body.rfind("\n", 0, max(current_start, 0))
        current_end = body.find("\n", match.end())
        next_end = body.find("\n", current_end + 1) if current_end >= 0 else -1
        window_start = previous_start + 1 if previous_start >= 0 else 0
        window_end = next_end if next_end >= 0 else len(body)
        window = body[window_start:window_end]
        if not re.search(
            r"https?://|\]\(|来源|证据|假设|目标|待验证|待补齐|路线|计划|样本|"
            r"不是.{0,20}结论|数据决定",
            window,
            re.I,
        ):
            unsupported_numeric_claims += 1
    metrics["unsupported_numeric_claims"] = unsupported_numeric_claims
    if unsupported_numeric_claims:
        findings.append(
            finding(
                "NAR014",
                "warning",
                f"有 {unsupported_numeric_claims} 个数量性表述附近未识别到来源或假设标签。",
                "为关键数字补直接来源，或显式标成内部假设/目标。",
                location="evidence",
            )
        )


def check_execution(
    body: str,
    frontmatter: dict[str, Any],
    metrics: dict[str, Any],
    findings: list[dict[str, str]],
) -> None:
    add_missing_field(findings, frontmatter, "EXE001", "status")
    if metrics["h2_sections"] < 5:
        findings.append(
            finding(
                "EXE002",
                "blocking",
                f"二级章节只有 {metrics['h2_sections']} 个，执行闭环不足。",
                "补齐范围、交付、责任、验收、风险和来源等章节。",
                location="headings",
            )
        )
    requirements = [
        ("EXE003", "范围或文档边界", r"范围|边界|不负责|不等于"),
        (
            "EXE004",
            "事实或状态标签",
            r"官方要求|内部建议|待团队填写|现有|待实现|验收|事实口径|状态标签",
        ),
        (
            "EXE005",
            "交付物或执行动作",
            r"交付|执行动作|工作包|WBS|资料总清单|提交|任务",
        ),
        ("EXE006", "责任人与时间安排", r"Owner|责任人|负责人|日期|排期|日历|阶段"),
        ("EXE007", "验收或完成定义", r"验收|完成定义|DoD|检查清单|Checklist"),
        ("EXE008", "风险或阻断条件", r"风险|阻断条件|失败条件|回滚"),
        ("EXE009", "来源或依据", r"参考资料|官方来源|来源|证据"),
    ]
    for code, label, pattern in requirements:
        require_pattern(
            findings,
            body,
            code,
            label,
            pattern,
            f"补充可执行的{label}，避免把愿望当成计划。",
        )
    require_pattern(
        findings,
        body,
        "EXE010",
        "演示或汇报结构",
        r"PPT|演示|路演|汇报|视频",
        "如果该文档将生成演示，补充演示受众、页数和逐页结构。",
        severity="warning",
    )
    labelled_blanks = len(re.findall(r"待团队填写|待补充|待确认", body))
    metrics["labelled_open_items"] = labelled_blanks
    if labelled_blanks:
        findings.append(
            finding(
                "EXE011",
                "warning",
                f"存在 {labelled_blanks} 个显式开放项。",
                "语义复核时确认每项有 owner、截止条件，且不会阻断当前演示。",
                location="open items",
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
            if svg_path.is_file():
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
        detect_profile(document, visible_text, frontmatter)
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
    if profile == "narrative-plan":
        check_narrative(body, frontmatter, metrics, findings)
    elif profile == "execution-plan":
        check_execution(body, frontmatter, metrics, findings)
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
        "kind": "input-preflight",
        "document": str(document),
        "document_sha256": sha256(document),
        "profile": profile,
        "passed": not blockers,
        "metrics": metrics,
        "required_semantic_categories": SEMANTIC_CATEGORIES[profile],
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
    if not isinstance(heading, str) or not heading.strip():
        return False, "证据 heading 不能为空。", None
    if isinstance(line, bool) or not isinstance(line, int):
        return False, "证据 line 必须是整数。", None
    if not 1 <= line <= len(document_lines):
        return False, f"证据 line 超出文档范围：{line}。", line
    if not isinstance(quote, str) or len(quote.strip()) < 8:
        return False, "证据 quote 至少包含 8 个非空字符。", line

    normalized_heading = re.sub(r"^#{1,6}[ \t]+", "", heading.strip())
    preceding = [row for row in headings if row[0] <= line]
    if not preceding:
        return False, f"第 {line} 行之前没有可核验标题。", line
    actual_heading = preceding[-1][1]
    if normalized_heading not in actual_heading and actual_heading not in normalized_heading:
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
    reviewer = review.get("reviewer")
    reviewer_valid = (
        isinstance(reviewer, dict)
        and isinstance(reviewer.get("name"), str)
        and bool(reviewer["name"].strip())
        and reviewer.get("kind") in {"ai-agent", "human", "hybrid"}
        and reviewer.get("method") == "full-document-review"
        and reviewer.get("attestation") == REVIEW_ATTESTATION
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
    valid_evidence_lines: set[int] = set()
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
                    valid, reason, evidence_line = validate_evidence(
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
                                "重新定位当前文档中的真实章节、行号和短摘录。",
                                location=category,
                            )
                        )
                    else:
                        category_has_valid_evidence = True
                        if evidence_line is not None:
                            valid_evidence_lines.add(evidence_line)
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
    if review.get("decision") == "pass" and len(valid_evidence_lines) < 4:
        findings.append(
            finding(
                "SEM010C",
                "blocking",
                f"六个复核维度只覆盖 {len(valid_evidence_lines)} 个不同证据位置。",
                "至少使用 4 个不同文档位置覆盖受众、叙事、事实和演示可制作性。",
                location="categories.*.evidence",
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
    blocking_findings = review.get("blocking_findings")
    if isinstance(blocking_findings, list):
        for index, row in enumerate(blocking_findings, 1):
            if isinstance(row, dict):
                message = str(
                    row.get("problem")
                    or row.get("message")
                    or "语义复核仍包含阻断项。"
                )
                required_change = str(
                    row.get("required_change")
                    or row.get("required_changes")
                    or "关闭该阻断项并在文档中留下可核验修改。"
                )
                location = str(row.get("location") or "blocking_findings")
            else:
                message = str(row)
                required_change = "关闭该阻断项并在文档中留下可核验修改。"
                location = "blocking_findings"
            findings.append(
                finding(
                    f"SEM012-{index:02d}",
                    "blocking",
                    message,
                    required_change,
                    location=location,
                )
            )
    else:
        findings.append(
            finding(
                "SEM012",
                "blocking",
                "blocking_findings 必须是数组。",
                "按复核模板修复字段格式。",
                location="blocking_findings",
            )
        )
    revision_plan = review.get("revision_plan")
    if not isinstance(revision_plan, list):
        findings.append(
            finding(
                "SEM013",
                "blocking",
                "revision_plan 必须是数组。",
                "按复核模板修复字段格式。",
                location="revision_plan",
            )
        )
    elif review.get("decision") != "pass" and not revision_plan:
        findings.append(
            finding(
                "SEM013",
                "blocking",
                "复核未通过，但 revision_plan 为空。",
                "按优先级、位置、问题、所需修改和验收标准形成返工计划。",
                location="revision_plan",
            )
        )
    elif review.get("decision") == "pass" and revision_plan:
        findings.append(
            finding(
                "SEM013A",
                "blocking",
                "总决策为 pass，但 revision_plan 仍包含返工项。",
                "完成并清空返工项，或把总决策改为 revise。",
                location="revision_plan",
            )
        )
    return review, findings


def gate_document(
    document: Path,
    requested_profile: str,
    review_path: Path | None,
) -> dict[str, Any]:
    preflight = inspect_document(document, requested_profile)
    if preflight["passed"]:
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
        "kind": "input-quality-gate",
        "document": preflight["document"],
        "document_sha256": preflight["document_sha256"],
        "profile": preflight["profile"],
        "passed": not blockers,
        "preflight_passed": preflight["passed"],
        "semantic_review_passed": not review_findings,
        "metrics": preflight["metrics"],
        "required_semantic_categories": preflight["required_semantic_categories"],
        "review": str(review_path.expanduser().resolve()) if review_path else None,
        "reviewer": review.get("reviewer") if review else None,
        "findings": findings,
    }


def review_template(preflight: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "document": preflight["document"],
        "document_sha256": preflight["document_sha256"],
        "profile": preflight["profile"],
        "reviewer": {
            "name": "",
            "kind": "ai-agent",
            "method": "full-document-review",
            "attestation": REVIEW_ATTESTATION,
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
        "blocking_findings": [],
        "revision_plan": [],
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
                "停止生成 SVG、PPTX、动画、旁白和视频。先修改输入文档，"
                "然后重新执行自动预检和语义复核。",
                "",
            ]
        )
    elif preflight_only:
        lines.extend(
            [
                "",
                "## 下一步",
                "",
                "自动预检通过不等于完整门禁通过。仍须完成全文语义复核，"
                "再运行 `validate-input`。",
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
    gate_parser.add_argument("--review", type=Path, required=True)
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

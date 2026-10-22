#!/usr/bin/env python3
"""Small deterministic contract for already prepared page-by-page narration."""

from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from contract_versions import PAGE_SCRIPT_CONTRACT_VERSION


PAGE_HEADING_RE = re.compile(
    r"^##[ \t]+(?:"
    r"第[ \t]*(?P<cn_page>\d+)[ \t]*页"
    r"|PAGE[ \t]+(?P<en_page>\d+)(?:/(?P<declared_total>\d+))?"
    r")[ \t]*[｜|][ \t]*(?P<title>.+?)[ \t]*$",
    re.I | re.M,
)
TARGET_SECONDS_RE = re.compile(r"(?:·|/|｜|\|)[ \t]*(\d+)[ \t]*秒(?:钟)?\s*$")
ENGINEERING_NUMBER_RE = re.compile(
    r"\d+(?:\.\d+)?(?:[ \t]*[×x乘][ \t]*\d+(?:\.\d+)?){1,2}[ \t]*"
    r"(?:mm|cm|m|毫米|厘米|米)?"
    r"|\d+(?:\.\d+)?[ \t]*(?:%|℃|°C|K|mm²|mm2|mm|cm|m²|m2|MPa|GPa|kg|t|"
    r"毫米|平方毫米|平方米|兆帕|吉帕|公斤|吨|件|架份|批次|年)"
    r"|百分之[零〇一二三四五六七八九十百千万亿]+",
    re.I,
)
RENDER_MARKER_RE = re.compile(
    r"<!--[ \t]*(?:speaker-notes[ \t]*:|layout[ \t]*:[ \t]*visual\b)"
    r"|^[ \t]*(?:(?:[-*+][ \t]+)?source[_ -]?svg|"
    r"[\"']source[_ -]?svg[\"'])[ \t]*:"
    r"|!\[[^\]]*]\([^)]*\.svg(?:[?#][^)]*)?\)|<svg\b",
    re.I | re.M,
)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _visible_body(value: str) -> str:
    value = re.sub(r"<!--.*?-->", "", value, flags=re.S)
    value = re.sub(r"(?m)^[ \t]*---[ \t]*$", "", value)
    return value.strip()


def _comparison_text(value: str) -> str:
    """Normalize formatting noise while retaining actual spoken content."""
    value = re.sub(r"!\[[^\]]*]\([^)]+\)", "", value)
    value = re.sub(r"\[([^\]]+)]\([^)]+\)", r"\1", value)
    value = re.sub(r"[`*_~>#|\-]", "", value)
    return re.sub(r"[^0-9A-Za-z\u3400-\u9fff]+", "", value).lower()


def narration_paragraphs(value: str) -> list[str]:
    """Convert page Markdown into canonical spoken paragraphs without summarizing."""
    paragraphs: list[str] = []
    for raw in re.split(r"\n[ \t]*\n", _visible_body(value)):
        text = re.sub(r"(?m)^#{1,6}[ \t]+", "", raw)
        text = re.sub(r"(?m)^[ \t]*(?:[-*+]|\d+[.)])[ \t]+", "", text)
        text = re.sub(r"(?m)^[ \t]*>[ \t]?", "", text)
        text = re.sub(r"!\[[^\]]*]\([^)]+\)", "", text)
        text = re.sub(r"\[([^\]]+)]\([^)]+\)", r"\1", text)
        text = re.sub(r"(?<!\\)[`*_~]", "", text)
        text = " ".join(text.split())
        if text:
            paragraphs.append(text)
    return paragraphs


def parse_page_script_text(text: str) -> list[dict[str, Any]]:
    matches = list(PAGE_HEADING_RE.finditer(text))
    pages: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        raw_body = text[start:end]
        body = _visible_body(raw_body)
        page = int(match.group("cn_page") or match.group("en_page"))
        title = match.group("title").strip()
        duration = TARGET_SECONDS_RE.search(title)
        spoken = narration_paragraphs(body)
        spoken_characters = len(re.sub(r"\s+", "", "".join(spoken)))
        pages.append(
            {
                "page": page,
                "declared_total": (
                    int(match.group("declared_total"))
                    if match.group("declared_total")
                    else None
                ),
                "title": title,
                "target_seconds": int(duration.group(1)) if duration else None,
                "body": body,
                "body_sha256": _sha256_text(body),
                "body_characters": spoken_characters,
                "spoken_paragraphs": len(spoken),
                "engineering_numbers": sorted(set(ENGINEERING_NUMBER_RE.findall(body))),
            }
        )
    return pages


def parse_page_script(path: Path) -> list[dict[str, Any]]:
    return parse_page_script_text(path.read_text(encoding="utf-8"))


def audit_director_text(
    page_script: Path,
    director: dict[str, Any],
) -> dict[str, Any]:
    """Prove that the TTS text is a formatting-only derivative of page-script."""
    expected_rows = parse_page_script(page_script.expanduser().resolve())
    raw_pages = director.get("pages")
    errors: list[str] = []
    if not isinstance(raw_pages, list):
        raw_pages = []
        errors.append("narration_director.pages 必须是数组")
    actual_by_page = {
        row.get("page"): row
        for row in raw_pages
        if isinstance(row, dict) and isinstance(row.get("page"), int)
    }
    expected_pages = [row["page"] for row in expected_rows]
    if sorted(actual_by_page) != expected_pages:
        errors.append(
            "导演稿页码必须与 page-script 完全一致："
            f"page_script={expected_pages}, director={sorted(actual_by_page)}"
        )
    evidence: list[dict[str, Any]] = []
    for row in expected_rows:
        page = row["page"]
        expected = "".join(narration_paragraphs(row["body"]))
        actual_row = actual_by_page.get(page, {})
        segments = actual_row.get("segments")
        actual = (
            "".join(
                segment.get("text", "")
                for segment in segments
                if isinstance(segment, dict)
                and isinstance(segment.get("text"), str)
            )
            if isinstance(segments, list)
            else ""
        )
        matched = actual == expected
        if not matched:
            errors.append(
                f"第 {page} 页导演稿正文不是 page-script 的保真派生；"
                "正文修改必须先发生在 page-script.md"
            )
        evidence.append(
            {
                "page": page,
                "matched": matched,
                "page_script_spoken_sha256": _sha256_text(expected),
                "director_spoken_sha256": _sha256_text(actual),
            }
        )
    return {
        "schema_version": 1,
        "contract_version": PAGE_SCRIPT_CONTRACT_VERSION,
        "status": "blocked" if errors else "pass",
        "page_count": len(expected_rows),
        "pages": evidence,
        "errors": errors,
    }


def audit_page_script(
    page_script: Path,
    *,
    source: Path | None = None,
    allow_substantial_rewrite: bool = False,
    enforce_source_fidelity: bool = True,
) -> dict[str, Any]:
    page_script = page_script.expanduser().resolve()
    pages = parse_page_script(page_script)
    errors: list[str] = []
    warnings: list[str] = []
    page_numbers = [row["page"] for row in pages]
    expected = list(range(1, len(pages) + 1))
    if not pages:
        errors.append(
            "没有识别到 `## 第 N 页｜标题` 或 `## PAGE N/T｜标题` 逐页正文"
        )
    elif page_numbers != expected:
        errors.append(f"页码必须从 1 连续排列，当前为 {page_numbers}")
    declared_totals = {
        row["declared_total"]
        for row in pages
        if row.get("declared_total") is not None
    }
    if declared_totals and declared_totals != {len(pages)}:
        errors.append(
            f"PAGE N/T 中声明的总页数 {sorted(declared_totals)} "
            f"与实际 {len(pages)} 页不一致"
        )
    for row in pages:
        if len(row["title"]) < 2:
            errors.append(f"第 {row['page']} 页标题为空或过短")
        if row["body_characters"] < 20:
            errors.append(
                f"第 {row['page']} 页只有 {row['body_characters']} 个可朗读字符"
            )

    page_script_text = page_script.read_text(encoding="utf-8")
    if RENDER_MARKER_RE.search(page_script_text):
        errors.append(
            "page-script 包含 SVG、layout 或 speaker-notes 渲染标记；"
            "请显式提供只含逐页口述正文的 page-script"
        )

    fidelity: dict[str, Any] | None = None
    if source is not None:
        source = source.expanduser().resolve()
        source_pages = parse_page_script(source)
        if source_pages:
            source_by_page = {row["page"]: row for row in source_pages}
            target_by_page = {row["page"]: row for row in pages}
            exact_copy = page_script.read_bytes() == source.read_bytes()
            if sorted(source_by_page) != sorted(target_by_page):
                errors.append(
                    "逐页稿页码与已整理正文源不一致："
                    f"source={sorted(source_by_page)}, page_script={sorted(target_by_page)}"
                )
            low_retention: list[int] = []
            low_coverage: list[int] = []
            missing_numbers: list[dict[str, Any]] = []
            source_chars = 0
            target_chars = 0
            matched_source_chars = 0
            comparable_source_chars = 0
            page_rows: list[dict[str, Any]] = []
            for page in sorted(set(source_by_page).intersection(target_by_page)):
                source_row = source_by_page[page]
                target_row = target_by_page[page]
                source_count = max(1, int(source_row["body_characters"]))
                target_count = int(target_row["body_characters"])
                retention = target_count / source_count
                source_chars += source_count
                target_chars += target_count
                source_comparison = _comparison_text(source_row["body"])
                target_comparison = _comparison_text(target_row["body"])
                if exact_copy:
                    matched = len(source_comparison)
                    coverage = 1.0
                    similarity = 1.0
                else:
                    matcher = SequenceMatcher(
                        None,
                        source_comparison,
                        target_comparison,
                        autojunk=False,
                    )
                    matched = sum(
                        block.size for block in matcher.get_matching_blocks()
                    )
                    coverage = matched / max(1, len(source_comparison))
                    similarity = matcher.ratio()
                matched_source_chars += matched
                comparable_source_chars += len(source_comparison)
                missing = sorted(
                    set(source_row["engineering_numbers"])
                    - set(target_row["engineering_numbers"])
                )
                if retention < 0.6:
                    low_retention.append(page)
                if coverage < 0.55:
                    low_coverage.append(page)
                if missing:
                    missing_numbers.append({"page": page, "values": missing})
                page_rows.append(
                    {
                        "page": page,
                        "source_body_sha256": source_row["body_sha256"],
                        "page_script_body_sha256": target_row["body_sha256"],
                        "character_retention": round(retention, 4),
                        "source_character_coverage": round(coverage, 4),
                        "sequence_similarity": round(similarity, 4),
                        "estimated_removed_characters": max(
                            0, len(source_comparison) - matched
                        ),
                        "estimated_added_characters": max(
                            0, len(target_comparison) - matched
                        ),
                        "missing_engineering_numbers": missing,
                    }
                )
            total_retention = target_chars / max(1, source_chars)
            total_source_coverage = matched_source_chars / max(
                1, comparable_source_chars
            )
            fidelity = {
                "comparison_mode": "page-aligned",
                "source": str(source),
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "exact_byte_copy": exact_copy,
                "total_character_retention": round(total_retention, 4),
                "total_source_character_coverage": round(
                    total_source_coverage, 4
                ),
                "low_retention_pages": low_retention,
                "low_coverage_pages": low_coverage,
                "missing_engineering_numbers": missing_numbers,
                "pages": page_rows,
            }
            if enforce_source_fidelity and not allow_substantial_rewrite:
                if not exact_copy:
                    errors.append(
                        "逐页稿与已整理正文源并非逐字节一致；任何改写都必须由用户"
                        "明确授权后再切换为 adapted 绑定"
                    )
                if (
                    total_retention < 0.7
                    or total_source_coverage < 0.65
                    or low_retention
                    or low_coverage
                ):
                    warnings.append(
                        "逐页稿相对已整理正文源删减过多；"
                        "详细页级差异已写入审计证据"
                    )
                if missing_numbers:
                    warnings.append(
                        "逐页稿遗漏源稿中的工程数字或单位："
                        + ", ".join(
                            f"第 {row['page']} 页 {row['values']}"
                            for row in missing_numbers
                        )
                    )
            elif enforce_source_fidelity and not exact_copy:
                warnings.append("已显式授权逐页稿脱离 identity 并记录为 adapted")
            elif not enforce_source_fidelity and not exact_copy:
                warnings.append(
                    "源文件不是已绑定逐页正文；页级差异仅作 adapted 内容审阅证据"
                )
        else:
            source_text = source.read_text(encoding="utf-8")
            target_text = "\n".join(row["body"] for row in pages)
            source_comparison = _comparison_text(source_text)
            target_comparison = _comparison_text(target_text)
            ngram_size = 4
            source_ngrams = {
                source_comparison[index : index + ngram_size]
                for index in range(max(0, len(source_comparison) - ngram_size + 1))
            }
            target_ngrams = {
                target_comparison[index : index + ngram_size]
                for index in range(max(0, len(target_comparison) - ngram_size + 1))
            }
            shared_ngrams = source_ngrams.intersection(target_ngrams)
            source_numbers = sorted(set(ENGINEERING_NUMBER_RE.findall(source_text)))
            target_numbers = set(ENGINEERING_NUMBER_RE.findall(target_text))
            missing_numbers = sorted(set(source_numbers) - target_numbers)
            fidelity = {
                "comparison_mode": "document-coverage",
                "source": str(source),
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "exact_byte_copy": page_script.read_bytes() == source.read_bytes(),
                "source_ngram_size": ngram_size,
                "source_ngram_coverage": round(
                    len(shared_ngrams) / max(1, len(source_ngrams)), 4
                ),
                "shared_source_ngrams": len(shared_ngrams),
                "source_ngrams": len(source_ngrams),
                "missing_engineering_numbers": (
                    [{"page": None, "values": missing_numbers}]
                    if missing_numbers
                    else []
                ),
                "pages": [],
            }
            warnings.append(
                "adapted 逐页稿已记录源文档覆盖证据；语义删改仍需人工确认"
            )

    return {
        "schema_version": 1,
        "contract_version": PAGE_SCRIPT_CONTRACT_VERSION,
        "status": "blocked" if errors else "pass",
        "page_script": str(page_script),
        "page_script_sha256": hashlib.sha256(page_script.read_bytes()).hexdigest(),
        "page_count": len(pages),
        "pages": [
            {key: value for key, value in row.items() if key != "body"}
            for row in pages
        ],
        "fidelity": fidelity,
        "errors": errors,
        "warnings": warnings,
    }

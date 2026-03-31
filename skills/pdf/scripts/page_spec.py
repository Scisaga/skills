from __future__ import annotations

import re


PAGE_RANGE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


def parse_page_spec(spec: str, total_pages: int) -> list[int]:
    if total_pages <= 0:
        raise ValueError("PDF 没有可用页面。")

    text = spec.strip().lower()
    if not text:
        raise ValueError("页码范围不能为空。")
    if text == "all":
        return list(range(total_pages))

    indexes: list[int] = []
    seen: set[int] = set()

    for raw_part in text.split(","):
        part = raw_part.strip()
        if not part:
            continue

        match = PAGE_RANGE_RE.match(part)
        if match:
            start = int(match.group(1))
            end = int(match.group(2))
            ensure_page_number(start, total_pages)
            ensure_page_number(end, total_pages)
            step = 1 if end >= start else -1
            current = start
            while True:
                idx = current - 1
                indexes.append(idx)
                seen.add(idx)
                if current == end:
                    break
                current += step
            continue

        page_number = int(part)
        ensure_page_number(page_number, total_pages)
        idx = page_number - 1
        indexes.append(idx)
        seen.add(idx)

    if not indexes:
        raise ValueError(f"未能从页码范围中解析到页面：{spec}")

    return indexes


def parse_unique_page_spec(spec: str, total_pages: int) -> list[int]:
    indexes = parse_page_spec(spec, total_pages)
    unique: list[int] = []
    seen: set[int] = set()
    for idx in indexes:
        if idx in seen:
            continue
        seen.add(idx)
        unique.append(idx)
    return unique


def complement_indexes(total_pages: int, removed: list[int]) -> list[int]:
    removed_set = set(removed)
    return [idx for idx in range(total_pages) if idx not in removed_set]


def ensure_page_number(page_number: int, total_pages: int) -> None:
    if not (1 <= page_number <= total_pages):
        raise ValueError(f"页码超出范围：{page_number}（有效范围 1..{total_pages}）")

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from page_spec import complement_indexes, parse_page_spec, parse_unique_page_spec
from runtime_utils import WORKFLOW_DEPENDENCIES, ensure_dependencies

try:
    from PyPDF2 import PdfReader, PdfWriter
except ImportError:
    PdfReader = PdfWriter = None  # type: ignore[assignment]


def ensure_runtime_ready() -> None:
    ensure_dependencies(WORKFLOW_DEPENDENCIES["page-ops"])
    if PdfReader is None or PdfWriter is None:
        raise RuntimeError("页面编排依赖已安装但当前进程未能完整加载，请重新运行脚本。")


def ensure_parent(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def merge_pdfs(inputs: list[str], output_pdf: str) -> None:
    ensure_runtime_ready()
    writer = PdfWriter()
    for pdf_path in inputs:
        reader = PdfReader(pdf_path)
        for page in reader.pages:
            writer.add_page(page)
    ensure_parent(output_pdf)
    with open(output_pdf, "wb") as handle:
        writer.write(handle)


def split_pdf(input_pdf: str, output_dir: str, pattern: str) -> None:
    ensure_runtime_ready()
    reader = PdfReader(input_pdf)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    total_pages = len(reader.pages)
    width = max(3, len(str(total_pages)))
    for page_number, page in enumerate(reader.pages, start=1):
        writer = PdfWriter()
        writer.add_page(page)
        filename = pattern.format(page=page_number, index=page_number - 1, width=width)
        output_path = out_dir / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as handle:
            writer.write(handle)


def extract_pages(input_pdf: str, output_pdf: str, page_spec: str) -> None:
    ensure_runtime_ready()
    reader = PdfReader(input_pdf)
    indexes = parse_page_spec(page_spec, len(reader.pages))
    writer = PdfWriter()
    for idx in indexes:
        writer.add_page(reader.pages[idx])
    ensure_parent(output_pdf)
    with open(output_pdf, "wb") as handle:
        writer.write(handle)


def remove_pages(input_pdf: str, output_pdf: str, page_spec: str) -> None:
    ensure_runtime_ready()
    reader = PdfReader(input_pdf)
    removed = parse_unique_page_spec(page_spec, len(reader.pages))
    kept = complement_indexes(len(reader.pages), removed)
    if not kept:
        raise ValueError("删除后没有剩余页面。")
    writer = PdfWriter()
    for idx in kept:
        writer.add_page(reader.pages[idx])
    ensure_parent(output_pdf)
    with open(output_pdf, "wb") as handle:
        writer.write(handle)


def reorder_pages(input_pdf: str, output_pdf: str, page_spec: str) -> None:
    ensure_runtime_ready()
    reader = PdfReader(input_pdf)
    indexes = parse_page_spec(page_spec, len(reader.pages))
    writer = PdfWriter()
    for idx in indexes:
        writer.add_page(reader.pages[idx])
    ensure_parent(output_pdf)
    with open(output_pdf, "wb") as handle:
        writer.write(handle)


def rotate_pages(input_pdf: str, output_pdf: str, angle: int, page_spec: str) -> None:
    ensure_runtime_ready()
    if angle % 90 != 0:
        raise ValueError("旋转角度必须是 90 的整数倍。")
    reader = PdfReader(input_pdf)
    targets = set(parse_unique_page_spec(page_spec, len(reader.pages)))
    writer = PdfWriter()
    normalized = angle % 360
    for idx, page in enumerate(reader.pages):
        if idx in targets and normalized:
            page.rotate(normalized)
        writer.add_page(page)
    ensure_parent(output_pdf)
    with open(output_pdf, "wb") as handle:
        writer.write(handle)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PDF 基础页面编排工具。所有页码范围均为 1 基。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    merge_parser = subparsers.add_parser("merge", help="按顺序合并多个 PDF")
    merge_parser.add_argument("output_pdf")
    merge_parser.add_argument("inputs", nargs="+")

    split_parser = subparsers.add_parser("split", help="把 PDF 按页拆成多个单页 PDF")
    split_parser.add_argument("input_pdf")
    split_parser.add_argument("output_dir")
    split_parser.add_argument(
        "--pattern",
        default="page-{page:03d}.pdf",
        help="输出文件名模板，可用变量：page / index / width",
    )

    extract_parser = subparsers.add_parser("extract", help="按页码范围抽页")
    extract_parser.add_argument("input_pdf")
    extract_parser.add_argument("output_pdf")
    extract_parser.add_argument("pages")

    remove_parser = subparsers.add_parser("remove", help="按页码范围删页")
    remove_parser.add_argument("input_pdf")
    remove_parser.add_argument("output_pdf")
    remove_parser.add_argument("pages")

    reorder_parser = subparsers.add_parser("reorder", help="按指定顺序重排页面")
    reorder_parser.add_argument("input_pdf")
    reorder_parser.add_argument("output_pdf")
    reorder_parser.add_argument("pages")

    rotate_parser = subparsers.add_parser("rotate", help="旋转指定页或整份 PDF")
    rotate_parser.add_argument("input_pdf")
    rotate_parser.add_argument("output_pdf")
    rotate_parser.add_argument("angle", type=int, help="旋转角度，支持负数")
    rotate_parser.add_argument("--pages", default="all", help="页码范围，默认 all")

    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ensure_runtime_ready()

    if args.command == "merge":
        merge_pdfs(args.inputs, args.output_pdf)
        print(f"已生成：{args.output_pdf}")
        return 0

    if args.command == "split":
        split_pdf(args.input_pdf, args.output_dir, args.pattern)
        print(f"已输出到：{args.output_dir}")
        return 0

    if args.command == "extract":
        extract_pages(args.input_pdf, args.output_pdf, args.pages)
        print(f"已生成：{args.output_pdf}")
        return 0

    if args.command == "remove":
        remove_pages(args.input_pdf, args.output_pdf, args.pages)
        print(f"已生成：{args.output_pdf}")
        return 0

    if args.command == "reorder":
        reorder_pages(args.input_pdf, args.output_pdf, args.pages)
        print(f"已生成：{args.output_pdf}")
        return 0

    if args.command == "rotate":
        rotate_pages(args.input_pdf, args.output_pdf, args.angle, args.pages)
        print(f"已生成：{args.output_pdf}")
        return 0

    raise RuntimeError(f"未知命令：{args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1)

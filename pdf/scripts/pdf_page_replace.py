#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from runtime_utils import WORKFLOW_DEPENDENCIES, ensure_dependencies

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore[assignment]


def ensure_runtime_ready() -> None:
    ensure_dependencies(WORKFLOW_DEPENDENCIES["replace-page"])
    if fitz is None:
        raise RuntimeError("PyMuPDF 已安装但当前进程未能加载，请重新运行脚本。")


def replace_page_with_fitz(src_pdf: str, repl_pdf: str, out_pdf: str, page_number: int) -> None:
    ensure_runtime_ready()

    doc = fitz.open(src_pdf)
    rdoc = fitz.open(repl_pdf)

    if rdoc.page_count != 1:
        raise ValueError(f"替换文件必须只有 1 页，但检测到 {rdoc.page_count} 页：{repl_pdf}")

    if not (1 <= page_number <= doc.page_count):
        raise ValueError(f"页码超出范围：{page_number}（有效范围 1..{doc.page_count}）")

    idx = page_number - 1
    doc.delete_page(idx)
    doc.insert_pdf(rdoc, from_page=0, to_page=0, start_at=idx)

    Path(out_pdf).parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_pdf)
    doc.close()
    rdoc.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="使用 PyMuPDF 将 PDF 中某一页替换为另一个单页 PDF。页码为 1 基。")
    parser.add_argument("src_pdf")
    parser.add_argument("repl_pdf")
    parser.add_argument("page", type=int)
    parser.add_argument("out_pdf")
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ensure_runtime_ready()
    replace_page_with_fitz(args.src_pdf, args.repl_pdf, args.out_pdf, args.page)
    print(f"已生成：{args.out_pdf}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import sys
from io import BytesIO
from typing import Tuple

from runtime_utils import WORKFLOW_DEPENDENCIES, ensure_dependencies

try:
    from PyPDF2 import PdfReader, PdfWriter
except ImportError:
    PdfReader = PdfWriter = None  # type: ignore[assignment]

try:
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
except ImportError:
    ImageReader = canvas = None  # type: ignore[assignment]

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore[assignment]


def ensure_runtime_ready() -> None:
    ensure_dependencies(WORKFLOW_DEPENDENCIES["seam-seal"])
    if PdfReader is None or PdfWriter is None or ImageReader is None or canvas is None or Image is None:
        raise RuntimeError("PDF 骑缝章依赖已安装但当前进程未能完整加载，请重新运行脚本。")


def _slice_bounds(img_w: int, img_h: int, n: int, i: int) -> Tuple[int, int, int, int]:
    split_w = img_w // n
    if i == n - 1:
        return (i * split_w, 0, img_w, img_h)
    return (i * split_w, 0, (i + 1) * split_w, img_h)


def add_seam_seal(
    pdf_path: str,
    seal_png_path: str,
    out_path: str,
    side: str = "right",
    height_ratio: float = 0.8,
    dpi: float | None = None,
) -> None:
    ensure_runtime_ready()

    reader = PdfReader(pdf_path)
    pages = list(reader.pages)
    n_pages = len(pages)
    if n_pages == 0:
        raise RuntimeError("空 PDF")

    seal = Image.open(seal_png_path).convert("RGBA")
    img_w, img_h = seal.size

    writer = PdfWriter()

    for i, page in enumerate(pages):
        pw = float(page.mediabox.width)
        ph = float(page.mediabox.height)

        seal = Image.open(seal_png_path).convert("RGBA")
        img_w, img_h = seal.size

        if dpi and dpi > 0:
            target_h_dpi = img_h * 72.0 / dpi
            target_h = min(target_h_dpi, ph * height_ratio)
        else:
            target_h = ph * height_ratio

        scale = target_h / img_h

        x0, y0, x1, y1 = _slice_bounds(img_w, img_h, n_pages, i)
        strip = seal.crop((x0, y0, x1, y1))
        strip_w_px = x1 - x0
        strip_w_pt = strip_w_px * scale

        wm_buf = BytesIO()
        c = canvas.Canvas(wm_buf, pagesize=(pw, ph))

        x = pw - strip_w_pt if side == "right" else 0.0
        y = (ph - target_h) / 2.0

        c.drawImage(ImageReader(strip), x, y, width=strip_w_pt, height=target_h, mask="auto")
        c.save()

        wm_buf.seek(0)
        wm_pdf = PdfReader(wm_buf)
        wm_page = wm_pdf.pages[0]

        page.merge_page(wm_page)
        writer.add_page(page)

    with open(out_path, "wb") as f:
        writer.write(f)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="为 PDF 添加骑缝章（等宽竖条，首页开始，保留透明）。")
    parser.add_argument("input_pdf")
    parser.add_argument("seal_png")
    parser.add_argument("output_pdf")
    parser.add_argument("--side", choices=["right", "left"], default="right")
    parser.add_argument("--height-ratio", type=float, default=0.8, help="章在页面上的目标高度占比，默认 0.8")
    parser.add_argument("--dpi", type=float, default=560, help="按给定 DPI 把像素换算为物理尺寸；与 height-ratio 同时给时取较小值")
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ensure_runtime_ready()
    add_seam_seal(
        pdf_path=args.input_pdf,
        seal_png_path=args.seal_png,
        out_path=args.output_pdf,
        side=args.side,
        height_ratio=args.height_ratio,
        dpi=args.dpi,
    )
    print(f"已生成：{args.output_pdf}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1)

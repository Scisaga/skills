#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from page_spec import parse_page_spec
from runtime_utils import WORKFLOW_DEPENDENCIES, ensure_dependencies

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore[assignment]

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore[assignment]


def ensure_runtime_ready() -> None:
    ensure_dependencies(WORKFLOW_DEPENDENCIES["image-convert"])
    if fitz is None or Image is None:
        raise RuntimeError("图片与 PDF 互转依赖已安装但当前进程未能完整加载，请重新运行脚本。")


def images_to_pdf(output_pdf: str, inputs: list[str], dpi: int) -> None:
    ensure_runtime_ready()
    if dpi <= 0:
        raise ValueError("dpi 必须大于 0。")

    document = fitz.open()
    try:
        for image_path in inputs:
            image = Image.open(image_path)
            width_px, height_px = image.size
            width_pt = width_px * 72.0 / dpi
            height_pt = height_px * 72.0 / dpi

            page = document.new_page(width=width_pt, height=height_pt)
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            page.insert_image(page.rect, stream=buffer.getvalue())
            buffer.close()

        output_path = Path(output_pdf)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        document.save(output_pdf, deflate=True)
    finally:
        document.close()


def pdf_to_images(
    input_pdf: str,
    output_dir: str,
    pages: str,
    dpi: int,
    image_format: str,
    jpeg_quality: int,
    password: str | None,
    prefix: str,
) -> None:
    ensure_runtime_ready()
    if dpi < 72:
        raise ValueError("dpi 至少应为 72。")

    document = fitz.open(input_pdf)
    try:
        if document.needs_pass:
            if not password:
                raise RuntimeError("源 PDF 已加密，请通过 --password 提供密码。")
            if not document.authenticate(password):
                raise RuntimeError("PDF 密码不正确。")

        indexes = parse_page_spec(pages, document.page_count)
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        extension = "jpg" if image_format == "jpeg" else image_format

        for seq, idx in enumerate(indexes, start=1):
            page = document.load_page(idx)
            pix = page.get_pixmap(matrix=matrix, alpha=False, colorspace=fitz.csRGB)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            output_path = out_dir / f"{prefix}-{seq:03d}-p{idx + 1:03d}.{extension}"

            if image_format == "png":
                image.save(output_path, format="PNG", optimize=True)
            else:
                image.save(output_path, format="JPEG", quality=jpeg_quality, optimize=True)

        print(f"已输出 {len(indexes)} 张图片到：{output_dir}")
    finally:
        document.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="图片与 PDF 互转工具。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    images_parser = subparsers.add_parser("images-to-pdf", help="把多张图片合成一个 PDF")
    images_parser.add_argument("output_pdf")
    images_parser.add_argument("inputs", nargs="+")
    images_parser.add_argument("--dpi", type=int, default=150, help="按给定 DPI 推导 PDF 页面尺寸")

    export_parser = subparsers.add_parser("pdf-to-images", help="把 PDF 页面导出为 PNG/JPEG")
    export_parser.add_argument("input_pdf")
    export_parser.add_argument("output_dir")
    export_parser.add_argument("--pages", default="all", help="页码范围，默认 all")
    export_parser.add_argument("--dpi", type=int, default=200, help="导出 DPI")
    export_parser.add_argument("--format", choices=["png", "jpeg"], default="png", help="导出格式")
    export_parser.add_argument("--jpeg-quality", type=int, default=90, help="JPEG 质量 1..95")
    export_parser.add_argument("--password", default=None, help="加密 PDF 的密码")
    export_parser.add_argument("--prefix", default="page", help="输出文件名前缀")

    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ensure_runtime_ready()

    if args.command == "images-to-pdf":
        images_to_pdf(args.output_pdf, args.inputs, args.dpi)
        print(f"已生成：{args.output_pdf}")
        return 0

    if args.command == "pdf-to-images":
        pdf_to_images(
            input_pdf=args.input_pdf,
            output_dir=args.output_dir,
            pages=args.pages,
            dpi=args.dpi,
            image_format=args.format,
            jpeg_quality=args.jpeg_quality,
            password=args.password,
            prefix=args.prefix,
        )
        return 0

    raise RuntimeError(f"未知命令：{args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1)

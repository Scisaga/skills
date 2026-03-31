#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import os
import sys
from io import BytesIO
from pathlib import Path
from typing import Optional

from runtime_utils import WORKFLOW_DEPENDENCIES, ensure_dependencies

try:
    from PyPDF2 import PdfReader, PdfWriter
except ImportError:
    PdfReader = PdfWriter = None  # type: ignore[assignment]

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore[assignment]

try:
    from reportlab.lib.colors import Color
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
except ImportError:
    Color = ImageReader = TTFont = canvas = None  # type: ignore[assignment]
    pdfmetrics = None  # type: ignore[assignment]


def ensure_runtime_ready() -> None:
    ensure_dependencies(WORKFLOW_DEPENDENCIES["overlay-watermark"])
    if (
        PdfReader is None
        or PdfWriter is None
        or Image is None
        or Color is None
        or ImageReader is None
        or TTFont is None
        or canvas is None
        or pdfmetrics is None
    ):
        raise RuntimeError("普通水印依赖已安装但当前进程未能完整加载，请重新运行脚本。")


def parse_hex_color(value: str) -> tuple[float, float, float]:
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        raise ValueError(f"无效颜色值：{value}")
    red = int(text[0:2], 16) / 255.0
    green = int(text[2:4], 16) / 255.0
    blue = int(text[4:6], 16) / 255.0
    return red, green, blue


def register_font(font_path: Optional[str]) -> str:
    if font_path and os.path.isfile(font_path):
        font_name = f"overlay_font_{abs(hash(os.path.abspath(font_path)))}"
        try:
            pdfmetrics.getFont(font_name)
        except KeyError:
            pdfmetrics.registerFont(TTFont(font_name, font_path))
        return font_name
    return "Helvetica"


def adjust_image_opacity(path: str, opacity: float) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    if not 0 <= opacity <= 1:
        raise ValueError("wm-opacity 必须在 0 到 1 之间。")
    if opacity < 1:
        alpha = image.getchannel("A")
        alpha = alpha.point(lambda value: int(value * opacity))
        image.putalpha(alpha)
    return image


def draw_text_overlay(
    painter: canvas.Canvas,
    page_width: float,
    page_height: float,
    text: str,
    font_name: str,
    font_size: int,
    color_rgb: tuple[float, float, float],
    angle: float,
    opacity: float,
    spacing: int,
    line_spacing: int,
) -> None:
    lines = text.splitlines() or [text]
    line_height = font_size + max(line_spacing, 0)
    text_width = max(pdfmetrics.stringWidth(line, font_name, font_size) for line in lines if line) if any(lines) else font_size
    tile_width = max(text_width, font_size) + 20
    tile_height = max(line_height * len(lines), font_size) + 20

    diagonal = math.hypot(page_width, page_height)
    x_positions = range(int(-diagonal), int(diagonal * 2) + spacing, max(spacing, 1))
    y_positions = range(int(-diagonal), int(diagonal * 2) + spacing, max(spacing, 1))

    painter.saveState()
    if hasattr(painter, "setFillAlpha"):
        painter.setFillAlpha(opacity)
    painter.setFillColor(Color(*color_rgb))
    painter.setFont(font_name, font_size)

    for origin_y in y_positions:
        for origin_x in x_positions:
            painter.saveState()
            painter.translate(origin_x, origin_y)
            painter.rotate(angle)
            text_object = painter.beginText()
            text_object.setTextOrigin(0, 0)
            text_object.setFont(font_name, font_size)
            if hasattr(text_object, "setLeading"):
                text_object.setLeading(line_height)
            for line in lines:
                text_object.textLine(line)
            painter.drawText(text_object)
            painter.restoreState()

            if tile_width <= 0 or tile_height <= 0:
                continue

    painter.restoreState()


def draw_image_overlay(
    painter: canvas.Canvas,
    page_width: float,
    page_height: float,
    image_path: str,
    angle: float,
    opacity: float,
    scale: float,
    spacing: int,
) -> None:
    image = adjust_image_opacity(image_path, opacity)
    target_width = max(page_width * scale, 1.0)
    target_height = target_width * image.height / image.width
    diagonal = math.hypot(page_width, page_height)
    x_positions = range(int(-diagonal), int(diagonal * 2) + spacing, max(spacing, 1))
    y_positions = range(int(-diagonal), int(diagonal * 2) + spacing, max(spacing, 1))

    painter.saveState()
    for origin_y in y_positions:
        for origin_x in x_positions:
            painter.saveState()
            painter.translate(origin_x, origin_y)
            painter.rotate(angle)
            painter.drawImage(
                ImageReader(image),
                0,
                0,
                width=target_width,
                height=target_height,
                mask="auto",
                preserveAspectRatio=True,
            )
            painter.restoreState()
    painter.restoreState()


def build_overlay_pdf(
    page_width: float,
    page_height: float,
    wm_text: Optional[str],
    wm_img: Optional[str],
    wm_font: Optional[str],
    wm_font_size: int,
    wm_color: tuple[float, float, float],
    wm_angle: float,
    wm_opacity: float,
    wm_spacing: int,
    wm_line_spacing: int,
    wm_img_scale: float,
    wm_img_spacing: int,
) -> BytesIO:
    if not wm_text and not wm_img:
        raise ValueError("必须至少提供 --wm-text 或 --wm-img。")

    font_name = register_font(wm_font)
    buffer = BytesIO()
    painter = canvas.Canvas(buffer, pagesize=(page_width, page_height))

    if wm_text:
        draw_text_overlay(
            painter=painter,
            page_width=page_width,
            page_height=page_height,
            text=wm_text,
            font_name=font_name,
            font_size=wm_font_size,
            color_rgb=wm_color,
            angle=wm_angle,
            opacity=wm_opacity,
            spacing=wm_spacing,
            line_spacing=wm_line_spacing,
        )

    if wm_img:
        draw_image_overlay(
            painter=painter,
            page_width=page_width,
            page_height=page_height,
            image_path=wm_img,
            angle=wm_angle,
            opacity=wm_opacity,
            scale=wm_img_scale,
            spacing=wm_img_spacing,
        )

    painter.save()
    buffer.seek(0)
    return buffer


def overlay_watermark_pdf(
    src_pdf: str,
    out_pdf: str,
    wm_text: Optional[str] = None,
    wm_img: Optional[str] = None,
    wm_font: Optional[str] = None,
    wm_font_size: int = 48,
    wm_color: tuple[float, float, float] = (0.4, 0.4, 0.4),
    wm_angle: float = -30.0,
    wm_opacity: float = 0.12,
    wm_spacing: int = 220,
    wm_line_spacing: int = 12,
    wm_img_scale: float = 0.28,
    wm_img_spacing: int = 260,
) -> None:
    ensure_runtime_ready()

    reader = PdfReader(src_pdf)
    writer = PdfWriter()

    for page in reader.pages:
        page_width = float(page.mediabox.width)
        page_height = float(page.mediabox.height)
        overlay_buffer = build_overlay_pdf(
            page_width=page_width,
            page_height=page_height,
            wm_text=wm_text,
            wm_img=wm_img,
            wm_font=wm_font,
            wm_font_size=wm_font_size,
            wm_color=wm_color,
            wm_angle=wm_angle,
            wm_opacity=wm_opacity,
            wm_spacing=wm_spacing,
            wm_line_spacing=wm_line_spacing,
            wm_img_scale=wm_img_scale,
            wm_img_spacing=wm_img_spacing,
        )
        overlay_reader = PdfReader(overlay_buffer)
        page.merge_page(overlay_reader.pages[0])
        writer.add_page(page)

    output_path = Path(out_pdf)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as handle:
        writer.write(handle)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="为 PDF 添加保留文本层的普通水印。")
    parser.add_argument("src_pdf")
    parser.add_argument("out_pdf")
    parser.add_argument("--wm-text", type=str, default=None, help="文字水印内容")
    parser.add_argument("--wm-img", type=str, default=None, help="图片水印路径（PNG/JPG）")
    parser.add_argument("--wm-font", type=str, default=None, help="文字水印字体路径")
    parser.add_argument("--wm-font-size", type=int, default=48, help="文字水印字号，单位 pt")
    parser.add_argument("--wm-color", type=str, default="#666666", help="文字水印颜色，十六进制格式")
    parser.add_argument("--wm-angle", type=float, default=-30.0, help="水印角度")
    parser.add_argument("--wm-opacity", type=float, default=0.12, help="水印透明度，范围 0..1")
    parser.add_argument("--wm-spacing", type=int, default=220, help="文字水印平铺间距，单位 pt")
    parser.add_argument("--wm-line-spacing", type=int, default=12, help="多行文字行距，单位 pt")
    parser.add_argument("--wm-img-scale", type=float, default=0.28, help="图片水印宽度占页面宽度的比例")
    parser.add_argument("--wm-img-spacing", type=int, default=260, help="图片水印平铺间距，单位 pt")
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ensure_runtime_ready()
    overlay_watermark_pdf(
        src_pdf=args.src_pdf,
        out_pdf=args.out_pdf,
        wm_text=args.wm_text,
        wm_img=args.wm_img,
        wm_font=args.wm_font,
        wm_font_size=args.wm_font_size,
        wm_color=parse_hex_color(args.wm_color),
        wm_angle=args.wm_angle,
        wm_opacity=args.wm_opacity,
        wm_spacing=args.wm_spacing,
        wm_line_spacing=args.wm_line_spacing,
        wm_img_scale=args.wm_img_scale,
        wm_img_spacing=args.wm_img_spacing,
    )
    print(f"已生成：{args.out_pdf}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1)

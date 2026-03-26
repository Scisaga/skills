#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rasterise a PDF into an image-only PDF, then burn in tiled text or image watermarks.

Dependencies:
  pip install PyMuPDF Pillow

Example:
  python3 pdf_to_image_pdf_with_watermark.py in.pdf out.pdf \
      --dpi 225 \
      --wm-text "PsiAI Planning Engine -- 2025-10-22" \
      --wm-font ./assets/fonts/Consolas-with-Yahei.ttf \
      --wm-font-index 0 \
      --wm-font-size 60 \
      --wm-line-spacing 60 \
      --wm-angle -30 \
      --wm-opacity 0.08 \
      --wm-spacing 520 \
      --wm-color "#FFFFFF" \
      --wm-stroke-width 2 \
      --wm-stroke-color "#FFFFFF" \
      --image-format jpeg \
      --jpeg-quality 88

  python3 pdf_to_image_pdf_with_watermark.py in.pdf out.pdf \
      --wm-img logo.png \
      --wm-img-scale 0.35 \
      --wm-img-spacing 600
"""

from __future__ import annotations

import argparse
import io
import math
import os
import sys
from typing import Any, List, Optional, Tuple, Union, cast

from runtime_utils import WORKFLOW_DEPENDENCIES, ensure_dependencies

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore[assignment]

try:
    from PIL import Image, ImageDraw, ImageFont
    from PIL.Image import Resampling
    from PIL.ImageFont import FreeTypeFont, ImageFont as ImageFontBase, TransposedFont
except ImportError:
    Image = ImageDraw = ImageFont = None  # type: ignore[assignment]
    Resampling = None  # type: ignore[assignment]
    FreeTypeFont = ImageFontBase = TransposedFont = Any  # type: ignore[assignment]

ColorTuple = Tuple[int, int, int]
FontLike = Union[FreeTypeFont, ImageFontBase, TransposedFont]


def ensure_runtime_ready() -> None:
    ensure_dependencies(WORKFLOW_DEPENDENCIES["watermark"])
    if fitz is None or Image is None or ImageDraw is None or ImageFont is None or Resampling is None:
        raise RuntimeError("PDF 水印依赖已安装但当前进程未能完整加载，请重新运行脚本。")


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def parse_hex_color(s: str) -> ColorTuple:
    value = s.strip().lstrip("#")
    if len(value) == 3:
        r, g, b = (int(value[i] * 2, 16) for i in range(3))
    elif len(value) == 6:
        r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    else:
        raise ValueError(f"Invalid colour: {s}")
    return (r, g, b)


def ensure_rgba(img: Image.Image) -> Image.Image:
    return img.convert("RGBA") if img.mode != "RGBA" else img


def load_font(
    font_path: Optional[str],
    font_size: int,
    font_index: int = 0,
) -> FontLike:
    """
    Load a font object.

    The return type needs to satisfy Pillow's drawing APIs. Pylance/pyright do not
    recognise the relationship between ``ImageFont.FreeTypeFont`` and the documented
    ``ImageFont.ImageFont`` base, so we intentionally cast to an explicit union.
    """
    if font_path and os.path.exists(font_path):
        try:
            return cast(FontLike, ImageFont.truetype(font_path, font_size, index=font_index))
        except Exception:
            try:
                return cast(FontLike, ImageFont.truetype(font_path, font_size))
            except Exception:
                pass

    for candidate in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return cast(FontLike, ImageFont.truetype(candidate, font_size))
        except Exception:
            continue

    return cast(FontLike, ImageFont.load_default())


def draw_text_tile_overlay(
    base_size: Tuple[int, int],
    text: str,
    font: FontLike,
    angle: float,
    opacity: float,
    spacing: int,
    fill_rgb: ColorTuple,
    line_spacing_px: int = 8,
    stroke_width: int = 0,
    stroke_rgb: Optional[ColorTuple] = None,
) -> Image.Image:
    """
    Generate an RGBA overlay that tiles the given text diagonally.
    """
    width, height = base_size
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    scratch = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw_scratch = ImageDraw.Draw(scratch)
    try:
        bbox = draw_scratch.multiline_textbbox((0, 0), text, font=font, spacing=line_spacing_px)
    except AttributeError:
        bbox = draw_scratch.textbbox((0, 0), text, font=font)

    text_width = int(math.ceil(bbox[2] - bbox[0]))
    text_height = int(math.ceil(bbox[3] - bbox[1]))

    tile = Image.new("RGBA", (text_width + 20, text_height + 20), (0, 0, 0, 0))
    draw_tile = ImageDraw.Draw(tile)
    try:
        draw_tile.multiline_text(
            (10, 10),
            text,
            font=font,
            fill=fill_rgb + (255,),
            spacing=line_spacing_px,
            stroke_width=stroke_width,
            stroke_fill=(stroke_rgb + (255,)) if stroke_rgb else None,
        )
    except TypeError:
        draw_tile.multiline_text((10, 10), text, font=font, fill=fill_rgb + (255,), spacing=line_spacing_px)

    rotated = tile.rotate(angle, expand=True, resample=Resampling.BICUBIC)

    step = max(spacing, 1)
    for y in range(-rotated.height, height + rotated.height, step):
        for x in range(-rotated.width, width + rotated.width, step):
            overlay.alpha_composite(rotated, (x, y))

    if not 0 <= opacity <= 1:
        raise ValueError("opacity must be in [0, 1]")
    if opacity < 1:
        r, g, b, a = overlay.split()
        a = a.point(lambda v: int(v * opacity))
        overlay.putalpha(a)

    return overlay


def draw_image_tile_overlay(
    base_size: Tuple[int, int],
    wm_img: Image.Image,
    angle: float,
    opacity: float,
    scale: float,
    spacing: int,
) -> Image.Image:
    """
    Generate an RGBA overlay that tiles an image watermark diagonally.
    """
    width, height = base_size
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    watermark = ensure_rgba(wm_img)
    if scale <= 0:
        scale = 0.3

    target_width = max(1, int(width * scale))
    aspect = watermark.height / watermark.width
    resized = watermark.resize(
        (target_width, max(1, int(target_width * aspect))),
        Resampling.LANCZOS,
    )

    rotated = resized.rotate(angle, expand=True, resample=Resampling.BICUBIC)

    if not 0 <= opacity <= 1:
        raise ValueError("opacity must be in [0, 1]")
    if opacity < 1:
        r, g, b, a = rotated.split()
        a = a.point(lambda v: int(v * opacity))
        rotated.putalpha(a)

    step = max(spacing, 1)
    for y in range(-rotated.height, height + rotated.height, step):
        for x in range(-rotated.width, width + rotated.width, step):
            overlay.alpha_composite(rotated, (x, y))

    return overlay


def apply_watermark(
    img: Image.Image,
    text: Optional[str] = None,
    font_path: Optional[str] = None,
    font_size: int = 64,
    color_rgb: ColorTuple = (0, 0, 0),
    angle: float = -30,
    opacity: float = 0.12,
    spacing: int = 480,
    img_watermark: Optional[Image.Image] = None,
    img_scale: float = 0.35,
    img_spacing: int = 600,
    text_line_spacing: int = 8,
    font_index: int = 0,
    text_stroke_width: int = 0,
    text_stroke_color: Optional[ColorTuple] = None,
) -> Image.Image:
    base = ensure_rgba(img)
    overlays: List[Image.Image] = []

    if text:
        font = load_font(font_path, font_size, font_index)
        overlays.append(
            draw_text_tile_overlay(
                base.size,
                text,
                font,
                angle,
                opacity,
                spacing,
                color_rgb,
                line_spacing_px=text_line_spacing,
                stroke_width=text_stroke_width,
                stroke_rgb=text_stroke_color,
            )
        )

    if img_watermark is not None:
        overlays.append(
            draw_image_tile_overlay(
                base.size,
                img_watermark,
                angle,
                opacity,
                img_scale,
                img_spacing,
            )
        )

    for overlay in overlays:
        base = Image.alpha_composite(base, overlay)

    return base.convert("RGB")


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------


def rasterize_pdf_to_image_pdf(
    src_pdf: str,
    out_pdf: str,
    dpi: int = 300,
    image_format: str = "jpeg",
    jpeg_quality: int = 85,
    password: Optional[str] = None,
    wm_text: Optional[str] = None,
    wm_font: Optional[str] = None,
    wm_font_size: int = 64,
    wm_color: ColorTuple = (0, 0, 0),
    wm_angle: float = -30,
    wm_opacity: float = 0.12,
    wm_spacing: int = 480,
    wm_img_path: Optional[str] = None,
    wm_img_scale: float = 0.35,
    wm_img_spacing: int = 600,
    wm_line_spacing: int = 8,
    wm_font_index: int = 0,
    wm_text_stroke_width: int = 0,
    wm_text_stroke_color: Optional[ColorTuple] = None,
) -> None:
    """
    Render every page of the source PDF to an image, apply the requested watermarks,
    and write the rasterised pages into a new PDF.
    """
    ensure_runtime_ready()

    if dpi < 72:
        raise ValueError("dpi must be at least 72; 200-300 is usually best")

    doc = cast(Any, fitz.open(src_pdf))
    out_doc: Optional[Any] = None

    try:
        if doc.needs_pass:
            if not password:
                raise RuntimeError("The source PDF is encrypted; supply --password")
            if not doc.authenticate(password):
                raise RuntimeError("Incorrect password for the source PDF")

        out_doc = cast(Any, fitz.open())
        if out_doc is None:
            raise RuntimeError("failed to create output PDF document")

        watermark_image: Optional[Image.Image] = None
        if wm_img_path:
            watermark_image = Image.open(wm_img_path)

        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)

        total_pages = doc.page_count
        for index, page in enumerate(doc, start=1):
            rect = page.rect
            pix = page.get_pixmap(matrix=matrix, alpha=False, colorspace=fitz.csRGB)
            img = Image.frombytes("RGB", (int(pix.width), int(pix.height)), pix.samples)

            watermarked = apply_watermark(
                img,
                text=wm_text,
                font_path=wm_font,
                font_size=wm_font_size,
                color_rgb=wm_color,
                angle=wm_angle,
                opacity=wm_opacity,
                spacing=wm_spacing,
                img_watermark=watermark_image,
                img_scale=wm_img_scale,
                img_spacing=wm_img_spacing,
                text_line_spacing=wm_line_spacing,
                font_index=wm_font_index,
                text_stroke_width=wm_text_stroke_width,
                text_stroke_color=wm_text_stroke_color,
            )

            assert out_doc is not None
            new_page = out_doc.new_page(width=rect.width, height=rect.height)
            buffer = io.BytesIO()
            fmt = image_format.lower()

            if fmt in ("jpeg", "jpg"):
                watermarked.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
            elif fmt == "png":
                watermarked.save(buffer, format="PNG", optimize=True)
            else:
                raise ValueError("image-format must be either 'jpeg' or 'png'")

            new_page.insert_image(new_page.rect, stream=buffer.getvalue())
            buffer.close()

            print(f"[{index}/{total_pages}] done: {pix.width}x{pix.height} @ {dpi} dpi")

        try:
            raw_meta = doc.metadata or {}
            metadata = {k: v for k, v in raw_meta.items() if isinstance(k, str) and isinstance(v, str)}
            producer = metadata.get("producer") or ""
            metadata["producer"] = f"{producer}; rasterized-by=PyMuPDF+Pillow".strip("; ")
            if out_doc is not None:
                out_doc.set_metadata(metadata)  # type: ignore[arg-type]
        except Exception:
            pass

        assert out_doc is not None
        out_doc.save(out_pdf, deflate=True)
    finally:
        if out_doc is not None:
            try:
                out_doc.close()
            except Exception:
                pass
        try:
            doc.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Rasterise a PDF and add tiled watermarks.")
    parser.add_argument("src", help="input PDF path")
    parser.add_argument("dst", help="output PDF path")

    parser.add_argument("--dpi", type=int, default=300, help="render DPI (recommend 200-300)")
    parser.add_argument("--password", type=str, default=None, help="password if the source PDF is encrypted")

    parser.add_argument(
        "--image-format",
        choices=["jpeg", "png"],
        default="jpeg",
        help="image encoding used inside the output PDF",
    )
    parser.add_argument("--jpeg-quality", type=int, default=85, help="JPEG quality 1-95")

    parser.add_argument("--wm-text", type=str, default=None, help="text watermark (leave empty to skip)")
    parser.add_argument("--wm-font", type=str, default=None, help="font path for the text watermark")
    parser.add_argument("--wm-font-index", type=int, default=0, help="font index when using TTC collections")
    parser.add_argument("--wm-font-size", type=int, default=64, help="font size for the text watermark")
    parser.add_argument("--wm-color", type=str, default="#000000", help="text colour (hex form, e.g. #000000)")
    parser.add_argument("--wm-angle", type=float, default=-30.0, help="rotation angle (negative is counter-clockwise)")
    parser.add_argument("--wm-opacity", type=float, default=0.12, help="watermark opacity between 0 and 1")
    parser.add_argument("--wm-spacing", type=int, default=480, help="tile spacing in pixels")
    parser.add_argument("--wm-line-spacing", type=int, default=8, help="line spacing in pixels for multiline text")
    parser.add_argument(
        "--wm-stroke-width",
        type=int,
        default=0,
        help="optional text outline width, useful for readability after compression",
    )
    parser.add_argument(
        "--wm-stroke-color",
        type=str,
        default=None,
        help="hex stroke colour; leave empty for no outline",
    )

    parser.add_argument("--wm-img", type=str, default=None, help="path to an image watermark (PNG/JPG)")
    parser.add_argument("--wm-img-scale", type=float, default=0.35, help="image watermark width relative to page width")
    parser.add_argument("--wm-img-spacing", type=int, default=600, help="tile spacing for image watermarks")

    args = parser.parse_args()
    ensure_runtime_ready()

    try:
        color_rgb = parse_hex_color(args.wm_color)
        stroke_rgb = parse_hex_color(args.wm_stroke_color) if args.wm_stroke_color else None
        rasterize_pdf_to_image_pdf(
            src_pdf=args.src,
            out_pdf=args.dst,
            dpi=args.dpi,
            image_format=args.image_format,
            jpeg_quality=args.jpeg_quality,
            password=args.password,
            wm_text=args.wm_text,
            wm_font=args.wm_font,
            wm_font_size=args.wm_font_size,
            wm_color=color_rgb,
            wm_angle=args.wm_angle,
            wm_opacity=args.wm_opacity,
            wm_spacing=args.wm_spacing,
            wm_img_path=args.wm_img,
            wm_img_scale=args.wm_img_scale,
            wm_img_spacing=args.wm_img_spacing,
            wm_line_spacing=args.wm_line_spacing,
            wm_font_index=args.wm_font_index,
            wm_text_stroke_width=args.wm_stroke_width,
            wm_text_stroke_color=stroke_rgb,
        )
        print(f"Completed: {args.dst}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1)

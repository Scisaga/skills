#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from add_qifeng_seal import add_seam_seal
from pdf_overlay_watermark import overlay_watermark_pdf, parse_hex_color
from pdf_to_image_pdf_with_watermark import rasterize_pdf_to_image_pdf
from runtime_utils import WORKFLOW_DEPENDENCIES, ensure_dependencies


def ensure_runtime_ready() -> None:
    ensure_dependencies(WORKFLOW_DEPENDENCIES["batch"])


def collect_pdfs(input_dir: str, recursive: bool) -> list[Path]:
    root = Path(input_dir)
    if not root.is_dir():
        raise ValueError(f"输入目录不存在：{input_dir}")
    pattern = "**/*.pdf" if recursive else "*.pdf"
    files = sorted(path for path in root.glob(pattern) if path.is_file())
    if not files:
        raise ValueError(f"目录中未找到 PDF：{input_dir}")
    return files


def build_output_path(input_root: Path, output_root: Path, source: Path, suffix: str) -> Path:
    relative = source.relative_to(input_root)
    stem = source.stem
    output_name = f"{stem}{suffix}.pdf"
    return output_root / relative.parent / output_name


def run_overlay_batch(
    input_dir: str,
    output_dir: str,
    recursive: bool,
    suffix: str,
    wm_text: str | None,
    wm_img: str | None,
    wm_font: str | None,
    wm_font_size: int,
    wm_color: str,
    wm_angle: float,
    wm_opacity: float,
    wm_spacing: int,
    wm_line_spacing: int,
    wm_img_scale: float,
    wm_img_spacing: int,
) -> None:
    input_root = Path(input_dir)
    output_root = Path(output_dir)
    for source in collect_pdfs(input_dir, recursive):
        target = build_output_path(input_root, output_root, source, suffix)
        target.parent.mkdir(parents=True, exist_ok=True)
        overlay_watermark_pdf(
            src_pdf=str(source),
            out_pdf=str(target),
            wm_text=wm_text,
            wm_img=wm_img,
            wm_font=wm_font,
            wm_font_size=wm_font_size,
            wm_color=parse_hex_color(wm_color),
            wm_angle=wm_angle,
            wm_opacity=wm_opacity,
            wm_spacing=wm_spacing,
            wm_line_spacing=wm_line_spacing,
            wm_img_scale=wm_img_scale,
            wm_img_spacing=wm_img_spacing,
        )
        print(f"[overlay] {source} -> {target}")


def run_rasterize_batch(
    input_dir: str,
    output_dir: str,
    recursive: bool,
    suffix: str,
    dpi: int,
    image_format: str,
    jpeg_quality: int,
    password: str | None,
    wm_text: str | None,
    wm_font: str | None,
    wm_font_size: int,
    wm_color: str,
    wm_angle: float,
    wm_opacity: float,
    wm_spacing: int,
    wm_img: str | None,
    wm_img_scale: float,
    wm_img_spacing: int,
    wm_line_spacing: int,
    wm_font_index: int,
    wm_stroke_width: int,
    wm_stroke_color: str | None,
) -> None:
    input_root = Path(input_dir)
    output_root = Path(output_dir)
    stroke_color = parse_hex_color(wm_stroke_color) if wm_stroke_color else None
    for source in collect_pdfs(input_dir, recursive):
        target = build_output_path(input_root, output_root, source, suffix)
        target.parent.mkdir(parents=True, exist_ok=True)
        rasterize_pdf_to_image_pdf(
            src_pdf=str(source),
            out_pdf=str(target),
            dpi=dpi,
            image_format=image_format,
            jpeg_quality=jpeg_quality,
            password=password,
            wm_text=wm_text,
            wm_font=wm_font,
            wm_font_size=wm_font_size,
            wm_color=tuple(int(channel * 255) for channel in parse_hex_color(wm_color)),
            wm_angle=wm_angle,
            wm_opacity=wm_opacity,
            wm_spacing=wm_spacing,
            wm_img_path=wm_img,
            wm_img_scale=wm_img_scale,
            wm_img_spacing=wm_img_spacing,
            wm_line_spacing=wm_line_spacing,
            wm_font_index=wm_font_index,
            wm_text_stroke_width=wm_stroke_width,
            wm_text_stroke_color=tuple(int(channel * 255) for channel in stroke_color) if stroke_color else None,
        )
        print(f"[rasterize] {source} -> {target}")


def run_seal_batch(
    input_dir: str,
    output_dir: str,
    seal_png: str,
    recursive: bool,
    suffix: str,
    side: str,
    height_ratio: float,
    dpi: float,
) -> None:
    input_root = Path(input_dir)
    output_root = Path(output_dir)
    for source in collect_pdfs(input_dir, recursive):
        target = build_output_path(input_root, output_root, source, suffix)
        target.parent.mkdir(parents=True, exist_ok=True)
        add_seam_seal(
            pdf_path=str(source),
            seal_png_path=seal_png,
            out_path=str(target),
            side=side,
            height_ratio=height_ratio,
            dpi=dpi,
        )
        print(f"[seal] {source} -> {target}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="批量处理目录中的 PDF。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    overlay_parser = subparsers.add_parser("overlay-watermark", help="批量添加保留文本层的普通水印")
    overlay_parser.add_argument("input_dir")
    overlay_parser.add_argument("output_dir")
    overlay_parser.add_argument("--recursive", action="store_true", help="递归扫描子目录")
    overlay_parser.add_argument("--suffix", default="-overlay", help="输出文件名后缀")
    overlay_parser.add_argument("--wm-text", default=None)
    overlay_parser.add_argument("--wm-img", default=None)
    overlay_parser.add_argument("--wm-font", default=None)
    overlay_parser.add_argument("--wm-font-size", type=int, default=48)
    overlay_parser.add_argument("--wm-color", default="#666666")
    overlay_parser.add_argument("--wm-angle", type=float, default=-30.0)
    overlay_parser.add_argument("--wm-opacity", type=float, default=0.12)
    overlay_parser.add_argument("--wm-spacing", type=int, default=220)
    overlay_parser.add_argument("--wm-line-spacing", type=int, default=12)
    overlay_parser.add_argument("--wm-img-scale", type=float, default=0.28)
    overlay_parser.add_argument("--wm-img-spacing", type=int, default=260)

    rasterize_parser = subparsers.add_parser("rasterize-watermark", help="批量栅格化并烧录水印")
    rasterize_parser.add_argument("input_dir")
    rasterize_parser.add_argument("output_dir")
    rasterize_parser.add_argument("--recursive", action="store_true", help="递归扫描子目录")
    rasterize_parser.add_argument("--suffix", default="-rasterized", help="输出文件名后缀")
    rasterize_parser.add_argument("--dpi", type=int, default=300)
    rasterize_parser.add_argument("--password", default=None)
    rasterize_parser.add_argument("--image-format", choices=["jpeg", "png"], default="jpeg")
    rasterize_parser.add_argument("--jpeg-quality", type=int, default=85)
    rasterize_parser.add_argument("--wm-text", default=None)
    rasterize_parser.add_argument("--wm-font", default=None)
    rasterize_parser.add_argument("--wm-font-size", type=int, default=64)
    rasterize_parser.add_argument("--wm-color", default="#000000")
    rasterize_parser.add_argument("--wm-angle", type=float, default=-30.0)
    rasterize_parser.add_argument("--wm-opacity", type=float, default=0.12)
    rasterize_parser.add_argument("--wm-spacing", type=int, default=480)
    rasterize_parser.add_argument("--wm-img", default=None)
    rasterize_parser.add_argument("--wm-img-scale", type=float, default=0.35)
    rasterize_parser.add_argument("--wm-img-spacing", type=int, default=600)
    rasterize_parser.add_argument("--wm-line-spacing", type=int, default=8)
    rasterize_parser.add_argument("--wm-font-index", type=int, default=0)
    rasterize_parser.add_argument("--wm-stroke-width", type=int, default=0)
    rasterize_parser.add_argument("--wm-stroke-color", default=None)

    seal_parser = subparsers.add_parser("seam-seal", help="批量添加骑缝章")
    seal_parser.add_argument("input_dir")
    seal_parser.add_argument("output_dir")
    seal_parser.add_argument("seal_png")
    seal_parser.add_argument("--recursive", action="store_true", help="递归扫描子目录")
    seal_parser.add_argument("--suffix", default="-sealed", help="输出文件名后缀")
    seal_parser.add_argument("--side", choices=["left", "right"], default="right")
    seal_parser.add_argument("--height-ratio", type=float, default=0.8)
    seal_parser.add_argument("--dpi", type=float, default=560)

    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ensure_runtime_ready()

    if args.command == "overlay-watermark":
        run_overlay_batch(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            recursive=args.recursive,
            suffix=args.suffix,
            wm_text=args.wm_text,
            wm_img=args.wm_img,
            wm_font=args.wm_font,
            wm_font_size=args.wm_font_size,
            wm_color=args.wm_color,
            wm_angle=args.wm_angle,
            wm_opacity=args.wm_opacity,
            wm_spacing=args.wm_spacing,
            wm_line_spacing=args.wm_line_spacing,
            wm_img_scale=args.wm_img_scale,
            wm_img_spacing=args.wm_img_spacing,
        )
        return 0

    if args.command == "rasterize-watermark":
        run_rasterize_batch(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            recursive=args.recursive,
            suffix=args.suffix,
            dpi=args.dpi,
            image_format=args.image_format,
            jpeg_quality=args.jpeg_quality,
            password=args.password,
            wm_text=args.wm_text,
            wm_font=args.wm_font,
            wm_font_size=args.wm_font_size,
            wm_color=args.wm_color,
            wm_angle=args.wm_angle,
            wm_opacity=args.wm_opacity,
            wm_spacing=args.wm_spacing,
            wm_img=args.wm_img,
            wm_img_scale=args.wm_img_scale,
            wm_img_spacing=args.wm_img_spacing,
            wm_line_spacing=args.wm_line_spacing,
            wm_font_index=args.wm_font_index,
            wm_stroke_width=args.wm_stroke_width,
            wm_stroke_color=args.wm_stroke_color,
        )
        return 0

    if args.command == "seam-seal":
        run_seal_batch(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            seal_png=args.seal_png,
            recursive=args.recursive,
            suffix=args.suffix,
            side=args.side,
            height_ratio=args.height_ratio,
            dpi=args.dpi,
        )
        return 0

    raise RuntimeError(f"未知命令：{args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1)

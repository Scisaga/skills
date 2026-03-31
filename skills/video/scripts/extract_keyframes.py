#!/usr/bin/env python3
import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from common import media_duration, resolve_binary, run_command


def even_sample(items: list[Path], max_items: int) -> list[Path]:
    if len(items) <= max_items:
        return items
    if max_items <= 1:
        return [items[0]]
    positions = [
        round(idx * (len(items) - 1) / (max_items - 1))
        for idx in range(max_items)
    ]
    return [items[position] for position in positions]


def extract_scene_frames(
    *,
    ffmpeg_bin: str,
    input_file: Path,
    temp_dir: Path,
    scene_threshold: float,
    width: int,
) -> list[Path]:
    output_pattern = temp_dir / "scene_%04d.jpg"
    run_command(
        [
            ffmpeg_bin,
            "-hide_banner",
            "-y",
            "-i",
            str(input_file),
            "-vf",
            f"select='gt(scene,{scene_threshold})',scale='min({width},iw)':-2",
            "-fps_mode",
            "vfr",
            str(output_pattern),
        ],
        check=False,
    )
    return sorted(temp_dir.glob("scene_*.jpg"))


def extract_even_frames(
    *,
    ffmpeg_bin: str,
    input_file: Path,
    output_dir: Path,
    width: int,
    max_frames: int,
) -> list[Path]:
    duration = max(1.0, media_duration(input_file))
    fps = max_frames / duration
    output_pattern = output_dir / "frame_%04d.jpg"
    run_command(
        [
            ffmpeg_bin,
            "-hide_banner",
            "-y",
            "-i",
            str(input_file),
            "-vf",
            f"fps={fps:.6f},scale='min({width},iw)':-2",
            "-frames:v",
            str(max_frames),
            str(output_pattern),
        ]
    )
    return sorted(output_dir.glob("frame_*.jpg"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sample keyframes from a video into JPG files")
    parser.add_argument("--input-file", required=True, help="输入视频路径")
    parser.add_argument("--output-dir", required=True, help="图片输出目录")
    parser.add_argument("--max-frames", type=int, default=12, help="最多输出多少张图")
    parser.add_argument("--scene-threshold", type=float, default=0.35, help="场景切换阈值")
    parser.add_argument("--width", type=int, default=1280, help="输出图片最大宽度")
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_file = Path(args.input_file)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_bin = resolve_binary("ffmpeg")

    with tempfile.TemporaryDirectory(prefix="video-keyframes-") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        scene_frames = extract_scene_frames(
            ffmpeg_bin=ffmpeg_bin,
            input_file=input_file,
            temp_dir=temp_dir,
            scene_threshold=args.scene_threshold,
            width=args.width,
        )

        if scene_frames:
            chosen = even_sample(scene_frames, args.max_frames)
            for idx, frame in enumerate(chosen, start=1):
                target = output_dir / f"frame_{idx:04d}.jpg"
                shutil.copy2(frame, target)
            print(f"已按场景切换抽取 {len(chosen)} 张关键帧到 {output_dir}")
            return 0

    extracted = extract_even_frames(
        ffmpeg_bin=ffmpeg_bin,
        input_file=input_file,
        output_dir=output_dir,
        width=args.width,
        max_frames=max(1, args.max_frames),
    )
    print(f"未检测到明显场景切换，已按时间均匀抽取 {len(extracted)} 张图片到 {output_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)

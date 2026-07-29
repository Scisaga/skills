#!/usr/bin/env python3
"""Validate the reusable contracts of a narrated-presentation project."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Sequence

from production_common import (
    approval_status,
    canonical_hash,
    load_project_config,
    load_voice_profile,
    normalize_director_pages,
    project_paths,
)
from validate_input_document import gate_document


SUPPORTED_EFFECTS = {
    "fade",
    "wipe_left",
    "wipe_right",
    "wipe_up",
    "wipe_down",
}
RATE_RE = re.compile(r"^[+-]\d+%$")


def load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} root must be an object")
    return payload


def page_map(rows: object, label: str, errors: list[str]) -> dict[int, dict[str, Any]]:
    if not isinstance(rows, list):
        errors.append(f"{label} must be an array")
        return {}
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            errors.append(f"{label} entries must be objects")
            continue
        page = row.get("page")
        if isinstance(page, bool) or not isinstance(page, int) or page <= 0:
            errors.append(f"{label} contains invalid page {page!r}")
            continue
        if page in result:
            errors.append(f"{label} contains duplicate page {page}")
        result[page] = row
    return result


def validate_svg(path: Path, errors: list[str]) -> None:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        errors.append(f"Cannot parse SVG {path}: {exc}")
        return
    view_box = root.get("viewBox", "").split()
    if view_box and view_box != ["0", "0", "1600", "900"]:
        errors.append(f"{path} viewBox must be 0 0 1600 900")


def validate(
    project: Path,
    *,
    stage: str | None = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    project_path = project / "project.json"
    if not project_path.is_file():
        return [f"Missing required file: {project_path}"], warnings
    try:
        project_config = load_project_config(project)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"Project contract: {exc}"], warnings
    target = stage or project_config["deliverable"]
    if target not in {
        "static_pptx",
        "animated_pptx",
        "narrated_pptx",
        "video",
    }:
        return [f"Unsupported validation stage: {target}"], warnings
    needs_animation = target != "static_pptx"
    needs_narration = target in {"narrated_pptx", "video"}
    required = {
        "project": project_path,
        "manifest": project / "video" / "animation_manifest.json",
    }
    if needs_animation:
        required["layers"] = project / "video" / "svg_layer_plan.json"
    if needs_narration:
        required["director"] = project / "video" / "narration_director.json"
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        return [f"Missing required file: {path}" for path in missing], warnings

    paths = project_paths(project, project_config)
    if not paths["page_script"].is_file():
        errors.append(f"Page script not found: {paths['page_script']}")
    elif not paths["page_script"].read_text(encoding="utf-8").strip():
        errors.append("page-script.md must not be empty")
    if not paths["template_working"].is_file():
        warnings.append(
            f"Working template has not been prepared: {paths['template_working']}"
        )
    template_config = project_config["template"]
    if (
        template_config["mode"] == "provided"
        and not paths["template_source"].is_file()
    ):
        errors.append(
            f"Preserved template source not found: {paths['template_source']}"
        )
    source_config = project_config.get("source")
    if not isinstance(source_config, dict):
        errors.append("project.json source must be an object")
    elif source_config.get("mode") == "document":
        document_value = source_config.get("document")
        review_value = source_config.get("review")
        gate_report_value = source_config.get("gate_report")
        profile = source_config.get("profile", "auto")
        if not isinstance(document_value, str) or not document_value:
            errors.append("project.json source.document is missing")
        elif not isinstance(review_value, str) or not review_value:
            errors.append("project.json source.review is missing")
        elif not isinstance(gate_report_value, str) or not gate_report_value:
            errors.append("project.json source.gate_report is missing")
        elif not isinstance(profile, str):
            errors.append("project.json source.profile is invalid")
        else:
            review_path = Path(review_value)
            if not review_path.is_absolute():
                review_path = project / review_path
            gate_report_path = Path(gate_report_value)
            if not gate_report_path.is_absolute():
                gate_report_path = project / gate_report_path
            if not gate_report_path.is_file():
                errors.append(
                    f"Input gate report not found: {gate_report_path}"
                )
            else:
                recorded_gate = load_object(gate_report_path)
                if recorded_gate.get("passed") is not True:
                    errors.append("Recorded input gate report is not passing")
                if (
                    recorded_gate.get("document_sha256")
                    != source_config.get("document_sha256")
                ):
                    errors.append(
                        "Recorded input gate report SHA-256 differs from project.json"
                    )
            try:
                gate = gate_document(
                    Path(document_value),
                    profile,
                    review_path,
                )
            except (FileNotFoundError, OSError, ValueError) as exc:
                errors.append(f"Cannot revalidate input document: {exc}")
            else:
                if source_config.get("document_sha256") != gate["document_sha256"]:
                    errors.append(
                        "project.json source.document_sha256 differs from input document"
                    )
                for row in gate["findings"]:
                    message = (
                        f"Input gate {row['code']}: {row['message']} "
                        f"Required change: {row['required_change']}"
                    )
                    if row["severity"] == "blocking":
                        errors.append(message)
                    elif row["severity"] == "warning":
                        warnings.append(message)
    else:
        errors.append("project.json source.mode must be document")

    manifest = load_object(required["manifest"])
    slides = page_map(manifest.get("slides"), "manifest.slides", errors)
    expected_pages = list(range(1, len(slides) + 1))
    if sorted(slides) != expected_pages:
        errors.append(f"Manifest pages must be contiguous from 1: {sorted(slides)}")
    if manifest.get("slide_count") not in (None, len(slides)):
        errors.append("manifest.slide_count does not match slides[]")
    director_pages: dict[int, dict[str, Any]] = {}
    if needs_narration:
        policy = manifest.get("narration_policy", {})
        if policy.get("visual_sync") != "independent":
            errors.append(
                "manifest narration_policy.visual_sync must be independent"
            )
        director = load_object(required["director"])
        director_policy = director.get("policy", {})
        if director_policy.get("visual_sync") != "independent":
            errors.append("director.policy.visual_sync must be independent")
        try:
            normalized_director = normalize_director_pages(
                director,
                sorted(slides),
            )
        except ValueError as exc:
            errors.append(f"Director contract: {exc}")
            director_pages = page_map(
                director.get("pages"),
                "director.pages",
                errors,
            )
        else:
            director_pages = {
                row["page"]: row for row in normalized_director
            }
        try:
            voice_profile = load_voice_profile(paths["voice_profile"])
        except (FileNotFoundError, ValueError) as exc:
            errors.append(f"Voice profile: {exc}")
            voice_profile = {}
        manifest_voice = manifest.get("voice")
        expected_voice = {
            "provider": voice_profile.get("provider"),
            "name": voice_profile.get("voice"),
            "style": voice_profile.get("style"),
            "rate": voice_profile.get("rate"),
            "pitch": voice_profile.get("pitch"),
        }
        if isinstance(manifest_voice, dict):
            for field, value in expected_voice.items():
                if manifest_voice.get(field) != value:
                    errors.append(
                        f"Manifest voice {field} differs from voice profile"
                    )
            if manifest_voice.get("profile_sha256") != canonical_hash(
                voice_profile
            ):
                errors.append("Manifest voice profile_sha256 is stale")
        else:
            errors.append("Manifest voice is missing")

    raw_layer_pages: dict[str, Any] = {}
    if needs_animation:
        layer_plan = load_object(required["layers"])
        if layer_plan.get("canvas") != {"width": 1600, "height": 900}:
            errors.append("svg_layer_plan.json canvas must be 1600x900")
        raw_layer_pages = layer_plan.get("pages")
        if not isinstance(raw_layer_pages, dict):
            errors.append("svg_layer_plan.pages must be an object")
            raw_layer_pages = {}

    for page, slide in slides.items():
        source_value = slide.get("source_svg")
        if not isinstance(source_value, str) or not source_value:
            errors.append(f"Page {page} is missing source_svg")
            continue
        source = project / source_value
        if not source.is_file():
            errors.append(f"Page {page} source SVG not found: {source}")
        else:
            validate_svg(source, errors)

        beats = slide.get("beats", [])
        if not isinstance(beats, list):
            errors.append(f"Page {page} beats must be an array")
            continue
        if needs_animation and not beats:
            errors.append(f"Page {page} is missing beats[]")
            continue
        if len(beats) > 6:
            errors.append(f"Page {page} has more than six animation groups")
        beat_ids: list[str] = []
        for beat in beats:
            if not isinstance(beat, dict):
                errors.append(f"Page {page} has non-object beat")
                continue
            beat_id = beat.get("id")
            effect = beat.get("effect")
            if not isinstance(beat_id, str) or not beat_id:
                errors.append(f"Page {page} has beat without id")
                continue
            beat_ids.append(beat_id)
            if effect not in SUPPORTED_EFFECTS:
                errors.append(f"Page {page} {beat_id} has unsupported effect {effect}")
        if len(beat_ids) != len(set(beat_ids)):
            errors.append(f"Page {page} has duplicate beat ids")
        if beat_ids and beat_ids[0] != "title":
            errors.append(f"Page {page} first animated group must be title")

        layer_row = raw_layer_pages.get(f"{page:02d}")
        if needs_animation and not isinstance(layer_row, dict):
            errors.append(f"Page {page} is missing from svg_layer_plan.pages")
        elif needs_animation and isinstance(layer_row, dict):
            layers = layer_row.get("layers")
            layer_names = [
                row.get("name") for row in layers if isinstance(row, dict)
            ] if isinstance(layers, list) else []
            expected_layers = ["base", *beat_ids]
            if layer_names != expected_layers:
                errors.append(
                    f"Page {page} layers {layer_names} != {expected_layers}"
                )
            layer_source = layer_row.get("source")
            if layer_source != source_value:
                errors.append(
                    f"Page {page} layer source {layer_source!r} "
                    f"!= manifest source {source_value!r}"
                )
            layer_effects = {
                row.get("name"): row.get("animation")
                for row in layers
                if isinstance(row, dict)
            } if isinstance(layers, list) else {}
            manifest_effects = {
                beat.get("id"): beat.get("effect")
                for beat in beats
                if isinstance(beat, dict)
            }
            if layer_effects.get("base") != "none":
                errors.append(f"Page {page} base layer must not animate")
            if {
                name: effect
                for name, effect in layer_effects.items()
                if name != "base"
            } != manifest_effects:
                errors.append(f"Page {page} layer effects differ from manifest")
            digest = layer_row.get("expected_source_sha256")
            if source.is_file() and isinstance(digest, str) and digest:
                actual = hashlib.sha256(source.read_bytes()).hexdigest()
                if actual != digest:
                    errors.append(f"Page {page} source SVG SHA-256 changed")
            else:
                warnings.append(f"Page {page} has no source SVG SHA-256")

        if needs_narration:
            narration = director_pages.get(page, {})
            for field in ("role", "direction"):
                if (
                    not isinstance(narration.get(field), str)
                    or not narration[field].strip()
                ):
                    errors.append(f"Director page {page} is missing {field}")
            segments = narration.get("segments")
            if not isinstance(segments, list) or not segments:
                errors.append(f"Director page {page} is missing segments[]")
            else:
                for index, segment in enumerate(segments, 1):
                    if not isinstance(segment, dict):
                        errors.append(
                            f"Director page {page} segment {index} is invalid"
                        )
                        continue
                    if (
                        not isinstance(segment.get("text"), str)
                        or not segment["text"].strip()
                    ):
                        errors.append(
                            f"Director page {page} segment {index} has no text"
                        )
                    if (
                        not isinstance(segment.get("rate"), str)
                        or not RATE_RE.fullmatch(segment["rate"])
                    ):
                        errors.append(
                            f"Director page {page} segment {index} rate is invalid"
                        )
                    pause = segment.get("pause_after_ms")
                    if (
                        isinstance(pause, bool)
                        or not isinstance(pause, int)
                        or not 0 <= pause <= 300
                    ):
                        errors.append(
                            f"Director page {page} segment {index} pause is invalid"
                        )
            merged_narration = slide.get("narration")
            if isinstance(merged_narration, dict) and isinstance(
                segments,
                list,
            ):
                expected_text = "".join(
                    segment.get("text", "")
                    for segment in segments
                    if isinstance(segment, dict)
                )
                if merged_narration.get("text") != expected_text:
                    errors.append(f"Manifest page {page} narration is stale")
                for field in ("chapter", "role", "direction", "segments"):
                    if merged_narration.get(field) != narration.get(field):
                        errors.append(
                            f"Manifest page {page} narration {field} "
                            "differs from director"
                        )

    timing_path = project / "video" / "fast_animation_timing.json"
    if needs_animation and timing_path.is_file():
        timing = load_object(timing_path)
        timing_pages = page_map(timing.get("slides"), "timing.slides", errors)
        if sorted(timing_pages) != sorted(slides):
            errors.append("Timing and manifest page sets differ")
        for page, slide in slides.items():
            row = timing_pages.get(page, {})
            if row.get("audio_start_ms") != 0:
                errors.append(f"Timing page {page} audio must start at 0ms")
            end_ms = row.get("animation_end_ms")
            if not isinstance(end_ms, int) or not 500 <= end_ms <= 1000:
                errors.append(f"Timing page {page} animation must end at 500-1000ms")
            timed_ids = [
                beat.get("id")
                for beat in row.get("beats", [])
                if isinstance(beat, dict)
            ]
            manifest_ids = [
                beat.get("id")
                for beat in slide.get("beats", [])
                if isinstance(beat, dict)
            ]
            if timed_ids != manifest_ids:
                errors.append(f"Timing page {page} beat order differs from manifest")
            timed_effects = [
                beat.get("effect")
                for beat in row.get("beats", [])
                if isinstance(beat, dict)
            ]
            manifest_effects = [
                beat.get("effect")
                for beat in slide.get("beats", [])
                if isinstance(beat, dict)
            ]
            if timed_effects != manifest_effects:
                errors.append(f"Timing page {page} effects differ from manifest")
            for beat in row.get("beats", []):
                if not isinstance(beat, dict):
                    continue
                start = beat.get("start_ms")
                duration = beat.get("duration_ms")
                if (
                    isinstance(start, bool)
                    or not isinstance(start, int)
                    or start < 0
                    or isinstance(duration, bool)
                    or not isinstance(duration, int)
                    or duration <= 0
                    or start + duration > 1000
                ):
                    errors.append(
                        f"Timing page {page} beat {beat.get('id')} "
                        "falls outside the first second"
                    )
    elif needs_animation:
        warnings.append("fast_animation_timing.json has not been generated")

    audio_path = project / "video" / "audio_timeline.json"
    if needs_narration and audio_path.is_file():
        audio = load_object(audio_path)
        safety_ms = audio.get("advance_safety_ms", 150)
        if (
            isinstance(safety_ms, bool)
            or not isinstance(safety_ms, int)
            or safety_ms < 0
        ):
            errors.append("audio_timeline.advance_safety_ms must be non-negative")
            safety_ms = 150
        audio_pages = page_map(audio.get("slides"), "audio_timeline.slides", errors)
        if sorted(audio_pages) != sorted(slides):
            errors.append("Audio timeline and manifest page sets differ")
        for page, row in audio_pages.items():
            duration = row.get("audio_duration_seconds")
            valid_duration = not (
                isinstance(duration, bool)
                or not isinstance(duration, (int, float))
                or duration <= 0
            )
            if not valid_duration:
                errors.append(f"Audio timeline page {page} has invalid duration")
            audio_file = row.get("audio_file")
            if not isinstance(audio_file, str) or not audio_file:
                errors.append(f"Audio timeline page {page} has no audio_file")
                continue
            resolved_audio = audio_path.parent / audio_file
            if not resolved_audio.is_file():
                errors.append(
                    f"Audio timeline page {page} file not found: {resolved_audio}"
                )
            if valid_duration:
                expected_advance = round(float(duration) * 1000) + int(safety_ms)
                if row.get("advance_ms") != expected_advance:
                    errors.append(
                        f"Audio timeline page {page} advance_ms is inconsistent"
                    )
            if resolved_audio.is_file() and valid_duration:
                try:
                    from mutagen.mp3 import MP3
                except ImportError:
                    warnings.append(
                        "mutagen is unavailable; actual MP3 durations were not checked"
                    )
                else:
                    actual_duration = float(MP3(resolved_audio).info.length)
                    if abs(actual_duration - float(duration)) > 0.05:
                        errors.append(
                            f"Audio timeline page {page} duration differs from MP3"
                        )
    elif needs_narration:
        warnings.append("audio_timeline.json is missing; final timing is not verified")

    required_approvals = ["content", "visual"]
    if needs_narration:
        required_approvals.append("narration")
    for approval in required_approvals:
        passed, message = approval_status(project, approval)
        if not passed:
            warnings.append(message)
    return errors, warnings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as validation failures",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project = args.project.expanduser().resolve()
    errors, warnings = validate(project)
    for warning in warnings:
        print(f"WARN {warning}")
    for error in errors:
        print(f"ERROR {error}")
    if errors or (args.strict and warnings):
        return 1
    suffix = " with warnings" if warnings else ""
    print(f"OK  {project}: project contract valid{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

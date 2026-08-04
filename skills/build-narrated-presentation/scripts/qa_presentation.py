#!/usr/bin/env python3
"""Run cached audio, standard, or release QA for a presentation project."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from pptx_production import P_NS, slide_audio_target, timeline_rows
from production_common import (
    canonical_hash,
    chapter_audio_fingerprint,
    chapter_groups,
    current_input_fingerprints,
    file_hash,
    load_object,
    load_project_config,
    load_state,
    load_voice_profile,
    normalize_director_pages,
    pronunciation_audit,
    project_paths,
    require_approvals,
    source_fingerprint,
    visual_fingerprint,
    voice_synthesis_projection,
    write_object,
)
from narration_performance import audit_narration_performance
from validate_project import validate as validate_full_project


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def directory_hashes(directory: Path, patterns: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    if not directory.is_dir():
        return result
    for pattern in patterns:
        for path in sorted(directory.glob(pattern)):
            if path.is_file():
                result[str(path.relative_to(directory))] = file_hash(path)
    return result


def qa_tool_hashes(*names: str) -> dict[str, str]:
    script_dir = Path(__file__).resolve().parent
    return {
        name: file_hash(script_dir / name)
        for name in names
        if (script_dir / name).is_file()
    }


def qa_dependency_payload(
    project: Path,
    state: dict[str, Any],
    level: str,
) -> dict[str, Any]:
    qa_state = state.get("qa")
    record = qa_state.get(level) if isinstance(qa_state, dict) else None
    report_value = record.get("report") if isinstance(record, dict) else None
    report_path = (
        project / report_value
        if isinstance(report_value, str) and report_value
        else None
    )
    return {
        "record": record,
        "actual_report_sha256": (
            file_hash(report_path)
            if report_path is not None and report_path.is_file()
            else None
        ),
    }


def cache_fingerprints(
    project: Path,
    level: str,
    state: dict[str, Any],
) -> dict[str, str]:
    paths = project_paths(project)
    config = load_project_config(project)
    if level == "static":
        static_delivery = config["deliverable"] == "static_pptx"
        visual_pptx = (
            paths["static_pptx"] if static_delivery else paths["animated_pptx"]
        )
        artifact_key = "static_pptx" if static_delivery else "animated_pptx"
        manifest = (
            load_object(paths["manifest"])
            if paths["manifest"].is_file()
            else {}
        )
        return {
            "static": canonical_hash(
                {
                    "source": source_fingerprint(project, config),
                    "visual": visual_fingerprint(
                        project,
                        config,
                        manifest,
                        include_timing=not static_delivery,
                    ),
                    "pptx": (
                        file_hash(visual_pptx)
                        if visual_pptx.is_file()
                        else None
                    ),
                    "visual_artifact": state.get("artifacts", {}).get(
                        artifact_key
                    ),
                    "qa_tools": qa_tool_hashes(
                        Path(__file__).name,
                        "validate_project.py",
                        "production_common.py",
                        "page_script_contract.py",
                    ),
                }
            )
        }

    manifest = (
        load_object(paths["manifest"])
        if paths["manifest"].is_file()
        else {}
    )
    narration_manifest = {
        "voice": manifest.get("voice"),
        "narration_policy": manifest.get("narration_policy"),
        "narration_chapters": manifest.get("narration_chapters"),
        "slides": [
            {"page": row.get("page"), "narration": row.get("narration")}
            for row in manifest.get("slides", [])
            if isinstance(row, dict)
        ],
    }
    audio_payload = {
        "director": (
            file_hash(paths["director"])
            if paths["director"].is_file()
            else None
        ),
        "voice_profile": (
            canonical_hash(
                voice_synthesis_projection(
                    load_voice_profile(paths["voice_profile"])
                )
            )
            if paths["voice_profile"].is_file()
            else None
        ),
        "narration_manifest": narration_manifest,
        "timeline": (
            file_hash(paths["audio_timeline"])
            if paths["audio_timeline"].is_file()
            else None
        ),
        "audio": directory_hashes(
            paths["audio_dir"],
            ("*.mp3", "*.sha256", "*.bookmarks.json"),
        ),
        "scripts": directory_hashes(paths["scripts_dir"], ("*.ssml",)),
        "qa_tools": qa_tool_hashes(
            Path(__file__).name,
            "production_common.py",
            "pptx_production.py",
        ),
    }
    fingerprints = {"audio": canonical_hash(audio_payload)}
    if level == "audio":
        return fingerprints
    static_fingerprint = cache_fingerprints(project, "static", state)["static"]
    fingerprints["static"] = static_fingerprint
    standard_payload = {
        "audio": audio_payload,
        "static_qa": {
            "fingerprint": static_fingerprint,
            **qa_dependency_payload(project, state, "static"),
        },
        "source": source_fingerprint(project, config),
        "visual": visual_fingerprint(project, config, manifest),
        "visual_artifacts": {
            key: state.get("artifacts", {}).get(key)
            for key in ("animated_pptx", "narrated_pptx")
        },
        "pptx": (
            file_hash(paths["narrated_pptx"])
            if paths["narrated_pptx"].is_file()
            else None
        ),
        "qa_tools": qa_tool_hashes(
            Path(__file__).name,
            "validate_project.py",
            "page_script_contract.py",
            "pptx_production.py",
            "production_common.py",
        ),
    }
    fingerprints["standard"] = canonical_hash(standard_payload)
    if level == "standard":
        return fingerprints
    release_payload = {
        "standard": standard_payload,
        "inputs": current_input_fingerprints(project),
        "video": file_hash(paths["video"]) if paths["video"].is_file() else None,
        "powerpoint": state.get("powerpoint"),
        "powerpoint_export_report": None,
        "qa_tools": qa_tool_hashes(
            "validate_project.py",
            "page_script_contract.py",
        ),
    }
    powerpoint = state.get("powerpoint")
    exported = (
        powerpoint.get("video_exported")
        if isinstance(powerpoint, dict)
        else None
    )
    report_value = exported.get("report") if isinstance(exported, dict) else None
    if isinstance(report_value, str) and report_value:
        report_path = project / report_value
        release_payload["powerpoint_export_report"] = (
            file_hash(report_path) if report_path.is_file() else None
        )
    fingerprints["release"] = canonical_hash(release_payload)
    return fingerprints


def cache_fingerprint(
    project: Path,
    level: str,
    state: dict[str, Any],
) -> str:
    return cache_fingerprints(project, level, state)[level]


def current_cached_report(
    project: Path,
    level: str,
    state: dict[str, Any],
    fingerprint: str,
) -> dict[str, Any] | None:
    qa_state = state.get("qa")
    cached = qa_state.get(level) if isinstance(qa_state, dict) else None
    if (
        not isinstance(cached, dict)
        or cached.get("status") != "passed"
        or cached.get("fingerprint") != fingerprint
        or not isinstance(cached.get("report"), str)
        or not isinstance(cached.get("report_sha256"), str)
    ):
        return None
    report_path = project / cached["report"]
    if (
        not report_path.is_file()
        or file_hash(report_path) != cached["report_sha256"]
    ):
        return None
    try:
        report = load_object(report_path)
    except (OSError, ValueError):
        return None
    if (
        report.get("schema_version") != 1
        or report.get("level") != level
        or report.get("status") != "passed"
        or report.get("fingerprint") != fingerprint
        or report.get("errors") != []
        or not isinstance(report.get("evidence"), dict)
    ):
        return None
    return report


def normalize_animation_filter(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    return {
        "fade": "fade",
        "wipe(left)": "wipe_left",
        "wipe(right)": "wipe_right",
        "wipe(up)": "wipe_up",
        "wipe(down)": "wipe_down",
    }.get(value.strip().lower())


def animation_slide_evidence(
    payload: bytes,
    *,
    page: int,
    beats: list[dict[str, Any]],
    timing_beats: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Verify actual entrance effects, targets, and stable beat shape names."""
    errors: list[str] = []
    root = ET.fromstring(payload)
    shape_rows = [
        {"id": node.get("id"), "name": node.get("name")}
        for node in root.findall(f".//{{{P_NS}}}cNvPr")
    ]
    shape_ids = [row["id"] for row in shape_rows if row["id"]]
    shape_name_values = [row["name"] for row in shape_rows if row["name"]]
    if len(shape_ids) != len(set(shape_ids)):
        errors.append(f"Slide {page} contains duplicate cNvPr shape ids")
    if len(shape_name_values) != len(set(shape_name_values)):
        errors.append(f"Slide {page} contains duplicate cNvPr shape names")
    shape_names = {
        row["id"]: row["name"]
        for row in shape_rows
        if row["id"] and row["name"]
    }
    timing = root.find(f"{{{P_NS}}}timing")
    timing_list = (
        timing.find(f"{{{P_NS}}}tnLst") if timing is not None else None
    )
    if timing is None or timing_list is None or len(timing_list) == 0:
        errors.append(f"Slide {page} has no non-empty p:timing/p:tnLst tree")

    raw_effects = (
        timing_list.findall(f".//{{{P_NS}}}animEffect")
        if timing_list is not None
        else []
    )
    all_effects = root.findall(f".//{{{P_NS}}}animEffect")
    inside_effect_ids = {id(effect) for effect in raw_effects}
    if any(id(effect) not in inside_effect_ids for effect in all_effects):
        errors.append(
            f"Slide {page} contains animEffect nodes outside p:timing/p:tnLst"
        )
    if any(
        isinstance(condition.get("evt"), str)
        and "click" in condition.get("evt", "").lower()
        for condition in root.findall(f".//{{{P_NS}}}cond")
    ):
        errors.append(f"Slide {page} animation timing contains an onClick trigger")
    effects: list[dict[str, Any]] = []
    for index, effect in enumerate(raw_effects, 1):
        transition = effect.get("transition")
        normalized_transition = (
            transition.strip().lower() if isinstance(transition, str) else None
        )
        filter_value = effect.get("filter")
        normalized_effect = normalize_animation_filter(filter_value)
        targets = effect.findall(f".//{{{P_NS}}}spTgt")
        target_ids = [
            target.get("spid") for target in targets if target.get("spid")
        ]
        target_id = target_ids[0] if len(target_ids) == 1 else None
        target_name = shape_names.get(target_id) if target_id else None
        behavior = effect.find(f".//{{{P_NS}}}cBhvr")
        duration_node = (
            behavior.find(f"{{{P_NS}}}cTn")
            if behavior is not None
            else None
        )
        duration_value = (
            duration_node.get("dur") if duration_node is not None else None
        )
        duration_ms = (
            int(duration_value)
            if isinstance(duration_value, str)
            and duration_value.isdigit()
            and 0 < int(duration_value) <= 1000
            else None
        )
        if normalized_transition != "in":
            errors.append(
                f"Slide {page} animation effect {index} is not an entrance effect"
            )
        if normalized_effect is None:
            errors.append(
                f"Slide {page} animation effect {index} has unsupported filter "
                f"{filter_value!r}"
            )
        if len(target_ids) != 1:
            errors.append(
                f"Slide {page} animation effect {index} must target one shape"
            )
        elif target_name is None:
            errors.append(
                f"Slide {page} animation target spid={target_id} does not exist"
            )
        if duration_ms is None:
            errors.append(
                f"Slide {page} animation effect {index} duration must be 1-1000ms"
            )
        effects.append(
            {
                "filter": filter_value,
                "effect": normalized_effect,
                "transition": normalized_transition,
                "target_spid": target_id,
                "target_name": target_name,
                "duration_ms": duration_ms,
            }
        )

    timing_by_id = {
        row.get("id"): row
        for row in timing_beats or []
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    expected: list[dict[str, Any]] = []
    for beat in beats:
        beat_id = beat.get("id") if isinstance(beat, dict) else None
        effect = beat.get("effect") if isinstance(beat, dict) else None
        if isinstance(beat_id, str) and isinstance(effect, str):
            expected.append(
                {
                    "beat_id": beat_id,
                    "shape_name": f"s{page:02d}_{beat_id}",
                    "effect": effect,
                    "duration_ms": (
                        timing_by_id.get(beat_id, {}).get("duration_ms")
                        if timing_beats is not None
                        else None
                    ),
                }
            )
    if len(effects) != len(expected):
        errors.append(
            f"Slide {page} entrance effect count {len(effects)} "
            f"!= manifest beats {len(expected)}"
        )
    actual_names = [row["target_name"] for row in effects]
    if len([name for name in actual_names if name is not None]) != len(
        set(name for name in actual_names if name is not None)
    ):
        errors.append(f"Slide {page} animation beats reuse a target shape")
    for row in expected:
        matches = [
            effect
            for effect in effects
            if effect["target_name"] == row["shape_name"]
        ]
        if len(matches) != 1:
            errors.append(
                f"Slide {page} beat {row['beat_id']} must map once to "
                f"shape {row['shape_name']}"
            )
        elif matches[0]["effect"] != row["effect"]:
            errors.append(
                f"Slide {page} beat {row['beat_id']} effect "
                f"{matches[0]['effect']!r} != {row['effect']!r}"
            )
        elif (
            timing_beats is not None
            and matches[0]["duration_ms"] != row["duration_ms"]
        ):
            errors.append(
                f"Slide {page} beat {row['beat_id']} duration "
                f"{matches[0]['duration_ms']!r} != timing "
                f"{row['duration_ms']!r}"
            )
    return {
        "page": page,
        "expected_beats": expected,
        "effects": effects,
        "matched": not errors,
    }, errors


def static_qa(
    project: Path,
    errors: list[str],
    warnings: list[str],
) -> tuple[str, dict[str, Any]]:
    paths = project_paths(project)
    config = load_project_config(project)
    static_delivery = config["deliverable"] == "static_pptx"
    artifact_key = "static_pptx" if static_delivery else "animated_pptx"
    validation_stage = "static_pptx" if static_delivery else "animated_pptx"
    full_errors, full_warnings = validate_full_project(
        project,
        stage=validation_stage,
    )
    errors.extend(full_errors)
    warnings.extend(full_warnings)
    template = paths["template_working"]
    if not template.is_file():
        errors.append(f"Working template not found: {template}")
    elif not zipfile.is_zipfile(template):
        errors.append(f"Working template is not a valid PPTX package: {template}")

    manifest = load_object(paths["manifest"])
    expected_pages = [
        row.get("page")
        for row in manifest.get("slides", [])
        if isinstance(row, dict)
    ]
    manifest_by_page = {
        row.get("page"): row
        for row in manifest.get("slides", [])
        if isinstance(row, dict)
    }
    timing_beats_by_page: dict[int, list[dict[str, Any]]] = {}
    if not static_delivery:
        if not paths["timing"].is_file():
            errors.append("Animated PPTX requires fast_animation_timing.json")
        else:
            timing_payload = load_object(paths["timing"])
            for row in timing_payload.get("slides", []):
                if (
                    isinstance(row, dict)
                    and isinstance(row.get("page"), int)
                    and not isinstance(row.get("page"), bool)
                    and isinstance(row.get("beats"), list)
                ):
                    timing_beats_by_page[row["page"]] = row["beats"]
    pptx = paths[artifact_key]
    state = load_state(paths["build_state"])
    recorded_static = state.get("artifacts", {}).get(artifact_key)
    current_static = (
        {
            "sha256": file_hash(pptx),
            "source_fingerprint": source_fingerprint(project, config),
            "visual_fingerprint": visual_fingerprint(
                project,
                config,
                manifest,
                include_timing=not static_delivery,
            ),
        }
        if pptx.is_file()
        else None
    )
    if current_static is not None and (
        not isinstance(recorded_static, dict)
        or any(
            recorded_static.get(key) != value
            for key, value in current_static.items()
        )
    ):
        errors.append(
            f"{artifact_key} visual provenance is missing or stale; rerun assembly"
        )
    pptx_report: dict[str, Any] | None = None
    if not pptx.is_file():
        errors.append(f"Static PPTX not found: {pptx}")
    else:
        try:
            with zipfile.ZipFile(pptx) as archive:
                bad_member = archive.testzip()
                if bad_member is not None:
                    errors.append(f"PPTX ZIP member is corrupt: {bad_member}")
                slide_names = {
                    name
                    for name in archive.namelist()
                    if name.startswith("ppt/slides/slide")
                    and name.endswith(".xml")
                    and "/_rels/" not in name
                }
                if len(slide_names) != len(expected_pages):
                    errors.append(
                        f"Static PPTX slide count {len(slide_names)} "
                        f"!= manifest pages {len(expected_pages)}"
                    )
                svg_members = [
                    name
                    for name in archive.namelist()
                    if name.startswith("ppt/media/")
                    and name.lower().endswith(".svg")
                ]
                if len(svg_members) < len(expected_pages):
                    errors.append(
                        "Static PPTX does not contain one embedded SVG per page"
                    )
                external_media: list[str] = []
                for name in archive.namelist():
                    if not name.endswith(".rels"):
                        continue
                    root = ET.fromstring(archive.read(name))
                    for relationship in root:
                        rel_type = relationship.get("Type", "")
                        if (
                            relationship.get("TargetMode") == "External"
                            and rel_type.rsplit("/", 1)[-1]
                            in {"audio", "image", "media"}
                        ):
                            external_media.append(
                                f"{name}:{relationship.get('Target')}"
                            )
                if external_media:
                    errors.append(
                        "Static PPTX contains external media relationships: "
                        + ", ".join(external_media)
                    )
                animation_reports: list[dict[str, Any]] = []
                if not static_delivery:
                    for page in expected_pages:
                        if isinstance(page, bool) or not isinstance(page, int):
                            continue
                        slide_name = f"ppt/slides/slide{page}.xml"
                        if slide_name not in slide_names:
                            errors.append(
                                f"Animated PPTX is missing {slide_name}"
                            )
                            continue
                        slide = manifest_by_page.get(page)
                        beats = (
                            slide.get("beats", [])
                            if isinstance(slide, dict)
                            else []
                        )
                        timing_beats = timing_beats_by_page.get(page)
                        if timing_beats is None:
                            errors.append(
                                f"Animation timing has no page {page} beat plan"
                            )
                        evidence, animation_errors = animation_slide_evidence(
                            archive.read(slide_name),
                            page=page,
                            beats=beats if isinstance(beats, list) else [],
                            timing_beats=timing_beats,
                        )
                        animation_reports.append(evidence)
                        errors.extend(animation_errors)
                    presentation_name = "ppt/presentation.xml"
                    if presentation_name not in archive.namelist():
                        errors.append(
                            "Animated PPTX is missing ppt/presentation.xml"
                        )
                    else:
                        presentation = ET.fromstring(
                            archive.read(presentation_name)
                        )
                        if presentation.get("showAnimation") == "0":
                            errors.append(
                                "Animated PPTX explicitly disables animations"
                            )
                pptx_report = {
                    "file": str(pptx.relative_to(project)),
                    "sha256": file_hash(pptx),
                    "slides": len(slide_names),
                    "embedded_svg": len(svg_members),
                    "animations": animation_reports,
                }
        except (ET.ParseError, zipfile.BadZipFile) as exc:
            errors.append(f"Invalid static PPTX package: {exc}")

    fingerprint = canonical_hash(
        {
            "source": source_fingerprint(project, config),
            "visual": visual_fingerprint(
                project,
                config,
                manifest,
                include_timing=not static_delivery,
            ),
            "template": (
                file_hash(template) if template.is_file() else None
            ),
            "pptx": file_hash(pptx) if pptx.is_file() else None,
            "qa_script": file_hash(Path(__file__)),
        }
    )
    return fingerprint, {
        "project": {
            "errors": full_errors,
            "warnings": full_warnings,
        },
        "template": (
            {
                "file": str(template.relative_to(project)),
                "sha256": file_hash(template),
            }
            if template.is_file()
            else None
        ),
        "pptx": pptx_report,
        "visual_provenance": recorded_static,
    }


def audio_qa(
    project: Path,
    errors: list[str],
    warnings: list[str],
) -> tuple[str, dict[str, Any]]:
    paths = project_paths(project)
    director = load_object(paths["director"])
    performance_audit = audit_narration_performance(director)
    errors.extend(
        f"Narration performance: {message}"
        for message in performance_audit["errors"]
    )
    warnings.extend(
        f"Narration performance: {message}"
        for message in performance_audit["warnings"]
    )
    manifest = load_object(paths["manifest"])
    voice = load_voice_profile(paths["voice_profile"])
    expected_pages = [
        int(row["page"])
        for row in manifest.get("slides", [])
        if isinstance(row, dict)
    ]
    pages = normalize_director_pages(director, expected_pages)
    groups = chapter_groups(pages)
    manifest_voice = manifest.get("voice")
    if (
        not isinstance(manifest_voice, dict)
        or manifest_voice.get("profile_sha256")
        != canonical_hash(voice_synthesis_projection(voice))
    ):
        errors.append(
            "Manifest voice is stale; rerun synthesize or manifest merge"
        )
    slide_by_page = {
        int(slide["page"]): slide
        for slide in manifest.get("slides", [])
        if isinstance(slide, dict)
        and isinstance(slide.get("page"), int)
        and not isinstance(slide.get("page"), bool)
    }
    for page in pages:
        merged = slide_by_page.get(page["page"], {}).get("narration")
        expected = {
            key: page[key]
            for key in (
                "chapter",
                "role",
                "intent",
                "direction",
                "rationale",
                "target_seconds",
                "segments",
            )
        }
        if not isinstance(merged, dict) or any(
            merged.get(key) != value for key, value in expected.items()
        ):
            errors.append(
                f"Manifest page {page['page']} narration is stale"
            )
        elif merged.get("text") != "".join(
            segment["text"] for segment in page["segments"]
        ):
            errors.append(
                f"Manifest page {page['page']} narration text is stale"
            )
    timeline = load_object(paths["audio_timeline"])
    rows = timeline_rows(timeline)
    if [row["page"] for row in rows] != expected_pages:
        errors.append("Audio timeline page set differs from the manifest")
    expected_chapters = {
        page["page"]: page["chapter"] for page in pages
    }
    director_by_page = {page["page"]: page for page in pages}
    for row in rows:
        if row.get("chapter") != expected_chapters.get(row["page"]):
            errors.append(
                f"Audio timeline page {row['page']} chapter is stale"
            )
        target = director_by_page.get(row["page"], {}).get("target_seconds")
        if target is not None and abs(float(row.get("target_seconds", 0)) - target) > 0.001:
            errors.append(
                f"Audio timeline page {row['page']} target_seconds is stale"
            )

    try:
        from mutagen.mp3 import MP3
    except ImportError as exc:
        raise RuntimeError("Missing mutagen; run bootstrap first") from exc

    expected_names = {f"{page:02d}.mp3" for page in expected_pages}
    actual_names = {
        path.name
        for path in paths["audio_dir"].glob("*.mp3")
        if path.stem.isdigit()
    }
    if actual_names != expected_names:
        errors.append(
            f"Audio file set differs: expected={sorted(expected_names)}, "
            f"actual={sorted(actual_names)}"
        )

    page_results: list[dict[str, Any]] = []
    for row in rows:
        page = int(row["page"])
        audio_file = (paths["audio_timeline"].parent / row["audio_file"]).resolve()
        if not audio_file.is_file():
            errors.append(f"Page {page} audio not found: {audio_file}")
            continue
        if audio_file.stat().st_size < 512:
            errors.append(f"Page {page} audio is unexpectedly small")
            continue
        try:
            actual_duration = float(MP3(audio_file).info.length)
        except Exception as exc:
            errors.append(f"Page {page} MP3 cannot be parsed: {exc}")
            continue
        recorded_duration = row.get("audio_duration_seconds")
        if (
            isinstance(recorded_duration, bool)
            or not isinstance(recorded_duration, (int, float))
            or recorded_duration <= 0
        ):
            errors.append(f"Page {page} timeline duration is invalid")
        elif abs(actual_duration - float(recorded_duration)) > 0.05:
            errors.append(f"Page {page} real duration differs from timeline")
        target_seconds = row.get("target_seconds")
        if (
            isinstance(target_seconds, bool)
            or not isinstance(target_seconds, (int, float))
            or target_seconds <= 0
        ):
            errors.append(f"Page {page} target duration is invalid")
        else:
            target_value = float(target_seconds)
            expected_delta = round(actual_duration - target_value, 3)
            expected_ratio = round(expected_delta / target_value, 4)
            expected_status = (
                "review"
                if abs(expected_delta) > max(3.0, target_value * 0.15)
                else "within-range"
            )
            expected_rate_delta = (
                max(-10, min(10, round(expected_ratio * 100)))
                if expected_status == "review"
                else 0
            )
            recorded_delta = row.get("duration_delta_seconds")
            if (
                isinstance(recorded_delta, bool)
                or not isinstance(recorded_delta, (int, float))
                or abs(float(recorded_delta) - expected_delta) > 0.05
            ):
                errors.append(f"Page {page} duration delta is stale")
            recorded_ratio = row.get("duration_delta_ratio")
            if (
                isinstance(recorded_ratio, bool)
                or not isinstance(recorded_ratio, (int, float))
                or abs(float(recorded_ratio) - expected_ratio) > 0.001
            ):
                errors.append(f"Page {page} duration ratio is stale")
            if row.get("timing_status") != expected_status:
                errors.append(f"Page {page} timing status is stale")
            if row.get("suggested_rate_delta_percent") != expected_rate_delta:
                errors.append(f"Page {page} rate correction suggestion is stale")
        expected_advance = (
            round(actual_duration * 1000)
            + int(timeline.get("advance_safety_ms", 150))
        )
        if abs(int(row["advance_ms"]) - expected_advance) > 50:
            errors.append(f"Page {page} advance time differs from real MP3")
        page_results.append(
            {
                "page": page,
                "file": str(audio_file.relative_to(project)),
                "sha256": file_hash(audio_file),
                "duration_seconds": round(actual_duration, 3),
                "target_seconds": row.get("target_seconds"),
                "duration_delta_seconds": row.get("duration_delta_seconds"),
                "timing_status": row.get("timing_status"),
                "suggested_rate_delta_percent": row.get(
                    "suggested_rate_delta_percent"
                ),
            }
        )
    actual_page_hashes = {
        row["page"]: row["sha256"] for row in page_results
    }

    chapter_results: list[dict[str, Any]] = []
    for group in groups:
        page_numbers = [page["page"] for page in group["pages"]]
        expected_digest, expected_ssml = chapter_audio_fingerprint(group, voice)
        digest_path = paths["audio_dir"] / f"{group['id']}.sha256"
        ssml_path = paths["scripts_dir"] / f"{group['id']}.ssml"
        recorded_digest = (
            digest_path.read_text(encoding="utf-8").strip()
            if digest_path.is_file()
            else None
        )
        if recorded_digest != expected_digest:
            errors.append(f"Chapter {group['id']} audio digest is stale")
        if (
            not ssml_path.is_file()
            or ssml_path.read_text(encoding="utf-8") != expected_ssml
        ):
            errors.append(f"Chapter {group['id']} SSML is stale or missing")
        metadata_path = paths["audio_dir"] / f"{group['id']}.bookmarks.json"
        if not metadata_path.is_file():
            errors.append(f"Chapter {group['id']} has no bookmark metadata")
        else:
            metadata = load_object(metadata_path)
            if metadata.get("chapter") != group["id"]:
                errors.append(
                    f"Chapter {group['id']} bookmark metadata has stale id"
                )
            if metadata.get("chapter_sha256") != expected_digest:
                errors.append(
                    f"Chapter {group['id']} bookmark digest is stale"
                )
            recorded_pages = [
                row.get("page")
                for row in metadata.get("pages", [])
                if isinstance(row, dict)
                and isinstance(row.get("page"), int)
                and not isinstance(row.get("page"), bool)
            ]
            if recorded_pages != page_numbers:
                errors.append(
                    f"Chapter {group['id']} bookmark pages differ: {recorded_pages}"
                )
            for metadata_page in metadata.get("pages", []):
                if not isinstance(metadata_page, dict):
                    continue
                page = metadata_page.get("page")
                if (
                    not isinstance(page, int)
                    or metadata_page.get("mp3") != f"{page:02d}.mp3"
                ):
                    errors.append(
                        f"Chapter {group['id']} page {page} MP3 name is stale"
                    )
                if actual_page_hashes.get(page) != metadata_page.get(
                    "mp3_sha256"
                ):
                    errors.append(
                        f"Chapter {group['id']} page {page} MP3 hash is stale"
                    )
        chapter_results.append(
            {
                "id": group["id"],
                "pages": page_numbers,
                "bookmark_metadata": (
                    str(metadata_path.relative_to(project))
                    if metadata_path.is_file()
                    else None
                ),
                "input_fingerprint": expected_digest,
            }
        )

    pronunciation_review = pronunciation_audit(
        pages,
        voice["pronunciations"],
    )
    applicable_terms = [
        row["term"] for row in pronunciation_review["configured"]
    ]
    if applicable_terms:
        warnings.append(
            "Pronunciation rules were rendered but human audition remains "
            f"required for: {', '.join(applicable_terms)}"
        )
    uncovered_terms = [
        row["term"] for row in pronunciation_review["uncovered"]
    ]
    if uncovered_terms:
        warnings.append(
            "Technical pronunciation candidates have no explicit rule: "
            + ", ".join(uncovered_terms)
        )
    warnings.append(
        "Automatic audio QA does not perform human pronunciation audition"
    )
    timing_review_pages = [
        row["page"]
        for row in rows
        if row.get("timing_status") == "review"
    ]
    if timing_review_pages:
        warnings.append(
            "Audio duration differs materially from target on pages "
            + ",".join(str(page) for page in timing_review_pages)
            + "; review the suggested rate deltas before chapter rebuild"
        )

    fingerprint = canonical_hash(
        {
            "director": pages,
            "voice": voice,
            "timeline": timeline,
            "audio": {row["file"]: row["sha256"] for row in page_results},
            "qa_script": file_hash(Path(__file__)),
        }
    )
    return fingerprint, {
        "pages": page_results,
        "chapters": chapter_results,
        "performance_audit": performance_audit,
        "timing_review_pages": timing_review_pages,
        "pronunciation_terms": applicable_terms,
        "pronunciation_review": pronunciation_review,
        "uncovered_pronunciation_candidates": uncovered_terms,
        "human_pronunciation": "not-confirmed",
    }


def transition_advance(payload: bytes) -> int | None:
    try:
        from lxml import etree
    except ImportError as exc:
        raise RuntimeError("Missing lxml; run bootstrap first") from exc
    root = etree.fromstring(payload)
    transition = root.find(f"{{{P_NS}}}transition")
    if transition is None:
        return None
    value = transition.get("advTm")
    return int(value) if value and value.isdigit() else None


def standard_qa(
    project: Path,
    errors: list[str],
    warnings: list[str],
    *,
    cached_audio_report: dict[str, Any] | None = None,
    cached_static_report: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    if cached_audio_report is None:
        audio_fingerprint, audio_report = audio_qa(project, errors, warnings)
    else:
        audio_fingerprint = str(cached_audio_report["fingerprint"])
        audio_report = cached_audio_report["evidence"]
        for warning in cached_audio_report.get("warnings", []):
            if isinstance(warning, str) and warning not in warnings:
                warnings.append(warning)
    if cached_static_report is None:
        static_fingerprint = None
        static_report = None
        errors.append(
            "Current animated baseline has no current static QA PASS; "
            "run qa --level static before standard QA"
        )
    else:
        static_fingerprint = str(cached_static_report["fingerprint"])
        static_report = cached_static_report["evidence"]
        for warning in cached_static_report.get("warnings", []):
            if isinstance(warning, str) and warning not in warnings:
                warnings.append(warning)
    paths = project_paths(project)
    full_errors, full_warnings = validate_full_project(
        project,
        stage="animation",
    )
    errors.extend(f"Full project: {message}" for message in full_errors)
    warnings.extend(f"Full project: {message}" for message in full_warnings)
    pptx = paths["narrated_pptx"]
    state = load_state(paths["build_state"])
    recorded_narrated = state.get("artifacts", {}).get("narrated_pptx")
    config = load_project_config(project)
    manifest = load_object(paths["manifest"])
    expected_source = source_fingerprint(project, config)
    expected_visual = visual_fingerprint(project, config, manifest)
    if not isinstance(recorded_narrated, dict):
        errors.append("Narrated PPTX has no visual/audio provenance record")
    else:
        recorded_visual = recorded_narrated.get("visual_baseline")
        if (
            not isinstance(recorded_visual, dict)
            or recorded_visual.get("source_fingerprint") != expected_source
            or recorded_visual.get("visual_fingerprint") != expected_visual
        ):
            errors.append("Narrated PPTX visual provenance is stale")
        if paths["audio_timeline"].is_file() and recorded_narrated.get(
            "audio_timeline_sha256"
        ) != file_hash(paths["audio_timeline"]):
            errors.append("Narrated PPTX audio timeline provenance is stale")
        if pptx.is_file() and recorded_narrated.get("sha256") != file_hash(pptx):
            errors.append("Narrated PPTX artifact SHA-256 is stale")
    if not pptx.is_file():
        errors.append(f"Narrated PPTX not found: {pptx}")
        return canonical_hash({"audio": audio_fingerprint, "pptx": None}), {
            "audio": audio_report,
            "full_project": {
                "errors": full_errors,
                "warnings": full_warnings,
            },
            "pptx": None,
        }
    timeline = load_object(paths["audio_timeline"])
    rows = timeline_rows(timeline)
    pptx_rows: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(pptx) as archive:
            bad_member = archive.testzip()
            if bad_member is not None:
                errors.append(f"PPTX ZIP member is corrupt: {bad_member}")
            slide_names = {
                name
                for name in archive.namelist()
                if name.startswith("ppt/slides/slide")
                and name.endswith(".xml")
                and "/_rels/" not in name
            }
            if len(slide_names) != len(rows):
                errors.append(
                    f"PPTX slide count {len(slide_names)} != audio pages {len(rows)}"
                )
            media_targets: set[str] = set()
            for row in rows:
                page = int(row["page"])
                try:
                    target = slide_audio_target(archive, page)
                except ValueError as exc:
                    errors.append(str(exc))
                    continue
                if target in media_targets:
                    errors.append(f"PPTX media target is shared: {target}")
                media_targets.add(target)
                source_audio = (
                    paths["audio_timeline"].parent / row["audio_file"]
                ).resolve()
                try:
                    embedded = archive.read(target)
                except KeyError:
                    errors.append(f"Embedded audio is missing: {target}")
                    continue
                if source_audio.is_file() and embedded != source_audio.read_bytes():
                    errors.append(
                        f"Slide {page} embedded audio differs from timeline file"
                    )
                slide_name = f"ppt/slides/slide{page}.xml"
                slide_xml = archive.read(slide_name)
                advance = transition_advance(slide_xml)
                if advance != row["advance_ms"]:
                    errors.append(
                        f"Slide {page} PPTX advance {advance} != "
                        f"timeline {row['advance_ms']}"
                    )
                if b"playFrom" not in slide_xml:
                    errors.append(
                        f"Slide {page} has no automatic media playFrom command"
                    )
                pptx_rows.append(
                    {
                        "page": page,
                        "media_target": target,
                        "advance_ms": advance,
                    }
                )
            presentation_xml = archive.read("ppt/presentation.xml")
            for attribute in (b'useTimings="1"', b'showNarration="1"', b'showAnimation="1"'):
                if attribute not in presentation_xml:
                    errors.append(
                        "ppt/presentation.xml is missing "
                        + attribute.decode("ascii")
                    )
    except zipfile.BadZipFile as exc:
        errors.append(f"Invalid PPTX ZIP: {exc}")

    fingerprint = canonical_hash(
        {
            "audio": audio_fingerprint,
            "static": static_fingerprint,
            "pptx": file_hash(pptx),
            "qa_script": file_hash(Path(__file__)),
        }
    )
    return fingerprint, {
        "audio": audio_report,
        "static": static_report,
        "full_project": {
            "errors": full_errors,
            "warnings": full_warnings,
        },
        "pptx": {
            "file": str(pptx.relative_to(project)),
            "sha256": file_hash(pptx),
            "slides": pptx_rows,
        },
    }


def probe_video(video: Path) -> dict[str, Any]:
    report: dict[str, Any] = {
        "file": str(video),
        "sha256": file_hash(video),
        "bytes": video.stat().st_size,
    }
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        report["ffprobe"] = "unavailable"
        return report
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(video),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        report["ffprobe"] = "failed"
        report["ffprobe_error"] = result.stderr.strip()
        return report
    report["ffprobe"] = "passed"
    payload = json.loads(result.stdout)
    duration = payload.get("format", {}).get("duration")
    if duration is not None:
        report["duration_seconds"] = float(duration)
    return report


def release_qa(
    project: Path,
    state: dict[str, Any],
    errors: list[str],
    warnings: list[str],
    *,
    cached_standard_report: dict[str, Any] | None = None,
    cached_audio_report: dict[str, Any] | None = None,
    cached_static_report: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    if cached_standard_report is None:
        standard_fingerprint, standard_report = standard_qa(
            project,
            errors,
            warnings,
            cached_audio_report=cached_audio_report,
            cached_static_report=cached_static_report,
        )
    else:
        standard_fingerprint = str(cached_standard_report["fingerprint"])
        standard_report = cached_standard_report["evidence"]
        for warning in cached_standard_report.get("warnings", []):
            if isinstance(warning, str) and warning not in warnings:
                warnings.append(warning)
    full_errors: list[str] = []
    full_warnings: list[str] = []
    paths = project_paths(project)
    video = paths["video"]
    video_report: dict[str, Any] | None = None
    if not video.is_file() or video.stat().st_size <= 0:
        errors.append(f"Exported video not found or empty: {video}")
    else:
        video_report = probe_video(video)
        if video_report.get("ffprobe") != "passed":
            errors.append(
                "ffprobe did not successfully inspect the exported MP4"
            )
        if not isinstance(video_report.get("duration_seconds"), (int, float)):
            errors.append("ffprobe did not return a valid MP4 duration")
        timeline = load_object(paths["audio_timeline"])
        duration = video_report.get("duration_seconds")
        estimated = timeline.get("estimated_deck_seconds")
        if isinstance(duration, (int, float)) and isinstance(
            estimated,
            (int, float),
        ):
            tolerance = max(2.0, float(estimated) * 0.05)
            if abs(float(duration) - float(estimated)) > tolerance:
                errors.append(
                    f"MP4 duration {duration:.3f}s differs from estimated "
                    f"{estimated:.3f}s"
                )

    powerpoint = state.get("powerpoint", {})
    opened = powerpoint.get("opened") if isinstance(powerpoint, dict) else None
    exported = (
        powerpoint.get("video_exported")
        if isinstance(powerpoint, dict)
        else None
    )
    watched = (
        powerpoint.get("human_watch")
        if isinstance(powerpoint, dict)
        else None
    )
    pptx_sha = (
        file_hash(paths["narrated_pptx"])
        if paths["narrated_pptx"].is_file()
        else None
    )
    video_sha = file_hash(video) if video.is_file() else None
    if not isinstance(opened, dict) or opened.get("pptx_sha256") != pptx_sha:
        errors.append("Current PPTX has no matching PowerPoint-open evidence")
    if not isinstance(exported, dict) or exported.get("video_sha256") != video_sha:
        errors.append("Current MP4 has no matching PowerPoint-export evidence")
    elif exported.get("pptx_sha256") != pptx_sha:
        errors.append("PowerPoint export evidence refers to another PPTX")
    else:
        report_value = exported.get("report")
        report_path = (
            project / report_value
            if isinstance(report_value, str) and report_value
            else None
        )
        if report_path is None or not report_path.is_file():
            errors.append("PowerPoint export report is missing")
        elif exported.get("report_sha256") != file_hash(report_path):
            errors.append("PowerPoint export report SHA-256 is stale")
    if not isinstance(watched, dict) or watched.get("video_sha256") != video_sha:
        errors.append(
            "Current MP4 has no human full-watch confirmation; rerun release "
            "QA with --human-confirmed only after actually watching it"
        )

    inputs = current_input_fingerprints(project)
    fingerprint = canonical_hash(
        {
            "standard": standard_fingerprint,
            "inputs": inputs,
            "video": video_sha,
            "powerpoint": powerpoint,
            "qa_script": file_hash(Path(__file__)),
        }
    )
    return fingerprint, {
        "standard": standard_report,
        "full_project": {
            "errors": full_errors,
            "warnings": full_warnings,
        },
        "video": video_report,
        "powerpoint": powerpoint,
        "inputs": inputs,
    }


def qa_command(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    config = load_project_config(project)
    deliverable = config["deliverable"]
    if args.level == "audio" and deliverable not in {
        "narration_audio",
        "narrated_pptx",
        "video",
    }:
        raise RuntimeError(
            "qa=audio requires narration_audio, narrated_pptx, or video"
        )
    if args.level == "static" and deliverable not in {
        "static_pptx",
        "animated_pptx",
        "narrated_pptx",
        "video",
    }:
        raise RuntimeError(
            "qa=static requires a static, animated, narrated PPTX, or video project"
        )
    if args.level == "standard" and deliverable not in {
        "narrated_pptx",
        "video",
    }:
        raise RuntimeError("qa=standard requires narrated_pptx or video")
    if args.level == "release" and deliverable != "video":
        raise RuntimeError("qa=release requires deliverable=video")
    approval_requirements = {
        "static": ("content", "visual"),
        "audio": ("content", "narration"),
        "standard": ("content", "visual", "narration"),
        "release": ("content", "visual", "narration"),
    }
    require_approvals(project, approval_requirements[args.level])
    paths = project_paths(project)
    state = load_state(paths["build_state"])
    if args.human_confirmed and args.level != "release":
        raise ValueError("--human-confirmed is only valid with --level release")
    if args.confirmed_by and not args.human_confirmed:
        raise ValueError("--confirmed-by requires --human-confirmed")
    if args.human_confirmed:
        video = paths["video"]
        if not video.is_file():
            raise FileNotFoundError(video)
        state["powerpoint"]["human_watch"] = {
            "status": "passed",
            "video_sha256": file_hash(video),
            "confirmed_at": now_iso(),
            "confirmed_by": args.confirmed_by or "user",
            "evidence": "explicit-full-watch-confirmation",
        }
        write_object(paths["build_state"], state)

    fingerprints = cache_fingerprints(project, args.level, state)
    fingerprint = fingerprints[args.level]
    cached_report = current_cached_report(
        project,
        args.level,
        state,
        fingerprint,
    )
    if not args.force and cached_report is not None:
        print(f"SKIP qa={args.level}: inputs and tools unchanged")
        return 0

    errors: list[str] = []
    warnings: list[str] = []
    if args.level == "static":
        _, report = static_qa(project, errors, warnings)
    elif args.level == "audio":
        _, report = audio_qa(project, errors, warnings)
    elif args.level == "standard":
        reusable_audio = current_cached_report(
            project,
            "audio",
            state,
            fingerprints["audio"],
        )
        reusable_static = current_cached_report(
            project,
            "static",
            state,
            fingerprints["static"],
        )
        _, report = standard_qa(
            project,
            errors,
            warnings,
            cached_audio_report=reusable_audio,
            cached_static_report=reusable_static,
        )
    else:
        reusable_standard = current_cached_report(
            project,
            "standard",
            state,
            fingerprints["standard"],
        )
        reusable_audio = (
            None
            if reusable_standard is not None
            else current_cached_report(
                project,
                "audio",
                state,
                fingerprints["audio"],
            )
        )
        reusable_static = (
            None
            if reusable_standard is not None
            else current_cached_report(
                project,
                "static",
                state,
                fingerprints["static"],
            )
        )
        _, report = release_qa(
            project,
            state,
            errors,
            warnings,
            cached_standard_report=reusable_standard,
            cached_audio_report=reusable_audio,
            cached_static_report=reusable_static,
        )

    for warning in warnings:
        print(f"WARN {warning}")
    for error in errors:
        print(f"ERROR {error}")
    qa_report = {
        "schema_version": 1,
        "level": args.level,
        "status": "failed" if errors else "passed",
        "fingerprint": fingerprint,
        "checked_at": now_iso(),
        "errors": errors,
        "warnings": warnings,
        "evidence": report,
    }
    report_path = project / "video" / f"qa_{args.level}.json"
    write_object(report_path, qa_report)
    state = load_state(paths["build_state"])
    state["qa"][args.level] = {
        "status": qa_report["status"],
        "fingerprint": fingerprint,
        "checked_at": qa_report["checked_at"],
        "report": str(report_path.relative_to(project)),
        "report_sha256": file_hash(report_path),
    }
    if not errors and args.level == "release":
        state["inputs"] = report["inputs"]
    write_object(paths["build_state"], state)
    if errors:
        return 1
    print(f"OK  qa={args.level}: {report_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument(
        "--level",
        choices=("static", "audio", "standard", "release"),
        required=True,
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--human-confirmed",
        action="store_true",
        help="Assert that a person watched the current MP4 in full",
    )
    parser.add_argument("--confirmed-by")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    return qa_command(build_parser().parse_args(argv))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        FileNotFoundError,
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)

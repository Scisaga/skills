#!/usr/bin/env python3
"""Run cached browser, audio, or synchronized playback QA."""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from browser_render import browser_page, open_deck
from build_audio_timeline import timeline_rows
from html_production import NARRATED_APPROVALS, STATIC_APPROVALS, require_current_html
from narration_performance import audit_narration_performance
from narration_pitch import narration_pitch_audit
from production_common import (
    HTML_DELIVERABLES,
    NARRATION_DELIVERABLES,
    canonical_hash,
    chapter_audio_fingerprint,
    chapter_groups,
    file_hash,
    load_object,
    load_project_config,
    load_state,
    load_voice_profile,
    normalize_director_pages,
    pronunciation_audit,
    project_lock,
    project_paths,
    require_approvals,
    synthesis_identity_errors,
    voice_synthesis_projection,
    write_object,
)
from validate_project import validate


APPROVALS = {
    "static": STATIC_APPROVALS,
    "audio": ("content", "narration"),
    "standard": NARRATED_APPROVALS,
}


def directory_hashes(directory: Path, patterns: tuple[str, ...]) -> dict[str, str]:
    return {
        path.name: file_hash(path)
        for pattern in patterns
        for path in sorted(directory.glob(pattern))
        if path.is_file()
    }


def qa_tool_hashes(*names: str) -> dict[str, str]:
    return {name: file_hash(Path(__file__).with_name(name)) for name in names}


def audio_fingerprint(project: Path) -> str:
    paths = project_paths(project)
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
        "scripts": directory_hashes(paths["scripts_dir"], ("*.ssml", "*.qwen-*.json")),
        "qa_tools": qa_tool_hashes(
            Path(__file__).name,
            "production_common.py",
            "build_audio_timeline.py",
        ),
    }
    return canonical_hash(audio_payload)


def narration_pitch_qa(
    pages: list[dict[str, Any]],
    voice: dict[str, Any],
    manifest: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    """Return the audio-QA pitch evidence and append blocking findings."""
    pitch_audit = narration_pitch_audit(pages, voice)
    for row in pitch_audit["out_of_range"]:
        errors.append(
            "Combined narration pitch is out of range on page "
            f"{row['page']} segment {row['segment']}: "
            f"{row['global_pitch']} + {row['local_pitch']} = "
            f"{row['final_pitch']}"
        )
    if manifest.get("narration_pitch") != pitch_audit:
        errors.append("Manifest narration_pitch evidence is stale")
    return pitch_audit


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
    pitch_audit = narration_pitch_qa(pages, voice, manifest, errors)
    pitch_is_valid = pitch_audit["status"] == "pass"
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
    execution_identities: dict[str, dict[str, Any]] = {}
    for group in groups:
        page_numbers = [page["page"] for page in group["pages"]]
        metadata_path = paths["audio_dir"] / f"{group['id']}.bookmarks.json"
        metadata = load_object(metadata_path) if metadata_path.is_file() else {}
        synthesis = metadata.get("synthesis")
        errors.extend(
            f"Chapter {group['id']}: {message}"
            for message in synthesis_identity_errors(voice, synthesis)
        )
        identity = synthesis if isinstance(synthesis, dict) else {"provider": "azure-speech", "voice": voice["voice"]}
        execution_identities[canonical_hash(identity)] = identity
        if isinstance(synthesis, dict) and synthesis.get("provider") == "qwen3-tts-openai":
            evidence = metadata.get("service_evidence")
            required_names = {f"{group['id']}.qwen-{kind}.json" for kind in ("plan", "job", "timeline", "manifest")}
            if not isinstance(evidence, dict) or not required_names.issubset(evidence):
                errors.append(f"Chapter {group['id']} Qwen service evidence is missing")
            else:
                for name, checksum in evidence.items():
                    path = paths["scripts_dir"] / name
                    if path.name != name or not path.is_file() or file_hash(path) != checksum:
                        errors.append(f"Chapter {group['id']} Qwen service evidence is stale: {name}")
        expected_digest: str | None = None
        expected_ssml: str | None = None
        if pitch_is_valid:
            expected_digest, expected_ssml = chapter_audio_fingerprint(
                group,
                voice,
                synthesis,
            )
        digest_path = paths["audio_dir"] / f"{group['id']}.sha256"
        ssml_path = paths["scripts_dir"] / f"{group['id']}.ssml"
        recorded_digest = (
            digest_path.read_text(encoding="utf-8").strip()
            if digest_path.is_file()
            else None
        )
        if pitch_is_valid and recorded_digest != expected_digest:
            errors.append(f"Chapter {group['id']} audio digest is stale")
        if pitch_is_valid and (
            not ssml_path.is_file()
            or ssml_path.read_text(encoding="utf-8") != expected_ssml
        ):
            errors.append(f"Chapter {group['id']} SSML is stale or missing")
        if not metadata_path.is_file():
            errors.append(f"Chapter {group['id']} has no bookmark metadata")
        else:
            metadata = load_object(metadata_path)
            if metadata.get("chapter") != group["id"]:
                errors.append(
                    f"Chapter {group['id']} bookmark metadata has stale id"
                )
            if (
                pitch_is_valid
                and metadata.get("chapter_sha256") != expected_digest
            ):
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
                "pitch_status": pitch_audit["status"],
                "synthesis": synthesis,
                "fallback_reason": metadata.get("fallback_reason"),
            }
        )

    if len(execution_identities) != 1:
        errors.append("Audio mixes different TTS providers, voices, or service/model identities; rebuild all chapters")
    actual_identity = next(iter(execution_identities.values()), {})

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
        "narration_pitch": pitch_audit,
        "voice_identity": {
            "status": "consistent" if len(execution_identities) == 1 else "mixed",
            "preference": voice["provider"],
            "provider": actual_identity.get("provider"),
            "voice": actual_identity.get("voice"),
            "execution": actual_identity,
            "style": voice["style"],
            "global_rate": voice["rate"],
            "global_pitch": voice["pitch"],
        },
        "timing_review_pages": timing_review_pages,
        "pronunciation_terms": applicable_terms,
        "pronunciation_review": pronunciation_review,
        "uncovered_pronunciation_candidates": uncovered_terms,
        "human_pronunciation": "not-confirmed",
    }


def current_cached_report(project: Path, level: str, state: dict, fingerprint: str) -> dict | None:
    record = state["qa"].get(level)
    if not isinstance(record, dict) or record.get("status") != "passed" or record.get("fingerprint") != fingerprint:
        return None
    path = project / "video" / f"qa_{level}.json"
    if (
        record.get("report") != str(path.relative_to(project))
        or not path.is_file()
        or file_hash(path) != record.get("report_sha256")
    ):
        return None
    try:
        report = load_object(path)
    except (OSError, ValueError):
        return None
    if (
        report.get("schema_version") != 1 or report.get("level") != level
        or report.get("status") != "passed" or report.get("fingerprint") != fingerprint
        or report.get("errors") != [] or not isinstance(report.get("evidence"), dict)
    ):
        return None
    return report


def cache_fingerprint(project: Path, level: str, state: dict) -> str:
    if level == "audio":
        return audio_fingerprint(project)
    _, record = require_current_html(project, state)
    static = canonical_hash({
        "html": record,
        "tools": qa_tool_hashes(Path(__file__).name, "browser_render.py", "validate_project.py"),
    })
    if level == "static":
        return static
    return canonical_hash({
        "html": record,
        "static_fingerprint": static,
        "audio_fingerprint": audio_fingerprint(project),
        "qa": [state["qa"].get(key) for key in ("static", "audio")],
    })


def require_qa(project: Path, level: str, state: dict | None = None) -> dict:
    require_approvals(project, APPROVALS[level])
    state = state if state is not None else load_state(project_paths(project)["build_state"])
    if level == "standard":
        require_qa(project, "static", state)
        require_qa(project, "audio", state)
    report = current_cached_report(project, level, state, cache_fingerprint(project, level, state))
    if report is None:
        raise RuntimeError(f"缺少当前 qa --level {level} PASS，请先运行该验收")
    return report


def static_qa(project: Path, errors: list[str], warnings: list[str]) -> tuple[str, dict]:
    directory, record = require_current_html(project)
    timeline = record["timeline"]
    stage = "visual" if timeline["mode"] == "static_html" else "animation"
    invalid, notices = validate(project, stage=stage)
    errors.extend(invalid)
    warnings.extend(notices)
    evidence = []
    browser_errors = []
    with browser_page() as page:
        page.on("pageerror", lambda error: browser_errors.append(str(error)))
        open_deck(page, directory / "index.html")
        if page.evaluate("window.slides.timeline") != timeline:
            errors.append("网页内的时间轴和构建状态不一致")
        for index, row in enumerate(timeline["slides"]):
            page.evaluate("i => window.slides.showFinal(i)", index)
            locator = page.locator(f'.page[data-page="{row["page"]}"]')
            bounds = locator.locator(".canvas").bounding_box()
            if not bounds or bounds["width"] != 1600 or bounds["height"] != 900:
                errors.append(f"第 {row['page']} 页渲染画布尺寸异常")
            screenshot = page.screenshot()
            evidence.append({"page": row["page"], "render_sha256": hashlib.sha256(screenshot).hexdigest()})
            for beat in row["beats"]:
                target = locator.locator("[data-beat]")
                passed = target.evaluate_all("""(elements, entry) => {
                    const el = elements.find(node => node.dataset.beat === entry.beat.id);
                    if (!el) return false;
                    const at = entry.row.start_ms + entry.beat.start_ms;
                    const duration = entry.beat.duration_ms;
                    window.slides.renderAt(at);
                    if (getComputedStyle(el).visibility !== "hidden") return false;
                    window.slides.renderAt(at + duration / 2);
                    const middle = getComputedStyle(el);
                    const active = entry.beat.effect === "fade"
                        ? Number(middle.opacity) > 0 && Number(middle.opacity) < 1
                        : middle.clipPath !== "none";
                    window.slides.showFinal(entry.index);
                    const final = getComputedStyle(el);
                    return active && final.visibility === "visible" && Number(final.opacity) === 1 && final.clipPath === "none";
                }""", {"row": row, "beat": beat, "index": index})
                if not passed:
                    errors.append(f"第 {row['page']} 页 {beat['id']} 的浏览器动画未正确执行")
    errors.extend(browser_errors)
    return ("failed" if errors else "passed"), {
        "pages": evidence,
        "fonts": record["fonts"],
        "font_substitutions": record["font_substitutions"],
    }


def standard_qa(project: Path, errors: list[str], warnings: list[str]) -> tuple[str, dict]:
    require_qa(project, "static")
    require_qa(project, "audio")
    directory, record = require_current_html(project)
    timeline = record["timeline"]
    with browser_page() as page:
        open_deck(page, directory / "index.html")
        page.wait_for_function("document.querySelector('#narration').readyState >= 1")
        duration = page.evaluate("document.querySelector('#narration').duration")
        if abs(duration * 1000 - timeline["total_ms"]) > 34:
            errors.append(f"网页音轨时长 {duration}s 与时间轴不一致")
        for index, row in enumerate(timeline["slides"]):
            actual = page.evaluate("""ms => {
              window.slides.renderAt(ms);
              return document.querySelector(".page:not([hidden])")?.dataset.page;
            }""", row["start_ms"])
            if actual != str(index + 1):
                errors.append(f"旁白时间点未进入第 {index + 1} 页")
    return ("failed" if errors else "passed"), {
        "pages": len(timeline["slides"]),
        "duration_ms": timeline["total_ms"],
        "browser_audio_seconds": duration,
        "track_sha256": record["files"]["narration.mp3"],
    }


def qa_command(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    config = load_project_config(project)
    mode = config["deliverable"]
    allowed = {
        "static": HTML_DELIVERABLES,
        "audio": NARRATION_DELIVERABLES,
        "standard": {"narrated_html"},
    }
    level = args.level
    if mode not in allowed[level]:
        raise ValueError(f"{mode} 不支持 qa --level {level}")
    require_approvals(project, APPROVALS[level])
    if level == "standard":
        require_qa(project, "static")
        require_qa(project, "audio")
    paths = project_paths(project, config)
    state = load_state(paths["build_state"])
    fingerprint = cache_fingerprint(project, level, state)
    if not args.force and current_cached_report(project, level, state, fingerprint):
        print(f"SKIP qa={level}: inputs and tools unchanged")
        return 0

    errors: list[str] = []
    warnings: list[str] = []
    if level == "audio":
        invalid, notices = validate(project, stage="audio")
        errors.extend(invalid)
        warnings.extend(notices)
    _, evidence = {"static": static_qa, "audio": audio_qa, "standard": standard_qa}[level](
        project, errors, warnings,
    )
    for warning in warnings:
        print(f"WARN {warning}")
    for error in errors:
        print(f"ERROR {error}")
    with project_lock(project):
        state = load_state(paths["build_state"])
        if cache_fingerprint(project, level, state) != fingerprint:
            raise RuntimeError("验收期间输入已变化，请重试")
        report = {
            "schema_version": 1,
            "level": level,
            "status": "failed" if errors else "passed",
            "fingerprint": fingerprint,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "errors": errors,
            "warnings": warnings,
            "evidence": evidence,
        }
        path = project / "video" / f"qa_{level}.json"
        write_object(path, report)
        state["qa"][level] = {
            "status": report["status"],
            "fingerprint": fingerprint,
            "checked_at": report["checked_at"],
            "report": str(path.relative_to(project)),
            "report_sha256": file_hash(path),
        }
        write_object(paths["build_state"], state)
    if errors:
        return 1
    print(f"OK  qa={level}: {path}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--level", choices=("static", "audio", "standard"), required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        return qa_command(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

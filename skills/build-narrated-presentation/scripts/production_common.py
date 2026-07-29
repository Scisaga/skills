#!/usr/bin/env python3
"""Shared contracts for incremental narrated-presentation production."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape, quoteattr


RATE_RE = re.compile(r"^[+-]\d+%$")
PITCH_RE = re.compile(r"^[+-]\d+(?:\.\d+)?st$")
STATE_SCHEMA_VERSION = 1
PROJECT_SCHEMA_VERSION = 2
DELIVERABLES = {
    "static_pptx",
    "animated_pptx",
    "narrated_pptx",
    "video",
}
APPROVAL_STAGES = {"content", "visual", "narration"}


def load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} root must be an object")
    return payload


def write_object(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(rendered)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def canonical_hash(payload: Any) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_path(project: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return project / path


def load_project_config(project: Path) -> dict[str, Any]:
    path = project / "project.json"
    config = load_object(path)
    version = config.get("schema_version")
    if version != PROJECT_SCHEMA_VERSION:
        raise ValueError(
            "Unsupported project.json schema_version "
            f"{version!r}; expected {PROJECT_SCHEMA_VERSION}. "
            "This skill supports only the current schema."
        )
    deliverable = config.get("deliverable")
    if deliverable not in DELIVERABLES:
        raise ValueError(
            "project.json deliverable must be one of "
            + ", ".join(sorted(DELIVERABLES))
        )
    if config.get("canvas") != {"width": 1600, "height": 900}:
        raise ValueError("project.json canvas must be 1600x900")
    for key in ("source", "content", "template", "visual", "paths", "outputs"):
        if not isinstance(config.get(key), dict):
            raise ValueError(f"project.json {key} must be an object")

    content = config["content"]
    if not isinstance(content.get("page_script"), str) or not content[
        "page_script"
    ]:
        raise ValueError("project.json content.page_script is required")

    template = config["template"]
    if template.get("mode") not in {"provided", "generated"}:
        raise ValueError(
            "project.json template.mode must be provided or generated"
        )
    source = template.get("source")
    if template["mode"] == "provided" and (
        not isinstance(source, str) or not source
    ):
        raise ValueError(
            "project.json template.source is required for provided mode"
        )
    if template["mode"] == "generated" and source is not None:
        raise ValueError(
            "project.json template.source must be null for generated mode"
        )
    if not isinstance(template.get("working"), str) or not template["working"]:
        raise ValueError("project.json template.working is required")
    safe_area = template.get("safe_area")
    if not isinstance(safe_area, dict):
        raise ValueError("project.json template.safe_area must be an object")
    expected_safe_fields = {"x", "y", "width", "height"}
    if set(safe_area) != expected_safe_fields:
        raise ValueError(
            "project.json template.safe_area must contain x, y, width, height"
        )
    values = [safe_area[field] for field in ("x", "y", "width", "height")]
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in values
    ):
        raise ValueError(
            "project.json template.safe_area values must be integers"
        )
    x, y, width, height = values
    if (
        x < 0
        or y < 0
        or width <= 0
        or height <= 0
        or x + width > 1600
        or y + height > 900
    ):
        raise ValueError(
            "project.json template.safe_area must fit inside 1600x900"
        )

    outputs = config["outputs"]
    for key in (
        "static_pptx",
        "animated_pptx",
        "narrated_pptx",
        "video",
    ):
        if not isinstance(outputs.get(key), str) or not outputs[key]:
            raise ValueError(f"project.json outputs.{key} is required")
    paths = config["paths"]
    for key in ("voice_profile", "build_state"):
        if not isinstance(paths.get(key), str) or not paths[key]:
            raise ValueError(f"project.json paths.{key} is required")
    visual = config["visual"]
    if visual.get("style_preset") not in {
        "project-default",
        "technical-infographic",
    }:
        raise ValueError("project.json visual.style_preset is invalid")
    if visual.get("theme") not in {"light", "dark"}:
        raise ValueError("project.json visual.theme is invalid")
    if visual.get("density") != "presentation":
        raise ValueError(
            "project.json visual.density must be presentation"
        )
    return config


def project_paths(
    project: Path,
    config: dict[str, Any] | None = None,
) -> dict[str, Path]:
    config = config or load_project_config(project)
    paths = config.get("paths")
    assert isinstance(paths, dict)
    outputs = config.get("outputs")
    assert isinstance(outputs, dict)
    content = config["content"]
    template = config["template"]
    return {
        "project": project / "project.json",
        "page_script": resolve_path(project, content["page_script"]),
        "template_source": (
            resolve_path(project, template["source"])
            if isinstance(template.get("source"), str)
            else project / "inputs" / "template-source.pptx"
        ),
        "template_working": resolve_path(project, template["working"]),
        "director": project / "video" / "narration_director.json",
        "manifest": project / "video" / "animation_manifest.json",
        "timing": project / "video" / "fast_animation_timing.json",
        "audio_timeline": project / "video" / "audio_timeline.json",
        "audio_dir": project / "video" / "audio",
        "scripts_dir": project / "video" / "scripts",
        "voice_profile": resolve_path(
            project,
            paths["voice_profile"],
        ),
        "build_state": resolve_path(
            project,
            paths["build_state"],
        ),
        "static_pptx": resolve_path(
            project,
            outputs["static_pptx"],
        ),
        "animated_pptx": resolve_path(
            project,
            outputs["animated_pptx"],
        ),
        "narrated_pptx": resolve_path(
            project,
            outputs["narrated_pptx"],
        ),
        "video": resolve_path(
            project,
            outputs["video"],
        ),
    }


def deliverable_pptx(project: Path) -> Path:
    config = load_project_config(project)
    paths = project_paths(project, config)
    deliverable = config["deliverable"]
    if deliverable == "static_pptx":
        return paths["static_pptx"]
    if deliverable == "animated_pptx":
        return paths["animated_pptx"]
    return paths["narrated_pptx"]


def normalize_voice_profile(profile: dict[str, Any]) -> dict[str, Any]:
    provider = profile.get("provider", "azure-speech")
    voice = profile.get("voice")
    style = profile.get("style")
    rate = profile.get("rate", "+0%")
    pitch = profile.get("pitch", "+0st")
    page_break_ms = profile.get("page_break_ms", 120)
    if provider != "azure-speech":
        raise ValueError(f"Unsupported voice provider: {provider!r}")
    if not isinstance(voice, str) or not voice.strip():
        raise ValueError("voice_profile.voice must be a non-empty string")
    if style is not None and (not isinstance(style, str) or not style.strip()):
        raise ValueError("voice_profile.style must be null or a non-empty string")
    if not isinstance(rate, str) or not RATE_RE.fullmatch(rate):
        raise ValueError("voice_profile.rate must use the +5% form")
    if not isinstance(pitch, str) or not PITCH_RE.fullmatch(pitch):
        raise ValueError("voice_profile.pitch must use the +0st form")
    if (
        isinstance(page_break_ms, bool)
        or not isinstance(page_break_ms, int)
        or not 0 <= page_break_ms <= 1000
    ):
        raise ValueError("voice_profile.page_break_ms must be 0-1000")

    pronunciations = profile.get("pronunciations", {})
    if not isinstance(pronunciations, dict):
        raise ValueError("voice_profile.pronunciations must be an object")
    normalized_pronunciations: dict[str, dict[str, str]] = {}
    for term, raw_rule in pronunciations.items():
        if not isinstance(term, str) or not term:
            raise ValueError("Pronunciation terms must be non-empty strings")
        if isinstance(raw_rule, str):
            rule = {"alias": raw_rule}
        elif isinstance(raw_rule, dict):
            rule = dict(raw_rule)
        else:
            raise ValueError(f"Pronunciation rule for {term!r} is invalid")
        alias = rule.get("alias")
        phoneme = rule.get("phoneme", rule.get("ph"))
        alphabet = rule.get("alphabet", "ipa")
        if alias is not None:
            if not isinstance(alias, str) or not alias:
                raise ValueError(f"Pronunciation alias for {term!r} is invalid")
            normalized_pronunciations[term] = {"alias": alias}
        elif phoneme is not None:
            if (
                not isinstance(phoneme, str)
                or not phoneme
                or not isinstance(alphabet, str)
                or not alphabet
            ):
                raise ValueError(f"Pronunciation phoneme for {term!r} is invalid")
            normalized_pronunciations[term] = {
                "alphabet": alphabet,
                "phoneme": phoneme,
            }
        else:
            raise ValueError(
                f"Pronunciation rule for {term!r} needs alias or phoneme"
            )

    audition = profile.get("audition", {})
    if not isinstance(audition, dict):
        raise ValueError("voice_profile.audition must be an object")
    audition_text = audition.get("text", "")
    if not isinstance(audition_text, str):
        raise ValueError("voice_profile.audition.text must be a string")

    return {
        "schema_version": 1,
        "provider": provider,
        "voice": voice,
        "style": style,
        "rate": rate,
        "pitch": pitch,
        "page_break_ms": page_break_ms,
        "pronunciations": normalized_pronunciations,
        "audition": {"text": audition_text},
    }


def load_voice_profile(profile_path: Path) -> dict[str, Any]:
    if not profile_path.is_file():
        raise FileNotFoundError(profile_path)
    return normalize_voice_profile(load_object(profile_path))


def validate_segments(page: int, segments: object) -> list[dict[str, Any]]:
    if not isinstance(segments, list) or not segments:
        raise ValueError(f"Page {page} is missing narration segments")
    normalized: list[dict[str, Any]] = []
    for index, raw_segment in enumerate(segments, 1):
        if not isinstance(raw_segment, dict):
            raise ValueError(f"Page {page} segment {index} must be an object")
        text = raw_segment.get("text")
        rate = raw_segment.get("rate", "+5%")
        pause = raw_segment.get("pause_after_ms", 80)
        pitch = raw_segment.get("pitch")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Page {page} segment {index} is missing text")
        if not isinstance(rate, str) or not RATE_RE.fullmatch(rate):
            raise ValueError(f"Page {page} segment {index} has invalid rate")
        if (
            isinstance(pause, bool)
            or not isinstance(pause, int)
            or not 0 <= pause <= 300
        ):
            raise ValueError(
                f"Page {page} segment {index} pause must be 0-300ms"
            )
        if pitch is not None and (
            not isinstance(pitch, str) or not PITCH_RE.fullmatch(pitch)
        ):
            raise ValueError(f"Page {page} segment {index} has invalid pitch")
        row = {
            "text": text.strip(),
            "rate": rate,
            "pause_after_ms": pause,
        }
        if pitch is not None:
            row["pitch"] = pitch
        normalized.append(row)
    return normalized


def normalize_director_pages(
    director: dict[str, Any],
    expected_pages: list[int] | None = None,
) -> list[dict[str, Any]]:
    policy = director.get("policy")
    if not isinstance(policy, dict) or policy.get("visual_sync") != "independent":
        raise ValueError("director.policy.visual_sync must be independent")
    raw_pages = director.get("pages")
    if not isinstance(raw_pages, list) or not raw_pages:
        raise ValueError("director.pages must be a non-empty array")
    pages: list[dict[str, Any]] = []
    seen: set[int] = set()
    for raw_page in raw_pages:
        if not isinstance(raw_page, dict):
            raise ValueError("director.pages[] must be objects")
        page = raw_page.get("page")
        if isinstance(page, bool) or not isinstance(page, int) or page <= 0:
            raise ValueError(f"Invalid director page: {page!r}")
        if page in seen:
            raise ValueError(f"Duplicate director page: {page}")
        seen.add(page)
        role = raw_page.get("role")
        direction = raw_page.get("direction")
        chapter = raw_page.get("chapter", f"page-{page:02d}")
        if not isinstance(role, str) or not role.strip():
            raise ValueError(f"Page {page} is missing role")
        if not isinstance(direction, str) or not direction.strip():
            raise ValueError(f"Page {page} is missing direction")
        if not isinstance(chapter, str) or not re.fullmatch(
            r"[a-z0-9][a-z0-9-]{0,62}",
            chapter,
        ):
            raise ValueError(
                f"Page {page} chapter must use lowercase letters, digits and hyphens"
            )
        pages.append(
            {
                "page": page,
                "chapter": chapter,
                "role": role.strip(),
                "direction": direction.strip(),
                "segments": validate_segments(page, raw_page.get("segments")),
            }
        )
    actual = [row["page"] for row in pages]
    expected = expected_pages or list(range(1, len(pages) + 1))
    if actual != expected:
        raise ValueError(f"Director pages must be {expected}; got {actual}")

    chapter_positions: dict[str, list[int]] = {}
    for row in pages:
        chapter_positions.setdefault(row["chapter"], []).append(row["page"])
    for chapter, positions in chapter_positions.items():
        if positions != list(range(positions[0], positions[-1] + 1)):
            raise ValueError(
                f"Chapter {chapter!r} pages must be contiguous; got {positions}"
            )
    return pages


def chapter_groups(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for page in pages:
        if not groups or groups[-1]["id"] != page["chapter"]:
            groups.append({"id": page["chapter"], "pages": [page]})
        else:
            groups[-1]["pages"].append(page)
    return groups


def pronunciation_fragment(
    text: str,
    pronunciations: dict[str, dict[str, str]],
) -> str:
    if not pronunciations:
        return escape(text)
    terms = sorted(pronunciations, key=len, reverse=True)
    matcher = re.compile("|".join(re.escape(term) for term in terms))
    parts: list[str] = []
    cursor = 0
    for match in matcher.finditer(text):
        parts.append(escape(text[cursor : match.start()]))
        term = match.group(0)
        rule = pronunciations[term]
        if "alias" in rule:
            parts.append(
                f"<sub alias={quoteattr(rule['alias'])}>{escape(term)}</sub>"
            )
        else:
            parts.append(
                f"<phoneme alphabet={quoteattr(rule['alphabet'])} "
                f"ph={quoteattr(rule['phoneme'])}>{escape(term)}</phoneme>"
            )
        cursor = match.end()
    parts.append(escape(text[cursor:]))
    return "".join(parts)


def combine_rate(global_rate: str, local_rate: str) -> str:
    total = int(global_rate[:-1]) + int(local_rate[:-1])
    if total <= -100:
        raise ValueError("Combined narration rate must be greater than -100%")
    return f"{total:+d}%"


def combine_pitch(global_pitch: str, local_pitch: str | None) -> str:
    global_value = float(global_pitch[:-2])
    local_value = float(local_pitch[:-2]) if local_pitch is not None else 0.0
    total = global_value + local_value
    rendered = f"{total:+.6f}".rstrip("0").rstrip(".")
    return rendered + "st"


def render_chapter_ssml(
    chapter: dict[str, Any],
    voice_profile: dict[str, Any],
) -> str:
    paragraphs: list[str] = []
    pronunciations = voice_profile["pronunciations"]
    pitch_default = voice_profile["pitch"]
    for page in chapter["pages"]:
        bookmark = f"page-{page['page']:02d}"
        segments: list[str] = []
        for segment in page["segments"]:
            content = pronunciation_fragment(segment["text"], pronunciations)
            rate = combine_rate(voice_profile["rate"], segment["rate"])
            pitch = combine_pitch(pitch_default, segment.get("pitch"))
            segments.append(
                f"<prosody rate={quoteattr(rate)} "
                f"pitch={quoteattr(pitch)}>{content}</prosody>"
            )
            if segment["pause_after_ms"]:
                segments.append(
                    f"<break time={quoteattr(str(segment['pause_after_ms']) + 'ms')}/>"
                )
        if voice_profile["page_break_ms"]:
            segments.append(
                f"<break time={quoteattr(str(voice_profile['page_break_ms']) + 'ms')}/>"
            )
        paragraphs.append(
            f"<bookmark mark={quoteattr(bookmark)}/>"
            f"<p>{''.join(segments)}</p>"
        )
    body = "".join(paragraphs)
    style = voice_profile["style"]
    if style:
        body = (
            f"<mstts:express-as style={quoteattr(style)} "
            f"styledegree=\"1.0\">{body}</mstts:express-as>"
        )
    locale_match = re.match(r"^([a-z]{2,3}-[A-Z]{2})-", voice_profile["voice"])
    locale = locale_match.group(1) if locale_match else "zh-CN"
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f"<speak version=\"1.0\" xml:lang={quoteattr(locale)} "
        'xmlns="http://www.w3.org/2001/10/synthesis" '
        'xmlns:mstts="https://www.w3.org/2001/mstts">\n'
        f"  <voice name={quoteattr(voice_profile['voice'])}>{body}</voice>\n"
        "</speak>\n"
    )


def load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "inputs": {},
            "artifacts": {},
            "approvals": {},
            "qa": {},
            "powerpoint": {
                "opened": None,
                "video_exported": None,
                "human_watch": None,
            },
        }
    state = load_object(path)
    state.setdefault("schema_version", STATE_SCHEMA_VERSION)
    state.setdefault("inputs", {})
    state.setdefault("artifacts", {})
    state.setdefault("approvals", {})
    state.setdefault("qa", {})
    state.setdefault(
        "powerpoint",
        {"opened": None, "video_exported": None, "human_watch": None},
    )
    return state


def source_fingerprint(project: Path, project_config: dict[str, Any]) -> str:
    source = project_config.get("source")
    assert isinstance(source, dict)
    document_value = source.get("document")
    document_hash = None
    if isinstance(document_value, str) and document_value:
        document = resolve_path(project, document_value)
        if document.is_file():
            document_hash = file_hash(document)
    page_script = resolve_path(
        project,
        project_config["content"]["page_script"],
    )
    return canonical_hash(
        {
            "source": source,
            "document_sha256": document_hash,
            "page_script_sha256": (
                file_hash(page_script) if page_script.is_file() else None
            ),
        }
    )


def visual_fingerprint(
    project: Path,
    project_config: dict[str, Any],
    manifest: dict[str, Any],
    *,
    include_timing: bool = True,
) -> str:
    visual_manifest = {
        key: value
        for key, value in manifest.items()
        if key not in {"voice", "narration_policy"}
    }
    normalized_slides: list[dict[str, Any]] = []
    for slide in visual_manifest.get("slides", []):
        if not isinstance(slide, dict):
            continue
        normalized_slides.append(
            {
                key: value
                for key, value in slide.items()
                if key != "narration"
            }
        )
    visual_manifest["slides"] = normalized_slides
    svg_hashes: dict[str, str] = {}
    for slide in normalized_slides:
        source = slide.get("source_svg")
        if isinstance(source, str):
            path = resolve_path(project, source)
            if path.is_file():
                svg_hashes[source] = file_hash(path)
    timing = project / "video" / "fast_animation_timing.json"
    template = project_config["template"]
    template_working = resolve_path(project, template["working"])
    return canonical_hash(
        {
            "preset": project_config["visual"],
            "template": {
                "mode": template["mode"],
                "working_sha256": (
                    file_hash(template_working)
                    if template_working.is_file()
                    else None
                ),
                "safe_area": template["safe_area"],
            },
            "manifest": visual_manifest,
            "svg": svg_hashes,
            "timing": (
                file_hash(timing)
                if include_timing and timing.is_file()
                else None
            ),
        }
    )


def current_input_fingerprints(project: Path) -> dict[str, str]:
    paths = project_paths(project)
    project_config = load_project_config(project)
    director = load_object(paths["director"])
    manifest = load_object(paths["manifest"])
    voice = load_voice_profile(paths["voice_profile"])
    pages = normalize_director_pages(director)
    narration_content = [
        {
            "page": page["page"],
            "chapter": page["chapter"],
            "role": page["role"],
            "direction": page["direction"],
            "text": [segment["text"] for segment in page["segments"]],
        }
        for page in pages
    ]
    performance = [
        {
            "page": page["page"],
            "segments": [
                {
                    key: segment.get(key)
                    for key in ("rate", "pitch", "pause_after_ms")
                }
                for segment in page["segments"]
            ],
        }
        for page in pages
    ]
    return {
        "source": source_fingerprint(project, project_config),
        "narration": canonical_hash(narration_content),
        "voice": canonical_hash(
            {
                "profile": voice,
                "local_performance": performance,
            }
        ),
        "visual": visual_fingerprint(project, project_config, manifest),
    }


def parse_page_list(value: str | None) -> list[int]:
    if value is None:
        return []
    pages: set[int] = set()
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start, end = int(start_text), int(end_text)
            if start <= 0 or end < start:
                raise ValueError(f"Invalid page range: {token}")
            pages.update(range(start, end + 1))
        else:
            page = int(token)
            if page <= 0:
                raise ValueError(f"Invalid page: {token}")
            pages.add(page)
    return sorted(pages)


def approval_fingerprint(
    project: Path,
    stage: str,
    *,
    pages: list[int] | None = None,
) -> tuple[str, dict[str, Any]]:
    if stage not in APPROVAL_STAGES:
        raise ValueError(f"Unsupported approval stage: {stage}")
    config = load_project_config(project)
    paths = project_paths(project, config)
    content_payload = {
        "source_and_script": source_fingerprint(project, config),
        "page_script": str(paths["page_script"].relative_to(project)),
    }
    if not paths["page_script"].is_file():
        raise FileNotFoundError(paths["page_script"])
    if stage == "content":
        return canonical_hash(content_payload), content_payload

    if stage == "visual":
        selected_pages = sorted(set(pages or []))
        if not selected_pages:
            raise ValueError(
                "Visual approval requires representative --pages"
            )
        if not paths["template_working"].is_file():
            raise FileNotFoundError(paths["template_working"])
        manifest = load_object(paths["manifest"])
        slide_map = {
            row.get("page"): row
            for row in manifest.get("slides", [])
            if isinstance(row, dict)
        }
        samples: dict[str, str] = {}
        for page in selected_pages:
            slide = slide_map.get(page)
            if not isinstance(slide, dict):
                raise ValueError(
                    f"Visual approval page {page} is absent from the manifest"
                )
            source = slide.get("source_svg")
            if not isinstance(source, str) or not source:
                raise ValueError(
                    f"Visual approval page {page} has no source_svg"
                )
            source_path = resolve_path(project, source)
            if not source_path.is_file():
                raise FileNotFoundError(source_path)
            samples[str(page)] = file_hash(source_path)
        payload = {
            "content": canonical_hash(content_payload),
            "template_sha256": file_hash(paths["template_working"]),
            "safe_area": config["template"]["safe_area"],
            "visual": config["visual"],
            "samples": samples,
        }
        return canonical_hash(payload), payload

    if not paths["director"].is_file():
        raise FileNotFoundError(paths["director"])
    director = load_object(paths["director"])
    voice = load_voice_profile(paths["voice_profile"])
    payload = {
        "content": canonical_hash(content_payload),
        "director_sha256": file_hash(paths["director"]),
        "voice_profile": voice,
    }
    return canonical_hash(payload), payload


def approval_status(
    project: Path,
    stage: str,
    state: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    paths = project_paths(project)
    state = state or load_state(paths["build_state"])
    approvals = state.get("approvals")
    record = approvals.get(stage) if isinstance(approvals, dict) else None
    if not isinstance(record, dict) or record.get("status") != "approved":
        return False, f"{stage} approval is missing"
    pages = record.get("pages")
    selected = (
        [int(page) for page in pages]
        if isinstance(pages, list)
        else None
    )
    try:
        current, _ = approval_fingerprint(
            project,
            stage,
            pages=selected,
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        return False, f"{stage} approval cannot be verified: {exc}"
    if record.get("fingerprint") != current:
        return False, f"{stage} approval is stale"
    return True, f"{stage} approval is current"


def require_approvals(project: Path, stages: tuple[str, ...]) -> None:
    paths = project_paths(project)
    state = load_state(paths["build_state"])
    failures = [
        message
        for stage in stages
        for passed, message in [approval_status(project, stage, state)]
        if not passed
    ]
    if failures:
        raise RuntimeError(
            "Production blocked: "
            + "; ".join(failures)
            + ". Run approve after reviewing the current artifacts."
        )


def record_approval(
    project: Path,
    stage: str,
    *,
    approved_by: str,
    pages: list[int] | None = None,
) -> dict[str, Any]:
    if not approved_by.strip():
        raise ValueError("--approved-by must be non-empty")
    paths = project_paths(project)
    fingerprint, evidence = approval_fingerprint(
        project,
        stage,
        pages=pages,
    )
    state = load_state(paths["build_state"])
    record = {
        "status": "approved",
        "fingerprint": fingerprint,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "approved_by": approved_by.strip(),
        "evidence": evidence,
    }
    if stage == "visual":
        record["pages"] = sorted(set(pages or []))
    state["approvals"][stage] = record
    write_object(paths["build_state"], state)
    return record

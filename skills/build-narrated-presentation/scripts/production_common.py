#!/usr/bin/env python3
"""Shared contracts for incremental narrated-presentation production."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape, quoteattr


RATE_RE = re.compile(r"^[+-]\d+%$")
PITCH_RE = re.compile(r"^[+-]\d+(?:\.\d+)?st$")
STATE_SCHEMA_VERSION = 1


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


def project_paths(project: Path) -> dict[str, Path]:
    config = load_object(project / "project.json")
    paths = config.get("paths")
    if not isinstance(paths, dict):
        paths = {}
    outputs = config.get("outputs")
    if not isinstance(outputs, dict):
        outputs = {}
    return {
        "project": project / "project.json",
        "director": project / "video" / "narration_director.json",
        "manifest": project / "video" / "animation_manifest.json",
        "timing": project / "video" / "fast_animation_timing.json",
        "audio_timeline": project / "video" / "audio_timeline.json",
        "audio_dir": project / "video" / "audio",
        "scripts_dir": project / "video" / "scripts",
        "voice_profile": resolve_path(
            project,
            paths.get("voice_profile", "video/voice_profile.json"),
        ),
        "build_state": resolve_path(
            project,
            paths.get("build_state", "video/build_state.json"),
        ),
        "animated_pptx": resolve_path(
            project,
            outputs.get("animated_pptx", "deliverables/animated.pptx"),
        ),
        "video": resolve_path(
            project,
            outputs.get("video", "deliverables/video.mp4"),
        ),
    }


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


def voice_profile_from_legacy_director(
    director: dict[str, Any],
) -> dict[str, Any] | None:
    voice = director.get("voice")
    if not isinstance(voice, dict):
        return None
    return normalize_voice_profile(
        {
            "provider": voice.get("provider", "azure-speech"),
            "voice": voice.get("name"),
            "style": voice.get("style"),
            # Legacy directors already store the effective rate on every
            # segment. Keep the new global adjustment neutral on migration.
            "rate": "+0%",
            "pitch": voice.get("pitch", "+0st"),
            "pronunciations": {},
            "audition": {"text": ""},
        }
    )


def load_voice_profile(
    profile_path: Path,
    *,
    director: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if profile_path.is_file():
        return normalize_voice_profile(load_object(profile_path))
    if director is not None:
        legacy = voice_profile_from_legacy_director(director)
        if legacy is not None:
            return legacy
    raise FileNotFoundError(profile_path)


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
    state.setdefault("qa", {})
    state.setdefault(
        "powerpoint",
        {"opened": None, "video_exported": None, "human_watch": None},
    )
    return state


def source_fingerprint(project: Path, project_config: dict[str, Any]) -> str:
    source = project_config.get("source")
    if not isinstance(source, dict):
        return canonical_hash({"source": None})
    document_value = source.get("document")
    if isinstance(document_value, str) and document_value:
        document = resolve_path(project, document_value)
        if document.is_file():
            return file_hash(document)
    return canonical_hash(source)


def visual_fingerprint(project: Path, manifest: dict[str, Any]) -> str:
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
    return canonical_hash(
        {
            "manifest": visual_manifest,
            "svg": svg_hashes,
            "timing": file_hash(timing) if timing.is_file() else None,
        }
    )


def current_input_fingerprints(project: Path) -> dict[str, str]:
    paths = project_paths(project)
    project_config = load_object(paths["project"])
    director = load_object(paths["director"])
    manifest = load_object(paths["manifest"])
    voice = load_voice_profile(paths["voice_profile"], director=director)
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
        "visual": visual_fingerprint(project, manifest),
    }

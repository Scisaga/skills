#!/usr/bin/env python3
"""Synthesize chapter-continuous narration and voice auditions."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import wave
from pathlib import Path
from typing import Any, Sequence

from build_manifest import build_manifest, render_review
from production_common import (
    canonical_hash,
    chapter_audio_fingerprint,
    chapter_groups,
    file_hash,
    load_object,
    load_project_config,
    load_state,
    load_voice_profile,
    normalize_director_pages,
    normalize_voice_profile,
    project_paths,
    require_approvals,
    render_chapter_ssml,
    voice_synthesis_projection,
    write_object,
)


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent


def load_environment(project: Path, explicit: Path | None) -> None:
    candidates = [
        explicit,
        Path.cwd() / ".env",
        SKILL_ROOT / ".env",
        SCRIPT_DIR / ".env",
    ]
    env_path = next(
        (path for path in candidates if path is not None and path.is_file()),
        None,
    )
    if env_path is None:
        return
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise RuntimeError(
            f"Found {env_path}, but python-dotenv is unavailable; run bootstrap"
        ) from exc
    load_dotenv(env_path, override=False)


def parse_pages(value: str | None) -> set[int] | None:
    if value is None:
        return None
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
    if not pages:
        raise ValueError("--pages did not contain any pages")
    return pages


def apply_voice_overrides(
    profile_path: Path,
    profile: dict[str, Any],
    *,
    voice: str | None,
    rate: str | None,
    pitch: str | None,
    persist: bool = True,
    announce: bool = True,
) -> dict[str, Any]:
    changed = False
    updated = dict(profile)
    for key, value in (("voice", voice), ("rate", rate), ("pitch", pitch)):
        if value is not None and value != updated.get(key):
            updated[key] = value
            changed = True
    normalized = normalize_voice_profile(updated)
    if changed and persist:
        write_object(profile_path, normalized)
        print(f"OK  updated voice profile: {profile_path}")
    elif changed and announce:
        print(f"PLAN update voice profile: {profile_path}")
    return normalized


def get_speech_sdk() -> Any:
    try:
        import azure.cognitiveservices.speech as speechsdk
    except ImportError as exc:
        raise RuntimeError(
            "Missing azure-cognitiveservices-speech; run bootstrap first"
        ) from exc
    return speechsdk


def speech_config(profile: dict[str, Any]) -> tuple[Any, Any]:
    key = os.getenv("AZURE_SPEECH_KEY", "")
    region = os.getenv("AZURE_SPEECH_REGION", "eastasia")
    if not key:
        raise RuntimeError("AZURE_SPEECH_KEY is required for synthesis")
    speechsdk = get_speech_sdk()
    config = speechsdk.SpeechConfig(subscription=key, region=region)
    return speechsdk, config


def synthesize_chapter_wav(
    ssml: str,
    output_wav: Path,
    profile: dict[str, Any],
) -> dict[str, int]:
    speechsdk, config = speech_config(profile)
    pcm_format = getattr(
        speechsdk.SpeechSynthesisOutputFormat,
        "Riff48Khz16BitMonoPcm",
        speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm,
    )
    config.set_speech_synthesis_output_format(pcm_format)
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    audio_config = speechsdk.audio.AudioOutputConfig(filename=str(output_wav))
    synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=config,
        audio_config=audio_config,
    )
    bookmarks: dict[str, int] = {}

    def on_bookmark(event: Any) -> None:
        bookmarks[str(event.text)] = int(event.audio_offset)

    synthesizer.bookmark_reached.connect(on_bookmark)
    result = synthesizer.speak_ssml_async(ssml).get()
    if result is None:
        raise RuntimeError("Azure Speech returned an empty synthesis result")
    if result.reason == speechsdk.ResultReason.Canceled:
        details = speechsdk.SpeechSynthesisCancellationDetails(result)
        raise RuntimeError(
            "Azure Speech canceled synthesis: "
            f"{details.reason}; {details.error_details}"
        )
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        raise RuntimeError(f"Azure Speech did not complete: {result.reason}")
    if not output_wav.is_file() or output_wav.stat().st_size == 0:
        raise RuntimeError(f"Azure Speech did not create {output_wav}")
    return bookmarks


def encode_mp3(
    pcm: bytes,
    *,
    sample_rate: int,
    channels: int,
) -> bytes:
    try:
        import lameenc
    except ImportError as exc:
        raise RuntimeError("Missing lameenc; run bootstrap first") from exc
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(192)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_channels(channels)
    encoder.set_quality(2)
    return encoder.encode(pcm) + encoder.flush()


def split_chapter(
    chapter: dict[str, Any],
    wav_path: Path,
    bookmark_ticks: dict[str, int],
    audio_dir: Path,
    chapter_digest: str,
) -> dict[str, Any]:
    pages = [int(row["page"]) for row in chapter["pages"]]
    offsets: dict[int, int] = {pages[0]: 0}
    for page in pages[1:]:
        mark = f"page-{page:02d}"
        if mark not in bookmark_ticks:
            raise RuntimeError(
                f"Azure Speech did not return bookmark {mark} for {chapter['id']}"
            )
        offsets[page] = bookmark_ticks[mark]

    with wave.open(str(wav_path), "rb") as source:
        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        sample_rate = source.getframerate()
        frame_count = source.getnframes()
        if sample_width != 2:
            raise RuntimeError(
                f"Expected 16-bit PCM, got sample width {sample_width}"
            )
        raw_pcm = source.readframes(frame_count)

    boundaries: list[int] = []
    for page in pages:
        seconds = offsets[page] / 10_000_000
        boundaries.append(max(0, min(frame_count, round(seconds * sample_rate))))
    boundaries.append(frame_count)
    if any(right <= left for left, right in zip(boundaries, boundaries[1:])):
        raise RuntimeError(
            f"Bookmark offsets for {chapter['id']} are not strictly increasing"
        )

    audio_dir.mkdir(parents=True, exist_ok=True)
    bytes_per_frame = channels * sample_width
    page_rows: list[dict[str, Any]] = []
    for index, page in enumerate(pages):
        start_frame, end_frame = boundaries[index], boundaries[index + 1]
        pcm = raw_pcm[
            start_frame * bytes_per_frame : end_frame * bytes_per_frame
        ]
        mp3 = encode_mp3(
            pcm,
            sample_rate=sample_rate,
            channels=channels,
        )
        output = audio_dir / f"{page:02d}.mp3"
        output.write_bytes(mp3)
        page_rows.append(
            {
                "page": page,
                "bookmark_ticks": offsets[page],
                "start_frame": start_frame,
                "end_frame": end_frame,
                "mp3": output.name,
                "mp3_sha256": file_hash(output),
            }
        )
    return {
        "schema_version": 1,
        "chapter": chapter["id"],
        "chapter_sha256": chapter_digest,
        "sample_rate": sample_rate,
        "channels": channels,
        "sample_width": sample_width,
        "pages": page_rows,
    }


def chapter_cache_is_current(
    chapter: dict[str, Any],
    digest: str,
    ssml: str,
    paths: dict[str, Path],
) -> bool:
    digest_path = paths["audio_dir"] / f"{chapter['id']}.sha256"
    ssml_path = paths["scripts_dir"] / f"{chapter['id']}.ssml"
    metadata_path = paths["audio_dir"] / f"{chapter['id']}.bookmarks.json"
    if (
        not digest_path.is_file()
        or digest_path.read_text(encoding="utf-8").strip() != digest
        or not ssml_path.is_file()
        or ssml_path.read_text(encoding="utf-8") != ssml
        or not metadata_path.is_file()
    ):
        return False
    try:
        metadata = load_object(metadata_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    expected_pages = [page["page"] for page in chapter["pages"]]
    rows = metadata.get("pages")
    if (
        metadata.get("chapter") != chapter["id"]
        or metadata.get("chapter_sha256") != digest
        or not isinstance(rows, list)
        or [row.get("page") for row in rows if isinstance(row, dict)]
        != expected_pages
    ):
        return False
    for row in rows:
        if not isinstance(row, dict) or isinstance(row.get("page"), bool):
            return False
        page = row.get("page")
        audio = paths["audio_dir"] / f"{page:02d}.mp3"
        if (
            row.get("mp3") != audio.name
            or not audio.is_file()
            or row.get("mp3_sha256") != file_hash(audio)
        ):
            return False
    return True


def synthesize_command(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    config = load_project_config(project)
    if config["deliverable"] not in {
        "narration_audio",
        "narrated_pptx",
        "video",
    }:
        raise RuntimeError(
            "Synthesis requires narration_audio, narrated_pptx, or video"
        )
    if any((args.voice, args.rate, args.pitch)):
        raise ValueError(
            "synthesize no longer changes voice settings; use configure-voice, "
            "then approve narration first; audition is recommended"
        )
    paths = project_paths(project)
    director = load_object(paths["director"])
    manifest = load_object(paths["manifest"])
    if config["deliverable"] == "narration_audio":
        pages = normalize_director_pages(director)
        expected_pages = [row["page"] for row in pages]
    else:
        expected_pages = [
            int(row["page"])
            for row in manifest.get("slides", [])
            if isinstance(row, dict)
        ]
        pages = normalize_director_pages(director, expected_pages)
    profile = load_voice_profile(paths["voice_profile"])
    require_approvals(project, ("content", "narration"))
    merged_manifest = build_manifest(
        None if config["deliverable"] == "narration_audio" else manifest,
        director,
        profile,
    )
    if not args.dry_run:
        write_object(paths["manifest"], merged_manifest)
        review_path = project / "video" / "narration_review.md"
        review_path.write_text(
            render_review(merged_manifest),
            encoding="utf-8",
        )
    manifest = merged_manifest
    if not args.dry_run:
        load_environment(project, args.env_file)
    selected = parse_pages(args.pages)
    groups = chapter_groups(pages)
    chapter_contracts: dict[str, tuple[str, str, bool]] = {}
    if selected is not None:
        missing = sorted(selected - set(expected_pages))
        if missing:
            raise ValueError(f"Pages are not in the presentation: {missing}")
        requested_groups = {
            group["id"]
            for group in groups
            if selected.intersection(page["page"] for page in group["pages"])
        }
        stale_groups: set[str] = set()
        for group in groups:
            expected_digest, expected_ssml = chapter_audio_fingerprint(
                group, profile
            )
            current = chapter_cache_is_current(
                group,
                expected_digest,
                expected_ssml,
                paths,
            )
            chapter_contracts[group["id"]] = (
                expected_digest,
                expected_ssml,
                current,
            )
            if not current:
                stale_groups.add(group["id"])
        extra = stale_groups - requested_groups
        if extra:
            print(
                "INFO also rebuilding stale chapters outside --pages: "
                + ",".join(sorted(extra))
            )
        groups = [
            group
            for group in groups
            if group["id"] in requested_groups.union(stale_groups)
        ]
    if not args.dry_run:
        paths["scripts_dir"].mkdir(parents=True, exist_ok=True)
        paths["audio_dir"].mkdir(parents=True, exist_ok=True)
    state = load_state(paths["build_state"])
    generated = 0
    reused = 0
    for chapter in groups:
        if chapter["id"] in chapter_contracts:
            digest, ssml, cache_current = chapter_contracts[chapter["id"]]
        else:
            digest, ssml = chapter_audio_fingerprint(chapter, profile)
            cache_current = chapter_cache_is_current(
                chapter,
                digest,
                ssml,
                paths,
            )
        ssml_path = paths["scripts_dir"] / f"{chapter['id']}.ssml"
        if not args.dry_run:
            ssml_path.write_text(ssml, encoding="utf-8")
        digest_path = paths["audio_dir"] / f"{chapter['id']}.sha256"
        if not args.force and cache_current:
            reused += 1
            print(f"SKIP {chapter['id']}: inputs unchanged")
            continue
        if args.dry_run:
            print(
                f"PLAN {chapter['id']}: pages "
                + ",".join(str(page["page"]) for page in chapter["pages"])
            )
            continue
        wav_path = paths["audio_dir"] / f".{chapter['id']}.wav"
        try:
            bookmarks = synthesize_chapter_wav(
                ssml,
                wav_path,
                profile,
            )
            metadata = split_chapter(
                chapter,
                wav_path,
                bookmarks,
                paths["audio_dir"],
                digest,
            )
        finally:
            if wav_path.exists():
                wav_path.unlink()
        write_object(
            paths["audio_dir"] / f"{chapter['id']}.bookmarks.json",
            metadata,
        )
        digest_path.write_text(digest + "\n", encoding="utf-8")
        generated += 1
        print(
            f"OK  {chapter['id']}: "
            f"{len(chapter['pages'])} page audio files"
        )

    if not args.dry_run:
        audio_files = sorted(paths["audio_dir"].glob("[0-9][0-9].mp3"))
        state["artifacts"]["audio"] = {
            path.name: file_hash(path) for path in audio_files
        }
        state["artifacts"]["audio_voice_sha256"] = canonical_hash(
            voice_synthesis_projection(profile)
        )
        write_object(paths["build_state"], state)
    print(
        f"OK  synthesis: generated={generated}, reused={reused}, "
        f"planned={len(groups) if args.dry_run else 0}"
    )
    return 0


def audition_command(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    config = load_project_config(project)
    if config["deliverable"] not in {
        "narration_audio",
        "narrated_pptx",
        "video",
    }:
        raise RuntimeError(
            "Voice audition requires narration_audio, narrated_pptx, or video"
        )
    paths = project_paths(project)
    base_profile = load_voice_profile(paths["voice_profile"])
    text = args.text or base_profile["audition"]["text"]
    if not text.strip():
        raise ValueError("Audition text is empty")
    voices = [voice.strip() for voice in args.voices.split(",") if voice.strip()]
    if not voices:
        raise ValueError("--voices did not contain any voices")
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else paths["audio_dir"] / "auditions"
    )
    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
    if not args.dry_run:
        load_environment(project, args.env_file)
    for voice in voices:
        profile = normalize_voice_profile(
            {
                **base_profile,
                "voice": voice,
                "rate": args.rate or base_profile["rate"],
                "pitch": args.pitch or base_profile["pitch"],
            }
        )
        chapter = {
            "id": "audition",
            "pages": [
                {
                    "page": 1,
                    "chapter": "audition",
                    "role": "voice audition",
                    "direction": "natural",
                    "segments": [
                        {
                            "text": text.strip(),
                            "rate": "+0%",
                            "pause_after_ms": 0,
                        }
                    ],
                }
            ],
        }
        ssml = render_chapter_ssml(chapter, profile)
        safe_voice = re.sub(r"[^A-Za-z0-9._-]+", "_", voice)
        ssml_path = output_dir / f"{safe_voice}.ssml"
        if args.dry_run:
            print(f"PLAN {voice}: {ssml_path}")
            continue
        ssml_path.write_text(ssml, encoding="utf-8")
        speechsdk, config = speech_config(profile)
        config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Audio48Khz192KBitRateMonoMp3
        )
        output_mp3 = output_dir / f"{safe_voice}.mp3"
        audio_config = speechsdk.audio.AudioOutputConfig(filename=str(output_mp3))
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=config,
            audio_config=audio_config,
        )
        result = synthesizer.speak_ssml_async(ssml).get()
        if result is None or result.reason != (
            speechsdk.ResultReason.SynthesizingAudioCompleted
        ):
            raise RuntimeError(f"Audition synthesis failed for {voice}")
        print(f"OK  {voice}: {output_mp3}")
    return 0


def configure_voice_command(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    config = load_project_config(project)
    if config["deliverable"] not in {
        "narration_audio",
        "narrated_pptx",
        "video",
    }:
        raise RuntimeError("Voice configuration requires a narration deliverable")
    paths = project_paths(project)
    current = load_voice_profile(paths["voice_profile"])
    updated = apply_voice_overrides(
        paths["voice_profile"],
        current,
        voice=args.voice,
        rate=args.rate,
        pitch=args.pitch,
        persist=False,
        announce=args.dry_run,
    )
    pronunciation_file = getattr(args, "pronunciation_file", None)
    replace_pronunciations = bool(
        getattr(args, "replace_pronunciations", False)
    )
    if replace_pronunciations and pronunciation_file is None:
        raise ValueError(
            "--replace-pronunciations requires --pronunciation-file"
        )
    if pronunciation_file is not None:
        glossary_path = pronunciation_file.expanduser().resolve()
        glossary = load_object(glossary_path)
        raw_pronunciations = (
            glossary.get("pronunciations")
            if "pronunciations" in glossary
            else glossary
        )
        if not isinstance(raw_pronunciations, dict):
            raise ValueError(
                "Pronunciation file must be an object or contain a "
                "pronunciations object"
            )
        merged_pronunciations = (
            {} if replace_pronunciations else dict(updated["pronunciations"])
        )
        merged_pronunciations.update(raw_pronunciations)
        updated = normalize_voice_profile(
            {**updated, "pronunciations": merged_pronunciations}
        )
    director = load_object(paths["director"])
    raw_pages = director.get("pages")
    refreshed: dict[str, Any] | None = None
    refreshed_review: str | None = None
    refresh_error: str | None = None
    derived_changed = False
    if isinstance(raw_pages, list) and raw_pages:
        try:
            current_manifest = load_object(paths["manifest"])
            refreshed = build_manifest(
                None
                if config["deliverable"] == "narration_audio"
                else current_manifest,
                director,
                updated,
            )
            refreshed_review = render_review(refreshed)
            review_path = project / "video" / "narration_review.md"
            derived_changed = (
                refreshed != current_manifest
                or not review_path.is_file()
                or review_path.read_text(encoding="utf-8") != refreshed_review
            )
        except (KeyError, OSError, TypeError, ValueError) as exc:
            refresh_error = str(exc)
    changed = updated != current
    if args.dry_run:
        if refreshed is not None and derived_changed:
            print("PLAN refresh narration manifest and review")
    else:
        if changed:
            write_object(paths["voice_profile"], updated)
            print(f"OK  updated voice profile: {paths['voice_profile']}")
        if refreshed is not None and refreshed_review is not None and derived_changed:
            write_object(paths["manifest"], refreshed)
            (project / "video" / "narration_review.md").write_text(
                refreshed_review,
                encoding="utf-8",
            )
    if updated == current:
        print("INFO voice profile unchanged")
    if refresh_error is not None:
        voice_state = (
            "would be updated"
            if args.dry_run and changed
            else "is updated"
            if changed
            else "is unchanged"
        )
        print(
            f"WARN voice configuration {voice_state}, but the derived narration "
            f"review could not be refreshed: {refresh_error}"
        )
    elif not isinstance(raw_pages, list) or not raw_pages:
        print("INFO narration director is empty; there is no review to refresh")
    else:
        print("INFO derived narration manifest and review are current")
    if args.dry_run:
        print("PLAN configure-voice; no files changed")
    elif changed or derived_changed:
        print(
            "OK  configure-voice; approve narration before synthesis; "
            "audition is recommended"
        )
    elif refresh_error is not None:
        print(
            "OK  configure-voice; voice unchanged and derived review remains "
            "unresolved; no approval status was inferred"
        )
    else:
        print(
            "OK  configure-voice; no changes; no new narration approval is "
            "required solely for this no-op"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    synthesize = subparsers.add_parser("synthesize")
    synthesize.add_argument("--project", type=Path, required=True)
    synthesize.add_argument("--pages", help="Comma-separated pages or ranges")
    synthesize.add_argument("--voice")
    synthesize.add_argument("--rate")
    synthesize.add_argument("--pitch")
    synthesize.add_argument("--env-file", type=Path)
    synthesize.add_argument("--force", action="store_true")
    synthesize.add_argument("--dry-run", action="store_true")
    synthesize.set_defaults(func=synthesize_command)

    configure = subparsers.add_parser("configure-voice")
    configure.add_argument("--project", type=Path, required=True)
    configure.add_argument("--voice")
    configure.add_argument("--rate")
    configure.add_argument("--pitch")
    configure.add_argument("--pronunciation-file", type=Path)
    configure.add_argument("--replace-pronunciations", action="store_true")
    configure.add_argument("--dry-run", action="store_true")
    configure.set_defaults(func=configure_voice_command)

    audition = subparsers.add_parser("audition")
    audition.add_argument("--project", type=Path, required=True)
    audition.add_argument("--voices", required=True)
    audition.add_argument("--text")
    audition.add_argument("--rate")
    audition.add_argument("--pitch")
    audition.add_argument("--output-dir", type=Path)
    audition.add_argument("--env-file", type=Path)
    audition.add_argument("--dry-run", action="store_true")
    audition.set_defaults(func=audition_command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)

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
from narration_pitch import require_narration_pitch
from qwen_tts_client import QwenTTSClient, QwenTTSError, load_tts_environment
from production_common import (
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
    normalize_voice_profile,
    project_lock,
    project_paths,
    require_approvals,
    render_chapter_ssml,
    voice_synthesis_projection,
    write_object,
)


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent


def load_environment(project: Path, explicit: Path | None) -> None:
    load_tts_environment(explicit)


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
            "Missing Azure SDK; install with: python -m pip install "
            "azure-cognitiveservices-speech"
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
        raise RuntimeError(
            "Missing lameenc; install with: python -m pip install lameenc"
        ) from exc
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
                f"TTS did not return bookmark {mark} for {chapter['id']}"
            )
        offsets[page] = bookmark_ticks[mark]

    with wave.open(str(wav_path), "rb") as source:
        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        sample_rate = source.getframerate()
        frame_count = source.getnframes()
        if sample_width != 2:
            raise RuntimeError(f"Expected 16-bit PCM, got sample width {sample_width}")
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
        pcm = raw_pcm[start_frame * bytes_per_frame : end_frame * bytes_per_frame]
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
        or [row.get("page") for row in rows if isinstance(row, dict)] != expected_pages
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
    evidence = metadata.get("service_evidence", {})
    if not isinstance(evidence, dict):
        return False
    synthesis = metadata.get("synthesis")
    if isinstance(synthesis, dict) and synthesis.get("provider") == "qwen3-tts-openai":
        required = {
            f"{chapter['id']}.qwen-{kind}.json"
            for kind in ("plan", "job", "timeline", "manifest")
        }
        if not required.issubset(evidence):
            return False
    for name, checksum in evidence.items():
        path = paths["scripts_dir"] / name
        if path.name != name or not path.is_file() or file_hash(path) != checksum:
            return False
    return True


def azure_synthesis(
    profile: dict[str, Any], reason: str | None = None
) -> dict[str, Any]:
    if reason:
        print(
            f"WARN Qwen unavailable; falling back to Azure for ALL chapters: {reason}",
            flush=True,
        )
        try:
            speech_config(profile)
        except RuntimeError as exc:
            raise RuntimeError(
                f"Qwen unavailable: {reason}; Azure fallback unavailable: {exc}"
            ) from exc
    return {"provider": "azure-speech", "voice": profile["voice"]}


def select_synthesis(
    profile: dict[str, Any],
    groups: list[dict[str, Any]],
) -> tuple[QwenTTSClient | None, dict[str, Any], str | None]:
    if profile["provider"] == "azure-speech":
        return None, azure_synthesis(profile), None
    try:
        client = QwenTTSClient()
        synthesis = client.resolve(profile)
        # Check every chapter before generating any audio. Never silently omit controls.
        for group in groups:
            client.compile(render_chapter_ssml(group, profile), profile)
        return client, synthesis, None
    except QwenTTSError as exc:
        if profile["provider"] != "auto":
            raise
        reason = str(exc)
        return None, azure_synthesis(profile, reason), reason


def synthesize_groups(
    groups: list[dict[str, Any]],
    profile: dict[str, Any],
    paths: dict[str, Path],
    args: argparse.Namespace,
    client: QwenTTSClient | None,
    synthesis: dict[str, Any] | None,
    fallback_reason: str | None,
) -> tuple[int, int]:
    selected = parse_pages(args.pages)
    generated, reused = 0, 0
    for chapter in groups:
        digest, ssml = chapter_audio_fingerprint(chapter, profile, synthesis)
        cache_current = chapter_cache_is_current(chapter, digest, ssml, paths)
        requested = selected is None or bool(
            selected.intersection(p["page"] for p in chapter["pages"])
        )
        if cache_current and (not args.force or not requested):
            reused += 1
            print(f"SKIP {chapter['id']}: inputs and service unchanged")
            continue
        if args.dry_run:
            print(
                f"PLAN {chapter['id']}: pages "
                + ",".join(str(p["page"]) for p in chapter["pages"])
            )
            continue
        if not requested:
            print(
                f"INFO also rebuilding stale chapter outside --pages: {chapter['id']}"
            )
        ssml_path = paths["scripts_dir"] / f"{chapter['id']}.ssml"
        ssml_path.write_text(ssml, encoding="utf-8")
        wav_path = paths["audio_dir"] / f".{chapter['id']}.wav"
        try:
            if client is not None:
                bookmarks = client.synthesize(
                    ssml, profile, wav_path, ssml_path.with_suffix("")
                )
                if client.resolve(profile) != synthesis:
                    raise QwenTTSError(
                        "Qwen service/model/reference identity changed during generation"
                    )
            else:
                bookmarks = synthesize_chapter_wav(ssml, wav_path, profile)
            metadata = split_chapter(
                chapter, wav_path, bookmarks, paths["audio_dir"], digest
            )
        finally:
            if wav_path.exists():
                wav_path.unlink()
        metadata["synthesis"] = synthesis
        metadata["fallback_reason"] = fallback_reason
        metadata["boundary_source"] = (
            "qwen-timeline-pcm" if client else "azure-bookmark-event"
        )
        metadata["generation_granularity"] = (
            "natural-sentence-or-short-paragraph" if client else "continuous-chapter"
        )
        if client:
            metadata["service_evidence"] = {
                path.name: file_hash(path)
                for path in paths["scripts_dir"].glob(f"{chapter['id']}.qwen-*.json")
            }
        write_object(paths["audio_dir"] / f"{chapter['id']}.bookmarks.json", metadata)
        (paths["audio_dir"] / f"{chapter['id']}.sha256").write_text(
            digest + "\n", encoding="utf-8"
        )
        generated += 1
        print(
            f"OK  {chapter['id']}: {len(chapter['pages'])} page audio files", flush=True
        )
    return generated, reused


def synthesize_command(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    config = load_project_config(project)
    if config["deliverable"] not in NARRATION_DELIVERABLES:
        raise RuntimeError(
            "Synthesis requires narration_audio or narrated_html"
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
    if selected is not None and selected - set(expected_pages):
        raise ValueError(
            f"Pages are not in the presentation: {sorted(selected - set(expected_pages))}"
        )
    groups = chapter_groups(pages)
    client, synthesis, fallback_reason = None, None, None
    if args.dry_run:
        print(f"PLAN service preference: {profile['provider']}; no network requests")
    else:
        paths["scripts_dir"].mkdir(parents=True, exist_ok=True)
        paths["audio_dir"].mkdir(parents=True, exist_ok=True)
        client, synthesis, fallback_reason = select_synthesis(profile, groups)
        print(
            f"INFO selected TTS: {synthesis['provider']} / {synthesis['voice']}",
            flush=True,
        )
    try:
        generated, reused = synthesize_groups(
            groups,
            profile,
            paths,
            args,
            client,
            synthesis,
            fallback_reason,
        )
    except QwenTTSError as exc:
        if profile["provider"] != "auto" or client is None:
            raise
        fallback_reason = str(exc)
        synthesis = azure_synthesis(profile, fallback_reason)
        # Revisit every chapter with the Azure identity; Qwen audio cannot survive in this run.
        generated, reused = synthesize_groups(
            groups,
            profile,
            paths,
            args,
            None,
            synthesis,
            fallback_reason,
        )
    if not args.dry_run:
        audio_files = sorted(paths["audio_dir"].glob("[0-9][0-9].mp3"))
        with project_lock(project):
            state = load_state(paths["build_state"])
            state["artifacts"]["audio"] = {
                path.name: file_hash(path) for path in audio_files
            }
            state["artifacts"]["audio_voice_sha256"] = canonical_hash(
                voice_synthesis_projection(profile)
            )
            state["artifacts"]["audio_synthesis"] = synthesis
            state["artifacts"]["audio_fallback_reason"] = fallback_reason
            write_object(paths["build_state"], state)
    print(
        f"OK  synthesis: generated={generated}, reused={reused}, "
        f"planned={len(groups) if args.dry_run else 0}"
    )
    return 0


def audition_command(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    config = load_project_config(project)
    if config["deliverable"] not in NARRATION_DELIVERABLES:
        raise RuntimeError(
            "Voice audition requires narration_audio or narrated_html"
        )
    paths = project_paths(project)
    base_profile = load_voice_profile(paths["voice_profile"])
    text = args.text or base_profile["audition"]["text"]
    if not text.strip():
        raise ValueError("Audition text is empty")
    if not args.dry_run:
        load_environment(project, args.env_file)
    provider = getattr(args, "provider", None) or base_profile["provider"]
    base_profile = normalize_voice_profile({**base_profile, "provider": provider})
    default_voice = (
        base_profile["voice"]
        if provider == "azure-speech"
        else base_profile.get("qwen_voice") or os.getenv("QWEN_TTS_VOICE_ID", "")
    )
    voices = [v.strip() for v in (args.voices or default_voice).split(",") if v.strip()]
    if not voices:
        raise ValueError(
            "No audition voices; run list-voices and pass --voices VOICE_ID"
        )
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else paths["audio_dir"] / "auditions"
    )
    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
    for voice in voices:
        profile = normalize_voice_profile(
            {
                **base_profile,
                ("voice" if provider == "azure-speech" else "qwen_voice"): voice,
                "rate": args.rate or base_profile["rate"],
                "pitch": args.pitch or base_profile["pitch"],
            }
        )
        chapter = {
            "id": "audition",
            "pages": [
                {
                    "page": 1,
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
        safe_voice = re.sub(r"[^A-Za-z0-9._-]+", "_", voice).strip(".") or "voice"
        prefix = output_dir / safe_voice
        if args.dry_run:
            print(f"PLAN {provider} / {voice}: {prefix}.mp3; no network requests")
            continue
        prefix.with_name(prefix.name + ".ssml").write_text(ssml, encoding="utf-8")
        client, synthesis, reason = select_synthesis(profile, [chapter])
        wav_path = prefix.with_name(prefix.name + ".wav")
        try:
            try:
                if client is not None:
                    client.synthesize(ssml, profile, wav_path, prefix)
                else:
                    synthesize_chapter_wav(ssml, wav_path, profile)
            except QwenTTSError as exc:
                if provider != "auto" or client is None:
                    raise
                reason = str(exc)
                synthesis = azure_synthesis(profile, reason)
                synthesize_chapter_wav(ssml, wav_path, profile)
            with wave.open(str(wav_path), "rb") as audio:
                if audio.getsampwidth() != 2:
                    raise RuntimeError("Audition requires 16-bit PCM WAV")
                mp3 = encode_mp3(
                    audio.readframes(audio.getnframes()),
                    sample_rate=audio.getframerate(),
                    channels=audio.getnchannels(),
                )
            output_mp3 = prefix.with_name(prefix.name + ".mp3")
            output_mp3.write_bytes(mp3)
        finally:
            if wav_path.exists():
                wav_path.unlink()
        write_object(
            prefix.with_name(prefix.name + ".synthesis.json"),
            {
                "synthesis": synthesis,
                "fallback_reason": reason,
                "mp3_sha256": file_hash(output_mp3),
            },
        )
        print(f"OK  {synthesis['provider']} / {synthesis['voice']}: {output_mp3}")
    return 0


def list_voices_command(args: argparse.Namespace) -> int:
    load_tts_environment(args.env_file)
    voices = QwenTTSClient().request("/v1/voices").get("voices", [])
    for voice in voices:
        print(
            f"{voice.get('voice_id')}\t{voice.get('conditioning_state')}\t{voice.get('name')}"
        )
    print(f"OK  {len(voices)} Qwen voices")
    return 0


def configure_voice_command(args: argparse.Namespace) -> int:
    project = args.project.expanduser().resolve()
    config = load_project_config(project)
    if config["deliverable"] not in NARRATION_DELIVERABLES:
        raise RuntimeError("Voice configuration requires a narration deliverable")
    paths = project_paths(project)
    current = load_voice_profile(paths["voice_profile"])
    provider = getattr(args, "provider", None)
    qwen_voice = getattr(args, "qwen_voice", None)
    if qwen_voice is not None and (provider or current["provider"]) == "azure-speech":
        raise ValueError("--qwen-voice requires --provider auto or qwen3-tts-openai")
    if provider is not None or qwen_voice is not None:
        load_environment(project, getattr(args, "env_file", None))
        if (
            provider in {"auto", "qwen3-tts-openai"}
            and not qwen_voice
            and not current.get("qwen_voice")
        ):
            qwen_voice = os.getenv("QWEN_TTS_VOICE_ID") or None
        current_settings = dict(current)
        if provider is not None:
            current_settings["provider"] = provider
        if qwen_voice is not None:
            current_settings["qwen_voice"] = qwen_voice
        configured = normalize_voice_profile(current_settings)
    else:
        configured = current
    updated = apply_voice_overrides(
        paths["voice_profile"],
        configured,
        voice=args.voice,
        rate=args.rate,
        pitch=args.pitch,
        persist=False,
        announce=args.dry_run,
    )
    pronunciation_file = getattr(args, "pronunciation_file", None)
    replace_pronunciations = bool(getattr(args, "replace_pronunciations", False))
    if replace_pronunciations and pronunciation_file is None:
        raise ValueError("--replace-pronunciations requires --pronunciation-file")
    if pronunciation_file is not None:
        glossary_path = pronunciation_file.expanduser().resolve()
        glossary = load_object(glossary_path)
        raw_pronunciations = (
            glossary.get("pronunciations") if "pronunciations" in glossary else glossary
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
        require_narration_pitch(
            normalize_director_pages(director),
            updated,
        )
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
    configure.add_argument(
        "--provider", choices=("auto", "qwen3-tts-openai", "azure-speech")
    )
    configure.add_argument(
        "--qwen-voice", help="Registered Qwen voice ID; --voice remains the Azure voice"
    )
    configure.add_argument("--env-file", type=Path)
    configure.add_argument("--rate")
    configure.add_argument("--pitch")
    configure.add_argument("--pronunciation-file", type=Path)
    configure.add_argument("--replace-pronunciations", action="store_true")
    configure.add_argument("--dry-run", action="store_true")
    configure.set_defaults(func=configure_voice_command)

    audition = subparsers.add_parser("audition")
    audition.add_argument("--project", type=Path, required=True)
    audition.add_argument(
        "--voices",
        help="Comma-separated Qwen voice IDs, or Azure names with --provider azure-speech",
    )
    audition.add_argument(
        "--provider", choices=("auto", "qwen3-tts-openai", "azure-speech")
    )
    audition.add_argument("--text")
    audition.add_argument("--rate")
    audition.add_argument("--pitch")
    audition.add_argument("--output-dir", type=Path)
    audition.add_argument("--env-file", type=Path)
    audition.add_argument("--dry-run", action="store_true")
    audition.set_defaults(func=audition_command)

    voices = subparsers.add_parser(
        "list-voices", help="List registered Qwen voices without generating audio"
    )
    voices.add_argument("--env-file", type=Path)
    voices.set_defaults(func=list_voices_command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    if sys.platform == "win32" and not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(main())
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)

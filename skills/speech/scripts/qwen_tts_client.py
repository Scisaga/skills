#!/usr/bin/env python3
"""Bounded, non-streaming client for qwen3-tts-openai narration jobs."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path
from typing import Any

from common import write_object

SKILL_ROOT = Path(os.path.abspath(__file__)).parent.parent


class QwenTTSError(RuntimeError):
    """The selected Qwen service cannot execute this narration."""


def load_tts_environment(explicit: Path | None = None) -> None:
    candidates = [
        explicit,
        Path.cwd() / ".env",
        SKILL_ROOT / ".env",
        SKILL_ROOT / "scripts" / ".env",
    ]
    existing = list(
        dict.fromkeys(
            path.expanduser().resolve()
            for path in candidates
            if path is not None and path.expanduser().is_file()
        )
    )
    if explicit is not None and not explicit.expanduser().is_file():
        raise FileNotFoundError(f"Environment file not found: {explicit}")
    if not existing:
        return
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise RuntimeError(
            "Found .env but cannot load it without python-dotenv; "
            "install with: python -m pip install python-dotenv"
        ) from exc
    for path in existing:
        load_dotenv(path, override=False, encoding="utf-8-sig")


def service_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    value = value.removesuffix("/v1")
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise QwenTTSError(
            "QWEN_TTS_API_BASE must be an HTTP(S) service URL without credentials"
        )
    return value


def positive_env_float(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise QwenTTSError(f"{name} must be a positive number") from exc
    if not math.isfinite(value) or value <= 0:
        raise QwenTTSError(f"{name} must be a positive number")
    return value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Keep bearer tokens on the configured origin.
        return None


class QwenTTSClient:
    def __init__(self) -> None:
        base = os.getenv("QWEN_TTS_API_BASE", "")
        if not base.strip():
            raise QwenTTSError("QWEN_TTS_API_BASE is not configured in .env")
        self.base_url = service_base_url(base)
        self.api_key = os.getenv("QWEN_TTS_API_KEY", "")
        self.timeout = positive_env_float("QWEN_TTS_TIMEOUT_SECONDS", 1800)
        self.poll_interval = positive_env_float("QWEN_TTS_POLL_INTERVAL_SECONDS", 2)
        host = urllib.parse.urlsplit(self.base_url).hostname or ""
        try:
            direct = ipaddress.ip_address(host).is_private
        except ValueError:
            direct = host == "localhost" or host.endswith(".local")
        handlers = [NoRedirect()]
        if direct:
            handlers.append(urllib.request.ProxyHandler({}))
        self.opener = urllib.request.build_opener(*handlers)

    def request(
        self,
        path: str,
        payload: dict | None = None,
        *,
        timeout: float = 15,
        binary: bool = False,
    ) -> Any:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path, data=body, headers=headers
        )
        try:
            with self.opener.open(request, timeout=timeout) as response:
                data = response.read()
            if binary:
                return data
            result = json.loads(data)
            if not isinstance(result, dict):
                raise ValueError("expected a JSON object")  # noqa: TRY004 -- invalid response contents
            return result
        except urllib.error.HTTPError as exc:
            detail = exc.read(4096).decode("utf-8", errors="replace")
            if self.api_key:
                detail = detail.replace(self.api_key, "[redacted]")
            raise QwenTTSError(f"Qwen {path}: HTTP {exc.code}: {detail}") from exc
        except (OSError, ValueError) as exc:
            raise QwenTTSError(f"Qwen {path}: {exc}") from exc

    def resolve(self, profile: dict[str, Any]) -> dict[str, Any]:
        ready = self.request("/ready")
        if ready.get("inference_ready") is not True:
            raise QwenTTSError("Qwen model or audio tools are not ready")
        voice_id = profile.get("qwen_voice")
        if not voice_id:
            raise QwenTTSError(
                "No Qwen voice configured; run list-voices, then "
                "synthesize --qwen-voice VOICE_ID "
                "(or set QWEN_TTS_VOICE_ID)"
            )
        voices = self.request("/v1/voices").get("voices", [])
        if not isinstance(voices, list) or any(not isinstance(v, dict) for v in voices):
            raise QwenTTSError("Qwen returned an invalid voice list")
        voice = next((v for v in voices if v.get("voice_id") == voice_id), None)
        if voice is None or voice.get("conditioning_state") != "ready":
            raise QwenTTSError(
                f"Qwen voice {voice_id!r} is missing or not ready; run list-voices"
            )
        model = ready.get("model", {})
        if not isinstance(model, dict):
            raise QwenTTSError("Qwen returned invalid model metadata")
        identity = model.get("identity", {})
        if (
            not isinstance(identity, dict)
            or not identity.get("model_id")
            or not voice.get("conditioning_key")
        ):
            raise QwenTTSError("Qwen returned incomplete model/reference identity")
        voice_model = voice.get("model")
        reference = voice.get("reference")
        if not isinstance(voice_model, dict) or not isinstance(reference, dict):
            raise QwenTTSError("Qwen returned incomplete voice model/reference metadata")
        for voice_key, model_key in (("model_id", "model_id"), ("revision", "resolved_revision"),
                                     ("dtype", "dtype"), ("adapter_version", "adapter_version")):
            if not voice_model.get(voice_key) or voice_model[voice_key] != identity.get(model_key):
                raise QwenTTSError("Qwen voice conditioning differs from the ready model")
        self.resolved_identity = {
            "provider": "qwen3-tts-openai",
            "voice": voice_id,
            "base_url": self.base_url,
            "model": {
                key: identity.get(key)
                for key in (
                    "model_id",
                    "resolved_revision",
                    "dtype",
                    "adapter_version",
                )
            },
            "inference_engine": model.get("inference_engine"),
            "backend": model.get("backend"),
            "attention": model.get("attention"),
            "conditioning_key": voice.get("conditioning_key"),
            "reference_sha256": reference.get("processed_sha256"),
        }
        return self.resolved_identity

    def payload(self, ssml: str, profile: dict[str, Any]) -> dict[str, Any]:
        return {
            "ssml": ssml,
            "voice_id": profile["qwen_voice"],
            "voice_mapping": {profile["voice"]: profile["qwen_voice"]},
            "compatibility": "build-narrated-presentation",
            "allow_degraded": False,
            "allow_experimental": False,
        }

    def compile(self, ssml: str, profile: dict[str, Any]) -> dict[str, Any]:
        plan = self.request("/v1/narrations/compile", self.payload(ssml, profile))
        if plan.get("valid") is not True:
            issues = "; ".join(
                f"{row.get('code')}: {row.get('message')}"
                for row in plan.get("issues", [])
                if row.get("severity") == "error"
            )
            raise QwenTTSError("Qwen preflight failed: " + (issues or "invalid plan"))
        return plan

    def validate_execution(self, plan: dict, manifest: dict, profile: dict) -> None:
        """Bind downloaded output to the compiled text, selected voice and controls."""
        def object_field(parent, key):
            value = parent.get(key, {})
            if not isinstance(value, dict):
                raise QwenTTSError(f"Qwen returned invalid execution {key}")
            return value

        for key in ("source_hash", "text_hash"):
            if not plan.get(key) or plan[key] != manifest.get(key):
                raise QwenTTSError(f"Qwen execution {key} differs from the compiled plan")
        expected_units, actual_units = plan.get("units"), manifest.get("units")
        if not isinstance(expected_units, list) or not expected_units or not isinstance(actual_units, list):
            raise QwenTTSError("Qwen execution has no verifiable generation units")
        if any(not isinstance(row, dict) for row in expected_units + actual_units):
            raise QwenTTSError("Qwen execution contains invalid generation units")
        if [row.get("unit_id") for row in actual_units] != [row.get("unit_id") for row in expected_units]:
            raise QwenTTSError("Qwen executed units differ from the compiled plan")
        expected_identity = getattr(self, "resolved_identity", {}).get("model", {})
        actual_identity = object_field(object_field(manifest, "model"), "identity")
        if expected_identity and any(actual_identity.get(key) != value for key, value in expected_identity.items()):
            raise QwenTTSError("Qwen model changed during generation")
        for expected, actual in zip(expected_units, actual_units):
            if actual.get("voice_id") != profile["qwen_voice"]:
                raise QwenTTSError("Qwen executed a different voice")
            planned, executed = object_field(expected, "postprocessing"), object_field(actual, "controls")
            for key in ("tempo", "pitch_semitones", "gain_db"):
                wanted, got = planned.get(key), executed.get(key)
                if any(isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value)
                       for value in (wanted, got)) or not math.isclose(wanted, got, abs_tol=1e-6):
                    raise QwenTTSError(f"Qwen did not execute the requested {key}")
                owner = object_field(actual, "control_owners").get(key)
                if wanted != {"tempo": 1, "pitch_semitones": 0, "gain_db": 0}[key] and (not isinstance(owner, str) or not owner or owner in {"none", "unsupported"}):
                    raise QwenTTSError(f"Qwen did not declare an execution owner for {key}")
            instruction = object_field(expected, "model_instruction")
            if instruction.get("style") and object_field(actual, "model_instruction").get("effective") != instruction.get("effective"):
                raise QwenTTSError("Qwen did not execute the requested style")

    def wait_for_job(self, job_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout
        next_update = 0.0
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise QwenTTSError(
                        f"Qwen job {job_id} timed out after {self.timeout:g}s"
                    )
                job = self.request(f"/v1/jobs/{job_id}", timeout=min(15, remaining))
                status = job.get("status")
                if status == "succeeded":
                    return job
                if status in {"failed", "cancelled", "canceled"}:
                    raise QwenTTSError(
                        f"Qwen job {job_id} {status}: {job.get('error')}"
                    )
                if time.monotonic() >= next_update:
                    print(
                        f"INFO Qwen job {job_id}: {status}, progress={job.get('progress', 0)}",
                        flush=True,
                    )
                    next_update = time.monotonic() + 10
                time.sleep(min(self.poll_interval, max(0, deadline - time.monotonic())))
        except (QwenTTSError, KeyboardInterrupt):
            try:
                self.request(f"/v1/jobs/{job_id}/cancel", {}, timeout=5)
            except QwenTTSError as exc:
                print(
                    f"WARN Qwen job cancellation could not be confirmed: {exc}",
                    flush=True,
                )
            raise

    def artifact(self, job: dict[str, Any], name: str, *, binary: bool = False) -> Any:
        row = next(
            (r for r in job.get("artifacts", []) if r.get("artifact_id") == name), None
        )
        if not row:
            raise QwenTTSError(f"Qwen job has no {name} artifact")
        job_id = urllib.parse.quote(job["job_id"], safe="")
        data = self.request(
            f"/v1/jobs/{job_id}/artifacts/{name}", binary=True, timeout=60
        )
        if len(data) != row.get("bytes") or hashlib.sha256(data).hexdigest() != row.get(
            "sha256"
        ):
            raise QwenTTSError(f"Qwen {name} artifact size or SHA256 mismatch")
        try:
            if binary:
                return data
            result = json.loads(data)
            if not isinstance(result, dict):
                raise ValueError("expected a JSON object")  # noqa: TRY004 -- invalid artifact contents
            return result
        except ValueError as exc:
            raise QwenTTSError(f"Qwen {name} artifact is not JSON") from exc

    def synthesize(
        self,
        ssml: str,
        profile: dict[str, Any],
        output_wav: Path,
        evidence_prefix: Path,
    ) -> dict[str, int]:
        plan = self.compile(ssml, profile)
        write_object(
            evidence_prefix.with_name(evidence_prefix.name + ".qwen-plan.json"), plan
        )
        submitted = self.request(
            "/v1/narrations", self.payload(ssml, profile), timeout=30
        )
        job_id = submitted.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            raise QwenTTSError("Qwen did not return a job_id")
        write_object(
            evidence_prefix.with_name(evidence_prefix.name + ".qwen-job.json"),
            submitted,
        )
        job = self.wait_for_job(urllib.parse.quote(job_id, safe=""))
        write_object(
            evidence_prefix.with_name(evidence_prefix.name + ".qwen-job.json"), job
        )
        timeline = self.artifact(job, "timeline")
        manifest = self.artifact(job, "manifest")
        self.validate_execution(plan, manifest, profile)
        write_object(
            evidence_prefix.with_name(evidence_prefix.name + ".qwen-timeline.json"),
            timeline,
        )
        write_object(
            evidence_prefix.with_name(evidence_prefix.name + ".qwen-manifest.json"),
            manifest,
        )
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        output_wav.write_bytes(self.artifact(job, "full-wav", binary=True))
        try:
            with wave.open(str(output_wav), "rb") as audio:
                if audio.getsampwidth() != 2 or audio.getnchannels() not in {1, 2}:
                    raise QwenTTSError(
                        "Qwen full-wav must contain 16-bit mono or stereo PCM"
                    )
                sample_rate = audio.getframerate()
                frames = audio.getnframes()
                if sample_rate <= 0 or frames <= 0:
                    raise QwenTTSError("Qwen full-wav is empty or has an invalid sample rate")
                actual_bytes = 0
                while block := audio.readframes(65536):
                    actual_bytes += len(block)
                if actual_bytes != frames * audio.getnchannels() * 2:
                    raise QwenTTSError("Qwen full-wav PCM data is truncated")
        except (wave.Error, EOFError) as exc:
            raise QwenTTSError("Qwen full-wav is not a valid PCM WAV") from exc
        rows = timeline.get("pages", [])
        if [r.get("page") for r in rows] != [
            r.get("page") for r in plan.get("pages", [])
        ]:
            raise QwenTTSError("Qwen timeline pages differ from the compiled plan")
        previous_end = 0
        bookmarks = {}
        for row in rows:
            start, end = row.get("start_seconds"), row.get("end_seconds")
            if any(
                isinstance(v, bool)
                or not isinstance(v, (int, float))
                or not math.isfinite(v)
                for v in (start, end)
            ):
                raise QwenTTSError("Qwen timeline contains invalid page boundaries")
            start_frame, end_frame = (
                round(start * sample_rate),
                round(end * sample_rate),
            )
            if (
                abs(start_frame - previous_end) > 1
                or end_frame <= start_frame
                or end_frame > frames + 1
            ):
                raise QwenTTSError(
                    "Qwen timeline is not contiguous within the actual WAV"
                )
            bookmarks[f"page-{row['page']:02d}"] = round(start * 10_000_000)
            previous_end = end_frame
        if not rows or abs(previous_end - frames) > 1:
            raise QwenTTSError("Qwen timeline does not cover the actual WAV")
        return bookmarks

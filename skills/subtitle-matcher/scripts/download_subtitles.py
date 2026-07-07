#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import requests
from bs4 import BeautifulSoup

from subtitle_matcher import (
    SUBTITLE_EXTS,
    VIDEO_EXTS,
    existing_auto_subtitles,
    is_probable_chinese_subtitle,
    iter_videos,
    language_from_name,
    load_env_files,
    load_cues,
    rel,
    validate_subtitle,
    write_html_report,
)


SUBHD_HOST = "https://subhd.tv"
REPORT_NAME = "_subtitle_download_report.html"
VERSION_TOKENS = {
    "webdl",
    "web",
    "webrip",
    "bluray",
    "brrip",
    "uhd",
    "hdtv",
    "hmax",
    "amzn",
    "nf",
    "dsnp",
    "atvp",
    "itunes",
    "h264",
    "h265",
    "x264",
    "x265",
    "hevc",
    "avc",
    "hdr",
    "hdr10",
    "hdr10plus",
    "dv",
    "ddp5",
    "dd5",
    "eac3",
    "atmos",
    "truehd",
    "dts",
    "1080p",
    "2160p",
    "720p",
    "smurf",
    "flux",
    "nogrp",
    "cm",
    "cmrg",
    "tepes",
    "naisu",
    "apex",
    "ntg",
    "fgt",
    "rarbg",
    "yts",
    "tbd",
    "timedcut",
    "timecut",
}
STOP_TOKENS = VERSION_TOKENS | {
    "proper",
    "repack",
    "korean",
    "japanese",
    "10bit",
    "aac",
    "aac2",
    "mp3",
    "ddp",
    "h",
    "rip",
    "dl",
}
TITLE_STOP = {"the", "a", "an", "and", "of", "in", "on", "for", "to"}
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
SID_RE = re.compile(r"/a/([A-Za-z0-9]+)")
URL_RE = re.compile(r"https?://[^\s|,，；;<>\"']+")
SIMPLIFIED_MARKERS = ("chs", "zh-cn", "zh_cn", "简体", "简中", "简英", "gb", "simplified")
TRADITIONAL_MARKERS = ("cht", "zh-tw", "zh_tw", "zh-hant", "繁体", "繁中", "繁英", "big5", "traditional")


@dataclass(frozen=True)
class Candidate:
    sid: str
    title: str
    url: str
    source: str
    score: int = 0
    reason: str = ""


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def tokens(value: str) -> list[str]:
    return [token for token in normalize_text(value).split() if token]


def video_identity(video: Path) -> dict[str, Any]:
    stem = video.stem
    folder = video.parent.name
    combined = f"{stem} {folder}"
    all_tokens = tokens(combined)
    years = set(YEAR_RE.findall(combined))
    title_tokens: list[str] = []
    for token in tokens(stem):
        if token in years:
            break
        if token in STOP_TOKENS or token.isdigit():
            break
        title_tokens.append(token)
    if not title_tokens:
        for token in all_tokens:
            if token in years or token in STOP_TOKENS or token.isdigit():
                break
            title_tokens.append(token)
    title_tokens = [token for token in title_tokens if token not in TITLE_STOP]
    if not title_tokens:
        title_tokens = [token for token in all_tokens if token not in STOP_TOKENS and token not in years][:4]

    version_tokens = {token for token in all_tokens if token in VERSION_TOKENS}
    return {
        "stem": stem,
        "folder": folder,
        "years": years,
        "title_tokens": set(title_tokens),
        "version_tokens": version_tokens,
    }


def search_terms(video: Path) -> list[str]:
    identity = video_identity(video)
    title = " ".join(identity["title_tokens"])
    years = sorted(identity["years"])
    terms = [
        video.stem,
        re.sub(r"[._]+", " ", video.stem),
    ]
    if title and years:
        terms.append(f"{title} {years[0]}")
    if title:
        terms.append(title)
    return list(dict.fromkeys(term.strip() for term in terms if term.strip()))


def candidate_score(video: Path, title: str) -> tuple[int, str]:
    identity = video_identity(video)
    cand_tokens = set(tokens(title))
    score = 0
    reasons: list[str] = []

    title_overlap = identity["title_tokens"] & cand_tokens
    if identity["title_tokens"]:
        ratio = len(title_overlap) / len(identity["title_tokens"])
        score += int(ratio * 80)
        if title_overlap:
            reasons.append("title:" + ",".join(sorted(title_overlap)))

    candidate_years = set(YEAR_RE.findall(title))
    if identity["years"] and candidate_years:
        if identity["years"] & candidate_years:
            score += 45
            reasons.append("year")
        else:
            score -= 80
            reasons.append("wrong_year")

    version_overlap = identity["version_tokens"] & cand_tokens
    if version_overlap:
        score += min(45, len(version_overlap) * 9)
        reasons.append("tokens:" + ",".join(sorted(version_overlap)))

    lowered = title.lower()
    if any(word in lowered for word in ("官方", "itunes", "netflix", "精校", "字幕组")):
        score += 12
        reasons.append("quality")
    if any(word in lowered for word in SIMPLIFIED_MARKERS):
        score += 14
        reasons.append("simplified")
    if any(word in lowered for word in TRADITIONAL_MARKERS):
        score += 5
        reasons.append("traditional")
    if any(word in lowered for word in ("机器翻译", "机翻")):
        score -= 25
        reasons.append("machine")
    return score, "; ".join(reasons)


def acceptable_candidate(video: Path, candidate: Candidate) -> bool:
    identity = video_identity(video)
    cand_tokens = set(tokens(candidate.title))
    if identity["title_tokens"]:
        overlap = identity["title_tokens"] & cand_tokens
        if not overlap:
            return False
        if len(identity["title_tokens"]) > 1 and len(overlap) / len(identity["title_tokens"]) < 0.45:
            return False
    years = set(YEAR_RE.findall(candidate.title))
    if identity["years"] and years and not (identity["years"] & years):
        return False
    return candidate.score >= 45


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
    )
    return session


def parse_subhd_candidates(html: str, source: str, video: Path) -> list[Candidate]:
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    candidates: list[Candidate] = []
    for anchor in soup.find_all("a", href=True):
        match = SID_RE.search(anchor["href"])
        if not match:
            continue
        sid = match.group(1)
        if sid in seen:
            continue
        seen.add(sid)
        title = anchor.get_text(" ", strip=True)
        if not title:
            continue
        score, reason = candidate_score(video, title)
        candidates.append(
            Candidate(
                sid=sid,
                title=title,
                url=f"{SUBHD_HOST}/a/{sid}",
                source=source,
                score=score,
                reason=reason,
            )
        )
    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates


def search_subhd(session: requests.Session, video: Path, max_pages: int = 1) -> list[Candidate]:
    results: list[Candidate] = []
    seen: set[str] = set()
    for term in search_terms(video):
        url = f"{SUBHD_HOST}/search/{quote(term)}"
        response = session.get(url, timeout=30)
        response.raise_for_status()
        for candidate in parse_subhd_candidates(response.text, f"SubHD search: {term}", video):
            if candidate.sid in seen:
                continue
            seen.add(candidate.sid)
            results.append(candidate)
        time.sleep(0.4)
        if max_pages <= 1:
            continue
    results.sort(key=lambda item: item.score, reverse=True)
    return results


def legacy_candidates(root: Path, video: Path, legacy_csv: Path | None) -> list[Candidate]:
    if legacy_csv is None or not legacy_csv.exists():
        return []
    try:
        video_rel = str(video.relative_to(root))
    except ValueError:
        video_rel = str(video)
    candidates: list[Candidate] = []
    with legacy_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("video") != video_rel:
                continue
            text = " ".join(row.get(key, "") for key in ("reason", "candidate", "url"))
            for raw_url in URL_RE.findall(text):
                match = SID_RE.search(raw_url)
                if not match:
                    continue
                sid = match.group(1)
                title = raw_url
                score, reason = candidate_score(video, title)
                candidates.append(
                    Candidate(
                        sid=sid,
                        title=title,
                        url=f"{SUBHD_HOST}/a/{sid}",
                        source="legacy-report-url",
                        score=score + 25,
                        reason=reason or "legacy URL",
                    )
                )
    dedup: dict[str, Candidate] = {}
    for candidate in candidates:
        if candidate.sid not in dedup or candidate.score > dedup[candidate.sid].score:
            dedup[candidate.sid] = candidate
    return sorted(dedup.values(), key=lambda item: item.score, reverse=True)


def enrich_candidate_title(session: requests.Session, video: Path, candidate: Candidate) -> Candidate:
    try:
        response = session.get(candidate.url, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return candidate
    soup = BeautifulSoup(response.text, "html.parser")
    title = ""
    if soup.title:
        title = soup.title.get_text(" ", strip=True).split(" 分享交流")[0].strip()
    if not title:
        button = soup.find(attrs={"sid": candidate.sid})
        if button:
            title = button.get_text(" ", strip=True)
    if not title or title == candidate.title:
        return candidate
    score, reason = candidate_score(video, title)
    return Candidate(
        sid=candidate.sid,
        title=title,
        url=candidate.url,
        source=candidate.source,
        score=max(candidate.score, score),
        reason=reason or candidate.reason,
    )


def subhd_download_url(session: requests.Session, candidate: Candidate) -> str:
    down_url = f"{SUBHD_HOST}/down/{candidate.sid}"
    session.get(candidate.url, timeout=30)
    session.get(down_url, timeout=30)
    response = session.post(
        f"{SUBHD_HOST}/api/sub/down",
        json={"sid": candidate.sid},
        headers={"Origin": SUBHD_HOST, "Referer": down_url, "Content-Type": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("success") or not data.get("pass") or not data.get("url"):
        raise RuntimeError(data.get("msg") or data.get("error") or "SubHD API did not return a download URL")
    return str(data["url"])


def safe_suffix_from_url(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix else ".bin"


def download_file(session: requests.Session, url: str, output: Path) -> Path:
    response = session.get(url, timeout=90)
    response.raise_for_status()
    content = response.content
    if content[:15].lower().startswith(b"<!doctype html") or content[:6].lower().startswith(b"<html"):
        raise RuntimeError("download URL returned HTML instead of a subtitle archive")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)
    return output


def safe_archive_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    path = Path(normalized)
    return not path.is_absolute() and ".." not in path.parts and ":" not in normalized


def extract_zip(archive: Path, dest: Path) -> list[Path]:
    extracted: list[Path] = []
    with zipfile.ZipFile(archive) as handle:
        for info in handle.infolist():
            if info.is_dir() or not safe_archive_member(info.filename):
                continue
            target = dest / info.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with handle.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted.append(target)
    return extracted


def extract_with_tar(archive: Path, dest: Path) -> list[Path]:
    tar = shutil.which("tar")
    if not tar:
        raise RuntimeError("tar.exe not found; cannot extract this archive type")
    listing = subprocess.run([tar, "-tf", str(archive)], capture_output=True, text=True, errors="replace")
    if listing.returncode != 0:
        raise RuntimeError((listing.stderr or listing.stdout or "tar could not list archive").strip())
    for line in listing.stdout.splitlines():
        if line.strip() and not safe_archive_member(line.strip()):
            raise RuntimeError(f"unsafe archive member: {line.strip()}")
    result = subprocess.run([tar, "-xf", str(archive), "-C", str(dest)], capture_output=True, text=True, errors="replace")
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "tar could not extract archive").strip())
    return [path for path in dest.rglob("*") if path.is_file()]


def extract_downloaded_file(downloaded: Path, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    data = downloaded.read_bytes()[:8]
    suffix = downloaded.suffix.lower()
    if suffix in SUBTITLE_EXTS:
        target = dest / downloaded.name
        shutil.copy2(downloaded, target)
        return [target]
    if suffix == ".zip" or data.startswith(b"PK"):
        return extract_zip(downloaded, dest)
    if suffix in {".rar", ".7z"} or data.startswith(b"Rar!") or data.startswith(b"7z"):
        return extract_with_tar(downloaded, dest)
    if suffix in SUBTITLE_EXTS or b"-->" in downloaded.read_bytes()[:2048]:
        target = dest / (downloaded.stem + ".srt")
        shutil.copy2(downloaded, target)
        return [target]
    raise RuntimeError(f"unsupported downloaded file type: {downloaded.name}")


def score_extracted_subtitle(video: Path, subtitle: Path) -> tuple[int, dict[str, Any] | None]:
    try:
        report = validate_subtitle(video, subtitle)
    except RuntimeError as exc:
        return (-999, {"status": "fail", "reason": str(exc), "subtitle": str(subtitle)})
    score = 0
    if report["status"] == "pass":
        score += 300
    elif report["status"] == "manual_check":
        score += 220
    else:
        reason = str(report.get("reason", ""))
        diff = report.get("diff_seconds")
        if reason.startswith("duration_mismatch") and isinstance(diff, (int, float)) and diff <= 600:
            score += 180
        else:
            return (-999, report)
    score += min(80, int(report.get("cue_count") or 0) // 20)
    score += min(80, int(report.get("cjk_count") or 0) // 40)
    lowered = subtitle.name.lower()
    script = report.get("script") or language_from_name(subtitle)
    if script == "chs":
        score += 38
    elif script == "cht":
        score += 16
    if any(marker in lowered for marker in SIMPLIFIED_MARKERS):
        score += 10
    if any(marker in lowered for marker in TRADITIONAL_MARKERS):
        score += 4
    if subtitle.suffix.lower() == ".srt":
        score += 8
    return score, report


def select_subtitle(video: Path, files: list[Path]) -> tuple[Path | None, dict[str, Any] | None, list[str]]:
    subtitle_files = [path for path in files if path.suffix.lower() in SUBTITLE_EXTS]
    diagnostics: list[str] = []
    scored: list[tuple[int, Path, dict[str, Any] | None]] = []
    for subtitle in subtitle_files:
        if not is_probable_chinese_subtitle(subtitle):
            diagnostics.append(f"{subtitle.name}: non_chinese")
            continue
        score, report = score_extracted_subtitle(video, subtitle)
        diagnostics.append(f"{subtitle.name}: {report.get('status') if report else 'unknown'} {report.get('reason') if report else ''}")
        if score > -999:
            scored.append((score, subtitle, report))
    if not scored:
        return None, None, diagnostics
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1], scored[0][2], diagnostics


def category_for_failure(reason: str) -> str:
    lowered = reason.lower()
    if any(token in lowered for token in ("api", "download", "html instead", "timeout", "connection", "验证", "500")):
        return "retry_download"
    if any(token in lowered for token in ("extract", "archive", "tar", "zip", "rar", "7z", "unsupported")):
        return "retry_extract"
    if "wrong_year" in lowered or "no acceptable candidate" in lowered:
        return "hard_reject"
    return "unresolved_not_completed"


def report_row(
    root: Path,
    video: Path,
    status: str,
    category: str,
    source: str = "",
    candidate: str = "",
    target: Path | None = None,
    reason: str = "",
    urls: list[str] | None = None,
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "video": rel(video, root),
        "status": status,
        "source": source,
        "candidate": candidate,
        "target": "" if target is None else rel(target, root),
        "max_diff_seconds": None if not validation else validation.get("diff_seconds"),
        "comparable_diff_seconds": None
        if not validation or validation.get("diff_seconds") is None or float(validation["diff_seconds"]) > 600
        else validation.get("diff_seconds"),
        "categories": [category] if category else [],
        "urls": urls or [],
        "reason": reason,
    }


def process_video(
    root: Path,
    video: Path,
    session: requests.Session,
    work_dir: Path,
    legacy_csv: Path | None,
    max_candidates: int,
    dry_run: bool,
) -> dict[str, Any]:
    auto = existing_auto_subtitles(video)
    if auto:
        return report_row(root, video, "skipped_existing", "", target=auto[0], reason="existing auto-load subtitle")

    raw_candidates = legacy_candidates(root, video, legacy_csv)
    try:
        raw_candidates.extend(search_subhd(session, video))
    except requests.RequestException as exc:
        if not raw_candidates:
            return report_row(root, video, "not_completed", "retry_download", source="SubHD", reason=f"search_failed: {exc}")

    dedup: dict[str, Candidate] = {}
    for candidate in raw_candidates:
        if candidate.sid not in dedup or candidate.score > dedup[candidate.sid].score:
            dedup[candidate.sid] = candidate

    enriched: list[Candidate] = []
    for candidate in sorted(dedup.values(), key=lambda item: item.score, reverse=True)[: max_candidates * 2]:
        enriched_candidate = enrich_candidate_title(session, video, candidate)
        if acceptable_candidate(video, enriched_candidate):
            enriched.append(enriched_candidate)
    enriched.sort(key=lambda item: item.score, reverse=True)

    if not enriched:
        return report_row(
            root,
            video,
            "not_completed",
            "hard_reject",
            source="SubHD",
            reason="no acceptable candidate after title/year scoring",
        )

    failures: list[str] = []
    video_work = work_dir / re.sub(r"[^A-Za-z0-9._-]+", "_", video.stem)[:120]
    video_work.mkdir(parents=True, exist_ok=True)
    for candidate in enriched[:max_candidates]:
        try:
            download_url = subhd_download_url(session, candidate)
            downloaded = video_work / f"{candidate.sid}{safe_suffix_from_url(download_url)}"
            download_file(session, download_url, downloaded)
            extract_dir = video_work / f"{candidate.sid}_extract"
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            files = extract_downloaded_file(downloaded, extract_dir)
            selected, validation, diagnostics = select_subtitle(video, files)
            if not selected:
                failures.append(f"{candidate.title}: no usable Chinese subtitle; {' | '.join(diagnostics[:6])}")
                continue
            lang = str(validation.get("script") or language_from_name(selected))
            target = video.with_name(f"{video.stem}.{lang}{selected.suffix.lower()}")
            validation_status = validation.get("status") if validation else "manual_check"
            if validation_status == "pass":
                status = "completed_subhd"
                category = "completed_subhd"
            elif validation_status == "manual_check":
                status = "manual_check"
                category = "manual_check"
            else:
                status = "needs_compare"
                category = "needs_compare"
            reason = (
                f"SubHD candidate accepted: {candidate.title}; score={candidate.score}; "
                f"{candidate.reason}; validation={validation.get('status') if validation else 'unknown'} "
                f"{validation.get('reason') if validation else ''}"
            )
            if not dry_run:
                if target.exists():
                    return report_row(
                        root,
                        video,
                        "skipped_existing",
                        "",
                        source="SubHD",
                        candidate=candidate.title,
                        target=target,
                        reason="target appeared before copy",
                        urls=[candidate.url, download_url],
                        validation=validation,
                    )
                shutil.copy2(selected, target)
            return report_row(
                root,
                video,
                status,
                category,
                source="SubHD",
                candidate=candidate.title,
                target=target,
                reason=reason,
                urls=[candidate.url, download_url],
                validation=validation,
            )
        except Exception as exc:
            failures.append(f"{candidate.title}: {type(exc).__name__}: {exc}")
            time.sleep(0.5)

    failure_text = " | ".join(failures[:10])
    return report_row(
        root,
        video,
        "not_completed",
        category_for_failure(failure_text),
        source="SubHD",
        candidate="; ".join(f"{c.title} ({c.sid})" for c in enriched[:max_candidates]),
        reason=failure_text or "no candidate completed",
        urls=[candidate.url for candidate in enriched[:max_candidates]],
    )


def build_report(root: Path, rows: list[dict[str, Any]], source: str) -> dict[str, Any]:
    category_counts: dict[str, int] = {}
    by_category: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        for category in row.get("categories", []):
            category_counts[category] = category_counts.get(category, 0) + 1
            by_category.setdefault(category, []).append(row)
    return {
        "source_report": source,
        "root": str(root),
        "row_count": len(rows),
        "category_counts": category_counts,
        "by_category": by_category,
        "rows": rows,
    }


def cmd_search_download(args: argparse.Namespace) -> int:
    load_env_files(args.env_file)
    root = Path(args.root).resolve()
    work_dir = Path(args.work_dir).resolve() if args.work_dir else Path(os.environ.get("TEMP", ".")) / "subtitle_work_codex" / "live_search"
    legacy_csv = Path(args.legacy_csv).resolve() if args.legacy_csv else root / "_subtitle_download_report.csv"
    session = make_session()

    videos = [video for video in iter_videos(root) if not existing_auto_subtitles(video)]
    if args.video:
        requested = {str(Path(item)) for item in args.video}
        videos = [video for video in videos if str(video) in requested or rel(video, root) in requested or video.name in requested]
    if args.limit:
        videos = videos[: args.limit]

    rows: list[dict[str, Any]] = []
    for index, video in enumerate(videos, start=1):
        print(f"[{index}/{len(videos)}] {rel(video, root)}", flush=True)
        rows.append(
            process_video(
                root=root,
                video=video,
                session=session,
                work_dir=work_dir,
                legacy_csv=legacy_csv,
                max_candidates=args.max_candidates,
                dry_run=args.dry_run,
            )
        )

    report = build_report(root, rows, "SubHD live search")
    output = Path(args.html_output) if args.html_output else root / REPORT_NAME
    write_html_report(report, output, title="字幕重新检索报告")
    print(f"HTML report written: {output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search and download Chinese subtitles into video folders")
    parser.add_argument("--root", required=True, help="Video root directory")
    parser.add_argument("--env-file", help="Load this .env file instead of the standard .env search order")
    parser.add_argument("--legacy-csv", help="Optional legacy report to seed candidate URLs")
    parser.add_argument("--html-output", help="HTML report path; defaults to <root>/_subtitle_download_report.html")
    parser.add_argument("--work-dir", help="Temporary download/extract directory")
    parser.add_argument("--max-candidates", type=int, default=6, help="Candidates to try per missing video")
    parser.add_argument("--limit", type=int, help="Process only the first N missing videos")
    parser.add_argument("--video", action="append", help="Process only this video path/name; can be repeated")
    parser.add_argument("--dry-run", action="store_true", help="Search and validate but do not copy subtitle files")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return cmd_search_download(args)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

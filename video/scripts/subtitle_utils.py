#!/usr/bin/env python3
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

SRT_TIMESTAMP_RE = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2},\d{3})(?P<rest>[^\r\n]*)"
)
ASS_EVENT_RE = re.compile(
    r"^(?P<prefix>(?:Dialogue|Comment):\s*[^,]*,)(?P<start>\d+:\d{2}:\d{2}\.\d{2}),(?P<end>\d+:\d{2}:\d{2}\.\d{2})(?P<rest>.*)$",
    re.MULTILINE,
)
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
ASS_OVERRIDE_RE = re.compile(r"\{[^}]*\}")


@dataclass
class SubtitleCue:
    start: float
    end: float
    text: str

    @property
    def midpoint(self) -> float:
        return self.start + max(0.0, self.end - self.start) / 2


def srt_time_to_ms(ts: str) -> int:
    hours, minutes, rest = ts.split(":")
    seconds, millis = rest.split(",")
    total = (
        int(hours) * 3600 * 1000
        + int(minutes) * 60 * 1000
        + int(seconds) * 1000
        + int(millis)
    )
    return total


def ms_to_srt_time(ms: int) -> str:
    ms = max(0, ms)
    hours, rem = divmod(ms, 3600 * 1000)
    minutes, rem = divmod(rem, 60 * 1000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def ass_time_to_ms(ts: str) -> int:
    hours, minutes, rest = ts.split(":")
    seconds, centis = rest.split(".")
    total = (
        int(hours) * 3600 * 1000
        + int(minutes) * 60 * 1000
        + int(seconds) * 1000
        + int(centis) * 10
    )
    return total


def ms_to_ass_time(ms: int) -> str:
    ms = max(0, ms)
    total_cs = int(round(ms / 10))
    total_seconds, centis = divmod(total_cs, 100)
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centis:02d}"


def shift_srt_timestamps(text: str, offset_ms: int) -> str:
    def repl(match: re.Match[str]) -> str:
        start_ms = srt_time_to_ms(match.group("start")) + offset_ms
        end_ms = srt_time_to_ms(match.group("end")) + offset_ms
        start_ms = max(0, start_ms)
        end_ms = max(0, end_ms)
        if end_ms < start_ms:
            end_ms = start_ms
        return f"{ms_to_srt_time(start_ms)} --> {ms_to_srt_time(end_ms)}{match.group('rest')}"

    return SRT_TIMESTAMP_RE.sub(repl, text)


def shift_ass_timestamps(text: str, offset_ms: int) -> str:
    def repl(match: re.Match[str]) -> str:
        start_ms = ass_time_to_ms(match.group("start")) + offset_ms
        end_ms = ass_time_to_ms(match.group("end")) + offset_ms
        start_ms = max(0, start_ms)
        end_ms = max(0, end_ms)
        if end_ms < start_ms:
            end_ms = start_ms
        return (
            f"{match.group('prefix')}"
            f"{ms_to_ass_time(start_ms)},{ms_to_ass_time(end_ms)}"
            f"{match.group('rest')}"
        )

    return ASS_EVENT_RE.sub(repl, text)


def detect_subtitle_format(suffix: str, text: str) -> str | None:
    lower = suffix.lower()
    if lower in (".ass", ".ssa"):
        return "ass"
    if lower == ".srt":
        return "srt"
    if SRT_TIMESTAMP_RE.search(text):
        return "srt"
    return None


def apply_subtitle_offset(
    text: str,
    subtitle_format: str | None,
    offset_sec: float,
) -> tuple[str, bool]:
    if offset_sec == 0 or subtitle_format is None:
        return text, False
    offset_ms = int(round(offset_sec * 1000))
    if subtitle_format == "ass":
        return shift_ass_timestamps(text, offset_ms), True
    if subtitle_format == "srt":
        return shift_srt_timestamps(text, offset_ms), True
    return text, False


def has_cjk(text: str) -> bool:
    return bool(CJK_RE.search(text))


def join_with_space(left: str, right: str) -> str:
    left = left.rstrip()
    right = right.lstrip()
    if not left:
        return right
    if not right:
        return left
    return f"{left} {right}"


def ass_has_cjk(line: str) -> bool:
    return has_cjk(ASS_OVERRIDE_RE.sub("", line))


def merge_same_script_lines(
    lines: list[str],
    is_cjk_fn,
) -> list[str]:
    if not lines:
        return []
    merged = [lines[0]]
    for line in lines[1:]:
        prev = merged[-1]
        prev_is_cjk = is_cjk_fn(prev)
        line_is_cjk = is_cjk_fn(line)
        if prev_is_cjk == line_is_cjk:
            if prev_is_cjk:
                merged[-1] = prev.rstrip() + line.lstrip()
            else:
                merged[-1] = join_with_space(prev, line)
        else:
            merged.append(line)
    return merged


def remove_ass_linebreaks(text: str) -> str:
    def process_text_field(text_field: str) -> str:
        parts = re.split(r"(\\N|\\n)", text_field)
        if len(parts) == 1:
            return text_field
        lines = []
        for idx in range(0, len(parts), 2):
            lines.append(parts[idx])
        merged = merge_same_script_lines(lines, ass_has_cjk)
        return r"\N".join(merged)

    out_lines = []
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        newline = line[len(content):]
        if content.startswith(("Dialogue:", "Comment:")):
            parts = content.split(",", 9)
            if len(parts) == 10:
                parts[9] = process_text_field(parts[9])
                content = ",".join(parts)
        out_lines.append(content + newline)
    return "".join(out_lines)


def remove_srt_linebreaks(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", normalized.strip())
    new_blocks = []
    for block in blocks:
        lines = block.split("\n")
        if not lines:
            continue
        if len(lines) >= 2 and "-->" in lines[1]:
            idx = lines[0]
            timing = lines[1]
            content_lines = lines[2:]
        elif "-->" in lines[0]:
            idx = None
            timing = lines[0]
            content_lines = lines[1:]
        else:
            new_blocks.append(block)
            continue
        merged_lines = merge_same_script_lines(
            [line.rstrip() for line in content_lines if line.strip()],
            has_cjk,
        )
        content = "\n".join(merged_lines)
        if idx is None:
            new_blocks.append("\n".join([timing, content]))
        else:
            new_blocks.append("\n".join([idx, timing, content]))
    return "\n\n".join(new_blocks) + "\n"


def apply_subtitle_linebreaks(
    text: str,
    subtitle_format: str | None,
    remove_linebreaks: bool,
) -> tuple[str, bool]:
    if not remove_linebreaks or subtitle_format is None:
        return text, False
    if subtitle_format == "ass":
        return remove_ass_linebreaks(text), True
    if subtitle_format == "srt":
        return remove_srt_linebreaks(text), True
    return text, False


def convert_subtitle_to_utf8(
    subtitle_path: str,
    sub_charenc: str | None,
    sub_offset_sec: float,
    remove_linebreaks: bool,
) -> tuple[str, str, bool, bool]:
    path = Path(subtitle_path)
    encodings = []
    if sub_charenc:
        encodings.append(sub_charenc)
    encodings.extend(
        [
            "utf-8",
            "utf-8-sig",
            "gb18030",
            "cp936",
            "big5",
            "utf-16",
            "utf-16le",
            "utf-16be",
        ]
    )

    seen = set()
    ordered = []
    for enc in encodings:
        key = enc.lower()
        if key not in seen:
            ordered.append(enc)
            seen.add(key)

    text = None
    used_enc = None
    for enc in ordered:
        try:
            text = path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
        except LookupError:
            continue
        else:
            used_enc = enc
            break

    if text is None:
        raise RuntimeError("Unable to decode subtitle; provide --sub-charenc.")

    subtitle_format = detect_subtitle_format(path.suffix, text)
    text, offset_applied = apply_subtitle_offset(text, subtitle_format, sub_offset_sec)
    text, linebreaks_applied = apply_subtitle_linebreaks(text, subtitle_format, remove_linebreaks)

    suffix = path.suffix if path.suffix else ".srt"
    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=suffix,
        prefix=f"{path.stem}.utf8.",
        mode="w",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        handle.write(text)
        tmp_path = handle.name

    return tmp_path, used_enc, offset_applied, linebreaks_applied


def parse_srt_cues(text: str) -> list[SubtitleCue]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    cues: list[SubtitleCue] = []
    for block in re.split(r"\n\s*\n", normalized):
        lines = [line.rstrip() for line in block.split("\n")]
        if not lines:
            continue

        if len(lines) >= 2 and "-->" in lines[1]:
            timing_line = lines[1]
            content_lines = lines[2:]
        elif "-->" in lines[0]:
            timing_line = lines[0]
            content_lines = lines[1:]
        else:
            continue

        match = SRT_TIMESTAMP_RE.match(timing_line)
        if not match:
            continue

        cues.append(
            SubtitleCue(
                start=srt_time_to_ms(match.group("start")) / 1000.0,
                end=srt_time_to_ms(match.group("end")) / 1000.0,
                text="\n".join([line for line in content_lines if line.strip()]).strip(),
            )
        )
    return cues


def parse_ass_cues(text: str) -> list[SubtitleCue]:
    cues: list[SubtitleCue] = []
    for match in ASS_EVENT_RE.finditer(text):
        parts = match.group(0).split(",", 9)
        text_field = parts[9] if len(parts) == 10 else match.group("rest")
        plain_text = ASS_OVERRIDE_RE.sub("", text_field).replace(r"\N", "\n").replace(r"\n", "\n").strip()
        cues.append(
            SubtitleCue(
                start=ass_time_to_ms(match.group("start")) / 1000.0,
                end=ass_time_to_ms(match.group("end")) / 1000.0,
                text=plain_text,
            )
        )
    return cues


def load_subtitle_cues(path: Path) -> list[SubtitleCue]:
    text = path.read_text(encoding="utf-8", errors="replace")
    subtitle_format = detect_subtitle_format(path.suffix, text)
    if subtitle_format == "ass":
        return parse_ass_cues(text)
    return parse_srt_cues(text)

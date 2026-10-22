from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from build_manifest import build_manifest, render_review
from narration_performance import (
    PERFORMANCE_CONTRACT,
    audit_narration_performance,
    derive_page_performance,
)
from narration_pitch import (
    PITCH_MAX_ST,
    PITCH_MIN_ST,
    narration_pitch_audit,
)
from production_common import (
    chapter_audio_fingerprint,
    chapter_groups,
    normalize_director_pages,
    normalize_voice_profile,
)
from qa_presentation import narration_pitch_qa


def voice_profile(pitch: str = "+0st") -> dict:
    return normalize_voice_profile(
        {
            "schema_version": 1,
            "provider": "azure-speech",
            "voice": "zh-CN-XiaochenNeural",
            "style": None,
            "rate": "+0%",
            "pitch": pitch,
            "page_break_ms": 120,
            "pronunciations": {},
            "audition": {"text": "试听。"},
        }
    )


def director_with_pitches(
    pitches: list[str],
    *,
    varied_rate_and_pause: bool,
) -> dict:
    intents = ["opening", "context", "explanation", "closing"]
    rates = ["-4%", "+4%", "-2%", "+5%"]
    pauses = [180, 80, 150, 0]
    pages = []
    for index, pitch in enumerate(pitches, 1):
        pages.append(
            {
                "page": index,
                "chapter": f"chapter-{index:02d}",
                "role": f"第 {index} 页",
                "intent": intents[index - 1],
                "direction": f"第 {index} 页采用清楚且具体的语气方向。",
                "rationale": f"第 {index} 页需要用不同节奏完成当前表达任务。",
                "target_seconds": 20,
                "segments": [
                    {
                        "text": f"第 {index} 页正文。",
                        "rate": rates[index - 1] if varied_rate_and_pause else "-4%",
                        "pitch": pitch,
                        "pause_after_ms": pauses[index - 1]
                        if varied_rate_and_pause
                        else 0,
                    }
                ],
            }
        )
    return {
        "schema_version": 2,
        "policy": {
            "visual_sync": "independent",
            "performance_contract": PERFORMANCE_CONTRACT,
        },
        "pages": pages,
    }


class NarrationPitchTests(unittest.TestCase):
    def test_default_generation_keeps_local_pitch_within_point_one(self) -> None:
        titles = [
            "开场",
            "背景",
            "机制解释",
            "方案对比",
            "验证数据",
            "典型案例",
            "能力布局",
            "结论",
            "结束",
        ]
        generated: list[float] = []
        for page, title in enumerate(titles, 1):
            performance = derive_page_performance(
                page=page,
                total_pages=len(titles),
                title=title,
                body="第一段用于建立关系。\n\n第二段用于收束结论。",
                paragraphs=["第一段用于建立关系。", "第二段用于收束结论。"],
            )
            generated.extend(
                float(segment["pitch"][:-2])
                for segment in performance["segments"]
            )
        self.assertTrue(generated)
        self.assertGreaterEqual(min(generated), PITCH_MIN_ST)
        self.assertLessEqual(max(generated), PITCH_MAX_ST)
        self.assertTrue(set(generated).issubset({-0.1, 0.0, 0.1}))

    def test_combined_pitch_blocks_manifest_before_ssml(self) -> None:
        director = director_with_pitches(
            ["+0.1st", "+0st", "+0st", "+0st"],
            varied_rate_and_pause=True,
        )
        profile = voice_profile("+0.1st")
        pages = normalize_director_pages(director)
        audit = narration_pitch_audit(pages, profile)
        qa_errors: list[str] = []
        self.assertEqual(
            narration_pitch_qa(
                pages,
                profile,
                {"narration_pitch": audit},
                qa_errors,
            )["status"],
            "blocked",
        )
        self.assertTrue(any("page 1 segment 1" in row for row in qa_errors))
        with self.assertRaisesRegex(ValueError, r"page 1 segment 1.*\+0.2st"):
            build_manifest(None, director, profile)

    def test_negative_global_and_positive_local_cancel_to_zero(self) -> None:
        director = director_with_pitches(
            ["+0.1st", "+0st", "+0st", "+0st"],
            varied_rate_and_pause=True,
        )
        profile = voice_profile("-0.1st")
        manifest = build_manifest(None, director, profile)
        pitch = manifest["narration_pitch"]
        self.assertEqual(pitch["segments"][0]["final_pitch"], "+0st")
        review = render_review(manifest)
        self.assertIn("- 全局语速 / 音高：`+0%` / `-0.1st`", review)
        self.assertIn(
            "| `-0.1st` | `+0.1st` | `-4%` | `+0st` |",
            review,
        )
        pages = normalize_director_pages(director)
        chapter = chapter_groups(pages)[0]
        _, ssml = chapter_audio_fingerprint(chapter, profile)
        self.assertIn('pitch="+0st"', ssml)
        self.assertEqual(
            narration_pitch_audit(pages, profile),
            manifest["narration_pitch"],
        )
        qa_errors: list[str] = []
        self.assertEqual(
            narration_pitch_qa(pages, profile, manifest, qa_errors),
            manifest["narration_pitch"],
        )
        self.assertEqual(qa_errors, [])

    def test_zero_pitch_passes_when_rate_and_pause_profiles_vary(self) -> None:
        director = director_with_pitches(
            ["+0st"] * 4,
            varied_rate_and_pause=True,
        )
        audit = audit_narration_performance(director)
        self.assertEqual(audit["status"], "pass", audit["errors"])

    def test_pitch_alternation_does_not_create_audible_profiles(self) -> None:
        director = director_with_pitches(
            ["-0.1st", "+0.1st", "-0.1st", "+0.1st"],
            varied_rate_and_pause=False,
        )
        audit = audit_narration_performance(director)
        self.assertEqual(audit["status"], "blocked")
        self.assertTrue(
            any(
                "prosody pattern" in message or "audible profiles" in message
                for message in audit["errors"]
            )
        )

    def test_global_and_local_components_reject_wider_default_range(self) -> None:
        with self.assertRaisesRegex(ValueError, r"within -0.1st to \+0.1st"):
            voice_profile("+0.2st")
        director = director_with_pitches(
            ["+0.2st", "+0st", "+0st", "+0st"],
            varied_rate_and_pause=True,
        )
        with self.assertRaisesRegex(ValueError, r"within -0.1st to \+0.1st"):
            normalize_director_pages(director)


if __name__ == "__main__":
    unittest.main()

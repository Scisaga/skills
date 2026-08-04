from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from build_manifest import build_manifest, render_review
from production_common import (
    normalize_voice_profile,
    pronunciation_audit,
    pronunciation_candidate_terms,
    pronunciation_fragment,
)


def voice_profile(pronunciations: dict[str, dict[str, str]]) -> dict:
    return normalize_voice_profile(
        {
            "schema_version": 1,
            "provider": "azure-speech",
            "voice": "zh-CN-XiaochenNeural",
            "style": None,
            "rate": "+0%",
            "pitch": "+0st",
            "page_break_ms": 120,
            "pronunciations": pronunciations,
            "audition": {"text": "试听。"},
        }
    )


def director(text: str) -> dict:
    return {
        "schema_version": 2,
        "policy": {
            "visual_sync": "independent",
            "performance_contract": "rhetorical-v1",
        },
        "pages": [
            {
                "page": 1,
                "chapter": "chapter-01",
                "role": "材料牌号",
                "intent": "explanation",
                "direction": "清楚说明材料牌号。",
                "rationale": "避免中英混读歧义。",
                "target_seconds": 20,
                "segments": [
                    {
                        "text": text,
                        "rate": "+0%",
                        "pitch": "+0st",
                        "pause_after_ms": 120,
                    }
                ],
            }
        ],
    }


class PronunciationTests(unittest.TestCase):
    def test_material_designation_uses_semantic_alias(self) -> None:
        rendered = pronunciation_fragment(
            "材料是 AlSi10Mg。",
            {"AlSi10Mg": {"alias": "铝硅十镁"}},
        )
        self.assertIn(
            '<sub alias="铝硅十镁">AlSi10Mg</sub>',
            rendered,
        )

    def test_ascii_boundaries_do_not_split_larger_grade(self) -> None:
        rendered = pronunciation_fragment(
            "TA1、TA15、XTA1 和 TA10",
            {"TA1": {"alias": "T A 一"}},
        )
        self.assertIn('<sub alias="T A 一">TA1</sub>、TA15', rendered)
        self.assertNotIn("</sub>5", rendered)
        self.assertNotIn("X<sub", rendered)
        self.assertNotIn("</sub>0", rendered)

    def test_say_as_characters_is_supported(self) -> None:
        profile = voice_profile({"LMD": {"say_as": "characters"}})
        self.assertEqual(
            profile["pronunciations"]["LMD"],
            {"say_as": "characters"},
        )
        self.assertEqual(
            pronunciation_fragment("LMD", profile["pronunciations"]),
            '<say-as interpret-as="characters">LMD</say-as>',
        )

    def test_candidate_inventory_includes_contextual_numeric_grades(self) -> None:
        text = (
            "钛合金，包括 TA1；铝合金，包括 AlSi10Mg、6061；"
            "不锈钢，包括 316L、304。"
        )
        candidates = pronunciation_candidate_terms(text)
        for term in ("TA1", "AlSi10Mg", "6061", "316L", "304"):
            self.assertIn(term, candidates)

    def test_audit_and_review_show_configured_and_uncovered_terms(self) -> None:
        text = "铝合金，包括 AlSi10Mg、6061；钛合金，包括 TA1。"
        profile = voice_profile(
            {"AlSi10Mg": {"alias": "铝硅十镁"}}
        )
        pages = director(text)["pages"]
        audit = pronunciation_audit(pages, profile["pronunciations"])
        self.assertEqual(
            [row["term"] for row in audit["configured"]],
            ["AlSi10Mg"],
        )
        self.assertEqual(
            {row["term"] for row in audit["uncovered"]},
            {"6061", "TA1"},
        )

        manifest = build_manifest(None, director(text), profile)
        review = render_review(manifest)
        self.assertIn("专业术语发音审阅", review)
        self.assertIn("铝硅十镁", review)
        self.assertIn("`6061`", review)
        self.assertIn("未配置读法", review)


if __name__ == "__main__":
    unittest.main()

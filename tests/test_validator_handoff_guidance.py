"""Contract tests for validator handoff reporting guidance."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ValidatorHandoffGuidanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.shared = (
            ROOT / "agents" / "_shared" / "validation-reporting-guidance.md"
        ).read_text(encoding="utf-8")
        self.claude_agents = {
            "code-validator": (
                ROOT / "agents" / "code-validator" / "code-validator-agent.md"
            ).read_text(encoding="utf-8"),
            "architecture-validator": (
                ROOT
                / "agents"
                / "architecture-validator"
                / "architecture-validator-agent.md"
            ).read_text(encoding="utf-8"),
            "pr-reviewer": (
                ROOT / "agents" / "pr-reviewer" / "pr-reviewer-agent.md"
            ).read_text(encoding="utf-8"),
        }
        self.codex_skills = {
            "dcness-code-validator": (
                ROOT / "codex" / "skills" / "dcness-code-validator" / "SKILL.md"
            ).read_text(encoding="utf-8"),
            "dcness-architecture-validator": (
                ROOT
                / "codex"
                / "skills"
                / "dcness-architecture-validator"
                / "SKILL.md"
            ).read_text(encoding="utf-8"),
            "dcness-pr-reviewer": (
                ROOT / "codex" / "skills" / "dcness-pr-reviewer" / "SKILL.md"
            ).read_text(encoding="utf-8"),
        }

    def test_shared_guidance_defines_fail_escalate_note_and_delta_first(self) -> None:
        for needle in (
            "# 검증 보고 가이드",
            "FAIL / ESCALATE 판단 노트",
            "재검증 delta-first 보고",
            "heading 은 권장 카테고리일 뿐 필수 schema 가 아니다",
            "판정",
            "깨진 기대",
            "근거",
            "확인 위치",
            "영향 표면",
            "오케스트레이터 판단점",
            "판단 한계",
            "해소됨",
            "유지됨",
            "신규",
            "판단 불가",
            "changed / resolved / still failing / new",
        ):
            self.assertIn(needle, self.shared)

    def test_shared_guidance_preserves_prose_only_boundaries(self) -> None:
        for needle in (
            "별도 영구 산출물 작성 금지",
            "read-only agent 가 직접 파일을 쓰지 않는다",
            "JSON, marker, 고정 schema, 필수 heading 강제는 도입하지 않는다",
            "`PASS` 단발에는 적용하지 않는다",
            "수정 설계, 담당자 지정, 최소 수정 범위 요구는 넣지 않는다",
            "형식이 아니라 의미 요구다",
        ):
            self.assertIn(needle, self.shared)

    def test_claude_side_validation_agents_reference_shared_guidance(self) -> None:
        for name, text in self.claude_agents.items():
            with self.subTest(agent=name):
                self.assertIn(
                    "../_shared/validation-reporting-guidance.md", text
                )
                self.assertIn("FAIL / ESCALATE 판단 노트", text)
                self.assertIn("재검증 delta-first 보고", text)

    def test_codex_read_only_validation_skills_embed_same_reporting_guidance(
        self,
    ) -> None:
        for name, text in self.codex_skills.items():
            with self.subTest(skill=name):
                for needle in (
                    "FAIL / ESCALATE 판단 노트",
                    "재검증 delta-first 보고",
                    "heading 은 권장 카테고리일 뿐 필수 schema 가 아니다",
                    "changed / resolved / still failing / new",
                    "JSON, marker, 고정 schema, 필수 heading 강제는 도입하지 않는다",
                    "수정 설계, 담당자 지정, 최소 수정 범위 요구는 넣지 않는다",
                ):
                    self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()

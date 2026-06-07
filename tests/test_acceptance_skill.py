"""Acceptance skill MVP contract tests."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AcceptanceSkillContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill = ROOT / "skills" / "acceptance" / "SKILL.md"
        self.routing = ROOT / "skills" / "acceptance" / "acceptance-routing.md"

    def test_acceptance_skill_exists_as_story_epic_mvp(self) -> None:
        text = self.skill.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^name:\s*acceptance$")
        self.assertIn("story issue", text)
        self.assertIn("epic issue", text)
        self.assertIn("PRD/stories path", text)
        self.assertIn("구현 PR 목록", text)
        self.assertIn("STORY_ACCEPTANCE", text)
        self.assertIn("EPIC_ACCEPTANCE", text)
        self.assertNotIn("SPEC_ACCEPTANCE", text)
        self.assertIn("full E2E", text)
        self.assertIn("MVP 범위", text)

    def test_acceptance_routing_defines_pass_fail_without_auto_mutation(self) -> None:
        text = self.routing.read_text(encoding="utf-8")
        self.assertIn("product-acceptance:STORY_ACCEPTANCE", text)
        self.assertIn("product-acceptance:EPIC_ACCEPTANCE", text)
        self.assertIn("PASS", text)
        self.assertIn("FAIL", text)
        self.assertIn("ESCALATE", text)
        self.assertIn("자동 수정", text)
        self.assertIn("자동 issue 생성", text)
        self.assertIn("사용자 승인", text)

    def test_story_and_epic_depth_are_distinct(self) -> None:
        skill = self.skill.read_text(encoding="utf-8")
        routing = self.routing.read_text(encoding="utf-8")
        for text in (skill, routing):
            self.assertIn("AC / PR / test evidence", text)
            self.assertIn("PRD Must", text)
            self.assertIn("cross-story gap", text)
            self.assertIn("security/ops risk", text)

    def test_lite_impl_is_not_forced_into_acceptance(self) -> None:
        text = self.skill.read_text(encoding="utf-8")
        self.assertIn("Lite `/impl`", text)
        self.assertIn("강제하지 않는다", text)

    def test_public_surface_tracks_acceptance_as_advanced_until_flip(self) -> None:
        script = (ROOT / "scripts" / "check_public_surface.mjs").read_text(
            encoding="utf-8"
        )
        positioning = (ROOT / "docs" / "plugin" / "positioning.md").read_text(
            encoding="utf-8"
        )
        advanced_match = re.search(r"advancedSkills:\s*\[([^\]]+)\]", script)
        self.assertIsNotNone(advanced_match)
        self.assertIn("'acceptance'", advanced_match.group(1))
        self.assertIn("`/acceptance`", positioning)

        init_doc = (ROOT / "commands" / "init-dcness.md").read_text(
            encoding="utf-8"
        )
        default_block = re.search(
            r"기본 workflow:\n(?P<body>.*?)\n\n고급 workflow:",
            init_doc,
            re.DOTALL,
        )
        advanced_block = re.search(
            r"고급 workflow:\n(?P<body>.*?)\n\n유틸리티:",
            init_doc,
            re.DOTALL,
        )
        self.assertIsNotNone(default_block)
        self.assertIsNotNone(advanced_block)
        self.assertNotIn("/acceptance", default_block.group("body"))
        self.assertIn("/acceptance", advanced_block.group("body"))


if __name__ == "__main__":
    unittest.main()

"""Design 공개 진입점 contract tests."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DesignSurfaceContractTests(unittest.TestCase):
    def test_design_skill_owns_design_loop_without_architect_loop_alias(self) -> None:
        design_dir = ROOT / "skills" / "design"
        design = (design_dir / "SKILL.md").read_text(encoding="utf-8")
        routing = (design_dir / "design-routing.md").read_text(encoding="utf-8")

        self.assertFalse((ROOT / "skills" / "architect-loop").exists())
        self.assertRegex(design, r"(?m)^name:\s*design$")
        self.assertIn("entry_point**: `design`", design)
        self.assertIn("begin-run design", design)
        self.assertIn("design-routing.md", design)
        self.assertIn("`/spec` 종료 후", design)
        self.assertIn("/spec -> /design -> /impl -> /acceptance", design)
        self.assertIn("`/design` skill **단일 전용**", routing)

        for text in (design, routing):
            self.assertNotIn("/architect-loop", text)
            self.assertNotIn("architect-loop", text)
            self.assertNotIn("호환", text)

    def test_design_is_default_lifecycle_surface(self) -> None:
        script = (ROOT / "scripts" / "check_public_surface.mjs").read_text(
            encoding="utf-8"
        )
        positioning = (ROOT / "docs" / "plugin" / "positioning.md").read_text(
            encoding="utf-8"
        )
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        default_match = re.search(r"defaultSkills:\s*\[([^\]]+)\]", script)
        advanced_match = re.search(r"advancedSkills:\s*\[([^\]]+)\]", script)
        self.assertIsNotNone(default_match)
        self.assertIsNotNone(advanced_match)
        self.assertIn("'design'", default_match.group(1))
        self.assertNotIn("'design'", advanced_match.group(1))

        for text in (positioning, readme):
            self.assertIn("`/design`", text)
            self.assertIn("product/technical design", text)
            self.assertIn("visual design", text)
            self.assertNotIn("`/architect-loop`", text)
            self.assertNotIn("호환 alias", text)

    def test_design_uses_epic_batch_module_design_and_final_validation(self) -> None:
        """#831 — /design no longer interleaves module writing and validation per Story."""
        design_dir = ROOT / "skills" / "design"
        design = (design_dir / "SKILL.md").read_text(encoding="utf-8")
        routing = (design_dir / "design-routing.md").read_text(encoding="utf-8")

        self.assertNotIn("module-architect × K → architecture-validator(2차)", design)
        self.assertNotIn("`PASS × K`", design)
        for stale in (
            "module-architect(common) → architecture-validator(공통 단위)",
            "module-architect(Story N) → architecture-validator(Story 단위)",
            "공통 task 선행 검증",
            "Story별 module-architect+architecture-validator",
            "공통 task 없음 → 공통 단위 검증 없이 Story 1",
            "각 Story 마다 **module-architect",
            "AV_COMMON",
            "AV_STORY",
        ):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, design)
                self.assertNotIn(stale, routing)

        self.assertNotIn(
            "다음 단위 module-architect / (마지막이면) architecture-validator 2차",
            routing,
        )

        for expected in (
            "architecture-validator(1차/system freeze)",
            "module-architect(epic-batch)",
            "epic 전체 impl 산출물을 하나의 컨텍스트에서 일괄 작성",
            "Story 단위 작성 주체로 쪼개지 않는다",
            "architecture-validator(final epic 검증)",
            "Step 5 — architecture-validator final epic 검증",
            "모든 Story 에 단위 검증을 기본값으로 복원하지 않는다",
            "check_design_artifact_structure.mjs",
        ):
            self.assertIn(expected, design)

        for expected in (
            "AV1 -->|PASS| MA_BATCH",
            "MA_BATCH -->|PASS| AV_FINAL",
            "`PASS`(final epic 검증)",
            "module-architect(epic-batch)",
            "architecture-validator(final epic 검증)",
        ):
            self.assertIn(expected, routing)

    def test_design_epic_batch_supports_issue_831_quality_controls(self) -> None:
        design_dir = ROOT / "skills" / "design"
        design = (design_dir / "SKILL.md").read_text(encoding="utf-8")
        routing = (design_dir / "design-routing.md").read_text(encoding="utf-8")
        system_architect = (
            ROOT / "agents" / "system-architect" / "system-architect-agent.md"
        ).read_text(encoding="utf-8")
        module_architect = (
            ROOT / "agents" / "module-architect" / "module-architect-agent.md"
        ).read_text(encoding="utf-8")
        validator = (
            ROOT
            / "agents"
            / "architecture-validator"
            / "architecture-validator-agent.md"
        ).read_text(encoding="utf-8")

        for needle in (
            "기록된 스택 결정",
            "확인 안내 후 skip",
            "첫 epic 등 미기록 상태",
            "domain-model.md 생략 가능",
            "생략 판단 근거",
            "계약 표면 코드 SSOT 대조",
            "포트, 도메인 타입, 공개 entrypoint",
            "risk / engine / depends_on",
            "수정 허용",
        ):
            self.assertIn(needle, design)

        for needle in (
            "final epic 검증 FAIL → 산출 주체 재진입",
            "3 cycle",
            "초과 시 사용자 위임",
        ):
            self.assertIn(needle, routing)

        for text in (system_architect, module_architect, validator):
            with self.subTest(text=text[:60]):
                self.assertIn("계약 표면 코드 SSOT 대조", text)
                self.assertIn("포트, 도메인 타입, 공개 entrypoint", text)


if __name__ == "__main__":
    unittest.main()

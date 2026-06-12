"""Module architect vertical-slice contract tests."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ModuleArchitectVerticalSliceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module_architect = (
            ROOT / "agents" / "module-architect" / "module-architect-agent.md"
        ).read_text(encoding="utf-8")
        self.impl_template = (
            ROOT / "agents" / "module-architect" / "templates" / "impl-task.md"
        ).read_text(encoding="utf-8")
        self.arch_validator = (
            ROOT
            / "agents"
            / "architecture-validator"
            / "architecture-validator-agent.md"
        ).read_text(encoding="utf-8")
        self.arch_validator_template = (
            ROOT
            / "agents"
            / "architecture-validator"
            / "templates"
            / "review-report.md"
        ).read_text(encoding="utf-8")
        self.arch_validator_examples = (
            ROOT
            / "agents"
            / "architecture-validator"
            / "references"
            / "finding-examples.md"
        ).read_text(encoding="utf-8")
        self.codex_arch_validator = (
            ROOT
            / "codex"
            / "skills"
            / "dcness-architecture-validator"
            / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.shared_principles = (
            ROOT / "agents" / "_shared" / "module-design-principles.md"
        ).read_text(encoding="utf-8")
        self.parallel_policy = (
            ROOT / "docs" / "plugin" / "parallel-policy.md"
        ).read_text(encoding="utf-8")
        self.design_skill = (
            ROOT / "skills" / "design" / "SKILL.md"
        ).read_text(encoding="utf-8")

    def test_module_architect_prioritizes_story_behavior_slice_over_file_parallelism(
        self,
    ) -> None:
        """#742 — task split must optimize for product behavior, not only parallel files."""
        for needle in (
            "사용자가 약속받은 동작",
            "수직 슬라이스",
            "제품 동작 슬라이스",
            "병렬 독립성·파일 경계와 동작 슬라이스가 충돌",
            "동작 슬라이스가 우선",
            "마지막 task에서야 처음 동작하는 흐름",
            "Story 완료 시 실제 검증되는 동작",
            "첫 동작 증거 지점",
        ):
            self.assertIn(needle, self.module_architect)

    def test_impl_task_template_requires_story_behavior_slice_evidence(self) -> None:
        for needle in (
            "## Story 동작 슬라이스",
            "Story 완료 시 실제로 검증되는 동작",
            "제품 경계(UI/API/CLI/worker entrypoint/통합 wiring)",
            "첫 동작 증거 지점",
            "병렬성보다 동작 슬라이스를 우선한 결정",
            "Story 마지막 task까지 밀리면",
        ):
            self.assertIn(needle, self.impl_template)

    def test_architecture_validator_checks_vertical_slice_gaps_as_task_local(
        self,
    ) -> None:
        for needle in (
            "사용자가 검증할 제품 동작 수직 슬라이스",
            "제품 동작 슬라이스",
            "Story 완료 시 실제로 검증되는 동작",
            "섹션명만 보지 말고",
            "cross-story 통합 검증에서는 Story별 첫 제품 경계 동작 증거",
            "공통/Story 단위 검증이면 대상 impl 문서의 제품 동작 수직 슬라이스 증거",
            "첫 동작 증거 지점",
            "레이어별 부품 task",
            "마지막 task까지 첫 제품 동작이 밀린 상태",
            "`TASK_LOCAL`",
        ):
            self.assertIn(needle, self.arch_validator)

        self.assertIn("제품 동작 슬라이스", self.arch_validator_template)
        self.assertIn("## Story 동작 수직 슬라이스 검토", self.arch_validator_template)
        self.assertIn("마지막 task까지 동작이 밀리는 분할 여부", self.arch_validator_template)
        self.assertIn("## 제품 동작 슬라이스", self.arch_validator_examples)
        self.assertIn("cross-story 통합 검증", self.arch_validator_examples)

    def test_codex_architecture_validator_checks_same_vertical_slice_axis(
        self,
    ) -> None:
        for needle in (
            "사용자가 검증할 제품 동작 수직 슬라이스",
            "Story 완료 시 실제로 검증되는 동작",
            "제품 경계(UI/API/CLI/worker entrypoint/통합 wiring)",
            "섹션명만 보지 말고",
            "cross-story 통합 검증에서는 Story별 첫 제품 경계 동작 증거",
            "마지막 task까지 첫 제품 동작이 밀린 상태",
            "`TASK_LOCAL`",
        ):
            self.assertIn(needle, self.codex_arch_validator)

    def test_shared_design_principles_and_parallel_policy_preserve_priority(
        self,
    ) -> None:
        for text in (self.shared_principles, self.parallel_policy):
            self.assertIn("제품 동작", text)
            self.assertIn("수직 슬라이스", text)

        self.assertIn("파일 경계를 맞추기 위해", self.parallel_policy)
        self.assertIn("충돌하면 병렬성을 포기", self.parallel_policy)

    def test_design_loop_tells_story_module_architect_to_leave_behavior_evidence(
        self,
    ) -> None:
        for needle in (
            "Story 동작 수직 슬라이스",
            "각 Story 완료 시 실제로 검증되는 동작",
            "첫 제품 경계 동작 증거 지점",
            "제품 동작 슬라이스",
        ):
            self.assertIn(needle, self.design_skill)


if __name__ == "__main__":
    unittest.main()

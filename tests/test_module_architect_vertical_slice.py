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

    def test_architecture_validator_checks_epic_implementation_order(self) -> None:
        for needle in (
            "구현 순서: epic architecture 의 Story/모듈 구현 순서가 의존만이 아니라 "
            "첫 제품 경계 동작 증거를 앞당기는가",
            "system 단위(1차) 검증에서는 epic architecture 의 구현 순서가 "
            "첫 제품 경계 동작 증거를 앞당기는지 확인한다",
            "epic 구현 순서가 사유 없이 부품-먼저로 남은 상태는 `SYSTEM_BOUNDARY` 다",
            "system 단위(1차) 검증이면 epic architecture 의 구현 순서가 "
            "첫 제품 경계 동작 증거를 앞당기는지 검토했다",
        ):
            self.assertIn(needle, self.arch_validator)

        self.assertIn(
            "epic architecture 의 `구현 순서` 섹션 또는 stories.md epic 완료 기준 "
            "근처에 경고와 사유가 있는지 본다",
            self.arch_validator,
        )
        self.assertIn(
            "사유가 기록돼 있으면 finding 대신 warning 으로 보고한다",
            self.arch_validator,
        )
        self.assertIn("| 구현 순서 |", self.arch_validator_template)
        self.assertIn("## 구현 순서", self.arch_validator_examples)
        self.assertIn(
            "인프라/부품 모듈을 전부 만든 뒤에야 첫 사용자 동작이 나오게 정렬됐는데 "
            "사유와 경고가 없음",
            self.arch_validator_examples,
        )
        epic_architecture_template = (
            ROOT
            / "agents"
            / "system-architect"
            / "templates"
            / "epic-architecture.md"
        ).read_text(encoding="utf-8")
        for needle in (
            "## 구현 순서",
            "첫 제품 경계 동작 증거가 나오는 시점:",
            "부품-먼저 순서면 경고와 사유:",
        ):
            self.assertIn(needle, epic_architecture_template)

    def test_codex_architecture_validator_checks_epic_implementation_order(
        self,
    ) -> None:
        for needle in (
            "epic architecture 의 Story/모듈 구현 순서가 의존만이 아니라 "
            "첫 제품 경계 동작 증거를 앞당기는가",
            "system 단위(1차) 검증에서는 epic architecture 의 구현 순서가 "
            "첫 제품 경계 동작 증거를 앞당기는지, 부품-먼저 순서면 epic architecture 의 "
            "`구현 순서` 섹션 또는 stories.md epic 완료 기준 근처에 사유와 경고가 "
            "남았는지 확인한다",
            "사유가 기록돼 있으면 finding 대신 warning 으로 보고한다",
            "epic 구현 순서가 사유 없이 부품-먼저로 남은 상태는 `SYSTEM_BOUNDARY` 다",
        ):
            self.assertIn(needle, self.codex_arch_validator)

    def test_design_loop_first_validation_includes_implementation_order(self) -> None:
        design_routing = (
            ROOT / "skills" / "design" / "design-routing.md"
        ).read_text(encoding="utf-8")
        for text in (self.design_skill, design_routing):
            self.assertIn("구현 순서(첫 제품 경계 동작 앞당김)", text)


if __name__ == "__main__":
    unittest.main()

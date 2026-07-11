"""고위험 상태 계약 추적 문서 계약 테스트 (#1046, #1048)."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StateContractSharedPrinciplesTests(unittest.TestCase):
    """공유 SSOT — module-design-principles.md 의 고위험 상태 계약 절."""

    def setUp(self) -> None:
        self.shared = (
            ROOT / "docs" / "plugin" / "agents" / "_shared" / "module-design-principles.md"
        ).read_text(encoding="utf-8")

    def test_high_risk_state_contract_section_traces_transitions(self) -> None:
        """#1046 — 상태 계약은 추상 문구가 아니라 실제 전이로 추적한다."""
        for needle in (
            "## 고위험 상태 계약",
            "동일 identity 의 가변 필드 변경",
            "empty 와 read failure 구분",
            "source 일부 실패와 기존 상태 보존",
            "no-change/idempotence",
            "trigger → producer → state owner → mutation/write → persistence/read model → consumer",
        ):
            self.assertIn(needle, self.shared)

    def test_stateful_code_ssot_surface_extends_beyond_public_ports(self) -> None:
        """#1046 — 상태성 작업의 코드 SSOT 는 공개 포트만이 아니다."""
        for needle in (
            "schema",
            "mapper",
            "DAO",
            "sync/reconcile",
            "lifecycle producer",
            "관련 기존 테스트",
        ):
            self.assertIn(needle, self.shared)

    def test_confirmed_decision_is_not_verification_exempt(self) -> None:
        """#1046 — 확정 결정 재논쟁 금지 != 검증 면제."""
        self.assertIn("재논쟁", self.shared)
        self.assertIn("검증 면제", self.shared)

    def test_qualitative_findings_are_promotable_with_evidence(self) -> None:
        """#1046 — '질적 판단은 finding 아님' 충돌 문구 교체."""
        self.assertNotIn(
            "질적 판단이 필요한 영역은 finding 이 아니라 수동 review 권고로 분리",
            self.shared,
        )
        self.assertIn("질적 판단이라는 이유만으로", self.shared)
        self.assertIn("방치 시 영향", self.shared)


class ArchitectureValidatorStateContractTests(unittest.TestCase):
    """#1046 — validator 정의 / Codex mirror / design 입력 계약 정렬."""

    def setUp(self) -> None:
        self.validator = (
            ROOT
            / "docs" / "plugin" / "agents"
            / "architecture-validator"
            / "architecture-validator-agent.md"
        ).read_text(encoding="utf-8")
        self.codex_validator = (
            ROOT / "codex" / "skills" / "dcness-architecture-validator" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.design_skill = (ROOT / "skills" / "design" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.examples = (
            ROOT
            / "docs" / "plugin" / "agents"
            / "architecture-validator"
            / "references"
            / "finding-examples.md"
        ).read_text(encoding="utf-8")

    def test_validator_tracks_high_risk_state_contracts(self) -> None:
        for needle in (
            "고위험 상태 계약",
            "module-design-principles.md#고위험-상태-계약",
            "실제 update 경로",
            "재논쟁 금지는 검증 면제가 아니다",
        ):
            self.assertIn(needle, self.validator)

    def test_validator_composes_cross_story_state_and_reports_pass_evidence(self) -> None:
        self.assertIn("공유 identity", self.validator)
        self.assertIn("핵심 상태 전이", self.validator)
        self.assertIn("질적 판단이라는 이유만으로", self.validator)

    def test_codex_mirror_keeps_same_state_contract_semantics(self) -> None:
        for needle in (
            "고위험 상태 계약",
            "전체 implementation task 를 읽고",
            "검증 면제",
            "핵심 상태 전이",
            "질적 판단이라는 이유만으로",
        ):
            self.assertIn(needle, self.codex_validator)

    def test_design_skill_prompt_extends_stateful_code_ssot_pointers(self) -> None:
        self.assertIn(
            "sync/reconcile·adapter·lifecycle producer·관련 테스트",
            self.design_skill,
        )
        self.assertIn("고위험 상태 계약 추적", self.design_skill)

    def test_finding_examples_include_state_contract_false_pass(self) -> None:
        self.assertIn("## 고위험 상태 계약", self.examples)
        self.assertIn("mirror 에 반영되지 않음", self.examples)


class ModuleArchitectStateContractTests(unittest.TestCase):
    """#1048 — module-architect 가 task 분할 전에 상태 계약을 닫는다."""

    def setUp(self) -> None:
        self.module_architect = (
            ROOT
            / "docs"
            / "plugin"
            / "agents"
            / "module-architect"
            / "module-architect-agent.md"
        ).read_text(encoding="utf-8")
        self.impl_template = (
            ROOT
            / "docs"
            / "plugin"
            / "agents"
            / "module-architect"
            / "templates"
            / "impl-task.md"
        ).read_text(encoding="utf-8")
        self.design_skill = (ROOT / "skills" / "design" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.parallel_policy = (ROOT / "docs" / "plugin" / "parallel-policy.md").read_text(
            encoding="utf-8"
        )

    def test_tracks_cross_story_state_contracts_before_task_split(self) -> None:
        for needle in (
            "module-design-principles.md#고위험-상태-계약",
            "task 를 자르기 전에",
            "그 절의 적용 가능한 전이",
            "producer → state owner → persistence/read model → consumer → 제품 증거",
        ):
            self.assertIn(needle, self.module_architect)

    def test_reads_stateful_code_surface_and_expands_entrypoints(self) -> None:
        for needle in (
            "schema·entity·mapper",
            "DAO·repository",
            "sync/reconcile",
            "관련 테스트",
            "receiver·observer·worker",
            "scheduler/job",
            "system callback",
            "application/activity lifecycle",
            "navigation destination",
        ):
            self.assertIn(needle, self.module_architect)

    def test_handoff_summary_keeps_semantics_outside_depends_on(self) -> None:
        self.assertIn(
            "owner/entrypoint 요약 (entrypoint task 한정 또는 cross-task state producer/consumer task)",
            self.impl_template,
        )
        for needle in (
            "produced transition",
            "consumer / consumed state",
            "validation path",
        ):
            self.assertIn(needle, self.impl_template)
        self.assertIn("`depends_on` 은 순서의 단일 SSOT", self.module_architect)
        self.assertIn("semantic produces/consumes", self.module_architect)
        self.assertIn("task 실행 선후의 단일 SSOT", self.parallel_policy)
        self.assertIn("owner/entrypoint 요약에서 복구", self.parallel_policy)
        self.assertNotIn(
            "contract produces/consumes 와 ordering 을 흡수한 단일 SSOT",
            self.parallel_policy,
        )
        self.assertIn(
            "계약 전문 복제 금지는 task-specific transition·실패 책임·acceptance 생략을 뜻하지 않는다",
            self.module_architect,
        )

    def test_revision_audits_preserved_producers_and_consumers(self) -> None:
        for needle in (
            "shared state 계약이 바뀌면",
            "보존 예정 task",
            "producer/consumer 영향 감사",
            "영향이 없으면 원문을 보존",
        ):
            self.assertIn(needle, self.module_architect)

    def test_design_prompt_requires_the_same_pre_split_pass(self) -> None:
        self.assertIn("task 분할 전 high-risk cross-story state contract pass", self.design_skill)
        self.assertIn("producer/consumer 영향 감사", self.design_skill)

    def test_module_architect_behavior_eval_pair_exists(self) -> None:
        cases = ROOT / "evals" / "cases"
        bad_prompt = (cases / "module-state-contract-bad" / "prompt.md").read_text(
            encoding="utf-8"
        )
        bad_expected = (
            cases / "module-state-contract-bad" / "expected.md"
        ).read_text(encoding="utf-8")
        good_prompt = (cases / "module-state-contract-good" / "prompt.md").read_text(
            encoding="utf-8"
        )
        good_expected = (
            cases / "module-state-contract-good" / "expected.md"
        ).read_text(encoding="utf-8")
        fixture_text = "\n".join(
            (cases / case / "fixture.md").read_text(encoding="utf-8")
            for case in ("module-state-contract-bad", "module-state-contract-good")
        )
        self.assertIn("module-architect-agent.md", bad_prompt)
        self.assertIn("module-architect-agent.md", good_prompt)
        self.assertIn("same-identity", bad_expected)
        self.assertIn("producer/consumer scope", bad_expected)
        self.assertIn("불필요하게 재설계", good_expected)
        self.assertNotIn("owner/state handoff", fixture_text)
        self.assertIn("owner/entrypoint 요약", fixture_text)


if __name__ == "__main__":
    unittest.main()

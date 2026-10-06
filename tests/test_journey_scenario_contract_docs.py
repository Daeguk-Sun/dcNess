"""Scenario journey guidance across design, build, review, and acceptance docs."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ScenarioContractDocumentTests(unittest.TestCase):
    """Every stage that designs, builds, reviews, or judges a journey knows scenarios."""

    def _read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_contract_defines_scenarios_partial_runs_and_compatibility(self) -> None:
        text = self._read("docs/plugin/product-journey.md")
        self.assertIn("### 시나리오 단위 실행", text)
        for phrase in ("`scenarios`", "--scenario", "partial=true", "NOT_RUN", "ac_results"):
            self.assertIn(phrase, text)
        self.assertIn("`scenarios`가 없는 기존 매니페스트", text)
        self.assertIn("UI 경계이면 선택한 시나리오의 화면 단계만 판정한다", text)
        build_worker = self._read("docs/plugin/agents/build-worker/build-worker-agent.md")
        self.assertIn("각 `ui_evidence` 단계에 그 화면을 남기는 시나리오의 `scenario_id`", build_worker)

    def test_design_stage_declares_scenarios(self) -> None:
        for path in (
            "docs/plugin/agents/module-architect/module-architect-agent.md",
            "docs/plugin/agents/module-architect/templates/impl-task.md",
        ):
            with self.subTest(path=path):
                text = self._read(path)
                self.assertIn("시나리오", text)
                self.assertIn("담당 AC", text)

    def test_both_architecture_validator_providers_review_scenarios(self) -> None:
        for path in (
            "docs/plugin/agents/architecture-validator/architecture-validator-agent.md",
            "codex/skills/dcness-architecture-validator/SKILL.md",
        ):
            with self.subTest(path=path):
                self.assertIn("시나리오별 id·담당 AC·독립 실행 조건", self._read(path))

    def test_convergence_reruns_failed_scenarios_then_judges_the_rest(self) -> None:
        for path in (
            "docs/plugin/agents/build-worker/build-worker-agent.md",
            "skills/impl-loop/impl-loop-finish.md",
        ):
            with self.subTest(path=path):
                text = self._read(path)
                self.assertIn("--scenario", text)
                self.assertIn("닿는지", text)
                self.assertIn("부분 실행 receipt는 전체 실행 receipt가 아니", text)

    def test_both_impl_validator_providers_match_scenario_ac_to_flow(self) -> None:
        for path in (
            "docs/plugin/agents/impl-validator/impl-validator-agent.md",
            "codex/skills/dcness-impl-validator/SKILL.md",
        ):
            with self.subTest(path=path):
                self.assertIn("각 시나리오의 `target_ac`", self._read(path))

    def test_acceptance_chooses_scenarios_and_judges_per_ac(self) -> None:
        text = self._read("docs/plugin/agents/product-acceptance/product-acceptance-agent.md")
        self.assertIn("같은 판단을 시나리오 단위로 한다", text)
        self.assertIn("`partial=true`이며 전체 실행 receipt가 아니다", text)
        self.assertIn("그 receipt가 없으면 전체 시나리오를 실행한다", text)
        self.assertIn("`ac_results`", text)


if __name__ == "__main__":
    unittest.main()

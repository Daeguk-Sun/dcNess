"""`/impl-loop` device-connected journey convergence contract regressions."""
from __future__ import annotations

import unittest
from pathlib import Path

from harness.agent_boundary import ALLOW_MATRIX


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class JourneyConvergenceContractTests(unittest.TestCase):
    def test_manifest_contract_declares_environment_and_plumbing(self) -> None:
        contract = read("docs/plugin/product-journey.md")

        for needle in (
            "acceptance_environment",
            "automation",
            "automated",
            "human_verification",
            "requirements",
            "probe",
            "prepare",
            "harness_paths",
            "journey 미선언",
            "비발동",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, contract)

    def test_worker_owns_preflight_and_fresh_convergence_call(self) -> None:
        worker = read("docs/plugin/agents/build-worker/build-worker-agent.md")
        skill = read("skills/impl-loop/SKILL.md")

        for needle in (
            "JOURNEY_ENV_PREFLIGHT",
            "worker 실행 컨텍스트",
            "자동 준비",
            "검출이 불확실",
            "JOURNEY_CONVERGENCE",
            "fresh context",
            "실행 → 관찰 → 배관 수정 → 재실행",
            "첫 실행",
            "재현 테스트",
            "설계·AC 계약과 충돌",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, worker + skill)

    def test_validator_has_fixed_target_ac_assertion_check(self) -> None:
        validator = read("docs/plugin/agents/impl-validator/impl-validator-agent.md")

        self.assertIn("고정 항목", validator)
        self.assertIn("`target_ac`", validator)
        self.assertIn("flow의 실제 assertion", validator)
        self.assertIn("self-verify", validator)
        self.assertIn("유일 관문", validator)

    def test_routing_has_bounded_convergence_and_three_way_escalation(self) -> None:
        routing = read("skills/impl-loop/impl-loop-routing.md")

        for needle in (
            "무진행 라운드",
            "3",
            "서로 다른 실패",
            "총 iteration",
            "12",
            "실질 runaway 가드",
            "수렴 재개",
            "production 만 착지",
            "run 폐기",
            "커밋 보존",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, routing)

    def test_clean_sequence_consolidates_after_acceptance_before_first_pr(self) -> None:
        skill = read("skills/impl-loop/SKILL.md")
        section = skill.split("## Story PR / integrated review / merge", 1)[1]

        sequence = (
            "JOURNEY_CONVERGENCE",
            "impl-validator:CODEBASE_SANITY",
            "product-acceptance",
            "target GitHub issue AC close audit",
            "커밋 consolidate",
            "PR 생성",
        )
        positions = [section.index(item) for item in sequence]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("최종 tree", section)
        self.assertIn("불변", section)
        self.assertIn("no-op", section)
        self.assertIn("최초 PR", section)

    def test_human_verification_remains_a_post_pr_merge_gate(self) -> None:
        skill = read("skills/impl-loop/SKILL.md")
        routing = read("skills/impl-loop/impl-loop-routing.md")

        self.assertIn("AC -->|typed require-complete PASS| CONSOLIDATE", routing)
        self.assertIn("CONSOLIDATE --> PRCUT", routing)
        self.assertIn("PRCUT --> HUMAN", routing)
        self.assertIn("human verification 대기", routing)
        self.assertNotIn("미충족·미체크 또는 사람 확인 대기", routing)
        self.assertIn("별도 merge gate", skill)

    def test_write_zero_and_user_merge_gate_remain_unchanged(self) -> None:
        skill = read("skills/impl-loop/SKILL.md")
        routing = read("skills/impl-loop/impl-loop-routing.md")

        self.assertEqual((), ALLOW_MATRIX["product-acceptance"])
        self.assertIn("사용자가 유일한 merge gate", skill)
        self.assertIn("사용자가 유일한 merge gate", routing)
        self.assertIn("자동 merge 금지", skill)
        self.assertIn("자동 merge 금지", routing)


if __name__ == "__main__":
    unittest.main()

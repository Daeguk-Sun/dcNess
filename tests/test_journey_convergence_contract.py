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

    def test_finish_has_bounded_convergence_and_three_way_escalation(self) -> None:
        finish = read("skills/impl-loop/impl-loop-finish.md")

        for needle in (
            "무진행은 3회",
            "3",
            "서로 다른 실패",
            "전체 iteration",
            "12",
            "실질 runaway 가드",
            "수렴 재개",
            "production만 착지",
            "run 폐기",
            "커밋을 보존",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, finish)

    def test_clean_sequence_freezes_before_fail_fast_validation_and_first_pr(self) -> None:
        section = read("skills/impl-loop/impl-loop-finish.md")
        section = section[section.index("마감 순서는 다음과 같다.") :]

        sequence = (
            "JOURNEY_CONVERGENCE",
            "final mutation owner",
            "candidate freeze",
            "holistic `impl-validator`",
            "validator가 terminal `PASS`일 때만",
            "target GitHub issue AC close audit",
            "PR 생성",
        )
        positions = [section.index(item) for item in sequence]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("tracked tree", section)
        self.assertIn("immutable candidate", section)
        self.assertIn("no-op", section)
        self.assertIn("최초 PR", section)

    def test_human_verification_remains_a_post_pr_merge_gate(self) -> None:
        finish = read("skills/impl-loop/impl-loop-finish.md")

        self.assertIn(
            "최초 PR 생성 뒤 `human verification 대기`",
            finish,
        )
        self.assertIn("별도 merge gate", finish)
        self.assertIn("사용자가 유일한 merge gate", finish)

    def test_env_split_is_a_durable_per_journey_deferred_disposition(self) -> None:
        skill = read("skills/impl-loop/SKILL.md") + read(
            "skills/impl-loop/impl-loop-finish.md"
        )
        routing = read("skills/impl-loop/impl-loop-routing.md")
        acceptance = read(
            "docs/plugin/agents/product-acceptance/product-acceptance-agent.md"
        )
        journey = read("docs/plugin/product-journey.md")

        for text in (skill, routing, acceptance, journey):
            with self.subTest(source=text[:40]):
                self.assertIn("journey_deferred", text)
        self.assertIn("ENVUSER -->|journey 검수 분리| DEFER", routing)
        self.assertIn("해당 journey", routing)
        self.assertIn("JOURNEY_CONVERGENCE 비발동", routing)
        self.assertIn("sealed journey 실행 비발동", routing)
        self.assertIn("종료 조건의 수렴 PASS Must 비대상", routing)
        self.assertIn("`Closes`를 붙이지 않는다", routing)
        self.assertIn("나머지 journey", acceptance)
        self.assertIn("매니페스트를 다시 쓰지 않는다", journey)

    def test_env_preflight_does_not_block_implementation(self) -> None:
        """Issue #1218 — 검수 환경 미충족은 구현의 blocker가 아니다."""
        worker = read("docs/plugin/agents/build-worker/build-worker-agent.md")
        routing = read("skills/impl-loop/impl-loop-routing.md")
        finish = read("skills/impl-loop/impl-loop-finish.md")

        self.assertIn("검수 환경과 구현은 독립", worker)
        self.assertIn("task를 중단하지 않는다", worker)
        self.assertIn("검수 환경과 구현은 독립", routing)
        self.assertIn(
            "preflight 는 `IMPLEMENTATION_ESCALATE` 를 내지 않는다", routing
        )
        # 사용자 처분은 사라지지 않고 마감으로 옮겨간다.
        self.assertIn("수렴 직전 사용자 처분 1회", routing)
        self.assertIn("환경 먼저 준비 / 해당 journey 검수 분리", finish)
        self.assertIn("같은 journey의 환경 처분을 다시 묻지 않는다", finish)

    def test_preflight_verdict_reaches_the_finish_sequence(self) -> None:
        """Issue #1218 — PASS 로 완료한 task 의 환경 판정이 마감까지 전달돼야 한다."""
        skill = read("skills/impl-loop/SKILL.md")
        finish = read("skills/impl-loop/impl-loop-finish.md")

        # chain stdout 은 환경 상태를 싣지 않으므로 task loop 가 판정을 보존한다.
        self.assertIn("chain stdout이 환경 상태를 싣지 않는다", skill)
        self.assertIn("진행 뷰에 남긴다", skill)
        self.assertIn("마감의 수렴 직전 환경 처분 입력", skill)
        # 마감은 그 값을 어디서 읽는지 알아야 한다.
        self.assertIn("진행 뷰에 남긴 판정에서 확인한다", finish)

    def test_escalate_resume_path_is_documented_per_entry_point(self) -> None:
        """Issue #1218 — ALREADY_COMPLETED가 가리키는 복구 수단이 실제로 쓸 수 있어야 한다."""
        routing = read("skills/impl-loop/impl-loop-routing.md")
        chain = read("scripts/dcness-implementation-chain")

        self.assertIn("ALREADY_COMPLETED", routing)
        self.assertIn("dcness-helper end-run", routing)
        self.assertIn("`--rework` 는 이 진입점에서 사용할 수 없다", routing)
        self.assertIn("--rework --resume-provider", routing)
        # chain 메시지도 --chain-state 진입점에 --rework를 권하지 않는다.
        self.assertIn("--rework is --direct-run only", chain)

    def test_n_story_convergence_fix_ownership_is_unambiguous(self) -> None:
        skill = read("skills/impl-loop/impl-loop-finish.md")

        self.assertIn("story-local production 수정", skill)
        self.assertIn("해당 story branch", skill)
        self.assertIn("downstream branch를 restack", skill)
        self.assertIn("flow/manifest 보정은 QA branch", skill)

    def test_write_zero_and_user_merge_gate_remain_unchanged(self) -> None:
        skill = read("skills/impl-loop/SKILL.md") + read(
            "skills/impl-loop/impl-loop-finish.md"
        )

        self.assertEqual((), ALLOW_MATRIX["product-acceptance"])
        self.assertIn("사용자가 유일한 merge gate", skill)
        self.assertIn("자동 merge 금지", skill)


if __name__ == "__main__":
    unittest.main()

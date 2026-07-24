"""Fast-start and autonomous recovery contracts for /impl and /impl-loop."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness import session_state

ROOT = Path(__file__).resolve().parents[1]


class ImplFastStartContractTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_impl_reaches_red_without_advisory_preflight_helpers(self) -> None:
        skill = self.read("skills/impl/SKILL.md")

        self.assertIn("착수: <target>", skill)
        self.assertIn("RED", skill)
        self.assertIn("첫 tool call은 pointer만", skill)
        self.assertIn("둘째 tool call 하나에서", skill)
        self.assertIn("다음 tool-bearing turn은 RED test 또는 첫 edit", skill)
        self.assertNotIn("impl-preview", skill)
        self.assertNotIn("boundary-suggestions", skill)
        self.assertNotIn("dcness-tdd-hooks\" status", skill)

    def test_impl_front_door_lazy_loads_finish_contract_after_green(self) -> None:
        skill = self.read("skills/impl/SKILL.md")
        finish = self.read("skills/impl/impl-finish.md")

        self.assertLess(len(skill.encode("utf-8")), 12_000)
        self.assertIn("target 확인 → 격리 → focused read → RED/첫 edit", skill)
        self.assertIn("GREEN 뒤에만", skill)
        self.assertNotIn("## Review Provider", skill)
        self.assertNotIn("### Cartography freshness boundary", skill)
        self.assertNotIn("Sub-agent prompt 작성 checkpoint", skill)
        self.assertIn("Cartography freshness", finish)
        self.assertIn("impl-validator", finish)
        self.assertIn("target GitHub issue AC close audit", finish)
        self.assertIn("PR", finish)

    def test_impl_loop_launches_worker_in_background_without_repeat_preflight(self) -> None:
        skill = self.read("skills/impl-loop/SKILL.md")

        self.assertIn("run_in_background", skill)
        self.assertIn("one-shot launch가 첫 tool call", skill)
        self.assertIn("`nohup`, `&`, `disown`", skill)
        self.assertIn("`.dcness-work`를 미리 만들지 않는다", skill)
        self.assertIn("same-workspace recovery", skill)
        self.assertIn("--init-path", skill)
        self.assertNotIn('routing resolve build-worker', skill)
        self.assertNotIn('prev-tasks-reset" 은', skill)
        self.assertNotIn("begin-step build-worker`로 열고", skill)
        self.assertNotIn("boundary-suggestions --impl-plan", skill)
        self.assertNotIn("generated TDD hook 상태를 확인", skill)

    def test_build_worker_order_gate_does_not_run_advisory_preflights(self) -> None:
        source = self.read("harness/session_state.py")

        gate = source[source.index("def evaluate_order_gate_for_step(") :]
        gate = gate[: gate.index("\ndef ", 1)]
        self.assertNotIn("_impl_plan_boundary_preflight_message", gate)
        self.assertNotIn("_generated_tdd_preflight_message", gate)

    def test_repeated_order_gate_reuses_plan_without_invoking_preflight_scans(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            plan = ROOT / "skills" / "impl-loop" / "SKILL.md"
            with patch(
                "harness.session_state._validate_design_doc",
                return_value=str(plan),
            ):
                session_state.transition(
                    "sid-fast-start",
                    "run_started",
                    run_id="run-11851181",
                    base_dir=base,
                    entry_point="impl",
                    design_doc=str(plan),
                )

            with (
                patch(
                    "harness.boundary_suggestions.collect_boundary_suggestions"
                ) as boundary_scan,
                patch("harness.tdd_hooks.inspect_installation") as tdd_scan,
            ):
                for _ in range(2):
                    self.assertIsNone(
                        session_state.evaluate_order_gate_for_step(
                            "sid-fast-start",
                            "run-11851181",
                            "build-worker",
                            base_dir=base,
                        )
                    )

            boundary_scan.assert_not_called()
            tdd_scan.assert_not_called()

    def test_task_scope_is_reused_as_mutation_time_authority(self) -> None:
        source = self.read("harness/agent_boundary.py")

        self.assertIn("task_scope_paths", source)
        self.assertIn("task-scope", source)

    def test_timeout_defaults_cover_long_headless_work(self) -> None:
        codex = self.read("scripts/dcness-codex-worker")
        claude = self.read("scripts/dcness-claude-worker")
        common = self.read("CLAUDE.md")

        self.assertIn('DCNESS_CODEX_TIMEOUT:-3000', codex)
        self.assertIn('DCNESS_CODEX_IDLE_TIMEOUT:-900', codex)
        self.assertIn('DCNESS_CLAUDE_TIMEOUT:-3000', claude)
        self.assertIn('DCNESS_CLAUDE_IDLE_TIMEOUT:-900', claude)
        self.assertIn("validator `600`, worker `3000`", common)
        self.assertGreaterEqual(common.count("| `900` | X |"), 2)
        self.assertIn(
            "| `DCNESS_IMPLEMENTATION_RECOVERY_LIMIT` "
            "| `dcness-implementation-chain` 의 동일 provider·동일 workspace 자동 복구 "
            "추가 시도 한도 | `2` | X |",
            common,
        )

    def test_external_fast_start_evidence_meets_replay_and_ab_gates(self) -> None:
        evidence = json.loads(
            (ROOT / "evals" / "impl-fast-start-metadata.json").read_text(
                encoding="utf-8"
            )
        )

        main = evidence["impl_main_direct"]
        fresh = evidence["impl_fresh_executor"]["trials"]
        loops = evidence["impl_loop_real_forks"]
        self.assertEqual((len(main), len(fresh), len(loops)), (3, 3, 3))
        self.assertTrue(
            all(
                row["time_to_first_edit_seconds"] < 60
                and row["blocking_assistant_requests"] <= 2
                and row["product_ac_passed"]
                for row in main
            )
        )
        self.assertTrue(
            all(
                row["time_to_first_edit_seconds"] < 60
                and row["product_ac_passed"]
                for row in fresh
            )
        )
        self.assertTrue(all(row["seconds_to_fork"] < 60 for row in loops))
        self.assertEqual(
            evidence["ab_decision"]["default"],
            "main-direct",
        )
        self.assertFalse(
            evidence["ab_decision"]["conditional_fresh_executor"]
        )

    def test_headless_workers_receive_canonical_phase_and_tdd_contracts(self) -> None:
        for wrapper in (
            self.read("scripts/dcness-codex-worker"),
            self.read("scripts/dcness-claude-worker"),
        ):
            with self.subTest(wrapper=wrapper[:40]):
                self.assertIn("CANONICAL_RUN_DIR", wrapper)
                self.assertIn("TDD_PROMPT_GUIDANCE", wrapper)
                self.assertIn("PROJECT TDD CONTRACT", wrapper)
                self.assertIn("build-test.md", wrapper)
                self.assertIn("phase_evidence", wrapper)


if __name__ == "__main__":
    unittest.main()

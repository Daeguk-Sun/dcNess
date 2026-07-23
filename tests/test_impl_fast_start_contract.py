"""Fast-start and autonomous recovery contracts for /impl and /impl-loop."""
from __future__ import annotations

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

        self.assertIn("첫 진행 이정표", skill)
        self.assertIn("RED", skill)
        self.assertNotIn("impl-preview", skill)
        self.assertNotIn("boundary-suggestions", skill)
        self.assertNotIn("dcness-tdd-hooks\" status", skill)

    def test_impl_loop_launches_worker_in_background_without_repeat_preflight(self) -> None:
        skill = self.read("skills/impl-loop/SKILL.md")

        self.assertIn("run_in_background", skill)
        self.assertIn("같은 provider", skill)
        self.assertIn("같은 workspace", skill)
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


if __name__ == "__main__":
    unittest.main()

"""Close-path fail-fast validation contracts for issue #1194."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import statistics
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from harness import ledger, session_state
from harness.chain_view import ChainTask, substeps_for
from harness.hooks import (
    _maybe_emit_continuation_signal,
    _strict_conveyor_gate_message,
)


ROOT = Path(__file__).resolve().parents[1]
SID = "sid-close-sequence"
RID = "run-1194abcd"
HEAD = "a" * 40
TREE = "b" * 40


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class CloseValidationSequenceStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        session_state.transition(
            SID,
            "run_started",
            run_id=RID,
            base_dir=self.base,
            entry_point="impl",
            lane="lite",
            acceptance_required=True,
        )

    def _start(self, agent: str, mode: str | None) -> None:
        session_state.transition(
            SID,
            "step_started",
            run_id=RID,
            base_dir=self.base,
            agent=agent,
            mode=mode,
            candidate_head=HEAD,
            candidate_tree=TREE,
        )

    def _complete(
        self,
        agent: str,
        mode: str | None,
        conclusion: str = "PASS",
    ) -> None:
        prose = f"{agent} complete\n\n{conclusion}\n"
        path = (
            session_state.run_dir(SID, RID, base_dir=self.base)
            / f"{agent}-{mode or 'default'}.md"
        )
        path.write_text(prose, encoding="utf-8")
        session_state.transition(
            SID,
            "step_completed",
            run_id=RID,
            base_dir=self.base,
            agent=agent,
            mode=mode,
            prose=prose,
            prose_path=path,
            strict_identity=True,
        )

    def _acceptance_gate(
        self,
        *,
        head: str = HEAD,
        tree: str = TREE,
    ) -> str | None:
        return session_state.evaluate_order_gate_for_step(
            SID,
            RID,
            "product-acceptance",
            "EPIC_ACCEPTANCE",
            base_dir=self.base,
            candidate_head=head,
            candidate_tree=tree,
        )

    def test_acceptance_is_blocked_until_validator_passes(self) -> None:
        self.assertIn("impl-validator 완료 뒤", self._acceptance_gate() or "")

        self._start("impl-validator", None)
        self._complete("impl-validator", None, "FAIL")

        message = self._acceptance_gate()
        self.assertIsNotNone(message)
        self.assertIn("terminal PASS가 아닙니다", message)

    def test_stop_after_validator_fail_does_not_request_acceptance(self) -> None:
        self._start("impl-validator", None)
        self._complete("impl-validator", None, "FAIL")

        slot = session_state.read_live(SID, base_dir=self.base)["active_runs"][RID]
        stdout = StringIO()
        with redirect_stdout(stdout):
            blocked = _maybe_emit_continuation_signal(
                sid=SID,
                rid=RID,
                slot=slot,
                active={RID: slot},
                last_agent="impl-validator",
                last_mode=None,
                base_dir=self.base,
            )

        self.assertTrue(blocked)
        reason = json.loads(stdout.getvalue())["reason"]
        self.assertIn("impl-validator is not terminal PASS", reason)
        self.assertIn("product-acceptance를 시작하지 말고", reason)

    def test_acceptance_starts_after_validator_pass_on_same_candidate(self) -> None:
        self._start("impl-validator", None)
        self._complete("impl-validator", None)

        self.assertIsNone(self._acceptance_gate())
        self._start("product-acceptance", "EPIC_ACCEPTANCE")
        current = session_state.read_live(SID, base_dir=self.base)["active_runs"][
            RID
        ]["current_step"]
        self.assertEqual(
            (current["candidate_head"], current["candidate_tree"]),
            (HEAD, TREE),
        )

        completed = ledger.read_step_completed(SID, RID, base_dir=self.base)
        self.assertEqual(
            (completed[-1]["candidate_head"], completed[-1]["candidate_tree"]),
            (HEAD, TREE),
        )

    def test_acceptance_rejects_validator_candidate_drift(self) -> None:
        self._start("impl-validator", None)
        self._complete("impl-validator", None)

        message = self._acceptance_gate(head="c" * 40)
        self.assertIsNotNone(message)
        self.assertIn("HEAD/tree가 다릅니다", message)

    def test_stop_after_validator_pass_requests_acceptance(self) -> None:
        self._start("impl-validator", None)
        self._complete("impl-validator", None)

        slot = session_state.read_live(SID, base_dir=self.base)["active_runs"][RID]
        stdout = StringIO()
        with redirect_stdout(stdout):
            blocked = _maybe_emit_continuation_signal(
                sid=SID,
                rid=RID,
                slot=slot,
                active={RID: slot},
                last_agent="impl-validator",
                last_mode=None,
                base_dir=self.base,
            )

        self.assertTrue(blocked)
        reason = json.loads(stdout.getvalue())["reason"]
        self.assertIn("product-acceptance", reason)
        self.assertIn("required next receipt missing", reason)

    def test_stop_join_allows_close_after_sequential_passes(self) -> None:
        self._start("impl-validator", None)
        self._complete("impl-validator", None)
        self.assertIsNone(self._acceptance_gate())
        self._start("product-acceptance", "STORY_ACCEPTANCE")
        self._complete("product-acceptance", "STORY_ACCEPTANCE")

        slot = session_state.read_live(SID, base_dir=self.base)["active_runs"][RID]
        with patch(
            "harness.hooks._current_tracked_candidate",
            return_value=(HEAD, TREE, True),
        ):
            self.assertFalse(
                _maybe_emit_continuation_signal(
                    sid=SID,
                    rid=RID,
                    slot=slot,
                    active={RID: slot},
                    last_agent="product-acceptance",
                    last_mode="STORY_ACCEPTANCE",
                    base_dir=self.base,
                )
            )

    def test_stop_join_rejects_tree_change_after_both_receipts(self) -> None:
        self._start("impl-validator", None)
        self._complete("impl-validator", None)
        self._start("product-acceptance", "STORY_ACCEPTANCE")
        self._complete("product-acceptance", "STORY_ACCEPTANCE")

        slot = session_state.read_live(SID, base_dir=self.base)["active_runs"][RID]
        stdout = StringIO()
        with patch(
            "harness.hooks._current_tracked_candidate",
            return_value=("c" * 40, "d" * 40, True),
        ), redirect_stdout(stdout):
            blocked = _maybe_emit_continuation_signal(
                sid=SID,
                rid=RID,
                slot=slot,
                active={RID: slot},
                last_agent="product-acceptance",
                last_mode="STORY_ACCEPTANCE",
                base_dir=self.base,
            )

        self.assertTrue(blocked)
        self.assertIn("changed after", json.loads(stdout.getvalue())["reason"])

    def test_close_sequence_requires_explicit_frozen_begin_step(self) -> None:
        slot = session_state.read_live(SID, base_dir=self.base)["active_runs"][RID]

        message = _strict_conveyor_gate_message(
            sid=SID,
            rid=RID,
            base_dir=self.base,
            slot=slot,
            subagent="impl-validator",
            mode=None,
            allow_implicit_start=False,
        )

        self.assertIsNotNone(message)
        self.assertIn("begin-step 누락", message)


class CloseValidationSequenceDocumentationTests(unittest.TestCase):
    def test_close_progress_exposes_one_fail_fast_sequence(self) -> None:
        story = ChainTask(name="final", engine="build-worker", closes="story")
        epic = ChainTask(name="final", engine="build-worker", closes="epic")

        self.assertEqual(
            substeps_for(story),
            ["build-worker", "validation-sequence:STORY"],
        )
        self.assertEqual(
            substeps_for(epic),
            ["build-worker", "validation-sequence:EPIC"],
        )

    def test_impl_loop_freezes_before_sequential_fail_fast_validation(self) -> None:
        finish = read("skills/impl-loop/impl-loop-finish.md")
        finish = finish[finish.index("마감 순서는 다음과 같다.") :]

        sequence = (
            "JOURNEY_CONVERGENCE",
            "final mutation owner",
            "candidate freeze",
            "holistic `impl-validator`",
            "validator가 terminal `PASS`일 때만",
            "target GitHub issue AC close audit",
        )
        positions = [finish.index(item) for item in sequence]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("두 Agent는 한 세션에서 동시에 호출하지 않는다", finish)
        self.assertNotIn(
            "module-architect",
            finish[finish.index("## Cartography freshness") :],
        )

    def test_route_only_refresh_is_owned_without_agent_regression(self) -> None:
        for path in (
            "skills/impl/impl-finish.md",
            "skills/impl/impl-routing.md",
            "skills/impl-loop/impl-loop-finish.md",
        ):
            with self.subTest(path=path):
                text = read(path)
                self.assertIn("final mutation owner", text)
                self.assertIn("route/state/as-built", text)
                self.assertNotIn("begin-step module-architect", text)
                self.assertNotIn("end-step module-architect", text)

    def test_review_is_holistic_and_acceptance_reuses_same_tree_gates(self) -> None:
        validators = (
            read("docs/plugin/agents/impl-validator/impl-validator-agent.md"),
            read("codex/skills/dcness-impl-validator/SKILL.md"),
        )
        for validator in validators:
            self.assertIn("holistic", validator)
            self.assertIn("fixed task/commit fan-out", validator)
            self.assertIn("실제 unresolved high-risk", validator)

        acceptance = read(
            "docs/plugin/agents/product-acceptance/product-acceptance-agent.md"
        )
        self.assertIn("same-tree terminal evidence", acceptance)
        self.assertIn("full unit suite를 다시 실행하지 않는다", acceptance)
        self.assertIn("sealed", acceptance)

    def test_recovery_invalidates_only_evidence_affected_by_tree_change(self) -> None:
        finish = read("skills/impl-loop/impl-loop-finish.md")

        self.assertIn("code/harness", finish)
        self.assertIn("same implementation owner", finish)
        self.assertIn("device/external transient", finish)
        self.assertIn("validator PASS를 유지", finish)
        self.assertIn("acceptance만 재실행", finish)

    def test_three_close_replays_reduce_median_time_without_quality_loss(self) -> None:
        metadata = json.loads(read("evals/impl-fast-start-metadata.json"))
        analysis = metadata["close_path_convergence_analysis"]
        trials = analysis["paired_replays"]

        self.assertGreaterEqual(len(trials), 3)
        self.assertGreaterEqual(
            statistics.median(
                trial["wall_clock_reduction_percent"] for trial in trials
            ),
            30,
        )
        for trial in trials:
            with self.subTest(trial=trial["trial"]):
                self.assertTrue(trial["quality_contract_preserved"])
                self.assertLess(
                    trial["optimized_main_blocking_requests"],
                    trial["baseline_main_blocking_requests"],
                )
                self.assertLess(
                    trial["optimized_projected_total_input_tokens"],
                    trial["baseline_all_total_input_tokens"],
                )


if __name__ == "__main__":
    unittest.main()

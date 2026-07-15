from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from harness import ledger
from harness import session_state as state


SID = "ledger-contract-session"
RID = "run-abcd1234"


class LedgerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        state.transition(
            SID,
            "run_started",
            run_id=RID,
            base_dir=self.base,
            entry_point="impl",
            lane="lite",
        )

    def test_catalog_separates_lifecycle_from_manual_checkpoints(self) -> None:
        self.assertEqual(
            ledger.LIFECYCLE_EVENT_TYPES,
            {"run_started", "step_started", "step_completed", "run_finished"},
        )
        self.assertTrue(ledger.LIFECYCLE_EVENT_TYPES.isdisjoint(ledger.MANUAL_EVENT_TYPES))
        self.assertEqual(
            ledger.EVENT_TYPES,
            ledger.LIFECYCLE_EVENT_TYPES | ledger.MANUAL_EVENT_TYPES,
        )
        self.assertFalse(hasattr(ledger, "append_event"))
        self.assertFalse(hasattr(ledger, "append_step_completed"))

    def test_receipt_keeps_prose_integrity_and_evidence_pointers(self) -> None:
        prose = "## 결론\nMUST FIX: `src/state.py` 보정\nhttps://example.test/pull/7"
        path = self.base / "validator.md"
        path.write_text(prose, encoding="utf-8")
        receipt = ledger.build_receipt(
            "impl-validator",
            "CODE_VALIDATION",
            "PROSE_LOGGED",
            prose,
            path,
            provider="codex-headless",
        )
        self.assertEqual(receipt["sha256"], ledger.sha256_text(prose))
        self.assertTrue(receipt["must_fix"])
        self.assertIn("src/state.py", receipt["evidence_paths"])
        self.assertEqual(receipt["provider"], "codex-headless")
        self.assertIn("root-cause", receipt["next_action"])

    def test_transition_preserves_append_order_and_manual_fields(self) -> None:
        state.transition(
            SID,
            "ledger_checkpoint",
            run_id=RID,
            base_dir=self.base,
            event="pr_created",
            pr_number=77,
            url="https://example.test/pull/77",
        )
        state.transition(
            SID,
            "ledger_checkpoint",
            run_id=RID,
            base_dir=self.base,
            event="task_completed",
            issue_num=1145,
        )
        events = ledger.read_events(SID, RID, base_dir=self.base)
        self.assertEqual([event["event"] for event in events], ["run_started", "pr_created", "task_completed"])
        self.assertEqual(events[1]["pr_number"], 77)

    def test_step_receipt_round_trip_and_status(self) -> None:
        state.transition(
            SID,
            "step_started",
            run_id=RID,
            base_dir=self.base,
            agent="impl-validator",
            mode=None,
        )
        prose_path = state.run_dir(SID, RID, base_dir=self.base) / "impl-validator.md"
        prose_path.write_text("검증 완료\n\nPASS", encoding="utf-8")
        state.transition(
            SID,
            "step_completed",
            run_id=RID,
            base_dir=self.base,
            agent="impl-validator",
            mode=None,
            enum="PROSE_LOGGED",
            prose="검증 완료\n\nPASS",
            prose_path=prose_path,
        )
        steps = ledger.read_step_completed(SID, RID, base_dir=self.base)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["agent"], "impl-validator")
        status = ledger.render_status(SID, RID, base_dir=self.base)
        self.assertIn("phase: validate", status)
        self.assertIn(str(prose_path), status)

    def test_analysis_reader_uses_run_directory_without_a_second_schema(self) -> None:
        run_path = state.run_dir(SID, RID, base_dir=self.base)
        self.assertEqual(ledger.read_events_at(run_path), ledger.read_events(SID, RID, base_dir=self.base))
        source = Path(ledger.__file__).read_text(encoding="utf-8")
        self.assertNotIn(".steps.jsonl", source)
        self.assertNotIn("migration", source.lower())


if __name__ == "__main__":
    unittest.main()

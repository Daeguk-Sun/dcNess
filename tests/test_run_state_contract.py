from __future__ import annotations

import json
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from harness import ledger, session_state


SID = "contract-session"
RID = "run-a1b2c3d4"


class CurrentStateContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def test_lifecycle_uses_one_transition_for_state_and_ledger(self) -> None:
        session_state.transition(
            SID,
            "run_started",
            run_id=RID,
            base_dir=self.base,
            entry_point="impl",
            lane="lite",
        )
        session_state.transition(
            SID,
            "step_started",
            run_id=RID,
            base_dir=self.base,
            agent="build-worker",
            mode=None,
        )
        prose = "구현 결과\n\nPASS"
        prose_path = session_state.run_dir(SID, RID, base_dir=self.base) / "build-worker.md"
        prose_path.write_text(prose, encoding="utf-8")
        session_state.transition(
            SID,
            "step_completed",
            run_id=RID,
            base_dir=self.base,
            agent="build-worker",
            mode=None,
            enum="PROSE_LOGGED",
            prose=prose,
            prose_path=prose_path,
        )
        session_state.transition(
            SID,
            "run_completed",
            run_id=RID,
            base_dir=self.base,
        )
        session_state.transition(
            SID,
            "run_completed",
            run_id=RID,
            base_dir=self.base,
        )

        slot = session_state.read_live(SID, base_dir=self.base)["active_runs"][RID]
        self.assertIsNotNone(slot["completed_at"])
        self.assertIsNone(slot["current_step"])
        self.assertEqual(
            [event["event"] for event in ledger.read_events(SID, RID, base_dir=self.base)],
            ["run_started", "step_started", "step_completed", "run_finished"],
        )

    def test_parallel_pending_transitions_do_not_lose_slots(self) -> None:
        session_state.transition(
            SID,
            "run_started",
            run_id=RID,
            base_dir=self.base,
            entry_point="impl",
            lane="lite",
        )
        barrier = threading.Barrier(3)

        def add(tool_use_id: str) -> None:
            barrier.wait()
            session_state.transition(
                SID,
                "pending_agent_set",
                run_id=RID,
                base_dir=self.base,
                tool_use_id=tool_use_id,
                sub_type="build-worker",
                mode=None,
            )

        threads = [threading.Thread(target=add, args=(tool_id,)) for tool_id in ("tool-1", "tool-2")]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()

        pending = session_state.read_live(SID, base_dir=self.base)["active_runs"][RID][
            "pending_agents"
        ]
        self.assertEqual(set(pending), {"tool-1", "tool-2"})

    def test_corrupt_or_partial_current_state_fails_with_recreation_help(self) -> None:
        path = session_state.live_path(SID, base_dir=self.base)
        path.parent.mkdir(parents=True)
        cases = ("{broken", json.dumps({"_meta": {"version": 1, "sessionId": SID}}))
        for raw in cases:
            with self.subTest(raw=raw):
                path.write_text(raw, encoding="utf-8")
                with self.assertRaisesRegex(session_state.StateFormatError, "recreate"):
                    session_state.read_live(SID, base_dir=self.base)

    def test_corrupt_current_ledger_fails_instead_of_skipping(self) -> None:
        session_state.transition(
            SID,
            "run_started",
            run_id=RID,
            base_dir=self.base,
            entry_point="impl",
            lane="lite",
        )
        with ledger.ledger_path(SID, RID, base_dir=self.base).open(
            "a", encoding="utf-8"
        ) as handle:
            handle.write("{truncated\n")
        with self.assertRaisesRegex(session_state.StateFormatError, "recreate"):
            ledger.read_events(SID, RID, base_dir=self.base)

    def test_tampered_receipt_is_an_explicit_current_state_failure(self) -> None:
        session_state.transition(
            SID,
            "run_started",
            run_id=RID,
            base_dir=self.base,
            entry_point="impl",
            lane="lite",
        )
        prose_path = session_state.run_dir(SID, RID, base_dir=self.base) / "validator.md"
        prose_path.write_text("PASS", encoding="utf-8")
        session_state.transition(
            SID,
            "step_completed",
            run_id=RID,
            base_dir=self.base,
            agent="impl-validator",
            mode=None,
            enum="PROSE_LOGGED",
            prose="PASS",
            prose_path=prose_path,
        )
        prose_path.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(session_state.StateFormatError, "receipt"):
            ledger.read_step_completed(SID, RID, base_dir=self.base)


if __name__ == "__main__":
    unittest.main()

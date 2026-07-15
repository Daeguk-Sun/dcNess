from __future__ import annotations

import json
import subprocess
import sys
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
            agent="dcness:build-worker",
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
            agent="dcness:build-worker",
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
        events = ledger.read_events(SID, RID, base_dir=self.base)
        self.assertEqual(
            [event["event"] for event in events],
            ["run_started", "step_started", "step_completed", "run_finished"],
        )
        self.assertEqual(
            [event["agent"] for event in events[1:3]],
            ["build-worker", "build-worker"],
        )

    def test_removed_writer_names_are_absent_in_a_fresh_process(self) -> None:
        """Regression fixtures must not recreate the removed product API surface."""
        probe = """
from harness import ledger, session_state

removed = {
    "session_state": [
        name for name in (
            "start_run", "update_current_step", "complete_run", "update_live",
            "mark_run_blocked", "set_pending_agent", "clear_pending_agent",
            "clear_current_step",
        ) if hasattr(session_state, name)
    ],
    "ledger": [
        name for name in ("append_event", "append_step_completed", "_append_event_raw")
        if hasattr(ledger, name)
    ],
}
if any(removed.values()):
    raise SystemExit(str(removed))
"""
        result = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

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

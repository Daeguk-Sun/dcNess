"""Minimal guard/eval receipt contracts."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from harness.guard_telemetry import (
    TELEMETRY_NAME,
    append_event,
    read_events,
    record_eval_case_result,
    record_guard_hit,
)
from harness.session_state import generate_run_id, run_dir


SID = "guard-telemetry-sid"


class ReceiptContractTests(unittest.TestCase):
    def test_guard_hit_roundtrip_prefers_run_dir(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            run_id = generate_run_id()
            record_guard_hit(
                "file-guard",
                category="write_boundary",
                detail="blocked\npath",
                source="plugin_hook",
                session_id=SID,
                run_id=run_id,
                base_dir=base,
            )

            target = run_dir(SID, run_id, base_dir=base) / TELEMETRY_NAME
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            events = read_events(base_dir=base)
            self.assertEqual([row["kind"] for row in events], ["telemetry_epoch", "guard_hit"])
            self.assertEqual(events[-1]["detail"], "blocked path")
            self.assertEqual(events[-1]["run_id"], run_id)

    def test_guard_hit_without_run_uses_project_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record_guard_hit("git-pre-commit", category="main_block", cwd=root)

            self.assertTrue((root / ".claude/harness-state" / TELEMETRY_NAME).is_file())
            self.assertEqual(read_events(cwd=root)[-1]["guard"], "git-pre-commit")

    def test_eval_is_a_receipt_not_a_runtime_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record_eval_case_result(
                "headless-prose-quality",
                passed=False,
                llm_turns=2,
                failure_stage="judge",
                failure_detail="failed\ncleanly",
                cwd=root,
            )

            event = read_events(cwd=root)[-1]
            self.assertEqual(event["kind"], "eval_case_result")
            self.assertEqual(event["llm_turns"], 2)
            self.assertEqual(event["failure_detail"], "failed cleanly")

    def test_reader_tolerates_invalid_rows_and_applies_window_and_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / ".claude/harness-state" / TELEMETRY_NAME
            target.parent.mkdir(parents=True)
            old = datetime.now(timezone.utc) - timedelta(days=20)
            target.write_text(
                "not-json\n"
                + json.dumps({"kind": "guard_hit", "ts": old.isoformat()})
                + "\n"
                + json.dumps({"kind": "guard_hit", "ts": datetime.now(timezone.utc).isoformat()})
                + "\n",
                encoding="utf-8",
            )

            self.assertEqual(len(read_events(cwd=root, since_days=7)), 1)
            self.assertEqual(read_events(cwd=root, limit=0), [])
            self.assertEqual(len(read_events(cwd=root, limit=1)), 1)

    def test_record_hit_cli_preserves_public_exit_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            result = subprocess.run(
                [
                    "python3.11",
                    "-m",
                    "harness.guard_telemetry",
                    "record-hit",
                    "--guard",
                    "tdd-guard",
                    "--base-dir",
                    str(base),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(read_events(base_dir=base)[-1]["guard"], "tdd-guard")


if __name__ == "__main__":
    unittest.main()

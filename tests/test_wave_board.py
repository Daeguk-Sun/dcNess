"""wave board — peer /impl-loop task claim board tests (#641)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from harness.wave_board import ClaimConflict, WaveBoard


REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_impl(root: Path, rel: str, *, story: str = "1", task_index: str = "1/2") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"story: {story}\n"
        f"task_index: {task_index}\n"
        "depends_on: []\n"
        "---\n\n"
        "## Scope\n\n"
        "### 수정 허용\n\n"
        f"- src/{path.stem}.py\n",
        encoding="utf-8",
    )
    return path


class WaveBoardClaimTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.board = WaveBoard(self.root)
        self.impl = _write_impl(
            self.root,
            "docs/milestones/v01/epics/epic-01-demo/impl/01-first.md",
        )

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_unregistered_impl_uses_existing_serial_flow(self) -> None:
        result = self.board.claim_if_registered(
            self.impl,
            session_id="s1",
            run_id="r1",
            worktree="/tmp/wt",
            branch="feature/demo",
        )

        self.assertEqual(result.mode, "serial")
        self.assertFalse(result.claimed)
        self.assertEqual(self.board.status_records(), [])

    def test_registered_impl_claim_is_atomic_and_blocks_duplicate(self) -> None:
        self.board.register([self.impl], plan_id="wave-demo")

        first = self.board.claim_if_registered(
            self.impl,
            session_id="s1",
            run_id="r1",
            worktree="/tmp/wt-a",
            branch="feature/a",
        )

        self.assertEqual(first.mode, "peer")
        self.assertTrue(first.claimed)
        self.assertEqual(first.record["state"], "claimed")

        with self.assertRaises(ClaimConflict) as ctx:
            self.board.claim_if_registered(
                self.impl,
                session_id="s2",
                run_id="r2",
                worktree="/tmp/wt-b",
                branch="feature/b",
            )

        self.assertFalse(ctx.exception.stale)
        self.assertIn("already claimed", str(ctx.exception))

    def test_completed_claim_blocks_later_session(self) -> None:
        self.board.register([self.impl])
        first = self.board.claim_if_registered(
            self.impl,
            session_id="s1",
            run_id="r1",
            worktree="/tmp/wt-a",
            branch="feature/a",
        )
        self.board.complete(first.key, pr_number=123, url="https://example/pr/123")

        with self.assertRaises(ClaimConflict) as ctx:
            self.board.claim_if_registered(
                self.impl,
                session_id="s2",
                run_id="r2",
                worktree="/tmp/wt-b",
                branch="feature/b",
            )

        self.assertIn("already completed", str(ctx.exception))
        status = self.board.status_records()
        self.assertEqual(status[0]["state"], "completed")
        self.assertEqual(status[0]["pr_number"], 123)

    def test_heartbeat_updates_claim_without_clobbering_run_identity(self) -> None:
        self.board.register([self.impl])
        claim = self.board.claim_if_registered(
            self.impl,
            session_id="s1",
            run_id="r1",
            worktree="/tmp/wt-a",
            branch="feature/a",
        )

        self.board.heartbeat(claim.key, session_id="s1", run_id="r1")

        record = self.board.get_record(claim.key)
        self.assertEqual(record["session_id"], "s1")
        self.assertEqual(record["run_id"], "r1")
        self.assertIn("heartbeat_at", record)
        self.assertIn("heartbeat_pid", record)

    def test_stale_claim_requires_explicit_reclaim_before_second_claim(self) -> None:
        now = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)
        later = now + timedelta(hours=3)
        self.board.register([self.impl])
        claim = self.board.claim_if_registered(
            self.impl,
            session_id="s1",
            run_id="r1",
            worktree="/tmp/wt-a",
            branch="feature/a",
            now=now,
        )

        with self.assertRaises(ClaimConflict) as ctx:
            self.board.claim_if_registered(
                self.impl,
                session_id="s2",
                run_id="r2",
                worktree="/tmp/wt-b",
                branch="feature/b",
                now=later,
                stale_after_seconds=3600,
            )
        self.assertTrue(ctx.exception.stale)

        reclaimed = self.board.reclaim(claim.key, reason="user confirmed stale")
        self.assertEqual(reclaimed["state"], "stale_reclaimed")

        second = self.board.claim_if_registered(
            self.impl,
            session_id="s2",
            run_id="r2",
            worktree="/tmp/wt-b",
            branch="feature/b",
            now=later,
        )
        self.assertTrue(second.claimed)
        self.assertEqual(second.record["session_id"], "s2")

    def test_release_state_frees_claim_but_failed_state_requires_reclaim(self) -> None:
        self.board.register([self.impl])
        first = self.board.claim_if_registered(
            self.impl,
            session_id="s1",
            run_id="r1",
            worktree="/tmp/wt-a",
            branch="feature/a",
        )

        released = self.board.release(first.key, state="released", reason="user cancelled")
        self.assertEqual(released["state"], "released")

        second = self.board.claim_if_registered(
            self.impl,
            session_id="s2",
            run_id="r2",
            worktree="/tmp/wt-b",
            branch="feature/b",
        )
        self.assertTrue(second.claimed)

        failed = self.board.release(second.key, state="failed", reason="ci failed")
        self.assertEqual(failed["state"], "failed")
        with self.assertRaises(ClaimConflict) as ctx:
            self.board.claim_if_registered(
                self.impl,
                session_id="s3",
                run_id="r3",
                worktree="/tmp/wt-c",
                branch="feature/c",
            )
        self.assertIn("failed claim requires explicit reclaim", str(ctx.exception))

    def test_status_text_exposes_human_claim_fields(self) -> None:
        self.board.register([self.impl], plan_id="wave-demo")
        self.board.claim_if_registered(
            self.impl,
            session_id="s1",
            run_id="r1",
            worktree="/tmp/wt-a",
            branch="feature/a",
        )

        text = self.board.status_text()

        self.assertIn("01-first.md", text)
        self.assertIn("session=s1", text)
        self.assertIn("run=r1", text)
        self.assertIn("worktree=/tmp/wt-a", text)
        self.assertIn("state=claimed", text)

    def test_record_files_are_json_per_impl_not_shared_between_runs(self) -> None:
        other = _write_impl(
            self.root,
            "docs/milestones/v01/epics/epic-01-demo/impl/02-second.md",
            task_index="2/2",
        )
        self.board.register([self.impl, other])
        first = self.board.claim_if_registered(
            self.impl,
            session_id="s1",
            run_id="r1",
            worktree="/tmp/wt-a",
            branch="feature/a",
        )
        second = self.board.claim_if_registered(
            other,
            session_id="s2",
            run_id="r2",
            worktree="/tmp/wt-b",
            branch="feature/b",
        )

        self.assertNotEqual(first.key, second.key)
        files = sorted(self.board.claims_dir.glob("*.json"))
        self.assertEqual(len(files), 2)
        payloads = [json.loads(p.read_text(encoding="utf-8")) for p in files]
        self.assertEqual({p["run_id"] for p in payloads}, {"r1", "r2"})


class WaveBoardCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.impl = _write_impl(
            self.root,
            "docs/milestones/v01/epics/epic-01-demo/impl/01-first.md",
        )

    def tearDown(self) -> None:
        self._td.cleanup()

    def _run_cli(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "harness.session_state", *args],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
            timeout=10,
        )

    def test_wave_plan_register_then_claim_enters_peer_mode(self) -> None:
        other = _write_impl(
            self.root,
            "docs/milestones/v01/epics/epic-01-demo/impl/02-second.md",
            task_index="2/2",
        )
        plan = self._run_cli(["wave-plan", "--register", str(self.impl), str(other)])
        self.assertEqual(plan.returncode, 0, plan.stderr)
        plan_payload = json.loads(plan.stdout)
        self.assertEqual(plan_payload["registered_count"], 2)
        self.assertEqual(plan_payload["execution_model"], "independent_interactive_sessions")

        claim = self._run_cli(
            [
                "wave-claim",
                str(self.impl),
                "--session-id",
                "s1",
                "--run-id",
                "r1",
                "--worktree",
                "/tmp/wt-a",
                "--branch",
                "feature/a",
            ]
        )

        self.assertEqual(claim.returncode, 0, claim.stderr)
        payload = json.loads(claim.stdout)
        self.assertEqual(payload["mode"], "peer")
        self.assertTrue(payload["claimed"])

    def test_wave_plan_register_only_parallel_step_tasks(self) -> None:
        serial = _write_impl(
            self.root,
            "docs/milestones/v01/epics/epic-01-demo/impl/00-serial.md",
            task_index="1/3",
        )
        independent_a = _write_impl(
            self.root,
            "docs/milestones/v01/epics/epic-01-demo/impl/01-first.md",
            task_index="2/3",
        )
        independent_b = _write_impl(
            self.root,
            "docs/milestones/v01/epics/epic-01-demo/impl/02-second.md",
            task_index="3/3",
        )
        serial.write_text(
            serial.read_text(encoding="utf-8").replace(
                "depends_on: []",
                "depends_on: []\nparallel: serial",
            ),
            encoding="utf-8",
        )

        plan = self._run_cli(
            [
                "wave-plan",
                "--register",
                str(serial),
                str(independent_a),
                str(independent_b),
            ]
        )

        self.assertEqual(plan.returncode, 0, plan.stderr)
        payload = json.loads(plan.stdout)
        registered = {Path(r["canonical_impl_path"]).name for r in payload["registered"]}
        self.assertEqual(registered, {"01-first.md", "02-second.md"})
        self.assertEqual(payload["registered_count"], 2)

    def test_wave_claim_unregistered_path_reports_serial_mode(self) -> None:
        claim = self._run_cli(
            [
                "wave-claim",
                str(self.impl),
                "--session-id",
                "s1",
                "--run-id",
                "r1",
                "--worktree",
                "/tmp/wt-a",
                "--branch",
                "feature/a",
            ]
        )

        self.assertEqual(claim.returncode, 0, claim.stderr)
        payload = json.loads(claim.stdout)
        self.assertEqual(payload["mode"], "serial")
        self.assertFalse(payload["claimed"])


if __name__ == "__main__":
    unittest.main()

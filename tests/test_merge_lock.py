"""merge lock — peer /impl-loop finalize gate tests (#641)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from harness.merge_lock import LockBusy, MergeLock, check_merge_order
from harness.merge_lock import external_git_completed
from harness.wave_board import WaveBoard


REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_impl(root: Path, name: str, *, story: str = "1", task_index: str = "1/2") -> Path:
    impl_dir = root / "docs/milestones/v01/epics/epic-01-demo/impl"
    impl_dir.mkdir(parents=True, exist_ok=True)
    path = impl_dir / name
    path.write_text(
        "---\n"
        f"story: {story}\n"
        f"task_index: {task_index}\n"
        "depends_on: []\n"
        "---\n\n"
        "## Scope\n\n"
        "### 수정 허용\n\n"
        f"- src/{name}.py\n",
        encoding="utf-8",
    )
    return path


class MergeLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_repo_level_lock_serializes_finalize(self) -> None:
        lock = MergeLock(self.root)
        first = lock.acquire(owner="session-a", branch="feature/a", pr_number=101)

        with self.assertRaises(LockBusy):
            lock.acquire(owner="session-b", branch="feature/b", pr_number=102)

        lock.release(first.token, state="released")
        second = lock.acquire(owner="session-b", branch="feature/b", pr_number=102)
        self.assertNotEqual(first.token, second.token)
        lock.release(second.token, state="released")

    def test_tokenless_break_releases_only_stale_lock(self) -> None:
        now = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)
        later = now + timedelta(hours=3)
        lock = MergeLock(self.root)
        first = lock.acquire(
            owner="session-a",
            branch="feature/a",
            pr_number=101,
            now=now,
        )

        with self.assertRaises(LockBusy):
            lock.break_stale(owner="operator", stale_after_seconds=4 * 60 * 60, now=later)
        self.assertTrue(lock.lock_path.exists())

        broken = lock.break_stale(
            owner="operator",
            stale_after_seconds=60 * 60,
            reason="session was SIGKILLed",
            now=later,
        )

        self.assertEqual(broken["state"], "stale_broken")
        self.assertEqual(broken["token"], first.token)
        self.assertEqual(broken["broken_by"], "operator")
        self.assertFalse(lock.lock_path.exists())
        second = lock.acquire(owner="session-b", branch="feature/b", pr_number=102)
        self.assertNotEqual(first.token, second.token)

    def test_order_check_uses_all_prior_sibling_tasks_not_only_claimed_tasks(self) -> None:
        first = _write_impl(self.root, "01-first.md", story="1", task_index="1/2")
        second = _write_impl(self.root, "02-second.md", story="1", task_index="2/2")
        board = WaveBoard(self.root)
        board.register([second])
        board.claim_if_registered(
            second,
            session_id="s2",
            run_id="r2",
            worktree="/tmp/wt-b",
            branch="feature/b",
        )

        result = check_merge_order(
            board,
            second,
            external_completed=lambda path: False,
        )

        self.assertFalse(result.allowed)
        self.assertEqual(result.blocked_prior_paths, (str(first.resolve()),))
        self.assertIn("01-first.md", result.reason)

    def test_prior_task_external_evidence_allows_order(self) -> None:
        first = _write_impl(self.root, "01-first.md", story="1", task_index="1/2")
        second = _write_impl(self.root, "02-second.md", story="1", task_index="2/2")
        board = WaveBoard(self.root)
        board.register([second])
        board.claim_if_registered(
            second,
            session_id="s2",
            run_id="r2",
            worktree="/tmp/wt-b",
            branch="feature/b",
        )

        result = check_merge_order(
            board,
            second,
            external_completed=lambda path: path == str(first.resolve()),
        )

        self.assertTrue(result.allowed)
        self.assertEqual(result.blocked_prior_paths, ())

    def test_prior_task_completed_on_board_allows_order(self) -> None:
        first = _write_impl(self.root, "01-first.md", story="1", task_index="1/2")
        second = _write_impl(self.root, "02-second.md", story="1", task_index="2/2")
        board = WaveBoard(self.root)
        board.register([first, second])
        first_claim = board.claim_if_registered(
            first,
            session_id="s1",
            run_id="r1",
            worktree="/tmp/wt-a",
            branch="feature/a",
        )
        board.complete(first_claim.key, pr_number=101, url="https://example/pr/101")

        result = check_merge_order(
            board,
            second,
            external_completed=lambda path: False,
        )

        self.assertTrue(result.allowed)

    def test_common_task_skips_story_order_gate(self) -> None:
        common = _write_impl(self.root, "01-common.md", story="공통", task_index="—")
        board = WaveBoard(self.root)

        result = check_merge_order(
            board,
            common,
            external_completed=lambda path: False,
        )

        self.assertTrue(result.allowed)
        self.assertEqual(result.reason, "story order gate not applicable")


class MergeLockCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.impl = _write_impl(self.root, "01-first.md", task_index="1/2")
        self.other = _write_impl(self.root, "02-second.md", task_index="2/2")

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

    def test_merge_lock_release_failed_marks_peer_claim_failed(self) -> None:
        register = self._run_cli(["wave-plan", "--register", str(self.impl), str(self.other)])
        self.assertEqual(register.returncode, 0, register.stderr)

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

        acquired = self._run_cli(["merge-lock", "acquire", "--branch", "feature/a", "--pr", "101"])
        self.assertEqual(acquired.returncode, 0, acquired.stderr)
        acquire_payload = json.loads(acquired.stdout)
        self.assertEqual(acquire_payload["mode"], "peer")

        released = self._run_cli(
            [
                "merge-lock",
                "release",
                "--token",
                acquire_payload["token"],
                "--claim-key",
                acquire_payload["claim_key"],
                "--state",
                "failed",
                "--reason",
                "ci failed",
            ]
        )

        self.assertEqual(released.returncode, 0, released.stderr)
        status = self._run_cli(["wave-status", "--json"])
        self.assertEqual(status.returncode, 0, status.stderr)
        records = json.loads(status.stdout)["records"]
        self.assertEqual(records[0]["state"], "failed")
        self.assertEqual(records[0]["reason"], "ci failed")

    def test_failed_claim_blocks_finalize_until_explicit_reclaim(self) -> None:
        register = self._run_cli(["wave-plan", "--register", str(self.impl), str(self.other)])
        self.assertEqual(register.returncode, 0, register.stderr)
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
        claim_key = json.loads(claim.stdout)["key"]
        failed = self._run_cli(["wave-release", claim_key, "--state", "failed", "--reason", "ci failed"])
        self.assertEqual(failed.returncode, 0, failed.stderr)

        acquire = self._run_cli(["merge-lock", "acquire", "--branch", "feature/a", "--pr", "101"])

        self.assertEqual(acquire.returncode, 1)
        payload = json.loads(acquire.stdout)
        self.assertIn("explicit wave-reclaim", payload["error"])

    def test_merge_lock_break_stale_cli_releases_without_token(self) -> None:
        old = datetime.now(timezone.utc) - timedelta(hours=3)
        lock = MergeLock(self.root)
        acquired = lock.acquire(
            owner="dead-session",
            branch="feature/a",
            pr_number=101,
            now=old,
        )

        broken = self._run_cli(
            [
                "merge-lock",
                "break",
                "--stale-after",
                str(60 * 60),
                "--owner",
                "operator",
                "--reason",
                "operator confirmed stale",
            ]
        )

        self.assertEqual(broken.returncode, 0, broken.stderr)
        payload = json.loads(broken.stdout)
        self.assertEqual(payload["record"]["state"], "stale_broken")
        self.assertEqual(payload["record"]["token"], acquired.token)
        self.assertFalse(lock.lock_path.exists())


class ExternalGitCompletedTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.root, check=True)
        (self.root / "README.md").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=self.root, check=True, capture_output=True)
        self.impl = self.root / "docs/milestones/v01/epics/epic-01-demo/impl/01-first.md"
        self.impl.parent.mkdir(parents=True, exist_ok=True)
        self.impl.write_text("---\nstory: 1\ntask_index: 1/2\n---\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._td.cleanup()

    def _commit_on_branch(self, branch: str, message: str) -> None:
        subprocess.run(["git", "checkout", "-B", branch], cwd=self.root, check=True, capture_output=True)
        marker = self.root / f"{branch.replace('/', '_')}.txt"
        marker.write_text(message, encoding="utf-8")
        subprocess.run(["git", "add", str(marker.name)], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", message], cwd=self.root, check=True, capture_output=True)

    def test_unmerged_feature_branch_does_not_prove_completion(self) -> None:
        self._commit_on_branch("feature/prior", "implement 01-first")
        subprocess.run(["git", "checkout", "main"], cwd=self.root, check=True, capture_output=True)

        self.assertFalse(external_git_completed(self.root, self.impl, base_ref="main"))

    def test_base_ref_history_proves_completion(self) -> None:
        self._commit_on_branch("feature/prior", "implement 01-first")
        subprocess.run(["git", "checkout", "main"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "merge", "--no-ff", "feature/prior", "-m", "merge prior"], cwd=self.root, check=True, capture_output=True)

        self.assertTrue(external_git_completed(self.root, self.impl, base_ref="main"))


if __name__ == "__main__":
    unittest.main()

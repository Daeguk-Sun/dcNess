"""pr-finalize peer merge lock wiring tests (#641)."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from harness.merge_lock import MergeLock
from harness.wave_board import WaveBoard


REPO_ROOT = Path(__file__).resolve().parent.parent


class PrFinalizePeerLockWiringTests(unittest.TestCase):
    def test_pr_finalize_acquires_and_completes_peer_merge_lock(self) -> None:
        script = (REPO_ROOT / "scripts" / "pr-finalize.sh").read_text(encoding="utf-8")

        self.assertIn("merge-lock acquire", script)
        self.assertIn("merge-lock complete", script)
        self.assertIn("merge-lock release", script)
        self.assertIn("MERGE_LOCK_TOKEN", script)
        self.assertIn("MERGE_CLAIM_KEY", script)
        self.assertIn("--claim-key", script)
        self.assertIn("gh pr update-branch", script)

    def test_pr_finalize_ci_failure_marks_peer_claim_failed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            origin = Path(td) / "origin.git"
            root.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            impl = root / "docs/milestones/v01/epics/epic-01-demo/impl/01-first.md"
            impl.parent.mkdir(parents=True)
            impl.write_text(
                "---\nstory: 1\ntask_index: 1/1\ndepends_on: []\n---\n",
                encoding="utf-8",
            )
            (root / "README.md").write_text("base\n", encoding="utf-8")
            (root / ".gitignore").write_text(".claude/\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "base"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
            subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=root, check=True)
            subprocess.run(["git", "push", "-u", "origin", "main"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "checkout", "-b", "feature/a"], cwd=root, check=True, capture_output=True)

            board = WaveBoard(root)
            board.register([impl])
            claim = board.claim_if_registered(
                impl,
                session_id="s1",
                run_id="r1",
                worktree=str(root),
                branch="feature/a",
            )

            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            gh = bin_dir / "gh"
            gh.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"pr\" ] && [ \"$2\" = \"checks\" ] && [ \"$4\" = \"--watch\" ]; then\n"
                "  exit 1\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            gh.chmod(0o755)

            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "pr-finalize.sh"), "101"],
                cwd=root,
                capture_output=True,
                text=True,
                env=env,
                timeout=20,
            )

            self.assertEqual(result.returncode, 1, result.stderr)
            record = WaveBoard(root).get_record(claim.key)
            self.assertEqual(record["state"], "failed")
            self.assertEqual(record["reason"], "pr-finalize exit 1")
            self.assertFalse(MergeLock(root).lock_path.exists())


if __name__ == "__main__":
    unittest.main()

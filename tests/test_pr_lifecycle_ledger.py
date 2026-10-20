"""PR lifecycle helper ledger instrumentation tests (#785).

The shell helpers remain integration wrappers around git/gh, so these tests keep
the contract at the script wiring level: successful PR create/finalize paths must
record durable ledger checkpoints when an active dcNess run exists.
"""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PR_CREATE = REPO_ROOT / "scripts" / "pr-create.sh"
PR_FINALIZE = REPO_ROOT / "scripts" / "pr-finalize.sh"


class PrLifecycleLedgerWiringTests(unittest.TestCase):
    def test_pr_create_syntax_valid(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(PR_CREATE)], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_pr_create_records_pr_created_after_gh_create(self) -> None:
        script = PR_CREATE.read_text(encoding="utf-8")
        self.assertIn("dcness-helper", script)
        self.assertIn("ledger-event pr_created", script)
        self.assertIn("--url", script)
        self.assertIn("--pr", script)
        self.assertIn("PR_NUMBER", script)
        self.assertLess(
            script.index("gh pr create"),
            script.index("ledger-event pr_created"),
        )

    def test_pr_finalize_records_pr_merged_after_merged_state(self) -> None:
        script = PR_FINALIZE.read_text(encoding="utf-8")
        self.assertIn("ledger-event pr_merged", script)
        self.assertIn("--url", script)
        self.assertIn("--pr", script)
        self.assertIn('--head "$merged_head"', script)
        self.assertLess(
            script.index('STATE" != "MERGED"'),
            script.index('record_pr_merged "$PR" "$PR_URL" "$HEAD_SHA"'),
        )


if __name__ == "__main__":
    unittest.main()

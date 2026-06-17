"""Deterministic guard-efficacy eval runner contract tests.

The runner itself exercises hook/function behavior without an LLM. These tests
keep the command shape and required coverage categories stable.
"""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "evals" / "guard_efficacy.py"


class GuardEfficacyEvalContractTests(unittest.TestCase):
    def test_runner_reports_required_categories_without_llm(self) -> None:
        self.assertTrue(RUNNER.is_file())

        result = subprocess.run(
            ["python3.11", str(RUNNER), "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        report = json.loads(result.stdout)
        self.assertEqual(report["total"]["failed"], 0)
        self.assertGreater(report["total"]["passed"], 0)

        categories = set(report["categories"])
        for category in (
            "file-boundary",
            "bash-mutation",
            "mcp-mutation",
            "order-gate",
            "tdd-guard",
            "known-bypass-boundary",
        ):
            with self.subTest(category=category):
                self.assertIn(category, categories)
                self.assertGreater(report["categories"][category]["passed"], 0)

        case_ids = {case["id"] for case in report["cases"]}
        for case_id in (
            "file_boundary_blocks_infra",
            "bash_mutation_blocks_git_push",
            "mcp_mutation_blocks_pr_merge",
            "order_gate_blocks_missing_begin_step",
            "tdd_guard_blocks_impl_without_test",
            "known_boundary_tdd_bash_write_not_enforced",
        ):
            with self.subTest(case_id=case_id):
                self.assertIn(case_id, case_ids)

    def test_runner_is_documented_in_eval_readme(self) -> None:
        readme = (ROOT / "evals" / "README.md").read_text(encoding="utf-8")
        self.assertIn("python3 evals/guard_efficacy.py", readme)
        self.assertIn("결정적 guard-efficacy", readme)


if __name__ == "__main__":
    unittest.main()

"""Tests for the one-shot policy cleanup baseline measurement."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "policy_cleanup_baseline.py"


def load_module():
    spec = importlib.util.spec_from_file_location("policy_cleanup_baseline", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


class PolicyCleanupBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()

    def test_measure_revision_uses_tracked_tree_and_stable_metric_definitions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            run("git", "init", "-q", cwd=repo)
            run("git", "config", "user.name", "Test", cwd=repo)
            run("git", "config", "user.email", "test@example.com", cwd=repo)

            files = {
                "README.md": "# Sample\n",
                "harness/core.py": "def current():\n    return True\n",
                "scripts/helper.py": "print('ok')\n",
                "evals/probe.py": "VALUE = 1\n",
                "tests/test_core.py": (
                    "def test_one():\n    pass\n\n"
                    "class TestCore:\n"
                    "    def test_two(self):\n        pass\n"
                ),
                "data/sample.jsonl": "{}\n",
            }
            for rel, content in files.items():
                path = repo / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            run("git", "add", ".", cwd=repo)
            run("git", "commit", "-qm", "fixture", cwd=repo)

            (repo / "untracked.py").write_text("def test_not_counted(): pass\n")
            result = self.module.measure_revision(repo, "HEAD")

        self.assertEqual(result["tracked_files"], 6)
        self.assertEqual(result["major_text_files"], 5)
        self.assertEqual(result["major_text_loc"], 11)
        self.assertEqual(result["code_loc"], 4)
        self.assertEqual(result["test_loc"], 6)
        self.assertEqual(result["test_functions"], 2)
        self.assertEqual(result["files_ge_500_loc"], 0)
        self.assertEqual(result["files_ge_1000_loc"], 0)

    def test_inventory_summary_requires_classification_mapping_and_compat_evidence(self) -> None:
        entries = [
            {
                "id": "DES-001",
                "area": "design",
                "policy_slice": "legacy reader",
                "classification": "한시적 호환 필요",
                "follow_up_issue": 1093,
                "current_ssot": ["docs/current.md"],
                "implementation": ["scripts/reader.mjs"],
                "tests_fixtures": ["tests/test_reader.py"],
                "docs_distribution": ["docs/plugin/design.md"],
                "consumer_evidence": "active-project survey found legacy documents",
                "compatibility": {
                    "consumer_or_format": "legacy Contract Ledger documents",
                    "reason": "existing documents must remain readable",
                    "removal_trigger": "all registered projects migrate",
                    "verification": "run the compatibility fixture",
                },
            },
            {
                "id": "RUN-001",
                "area": "run-ledger",
                "policy_slice": "canonical writer",
                "classification": "현재 실사용",
                "follow_up_issue": 1094,
                "current_ssot": ["docs/current.md"],
                "implementation": ["harness/ledger.py"],
                "tests_fixtures": ["tests/test_ledger.py"],
                "docs_distribution": ["docs/plugin/loop-procedure.md"],
                "consumer_evidence": "current runs contain ledger.jsonl",
                "compatibility": None,
            },
        ]
        entries[1]["classification"] = "퇴역 완료"

        summary = self.module.summarize_inventory(entries)

        self.assertEqual(summary["compatibility_candidates"], 1)
        self.assertEqual(summary["by_classification"]["한시적 호환 필요"], 1)
        self.assertEqual(summary["by_classification"]["퇴역 완료"], 1)

        broken = json.loads(json.dumps(entries))
        del broken[0]["compatibility"]["removal_trigger"]
        with self.assertRaisesRegex(ValueError, "removal_trigger"):
            self.module.summarize_inventory(broken)

    def test_inventory_rejects_duplicate_ids_and_wrong_follow_up_scope(self) -> None:
        entry = {
            "id": "ROUTE-001",
            "area": "routing",
            "policy_slice": "route",
            "classification": "제거 가능",
            "follow_up_issue": 1094,
            "current_ssot": ["docs/current.md"],
            "implementation": ["harness/agent_routing.py"],
            "tests_fixtures": ["tests/test_agent_routing.py"],
            "docs_distribution": ["docs/plugin/init-dcness.md"],
            "consumer_evidence": "no active config uses the preset",
            "compatibility": None,
        }

        with self.assertRaisesRegex(ValueError, "follow_up_issue"):
            self.module.summarize_inventory([entry])

        entry["follow_up_issue"] = 1095
        with self.assertRaisesRegex(ValueError, "duplicate inventory id"):
            self.module.summarize_inventory([entry, dict(entry)])

    def test_run006_transition_is_terminal_and_private_facade_is_absent(self) -> None:
        entries = self.module.load_inventory(
            ROOT / "docs" / "internal" / "policy-sunset-inventory.json"
        )
        run006 = next(entry for entry in entries if entry["id"] == "RUN-006")
        state_source = (ROOT / "harness" / "session_state.py").read_text(
            encoding="utf-8"
        )

        self.assertEqual(run006["classification"], "퇴역 완료")
        self.assertNotIn("_CLI_REEXPORT_NAMES", state_source)
        self.assertNotIn("def __getattr__(", state_source)

    def test_unit_suite_runs_the_requested_revision_not_dirty_working_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            run("git", "init", "-q", cwd=repo)
            run("git", "config", "user.name", "Test", cwd=repo)
            run("git", "config", "user.email", "test@example.com", cwd=repo)
            test_path = repo / "tests" / "test_clean_tree.py"
            test_path.parent.mkdir(parents=True)
            test_path.write_text(
                "import unittest\n\n"
                "class CleanTreeTests(unittest.TestCase):\n"
                "    def test_committed_tree(self):\n"
                "        self.assertTrue(True)\n",
                encoding="utf-8",
            )
            run("git", "add", ".", cwd=repo)
            run("git", "commit", "-qm", "fixture", cwd=repo)
            revision = run("git", "rev-parse", "HEAD", cwd=repo).stdout.strip()

            test_path.write_text(
                "import unittest\n\n"
                "class DirtyTreeTests(unittest.TestCase):\n"
                "    def test_dirty_tree(self):\n"
                "        self.fail('dirty working tree leaked into baseline')\n",
                encoding="utf-8",
            )
            result = self.module.run_unit_suite(repo, revision)

        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["tree_mode"], "detached_git_worktree")


if __name__ == "__main__":
    unittest.main()

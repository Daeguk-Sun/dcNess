"""Public evidence freshness gate regression tests."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_public_evidence.mjs"


class PublicEvidenceGateTests(unittest.TestCase):
    def _fixture(self, root: Path, *, version: str = "1.2.3", tests: int = 7) -> None:
        (root / ".claude-plugin").mkdir(parents=True)
        (root / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "dcness", "version": version}), encoding="utf-8"
        )
        snapshot = {
            "plugin_version": version,
            "measured_at": "2026-07-12",
            "unit_tests": {"passed": tests, "total": tests},
            "guard": {"passed": 3, "total": 3},
            "source_project_count": 2,
        }
        marker = f"<!-- public-evidence-snapshot {json.dumps(snapshot)} -->\n"
        (root / "README.md").write_text(marker, encoding="utf-8")
        docs = root / "docs" / "plugin"
        docs.mkdir(parents=True)
        (docs / "benchmark.md").write_text(marker, encoding="utf-8")
        (root / "unittest.txt").write_text(
            f"Ran {tests} tests in 0.100s\n\nOK\n", encoding="utf-8"
        )
        (root / "guard.json").write_text(
            json.dumps({"total": {"passed": 3, "failed": 0, "total": 3}}),
            encoding="utf-8",
        )

    def _run(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "node",
                str(CHECKER),
                "--root",
                str(root),
                "--test-output",
                str(root / "unittest.txt"),
                "--guard-output",
                str(root / "guard.json"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    def test_fixture_snapshot_passes_with_matching_runtime_measurements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            result = self._run(root)

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("PASS", result.stdout)
        self.assertIn("tests=7/7", result.stdout)
        self.assertIn("guard=3/3", result.stdout)

    def test_version_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            manifest = root / ".claude-plugin" / "plugin.json"
            manifest.write_text(
                json.dumps({"name": "dcness", "version": "1.2.4"}),
                encoding="utf-8",
            )
            result = self._run(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("plugin version drift", result.stderr)

    def test_test_count_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root, tests=7)
            (root / "unittest.txt").write_text(
                "Ran 8 tests in 0.100s\n\nOK\n", encoding="utf-8"
            )
            result = self._run(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("unit test drift", result.stderr)

    def test_guard_count_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            (root / "guard.json").write_text(
                json.dumps({"total": {"passed": 4, "failed": 0, "total": 4}}),
                encoding="utf-8",
            )
            result = self._run(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("guard drift", result.stderr)

    def test_readme_and_benchmark_snapshot_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            benchmark = root / "docs" / "plugin" / "benchmark.md"
            benchmark.write_text(
                benchmark.read_text(encoding="utf-8").replace(
                    '"source_project_count": 2', '"source_project_count": 1'
                ),
                encoding="utf-8",
            )
            result = self._run(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("README/benchmark snapshot drift", result.stderr)


if __name__ == "__main__":
    unittest.main()

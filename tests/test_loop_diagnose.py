"""loop_diagnose self-improvement sweep tool tests (#902)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "loop_diagnose.py"


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_guard_hit(project: Path, guard: str = "file-guard") -> None:
    _write_jsonl(
        project / ".claude" / "harness-state" / "guard-telemetry.jsonl",
        [
            {
                "kind": "guard_hit",
                "guard": guard,
                "category": "write_boundary",
                "source": "test",
                "ts": "2026-01-01T00:00:00Z",
            }
        ],
    )


def _write_recurrent_waste_run(project: Path) -> None:
    run_dir = (
        project
        / ".claude"
        / "harness-state"
        / ".sessions"
        / "sid-loop-diagnose"
        / "runs"
        / "run-loop902a"
    )
    _write_jsonl(
        run_dir / ".steps.jsonl",
        [
            {
                "ts": "2026-01-01T00:00:01Z",
                "agent": "engineer",
                "mode": "IMPL",
                "enum": "TESTS_FAIL",
                "must_fix": False,
                "prose_excerpt": "same failure\nline2\nline3\nline4\nline5",
            },
            {
                "ts": "2026-01-01T00:01:01Z",
                "agent": "engineer",
                "mode": "IMPL",
                "enum": "TESTS_FAIL",
                "must_fix": False,
                "prose_excerpt": "same failure\nline2\nline3\nline4\nline5",
            },
        ],
    )


def _write_eval_events(repo_root: Path) -> None:
    _write_jsonl(
        repo_root / ".metrics" / "evals" / "run-1" / "guard-telemetry.jsonl",
        [
            {
                "kind": "eval_case_result",
                "case": "headless-prose-quality",
                "passed": True,
                "ts": "2026-07-01T00:00:00Z",
            },
            {
                "kind": "eval_case_result",
                "case": "headless-prose-quality",
                "passed": True,
                "ts": "2026-07-02T00:00:00Z",
            },
        ],
    )


def _snapshot_tree(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        out[str(path.relative_to(root))] = path.read_text(encoding="utf-8")
    return out


class LoopDiagnoseTests(unittest.TestCase):
    def _run(
        self,
        repo_root: Path,
        projects_file: Path,
        *extra: str,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["DCNESS_PROJECTS_FILE"] = str(projects_file)
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--repo-root",
                str(repo_root),
                "--recurrence-threshold",
                "1",
                "--saturation-min-runs",
                "2",
                *extra,
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_report_aggregates_projects_watermark_json_and_readonly(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            repo_root = tmp / "dcness"
            repo_root.mkdir()
            alpha = tmp / "alpha"
            beta = tmp / "beta"
            alpha.mkdir()
            beta.mkdir()
            _write_guard_hit(alpha)
            _write_recurrent_waste_run(alpha)
            projects_file = tmp / "projects.json"
            projects_file.write_text(
                json.dumps({"version": 1, "projects": [str(alpha), str(beta)]}),
                encoding="utf-8",
            )
            before_alpha = _snapshot_tree(alpha)
            before_beta = _snapshot_tree(beta)

            first = self._run(repo_root, projects_file)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("guard:file-guard@alpha", first.stdout)
            self.assertIn("waste:RETRY_SAME_FAIL@alpha", first.stdout)
            self.assertIn("프로젝트: beta", first.stdout)
            self.assertIn("관측 이력 없음(미배포 또는 무발화)", first.stdout)
            self.assertIn("신규", first.stdout)
            self.assertTrue((repo_root / ".metrics" / "loop-diagnose" / "sweeps.jsonl").is_file())
            self.assertEqual(_snapshot_tree(alpha), before_alpha)
            self.assertEqual(_snapshot_tree(beta), before_beta)

            second = self._run(repo_root, projects_file)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("기왕", second.stdout)

            as_json = self._run(repo_root, projects_file, "--json")
            self.assertEqual(as_json.returncode, 0, as_json.stderr)
            payload = json.loads(as_json.stdout)
            self.assertEqual([p["name"] for p in payload["projects"]], ["alpha", "beta"])
            self.assertIn("swept_at", payload)
            self.assertIn("candidates", payload)
            keys = {candidate["key"] for candidate in payload["candidates"]}
            self.assertIn("guard:file-guard@alpha", keys)
            self.assertIn("waste:RETRY_SAME_FAIL@alpha", keys)

    def test_decision_record_annotation_and_hide_decided(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            repo_root = tmp / "dcness"
            repo_root.mkdir()
            alpha = tmp / "alpha"
            alpha.mkdir()
            _write_guard_hit(alpha)
            _write_recurrent_waste_run(alpha)
            projects_file = tmp / "projects.json"
            projects_file.write_text(
                json.dumps({"version": 1, "projects": [str(alpha)]}),
                encoding="utf-8",
            )

            invalid = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "record-decision",
                    "--repo-root",
                    str(repo_root),
                    "--key",
                    "guard:file-guard@alpha",
                    "--decision",
                    "maybe",
                    "--ref",
                    "#902",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(invalid.returncode, 0)
            self.assertFalse((repo_root / "docs" / "internal" / "loop-decisions.jsonl").exists())

            fixed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "record-decision",
                    "--repo-root",
                    str(repo_root),
                    "--key",
                    "guard:file-guard@alpha",
                    "--decision",
                    "fixed",
                    "--ref",
                    "#902",
                    "--decided-at",
                    "2026-07-04T00:00:00Z",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(fixed.returncode, 0, fixed.stderr)
            hold = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "record-decision",
                    "--repo-root",
                    str(repo_root),
                    "--key",
                    "waste:RETRY_SAME_FAIL@alpha",
                    "--decision",
                    "hold",
                    "--ref",
                    "#903",
                    "--decided-at",
                    "2026-07-04T00:00:01Z",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(hold.returncode, 0, hold.stderr)

            report = self._run(repo_root, projects_file)
            self.assertIn("이전 결정: 고침 2026-07-04 #902", report.stdout)
            self.assertIn("이전 결정: 보류 2026-07-04 #903", report.stdout)

            hidden = self._run(repo_root, projects_file, "--hide-decided")
            self.assertNotIn("guard:file-guard@alpha", hidden.stdout)
            self.assertIn("waste:RETRY_SAME_FAIL@alpha", hidden.stdout)

    def test_eval_saturation_candidate_from_self_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            repo_root = tmp / "dcness"
            repo_root.mkdir()
            projects_file = tmp / "projects.json"
            projects_file.write_text(
                json.dumps({"version": 1, "projects": []}),
                encoding="utf-8",
            )
            _write_eval_events(repo_root)

            result = self._run(repo_root, projects_file)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("eval:headless-prose-quality", result.stdout)
            self.assertIn("judge 보정은 자동 수집하지 않습니다", result.stdout)


if __name__ == "__main__":
    unittest.main()

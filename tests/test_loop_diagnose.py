"""loop_diagnose self-improvement sweep tool tests (#902)."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest import mock

from tests.run_fixtures import make_ledger_run_dir


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "loop_diagnose.py"


def _load_loop_diagnose() -> Any:
    spec = importlib.util.spec_from_file_location("loop_diagnose", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _iso_days_ago(days: int) -> str:
    return (
        datetime.now(timezone.utc)
        - timedelta(days=days)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_guard_hit(project: Path, guard: str = "file-guard") -> None:
    _write_jsonl(
        project / ".claude" / "harness-state" / "guard-telemetry.jsonl",
        [
            {
                "kind": "guard_hit",
                "guard": guard,
                "category": "write_boundary",
                "source": "test",
                "ts": _iso_days_ago(45),
            }
        ],
    )


def _write_telemetry_epoch(project: Path, *, days_ago: int) -> None:
    _write_jsonl(
        project / ".claude" / "harness-state" / "guard-telemetry.jsonl",
        [
            {
                "kind": "telemetry_epoch",
                "source": "test",
                "ts": _iso_days_ago(days_ago),
            }
        ],
    )


def _write_recurrent_waste_run(project: Path) -> None:
    excerpt = "same failure\nline2\nline3\nline4\nline5"
    make_ledger_run_dir(
        project,
        "sid-loop-diagnose",
        "run-loop902a",
        [
            {"event": "run_started", "ts": "2026-01-01T00:00:00Z"},
            {
                "event": "step_completed",
                "ts": "2026-01-01T00:00:01Z",
                "agent": "engineer",
                "mode": "IMPL",
                "enum": "TESTS_FAIL",
                "must_fix": False,
                "prose_excerpt": excerpt,
                "prose_file": "engineer-1.md",
            },
            {
                "event": "step_completed",
                "ts": "2026-01-01T00:01:01Z",
                "agent": "engineer",
                "mode": "IMPL",
                "enum": "TESTS_FAIL",
                "must_fix": False,
                "prose_excerpt": excerpt,
                "prose_file": "engineer-2.md",
            },
            {"event": "run_finished", "ts": "2026-01-01T00:02:00Z"},
        ],
        {"engineer-1.md": excerpt, "engineer-2.md": excerpt},
    )


def _write_eval_events(repo_root: Path) -> None:
    _write_jsonl(
        repo_root / ".metrics" / "evals" / "run-1" / "guard-telemetry.jsonl",
        [
            {
                "kind": "eval_case_result",
                "case": "headless-prose-quality",
                "passed": True,
                "ts": _iso_days_ago(2),
            },
            {
                "kind": "eval_case_result",
                "case": "headless-prose-quality",
                "passed": True,
                "ts": _iso_days_ago(1),
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
            self.assertEqual(payload["projects"][0]["guard_summary"]["since_days"], 90)

    def test_zero_hit_guard_after_observation_window_is_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            repo_root = tmp / "dcness"
            repo_root.mkdir()
            old_observed = tmp / "old-observed"
            new_observed = tmp / "new-observed"
            old_observed.mkdir()
            new_observed.mkdir()
            _write_telemetry_epoch(old_observed, days_ago=45)
            _write_telemetry_epoch(new_observed, days_ago=5)
            projects_file = tmp / "projects.json"
            projects_file.write_text(
                json.dumps(
                    {"version": 1, "projects": [str(old_observed), str(new_observed)]}
                ),
                encoding="utf-8",
            )

            result = self._run(repo_root, projects_file, "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            keys = {candidate["key"] for candidate in payload["candidates"]}
            self.assertIn("guard:file-guard@old-observed", keys)
            self.assertNotIn("guard:file-guard@new-observed", keys)
            old_summary = payload["projects"][0]["guard_summary"]["guards"]["file-guard"]
            new_summary = payload["projects"][1]["guard_summary"]["guards"]["file-guard"]
            self.assertEqual(old_summary["count"], 0)
            self.assertEqual(old_summary["observation_status"], "observed")
            self.assertTrue(old_summary["reassessment_candidate"])
            self.assertEqual(
                new_summary["observation_status"],
                "insufficient_observation",
            )
            self.assertFalse(new_summary["reassessment_candidate"])

            rendered = self._run(repo_root, projects_file)
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            self.assertIn("| file-guard | 0 | - | 재평가 후보 |", rendered.stdout)
            self.assertIn("| file-guard | 0 | - | 관측 부족 |", rendered.stdout)

    def test_since_days_limits_guard_summary_scan_window(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            repo_root = tmp / "dcness"
            repo_root.mkdir()
            alpha = tmp / "alpha"
            alpha.mkdir()
            _write_jsonl(
                alpha / ".claude" / "harness-state" / "guard-telemetry.jsonl",
                [
                    {
                        "kind": "guard_hit",
                        "guard": "file-guard",
                        "category": "write_boundary",
                        "source": "test",
                        "ts": _iso_days_ago(45),
                    }
                ],
            )
            projects_file = tmp / "projects.json"
            projects_file.write_text(
                json.dumps({"version": 1, "projects": [str(alpha)]}),
                encoding="utf-8",
            )

            result = self._run(repo_root, projects_file, "--since-days", "7", "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            summary = payload["projects"][0]["guard_summary"]
            self.assertEqual(summary["since_days"], 7)
            row = summary["guards"]["file-guard"]
            self.assertEqual(row["count"], 0)
            self.assertEqual(row["observation_status"], "insufficient_observation")
            keys = {candidate["key"] for candidate in payload["candidates"]}
            self.assertNotIn("guard:file-guard@alpha", keys)

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

    def test_eval_flaky_candidate_from_self_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            repo_root = tmp / "dcness"
            repo_root.mkdir()
            projects_file = tmp / "projects.json"
            projects_file.write_text(
                json.dumps({"version": 1, "projects": []}),
                encoding="utf-8",
            )
            _write_jsonl(
                repo_root / ".metrics" / "evals" / "run-1" / "guard-telemetry.jsonl",
                [
                    {
                        "kind": "eval_case_result",
                        "case": "flow-ownership-entrypoint-bad",
                        "passed": True,
                        "ts": _iso_days_ago(2),
                    },
                    {
                        "kind": "eval_case_result",
                        "case": "flow-ownership-entrypoint-bad",
                        "passed": False,
                        "ts": _iso_days_ago(1),
                    },
                ],
            )

            result = self._run(repo_root, projects_file)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("eval:flow-ownership-entrypoint-bad", result.stdout)
            self.assertIn("flaky", result.stdout)

    def test_action_brief_reports_no_work_without_advancing_watermark(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            repo_root = tmp / "dcness"
            repo_root.mkdir()
            projects_file = tmp / "projects.json"
            projects_file.write_text(
                json.dumps({"version": 1, "projects": []}), encoding="utf-8"
            )

            result = self._run(
                repo_root, projects_file, "--action-brief", "--no-watermark"
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("지금 검토할 하네스 개선 후보가 없습니다", result.stdout)
            self.assertFalse((repo_root / ".metrics" / "loop-diagnose").exists())

    def test_action_brief_prioritizes_one_candidate_in_user_language(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            repo_root = tmp / "dcness"
            repo_root.mkdir()
            alpha = tmp / "alpha"
            alpha.mkdir()
            _write_guard_hit(alpha)
            projects_file = tmp / "projects.json"
            projects_file.write_text(
                json.dumps({"version": 1, "projects": [str(alpha)]}),
                encoding="utf-8",
            )

            result = self._run(
                repo_root, projects_file, "--action-brief", "--no-watermark"
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            for expected in (
                "우선 검토 후보",
                "대상 구성요소",
                "반복 근거",
                "기대 효과",
                "안전 경계",
                "예상 LLM trial: 2회",
                "애매하면 최대 4회",
                "실행할까요?",
            ):
                self.assertIn(expected, result.stdout)
            self.assertNotIn("ablation", result.stdout.lower())


class LoopSweepTests(unittest.TestCase):
    def _run_sweep(
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
                "sweep",
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

    def test_sweep_persists_digest_and_log_and_is_readonly(self) -> None:
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

            first = self._run_sweep(repo_root, projects_file)
            self.assertEqual(first.returncode, 0, first.stderr)

            digest_dir = repo_root / ".metrics" / "loop-diagnose"
            digest = digest_dir / "digest-latest.md"
            sweep_log = digest_dir / "sweep-log.jsonl"
            watermark = digest_dir / "sweeps.jsonl"

            self.assertTrue(digest.is_file())
            self.assertTrue(watermark.is_file())
            digest_text = digest.read_text(encoding="utf-8")
            self.assertIn("통합 후보", digest_text)
            self.assertIn("guard:file-guard@alpha", digest_text)
            self.assertIn("신규", digest_text)

            self.assertTrue(sweep_log.is_file())
            entries = [json.loads(line) for line in sweep_log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(entries[-1]["status"], "ok")
            self.assertGreaterEqual(entries[-1]["candidate_count"], 1)
            self.assertEqual(Path(entries[-1]["digest_path"]).resolve(), digest.resolve())

            # read-only: swept projects are untouched
            self.assertEqual(_snapshot_tree(alpha), before_alpha)
            self.assertEqual(_snapshot_tree(beta), before_beta)

            second = self._run_sweep(repo_root, projects_file)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("기왕", digest.read_text(encoding="utf-8"))
            entries = [json.loads(line) for line in sweep_log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(entries), 2)
            self.assertTrue(all(entry["status"] == "ok" for entry in entries))

    def test_sweep_digest_failure_leaves_error_and_does_not_advance_watermark(self) -> None:
        # If the digest cannot be persisted, the watermark must NOT advance — otherwise the
        # candidates would be recorded as seen and resurface as 기왕 (signal lost) — and the
        # failure must still leave a status:error trace.
        module = _load_loop_diagnose()
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            repo_root = tmp / "dcness"
            repo_root.mkdir()
            alpha = tmp / "alpha"
            alpha.mkdir()
            _write_guard_hit(alpha)
            projects_file = tmp / "projects.json"
            projects_file.write_text(
                json.dumps({"version": 1, "projects": [str(alpha)]}),
                encoding="utf-8",
            )
            digest_dir = repo_root / ".metrics" / "loop-diagnose"
            # digest-latest.md as a directory makes _write_digest's os.replace fail
            (digest_dir / "digest-latest.md").mkdir(parents=True)
            args = module._build_sweep_parser().parse_args(
                ["--repo-root", str(repo_root), "--projects-file", str(projects_file),
                 "--recurrence-threshold", "1"]
            )

            rc = module._run_sweep(args)

            self.assertEqual(rc, 1)
            last = json.loads((digest_dir / "sweep-log.jsonl").read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(last["status"], "error")
            self.assertFalse((digest_dir / "sweeps.jsonl").exists())

    def test_sweep_failure_leaves_trace_and_nonzero_exit(self) -> None:
        module = _load_loop_diagnose()
        with tempfile.TemporaryDirectory() as td:
            digest_dir = Path(td) / "digest"
            args = module._build_sweep_parser().parse_args(
                ["--repo-root", td, "--digest-dir", str(digest_dir)]
            )
            with mock.patch.object(module, "build_payload", side_effect=RuntimeError("boom")):
                rc = module._run_sweep(args)

            self.assertEqual(rc, 1)
            sweep_log = digest_dir / "sweep-log.jsonl"
            self.assertTrue(sweep_log.is_file())
            last = json.loads(sweep_log.read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(last["status"], "error")
            self.assertIn("boom", last["error"])
            # a failed build must not leave a stale/partial digest
            self.assertFalse((digest_dir / "digest-latest.md").exists())


if __name__ == "__main__":
    unittest.main()

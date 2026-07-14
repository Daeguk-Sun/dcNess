"""guard telemetry append/read/summary contracts (#875)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from harness.guard_telemetry import (
    TELEMETRY_NAME,
    append_event,
    collect_eval_summary,
    collect_guard_summary,
    format_telemetry_report,
    read_events,
    record_eval_case_result,
    record_guard_hit,
)
from harness.session_state import generate_run_id, run_dir


SID = "guard-telemetry-sid"


class GuardTelemetryAppendTests(unittest.TestCase):
    def test_guard_hit_roundtrip_in_run_dir(self) -> None:
        with TemporaryDirectory() as td:
            base = Path(td)
            rid = generate_run_id()
            record_guard_hit(
                "catastrophic-gate",
                category="order_gate",
                detail="engineer before design",
                session_id=SID,
                run_id=rid,
                base_dir=base,
            )

            target = run_dir(SID, rid, base_dir=base) / TELEMETRY_NAME
            self.assertTrue(target.is_file())
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            events = read_events(base_dir=base)
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["kind"], "telemetry_epoch")
            self.assertEqual(events[1]["kind"], "guard_hit")
            self.assertEqual(events[1]["guard"], "catastrophic-gate")
            self.assertEqual(events[1]["category"], "order_gate")

    def test_guard_hit_without_run_falls_back_to_project_log(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            record_guard_hit(
                "git-pre-commit",
                category="main_block",
                detail="main commit blocked",
                cwd=root,
            )

            target = root / ".claude" / "harness-state" / TELEMETRY_NAME
            self.assertTrue(target.is_file())
            events = read_events(cwd=root)
            self.assertEqual(events[0]["kind"], "telemetry_epoch")
            self.assertEqual(events[1]["guard"], "git-pre-commit")
            self.assertEqual(events[1]["source"], "git_hook")

    def test_cli_record_hit_accepts_run_context(self) -> None:
        with TemporaryDirectory() as td:
            base = Path(td)
            rid = generate_run_id()

            result = subprocess.run(
                [
                    "python3.11",
                    "-m",
                    "harness.guard_telemetry",
                    "record-hit",
                    "--guard",
                    "tdd-guard",
                    "--category",
                    "bash_missing_test",
                    "--session-id",
                    SID,
                    "--run-id",
                    rid,
                    "--base-dir",
                    str(base),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            events = read_events(base_dir=base)
            hit = [event for event in events if event.get("kind") == "guard_hit"][0]
            self.assertEqual(hit["session_id"], SID)
            self.assertEqual(hit["run_id"], rid)
            self.assertTrue((run_dir(SID, rid, base_dir=base) / TELEMETRY_NAME).is_file())


class GuardSummaryTests(unittest.TestCase):
    def test_summary_marks_no_log_as_observation_insufficient(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            summary = collect_guard_summary(
                cwd=root,
                known_guards=("catastrophic-gate",),
                idle_days=30,
            )

            self.assertEqual(summary["guards"]["catastrophic-gate"]["count"], 0)
            self.assertFalse(summary["guards"]["catastrophic-gate"]["reassessment_candidate"])
            self.assertEqual(
                summary["guards"]["catastrophic-gate"]["observation_status"],
                "no_observation",
            )

    def test_zero_hit_guard_needs_full_idle_window_before_reassessment(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            epoch = datetime.now(timezone.utc) - timedelta(days=10)
            append_event(
                {
                    "kind": "telemetry_epoch",
                    "ts": epoch.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                },
                cwd=root,
            )

            summary = collect_guard_summary(
                cwd=root,
                known_guards=("catastrophic-gate",),
                idle_days=30,
            )

            row = summary["guards"]["catastrophic-gate"]
            self.assertEqual(row["count"], 0)
            self.assertFalse(row["reassessment_candidate"])
            self.assertEqual(row["observation_status"], "insufficient_observation")

    def test_zero_hit_guard_after_idle_window_is_reassessment_candidate(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            epoch = datetime.now(timezone.utc) - timedelta(days=45)
            append_event(
                {
                    "kind": "telemetry_epoch",
                    "ts": epoch.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                },
                cwd=root,
            )

            summary = collect_guard_summary(
                cwd=root,
                known_guards=("catastrophic-gate",),
                idle_days=30,
            )

            row = summary["guards"]["catastrophic-gate"]
            self.assertEqual(row["count"], 0)
            self.assertTrue(row["reassessment_candidate"])
            self.assertEqual(row["observation_status"], "observed")

    def test_recent_hit_is_not_reassessment_candidate(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            record_guard_hit("file-guard", category="write_boundary", cwd=root)

            summary = collect_guard_summary(
                cwd=root,
                known_guards=("file-guard",),
                idle_days=30,
            )

            row = summary["guards"]["file-guard"]
            self.assertEqual(row["count"], 1)
            self.assertFalse(row["reassessment_candidate"])
            self.assertEqual(row["observation_status"], "observed")

    def test_since_days_limits_guard_summary_window(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            old = datetime.now(timezone.utc) - timedelta(days=20)
            append_event(
                {
                    "kind": "guard_hit",
                    "guard": "file-guard",
                    "category": "write_boundary",
                    "source": "plugin_hook",
                    "ts": old.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                },
                cwd=root,
            )

            summary = collect_guard_summary(
                cwd=root,
                known_guards=("file-guard",),
                idle_days=30,
                since_days=7,
            )

            self.assertEqual(summary["since_days"], 7)
            self.assertEqual(summary["guards"]["file-guard"]["count"], 0)
            self.assertEqual(
                summary["guards"]["file-guard"]["observation_status"],
                "insufficient_observation",
            )

    def test_default_report_known_guards_include_distributed_pre_commit(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            summary = collect_guard_summary(cwd=root, idle_days=30)

            self.assertIn("git-commit-msg", summary["guards"])
            self.assertIn("git-pre-push", summary["guards"])
            self.assertIn("git-pre-commit", summary["guards"])


class EvalSummaryTests(unittest.TestCase):
    def test_eval_case_results_share_the_same_event_log(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            record_eval_case_result(
                "headless-prose-quality",
                passed=True,
                run_index=1,
                total_runs=2,
                cwd=root,
                report_file="/tmp/report.md",
                judge_file="/tmp/judge.md",
                llm_turns=2,
                report_chars=120,
                judge_chars=80,
                estimated_output_tokens=50,
            )

            events = read_events(cwd=root)
            event = [row for row in events if row.get("kind") == "eval_case_result"][0]
            self.assertEqual(event["case"], "headless-prose-quality")
            self.assertTrue(event["passed"])
            self.assertEqual(event["llm_turns"], 2)
            self.assertEqual(event["estimated_output_tokens"], 50)

    def test_eval_case_failure_stage_counts_as_attempt(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            record_eval_case_result(
                "headless-prose-quality",
                passed=False,
                cwd=root,
                failure_stage="report",
                failure_detail="claude exited 1",
                llm_turns=1,
            )

            summary = collect_eval_summary(cwd=root, saturation_min_runs=1)

            row = summary["cases"]["headless-prose-quality"]
            self.assertEqual(row["attempts"], 1)
            self.assertEqual(row["passes"], 0)
            self.assertEqual(row["failure_stages"]["report"], 1)
            self.assertFalse(row["saturation_candidate"])
            self.assertFalse(row["flaky_candidate"])

    def test_all_pass_eval_case_is_saturation_candidate(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            for run_index in (1, 2):
                record_eval_case_result(
                    "shorts-real-spec",
                    passed=True,
                    run_index=run_index,
                    total_runs=2,
                    cwd=root,
                )

            summary = collect_eval_summary(
                cwd=root,
                saturation_days=30,
                saturation_min_runs=2,
            )

            row = summary["cases"]["shorts-real-spec"]
            self.assertEqual(row["attempts"], 2)
            self.assertEqual(row["passes"], 2)
            self.assertEqual(row["accuracy"], 1.0)
            self.assertTrue(row["saturation_candidate"])
            self.assertFalse(row["flaky_candidate"])

    def test_partial_pass_eval_case_is_flaky_candidate(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            for passed in (True, True, False):
                record_eval_case_result(
                    "flow-ownership-entrypoint-bad",
                    passed=passed,
                    cwd=root,
                )

            summary = collect_eval_summary(
                cwd=root,
                saturation_days=30,
                saturation_min_runs=3,
            )

            row = summary["cases"]["flow-ownership-entrypoint-bad"]
            self.assertEqual(row["attempts"], 3)
            self.assertEqual(row["passes"], 2)
            self.assertTrue(row["flaky_candidate"])
            self.assertFalse(row["saturation_candidate"])

    def test_any_recent_fail_prevents_saturation_candidate(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            record_eval_case_result("flow-ownership-owner-good", passed=True, cwd=root)
            record_eval_case_result(
                "flow-ownership-owner-good",
                passed=False,
                cwd=root,
                llm_turns=2,
                estimated_output_tokens=40,
            )

            summary = collect_eval_summary(
                cwd=root,
                saturation_days=30,
                saturation_min_runs=2,
            )

            row = summary["cases"]["flow-ownership-owner-good"]
            self.assertEqual(row["accuracy"], 0.5)
            self.assertEqual(row["llm_turns"], 2)
            self.assertEqual(row["estimated_output_tokens"], 40)
            self.assertEqual(row["avg_llm_turns"], 1.0)
            self.assertEqual(row["avg_estimated_output_tokens"], 20.0)
            self.assertFalse(row["saturation_candidate"])

    def test_project_summary_reads_default_metrics_eval_output_logs(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            record_eval_case_result(
                "headless-prose-quality",
                passed=True,
                base_dir=root / ".metrics" / "evals" / "run-1",
            )

            summary = collect_eval_summary(
                cwd=root,
                saturation_days=30,
                saturation_min_runs=1,
            )

            self.assertIn("headless-prose-quality", summary["cases"])


class ReportFormatTests(unittest.TestCase):
    def test_report_marks_guard_and_eval_candidates(self) -> None:
        guard_summary = {
            "idle_days": 30,
            "guards": {
                "catastrophic-gate": {
                    "count": 0,
                    "last_ts": None,
                    "categories": {},
                    "sources": [],
                    "reassessment_candidate": True,
                    "observation_status": "observed",
                }
            },
        }
        eval_summary = {
            "saturation_days": 30,
            "saturation_min_runs": 2,
            "cases": {
                "shorts-real-spec": {
                    "attempts": 2,
                    "passes": 2,
                    "accuracy": 1.0,
                    "llm_turns": 4,
                    "estimated_output_tokens": 120,
                    "avg_llm_turns": 2.0,
                    "avg_estimated_output_tokens": 60.0,
                    "last_ts": "2026-07-04T00:00:00Z",
                    "saturation_candidate": True,
                    "failure_stages": {},
                }
            },
            "token_estimate_basis": "utf8_bytes/4_lower_bound",
        }

        report = format_telemetry_report(guard_summary, eval_summary)
        self.assertIn("재평가 후보", report)
        self.assertIn("노후 후보", report)
        self.assertIn("avg_turns=2.0", report)
        self.assertIn("avg_tokens≈60", report)
        self.assertIn("토큰 추정 하한", report)

    def test_report_marks_observation_insufficient(self) -> None:
        guard_summary = {
            "idle_days": 30,
            "since_days": 7,
            "guards": {
                "catastrophic-gate": {
                    "count": 0,
                    "last_ts": None,
                    "categories": {},
                    "sources": [],
                    "reassessment_candidate": False,
                    "observation_status": "insufficient_observation",
                }
            },
        }

        report = format_telemetry_report(guard_summary)

        self.assertIn("scan window: 7d", report)
        self.assertIn("관측 부족", report)

    def test_report_marks_flaky_candidate(self) -> None:
        guard_summary = {"idle_days": 30, "guards": {}}
        eval_summary = {
            "saturation_days": 30,
            "saturation_min_runs": 3,
            "cases": {
                "flow-ownership-entrypoint-bad": {
                    "attempts": 3,
                    "passes": 2,
                    "accuracy": 2 / 3,
                    "avg_llm_turns": 2.0,
                    "avg_estimated_output_tokens": 60.0,
                    "last_ts": "2026-07-05T00:00:00Z",
                    "saturation_candidate": False,
                    "flaky_candidate": True,
                    "failure_stages": {},
                }
            },
            "token_estimate_basis": "utf8_bytes/4_lower_bound",
        }

        report = format_telemetry_report(guard_summary, eval_summary)

        self.assertIn("flaky 후보", report)
        self.assertIn("2/3", report)


if __name__ == "__main__":
    unittest.main()

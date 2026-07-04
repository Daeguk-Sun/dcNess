"""guard telemetry append/read/summary contracts (#875)."""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from harness.guard_telemetry import (
    TELEMETRY_NAME,
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
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["kind"], "guard_hit")
            self.assertEqual(events[0]["guard"], "catastrophic-gate")
            self.assertEqual(events[0]["category"], "order_gate")

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
            self.assertEqual(events[0]["guard"], "git-pre-commit")
            self.assertEqual(events[0]["source"], "git_hook")


class GuardSummaryTests(unittest.TestCase):
    def test_summary_includes_known_zero_hit_guards_as_candidates(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            summary = collect_guard_summary(
                cwd=root,
                known_guards=("catastrophic-gate",),
                idle_days=30,
            )

            self.assertEqual(summary["guards"]["catastrophic-gate"]["count"], 0)
            self.assertTrue(
                summary["guards"]["catastrophic-gate"]["reassessment_candidate"]
            )

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

    def test_default_report_known_guards_exclude_self_only_pre_commit(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            summary = collect_guard_summary(cwd=root, idle_days=30)

            self.assertIn("git-commit-msg", summary["guards"])
            self.assertIn("git-pre-push", summary["guards"])
            self.assertNotIn("git-pre-commit", summary["guards"])


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
            self.assertEqual(events[0]["kind"], "eval_case_result")
            self.assertEqual(events[0]["case"], "headless-prose-quality")
            self.assertTrue(events[0]["passed"])
            self.assertEqual(events[0]["llm_turns"], 2)
            self.assertEqual(events[0]["estimated_output_tokens"], 50)

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
                }
            },
        }

        report = format_telemetry_report(guard_summary, eval_summary)
        self.assertIn("재평가 후보", report)
        self.assertIn("노후 후보", report)
        self.assertIn("avg_turns=2.0", report)
        self.assertIn("avg_tokens≈60", report)


if __name__ == "__main__":
    unittest.main()

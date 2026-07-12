"""Judge calibration report contracts (#894)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "evals" / "calibrate_judge.py"


class JudgeCalibrationTests(unittest.TestCase):
    def _command(
        self,
        run_dir: Path,
        *extra: str,
        golden_version: str = "test-golden-v1",
        subset_version: str = "test-subset-v1",
    ) -> list[str]:
        return [
            sys.executable,
            str(SCRIPT),
            str(run_dir),
            "--expect-golden-version",
            golden_version,
            "--expect-subset-version",
            subset_version,
            *extra,
        ]

    def _golden(
        self,
        *,
        case: str,
        run: int,
        report: Path,
        expectations: dict[str, str],
        verification_status: str = "verified",
        golden_version: str = "test-golden-v1",
        subset_version: str = "test-subset-v1",
    ) -> dict:
        return {
            "schema_version": 2,
            "golden_version": golden_version,
            "subset_version": subset_version,
            "verification_status": verification_status,
            "measurement": {
                "model": "fixture-model",
                "prompt_version": "fixture-prompt-v1",
                "measured_at": "2026-07-05T08:28:27Z",
            },
            "labels": [
                {
                    "case": case,
                    "run": run,
                    "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
                    "expectations": expectations,
                    "reasons": {
                        key: f"human reason for {key}" for key in expectations
                    },
                }
            ],
        }

    def test_reports_review_candidate_when_agreement_is_below_threshold(self) -> None:
        with TemporaryDirectory() as td:
            run_dir = Path(td)
            case_dir = run_dir / "shorts-real-spec"
            case_dir.mkdir()
            (case_dir / "run-1-judge.md").write_text(
                "OK E1\nMISS E2\nRESULT: FAIL\n",
                encoding="utf-8",
            )
            report = case_dir / "run-1-report.md"
            report.write_text("blind report evidence\n", encoding="utf-8")
            golden = run_dir / "judge-golden.json"
            golden.write_text(
                json.dumps(
                    self._golden(
                        case="shorts-real-spec",
                        run=1,
                        report=report,
                        expectations={"E1": "OK", "E2": "OK"},
                    )
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                self._command(run_dir, "--min-agreement", "1.0"),
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("agreement: 1/3 (33.3%)", result.stdout)
            self.assertIn("judge_review_candidate: YES", result.stdout)
            self.assertIn("attempts: 1", result.stdout)
            self.assertIn("judge_or_criteria_disagreement", result.stdout)
            self.assertIn("shorts-real-spec run 1 E2", result.stdout)
            self.assertIn("No judge settings were changed.", result.stdout)

    def test_json_report_passes_when_threshold_is_met(self) -> None:
        with TemporaryDirectory() as td:
            run_dir = Path(td)
            case_dir = run_dir / "flow-ownership-owner-good"
            case_dir.mkdir()
            (case_dir / "run-2-judge.md").write_text(
                "OK E1 - accepted by the report\nOK `E2`\nRESULT: PASS\n",
                encoding="utf-8",
            )
            report = case_dir / "run-2-report.md"
            report.write_text("blind report evidence\n", encoding="utf-8")
            golden = run_dir / "judge-golden.json"
            golden.write_text(
                json.dumps(
                    self._golden(
                        case="flow-ownership-owner-good",
                        run=2,
                        report=report,
                        expectations={"E1": "OK", "E2": "OK"},
                    )
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                self._command(run_dir, "--json", "--min-agreement", "1.0"),
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["agreement"], 1.0)
            self.assertFalse(payload["judge_review_candidate"])
            self.assertEqual(payload["totals"], {"matches": 3, "comparisons": 3})
            self.assertEqual(payload["attempts"], 1)
            self.assertEqual(payload["golden_version"], "test-golden-v1")
            self.assertEqual(payload["subset_version"], "test-subset-v1")
            self.assertEqual(payload["measurement"]["model"], "fixture-model")

    def test_unversioned_or_unverified_golden_cannot_pass(self) -> None:
        with TemporaryDirectory() as td:
            run_dir = Path(td)
            case_dir = run_dir / "shorts-real-spec"
            case_dir.mkdir()
            report = case_dir / "run-1-report.md"
            report.write_text("blind report\n", encoding="utf-8")
            (case_dir / "run-1-judge.md").write_text(
                "OK E1\nRESULT: PASS\n", encoding="utf-8"
            )
            golden = run_dir / "judge-golden.json"
            pending = self._golden(
                case="shorts-real-spec",
                run=1,
                report=report,
                expectations={"E1": "OK"},
                verification_status="pending_owner_confirmation",
            )
            golden.write_text(json.dumps(pending), encoding="utf-8")

            pending_result = subprocess.run(
                self._command(run_dir),
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            del pending["golden_version"]
            golden.write_text(json.dumps(pending), encoding="utf-8")
            unversioned_result = subprocess.run(
                self._command(run_dir),
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

        self.assertEqual(pending_result.returncode, 2)
        self.assertIn("not human-verified", pending_result.stderr)
        self.assertEqual(unversioned_result.returncode, 2)
        self.assertIn("golden_version is required", unversioned_result.stderr)

    def test_report_digest_mismatch_is_unmeasured_not_calibration_pass(self) -> None:
        with TemporaryDirectory() as td:
            run_dir = Path(td)
            case_dir = run_dir / "shorts-real-spec"
            case_dir.mkdir()
            report = case_dir / "run-1-report.md"
            report.write_text("original blind report\n", encoding="utf-8")
            (case_dir / "run-1-judge.md").write_text(
                "OK E1\nRESULT: PASS\n", encoding="utf-8"
            )
            golden = run_dir / "judge-golden.json"
            golden.write_text(
                json.dumps(
                    self._golden(
                        case="shorts-real-spec",
                        run=1,
                        report=report,
                        expectations={"E1": "OK"},
                    )
                ),
                encoding="utf-8",
            )
            report.write_text("different blind report\n", encoding="utf-8")

            result = subprocess.run(
                self._command(run_dir, "--json"),
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["artifacts"][0]["status"], "판정 불가")
        self.assertEqual(payload["invalid_artifacts"][0]["reason"], "report_sha256_mismatch")

    def test_agreed_human_miss_is_agent_regression_not_judge_disagreement(self) -> None:
        with TemporaryDirectory() as td:
            run_dir = Path(td)
            case_dir = run_dir / "incident-case"
            case_dir.mkdir()
            report = case_dir / "run-1-report.md"
            report.write_text("blind report missed the incident\n", encoding="utf-8")
            (case_dir / "run-1-judge.md").write_text(
                "MISS E1\nRESULT: FAIL\n", encoding="utf-8"
            )
            golden = run_dir / "judge-golden.json"
            golden.write_text(
                json.dumps(
                    self._golden(
                        case="incident-case",
                        run=1,
                        report=report,
                        expectations={"E1": "MISS"},
                    )
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                self._command(run_dir, "--json"),
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["agreement"], 1.0)
        self.assertEqual(payload["mismatches"], [])
        self.assertEqual(
            payload["agent_behavior_regressions"][0]["classification"],
            "agent_behavior_regression",
        )

    def test_expected_version_mismatch_cannot_pass(self) -> None:
        with TemporaryDirectory() as td:
            run_dir = Path(td)
            case_dir = run_dir / "incident-case"
            case_dir.mkdir()
            report = case_dir / "run-1-report.md"
            report.write_text("blind report\n", encoding="utf-8")
            (case_dir / "run-1-judge.md").write_text(
                "OK E1\nRESULT: PASS\n", encoding="utf-8"
            )
            golden = run_dir / "judge-golden.json"
            golden.write_text(
                json.dumps(
                    self._golden(
                        case="incident-case",
                        run=1,
                        report=report,
                        expectations={"E1": "OK"},
                    )
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                self._command(run_dir, subset_version="different-subset-v2"),
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("subset version mismatch", result.stderr)

    def test_expected_versions_are_required(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "/tmp/not-used"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("--expect-golden-version", result.stderr)
        self.assertIn("--expect-subset-version", result.stderr)

    def test_incomplete_judge_output_is_unmeasured_even_at_zero_threshold(self) -> None:
        with TemporaryDirectory() as td:
            run_dir = Path(td)
            case_dir = run_dir / "incident-case"
            case_dir.mkdir()
            report = case_dir / "run-1-report.md"
            report.write_text("blind report\n", encoding="utf-8")
            (case_dir / "run-1-judge.md").write_text(
                "OK E1\n", encoding="utf-8"
            )
            (run_dir / "judge-golden.json").write_text(
                json.dumps(
                    self._golden(
                        case="incident-case",
                        run=1,
                        report=report,
                        expectations={"E1": "OK", "E2": "OK"},
                    )
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                self._command(run_dir, "--json", "--min-agreement", "0.0"),
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["artifacts"][0]["status"], "판정 불가")
        self.assertEqual(payload["artifacts"][0]["comparisons"], 0)
        self.assertEqual(
            payload["invalid_artifacts"][0]["reason"],
            "judge_output_incomplete",
        )
        self.assertEqual(
            payload["invalid_artifacts"][0]["missing"], ["E2", "RESULT"]
        )


if __name__ == "__main__":
    unittest.main()

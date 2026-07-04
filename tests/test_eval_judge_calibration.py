"""Judge calibration report contracts (#894)."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "evals" / "calibrate_judge.py"


class JudgeCalibrationTests(unittest.TestCase):
    def test_reports_review_candidate_when_agreement_is_below_threshold(self) -> None:
        with TemporaryDirectory() as td:
            run_dir = Path(td)
            case_dir = run_dir / "shorts-real-spec"
            case_dir.mkdir()
            (case_dir / "run-1-judge.md").write_text(
                "OK E1\nMISS E2\nRESULT: FAIL\n",
                encoding="utf-8",
            )
            golden = run_dir / "judge-golden.json"
            golden.write_text(
                json.dumps(
                    {
                        "labels": [
                            {
                                "case": "shorts-real-spec",
                                "run": 1,
                                "expectations": {"E1": "OK", "E2": "OK"},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(run_dir),
                    "--min-agreement",
                    "1.0",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertIn("agreement: 1/3 (33.3%)", result.stdout)
            self.assertIn("judge_review_candidate: YES", result.stdout)
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
            golden = run_dir / "judge-golden.json"
            golden.write_text(
                json.dumps(
                    {
                        "labels": [
                            {
                                "case": "flow-ownership-owner-good",
                                "run": 2,
                                "expectations": {"E1": "OK", "E2": "OK"},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(run_dir),
                    "--json",
                    "--min-agreement",
                    "1.0",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["agreement"], 1.0)
            self.assertFalse(payload["judge_review_candidate"])
            self.assertEqual(payload["totals"], {"matches": 3, "comparisons": 3})


if __name__ == "__main__":
    unittest.main()

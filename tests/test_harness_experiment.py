"""Approved harness-lightweight experiment orchestration contracts (#1088)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "evals" / "harness_experiment.py"


def _trace(path: Path, *, variant: str, input_tokens: int, ac_passed: int = 2) -> None:
    answer = {
        "product_ac": {"passed": ac_passed, "total": 2},
        "must_fix_count": 0,
        "regression_count": 0,
        "human_recovery_count": 0,
    }
    rows = [
        {
            "meta": {
                "task": "fixture-task",
                "variant": variant,
                "sandbox": "<SANDBOX>/repo",
            }
        },
        {
            "elapsed_ms": 10,
            "event": {
                "type": "system",
                "subtype": "init",
                "session_id": f"run-{variant}",
                "model": "test-model",
            },
        },
        {
            "elapsed_ms": 1000,
            "event": {
                "type": "result",
                "result": f"```json\n{json.dumps(answer)}\n```",
                "session_id": f"run-{variant}",
                "num_turns": 1,
                "usage": {"input_tokens": input_tokens, "output_tokens": 10},
            },
        },
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


def _plan(tmp: Path, *, safety_class: str = "optional") -> Path:
    fixture = tmp / "fixture-source"
    fixture.mkdir()
    (fixture / "README.md").write_text("frozen fixture\n", encoding="utf-8")
    plan = {
        "schema_version": 1,
        "candidate": {
            "id": "read-repeat-metadata",
            "component": "반복 read 안내 메타데이터",
            "optional_reason": "작업 순서나 접근 영역을 강제하지 않는 선택형 안내",
            "telemetry": {
                "pattern": "READ_REPEAT_HIGH",
                "count": 8,
                "finished_run_denominator": 5,
                "source_project_count": 2,
            },
            "expected_saving_metric": "input_tokens",
            "meaningful_reduction": {"absolute": 20, "relative": 0.1},
        },
        "safety_class": safety_class,
        "fixture_source": str(fixture),
        "task": "저장소를 읽고 제품 수용 기준 두 항목을 판정한다.",
        "baseline_condition": "현재 선택형 반복 read 안내와 상세 메타데이터를 모두 유지한다.",
        "variant_condition": "반복 read 안내를 줄인다.",
        "provider": {"name": "test-provider", "model": "test-model"},
        "execution_month": "2026-07",
    }
    path = tmp / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path


class HarnessExperimentTests(unittest.TestCase):
    def _run(
        self, plan: Path, output: Path, ledger: Path
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--plan",
                str(plan),
                "--output-dir",
                str(output),
                "--ledger",
                str(ledger),
                "--from-traces",
                "--json",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_first_clear_pair_builds_and_validates_provenance_record(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            plan = _plan(tmp)
            output = tmp / "output"
            _trace(
                output / "pair1-baseline.jsonl",
                variant="baseline",
                input_tokens=200,
            )
            _trace(
                output / "pair1-variant.jsonl",
                variant="variant",
                input_tokens=100,
            )

            result = self._run(plan, output, tmp / "trial-ledger.jsonl")

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["decision"], "remove")
            self.assertEqual(report["trial_count"], 2)
            record = json.loads(
                (output / "record.json").read_text(encoding="utf-8")
            )
            self.assertEqual(record["schema_version"], 2)
            for trial in record["paired_screening"]["trials"]:
                self.assertTrue(trial["run_id"].startswith("run-"))
                self.assertRegex(trial["raw_trace_sha256"], r"^[0-9a-f]{64}$")
                self.assertRegex(trial["artifact_sha256"], r"^[0-9a-f]{64}$")
                self.assertNotEqual(
                    trial["raw_trace_sha256"], trial["artifact_sha256"]
                )
                self.assertTrue(Path(trial["artifact"]).is_file())
                self.assertIn("read_trace", trial)
                self.assertEqual(trial["model"], "test-model")
                self.assertEqual(
                    trial["provider"], "claude -p --safe-mode (headless)"
                )
                self.assertEqual(trial["requested_provider"], "test-provider")
            self.assertFalse((tmp / "trial-ledger.jsonl").exists())

            ledger = tmp / "trial-ledger.jsonl"
            ledger_rows = []
            for index, trial in enumerate(record["paired_screening"]["trials"]):
                attempt_id = f"attempt-{index}"
                ledger_rows.extend(
                    [
                        {
                            "kind": "trial_started",
                            "execution_month": "2026-07",
                            "attempt_id": attempt_id,
                        },
                        {
                            "kind": "trial_result",
                            "execution_month": "2026-07",
                            "attempt_id": attempt_id,
                            "raw_trace_sha256": trial["raw_trace_sha256"],
                        },
                    ]
                )
            ledger.write_text(
                "".join(json.dumps(row) + "\n" for row in ledger_rows),
                encoding="utf-8",
            )
            rebuilt = self._run(plan, output, ledger)
            self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr)
            rebuilt_record = json.loads(
                (output / "record.json").read_text(encoding="utf-8")
            )
            self.assertEqual(rebuilt_record["budget"]["used_before"], 0)

    def test_monthly_four_trial_cap_blocks_a_new_pair(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            plan = _plan(tmp)
            output = tmp / "output"
            _trace(
                output / "pair1-baseline.jsonl",
                variant="baseline",
                input_tokens=200,
            )
            _trace(
                output / "pair1-variant.jsonl",
                variant="variant",
                input_tokens=100,
            )
            ledger = tmp / "trial-ledger.jsonl"
            ledger.write_text(
                "".join(
                    json.dumps(
                        {
                            "kind": "trial_started",
                            "execution_month": "2026-07",
                            "attempt_id": str(index),
                        }
                    )
                    + "\n"
                    for index in range(3)
                ),
                encoding="utf-8",
            )

            result = self._run(plan, output, ledger)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("monthly_trial_cap_exceeded", result.stderr)

    def test_hard_guard_candidate_is_rejected_before_trial(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            result = self._run(
                _plan(tmp, safety_class="hard_guard"),
                tmp / "output",
                tmp / "trial-ledger.jsonl",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("candidate_must_be_optional", result.stderr)


if __name__ == "__main__":
    unittest.main()

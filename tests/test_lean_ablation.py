"""Lean ablation protocol and recorded pilot contract tests (#1069)."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "evals" / "lean_ablation.py"
PILOT = ROOT / "evals" / "lean-ablation" / "tool-repeat-lesson-metadata.json"


def _trial(variant: str, *, tokens: int, ac_passed: int = 2) -> dict:
    return {
        "variant": variant,
        "task_id": "frozen-read-reuse-v1",
        "input_sha256": "a" * 64,
        "model": "gpt-5.2-codex",
        "provider": "openai-codex",
        "product_ac": {"passed": ac_passed, "total": 2},
        "must_fix_count": 0,
        "regression_count": 0,
        "human_intervention_count": 0,
        "input_tokens": tokens,
        "output_tokens": 100,
        "wall_clock_seconds": 10.0,
        "evidence": "evals/lean-ablation/evidence/example.jsonl",
    }


def _record(trials: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "candidate": {
            "id": "tool-repeat-lesson-metadata",
            "component": "TOOL_REPEAT_HIGH lesson hits/last/evidence prompt metadata",
            "optional_reason": "advisory context; not an order or access guard",
            "telemetry": {
                "pattern": "TOOL_REPEAT_HIGH",
                "count": 42,
                "finished_run_denominator": 26,
                "source_project_count": 2,
            },
            "expected_saving_metric": "input_tokens",
            "meaningful_reduction": {"absolute": 40, "relative": 0.05},
        },
        "safety": {
            "hard_guards_excluded": [
                "order",
                "file-boundary",
                "external-state",
                "tdd",
            ],
            "live_hard_guard_disabled": False,
        },
        "deterministic": {
            "passed": True,
            "command": "python3.11 evals/lean_ablation.py RECORD",
            "baseline_prompt_bytes": 320,
            "variant_prompt_bytes": 180,
        },
        "shadow": {
            "passed": True,
            "live_product_affected": False,
            "baseline_prompt_sha256": "b" * 64,
            "variant_prompt_sha256": "c" * 64,
        },
        "budget": {
            "execution_month": "2026-07",
            "monthly_cap": 4,
            "used_before": 0,
            "agent_effectiveness_screening_month": None,
        },
        "paired_screening": {"trials": trials},
        "decision": "remove",
        "follow_up": "drop volatile metadata while retaining the lesson text",
        "limitations": ["single frozen fixture", "not public superiority evidence"],
    }


class LeanAblationProtocolTests(unittest.TestCase):
    def _run(self, record: dict) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            return subprocess.run(
                ["python3.11", str(RUNNER), str(path), "--json"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )

    def test_clear_first_pair_accepts_remove_without_extra_trials(self) -> None:
        result = self._run(
            _record(
                [
                    _trial("baseline", tokens=1000),
                    _trial("variant", tokens=850),
                ]
            )
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["decision"], "remove")
        self.assertEqual(report["trial_count"], 2)
        self.assertEqual(report["epic_monthly_trial_total"], 2)

    def test_quality_loss_forces_keep_even_when_variant_is_cheaper(self) -> None:
        record = _record(
            [
                _trial("baseline", tokens=1000),
                _trial("variant", tokens=800, ac_passed=1),
            ]
        )
        record["decision"] = "keep"

        result = self._run(record)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["decision"], "keep")

    def test_no_saving_is_a_clear_keep_without_extra_trials(self) -> None:
        record = _record(
            [
                _trial("baseline", tokens=1000),
                _trial("variant", tokens=1100),
            ]
        )
        record["decision"] = "keep"

        result = self._run(record)

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["decision"], "keep")
        self.assertEqual(report["trial_count"], 2)

    def test_ambiguous_first_pair_requires_one_more_pair(self) -> None:
        record = _record(
            [
                _trial("baseline", tokens=1000),
                _trial("variant", tokens=980),
            ]
        )
        record["decision"] = "hold"

        result = self._run(record)

        self.assertEqual(result.returncode, 2)
        self.assertIn("additional_pair_required", result.stderr)

    def test_four_trial_cap_allows_hold_after_ambiguous_repeat(self) -> None:
        record = _record(
            [
                _trial("baseline", tokens=1000),
                _trial("variant", tokens=980),
                _trial("baseline", tokens=990),
                _trial("variant", tokens=970),
            ]
        )
        record["decision"] = "hold"

        result = self._run(record)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["decision"], "hold")

    def test_rejects_budget_collision_or_live_hard_guard_ablation(self) -> None:
        record = _record(
            [_trial("baseline", tokens=1000), _trial("variant", tokens=850)]
        )
        record["budget"]["agent_effectiveness_screening_month"] = "2026-07"
        record["safety"]["live_hard_guard_disabled"] = True

        result = self._run(record)

        self.assertEqual(result.returncode, 2)
        self.assertIn("same_month_agent_effectiveness_screening", result.stderr)
        self.assertIn("live_hard_guard_disabled", result.stderr)

    def test_recorded_pilot_is_self_consistent(self) -> None:
        result = subprocess.run(
            ["python3.11", str(RUNNER), str(PILOT), "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertIn(report["decision"], {"keep", "remove", "hold"})
        self.assertLessEqual(report["epic_monthly_trial_total"], 4)


if __name__ == "__main__":
    unittest.main()

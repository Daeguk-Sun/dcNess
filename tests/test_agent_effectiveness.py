"""Deterministic agent-effectiveness measurement contracts for issue #1070."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "harness" / "outcome_scorecard.py"
PILOT = (
    ROOT
    / "evals"
    / "agent-effectiveness"
    / "cartography-sanity-replay.json"
)


def _quality(*, context_rework: int, cross_session_resume: bool) -> dict:
    return {
        "product_ac": {"passed": 2, "total": 2},
        "must_fix_count": 0,
        "regression_count": 0,
        "human_recovery_count": 0,
        "context_rework_count": context_rework,
        "cross_session_resume": cross_session_resume,
    }


def _cold_run(variant: str) -> dict:
    expected = {
        "ssot": "docs/architecture.md",
        "runtime_entrypoint": "src/app.py",
        "capability_owner": "src/notifications/dispatcher.py",
        "decision": "docs/decisions/0001-notification-routing.md",
    }
    if variant == "baseline":
        visited = [
            {"path": "README.md", "tool": "read", "bytes": 900, "elapsed_ms": 10},
            {
                "path": "legacy/notification_router.py",
                "tool": "read",
                "bytes": 700,
                "elapsed_ms": 20,
            },
            {"path": expected["ssot"], "tool": "read", "bytes": 600, "elapsed_ms": 30},
            {
                "path": expected["runtime_entrypoint"],
                "tool": "read",
                "bytes": 500,
                "elapsed_ms": 40,
            },
            {
                "path": expected["capability_owner"],
                "tool": "read",
                "bytes": 400,
                "elapsed_ms": 50,
            },
            {
                "path": expected["decision"],
                "tool": "read",
                "bytes": 300,
                "elapsed_ms": 60,
            },
        ]
    else:
        visited = [
            {"path": expected["ssot"], "tool": "read", "bytes": 600, "elapsed_ms": 10},
            {
                "path": expected["runtime_entrypoint"],
                "tool": "read",
                "bytes": 500,
                "elapsed_ms": 20,
            },
            {
                "path": expected["capability_owner"],
                "tool": "read",
                "bytes": 400,
                "elapsed_ms": 30,
            },
            {
                "path": expected["decision"],
                "tool": "read",
                "bytes": 300,
                "elapsed_ms": 40,
            },
        ]
    return {
        "variant": variant,
        "reported_coordinates": expected,
        "visited": visited,
        "quality": _quality(
            context_rework=1 if variant == "baseline" else 0,
            cross_session_resume=variant == "current",
        ),
        "cost": {
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0,
            "basis": "deterministic replay; no LLM invocation",
        },
    }


def _refactor_run(variant: str) -> dict:
    classifications = {
        "legacy/notification_router.py": "stale_old_path",
        "src/runtime_handler.py": "framework_reachable",
        "src/extension_port.py": "intentional_seam",
    }
    impact = [
        "src/notifications/dispatcher.py",
        "src/app.py",
        "tests/test_notifications.py",
    ]
    if variant == "baseline":
        classifications = {
            "legacy/notification_router.py": "framework_reachable",
            "src/runtime_handler.py": "framework_reachable",
        }
        impact = ["src/notifications/dispatcher.py", "src/app.py", "README.md"]
    return {
        "variant": variant,
        "classifications": classifications,
        "observed_impact": impact,
        "tool_calls": 7 if variant == "baseline" else 5,
        "read_bytes": 3600 if variant == "baseline" else 2800,
        "quality": _quality(
            context_rework=1 if variant == "baseline" else 0,
            cross_session_resume=variant == "current",
        ),
        "cost": {
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0,
            "basis": "deterministic replay; no LLM invocation",
        },
    }


def _record() -> dict:
    return {
        "schema_version": 1,
        "measurement": {
            "id": "agent-effectiveness-fixture-v1",
            "measured_at": "2026-07-12T10:00:00Z",
            "source": "stored deterministic replay",
            "source_count": 1,
            "limitations": [
                "synthetic repository fixture",
                "no live LLM trial",
                "not public superiority evidence",
            ],
        },
        "conditions": {
            "repo_type": "frozen synthetic application",
            "provider": "deterministic-replay",
            "model": "none",
            "harness_variants": ["baseline", "current"],
        },
        "budget": {
            "execution_month": "2026-07",
            "monthly_cap": 4,
            "used_before": 2,
            "new_llm_trials": 0,
            "lean_ablation_screening_month": "2026-07",
        },
        "fixture_root": "fixture",
        "fixtures": {},
        "tasks": [
            {
                "id": "cold-start-notification-route",
                "type": "cold_start",
                "expected_coordinates": {
                    "ssot": "docs/architecture.md",
                    "runtime_entrypoint": "src/app.py",
                    "capability_owner": "src/notifications/dispatcher.py",
                    "decision": "docs/decisions/0001-notification-routing.md",
                },
                "runs": [_cold_run("baseline"), _cold_run("current")],
            },
            {
                "id": "notification-router-replacement",
                "type": "refactor_replacement",
                "expected_classifications": {
                    "legacy/notification_router.py": "stale_old_path",
                    "src/runtime_handler.py": "framework_reachable",
                    "src/extension_port.py": "intentional_seam",
                },
                "expected_impact": [
                    "src/notifications/dispatcher.py",
                    "src/app.py",
                    "tests/test_notifications.py",
                ],
                "runs": [_refactor_run("baseline"), _refactor_run("current")],
            },
        ],
    }


class AgentEffectivenessContractTests(unittest.TestCase):
    def _run(
        self, record: dict, *, tamper_fixture: bool = False
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture_root = root / "fixture"
            shutil.copytree(
                ROOT / "evals" / "agent-effectiveness" / "fixture", fixture_root
            )
            record["fixture_root"] = "fixture"
            record["fixtures"] = {
                str(path.relative_to(fixture_root)): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in sorted(fixture_root.rglob("*"))
                if path.is_file()
            }
            if tamper_fixture:
                (fixture_root / "docs" / "architecture.md").write_text(
                    "tampered\n", encoding="utf-8"
                )
            projects_file = root / "projects.json"
            projects_file.write_text(
                json.dumps({"version": 1, "projects": []}), encoding="utf-8"
            )
            record_file = root / "record.json"
            record_file.write_text(json.dumps(record), encoding="utf-8")
            return subprocess.run(
                [
                    "python3.11",
                    str(RUNNER),
                    "--projects-file",
                    str(projects_file),
                    "--agent-effectiveness-record",
                    str(record_file),
                    "--json",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )

    def test_replays_both_task_types_and_reports_improvement_without_quality_loss(
        self,
    ) -> None:
        result = self._run(_record())

        self.assertEqual(result.returncode, 0, result.stderr)
        effectiveness = json.loads(result.stdout)["agent_effectiveness"]
        self.assertEqual(effectiveness["status"], "관측")
        self.assertEqual(effectiveness["source_count"], 1)
        self.assertEqual(effectiveness["task_count"], 2)
        self.assertEqual(effectiveness["denominator"], 4)
        self.assertTrue(effectiveness["improved"])
        self.assertFalse(effectiveness["quality_worse"])
        cold = effectiveness["tasks"][0]
        self.assertEqual(cold["current"]["coordinate_accuracy"], "4/4")
        self.assertEqual(cold["current"]["wrong_path_count"], 0)
        self.assertEqual(cold["current"]["first_correct_target_tool_count"], 3)
        self.assertEqual(cold["current"]["first_correct_target_read_bytes"], 1500)
        self.assertLess(cold["current"]["tool_calls"], cold["baseline"]["tool_calls"])
        refactor = effectiveness["tasks"][1]
        self.assertEqual(refactor["current"]["classification_accuracy"], "3/3")
        self.assertEqual(refactor["current"]["missed_impact"], [])
        self.assertEqual(refactor["current"]["excess_impact"], [])
        self.assertEqual(effectiveness["cost"]["input_tokens"], 0)
        self.assertEqual(effectiveness["cost"]["cost_usd"], 0)

    def test_rejects_current_coordinate_mismatch(self) -> None:
        record = _record()
        record["tasks"][0]["runs"][1]["reported_coordinates"]["capability_owner"] = (
            "legacy/notification_router.py"
        )

        result = self._run(record)

        self.assertEqual(result.returncode, 2)
        self.assertIn("current_coordinate_mismatch:capability_owner", result.stderr)

    def test_rejects_tampered_fixture_bundle(self) -> None:
        result = self._run(_record(), tamper_fixture=True)

        self.assertEqual(result.returncode, 2)
        self.assertIn("fixture_sha256_mismatch:docs/architecture.md", result.stderr)

    def test_rejects_same_month_llm_trial_collision_and_budget_overrun(self) -> None:
        record = _record()
        record["budget"]["new_llm_trials"] = 3

        result = self._run(record)

        self.assertEqual(result.returncode, 2)
        self.assertIn("same_month_lean_ablation_collision", result.stderr)
        self.assertIn("monthly_trial_cap_exceeded", result.stderr)

    def test_rejects_product_quality_regression_even_if_navigation_is_cheaper(self) -> None:
        record = _record()
        record["tasks"][1]["runs"][1]["quality"]["product_ac"]["passed"] = 1

        result = self._run(record)

        self.assertEqual(result.returncode, 2)
        self.assertIn("current_quality_worse", result.stderr)

    def test_checked_in_replay_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            projects_file = Path(directory) / "projects.json"
            projects_file.write_text(
                json.dumps({"version": 1, "projects": []}), encoding="utf-8"
            )
            result = subprocess.run(
                [
                    "python3.11",
                    str(RUNNER),
                    "--projects-file",
                    str(projects_file),
                    "--agent-effectiveness-record",
                    str(PILOT),
                    "--json",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        effectiveness = json.loads(result.stdout)["agent_effectiveness"]
        self.assertEqual(effectiveness["measurement_id"], "agent-effectiveness-2026-07")
        self.assertEqual(effectiveness["measured_at"], "2026-07-12T10:00:00Z")
        self.assertEqual(effectiveness["monthly_llm_trial_total"], 2)

    def test_scorecard_docs_record_replay_conditions_denominators_and_limits(self) -> None:
        contract = (ROOT / "docs" / "plugin" / "outcome-scorecard.md").read_text(
            encoding="utf-8"
        )
        baseline = (ROOT / "docs" / "internal" / "outcome-baseline.md").read_text(
            encoding="utf-8"
        )
        for term in (
            "--agent-effectiveness-record",
            "첫 올바른 대상까지의 tool/read",
            "영향 범위 과다 포함",
            "cross-session",
            "제품 AC",
        ):
            self.assertIn(term, contract)
        for evidence in (
            "agent-effectiveness-2026-07",
            "deterministic-replay",
            "비교 trial 4",
            "source fixture 1",
            "task 2",
            "input/output token `0/0`",
            "cost `$0.00`",
            "2026-07 epic 공통 추가 LLM trial 누계 `2/4`",
            "문서 수",
            "synthetic",
        ):
            self.assertIn(evidence, baseline)


if __name__ == "__main__":
    unittest.main()

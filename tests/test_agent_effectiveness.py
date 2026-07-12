"""Deterministic agent-effectiveness measurement contracts for issue #1070."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

from evals import agent_effectiveness_measure as measure
from harness.agent_effectiveness import evaluate_record


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "harness" / "outcome_scorecard.py"
PILOT = (
    ROOT
    / "evals"
    / "agent-effectiveness"
    / "cartography-sanity-replay.json"
)
LIVE = (
    ROOT
    / "evals"
    / "agent-effectiveness"
    / "cartography-sanity-real.json"
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
        "tool_calls": len(visited),
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
        trial_metadata = json.loads(result.stdout)["trial_metadata"]
        self.assertEqual(trial_metadata["source_count"], 1)
        self.assertNotIn("source_project_count", trial_metadata)

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

    def test_rejects_extra_current_classification_outside_expected_set(self) -> None:
        record = _record()
        record["tasks"][1]["runs"][1]["classifications"]["README.md"] = (
            "stale_old_path"
        )

        result = self._run(record)

        self.assertEqual(result.returncode, 2)
        self.assertIn("current_classification_scope_mismatch", result.stderr)

    def test_rejects_extra_coordinate_key_or_nonmonotonic_trace(self) -> None:
        record = _record()
        current = record["tasks"][0]["runs"][1]
        current["reported_coordinates"]["extra"] = "README.md"
        current["visited"][2]["elapsed_ms"] = 5

        result = self._run(record)

        self.assertEqual(result.returncode, 2)
        self.assertIn("current_coordinate_keys_invalid", result.stderr)
        self.assertIn("current_elapsed_not_monotonic", result.stderr)

    def test_rejects_monthly_trial_budget_overrun(self) -> None:
        record = _record()
        record["budget"]["new_llm_trials"] = 3

        result = self._run(record)

        self.assertEqual(result.returncode, 2)
        self.assertIn("monthly_trial_cap_exceeded", result.stderr)
        # 월 배분 분리 규칙(ablation 과 같은 달 실행 금지)은 2026-07-13 사용자
        # 결정으로 폐지됐다. 예산은 월 cap 초과만 차단한다.
        self.assertNotIn("same_month_lean_ablation_collision", result.stderr)

    def test_rejects_self_declared_or_out_of_month_cap_exception(self) -> None:
        record = _record()
        record["budget"]["monthly_cap"] = 100

        result = self._run(record)

        self.assertEqual(result.returncode, 2)
        self.assertIn("monthly_cap_policy_mismatch", result.stderr)

        record = _record()
        record["budget"].update(
            {"execution_month": "2026-08", "monthly_cap": 6}
        )
        result = self._run(record)

        self.assertEqual(result.returncode, 2)
        self.assertIn("monthly_cap_policy_mismatch", result.stderr)

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

    def test_checked_in_live_record_is_reproducible_with_provenance(self) -> None:
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
                    str(LIVE),
                    "--json",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        effectiveness = json.loads(result.stdout)["agent_effectiveness"]
        self.assertEqual(
            effectiveness["measurement_id"], "agent-effectiveness-real-2026-07"
        )
        self.assertEqual(effectiveness["conditions"]["model"], "claude-sonnet-4-6")
        self.assertEqual(effectiveness["new_llm_trials"], 2)
        self.assertEqual(effectiveness["monthly_llm_trial_total"], 6)
        self.assertTrue(effectiveness["improved"])
        self.assertEqual(effectiveness["baseline"]["tool_calls"], 15)
        self.assertEqual(effectiveness["current"]["tool_calls"], 13)
        self.assertEqual(
            effectiveness["unmeasured_quality_fields"],
            [
                "context_rework_count",
                "cross_session_resume",
                "human_recovery_count",
                "must_fix_count",
                "regression_count",
            ],
        )
        self.assertGreater(effectiveness["cost"]["cost_usd"], 0)

        record = json.loads(LIVE.read_text(encoding="utf-8"))
        # 동일 frozen task 증거: synthetic replay record와 fixture hash가 같아야 한다.
        pilot = json.loads(PILOT.read_text(encoding="utf-8"))
        self.assertEqual(record["fixtures"], pilot["fixtures"])
        # provenance 계약: 실제 run 유래 증거(세션 ID, raw trace 파일, SHA-256, 생성 명령).
        provenance = record["provenance"]
        self.assertIn("agent_effectiveness_measure.py", provenance["generation_command"])
        self.assertIn("--from-traces", provenance["rebuild_command"])
        self.assertIn("account/runtime inventory", provenance["trace_redaction"])
        runs = provenance["runs"]
        self.assertEqual(len(runs), 4)
        session_ids = {run["session_id"] for run in runs.values()}
        self.assertEqual(len(session_ids), 4)
        for run in runs.values():
            trace = LIVE.parent / run["trace_file"]
            self.assertTrue(trace.is_file(), trace)
            self.assertEqual(
                hashlib.sha256(trace.read_bytes()).hexdigest(), run["trace_sha256"]
            )
            trace_text = trace.read_text(encoding="utf-8")
            self.assertNotIn("/Users/", trace_text)
            self.assertNotIn('"plugins"', trace_text)
            self.assertNotIn('"uuid"', trace_text)

        with tempfile.TemporaryDirectory() as directory:
            rebuilt_path = Path(directory) / "rebuilt.json"
            rebuild = subprocess.run(
                [
                    "python3.11",
                    str(ROOT / "evals" / "agent_effectiveness_measure.py"),
                    "--model",
                    "sonnet",
                    "--output-dir",
                    str(LIVE.parent / "evidence" / "real-2026-07-attempt2"),
                    "--record-out",
                    str(rebuilt_path),
                    "--from-traces",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(rebuild.returncode, 0, rebuild.stderr)
            self.assertEqual(
                json.loads(rebuilt_path.read_text(encoding="utf-8")),
                record,
            )

    def test_live_record_rejects_missing_provenance(self) -> None:
        record = json.loads(LIVE.read_text(encoding="utf-8"))
        record.pop("provenance")

        _, errors = evaluate_record(record, record_root=LIVE.parent)

        self.assertIn("provenance_must_be_object", errors)
        self.assertIn("provenance_run_set_invalid", errors)

    def test_live_runner_timeout_fires_without_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "claude"
            executable.write_text(
                "#!/usr/bin/env python3\nimport time\ntime.sleep(5)\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)
            output_dir = root / "evidence"
            output_dir.mkdir()
            args = Namespace(output_dir=output_dir, model="sonnet", timeout=0.1)
            started = time.monotonic()

            with mock.patch.dict(
                "os.environ", {"PATH": f"{root}:{os.environ['PATH']}"}
            ):
                with self.assertRaisesRegex(RuntimeError, "timed out"):
                    measure.run_agent("cold-start", "baseline", "prompt", args)

            self.assertLess(time.monotonic() - started, 2)

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
            "agent-effectiveness-real-2026-07",
            "cartography-sanity-real.json",
            "claude-sonnet-4-6",
        ):
            self.assertIn(evidence, baseline)


if __name__ == "__main__":
    unittest.main()

"""One-command internal release preflight contracts (#1088)."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_preflight.py"
EXPECTED_AXES = [
    "guard",
    "core_behavior",
    "judge_calibration",
    "product_outcome_snapshot",
    "agent_effectiveness",
    "lightweight_decision",
    "public_evidence",
    "bundle_consumer",
]


class ReleasePreflightTests(unittest.TestCase):
    def _fixture(self, tmp: Path) -> tuple[Path, Path]:
        helper = tmp / "step.py"
        helper.write_text(
            "import json, os, pathlib, sys\n"
            "step=sys.argv[1]\n"
            "p=pathlib.Path(os.environ['PREFLIGHT_ORDER_FILE'])\n"
            "p.write_text((p.read_text() if p.exists() else '') + step + '\\n')\n"
            "print(json.dumps({'step': step, 'status': 'PASS'}))\n"
            "raise SystemExit(1 if step == os.environ.get('PREFLIGHT_FAIL') else 0)\n",
            encoding="utf-8",
        )
        config = tmp / "config.json"
        config.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "steps": [
                        {
                            "id": axis,
                            "command": [sys.executable, str(helper), axis],
                            "required": True,
                        }
                        for axis in EXPECTED_AXES
                    ],
                }
            ),
            encoding="utf-8",
        )
        return config, tmp / "order.txt"

    def _behavior_fixture(
        self, tmp: Path, *, outcomes: dict[str, list[str]]
    ) -> tuple[Path, Path]:
        behavior = tmp / "behavior.py"
        behavior.write_text(
            "import json, os, pathlib, sys\n"
            "mode=sys.argv[1]\n"
            "cases=os.environ.get('EVAL_CASES', 'case-a case-b').split()\n"
            "runs=int(os.environ.get('EVAL_RUNS', '1'))\n"
            "output=pathlib.Path(os.environ['EVAL_OUTPUT_DIR'])\n"
            "state_path=pathlib.Path(os.environ['BEHAVIOR_STATE_FILE'])\n"
            "trace_path=pathlib.Path(os.environ['BEHAVIOR_TRACE_FILE'])\n"
            "outcomes=json.loads(os.environ['BEHAVIOR_OUTCOMES'])\n"
            "state=json.loads(state_path.read_text()) if state_path.exists() else {}\n"
            "failed=False\n"
            "for case in cases:\n"
            "    case_dir=output / case\n"
            "    case_dir.mkdir(parents=True, exist_ok=True)\n"
            "    for run in range(1, runs + 1):\n"
            "        index=state.get(case, 0)\n"
            "        result=outcomes[case][min(index, len(outcomes[case]) - 1)]\n"
            "        state[case]=index + 1\n"
            "        (case_dir / f'run-{run}-report.md').write_text(f'{mode} {case} report {index + 1}\\n')\n"
            "        (case_dir / f'run-{run}-judge.md').write_text(f'RESULT: {result}\\n')\n"
            "        with trace_path.open('a') as trace:\n"
            "            trace.write(f'{mode} {case} {result} {case_dir}\\n')\n"
            "        failed = failed or result != 'PASS'\n"
            "state_path.write_text(json.dumps(state))\n"
            "raise SystemExit(1 if failed else 0)\n",
            encoding="utf-8",
        )
        generic = tmp / "step.py"
        generic.write_text(
            "import pathlib, sys\n"
            "pathlib.Path(sys.argv[2]).open('a').write(sys.argv[1] + '\\n')\n",
            encoding="utf-8",
        )
        order = tmp / "order.txt"
        shared_env = {
            "BEHAVIOR_STATE_FILE": str(tmp / "behavior-state.json"),
            "BEHAVIOR_TRACE_FILE": str(tmp / "behavior-trace.txt"),
            "BEHAVIOR_OUTCOMES": json.dumps(outcomes),
            "EVAL_CASES": "case-a case-b",
            "EVAL_RUNS": "1",
            "EVAL_OUTPUT_DIR": str(tmp / "output" / "core-behavior" / "initial"),
        }
        steps = []
        for axis in EXPECTED_AXES:
            if axis == "core_behavior":
                steps.append(
                    {
                        "id": axis,
                        "command": [sys.executable, str(behavior), "initial"],
                        "diagnostic_command": [
                            sys.executable,
                            str(behavior),
                            "diagnostic",
                        ],
                        "behavior_cases": ["case-a", "case-b"],
                        "required": True,
                        "env": shared_env,
                    }
                )
            else:
                steps.append(
                    {
                        "id": axis,
                        "command": [sys.executable, str(generic), axis, str(order)],
                        "required": True,
                    }
                )
        config = tmp / "config.json"
        config.write_text(
            json.dumps({"schema_version": 1, "steps": steps}), encoding="utf-8"
        )
        return config, tmp / "behavior-trace.txt"

    def _run(
        self,
        tmp: Path,
        *,
        failing: str = "",
        config: Path | None = None,
        diagnose_core_misses: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        fixture_config, order = self._fixture(tmp) if config is None else (config, None)
        env = os.environ.copy()
        if order is not None:
            env["PREFLIGHT_ORDER_FILE"] = str(order)
        env["PREFLIGHT_FAIL"] = failing
        command = [
            sys.executable,
            str(SCRIPT),
            "--config",
            str(fixture_config),
            "--output-dir",
            str(tmp / "output"),
            "--json",
        ]
        if diagnose_core_misses:
            command.append("--diagnose-core-misses")
        return subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_all_release_axes_run_in_order_and_report_releasable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            result = self._run(tmp)

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["releasable"])
            self.assertEqual(
                [step["id"] for step in report["steps"]], EXPECTED_AXES
            )
            self.assertEqual(
                (tmp / "order.txt").read_text(encoding="utf-8").splitlines(),
                EXPECTED_AXES,
            )

            product = next(
                step
                for step in report["steps"]
                if step["id"] == "product_outcome_snapshot"
            )
            self.assertTrue(product["snapshot_collection_succeeded"])
            self.assertIn("not_current_product_success", product["interpretation"])
            markdown = (tmp / "output" / "report.md").read_text(encoding="utf-8")
            self.assertIn(
                "| product_outcome_snapshot | SNAPSHOT COLLECTED |", markdown
            )
            self.assertNotIn("| product_outcome_snapshot | PASS |", markdown)

    def test_failure_is_reported_but_later_independent_axes_still_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            result = self._run(tmp, failing="judge_calibration")

            self.assertNotEqual(result.returncode, 0)
            report = json.loads(result.stdout)
            self.assertFalse(report["releasable"])
            self.assertEqual(report["failed_required"], ["judge_calibration"])
            self.assertEqual(
                (tmp / "order.txt").read_text(encoding="utf-8").splitlines(),
                EXPECTED_AXES,
            )

    def test_default_config_composes_existing_tools_without_new_public_command(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        for needle in (
            "guard_efficacy.py",
            "run-core.sh",
            "calibrate_judge.py",
            "outcome_scorecard.py",
            "cartography-sanity-real.json",
            "lean_ablation.py",
            "check_public_evidence.mjs",
            "release_artifact.py",
        ):
            self.assertIn(needle, text)
        spec = importlib.util.spec_from_file_location("release_preflight", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as td:
            steps = {step["id"]: step for step in module._default_steps(Path(td))}
        product = steps["product_outcome_snapshot"]["command"]
        effectiveness = steps["agent_effectiveness"]["command"]
        self.assertNotEqual(product, effectiveness)
        self.assertNotIn("--agent-effectiveness-record", product)
        self.assertIn("--projects-file", effectiveness)
        core = steps["core_behavior"]
        self.assertEqual(core["env"]["EVAL_RUNS"], "1")
        self.assertEqual(core["behavior_cases"], ["shorts-real-spec", "headless-prose-quality"])
        self.assertTrue(core["diagnostic_command"][-1].endswith("evals/run.sh"))

    def test_core_success_runs_each_case_once(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            config, trace = self._behavior_fixture(
                tmp,
                outcomes={"case-a": ["PASS"], "case-b": ["PASS"]},
            )

            result = self._run(tmp, config=config)

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            core = next(step for step in report["steps"] if step["id"] == "core_behavior")
            behavior = core["behavior_trials"]
            self.assertEqual(behavior["initial_trial_count"], 2)
            self.assertEqual(behavior["diagnostic_trial_count"], 0)
            self.assertEqual(
                [line.split()[:3] for line in trace.read_text(encoding="utf-8").splitlines()],
                [
                    ["initial", "case-a", "PASS"],
                    ["initial", "case-b", "PASS"],
                ],
            )

    def test_initial_miss_latches_release_failure_and_preserves_all_four_trials(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            config, trace = self._behavior_fixture(
                tmp,
                outcomes={"case-a": ["FAIL", "PASS", "PASS"], "case-b": ["PASS"]},
            )

            result = self._run(
                tmp, config=config, diagnose_core_misses=True
            )

            self.assertEqual(result.returncode, 1, result.stderr)
            report = json.loads(result.stdout)
            self.assertFalse(report["releasable"])
            self.assertEqual(report["failed_required"], ["core_behavior"])
            core = next(step for step in report["steps"] if step["id"] == "core_behavior")
            behavior = core["behavior_trials"]
            self.assertEqual(behavior["initial_failed_cases"], ["case-a"])
            self.assertTrue(behavior["release_failure_latched"])
            self.assertEqual(behavior["diagnostic_runs_per_case"], 2)
            self.assertEqual(behavior["total_trial_count"], 4)
            self.assertEqual(core["status"], "FAIL")
            traces = trace.read_text(encoding="utf-8").splitlines()
            self.assertEqual(
                [line.split()[:3] for line in traces],
                [
                    ["initial", "case-a", "FAIL"],
                    ["initial", "case-b", "PASS"],
                    ["diagnostic", "case-a", "PASS"],
                    ["diagnostic", "case-a", "PASS"],
                ],
            )
            artifacts = list((tmp / "output" / "core-behavior").rglob("run-*-*.md"))
            self.assertEqual(len(artifacts), 8)

    def test_two_initial_misses_share_the_remaining_two_trial_budget(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            config, trace = self._behavior_fixture(
                tmp,
                outcomes={"case-a": ["FAIL", "PASS"], "case-b": ["FAIL", "PASS"]},
            )

            result = self._run(tmp, config=config, diagnose_core_misses=True)

            self.assertEqual(result.returncode, 1, result.stderr)
            report = json.loads(result.stdout)
            core = next(step for step in report["steps"] if step["id"] == "core_behavior")
            behavior = core["behavior_trials"]
            self.assertEqual(behavior["initial_failed_cases"], ["case-a", "case-b"])
            self.assertEqual(behavior["diagnostic_runs_per_case"], 1)
            self.assertEqual(behavior["total_trial_count"], 4)
            self.assertEqual(len(trace.read_text(encoding="utf-8").splitlines()), 4)

    def test_initial_miss_does_not_rerun_without_diagnostic_request(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            config, trace = self._behavior_fixture(
                tmp,
                outcomes={"case-a": ["FAIL", "PASS"], "case-b": ["PASS"]},
            )

            result = self._run(tmp, config=config)

            self.assertEqual(result.returncode, 1, result.stderr)
            report = json.loads(result.stdout)
            core = next(step for step in report["steps"] if step["id"] == "core_behavior")
            behavior = core["behavior_trials"]
            self.assertEqual(behavior["total_trial_count"], 2)
            self.assertEqual(behavior["diagnostic_trial_count"], 0)
            self.assertEqual(len(trace.read_text(encoding="utf-8").splitlines()), 2)


if __name__ == "__main__":
    unittest.main()

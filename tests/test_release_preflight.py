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
    "product_outcome",
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

    def _run(
        self, tmp: Path, *, failing: str = ""
    ) -> subprocess.CompletedProcess[str]:
        config, order = self._fixture(tmp)
        env = os.environ.copy()
        env["PREFLIGHT_ORDER_FILE"] = str(order)
        env["PREFLIGHT_FAIL"] = failing
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--config",
                str(config),
                "--output-dir",
                str(tmp / "output"),
                "--json",
            ],
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
        product = steps["product_outcome"]["command"]
        effectiveness = steps["agent_effectiveness"]["command"]
        self.assertNotEqual(product, effectiveness)
        self.assertNotIn("--agent-effectiveness-record", product)
        self.assertIn("--projects-file", effectiveness)


if __name__ == "__main__":
    unittest.main()

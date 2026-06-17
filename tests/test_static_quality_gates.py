import os
import re
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StaticQualityGateConfigTests(unittest.TestCase):
    def test_pyproject_defines_python311_static_quality_baseline(self) -> None:
        config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        ruff = config["tool"]["ruff"]
        self.assertEqual(ruff["target-version"], "py311")
        self.assertEqual(ruff["lint"]["select"], ["E4", "E7", "E9", "F", "C901"])
        self.assertEqual(ruff["lint"]["mccabe"]["max-complexity"], 30)

        mypy = config["tool"]["mypy"]
        self.assertEqual(mypy["python_version"], "3.11")
        self.assertTrue(mypy["explicit_package_bases"])
        self.assertTrue(mypy["check_untyped_defs"])
        self.assertEqual(mypy["files"], ["harness", "scripts/measure_main_turns.py"])

        bandit = config["tool"]["bandit"]
        self.assertEqual(bandit["targets"], ["harness", "scripts"])
        self.assertIn("tests", bandit["exclude_dirs"])

    def test_static_quality_workflow_exposes_stable_check_names(self) -> None:
        workflow = (ROOT / ".github/workflows/static-quality.yml").read_text(encoding="utf-8")

        self.assertIn("name: static-quality", workflow)
        self.assertIn("name: ruff lint + complexity", workflow)
        self.assertIn("name: mypy type check", workflow)
        self.assertIn("name: bandit security scan", workflow)
        self.assertIn("python-version: '3.11'", workflow)
        self.assertIn("pip install -r requirements-quality.txt", workflow)
        self.assertIn("ruff check .", workflow)
        self.assertIn("mypy", workflow)
        self.assertIn("bandit -c pyproject.toml -r harness scripts -l -i", workflow)
        self.assertNotIn("-ll", workflow)

    def test_local_static_quality_script_matches_ci_bandit_threshold(self) -> None:
        script_path = ROOT / "scripts/check_static_quality.sh"
        script = script_path.read_text(encoding="utf-8")

        self.assertTrue(os.access(script_path, os.X_OK))
        self.assertIn("ruff check .", script)
        self.assertIn("-m mypy", script)
        self.assertIn("-m bandit -c pyproject.toml -r harness scripts -l -i", script)
        self.assertNotIn("-ll", script)

    def test_quality_tool_versions_are_pinned_for_ci_and_local_repro(self) -> None:
        requirements = (ROOT / "requirements-quality.txt").read_text(encoding="utf-8")

        for package in ("ruff", "mypy", "bandit"):
            with self.subTest(package=package):
                self.assertRegex(requirements, rf"(?m)^{re.escape(package)}==\d+\.\d+\.\d+$")

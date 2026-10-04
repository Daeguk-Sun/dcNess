"""Scenario-level product journey execution and per-AC verdict tests."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from harness.product_journey import (
    JourneyConfigError,
    main,
    read_receipts,
    run_from_config,
)


CONFIG_PATH = Path("app/.maestro/dcness-journey.json")


def _command(code: str, timeout: int = 10) -> dict[str, object]:
    return {"argv": [sys.executable, "-c", code], "timeout_sec": timeout}


def _count(name: str) -> str:
    # Append one line per call so the test can count how often a phase ran.
    return f"open({name!r}, 'a').write('x\\n')"


def _scenario(
    scenario_id: str, target_ac: list[str], *, exit_code: int = 0, extra: str = ""
) -> dict[str, object]:
    parts = [_count(scenario_id + ".ran"), extra, f"raise SystemExit({exit_code})"]
    code = "; ".join(part for part in parts if part)
    return {
        "scenario_id": scenario_id,
        "description": f"{scenario_id} 화면 흐름",
        **_command(code),
        "target_ac": target_ac,
    }


def _write_config(root: Path, payload: dict[str, object]) -> Path:
    path = root / CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _base_config(scenarios: list[dict[str, object]], target_ac: list[str]) -> dict[str, object]:
    return {
        "version": 1,
        "journey_id": "fixture-scenario-journey",
        "target_ac": target_ac,
        "boundary": "cli",
        "assertion": {
            "description": "각 시나리오 명령이 담당 AC 동작을 판정한다",
            "source": "journey_exit",
        },
        "human_intervention_count": 0,
        "commands": {
            "start": {**_command(_count("start.ran")), "mode": "command"},
            "health": _command("print('healthy')"),
            "cleanup": _command(_count("cleanup.ran")),
        },
        "scenarios": scenarios,
        "evidence_dir": ".dcness-work/product-journey",
    }


def _three_scenarios(second_exit: int = 1) -> dict[str, object]:
    return _base_config(
        [
            _scenario("scenario-one", ["AC-1"]),
            _scenario("scenario-two", ["AC-2"], exit_code=second_exit),
            _scenario("scenario-three", ["AC-3"]),
        ],
        ["AC-1", "AC-2", "AC-3"],
    )


def _lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0


def _receipt(result) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return json.loads(result.receipt_path.read_text(encoding="utf-8"))


class ScenarioExecutionTests(unittest.TestCase):
    def test_one_failing_scenario_fails_only_its_ac_and_the_rest_still_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = _write_config(root, _three_scenarios(second_exit=1))
            result = run_from_config(root, config_path=config_path, run_id="mixed-run")
            receipt = _receipt(result)

            self.assertEqual(_lines(root / "start.ran"), 1)
            self.assertEqual(_lines(root / "cleanup.ran"), 1)
            for scenario_id in ("scenario-one", "scenario-two", "scenario-three"):
                self.assertEqual(_lines(root / f"{scenario_id}.ran"), 1, scenario_id)
            valid = read_receipts(root)

        self.assertEqual(result.exit_code, 1)
        self.assertEqual(receipt["outcome"], "FAIL")
        self.assertEqual(
            receipt["ac_results"], {"AC-1": "PASS", "AC-2": "FAIL", "AC-3": "PASS"}
        )
        self.assertEqual(receipt["product_ac"], {"passed": 2, "total": 3})
        self.assertFalse(receipt["partial"])
        self.assertIn("journey_failed", receipt["failure_reasons"])
        self.assertNotIn("journey", receipt["commands"])
        self.assertEqual(
            [(s["scenario_id"], s["executed"], s["exit_code"]) for s in receipt["scenarios"]],
            [("scenario-one", True, 0), ("scenario-two", True, 1), ("scenario-three", True, 0)],
        )
        self.assertEqual([item["run_id"] for item in valid], ["mixed-run"])

    def test_all_scenarios_passing_closes_every_ac(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = _write_config(root, _three_scenarios(second_exit=0))
            result = run_from_config(root, config_path=config_path, run_id="green-run")
            receipt = _receipt(result)
            valid = read_receipts(root)

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(receipt["outcome"], "PASS")
        self.assertEqual(set(receipt["ac_results"].values()), {"PASS"})
        self.assertEqual(receipt["product_ac"], {"passed": 3, "total": 3})
        self.assertTrue(receipt["journey_executed"])
        self.assertTrue(receipt["assertion"]["passed"])
        self.assertEqual([item["run_id"] for item in valid], ["green-run"])

    def test_ac_shared_by_two_scenarios_needs_both_to_pass(self) -> None:
        config = _base_config(
            [
                _scenario("scenario-one", ["AC-1", "AC-SHARED"]),
                _scenario("scenario-two", ["AC-SHARED"], exit_code=1),
            ],
            ["AC-1", "AC-SHARED"],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_from_config(
                root, config_path=_write_config(root, config), run_id="shared-run"
            )
            receipt = _receipt(result)

        self.assertEqual(receipt["ac_results"], {"AC-1": "PASS", "AC-SHARED": "FAIL"})

    def test_failed_health_runs_no_scenario_and_fails_every_ac(self) -> None:
        config = _three_scenarios(second_exit=0)
        config["commands"]["health"] = _command("raise SystemExit(3)")  # type: ignore[index]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_from_config(
                root, config_path=_write_config(root, config), run_id="unhealthy-run"
            )
            receipt = _receipt(result)
            ran = [_lines(root / f"{s}.ran") for s in ("scenario-one", "scenario-two")]
            self.assertEqual(_lines(root / "cleanup.ran"), 1)

        self.assertEqual(ran, [0, 0])
        self.assertEqual(set(receipt["ac_results"].values()), {"FAIL"})
        self.assertEqual(receipt["product_ac"]["passed"], 0)
        self.assertFalse(receipt["journey_executed"])

    def test_scenario_close_to_its_timeout_is_warned(self) -> None:
        from harness.product_journey import _timeout_warnings

        warnings = _timeout_warnings(
            {"scenario:slow-flow": {"duration_ms": 9_000, "timeout_sec": 10, "timed_out": False}}
        )
        self.assertEqual(warnings[0]["phase"], "scenario:slow-flow")


class PartialScenarioRunTests(unittest.TestCase):
    def test_selected_scenarios_rerun_once_and_partial_receipt_is_not_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = _write_config(root, _three_scenarios(second_exit=0))
            result = run_from_config(
                root,
                config_path=config_path,
                run_id="rerun-two",
                scenarios=["scenario-two"],
            )
            receipt = _receipt(result)
            ran = {
                s: _lines(root / f"{s}.ran")
                for s in ("scenario-one", "scenario-two", "scenario-three")
            }
            self.assertEqual(_lines(root / "start.ran"), 1)
            self.assertEqual(_lines(root / "cleanup.ran"), 1)
            valid = read_receipts(root)

        self.assertEqual(ran, {"scenario-one": 0, "scenario-two": 1, "scenario-three": 0})
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(receipt["partial"])
        self.assertEqual(receipt["selected_scenarios"], ["scenario-two"])
        self.assertEqual(
            receipt["ac_results"], {"AC-1": "NOT_RUN", "AC-2": "PASS", "AC-3": "NOT_RUN"}
        )
        self.assertEqual(valid, [])

    def test_partial_run_fails_when_a_selected_scenario_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = _write_config(root, _three_scenarios(second_exit=1))
            result = run_from_config(
                root,
                config_path=config_path,
                run_id="rerun-fail",
                scenarios=["scenario-two", "scenario-three"],
            )
            receipt = _receipt(result)

        self.assertEqual(result.exit_code, 1)
        self.assertEqual(receipt["outcome"], "FAIL")
        self.assertEqual(
            receipt["ac_results"], {"AC-1": "NOT_RUN", "AC-2": "FAIL", "AC-3": "PASS"}
        )

    def test_cli_scenario_option_is_repeatable_and_rejects_unknown_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = _write_config(root, _three_scenarios(second_exit=0))
            code = main(
                [
                    "run",
                    "--project-root", str(root),
                    "--config", str(config_path),
                    "--run-id", "cli-rerun",
                    "--scenario", "scenario-one",
                    "--scenario", "scenario-three",
                ]
            )
            receipt = json.loads(
                (root / ".dcness-work/product-journey/cli-rerun/receipt.json").read_text(
                    encoding="utf-8"
                )
            )
            unknown = main(
                [
                    "run",
                    "--project-root", str(root),
                    "--config", str(config_path),
                    "--scenario", "scenario-missing",
                ]
            )

        self.assertEqual(code, 0)
        self.assertEqual(receipt["selected_scenarios"], ["scenario-one", "scenario-three"])
        self.assertEqual(unknown, 2)


class ScenarioContractTests(unittest.TestCase):
    def _assert_contract_error(
        self, config: dict[str, object], pattern: str, **kwargs: object
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = _write_config(root, config)
            with self.assertRaisesRegex(JourneyConfigError, pattern):
                run_from_config(root, config_path=config_path, **kwargs)  # type: ignore[arg-type]
            self.assertFalse((root / "start.ran").exists())

    def test_invalid_scenario_declarations_are_contract_errors(self) -> None:
        both = _three_scenarios()
        both["commands"]["journey"] = _command("print('x')")  # type: ignore[index]
        neither = _three_scenarios()
        del neither["scenarios"]
        orphan_ac = _three_scenarios()
        orphan_ac["target_ac"] = ["AC-1", "AC-2", "AC-3", "AC-ORPHAN"]
        duplicate = _three_scenarios()
        duplicate["scenarios"][1]["scenario_id"] = "scenario-one"  # type: ignore[index]
        undeclared_ac = _three_scenarios()
        undeclared_ac["scenarios"][0]["target_ac"] = ["AC-UNDECLARED"]  # type: ignore[index]
        empty = _three_scenarios()
        empty["scenarios"] = []
        slow = _three_scenarios()
        slow["scenarios"][0]["timeout_sec"] = 1801  # type: ignore[index]
        bad_id = _three_scenarios()
        bad_id["scenarios"][0]["scenario_id"] = "Bad Id"  # type: ignore[index]
        repeated_ac = _three_scenarios()
        repeated_ac["target_ac"] = ["AC-1", "AC-2", "AC-3", " AC-1 "]
        cases = {
            "both": (both, "scenarios and commands.journey"),
            "neither": (neither, "commands.journey"),
            "orphan-ac": (orphan_ac, "AC-ORPHAN"),
            "duplicate": (duplicate, "scenario_id must be unique"),
            "undeclared-ac": (undeclared_ac, "declared in target_ac"),
            "empty": (empty, "at least one scenario"),
            "slow": (slow, r"\(0, 1800\]"),
            "bad-id": (bad_id, "scenario_id must match"),
            "repeated-ac": (repeated_ac, "must not repeat"),
        }
        for name, (config, pattern) in cases.items():
            with self.subTest(name=name):
                self._assert_contract_error(config, pattern)

    def test_scenario_selection_requires_scenario_manifest_and_known_ids(self) -> None:
        self._assert_contract_error(
            _three_scenarios(), "unknown scenario", scenarios=["scenario-missing"]
        )
        legacy = _three_scenarios()
        del legacy["scenarios"]
        legacy["commands"]["journey"] = _command("print('ok')")  # type: ignore[index]
        self._assert_contract_error(
            legacy, "only valid for scenario", scenarios=["scenario-one"]
        )


class ScenarioReceiptIntegrityTests(unittest.TestCase):
    def _mixed_receipt(self, root: Path) -> tuple[Path, dict[str, object]]:
        config_path = _write_config(root, _three_scenarios(second_exit=1))
        result = run_from_config(root, config_path=config_path, run_id="mixed-run")
        return result.receipt_path, _receipt(result)

    def _assert_tamper_rejected(self, mutate) -> None:  # type: ignore[no-untyped-def]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt_path, receipt = self._mixed_receipt(root)
            self.assertEqual(len(read_receipts(root)), 1)
            mutate(receipt, root)
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            self.assertEqual(read_receipts(root), [])

    def test_forged_ac_verdict_is_recomputed_and_rejected(self) -> None:
        def mutate(receipt, _root):  # type: ignore[no-untyped-def]
            receipt["ac_results"]["AC-2"] = "PASS"
            receipt["product_ac"]["passed"] = 3

        self._assert_tamper_rejected(mutate)

    def test_reassigned_scenario_ac_ownership_is_rejected(self) -> None:
        def mutate(receipt, _root):  # type: ignore[no-untyped-def]
            # Move the failing scenario onto an AC the manifest gave to another scenario.
            receipt["scenarios"][1]["target_ac"] = ["AC-3"]
            receipt["scenarios"][2]["target_ac"] = ["AC-2"]

        self._assert_tamper_rejected(mutate)

    def test_tampered_scenario_log_is_rejected(self) -> None:
        def mutate(receipt, root):  # type: ignore[no-untyped-def]
            log = root / receipt["scenarios"][0]["log_path"]
            log.write_text("forged", encoding="utf-8")

        self._assert_tamper_rejected(mutate)

    def test_malformed_scenario_receipt_is_skipped_without_breaking_aggregation(
        self,
    ) -> None:
        malformed = {
            "ac-verdict-list": lambda receipt: receipt["ac_results"].update(
                {"AC-2": ["FAIL"]}
            ),
            "commands-list": lambda receipt: receipt.update({"commands": []}),
            "scenario-entry-string": lambda receipt: receipt["scenarios"].append("x"),
        }
        for name, mutate in malformed.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                receipt_path, receipt = self._mixed_receipt(root)
                mutate(receipt)
                receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
                self.assertEqual(read_receipts(root), [])

    def test_partial_flag_cannot_be_dropped_to_promote_a_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = _write_config(root, _three_scenarios(second_exit=0))
            result = run_from_config(
                root, config_path=config_path, run_id="rerun", scenarios=["scenario-two"]
            )
            receipt = _receipt(result)
            receipt["partial"] = False
            result.receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            self.assertEqual(read_receipts(root), [])


_LAYOUT = json.dumps(
    {
        "version": 1,
        "viewport": {"width": 1080, "height": 2400},
        "safe_area": {"top": 96, "right": 0, "bottom": 48, "left": 0},
        "elements": [
            {
                "element_id": "cta",
                "bounds": {"x": 40, "y": 400, "width": 1000, "height": 120},
                "z": 0,
            }
        ],
    }
)


def _writes(*files: str) -> str:
    parts = [
        "import os",
        "from pathlib import Path",
        "run=Path(os.environ['DCNESS_PRODUCT_JOURNEY_RUN_DIR'])",
    ]
    for name in files:
        content = _LAYOUT if name.endswith(".json") else "png"
        parts.append(f"(run/{name!r}).write_text({content!r})")
    return "; ".join(parts)


def _ui_config(
    specs: list[tuple[str, list[str], list[tuple[str, str, bool]]]],
    target_ac: list[str],
) -> dict[str, object]:
    """specs: (scenario_id, scenario AC, [(step_id, step AC, captures screenshot)])."""
    scenarios = []
    steps = []
    snapshots = []
    for scenario_id, scenario_ac, scenario_steps in specs:
        files = []
        for step_id, ac, captures in scenario_steps:
            files.append(f"{step_id}-layout.json")
            if captures:
                files.append(f"{step_id}.png")
            steps.append(
                {
                    "step_id": step_id,
                    "scenario_id": scenario_id,
                    "description": f"{step_id} 화면",
                    "target_ac": [ac],
                    "final": True,
                    "evidence": [{"path": f"{step_id}.png", "type": "screenshot"}],
                }
            )
            snapshots.append(
                {
                    "step_id": step_id,
                    "layout_report": f"{step_id}-layout.json",
                    "elements": [{"element_id": "cta", "target_ac": [ac]}],
                }
            )
        scenarios.append(_scenario(scenario_id, scenario_ac, extra=_writes(*files)))
    config = _base_config(scenarios, target_ac)
    config["boundary"] = "ui"
    config["ui_evidence"] = {"steps": steps}
    config["ux_integrity"] = {"snapshots": snapshots}
    return config


class UiScenarioTests(unittest.TestCase):
    def test_missing_screen_evidence_fails_only_the_ac_it_backs(self) -> None:
        config = _ui_config(
            [
                ("login-flow", ["AC-1"], [("login", "AC-1", True)]),
                # Exits 0 but never captures its screenshot.
                ("home-flow", ["AC-2"], [("home", "AC-2", False)]),
            ],
            ["AC-1", "AC-2"],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_from_config(
                root, config_path=_write_config(root, config), run_id="ui-run"
            )
            receipt = _receipt(result)
            valid = read_receipts(root)

        self.assertEqual(receipt["ac_results"], {"AC-1": "PASS", "AC-2": "FAIL"})
        self.assertEqual(receipt["product_ac"], {"passed": 1, "total": 2})
        self.assertIn("ui_evidence_missing", receipt["failure_reasons"])
        self.assertEqual([item["run_id"] for item in valid], ["ui-run"])

    def _shared_ac_config(self) -> dict[str, object]:
        return _ui_config(
            [
                # flow-a exits 0 but misses its screenshot for the shared AC.
                ("flow-a", ["AC-S"], [("a-screen", "AC-S", False)]),
                ("flow-b", ["AC-S"], [("b-screen", "AC-S", True)]),
            ],
            ["AC-S"],
        )

    def test_partial_run_reports_ui_failure_of_the_scenario_it_ran(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_from_config(
                root,
                config_path=_write_config(root, self._shared_ac_config()),
                run_id="rerun-a",
                scenarios=["flow-a"],
            )
            receipt = _receipt(result)

        self.assertEqual(result.exit_code, 1)
        self.assertEqual(receipt["ac_results"], {"AC-S": "FAIL"})

    def test_partial_run_matches_padded_ids_like_the_contract_check(self) -> None:
        config = self._shared_ac_config()
        steps = config["ui_evidence"]["steps"]  # type: ignore[index]
        steps[0]["scenario_id"] = " flow-a "
        config["ux_integrity"]["snapshots"][0]["step_id"] = " a-screen "  # type: ignore[index]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_from_config(
                root,
                config_path=_write_config(root, config),
                run_id="rerun-padded",
                scenarios=["flow-a"],
            )
            receipt = _receipt(result)

        self.assertEqual(result.exit_code, 1)
        self.assertEqual(receipt["ac_results"], {"AC-S": "FAIL"})
        self.assertEqual(len(receipt["ux_integrity"]["snapshots"]), 1)

    def test_partial_run_judges_only_the_screens_of_selected_scenarios(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_from_config(
                root,
                config_path=_write_config(root, self._shared_ac_config()),
                run_id="rerun-b",
                scenarios=["flow-b"],
            )
            receipt = _receipt(result)

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(receipt["ac_results"], {"AC-S": "NOT_RUN"})
        self.assertEqual(
            [step["step_id"] for step in receipt["ui_evidence"]["steps"]], ["b-screen"]
        )
        self.assertNotIn("ui_evidence_missing", receipt["failure_reasons"])

    def test_ui_steps_must_belong_to_a_scenario_that_owns_their_ac(self) -> None:
        base = [
            ("login-flow", ["AC-1"], [("login", "AC-1", True)]),
            ("home-flow", ["AC-2"], [("home", "AC-2", True)]),
        ]
        missing = _ui_config(base, ["AC-1", "AC-2"])
        del missing["ui_evidence"]["steps"][0]["scenario_id"]  # type: ignore[index]
        unknown = _ui_config(base, ["AC-1", "AC-2"])
        unknown["ui_evidence"]["steps"][0]["scenario_id"] = "nope-flow"  # type: ignore[index]
        foreign_ac = _ui_config(base, ["AC-1", "AC-2"])
        foreign_ac["ui_evidence"]["steps"][0]["scenario_id"] = "home-flow"  # type: ignore[index]
        cases = {
            "missing": (missing, "scenario_id"),
            "unknown": (unknown, "declared scenario"),
            "foreign-ac": (foreign_ac, "owned by its scenario"),
        }
        for name, (config, pattern) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with self.assertRaisesRegex(JourneyConfigError, pattern):
                    run_from_config(root, config_path=_write_config(root, config))


if __name__ == "__main__":
    unittest.main()

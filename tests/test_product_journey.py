"""Project-local product journey execution contract tests."""

from __future__ import annotations

import copy
import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness.product_journey import (
    JourneyConfigError,
    read_receipts,
    run_from_config,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path("app/.maestro/dcness-journey.json")


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _command(code: str) -> dict[str, object]:
    return {"argv": [sys.executable, "-c", code], "timeout_sec": 10}


def _write_config(root: Path, payload: dict[str, object]) -> Path:
    path = root / CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _ui_steps() -> list[dict[str, object]]:
    return [
        {
            "step_id": "first",
            "description": "권한 안내 배너가 보이는 첫 화면",
            "target_ac": ["AC-FIXTURE-1"],
            "final": False,
            "evidence": [{"path": "first.png", "type": "screenshot"}],
        },
        {
            "step_id": "final",
            "description": "제품 AC를 판정하는 최종 화면",
            "target_ac": ["AC-FIXTURE-1"],
            "final": True,
            "evidence": [{"path": "final.png", "type": "screenshot"}],
        },
    ]


def _ux_element(
    element_id: str = "permission-banner-cta",
    target_ac: tuple[str, ...] = ("AC-FIXTURE-1",),
    node_id: str | None = None,
) -> dict[str, object]:
    element: dict[str, object] = {
        "element_id": element_id,
        "target_ac": list(target_ac),
    }
    if node_id is not None:
        element["node_id"] = node_id
    return element


def _ux_snapshot(
    *,
    step_id: str = "final",
    layout_report: str = "layout.json",
    elements: list[dict[str, object]] | None = None,
    element_id: str = "permission-banner-cta",
    target_ac: tuple[str, ...] = ("AC-FIXTURE-1",),
    node_id: str | None = None,
    mockup: str | None = None,
) -> dict[str, object]:
    snapshot: dict[str, object] = {
        "step_id": step_id,
        "layout_report": layout_report,
        "elements": (
            list(elements)
            if elements is not None
            else [_ux_element(element_id, target_ac, node_id)]
        ),
    }
    if mockup is not None:
        snapshot["mockup_reference"] = mockup
    return snapshot


def _ux_integrity(**kwargs: object) -> dict[str, object]:
    return {"snapshots": [_ux_snapshot(**kwargs)]}  # type: ignore[arg-type]


def _layout_report(
    bounds: dict[str, float],
    *,
    element_id: str = "permission-banner-cta",
    overlays: tuple[dict[str, object], ...] = (),
) -> dict[str, object]:
    return {
        "version": 1,
        "viewport": {"width": 1080, "height": 2400},
        "safe_area": {"top": 96, "right": 0, "bottom": 48, "left": 0},
        "elements": [
            {"element_id": element_id, "bounds": bounds, "z": 0},
            *overlays,
        ],
    }


CLEAN_BOUNDS = {"x": 40, "y": 400, "width": 1000, "height": 120}


def _ui_journey_command(*layouts: object, names: tuple[str, ...] = ("layout.json",)) -> dict[str, object]:
    code = (
        "import os; from pathlib import Path; "
        "run=Path(os.environ['DCNESS_PRODUCT_JOURNEY_RUN_DIR']); "
        "(run/'first.png').write_bytes(b'fixture-first'); "
        "(run/'final.png').write_bytes(b'fixture-final'); "
    )
    for name, layout in zip(names, layouts):
        if layout is None:
            continue
        payload = layout if isinstance(layout, str) else json.dumps(layout)
        code += f"(run/{name!r}).write_text({payload!r}, encoding='utf-8'); "
    code += "print('assertion passed')"
    return _command(code)


def _final_layout_report() -> dict[str, object]:
    return _layout_report(
        CLEAN_BOUNDS,
        element_id="result-confirm-cta",
        overlays=(
            {
                "element_id": "result-summary",
                "bounds": {"x": 40, "y": 700, "width": 1000, "height": 200},
                "z": 0,
            },
        ),
    )


def _MULTI_SCREEN_SNAPSHOTS() -> dict[str, object]:
    return {
        "snapshots": [
            _ux_snapshot(
                step_id="first",
                layout_report="first-layout.json",
                target_ac=("AC-FIXTURE-1",),
            ),
            _ux_snapshot(
                step_id="final",
                layout_report="final-layout.json",
                elements=[
                    _ux_element("result-confirm-cta", ("AC-FIXTURE-2",)),
                    _ux_element("result-summary", ("AC-FIXTURE-1",)),
                ],
            ),
        ]
    }


class ProductJourneyExecutionTests(unittest.TestCase):
    def _base_config(self) -> dict[str, object]:
        return {
            "version": 1,
            "journey_id": "fixture-cli-journey",
            "target_ac": ["AC-FIXTURE-1"],
            "boundary": "cli",
            "assertion": {
                "description": "journey command evaluates the promised behavior",
                "source": "journey_exit",
            },
            "human_intervention_count": 0,
            "commands": {
                "start": {
                    **_command("print('cli started')"),
                    "mode": "command",
                },
                "health": _command("print('healthy')"),
                "journey": _command("print('assertion passed')"),
                "cleanup": _command("print('cleaned')"),
            },
            "evidence_dir": ".dcness-work/product-journey",
        }

    def test_service_journey_records_commands_assertion_logs_and_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            port = _free_port()
            config = self._base_config()
            config["journey_id"] = "http-service-journey"
            config["boundary"] = "api"
            config["commands"] = {
                "start": {
                    "argv": [
                        sys.executable,
                        "-m",
                        "http.server",
                        str(port),
                        "--bind",
                        "127.0.0.1",
                    ],
                    "mode": "service",
                    "startup_grace_sec": 0.2,
                    "timeout_sec": 10,
                },
                "health": _command(
                    "import urllib.request; "
                    f"assert urllib.request.urlopen('http://127.0.0.1:{port}', timeout=2).status == 200"
                ),
                "journey": _command(
                    "import urllib.request; "
                    f"body=urllib.request.urlopen('http://127.0.0.1:{port}', timeout=2).read(); "
                    "assert b'directory listing' in body.lower()"
                ),
                "cleanup": _command("print('cleanup hook ran')"),
            }
            config_path = _write_config(root, config)

            result = run_from_config(
                root,
                config_path=config_path,
                run_id="pilot-success",
                measured_at="2026-07-12T08:00:00Z",
            )
            receipt = json.loads(result.receipt_path.read_text(encoding="utf-8"))

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(receipt["outcome"], "PASS")
        self.assertTrue(receipt["app_started"])
        self.assertTrue(receipt["journey_executed"])
        self.assertEqual(receipt["assertion"].get("evaluated"), True)
        self.assertEqual(receipt["assertion"].get("passed"), True)
        self.assertEqual(receipt["target_ac"], ["AC-FIXTURE-1"])
        self.assertEqual(receipt["product_ac"], {"passed": 1, "total": 1})
        self.assertEqual(receipt["human_intervention_count"], 0)
        self.assertIn("api", receipt["evidence_types"])
        for phase in ("start", "health", "journey", "cleanup"):
            self.assertIn("argv", receipt["commands"][phase])
            self.assertIsInstance(receipt["commands"][phase]["exit_code"], int)
            self.assertIn(phase, receipt["evidence_sha256"])
        self.assertFalse(Path(receipt["evidence_paths"]["receipt"]).is_absolute())

    def test_mock_app_not_started_journey_skipped_and_unmeasured_assertion_never_pass(
        self,
    ) -> None:
        cases = {
            "mock-only": {
                "boundary": "mock",
                "expected": "mock_only_boundary",
            },
            "app-not-started": {
                "start": {**_command("raise SystemExit(3)"), "mode": "command"},
                "expected": "app_not_started",
            },
            "journey-not-executed": {
                "health": _command("raise SystemExit(4)"),
                "expected": "journey_not_executed",
            },
            "assertion-not-evaluated": {
                "assertion": {"description": "declared but not evaluated", "source": "none"},
                "expected": "assertion_not_evaluated",
            },
        }
        for name, mutation in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._base_config()
                commands = dict(config["commands"])
                if "boundary" in mutation:
                    config["boundary"] = mutation["boundary"]
                if "start" in mutation:
                    commands["start"] = mutation["start"]
                if "health" in mutation:
                    commands["health"] = mutation["health"]
                if "assertion" in mutation:
                    config["assertion"] = mutation["assertion"]
                config["commands"] = commands
                config_path = _write_config(root, config)

                result = run_from_config(
                    root,
                    config_path=config_path,
                    run_id=name,
                    measured_at="2026-07-12T08:00:00Z",
                )
                receipt = json.loads(result.receipt_path.read_text(encoding="utf-8"))

            self.assertEqual(result.exit_code, 1)
            self.assertEqual(receipt["outcome"], "FAIL")
            self.assertIn(mutation["expected"], receipt["failure_reasons"])
            self.assertEqual(receipt["product_ac"]["passed"], 0)

    def test_ui_journey_records_multistep_screen_state_and_log_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._base_config()
            config["journey_id"] = "fixture-ui-journey"
            config["boundary"] = "ui"
            config["commands"] = dict(config["commands"])
            layout = json.dumps(
                _layout_report({"x": 40, "y": 400, "width": 1000, "height": 120})
            )
            config["commands"]["journey"] = _command(
                "import json, os; from pathlib import Path; "
                "run=Path(os.environ['DCNESS_PRODUCT_JOURNEY_RUN_DIR']); "
                "(run/'landing.png').write_bytes(b'fixture-png'); "
                "(run/'onboarding-state.json').write_text(json.dumps({'consent': True})); "
                f"(run/'layout.json').write_text({layout!r}, encoding='utf-8'); "
                "(run/'results.png').write_bytes(b'fixture-results-png')"
            )
            config["ux_integrity"] = _ux_integrity(step_id="results")
            config["ui_evidence"] = {
                "steps": [
                    {
                        "step_id": "landing",
                        "description": "랜딩에서 무료 시작 CTA를 확인한다",
                        "target_ac": ["AC-FIXTURE-1"],
                        "final": False,
                        "evidence": [
                            {"path": "landing.png", "type": "screenshot"}
                        ],
                    },
                    {
                        "step_id": "onboarding",
                        "description": "성인 생년월일과 동의를 제출한다",
                        "target_ac": ["AC-FIXTURE-1"],
                        "final": False,
                        "evidence": [
                            {
                                "path": "onboarding-state.json",
                                "type": "state",
                            }
                        ],
                    },
                    {
                        "step_id": "results",
                        "description": "최종 결과 화면에서 제품 AC를 확인한다",
                        "target_ac": ["AC-FIXTURE-1"],
                        "final": True,
                        "evidence": [
                            {"path": "results.png", "type": "screenshot"}
                        ],
                    },
                ]
            }
            config_path = _write_config(root, config)

            result = run_from_config(
                root,
                config_path=config_path,
                run_id="ui-pilot-success",
                measured_at="2026-07-13T08:00:00Z",
            )
            receipt = json.loads(result.receipt_path.read_text(encoding="utf-8"))

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(receipt["outcome"], "PASS")
            self.assertEqual(receipt["boundary"], "ui")
            self.assertEqual(
                receipt["evidence_types"],
                ["command", "log", "screenshot", "state", "ui"],
            )
            self.assertEqual(
                [step["step_id"] for step in receipt["ui_evidence"]["steps"]],
                ["landing", "onboarding", "results"],
            )
            self.assertTrue(receipt["ui_evidence"]["steps"][-1]["final"])
            for step in receipt["ui_evidence"]["steps"]:
                for evidence in step["evidence"]:
                    self.assertFalse(Path(evidence["path"]).is_absolute())
                    self.assertRegex(evidence["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(len(read_receipts(root)), 1)

    def test_ui_journey_missing_declared_evidence_never_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._base_config()
            config["boundary"] = "ui"
            config["ux_integrity"] = _ux_integrity(step_id="finish")
            config["ui_evidence"] = {
                "steps": [
                    {
                        "step_id": "start",
                        "description": "첫 화면",
                        "target_ac": ["AC-FIXTURE-1"],
                        "final": False,
                        "evidence": [
                            {"path": "missing-start.png", "type": "screenshot"}
                        ],
                    },
                    {
                        "step_id": "finish",
                        "description": "최종 화면",
                        "target_ac": ["AC-FIXTURE-1"],
                        "final": True,
                        "evidence": [
                            {"path": "missing-finish.png", "type": "screenshot"}
                        ],
                    },
                ]
            }
            config_path = _write_config(root, config)

            result = run_from_config(
                root,
                config_path=config_path,
                run_id="ui-missing-evidence",
                measured_at="2026-07-13T08:00:00Z",
            )

        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.receipt["outcome"], "FAIL")
        self.assertIn("ui_evidence_missing", result.receipt["failure_reasons"])
        self.assertEqual(result.receipt["product_ac"]["passed"], 0)

    def test_ui_evidence_symlink_escape_fails_closed_with_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._base_config()
            config["boundary"] = "ui"
            config["commands"] = dict(config["commands"])
            config["commands"]["journey"] = _command(
                "import os; from pathlib import Path; "
                "run=Path(os.environ['DCNESS_PRODUCT_JOURNEY_RUN_DIR']); "
                "(run/'first.png').symlink_to('/etc/hosts'); "
                "(run/'final.png').write_bytes(b'final')"
            )
            config["ux_integrity"] = _ux_integrity()
            config["ui_evidence"] = {
                "steps": [
                    {
                        "step_id": "first",
                        "description": "첫 화면",
                        "target_ac": ["AC-FIXTURE-1"],
                        "final": False,
                        "evidence": [
                            {"path": "first.png", "type": "screenshot"}
                        ],
                    },
                    {
                        "step_id": "final",
                        "description": "최종 화면",
                        "target_ac": ["AC-FIXTURE-1"],
                        "final": True,
                        "evidence": [
                            {"path": "final.png", "type": "screenshot"}
                        ],
                    },
                ]
            }
            config_path = _write_config(root, config)

            result = run_from_config(
                root,
                config_path=config_path,
                run_id="ui-symlink-escape",
                measured_at="2026-07-13T08:00:00Z",
            )

        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.receipt["outcome"], "FAIL")
        self.assertIn("ui_evidence_missing", result.receipt["failure_reasons"])

    def test_ui_evidence_hash_error_fails_closed_with_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._base_config()
            config["boundary"] = "ui"
            config["commands"] = dict(config["commands"])
            config["commands"]["journey"] = _ui_journey_command(
                _layout_report({"x": 40, "y": 400, "width": 1000, "height": 120})
            )
            config["ux_integrity"] = _ux_integrity()
            config["ui_evidence"] = {
                "steps": [
                    {
                        "step_id": "first",
                        "description": "첫 화면",
                        "target_ac": ["AC-FIXTURE-1"],
                        "final": False,
                        "evidence": [
                            {"path": "first.png", "type": "screenshot"}
                        ],
                    },
                    {
                        "step_id": "final",
                        "description": "최종 화면",
                        "target_ac": ["AC-FIXTURE-1"],
                        "final": True,
                        "evidence": [
                            {"path": "final.png", "type": "screenshot"}
                        ],
                    },
                ]
            }
            config_path = _write_config(root, config)
            original_hash = __import__(
                "harness.product_journey", fromlist=["_sha256_file"]
            )._sha256_file

            def flaky_hash(path: Path) -> str:
                if path.name == "first.png":
                    raise OSError("fixture evidence became unreadable")
                return original_hash(path)

            with patch("harness.product_journey._sha256_file", side_effect=flaky_hash):
                result = run_from_config(
                    root,
                    config_path=config_path,
                    run_id="ui-hash-error",
                    measured_at="2026-07-13T08:00:00Z",
                )

        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.receipt["outcome"], "FAIL")
        self.assertIn("ui_evidence_missing", result.receipt["failure_reasons"])

    def test_ui_contract_requires_multistep_final_ac_coverage(self) -> None:
        cases = {
            "single-step": [
                {
                    "step_id": "only",
                    "description": "한 단계뿐인 흐름",
                    "target_ac": ["AC-FIXTURE-1"],
                    "final": True,
                    "evidence": [{"path": "only.png", "type": "screenshot"}],
                }
            ],
            "no-final": [
                {
                    "step_id": step_id,
                    "description": step_id,
                    "target_ac": ["AC-FIXTURE-1"],
                    "final": False,
                    "evidence": [{"path": f"{step_id}.png", "type": "screenshot"}],
                }
                for step_id in ("first", "second")
            ],
            "final-misses-ac": [
                {
                    "step_id": "first",
                    "description": "첫 단계",
                    "target_ac": ["AC-FIXTURE-1", "AC-FIXTURE-2"],
                    "final": False,
                    "evidence": [{"path": "first.png", "type": "screenshot"}],
                },
                {
                    "step_id": "finish",
                    "description": "최종 단계",
                    "target_ac": ["AC-FIXTURE-1"],
                    "final": True,
                    "evidence": [{"path": "finish.png", "type": "screenshot"}],
                },
            ],
        }
        for name, steps in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._base_config()
                config["boundary"] = "ui"
                if name == "final-misses-ac":
                    config["target_ac"] = ["AC-FIXTURE-1", "AC-FIXTURE-2"]
                config["ui_evidence"] = {"steps": steps}
                config_path = _write_config(root, config)

                with self.assertRaises(JourneyConfigError):
                    run_from_config(root, config_path=config_path, run_id=name)

    def _ux_config(self, **kwargs: object) -> dict[str, object]:
        config = self._base_config()
        config["journey_id"] = "fixture-ux-journey"
        config["boundary"] = "ui"
        config["ui_evidence"] = {"steps": _ui_steps()}
        config["ux_integrity"] = _ux_integrity(**kwargs)  # type: ignore[arg-type]
        config["commands"] = dict(config["commands"])
        return config

    def test_occluded_element_fails_journey_though_functional_assertion_passes(
        self,
    ) -> None:
        cases = {
            "system-chrome-overlap": (
                _layout_report({"x": 40, "y": 40, "width": 1000, "height": 120}),
                "ux_integrity_chrome_overlap",
            ),
            "covered-by-higher-layer": (
                _layout_report(
                    {"x": 40, "y": 400, "width": 1000, "height": 120},
                    overlays=(
                        {
                            "element_id": "modal-scrim",
                            "bounds": {
                                "x": 0,
                                "y": 96,
                                "width": 1080,
                                "height": 2256,
                            },
                            "z": 5,
                        },
                    ),
                ),
                "ux_integrity_occluded",
            ),
        }
        for name, (layout, expected) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._ux_config()
                config["commands"]["journey"] = _ui_journey_command(layout)
                config_path = _write_config(root, config)

                result = run_from_config(
                    root,
                    config_path=config_path,
                    run_id=name,
                    measured_at="2026-07-26T08:00:00Z",
                )
                receipt = result.receipt

                self.assertEqual(result.exit_code, 1)
                self.assertEqual(receipt["outcome"], "FAIL")
                self.assertEqual(receipt["assertion"]["passed"], True)
                self.assertNotIn("ui_evidence_missing", receipt["failure_reasons"])
                self.assertIn(expected, receipt["failure_reasons"])
                self.assertEqual(receipt["product_ac"]["passed"], 0)
                self.assertEqual(
                    [item["outcome"] for item in read_receipts(root)], ["FAIL"]
                )

    def test_unobstructed_elements_pass_and_receipt_records_mockup_link(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._ux_config(
                node_id="onboarding.permission-cta",
                mockup="docs/design-variants/onboarding.html",
            )
            config["commands"]["journey"] = _ui_journey_command(
                _layout_report(
                    {"x": 40, "y": 400, "width": 1000, "height": 120},
                    overlays=(
                        {
                            "element_id": "background-card",
                            "bounds": {
                                "x": 0,
                                "y": 300,
                                "width": 1080,
                                "height": 400,
                            },
                            "z": -1,
                        },
                    ),
                )
            )
            config_path = _write_config(root, config)

            result = run_from_config(
                root,
                config_path=config_path,
                run_id="ux-integrity-clean",
                measured_at="2026-07-26T08:00:00Z",
            )
            receipt = result.receipt
            snapshot = receipt["ux_integrity"]["snapshots"][0]

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(receipt["outcome"], "PASS")
            self.assertEqual(snapshot["step_id"], "final")
            self.assertEqual(
                snapshot["mockup_reference"], "docs/design-variants/onboarding.html"
            )
            self.assertTrue(snapshot["layout_report"]["present"])
            self.assertRegex(snapshot["layout_report"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertFalse(Path(snapshot["layout_report"]["path"]).is_absolute())
            element = snapshot["elements"][0]
            self.assertEqual(element["element_id"], "permission-banner-cta")
            self.assertEqual(element["node_id"], "onboarding.permission-cta")
            self.assertEqual(element["target_ac"], ["AC-FIXTURE-1"])
            self.assertTrue(element["evaluated"])
            self.assertTrue(element["within_safe_area"])
            self.assertEqual(element["occluded_by"], [])
            self.assertEqual(len(read_receipts(root)), 1)

    def test_unusable_layout_report_never_closes_ui_requirement(self) -> None:
        cases = {
            "report-not-produced": (None, "ux_integrity_report_missing"),
            "report-unparseable": ("not-json", "ux_integrity_report_invalid"),
            "declared-element-absent": (
                _layout_report(CLEAN_BOUNDS, element_id="some-other-element"),
                "ux_integrity_element_missing",
            ),
            "duplicate-element-ids": (
                _layout_report(
                    {"x": 40, "y": 400, "width": 1000, "height": 120},
                    overlays=(
                        {
                            "element_id": "permission-banner-cta",
                            "bounds": {
                                "x": 40,
                                "y": 900,
                                "width": 1000,
                                "height": 120,
                            },
                            "z": 0,
                        },
                    ),
                ),
                "ux_integrity_report_invalid",
            ),
        }
        for name, (layout, expected) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._ux_config()
                config["commands"]["journey"] = _ui_journey_command(layout)
                config_path = _write_config(root, config)

                result = run_from_config(
                    root,
                    config_path=config_path,
                    run_id=name,
                    measured_at="2026-07-26T08:00:00Z",
                )

                self.assertEqual(result.exit_code, 1)
                self.assertEqual(result.receipt["outcome"], "FAIL")
                self.assertIn(expected, result.receipt["failure_reasons"])
                self.assertEqual(result.receipt["product_ac"]["passed"], 0)

    def test_layout_report_without_stack_order_or_safe_area_is_not_judgeable(
        self,
    ) -> None:
        overlay = {
            "element_id": "modal-scrim",
            "bounds": {"x": 0, "y": 96, "width": 1080, "height": 2256},
        }
        no_order = _layout_report(CLEAN_BOUNDS, overlays=(dict(overlay, z=5),))
        for element in no_order["elements"]:  # type: ignore[attr-defined]
            element.pop("z")
        no_safe_area = _layout_report(CLEAN_BOUNDS)
        no_safe_area.pop("safe_area")
        cases = {
            "stack-order-omitted": no_order,
            "safe-area-omitted": no_safe_area,
        }
        for name, layout in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._ux_config()
                config["commands"]["journey"] = _ui_journey_command(layout)
                config_path = _write_config(root, config)

                result = run_from_config(
                    root,
                    config_path=config_path,
                    run_id=name,
                    measured_at="2026-07-26T08:00:00Z",
                )

                self.assertEqual(result.exit_code, 1)
                self.assertEqual(result.receipt["outcome"], "FAIL")
                self.assertIn(
                    "ux_integrity_report_invalid", result.receipt["failure_reasons"]
                )

    def _multi_step_config(self) -> dict[str, object]:
        config = self._base_config()
        config["target_ac"] = ["AC-FIXTURE-1", "AC-FIXTURE-2"]
        config["boundary"] = "ui"
        config["commands"] = dict(config["commands"])
        steps = _ui_steps()
        steps[1]["target_ac"] = ["AC-FIXTURE-1", "AC-FIXTURE-2"]
        config["ui_evidence"] = {"steps": steps}
        return config

    def test_each_screen_snapshot_is_judged_against_its_own_layout_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._multi_step_config()
            config["ux_integrity"] = _MULTI_SCREEN_SNAPSHOTS()
            config["commands"]["journey"] = _ui_journey_command(
                _layout_report(
                    CLEAN_BOUNDS,
                    overlays=(
                        {
                            "element_id": "onboarding-sheet",
                            "bounds": {
                                "x": 0,
                                "y": 96,
                                "width": 1080,
                                "height": 2256,
                            },
                            "z": 9,
                        },
                    ),
                ),
                _final_layout_report(),
                names=("first-layout.json", "final-layout.json"),
            )
            config_path = _write_config(root, config)

            result = run_from_config(
                root,
                config_path=config_path,
                run_id="multi-screen-snapshots",
                measured_at="2026-07-26T08:00:00Z",
            )
            snapshots = result.receipt["ux_integrity"]["snapshots"]

            self.assertEqual(result.exit_code, 1)
            self.assertEqual(
                [snapshot["step_id"] for snapshot in snapshots], ["first", "final"]
            )
            self.assertIn(
                "ux_integrity_occluded", result.receipt["failure_reasons"]
            )
            self.assertNotIn(
                "ux_integrity_element_missing", result.receipt["failure_reasons"]
            )
            self.assertEqual(
                snapshots[0]["elements"][0]["occluded_by"], ["onboarding-sheet"]
            )
            self.assertEqual(snapshots[1]["elements"][0]["occluded_by"], [])
            self.assertTrue(snapshots[1]["elements"][0]["within_safe_area"])

    def test_snapshot_element_cannot_claim_an_ac_its_screen_does_not_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._multi_step_config()
            config["ux_integrity"] = {
                "snapshots": [
                    _ux_snapshot(
                        step_id="first",
                        target_ac=("AC-FIXTURE-1", "AC-FIXTURE-2"),
                    )
                ]
            }
            config_path = _write_config(root, config)

            with self.assertRaises(JourneyConfigError):
                run_from_config(
                    root, config_path=config_path, run_id="cross-screen-ac-claim"
                )

    def test_non_finite_layout_numbers_are_not_judgeable(self) -> None:
        scrim = {
            "element_id": "modal-scrim",
            "bounds": {"x": 0, "y": 96, "width": 1080, "height": 2256},
            "z": 5,
        }
        nan_order = _layout_report(CLEAN_BOUNDS, overlays=(scrim,))
        nan_order["elements"][0]["z"] = float("nan")  # type: ignore[index]
        oversized = _layout_report(CLEAN_BOUNDS, overlays=(scrim,))
        oversized["elements"][0]["z"] = 10**400  # type: ignore[index]
        cases = {
            "nan-stack-order": nan_order,
            "oversized-stack-order": oversized,
        }
        for name, layout in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._ux_config()
                config["commands"]["journey"] = _ui_journey_command(layout)
                config_path = _write_config(root, config)

                result = run_from_config(
                    root,
                    config_path=config_path,
                    run_id=name,
                    measured_at="2026-07-26T08:00:00Z",
                )

                self.assertEqual(result.exit_code, 1)
                self.assertIn(
                    "ux_integrity_report_invalid", result.receipt["failure_reasons"]
                )

    def test_receipt_snapshot_step_contract_is_revalidated_by_consumers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._multi_step_config()
            config["ux_integrity"] = _MULTI_SCREEN_SNAPSHOTS()
            config["commands"]["journey"] = _ui_journey_command(
                _layout_report(CLEAN_BOUNDS),
                _final_layout_report(),
                names=("first-layout.json", "final-layout.json"),
            )
            config_path = _write_config(root, config)
            result = run_from_config(
                root,
                config_path=config_path,
                run_id="snapshot-step-contract",
                measured_at="2026-07-26T08:00:00Z",
            )
            self.assertEqual(result.receipt["outcome"], "PASS")
            self.assertEqual(len(read_receipts(root)), 1)
            original = json.loads(result.receipt_path.read_text(encoding="utf-8"))

            def drop_final_snapshot(receipt: dict[str, object]) -> None:
                snapshots = receipt["ux_integrity"]["snapshots"]
                del snapshots[1]
                snapshots[0]["elements"][0]["target_ac"] = [
                    "AC-FIXTURE-1",
                    "AC-FIXTURE-2",
                ]

            def duplicate_first_snapshot(receipt: dict[str, object]) -> None:
                snapshots = receipt["ux_integrity"]["snapshots"]
                snapshots[1] = copy.deepcopy(snapshots[0])

            def rename_step(receipt: dict[str, object]) -> None:
                receipt["ux_integrity"]["snapshots"][1]["step_id"] = "never-declared"

            mutations = {
                "later-snapshot-dropped": drop_final_snapshot,
                "snapshot-step-duplicated": duplicate_first_snapshot,
                "snapshot-step-unknown": rename_step,
            }
            for name, mutate in mutations.items():
                with self.subTest(name=name):
                    candidate = copy.deepcopy(original)
                    mutate(candidate)
                    result.receipt_path.write_text(
                        json.dumps(candidate, ensure_ascii=False), encoding="utf-8"
                    )
                    self.assertEqual(read_receipts(root), [])

    def test_nested_child_element_is_not_treated_as_an_occluder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._ux_config()
            config["commands"]["journey"] = _ui_journey_command(
                _layout_report(
                    CLEAN_BOUNDS,
                    overlays=(
                        {
                            "element_id": "permission-banner-label",
                            "bounds": {
                                "x": 60,
                                "y": 420,
                                "width": 960,
                                "height": 80,
                            },
                            "z": 3,
                        },
                    ),
                )
            )
            config_path = _write_config(root, config)

            result = run_from_config(
                root,
                config_path=config_path,
                run_id="nested-child-element",
                measured_at="2026-07-26T08:00:00Z",
            )
            element = result.receipt["ux_integrity"]["snapshots"][0]["elements"][0]

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.receipt["outcome"], "PASS")
            self.assertEqual(element["occluded_by"], [])
            self.assertEqual(len(read_receipts(root)), 1)

    def test_forged_element_swap_over_the_same_report_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._ux_config()
            config["commands"]["journey"] = _ui_journey_command(
                _layout_report(
                    {"x": 40, "y": 40, "width": 1000, "height": 120},
                    overlays=(
                        {
                            "element_id": "safe-background",
                            "bounds": {
                                "x": 40,
                                "y": 700,
                                "width": 400,
                                "height": 200,
                            },
                            "z": 0,
                        },
                    ),
                )
            )
            config_path = _write_config(root, config)
            result = run_from_config(
                root,
                config_path=config_path,
                run_id="element-swap-forgery",
                measured_at="2026-07-26T08:00:00Z",
            )
            self.assertEqual(result.receipt["outcome"], "FAIL")
            self.assertIn(
                "ux_integrity_chrome_overlap", result.receipt["failure_reasons"]
            )

            forged = json.loads(result.receipt_path.read_text(encoding="utf-8"))
            forged.update(outcome="PASS", failure_reasons=[])
            forged["product_ac"].update(passed=forged["product_ac"]["total"])
            forged["ux_integrity"]["snapshots"][0]["elements"] = [
                {
                    "element_id": "safe-background",
                    "target_ac": ["AC-FIXTURE-1"],
                    "node_id": None,
                    "evaluated": True,
                    "bounds": {"x": 40.0, "y": 700.0, "width": 400.0, "height": 200.0},
                    "within_safe_area": True,
                    "occluded_by": [],
                }
            ]
            result.receipt_path.write_text(
                json.dumps(forged, ensure_ascii=False), encoding="utf-8"
            )

            self.assertEqual(read_receipts(root), [])

    def test_symlinked_layout_report_never_backs_a_valid_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._ux_config()
            config["commands"]["journey"] = _ui_journey_command(
                _layout_report(CLEAN_BOUNDS)
            )
            config_path = _write_config(root, config)
            result = run_from_config(
                root,
                config_path=config_path,
                run_id="layout-report-symlink",
                measured_at="2026-07-26T08:00:00Z",
            )
            self.assertEqual(len(read_receipts(root)), 1)

            run_dir = result.receipt_path.parent
            aliased = run_dir / "aliased-layout.json"
            report = run_dir / "layout.json"
            report.rename(aliased)
            report.symlink_to(aliased.name)

            self.assertEqual(read_receipts(root), [])

    def test_forged_ac_ownership_cannot_ride_a_valid_journey(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._ux_config()
            config["commands"]["journey"] = _ui_journey_command(
                _layout_report(CLEAN_BOUNDS)
            )
            config_path = _write_config(root, config)
            result = run_from_config(
                root,
                config_path=config_path,
                run_id="forged-ac-ownership",
                measured_at="2026-07-26T08:00:00Z",
            )
            self.assertEqual(result.receipt["outcome"], "PASS")
            self.assertEqual(len(read_receipts(root)), 1)

            forged = json.loads(result.receipt_path.read_text(encoding="utf-8"))
            forged["target_ac"] = ["AC-NEVER-TESTED"]
            for step in forged["ui_evidence"]["steps"]:
                step["target_ac"] = ["AC-NEVER-TESTED"]
            result.receipt_path.write_text(
                json.dumps(forged, ensure_ascii=False), encoding="utf-8"
            )

            self.assertEqual(read_receipts(root), [])

    def test_ux_integrity_contract_is_required_and_bound_to_declared_ac(self) -> None:
        cases: dict[str, object] = {
            "missing-for-ui-boundary": None,
            "snapshots-empty": {"snapshots": []},
            "step-id-not-declared": {
                "snapshots": [_ux_snapshot(step_id="never-declared")]
            },
            "final-evidence-step-not-judged": {
                "snapshots": [_ux_snapshot(step_id="first")]
            },
            "elements-empty": {
                "snapshots": [dict(_ux_snapshot(), elements=[])]
            },
            "element-ac-not-declared": {
                "snapshots": [_ux_snapshot(target_ac=("AC-UNDECLARED",))]
            },
            "layout-report-escapes-run-dir": {
                "snapshots": [_ux_snapshot(layout_report="../layout.json")]
            },
            "layout-report-shared-between-snapshots": {
                "snapshots": [
                    _ux_snapshot(step_id="first"),
                    _ux_snapshot(step_id="final"),
                ]
            },
            "layout-report-shared-by-case-alias": {
                "snapshots": [
                    _ux_snapshot(step_id="first", layout_report="layout.json"),
                    _ux_snapshot(step_id="final", layout_report="LAYOUT.json"),
                ]
            },
            "mockup-without-node-id": {
                "snapshots": [
                    _ux_snapshot(mockup="docs/design-variants/onboarding.html")
                ]
            },
        }
        for name, declared in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._ux_config()
                if declared is None:
                    config.pop("ux_integrity")
                else:
                    config["ux_integrity"] = declared
                config_path = _write_config(root, config)

                with self.assertRaises(JourneyConfigError):
                    run_from_config(root, config_path=config_path, run_id=name)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._base_config()
            config["ux_integrity"] = _ux_integrity()
            config_path = _write_config(root, config)

            with self.assertRaises(JourneyConfigError):
                run_from_config(root, config_path=config_path, run_id="cli-with-lens")

    def test_forged_ux_integrity_pass_receipt_is_ignored_by_scorecard_consumers(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._ux_config()
            config["commands"]["journey"] = _ui_journey_command(
                _layout_report(CLEAN_BOUNDS)
            )
            config_path = _write_config(root, config)
            result = run_from_config(
                root,
                config_path=config_path,
                run_id="ux-forgery-check",
                measured_at="2026-07-26T08:00:00Z",
            )
            self.assertEqual(len(read_receipts(root)), 1)
            original = json.loads(result.receipt_path.read_text(encoding="utf-8"))

            def element(receipt: dict[str, object]) -> dict[str, object]:
                return receipt["ux_integrity"]["snapshots"][0]["elements"][0]

            mutations = {
                "lens-dropped": lambda receipt: receipt.pop("ux_integrity"),
                "occlusion-hidden": lambda receipt: element(receipt).update(
                    occluded_by=["modal-scrim"]
                ),
                "chrome-overlap-hidden": lambda receipt: element(receipt).update(
                    within_safe_area=False
                ),
                "element-unevaluated": lambda receipt: element(receipt).update(
                    evaluated=False
                ),
                "bounds-restated": lambda receipt: element(receipt).update(
                    bounds={"x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0}
                ),
                "report-hash-forged": lambda receipt: receipt["ux_integrity"][
                    "snapshots"
                ][0]["layout_report"].update(sha256="0" * 64),
                "ac-coverage-dropped": lambda receipt: element(receipt).update(
                    target_ac=["AC-OTHER"]
                ),
            }
            for name, mutate in mutations.items():
                with self.subTest(name=name):
                    candidate = copy.deepcopy(original)
                    mutate(candidate)
                    result.receipt_path.write_text(
                        json.dumps(candidate, ensure_ascii=False), encoding="utf-8"
                    )
                    self.assertEqual(read_receipts(root), [])

    def test_forged_pass_over_occluded_layout_report_is_recomputed_and_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._ux_config()
            config["commands"]["journey"] = _ui_journey_command(
                _layout_report(
                    CLEAN_BOUNDS,
                    overlays=(
                        {
                            "element_id": "modal-scrim",
                            "bounds": {
                                "x": 0,
                                "y": 96,
                                "width": 1080,
                                "height": 2256,
                            },
                            "z": 5,
                        },
                    ),
                )
            )
            config_path = _write_config(root, config)
            result = run_from_config(
                root,
                config_path=config_path,
                run_id="ux-verdict-forgery",
                measured_at="2026-07-26T08:00:00Z",
            )
            self.assertEqual(result.receipt["outcome"], "FAIL")

            forged = json.loads(result.receipt_path.read_text(encoding="utf-8"))
            forged.update(outcome="PASS", failure_reasons=[])
            forged["product_ac"].update(passed=forged["product_ac"]["total"])
            forged["ux_integrity"]["snapshots"][0]["elements"][0].update(
                occluded_by=[]
            )
            result.receipt_path.write_text(
                json.dumps(forged, ensure_ascii=False), encoding="utf-8"
            )

            self.assertEqual(read_receipts(root), [])

    def test_tampered_log_invalidates_receipt_for_scorecard_consumers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = _write_config(root, self._base_config())
            result = run_from_config(
                root,
                config_path=config_path,
                run_id="tamper-check",
                measured_at="2026-07-12T08:00:00Z",
            )
            self.assertEqual(len(read_receipts(root)), 1)
            journey_log = root / result.receipt["evidence_paths"]["journey"]
            journey_log.write_text("tampered\n", encoding="utf-8")

            receipts = read_receipts(root)

        self.assertEqual(receipts, [])

    def test_tampered_ui_evidence_invalidates_receipt_for_scorecard_consumers(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._base_config()
            config["boundary"] = "ui"
            config["commands"] = dict(config["commands"])
            config["commands"]["journey"] = _ui_journey_command(
                _layout_report({"x": 40, "y": 400, "width": 1000, "height": 120})
            )
            config["ux_integrity"] = _ux_integrity()
            config["ui_evidence"] = {
                "steps": [
                    {
                        "step_id": "first",
                        "description": "첫 화면",
                        "target_ac": ["AC-FIXTURE-1"],
                        "final": False,
                        "evidence": [
                            {"path": "first.png", "type": "screenshot"}
                        ],
                    },
                    {
                        "step_id": "final",
                        "description": "최종 화면",
                        "target_ac": ["AC-FIXTURE-1"],
                        "final": True,
                        "evidence": [
                            {"path": "final.png", "type": "screenshot"}
                        ],
                    },
                ]
            }
            config_path = _write_config(root, config)
            result = run_from_config(
                root,
                config_path=config_path,
                run_id="ui-tamper-check",
                measured_at="2026-07-13T08:00:00Z",
            )
            self.assertEqual(len(read_receipts(root)), 1)
            ui_path = (
                root
                / result.receipt["ui_evidence"]["steps"][0]["evidence"][0]["path"]
            )
            ui_path.write_bytes(b"tampered")

            receipts = read_receipts(root)

        self.assertEqual(receipts, [])

    def test_malformed_or_incomplete_pass_receipts_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = _write_config(root, self._base_config())
            result = run_from_config(
                root,
                config_path=config_path,
                run_id="malformed-check",
                measured_at="2026-07-12T08:00:00Z",
            )
            original = json.loads(result.receipt_path.read_text(encoding="utf-8"))
            mutations = {
                "missing-run-id": lambda receipt: receipt.pop("run_id"),
                "non-string-ac": lambda receipt: receipt.update(target_ac=[1]),
                "negative-human-intervention": lambda receipt: receipt.update(
                    human_intervention_count=-1
                ),
                "pass-with-failure": lambda receipt: receipt.update(
                    failure_reasons=["forged"]
                ),
                "pass-without-cleanup": lambda receipt: (
                    receipt["commands"].pop("cleanup"),
                    receipt["evidence_paths"].pop("cleanup"),
                    receipt["evidence_sha256"].pop("cleanup"),
                ),
                "fail-with-passed-ac": lambda receipt: (
                    receipt.update(outcome="FAIL", failure_reasons=["journey_failed"]),
                    receipt["assertion"].update(passed=False),
                ),
                "fail-without-reason": lambda receipt: (
                    receipt.update(outcome="FAIL"),
                    receipt["product_ac"].update(passed=0),
                    receipt["assertion"].update(passed=False),
                ),
            }
            for name, mutate in mutations.items():
                with self.subTest(name=name):
                    candidate = copy.deepcopy(original)
                    mutate(candidate)
                    result.receipt_path.write_text(
                        json.dumps(candidate, ensure_ascii=False), encoding="utf-8"
                    )
                    self.assertEqual(read_receipts(root), [])


class ProductJourneyContractDocumentTests(unittest.TestCase):
    def test_contract_and_workflows_define_acceptance_execution_and_write_zero_handoff(
        self,
    ) -> None:
        contract = (ROOT / "docs/plugin/product-journey.md").read_text(encoding="utf-8")
        acceptance = (ROOT / "skills/acceptance/SKILL.md").read_text(encoding="utf-8")
        impl_loop = (
            (ROOT / "skills/impl-loop/SKILL.md").read_text(encoding="utf-8")
            + "\n"
            + (ROOT / "skills/impl-loop/impl-loop-finish.md").read_text(
                encoding="utf-8"
            )
        )
        product_acceptance = (
            ROOT
            / "docs/plugin/agents/product-acceptance/product-acceptance-agent.md"
        ).read_text(encoding="utf-8")
        init_contract = (ROOT / "docs/plugin/init-dcness.md").read_text(encoding="utf-8")
        deliverables = (ROOT / "docs/plugin/deliverables-map.md").read_text(
            encoding="utf-8"
        )

        for term in (
            "start",
            "health",
            "journey",
            "cleanup",
            "evidence_dir",
            "journey_exit",
            "mock_only_boundary",
            "ui_evidence.steps",
            "DCNESS_PRODUCT_JOURNEY_RUN_DIR",
            "screenshot",
            ".dcness-work/product-journey",
        ):
            self.assertIn(term, contract)
        for workflow in (acceptance, impl_loop):
            self.assertIn("dcness-product-journey", workflow)
            self.assertIn("product-acceptance", workflow)
            self.assertIn("receipt", workflow)
        self.assertIn("app_started", product_acceptance)
        self.assertIn("journey_executed", product_acceptance)
        self.assertIn("assertion", product_acceptance)
        self.assertIn("ui_evidence.steps", product_acceptance)
        self.assertIn("present=true", product_acceptance)
        self.assertIn("dcness-product-journey run", product_acceptance)
        self.assertIn("write-zero", product_acceptance)
        self.assertIn("tracked 구현·설계 소스", product_acceptance)
        self.assertIn("사용자 repo에 복사하지", init_contract)
        self.assertIn("dcness-product-journey", init_contract)
        self.assertIn(".dcness-work/product-journey/", deliverables)

    def test_contract_defines_ux_integrity_lens_and_mockup_link(self) -> None:
        contract = (ROOT / "docs/plugin/product-journey.md").read_text(encoding="utf-8")
        product_acceptance = (
            ROOT
            / "docs/plugin/agents/product-acceptance/product-acceptance-agent.md"
        ).read_text(encoding="utf-8")
        impl_task = (
            ROOT / "docs/plugin/agents/module-architect/templates/impl-task.md"
        ).read_text(encoding="utf-8")
        build_worker = (
            ROOT / "docs/plugin/agents/build-worker/build-worker-agent.md"
        ).read_text(encoding="utf-8")

        for term in (
            "UX 정합성",
            "ux_integrity",
            "layout_report",
            "safe_area",
            "mockup_reference",
            "node_id",
            "ux_integrity_chrome_overlap",
            "ux_integrity_occluded",
        ):
            self.assertIn(term, contract)
        self.assertIn("가시성 assertion", contract)
        self.assertIn("docs/design-variants/", contract)
        for consumer in (product_acceptance, impl_task, build_worker):
            self.assertIn("ux_integrity", consumer)
        self.assertIn("data-node-id", impl_task)


if __name__ == "__main__":
    unittest.main()

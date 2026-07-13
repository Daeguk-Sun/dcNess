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
    CONFIG_REL,
    JourneyConfigError,
    read_receipts,
    run_from_config,
)


ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _command(code: str) -> dict[str, object]:
    return {"argv": [sys.executable, "-c", code], "timeout_sec": 10}


def _write_config(root: Path, payload: dict[str, object]) -> Path:
    path = root / CONFIG_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


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
            config["commands"]["journey"] = _command(
                "import json, os; from pathlib import Path; "
                "run=Path(os.environ['DCNESS_PRODUCT_JOURNEY_RUN_DIR']); "
                "(run/'landing.png').write_bytes(b'fixture-png'); "
                "(run/'onboarding-state.json').write_text(json.dumps({'consent': True})); "
                "(run/'results.png').write_bytes(b'fixture-results-png')"
            )
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
            config["commands"]["journey"] = _command(
                "import os; from pathlib import Path; "
                "run=Path(os.environ['DCNESS_PRODUCT_JOURNEY_RUN_DIR']); "
                "(run/'first.png').write_bytes(b'first'); "
                "(run/'final.png').write_bytes(b'final')"
            )
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
            config["commands"]["journey"] = _command(
                "import os; from pathlib import Path; "
                "run=Path(os.environ['DCNESS_PRODUCT_JOURNEY_RUN_DIR']); "
                "(run/'first.png').write_bytes(b'first'); "
                "(run/'final.png').write_bytes(b'final')"
            )
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
        impl_loop = (ROOT / "skills/impl-loop/SKILL.md").read_text(encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()

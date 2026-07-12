"""Project-local non-UI product journey execution contract tests."""

from __future__ import annotations

import copy
import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path

from harness.product_journey import CONFIG_REL, read_receipts, run_from_config


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
    def test_contract_and_main_workflows_define_execution_and_read_only_handoff(
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
        self.assertIn("읽기 전용", product_acceptance)
        self.assertIn("사용자 repo에 복사하지", init_contract)
        self.assertIn("dcness-product-journey", init_contract)
        self.assertIn(".dcness-work/product-journey/", deliverables)


if __name__ == "__main__":
    unittest.main()

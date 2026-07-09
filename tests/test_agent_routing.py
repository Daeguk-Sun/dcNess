"""Tests for local agent provider routing."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from harness import agent_routing


class AgentRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.path = Path(self._td.name) / "routing.json"
        self._old_env = os.environ.get("DCNESS_ROUTING_PATH")
        os.environ["DCNESS_ROUTING_PATH"] = str(self.path)

    def tearDown(self) -> None:
        if self._old_env is None:
            os.environ.pop("DCNESS_ROUTING_PATH", None)
        else:
            os.environ["DCNESS_ROUTING_PATH"] = self._old_env
        self._td.cleanup()

    def test_missing_config_defaults_to_claude(self) -> None:
        self.assertEqual(agent_routing.resolve_provider("impl-validator"), "claude")
        self.assertEqual(agent_routing.resolve_provider("engineer"), "headless-chain")
        self.assertEqual(agent_routing.resolve_provider("unknown-agent"), "claude")
        self.assertFalse(self.path.exists())

    def test_enable_codex_validation_routes_only_validators(self) -> None:
        agent_routing.enable_codex_validation()
        for agent in agent_routing.ROUTABLE_VALIDATION_AGENTS:
            self.assertEqual(agent_routing.resolve_provider(agent), "codex")
        self.assertEqual(agent_routing.resolve_provider("engineer"), "headless-chain")

    def test_disable_codex_validation_returns_validators_to_claude(self) -> None:
        agent_routing.enable_codex_validation()
        agent_routing.disable_codex_validation()
        for agent in agent_routing.ROUTABLE_VALIDATION_AGENTS:
            self.assertEqual(agent_routing.resolve_provider(agent), "claude")

    def test_set_provider_validates_agent_and_provider(self) -> None:
        agent_routing.set_provider("impl-validator", "codex")
        self.assertEqual(agent_routing.resolve_provider("impl-validator"), "codex")
        with self.assertRaises(ValueError):
            agent_routing.set_provider("engineer", "codex")
        with self.assertRaises(ValueError):
            agent_routing.set_provider("impl-validator", "openai")

    def test_implementation_routes_can_disable_and_enable_headless_chain(self) -> None:
        agent_routing.disable_codex_implementation()
        for agent in agent_routing.ROUTABLE_IMPLEMENTATION_AGENTS:
            self.assertEqual(agent_routing.resolve_provider(agent), "claude")

        agent_routing.enable_headless_implementation()
        for agent in agent_routing.ROUTABLE_IMPLEMENTATION_AGENTS:
            self.assertEqual(agent_routing.resolve_provider(agent), "headless-chain")

    def test_legacy_enable_codex_implementation_keeps_codex_first_semantics(self) -> None:
        agent_routing.enable_codex_implementation()
        for agent in agent_routing.ROUTABLE_IMPLEMENTATION_AGENTS:
            self.assertEqual(agent_routing.resolve_provider(agent), "codex-first")

    def test_role_split_preset_routes_implementation_and_contract_roles(self) -> None:
        agent_routing.enable_role_split_routing()

        self.assertEqual(agent_routing.resolve_provider("engineer"), "headless-chain")
        self.assertEqual(agent_routing.resolve_provider("build-worker"), "headless-chain")
        self.assertEqual(agent_routing.resolve_provider("test-engineer"), "claude")
        self.assertEqual(agent_routing.resolve_provider("impl-validator"), "claude")
        self.assertEqual(agent_routing.resolve_provider("architecture-validator"), "codex")
        self.assertEqual(agent_routing.doctor(), [])

    def test_set_implementation_provider_validates_agent_and_provider(self) -> None:
        agent_routing.set_implementation_provider("build-worker", "claude")
        self.assertEqual(agent_routing.resolve_provider("build-worker"), "claude")
        agent_routing.set_implementation_provider("build-worker", "claude-headless")
        self.assertEqual(agent_routing.resolve_provider("build-worker"), "claude-headless")
        agent_routing.set_implementation_provider("build-worker", "headless-chain")
        self.assertEqual(agent_routing.resolve_provider("build-worker"), "headless-chain")
        with self.assertRaises(ValueError):
            agent_routing.set_implementation_provider("impl-validator", "claude")
        with self.assertRaises(ValueError):
            agent_routing.set_implementation_provider("build-worker", "codex")

    def test_doctor_reports_invalid_config(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "version": 999,
                    "routes": {
                        "impl-validator": "codex",
                        "engineer": "codex",
                        "legacy-reviewer": "other",
                    },
                    "implementation_routes": {
                        "build-worker": "codex",
                        "engineer": "unknown-chain",
                        "designer": "codex-first",
                    },
                }
            ),
            encoding="utf-8",
        )
        problems = agent_routing.doctor()
        self.assertTrue(any("unsupported version" in p for p in problems))
        self.assertTrue(
            any("unknown validation agent route: engineer" in p for p in problems)
        )
        self.assertTrue(any("unknown validation agent route: legacy-reviewer" in p for p in problems))
        self.assertTrue(
            any("invalid implementation provider for build-worker" in p for p in problems)
        )
        self.assertTrue(
            any("unknown implementation agent route: designer" in p for p in problems)
        )
        self.assertTrue(
            any("invalid implementation provider for engineer" in p for p in problems)
        )

    def test_status_includes_effective_routes(self) -> None:
        agent_routing.set_provider("architecture-validator", "codex")
        agent_routing.set_implementation_provider("build-worker", "claude")
        text = agent_routing.format_status()
        self.assertIn("[dcness routing] status: OK", text)
        self.assertIn("[dcness routing] validation:", text)
        self.assertIn("[dcness routing] implementation:", text)
        self.assertIn("architecture-validator: codex", text)
        self.assertIn("impl-validator: claude", text)
        self.assertIn("build-worker: claude", text)
        self.assertIn("engineer: headless-chain", text)

    def test_v1_config_is_supported_and_defaults_implementation_to_headless_chain(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "routes": {
                        "impl-validator": "codex",
                    },
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(agent_routing.doctor(), [])
        self.assertEqual(agent_routing.resolve_provider("impl-validator"), "codex")
        self.assertEqual(agent_routing.resolve_provider("build-worker"), "headless-chain")

    def test_v2_explicit_codex_first_keeps_legacy_chain(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "version": 2,
                    "routes": {},
                    "implementation_routes": {"build-worker": "codex-first"},
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(agent_routing.doctor(), [])
        self.assertEqual(agent_routing.resolve_provider("build-worker"), "codex-first")


class AgentRoutingCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.path = Path(self._td.name) / "routing.json"
        self._old_env = os.environ.get("DCNESS_ROUTING_PATH")
        os.environ["DCNESS_ROUTING_PATH"] = str(self.path)

    def tearDown(self) -> None:
        if self._old_env is None:
            os.environ.pop("DCNESS_ROUTING_PATH", None)
        else:
            os.environ["DCNESS_ROUTING_PATH"] = self._old_env
        self._td.cleanup()

    def test_argparse_routing_resolve(self) -> None:
        from harness.session_state import _build_arg_parser

        parser = _build_arg_parser()
        ns = parser.parse_args(["routing", "resolve", "impl-validator"])
        self.assertEqual(ns.cmd, "routing")
        self.assertEqual(ns.routing_cmd, "resolve")
        self.assertEqual(ns.agent, "impl-validator")

        ns = parser.parse_args(["routing", "enable-role-split-routing"])
        self.assertEqual(ns.routing_cmd, "enable-role-split-routing")

        ns = parser.parse_args(
            ["routing", "set-implementation", "build-worker", "claude-headless"]
        )
        self.assertEqual(ns.routing_cmd, "set-implementation")
        self.assertEqual(ns.agent, "build-worker")
        self.assertEqual(ns.provider, "claude-headless")

    def test_cli_enable_and_resolve(self) -> None:
        from harness.session_state import _cli_routing

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_routing(SimpleNamespace(routing_cmd="enable-codex-validation"))
        self.assertEqual(rc, 0)
        self.assertIn("enabled Codex validation", out.getvalue())

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_routing(
                SimpleNamespace(routing_cmd="resolve", agent="impl-validator")
            )
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), "codex")

    def test_cli_implementation_modes_and_resolve(self) -> None:
        from harness.session_state import _cli_routing

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_routing(SimpleNamespace(routing_cmd="disable-codex-implementation"))
        self.assertEqual(rc, 0)
        self.assertIn("disabled Codex implementation", out.getvalue())

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_routing(
                SimpleNamespace(routing_cmd="resolve", agent="build-worker")
            )
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), "claude")

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_routing(SimpleNamespace(routing_cmd="enable-headless-implementation"))
        self.assertEqual(rc, 0)
        self.assertIn("enabled headless implementation chain", out.getvalue())

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_routing(
                SimpleNamespace(routing_cmd="resolve", agent="build-worker")
            )
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), "headless-chain")

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_routing(
                SimpleNamespace(routing_cmd="enable-claude-headless-implementation")
            )
        self.assertEqual(rc, 0)
        self.assertIn("enabled Claude headless implementation", out.getvalue())

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_routing(
                SimpleNamespace(routing_cmd="resolve", agent="build-worker")
            )
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), "claude-headless")

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_routing(
                SimpleNamespace(
                    routing_cmd="set-implementation",
                    agent="build-worker",
                    provider="codex-first",
                )
            )
        self.assertEqual(rc, 0)
        self.assertIn("set implementation build-worker=codex-first", out.getvalue())

    def test_cli_role_split_routing_preset_and_doctor(self) -> None:
        from harness.session_state import _cli_routing

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_routing(SimpleNamespace(routing_cmd="enable-role-split-routing"))
        self.assertEqual(rc, 0)
        text = out.getvalue()
        self.assertIn("enabled role-split routing", text)
        self.assertIn("architecture-validator: codex", text)
        self.assertIn("impl-validator: claude", text)
        self.assertIn("test-engineer: claude", text)
        self.assertIn("engineer: headless-chain", text)
        self.assertIn("build-worker: headless-chain", text)

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_routing(SimpleNamespace(routing_cmd="doctor"))
        self.assertEqual(rc, 0)
        self.assertIn("[dcness routing] doctor: PASS", out.getvalue())

    def test_cli_doctor_fails_on_bad_file(self) -> None:
        from harness.session_state import _cli_routing

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{bad json", encoding="utf-8")
        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_routing(SimpleNamespace(routing_cmd="doctor"))
        self.assertEqual(rc, 1)
        self.assertIn("status: INVALID", out.getvalue())


class InitRoleSplitRoutingDocsTests(unittest.TestCase):
    def test_init_docs_recommend_role_split_preset_and_keep_custom_routes(self) -> None:
        root = Path(__file__).resolve().parents[1]
        command = (root / "commands" / "init-dcness.md").read_text(
            encoding="utf-8",
        )
        doc = (root / "docs" / "plugin" / "init-dcness.md").read_text(
            encoding="utf-8",
        )

        for text in (command, doc):
            with self.subTest(text=text[:40]):
                self.assertIn("enable-role-split-routing", text)
                self.assertIn("engineer/build-worker=headless-chain", text)
                self.assertIn("test-engineer/impl-validator=claude", text)
                self.assertIn("architecture-validator=codex", text)
                self.assertIn("기존 활성 프로젝트", text)
                self.assertIn("routing doctor", text)
                self.assertIn("enable-codex-validation", text)
                self.assertIn("enable-codex-implementation", text)
                self.assertIn("disable-codex-implementation", text)


if __name__ == "__main__":
    unittest.main()

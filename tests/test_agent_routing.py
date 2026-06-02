"""Tests for local validation-agent provider routing."""
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
        self.assertEqual(agent_routing.resolve_provider("code-validator"), "claude")
        self.assertEqual(agent_routing.resolve_provider("engineer"), "claude")
        self.assertFalse(self.path.exists())

    def test_enable_codex_validation_routes_only_validators(self) -> None:
        agent_routing.enable_codex_validation()
        for agent in agent_routing.ROUTABLE_VALIDATION_AGENTS:
            self.assertEqual(agent_routing.resolve_provider(agent), "codex")
        self.assertEqual(agent_routing.resolve_provider("engineer"), "claude")

    def test_disable_codex_validation_returns_validators_to_claude(self) -> None:
        agent_routing.enable_codex_validation()
        agent_routing.disable_codex_validation()
        for agent in agent_routing.ROUTABLE_VALIDATION_AGENTS:
            self.assertEqual(agent_routing.resolve_provider(agent), "claude")

    def test_set_provider_validates_agent_and_provider(self) -> None:
        agent_routing.set_provider("pr-reviewer", "codex")
        self.assertEqual(agent_routing.resolve_provider("pr-reviewer"), "codex")
        with self.assertRaises(ValueError):
            agent_routing.set_provider("engineer", "codex")
        with self.assertRaises(ValueError):
            agent_routing.set_provider("pr-reviewer", "openai")

    def test_doctor_reports_invalid_config(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "version": 999,
                    "routes": {
                        "code-validator": "codex",
                        "engineer": "codex",
                        "pr-reviewer": "other",
                    },
                }
            ),
            encoding="utf-8",
        )
        problems = agent_routing.doctor()
        self.assertTrue(any("unsupported version" in p for p in problems))
        self.assertTrue(any("unknown agent route: engineer" in p for p in problems))
        self.assertTrue(any("invalid provider for pr-reviewer" in p for p in problems))

    def test_status_includes_effective_routes(self) -> None:
        agent_routing.set_provider("architecture-validator", "codex")
        text = agent_routing.format_status()
        self.assertIn("[dcness routing] status: OK", text)
        self.assertIn("architecture-validator: codex", text)
        self.assertIn("code-validator: claude", text)


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
        ns = parser.parse_args(["routing", "resolve", "code-validator"])
        self.assertEqual(ns.cmd, "routing")
        self.assertEqual(ns.routing_cmd, "resolve")
        self.assertEqual(ns.agent, "code-validator")

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
                SimpleNamespace(routing_cmd="resolve", agent="code-validator")
            )
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), "codex")

    def test_cli_doctor_fails_on_bad_file(self) -> None:
        from harness.session_state import _cli_routing

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{bad json", encoding="utf-8")
        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_routing(SimpleNamespace(routing_cmd="doctor"))
        self.assertEqual(rc, 1)
        self.assertIn("status: INVALID", out.getvalue())


if __name__ == "__main__":
    unittest.main()

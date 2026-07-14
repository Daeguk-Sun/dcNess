"""Tests for local agent provider routing."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from harness import agent_routing
from harness.session_state_cli import _build_arg_parser, _cli_routing


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

    def test_missing_config_defaults_impl_validator_to_cross_provider(self) -> None:
        self.assertEqual(
            agent_routing.resolve_provider("impl-validator", codex_available=True),
            "codex",
        )
        self.assertEqual(
            agent_routing.resolve_provider("impl-validator", codex_available=False),
            "claude",
        )
        self.assertEqual(agent_routing.resolve_provider("build-worker"), "headless-chain")
        self.assertEqual(agent_routing.resolve_provider("unknown-agent"), "claude")
        self.assertFalse(self.path.exists())

    def test_impl_validator_default_crosses_build_worker_implementation_camp(self) -> None:
        self.assertEqual(
            agent_routing.resolve_provider(
                "impl-validator",
                implementation_provider="headless-chain",
                codex_available=True,
            ),
            "claude",
        )
        self.assertEqual(
            agent_routing.resolve_provider(
                "impl-validator",
                implementation_provider="claude-headless",
                codex_available=True,
            ),
            "codex",
        )

    def test_enable_codex_validation_routes_only_validators(self) -> None:
        agent_routing.enable_codex_validation()
        for agent in agent_routing.ROUTABLE_VALIDATION_AGENTS:
            self.assertEqual(agent_routing.resolve_provider(agent), "codex")
        self.assertEqual(agent_routing.resolve_provider("build-worker"), "headless-chain")

    def test_disable_codex_validation_returns_validators_to_claude(self) -> None:
        agent_routing.enable_codex_validation()
        agent_routing.disable_codex_validation()
        for agent in agent_routing.ROUTABLE_VALIDATION_AGENTS:
            self.assertEqual(agent_routing.resolve_provider(agent), "claude")

    def test_set_provider_validates_agent_and_provider(self) -> None:
        agent_routing.set_provider("impl-validator", "codex")
        self.assertEqual(agent_routing.resolve_provider("impl-validator"), "codex")
        with self.assertRaises(ValueError):
            agent_routing.set_provider("build-worker", "codex")
        with self.assertRaises(ValueError):
            agent_routing.set_provider("impl-validator", "openai")

    def test_implementation_routes_can_select_claude_and_headless_chain(self) -> None:
        agent_routing.set_implementation_provider("build-worker", "claude")
        for agent in agent_routing.ROUTABLE_IMPLEMENTATION_AGENTS:
            self.assertEqual(agent_routing.resolve_provider(agent), "claude")

        agent_routing.enable_headless_implementation()
        for agent in agent_routing.ROUTABLE_IMPLEMENTATION_AGENTS:
            self.assertEqual(agent_routing.resolve_provider(agent), "headless-chain")

    def test_legacy_aliases_are_not_public_or_routable(self) -> None:
        self.assertNotIn("VALID_PROVIDERS", agent_routing.__all__)
        self.assertFalse(hasattr(agent_routing, "VALID_PROVIDERS"))
        self.assertFalse(hasattr(agent_routing, "enable_codex_implementation"))
        self.assertFalse(hasattr(agent_routing, "disable_codex_implementation"))
        self.assertEqual(
            agent_routing.implementation_provider_chain("codex-first"),
            ("claude-main",),
        )

    def test_role_split_preset_routes_implementation_and_contract_roles(self) -> None:
        agent_routing.enable_role_split_routing()

        self.assertEqual(agent_routing.resolve_provider("build-worker"), "headless-chain")
        self.assertEqual(agent_routing.resolve_provider("impl-validator"), "codex")
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
        with self.assertRaises(ValueError):
            agent_routing.set_implementation_provider("build-worker", "codex-first")

    def test_doctor_reports_invalid_config(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "version": 999,
                    "routes": {
                        "impl-validator": "codex",
                        "build-worker": "codex",
                        "legacy-reviewer": "other",
                    },
                    "implementation_routes": {
                        "engineer": "unknown-chain",
                        "test-engineer": "claude",
                        "designer": "codex-first",
                    },
                }
            ),
            encoding="utf-8",
        )
        problems = agent_routing.doctor()
        self.assertTrue(any("unsupported version" in p for p in problems))
        self.assertTrue(
            any("unknown validation agent route: build-worker" in p for p in problems)
        )
        self.assertTrue(any("unknown validation agent route: legacy-reviewer" in p for p in problems))
        self.assertTrue(
            any("unknown implementation agent route: designer" in p for p in problems)
        )
        self.assertTrue(
            any("unknown implementation agent route: engineer" in p for p in problems)
        )
        self.assertTrue(
            any("unknown implementation agent route: test-engineer" in p for p in problems)
        )

    def test_status_includes_effective_routes(self) -> None:
        agent_routing.set_provider("architecture-validator", "codex")
        agent_routing.set_implementation_provider("build-worker", "claude")
        text = agent_routing.format_status()
        self.assertIn("[dcness routing] status: OK", text)
        self.assertIn("[dcness routing] validation:", text)
        self.assertIn("[dcness routing] implementation:", text)
        self.assertIn("architecture-validator: codex", text)
        self.assertIn("impl-validator:", text)
        self.assertIn("build-worker: claude", text)

    def test_v1_config_requires_migration_and_uses_safe_routes(self) -> None:
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
        problems = agent_routing.doctor()
        self.assertTrue(any("unsupported version: 1" in problem for problem in problems))
        self.assertEqual(agent_routing.resolve_provider("impl-validator"), "claude")
        self.assertEqual(agent_routing.resolve_provider("build-worker"), "claude")
        self.assertIn("impl-validator: claude", agent_routing.format_status())
        self.assertIn("build-worker: claude", agent_routing.format_status())

    def test_v2_codex_first_requires_migration_and_uses_safe_routes(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "version": 2,
                    "routes": {"pr-reviewer": "claude"},
                    "implementation_routes": {"build-worker": "codex-first"},
                }
            ),
            encoding="utf-8",
        )
        problems = agent_routing.doctor()
        self.assertTrue(any("unsupported version: 2" in problem for problem in problems))
        self.assertTrue(
            any(
                "invalid implementation provider for build-worker: codex-first" in problem
                for problem in problems
            )
        )
        self.assertEqual(agent_routing.resolve_provider("build-worker"), "claude")

        agent_routing.enable_role_split_routing()
        self.assertEqual(agent_routing.load_routing()["version"], 3)
        self.assertEqual(agent_routing.doctor(), [])
        self.assertEqual(agent_routing.resolve_provider("build-worker"), "headless-chain")


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

        parser = _build_arg_parser()
        ns = parser.parse_args(["routing", "resolve", "impl-validator"])
        self.assertEqual(ns.cmd, "routing")
        self.assertEqual(ns.routing_cmd, "resolve")
        self.assertEqual(ns.agent, "impl-validator")
        self.assertIsNone(ns.implementation_provider)

        ns = parser.parse_args(["routing", "enable-role-split-routing"])
        self.assertEqual(ns.routing_cmd, "enable-role-split-routing")

        ns = parser.parse_args(
            [
                "routing",
                "resolve",
                "impl-validator",
                "--implementation-provider",
                "headless-chain",
            ]
        )
        self.assertEqual(ns.routing_cmd, "resolve")
        self.assertEqual(ns.agent, "impl-validator")
        self.assertEqual(ns.implementation_provider, "headless-chain")

        ns = parser.parse_args(
            ["routing", "set-implementation", "build-worker", "claude-headless"]
        )
        self.assertEqual(ns.routing_cmd, "set-implementation")
        self.assertEqual(ns.agent, "build-worker")
        self.assertEqual(ns.provider, "claude-headless")

        for argv in (
            ["routing", "enable-codex-implementation"],
            ["routing", "disable-codex-implementation"],
            ["routing", "set-implementation", "build-worker", "codex-first"],
        ):
            with self.subTest(argv=argv), redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit):
                    parser.parse_args(argv)

    def test_cli_enable_and_resolve(self) -> None:

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

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_routing(
                SimpleNamespace(
                    routing_cmd="resolve",
                    agent="impl-validator",
                    implementation_provider="headless-chain",
                    main_provider="claude",
                )
            )
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), "codex")

    def test_cli_resolve_impl_validator_crosses_impl_loop_provider(self) -> None:

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_routing(
                SimpleNamespace(
                    routing_cmd="resolve",
                    agent="impl-validator",
                    implementation_provider="headless-chain",
                    main_provider="claude",
                )
            )
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), "claude")

    def test_cli_implementation_modes_and_resolve(self) -> None:

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_routing(
                SimpleNamespace(
                    routing_cmd="set-implementation",
                    agent="build-worker",
                    provider="claude",
                )
            )
        self.assertEqual(rc, 0)
        self.assertIn("set implementation build-worker=claude", out.getvalue())

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

    def test_cli_role_split_routing_preset_and_doctor(self) -> None:

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_routing(SimpleNamespace(routing_cmd="enable-role-split-routing"))
        self.assertEqual(rc, 0)
        text = out.getvalue()
        self.assertIn("enabled role-split routing", text)
        self.assertIn("architecture-validator: codex", text)
        self.assertIn("impl-validator: codex", text)
        self.assertIn("build-worker: headless-chain", text)

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_routing(SimpleNamespace(routing_cmd="doctor"))
        self.assertEqual(rc, 0)
        self.assertIn("[dcness routing] doctor: PASS", out.getvalue())

    def test_cli_doctor_fails_on_bad_file(self) -> None:

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{bad json", encoding="utf-8")
        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_routing(SimpleNamespace(routing_cmd="doctor"))
        self.assertEqual(rc, 1)
        self.assertIn("status: INVALID", out.getvalue())


class InitRoleSplitRoutingDocsTests(unittest.TestCase):
    def test_init_docs_recommend_role_split_preset_and_current_custom_routes(self) -> None:
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
                self.assertIn("build-worker=headless-chain", text)
                self.assertIn("impl-validator=codex", text)
                self.assertIn("architecture-validator=codex", text)
                self.assertIn("기존 활성 프로젝트", text)
                self.assertIn("routing doctor", text)
                self.assertIn("enable-codex-validation", text)
                self.assertIn("set-implementation build-worker claude", text)
                self.assertNotIn("enable-codex-implementation", text)
                self.assertNotIn("disable-codex-implementation", text)
                self.assertNotIn("codex-first", text)


if __name__ == "__main__":
    unittest.main()

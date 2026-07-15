"""Compact contracts for active session-state CLI and activation surfaces."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from harness import ledger, session_state
from harness import session_state_activation as activation
from harness import session_state_cli as cli
from harness import session_state_cli_finalize as finalize


class SessionCliLifecycleContractTests(unittest.TestCase):
    sid = "sid-cli-contract"
    rid = "run-a1b2c3d4"
    cc_pid = 45678

    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.previous_cwd = Path.cwd()
        os.chdir(self.base)
        session_state._clear_default_base_cache()
        session_state.transition(
            self.sid,
            "run_started",
            run_id=self.rid,
            entry_point="impl",
            lane="lite",
        )
        session_state.write_pid_session(self.cc_pid, self.sid)
        session_state.write_pid_current_run(self.cc_pid, self.rid)
        self.pid_patch = patch(
            "harness.session_state.get_cc_pid_via_ppid_chain",
            return_value=self.cc_pid,
        )
        self.pid_patch.start()

    def tearDown(self) -> None:
        self.pid_patch.stop()
        os.chdir(self.previous_cwd)
        session_state._clear_default_base_cache()
        self.tmp.cleanup()

    def _complete(self, agent: str, prose: str) -> Path:
        session_state.transition(
            self.sid,
            "step_started",
            run_id=self.rid,
            agent=agent,
            mode=None,
        )
        source = self.base / f"{agent}-source.md"
        source.write_text(prose, encoding="utf-8")
        return source

    def test_end_step_logs_prose_receipt_and_rejects_missing_input(self) -> None:
        source = self._complete("impl-validator", "검증 완료\n\nPASS\n")
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            rc = finalize._cli_end_step(
                SimpleNamespace(
                    agent="dcness:impl-validator",
                    mode=None,
                    prose_file=str(source),
                    provider="claude",
                )
            )

        self.assertEqual(rc, 0)
        self.assertEqual(stdout.getvalue().strip(), "PROSE_LOGGED")
        self.assertIn("[impl-validator = PROSE_LOGGED]", stderr.getvalue())
        steps = ledger.read_step_completed(self.sid, self.rid)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["agent"], "impl-validator")
        self.assertEqual(steps[0]["provider"], "claude")
        self.assertTrue(Path(steps[0]["prose_file"]).is_file())

        missing = StringIO()
        with redirect_stderr(missing):
            rc = finalize._cli_end_step(
                SimpleNamespace(
                    agent="build-worker",
                    mode=None,
                    prose_file=None,
                    provider=None,
                )
            )
        self.assertEqual(rc, 1)
        self.assertIn("hook staging 없음", missing.getvalue())

    def test_finalize_run_emits_status_persists_snapshot_and_chains_review(self) -> None:
        source = self._complete("impl-validator", "MUST FIX 없음\n\nPASS\n")
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(
                finalize._cli_end_step(
                    SimpleNamespace(
                        agent="impl-validator",
                        mode=None,
                        prose_file=str(source),
                        provider=None,
                    )
                ),
                0,
            )

        def fake_review(argv: list[str]) -> int:
            self.assertEqual(argv[:2], ["--run-id", self.rid])
            print("review complete\n\nPASS")
            return 0

        stdout = StringIO()
        stderr = StringIO()
        with patch("harness.run_review.main", side_effect=fake_review), redirect_stdout(
            stdout
        ), redirect_stderr(stderr):
            rc = finalize._cli_finalize_run(
                SimpleNamespace(expected_steps=2, auto_review=True)
            )

        self.assertEqual(rc, 0)
        status_text = stdout.getvalue().split("\n\n--- /run-review", 1)[0]
        status = json.loads(status_text)
        self.assertEqual(status["step_count"], 1)
        self.assertFalse(status["has_must_fix"])
        self.assertIn("STEP COUNT WARN", stderr.getvalue())
        self.assertIn("[REVIEW_READY]", stderr.getvalue())
        slot = session_state.read_live(self.sid)["active_runs"][self.rid]
        self.assertIsNotNone(slot["finalized_at"])
        review = session_state.run_dir(self.sid, self.rid) / "review.md"
        self.assertIn("review complete", review.read_text(encoding="utf-8"))

    def test_auto_resolve_matrix_preserves_actions_and_exit_codes(self) -> None:
        cases = (
            ("ux-architect:UX_FLOW_ESCALATE", 0, "re-invoke"),
            ("architecture-validator:FAIL", 0, "route-by-classification"),
            ("future-agent:AMBIGUOUS", 0, "user-delegate"),
            ("future-agent:MYSTERY", 1, "unmapped"),
        )
        for key, expected_rc, expected_action in cases:
            with self.subTest(key=key):
                output = StringIO()
                with redirect_stdout(output):
                    rc = finalize._cli_auto_resolve(SimpleNamespace(agent_mode=key))
                self.assertEqual(rc, expected_rc)
                self.assertEqual(json.loads(output.getvalue())["action"], expected_action)


class AutoDetectionContractTests(unittest.TestCase):
    def test_environment_then_open_run_scan_and_completed_exclusion(self) -> None:
        sid = "sid-auto-detect"
        rid = "run-bbbbbbbb"
        with TemporaryDirectory() as td:
            base = Path(td)
            session_state.transition(
                sid,
                "run_started",
                run_id=rid,
                entry_point="impl",
                lane="lite",
                base_dir=base,
            )
            session_state.transition(
                sid,
                "run_finalized",
                run_id=rid,
                base_dir=base,
            )
            empty_env = {"DCNESS_SESSION_ID": "", "DCNESS_RUN_ID": ""}
            with patch.dict(os.environ, empty_env, clear=False), patch(
                "harness.session_state.get_cc_pid_via_ppid_chain", return_value=None
            ):
                self.assertEqual(session_state.auto_detect_session_id(base_dir=base), sid)
                self.assertEqual(session_state.auto_detect_run_id(base_dir=base), rid)

                session_state.transition(
                    sid,
                    "run_completed",
                    run_id=rid,
                    base_dir=base,
                )
                self.assertEqual(session_state.auto_detect_session_id(base_dir=base), "")
                self.assertEqual(session_state.auto_detect_run_id(base_dir=base), "")

            explicit = {
                "DCNESS_SESSION_ID": "sid-explicit",
                "DCNESS_RUN_ID": "run-explicit",
            }
            with patch.dict(os.environ, explicit, clear=False):
                self.assertEqual(
                    session_state.auto_detect_session_id(base_dir=base), "sid-explicit"
                )
                self.assertEqual(
                    session_state.auto_detect_run_id(base_dir=base), "run-explicit"
                )


class ProjectActivationContractTests(unittest.TestCase):
    def test_enable_gate_disable_and_force_override_share_one_whitelist(self) -> None:
        with TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            whitelist = base / "projects.json"
            env = {"DCNESS_WHITELIST_PATH": str(whitelist)}
            with patch.dict(os.environ, env, clear=False), patch.object(
                activation, "_resolve_project_root", return_value=project
            ):
                self.assertEqual(cli._cli_is_active(SimpleNamespace()), 1)
                with redirect_stdout(StringIO()):
                    self.assertEqual(cli._cli_enable(SimpleNamespace()), 0)
                self.assertEqual(cli._cli_is_active(SimpleNamespace()), 0)
                self.assertEqual(
                    activation.list_active_projects(), [str(project.resolve())]
                )
                with redirect_stdout(StringIO()):
                    self.assertEqual(cli._cli_disable(SimpleNamespace()), 0)
                self.assertEqual(cli._cli_is_active(SimpleNamespace()), 1)

                with patch.dict(os.environ, {"DCNESS_FORCE_ENABLE": "1"}, clear=False):
                    self.assertEqual(cli._cli_is_active(SimpleNamespace()), 0)


if __name__ == "__main__":
    unittest.main()

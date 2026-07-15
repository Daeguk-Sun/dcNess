from __future__ import annotations

import os
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import harness.hooks as hooks
from harness import session_state as state


SID = "hook-contract-session"
RID = "run-deadbeef"


class HookContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = self.root / ".claude" / "harness-state"
        self.pid = 4242

    def start(self, *, lane: str = "lite", agent: str | None = None) -> None:
        state.write_pid_session(self.pid, SID, base_dir=self.base)
        state.transition(
            SID,
            "run_started",
            run_id=RID,
            base_dir=self.base,
            entry_point="impl",
            lane=lane,
        )
        state.write_pid_current_run(self.pid, RID, base_dir=self.base)
        if agent:
            state.transition(
                SID,
                "step_started",
                run_id=RID,
                base_dir=self.base,
                agent=agent,
                mode=None,
            )

    def agent_payload(self, agent: str, *, tool_id: str = "tool-1") -> dict:
        return {
            "sessionId": SID,
            "tool_use_id": tool_id,
            "tool_input": {"subagent_type": agent},
        }

    def test_session_start_accepts_current_id_variants_and_is_idempotent(self) -> None:
        for index, key in enumerate(("session_id", "sessionId", "sessionid"), start=1):
            with self.subTest(key=key):
                pid = self.pid + index
                self.assertEqual(
                    hooks.handle_session_start(
                        stdin_data={key: SID}, cc_pid=pid, base_dir=self.base
                    ),
                    0,
                )
                self.assertEqual(state.read_pid_session(pid, base_dir=self.base), SID)
                self.assertEqual(
                    state.read_live(SID, base_dir=self.base)["active_runs"], {}
                )
        self.assertEqual(
            hooks.handle_session_start(
                stdin_data={"sessionId": "../escape"},
                cc_pid=self.pid,
                base_dir=self.base,
            ),
            0,
        )

    def test_pretool_agent_enforces_strict_step_and_order_contracts(self) -> None:
        cases = (
            ("lite", "build-worker", "build-worker", True, 0),
            ("lite", "impl-validator", "build-worker", False, 1),
            ("standard", "build-worker", "build-worker", False, 1),
        )
        for index, (lane, begun, called, design_pass, expected) in enumerate(cases):
            with self.subTest(lane=lane, begun=begun, called=called):
                base = self.root / f"case-{index}"
                state.write_pid_session(self.pid, SID, base_dir=base)
                state.transition(
                    SID,
                    "run_started",
                    run_id=RID,
                    base_dir=base,
                    entry_point="impl",
                    lane=lane,
                )
                state.write_pid_current_run(self.pid, RID, base_dir=base)
                state.transition(
                    SID,
                    "step_started",
                    run_id=RID,
                    base_dir=base,
                    agent=begun,
                    mode=None,
                )
                if design_pass:
                    (state.run_dir(SID, RID, base_dir=base) / "module-architect.md").write_text(
                        "PASS", encoding="utf-8"
                    )
                rc = hooks.handle_pretooluse_agent(
                    stdin_data=self.agent_payload(called),
                    cc_pid=self.pid,
                    base_dir=base,
                )
                self.assertEqual(rc, expected)

    def test_pretool_agent_records_active_and_pending_state_on_allow(self) -> None:
        self.start(agent="build-worker")
        self.assertEqual(
            hooks.handle_pretooluse_agent(
                stdin_data=self.agent_payload("build-worker"),
                cc_pid=self.pid,
                base_dir=self.base,
            ),
            0,
        )
        live = state.read_live(SID, base_dir=self.base)
        self.assertEqual(live["active_agent"], "build-worker")
        pending = live["active_runs"][RID]["pending_agents"]
        self.assertEqual(pending["tool-1"]["sub_type"], "build-worker")

    def test_posttool_agent_stages_prose_and_clears_transient_state(self) -> None:
        self.start(agent="impl-validator")
        state.transition(
            SID,
            "active_agent_set",
            base_dir=self.base,
            agent="impl-validator",
        )
        state.transition(
            SID,
            "pending_agent_set",
            run_id=RID,
            base_dir=self.base,
            tool_use_id="tool-1",
            sub_type="impl-validator",
            mode=None,
        )
        prose = "## 결론\nPASS\n"
        payload = {
            **self.agent_payload("impl-validator"),
            "tool_name": "Agent",
            "tool_response": [{"type": "text", "text": prose}],
        }
        self.assertEqual(
            hooks.handle_posttooluse_agent(
                stdin_data=payload, cc_pid=self.pid, base_dir=self.base
            ),
            0,
        )
        prose_path = state.run_dir(SID, RID, base_dir=self.base) / "impl-validator.md"
        self.assertEqual(prose_path.read_text(encoding="utf-8"), prose)
        live = state.read_live(SID, base_dir=self.base)
        self.assertNotIn("active_agent", live)
        self.assertNotIn("pending_agents", live["active_runs"][RID])
        self.assertEqual(
            live["active_runs"][RID]["current_step"]["prose_file"], str(prose_path)
        )

    def test_file_hook_preserves_public_allow_block_matrix(self) -> None:
        self.start(agent="build-worker")
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        with mock.patch.dict(
            os.environ, {"DCNESS_INFRA": "", "CLAUDE_PLUGIN_ROOT": ""}, clear=False
        ):
            cases = (
                ("Edit", {"file_path": "src/app.py"}, 0),
                ("Edit", {"file_path": "hooks/file-guard.sh"}, 1),
                ("Write", {"file_path": "README.md"}, 1),
                ("Bash", {"command": "git push origin main"}, 1),
                ("Bash", {"command": "git status --short"}, 0),
            )
            for tool_name, tool_input, expected in cases:
                with self.subTest(tool_name=tool_name, tool_input=tool_input):
                    rc = hooks.handle_pretooluse_file_op(
                        stdin_data={
                            "sessionId": SID,
                            "agent_type": "build-worker",
                            "tool_name": tool_name,
                            "tool_input": tool_input,
                        },
                        cc_pid=self.pid,
                        base_dir=self.base,
                    )
                    self.assertEqual(rc, expected)

    def test_subagent_stop_only_clears_matching_active_agent(self) -> None:
        self.start()
        for active, stopped, remains in (
            ("build-worker", "build-worker", False),
            ("build-worker", "impl-validator", True),
        ):
            with self.subTest(active=active, stopped=stopped):
                state.transition(
                    SID,
                    "active_agent_set",
                    base_dir=self.base,
                    agent=active,
                )
                hooks.handle_subagent_stop(
                    stdin_data={"sessionId": SID, "agent_type": stopped},
                    base_dir=self.base,
                )
                self.assertEqual(
                    "active_agent" in state.read_live(SID, base_dir=self.base), remains
                )

    def test_stop_hook_fail_open_and_recursion_guards_remain(self) -> None:
        self.assertEqual(hooks.handle_stop(stdin_data={"stop_hook_active": True}), 0)
        self.assertEqual(hooks.handle_stop(stdin_data={}), 0)
        self.assertIn("VALIDATION_BLOCKED", hooks._CONTINUE_ENUMS)

    def test_hook_cli_maps_policy_block_and_handler_failure(self) -> None:
        with mock.patch.object(hooks, "handle_pretooluse_agent", return_value=1):
            self.assertEqual(hooks._main(["pretooluse-agent", "--cc-pid", "1"]), 2)
        with mock.patch.object(
            hooks, "handle_pretooluse_agent", side_effect=RuntimeError("boom")
        ):
            self.assertEqual(hooks._main(["pretooluse-agent", "--cc-pid", "1"]), 0)

    def test_invalid_payloads_fail_open_without_policy_output(self) -> None:
        stderr = StringIO()
        with redirect_stderr(stderr):
            for payload in ("not-an-object", {"sessionId": SID}):
                with self.subTest(payload=payload):
                    self.assertEqual(
                        hooks.handle_pretooluse_agent(
                            stdin_data=payload, cc_pid=self.pid, base_dir=self.base
                        ),
                        0,
                    )
        self.assertNotIn("순서 차단", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

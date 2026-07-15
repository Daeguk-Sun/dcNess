"""Contract-focused tests for the public Claude hook adapters.

The exhaustive policy input matrix lives in ``evals/guard_efficacy.py``.  This
module keeps only adapter, lifecycle, persistence, and failure-mode contracts.
"""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from harness import hooks
from harness.hooks import (
    _extract_prose_text,
    handle_posttooluse_agent,
    handle_pretooluse_agent,
    handle_session_start,
    handle_subagent_stop,
)
from harness.session_state import (
    read_live,
    read_pid_session,
    run_dir,
    transition,
)


class SessionStartContractTests(unittest.TestCase):
    def test_session_start_payload_matrix(self) -> None:
        cases = (
            ("session_id", "sid-a", 11111, True),
            ("sessionId", "sid-b", 22222, True),
            ("sessionid", "sid-c", 33333, True),
            ("sessionId", "../bad", 44444, False),
            ("sessionId", "sid-d", 0, False),
        )
        with TemporaryDirectory() as td:
            base = Path(td)
            for key, sid, pid, expected in cases:
                with self.subTest(key=key, sid=sid, pid=pid):
                    self.assertEqual(
                        handle_session_start(
                            stdin_data={key: sid}, cc_pid=pid, base_dir=base
                        ),
                        0,
                    )
                    self.assertEqual(bool(read_pid_session(pid, base_dir=base)), expected)
                    if expected:
                        self.assertEqual(read_live(sid, base_dir=base)["active_runs"], {})

    def test_session_start_is_idempotent(self) -> None:
        with TemporaryDirectory() as td:
            base = Path(td)
            payload = {"session_id": "sid-idempotent"}
            handle_session_start(payload, 12345, base_dir=base)
            transition(
                "sid-idempotent",
                "run_started",
                run_id="run-aaaaaaaa",
                entry_point="impl",
                base_dir=base,
            )
            handle_session_start(payload, 12345, base_dir=base)

            self.assertIn(
                "run-aaaaaaaa",
                read_live("sid-idempotent", base_dir=base)["active_runs"],
            )


class EnforcementAdapterContractTests(unittest.TestCase):
    def test_agent_outside_active_run_is_allowed(self) -> None:
        with TemporaryDirectory() as td:
            base = Path(td)
            handle_session_start({"session_id": "sid-agent"}, 12345, base_dir=base)

            rc = handle_pretooluse_agent(
                {
                    "session_id": "sid-agent",
                    "tool_name": "Agent",
                    "tool_input": {"subagent_type": "dcness:build-worker"},
                },
                12345,
                base_dir=base,
            )

            self.assertEqual(rc, 0)

    def test_main_maps_only_policy_blocks_to_exit_two(self) -> None:
        cases = (
            ("pretooluse-agent", "handle_pretooluse_agent", 1, 2),
            ("pretooluse-file-op", "handle_pretooluse_file_op", 1, 2),
            ("pretooluse-agent", "handle_pretooluse_agent", 0, 0),
            ("session-start", "handle_session_start", 1, 0),
        )
        for command, handler, result, expected in cases:
            with self.subTest(command=command, result=result):
                with patch.object(hooks, handler, return_value=result):
                    self.assertEqual(hooks._main([command, "--cc-pid", "1"]), expected)

        with patch.object(
            hooks,
            "handle_pretooluse_agent",
            side_effect=RuntimeError("hook bug"),
        ):
            self.assertEqual(hooks._main(["pretooluse-agent", "--cc-pid", "1"]), 0)


class PostAgentLifecycleContractTests(unittest.TestCase):
    sid = "sid-post-agent"
    rid = "run-bbbbbbbb"

    def _base(self, root: Path, *, begin_step: bool = True) -> None:
        transition(self.sid, "session_initialized", base_dir=root)
        transition(
            self.sid,
            "run_started",
            run_id=self.rid,
            entry_point="impl",
            base_dir=root,
        )
        if begin_step:
            transition(
                self.sid,
                "step_started",
                run_id=self.rid,
                agent="impl-validator",
                mode=None,
                base_dir=root,
            )
        transition(
            self.sid,
            "active_agent_set",
            agent="impl-validator",
            base_dir=root,
        )
        transition(
            self.sid,
            "pending_agent_set",
            run_id=self.rid,
            tool_use_id="tool-1",
            sub_type="impl-validator",
            mode=None,
            base_dir=root,
        )

    def test_post_agent_stages_prose_and_clears_runtime_identity(self) -> None:
        with TemporaryDirectory() as td:
            base = Path(td)
            self._base(base)
            payload = {
                "session_id": self.sid,
                "tool_use_id": "tool-1",
                "tool_name": "Agent",
                "tool_input": {"subagent_type": "impl-validator"},
                "tool_response": [{"type": "text", "text": "검증 완료\n\nPASS\n"}],
            }

            self.assertEqual(handle_posttooluse_agent(payload, base_dir=base), 0)

            live = read_live(self.sid, base_dir=base)
            slot = live["active_runs"][self.rid]
            self.assertNotIn("active_agent", live)
            self.assertNotIn("pending_agents", slot)
            prose_file = Path(slot["current_step"]["prose_file"])
            self.assertEqual(prose_file.parent, run_dir(self.sid, self.rid, base_dir=base))
            self.assertIn("PASS", prose_file.read_text(encoding="utf-8"))

    def test_post_agent_preserves_staging_diagnostic_stdout(self) -> None:
        with TemporaryDirectory() as td:
            base = Path(td)
            self._base(base, begin_step=False)
            output = StringIO()
            with redirect_stdout(output):
                rc = handle_posttooluse_agent(
                    {
                        "session_id": self.sid,
                        "tool_use_id": "tool-1",
                        "tool_response": {"text": "PASS"},
                    },
                    base_dir=base,
                )

            self.assertEqual(rc, 0)
            response = json.loads(output.getvalue())
            self.assertIn(
                "current_step 부재",
                response["hookSpecificOutput"]["additionalContext"],
            )

    def test_subagent_stop_clears_only_matching_agent(self) -> None:
        with TemporaryDirectory() as td:
            base = Path(td)
            transition(self.sid, "session_initialized", base_dir=base)
            transition(
                self.sid,
                "active_agent_set",
                agent="dcness:build-worker",
                base_dir=base,
            )

            self.assertEqual(
                handle_subagent_stop(
                    {"session_id": self.sid, "agent_type": "impl-validator"},
                    base_dir=base,
                ),
                0,
            )
            self.assertIn("active_agent", read_live(self.sid, base_dir=base))
            self.assertEqual(
                handle_subagent_stop(
                    {"session_id": self.sid, "agent_type": "dcness:build-worker"},
                    base_dir=base,
                ),
                0,
            )
            self.assertNotIn("active_agent", read_live(self.sid, base_dir=base))


class PayloadExtractionContractTests(unittest.TestCase):
    def test_prose_shapes_are_table_driven(self) -> None:
        cases = (
            ("plain", "plain"),
            ({"text": "direct"}, "direct"),
            ([{"type": "text", "text": "block"}], "block"),
            ({"content": [{"value": "nested"}]}, "nested"),
            ({"type": "tool_result"}, ""),
        )
        for payload, expected in cases:
            with self.subTest(payload=payload):
                self.assertEqual(_extract_prose_text(payload), expected)


if __name__ == "__main__":
    unittest.main()

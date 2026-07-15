"""Contract-focused tests for the public Claude hook adapters.

The exhaustive policy input matrix lives in ``evals/guard_efficacy.py``.  This
module keeps only adapter, lifecycle, persistence, and failure-mode contracts.
"""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
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
    handle_stop,
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


class StrictConveyorContractTests(unittest.TestCase):
    sid = "sid-strict-contract"
    rid = "run-cccccccc"

    def test_all_block_reasons_are_preserved_as_a_table(self) -> None:
        with TemporaryDirectory() as td:
            base = Path(td)
            transition(
                self.sid,
                "run_started",
                run_id=self.rid,
                entry_point="impl",
                lane="lite",
                base_dir=base,
            )
            prose_path = run_dir(self.sid, self.rid, base_dir=base) / "module-architect.md"
            prose_path.write_text("PASS", encoding="utf-8")
            transition(
                self.sid,
                "step_completed",
                run_id=self.rid,
                agent="module-architect",
                mode=None,
                enum="PROSE_LOGGED",
                prose="PASS",
                prose_path=prose_path,
                base_dir=base,
            )
            base_slot = {"entry_point": "impl"}
            cases = (
                (base_slot, "module-architect", "begin-step 누락"),
                (
                    {**base_slot, "current_step": {"agent": ""}},
                    "module-architect",
                    "current_step.agent 공백",
                ),
                (
                    {**base_slot, "current_step": {"agent": "system-architect"}},
                    "module-architect",
                    "begin-step/Agent 불일치",
                ),
                (
                    {
                        **base_slot,
                        "current_step": {
                            "agent": "module-architect",
                            "prose_file": str(prose_path),
                        },
                    },
                    "module-architect",
                    "이미 staged",
                ),
                (
                    {**base_slot, "current_step": {"agent": "module-architect"}},
                    "module-architect",
                    "steps_count_at_begin 부재",
                ),
                (
                    {
                        **base_slot,
                        "current_step": {
                            "agent": "module-architect",
                            "steps_count_at_begin": 0,
                        },
                    },
                    "module-architect",
                    "이미 ledger.jsonl 에 기록",
                ),
            )
            for slot, requested, fragment in cases:
                with self.subTest(fragment=fragment):
                    message = hooks._strict_conveyor_gate_message(
                        sid=self.sid,
                        rid=self.rid,
                        base_dir=base,
                        slot=slot,
                        subagent=requested,
                        mode=None,
                    )
                    self.assertIsNotNone(message)
                    self.assertIn(fragment, message)

    def test_matching_design_step_and_completed_run_are_not_overblocked(self) -> None:
        cases = (
            (
                {
                    "entry_point": "design",
                    "current_step": {
                        "agent": "module-architect",
                        "mode": "epic-batch",
                        "steps_count_at_begin": 0,
                    },
                },
                "module-architect",
                None,
            ),
            ({"entry_point": "impl", "completed_at": "done"}, "build-worker", None),
        )
        with TemporaryDirectory() as td:
            base = Path(td)
            for slot, requested, mode in cases:
                with self.subTest(slot=slot):
                    self.assertIsNone(
                        hooks._strict_conveyor_gate_message(
                            sid=self.sid,
                            rid=self.rid,
                            base_dir=base,
                            slot=slot,
                            subagent=requested,
                            mode=mode,
                        )
                    )


class StopHookContractTests(unittest.TestCase):
    sid = "sid-stop-contract"

    def _complete_step(self, base: Path, rid: str, agent: str) -> None:
        transition(
            self.sid,
            "run_started",
            run_id=rid,
            entry_point="impl",
            lane="lite",
            base_dir=base,
        )
        prose = "작업 완료\n\nPASS\n"
        prose_path = run_dir(self.sid, rid, base_dir=base) / f"{agent}.md"
        prose_path.write_text(prose, encoding="utf-8")
        transition(
            self.sid,
            "step_completed",
            run_id=rid,
            agent=agent,
            mode=None,
            enum="PROSE_LOGGED",
            prose=prose,
            prose_path=prose_path,
            base_dir=base,
        )

    def test_auto_end_recovery_and_in_progress_guards(self) -> None:
        cases = ("completed-step", "finalize-only", "already-finished", "next-step-active")
        expected_calls = (1, 1, 0, 0)
        for index, (case, expected) in enumerate(zip(cases, expected_calls), start=1):
            with self.subTest(case=case), TemporaryDirectory() as td:
                base = Path(td)
                rid = f"run-0000000{index}"
                self._complete_step(base, rid, "impl-validator")
                if case in {"finalize-only", "already-finished"}:
                    transition(
                        self.sid,
                        "run_finalized",
                        run_id=rid,
                        base_dir=base,
                    )
                if case == "already-finished":
                    transition(
                        self.sid,
                        "run_completed",
                        run_id=rid,
                        base_dir=base,
                    )
                if case == "next-step-active":
                    transition(
                        self.sid,
                        "step_started",
                        run_id=rid,
                        agent="impl-validator",
                        mode=None,
                        base_dir=base,
                    )
                env = {"DCNESS_SESSION_ID": self.sid, "DCNESS_RUN_ID": rid}
                with patch.dict(os.environ, env, clear=False), patch(
                    "harness.session_state_cli._cli_end_run", return_value=0
                ) as end_run:
                    self.assertEqual(handle_stop({}, base_dir=base), 0)
                self.assertEqual(end_run.call_count, expected)

        with patch("sys.stdin.read", return_value="{broken"):
            self.assertEqual(handle_stop(None), 0)
        self.assertEqual(handle_stop("invalid"), 0)  # type: ignore[arg-type]
        self.assertEqual(handle_stop({"stop_hook_active": True}), 0)

    def test_continuation_json_persists_and_honors_block_count_cap(self) -> None:
        with TemporaryDirectory() as td:
            base = Path(td)
            rid = "run-11111111"
            self._complete_step(base, rid, "build-worker")

            for attempt in range(3):
                slot = read_live(self.sid, base_dir=base)["active_runs"][rid]
                output = StringIO()
                with redirect_stdout(output):
                    emitted = hooks._maybe_emit_continuation_signal(
                        sid=self.sid,
                        rid=rid,
                        slot=slot,
                        active={rid: slot},
                        last_agent="build-worker",
                        last_mode=None,
                        base_dir=base,
                    )
                self.assertEqual(emitted, attempt < hooks._STOP_BLOCK_COUNT_MAX)
                if attempt < hooks._STOP_BLOCK_COUNT_MAX:
                    self.assertEqual(json.loads(output.getvalue())["decision"], "block")
                else:
                    self.assertEqual(output.getvalue(), "")

            persisted = read_live(self.sid, base_dir=base)["active_runs"][rid]
            self.assertEqual(
                persisted["stop_block_count"]["build-worker:"],
                hooks._STOP_BLOCK_COUNT_MAX,
            )

            terminal_rid = "run-22222222"
            self._complete_step(base, terminal_rid, "impl-validator")
            terminal = read_live(self.sid, base_dir=base)["active_runs"][terminal_rid]
            output = StringIO()
            with redirect_stdout(output):
                self.assertFalse(
                    hooks._maybe_emit_continuation_signal(
                        sid=self.sid,
                        rid=terminal_rid,
                        slot=terminal,
                        active={terminal_rid: terminal},
                        last_agent="impl-validator",
                        last_mode=None,
                        base_dir=base,
                    )
                )
            self.assertEqual(output.getvalue(), "")


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

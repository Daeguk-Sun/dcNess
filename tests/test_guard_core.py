"""Public contract for the shared guard request and decision boundary."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from harness.guard_core import GuardContext, GuardDecision, HookRequest


ROOT = Path(__file__).resolve().parents[1]


class HookRequestContractTests(unittest.TestCase):
    def test_hook_payload_is_normalized_once(self) -> None:
        request = HookRequest.from_payload(
            {
                "sessionId": "session-1",
                "tool_name": "Edit",
                "tool_use_id": "tool-1",
                "agent_type": "dcness:build-worker",
                "tool_input": {"file_path": "src/app.py"},
            },
            guard="file-guard",
        )

        self.assertEqual(request.context.session_id, "session-1")
        self.assertEqual(request.context.agent, "build-worker")
        self.assertEqual(request.context.tool, "Edit")
        self.assertEqual(request.tool_use_id, "tool-1")
        self.assertEqual(request.tool_input, {"file_path": "src/app.py"})

    def test_requested_agent_is_normalized_from_tool_input(self) -> None:
        request = HookRequest.from_payload(
            {
                "session_id": "session-2",
                "tool_name": "Agent",
                "tool_input": {"subagent_type": "dcness:impl-validator"},
            },
            guard="catastrophic-gate",
            agent_source="requested",
        )

        self.assertEqual(request.context.agent, "impl-validator")

    def test_invalid_payload_shape_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "payload must be an object"):
            HookRequest.from_payload([], guard="file-guard")  # type: ignore[arg-type]

        with self.assertRaisesRegex(ValueError, "tool_input must be an object"):
            HookRequest.from_payload(
                {"session_id": "session-3", "tool_input": []},
                guard="file-guard",
            )


class GuardDecisionContractTests(unittest.TestCase):
    def test_allow_and_block_share_one_adapter_contract(self) -> None:
        context = GuardContext(guard="file-guard", category="write_boundary")

        allow = GuardDecision.allow(context)
        block = GuardDecision.block(context, "outside write", evidence=("../x",))

        self.assertTrue(allow.allowed)
        self.assertEqual(allow.exit_code, 0)
        self.assertIsNone(allow.legacy_reason)
        self.assertFalse(block.allowed)
        self.assertEqual(block.exit_code, 1)
        self.assertEqual(block.legacy_reason, "outside write")
        self.assertEqual(block.evidence, ("../x",))

    def test_context_category_change_preserves_request_identity(self) -> None:
        context = GuardContext(
            guard="file-guard",
            session_id="session-4",
            run_id="run-4",
            agent="build-worker",
            tool="Bash",
        )

        changed = context.with_category("bash_mutation")

        self.assertEqual(changed.category, "bash_mutation")
        self.assertEqual(changed.session_id, context.session_id)
        self.assertEqual(changed.run_id, context.run_id)
        self.assertEqual(changed.agent, context.agent)
        self.assertEqual(changed.tool, context.tool)


class RuntimeEvidenceBoundaryTests(unittest.TestCase):
    def test_release_runtime_excludes_post_run_analysis(self) -> None:
        contract = json.loads(
            (ROOT / "scripts/release_artifact.json").read_text(encoding="utf-8")
        )
        included = set(contract["include_paths"])
        product_python = set(contract["product_python"])
        excluded = {
            "harness/agent_trace.py",
            "harness/benchmark_aggregate.py",
            "harness/loop_insights.py",
            "harness/loop_lessons.py",
            "harness/sub_eval.py",
            "scripts/loop_diagnose.py",
            "scripts/measure_main_turns.py",
        }

        self.assertFalse(excluded & included)
        self.assertFalse(excluded & product_python)
        self.assertNotIn("harness/efficiency", included)
        self.assertIn("harness/efficiency/analyze_sessions.py", included)

    def test_public_hooks_do_not_capture_per_tool_trace(self) -> None:
        manifest = json.loads((ROOT / "hooks/hooks.json").read_text(encoding="utf-8"))
        post_hooks = manifest["hooks"]["PostToolUse"]

        self.assertEqual([entry.get("matcher") for entry in post_hooks], ["Agent"])
        self.assertFalse((ROOT / "hooks/post-file-op-trace.sh").exists())


if __name__ == "__main__":
    unittest.main()

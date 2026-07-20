from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.measure_main_turns import build_paired_screening, parse_session


class MeasureMainTurnsTests(unittest.TestCase):
    def _trace(self, path: Path, *, tool_calls: int, input_tokens: int) -> None:
        content = [
            {
                "type": "tool_use",
                "id": f"tool-{index}",
                "name": "Agent" if index == tool_calls - 1 else "Bash",
                "input": {"subagent_type": "impl-validator"},
            }
            for index in range(tool_calls)
        ]
        rows = [
            {
                "type": "assistant",
                "timestamp": "2026-07-20T00:00:00Z",
                "request_id": "main-request-1",
                "parent_tool_use_id": None,
                "message": {
                    "role": "assistant",
                    "model": "claude-sonnet-4-6",
                    "usage": {
                        "input_tokens": input_tokens,
                        "output_tokens": 25,
                    },
                    "content": content,
                },
                "effort": {"level": "high"},
                "provider": "claude-main",
            },
            {
                "type": "assistant",
                "timestamp": "2026-07-20T00:00:01Z",
                "request_id": "main-request-1",
                "parent_tool_use_id": None,
                "message": {
                    "role": "assistant",
                    "usage": {
                        "input_tokens": input_tokens,
                        "output_tokens": 25,
                    },
                    "content": [{"type": "thinking", "thinking": "fragment"}],
                },
            },
            {
                "type": "assistant",
                "timestamp": "2026-07-20T00:00:01Z",
                "request_id": "subagent-request",
                "parent_tool_use_id": "tool-agent",
                "message": {
                    "role": "assistant",
                    "usage": {"input_tokens": 999, "output_tokens": 999},
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "subagent-tool",
                            "name": "Read",
                            "input": {},
                        }
                    ],
                },
            },
            {
                "type": "assistant",
                "timestamp": "2026-07-20T00:00:02Z",
                "request_id": "main-request-2",
                "parent_tool_use_id": None,
                "message": {
                    "role": "assistant",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                    "content": [{"type": "text", "text": "done"}],
                },
            },
        ]
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    def test_parse_session_collects_requests_tools_time_tokens_and_runtime(self) -> None:
        with TemporaryDirectory() as td:
            trace = Path(td) / "baseline.jsonl"
            self._trace(trace, tool_calls=3, input_tokens=100)

            result = parse_session(trace)

        self.assertEqual(result["main_assistant_requests"], 2)
        self.assertEqual(result["tool_calls"], 3)
        self.assertEqual(result["wall_clock_seconds"], 2.0)
        self.assertEqual(result["input_tokens"], 110)
        self.assertEqual(result["output_tokens"], 30)
        self.assertEqual(result["models"], ["claude-sonnet-4-6"])
        self.assertEqual(result["effort_levels"], ["high"])
        self.assertEqual(result["providers"], ["claude-main"])

    def test_paired_screening_requires_same_fixture_and_quality_axes(self) -> None:
        with TemporaryDirectory() as td:
            base = Path(td)
            baseline_path = base / "baseline.jsonl"
            variant_path = base / "variant.jsonl"
            self._trace(baseline_path, tool_calls=5, input_tokens=120)
            self._trace(variant_path, tool_calls=3, input_tokens=90)
            outcomes = {
                "fixture": {"id": "one-task", "sha256": "a" * 64},
                "trials": {
                    "baseline": {
                        "runtime": {
                            "model": "claude-sonnet-5",
                            "effort": "medium",
                            "provider": "claude-main",
                        },
                        "product_ac": {"passed": 2, "total": 2},
                        "must_fix_count": 0,
                        "regression_count": 0,
                        "human_intervention_count": 0,
                    },
                    "variant": {
                        "runtime": {
                            "model": "claude-sonnet-5",
                            "effort": "medium",
                            "provider": "claude-main",
                        },
                        "product_ac": {"passed": 2, "total": 2},
                        "must_fix_count": 0,
                        "regression_count": 0,
                        "human_intervention_count": 0,
                    },
                },
            }

            paired = build_paired_screening(
                parse_session(baseline_path),
                parse_session(variant_path),
                outcomes,
            )

        self.assertEqual(paired["fixture"]["id"], "one-task")
        self.assertEqual([row["variant"] for row in paired["trials"]], ["baseline", "variant"])
        self.assertEqual(paired["trials"][0]["product_ac"], {"passed": 2, "total": 2})
        self.assertEqual(paired["delta"]["main_assistant_requests"], 0)
        self.assertEqual(paired["delta"]["tool_calls"], -2)
        self.assertFalse(paired["quality_regressed"])

        broken = json.loads(json.dumps(outcomes))
        del broken["trials"]["variant"]["human_intervention_count"]
        with self.assertRaisesRegex(ValueError, "human_intervention_count"):
            build_paired_screening({}, {}, broken)


if __name__ == "__main__":
    unittest.main()

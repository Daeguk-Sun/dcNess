from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.measure_main_turns import (
    build_paired_screening,
    build_repeated_screening,
    parse_session,
)


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

    def _action_trace(
        self,
        path: Path,
        *,
        edit_second: int,
        fresh: bool,
        input_tokens: int,
    ) -> None:
        parent = "agent-launch" if fresh else None
        rows = [
            {
                "type": "user",
                "timestamp": "2026-07-20T00:00:00Z",
                "parent_tool_use_id": None,
                "message": {"role": "user", "content": "implement fixture"},
            },
            {
                "type": "assistant",
                "timestamp": "2026-07-20T00:00:01Z",
                "request_id": "main-read",
                "parent_tool_use_id": None,
                "message": {
                    "role": "assistant",
                    "usage": {
                        "input_tokens": input_tokens,
                        "output_tokens": 10,
                    },
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "read",
                            "name": "Read",
                            "input": {"file_path": "src/fixture.py"},
                        }
                    ],
                },
            },
            {
                "type": "assistant",
                "timestamp": f"2026-07-20T00:00:{edit_second - 1:02d}Z",
                "request_id": "executor-edit",
                "parent_tool_use_id": parent,
                "message": {
                    "role": "assistant",
                    "usage": {
                        "input_tokens": input_tokens // 2,
                        "output_tokens": 7,
                    },
                    "content": [
                        {"type": "thinking", "thinking": "prepare edit"},
                    ],
                },
            },
            {
                "type": "assistant",
                "timestamp": f"2026-07-20T00:00:{edit_second:02d}Z",
                "request_id": "executor-edit",
                "parent_tool_use_id": parent,
                "message": {
                    "role": "assistant",
                    "usage": {
                        "input_tokens": input_tokens // 2,
                        "output_tokens": 7,
                    },
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "edit",
                            "name": "Edit",
                            "input": {"file_path": "src/fixture.py"},
                        }
                    ],
                },
            },
        ]
        path.write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n",
            encoding="utf-8",
        )

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
        self.assertEqual(result["all_total_input_tokens"], 1109)
        self.assertEqual(result["all_output_tokens"], 1029)

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

    def test_parse_session_measures_first_edit_across_fresh_executor(self) -> None:
        with TemporaryDirectory() as td:
            trace = Path(td) / "fresh.jsonl"
            self._action_trace(
                trace,
                edit_second=7,
                fresh=True,
                input_tokens=100,
            )

            result = parse_session(trace)

        self.assertEqual(result["time_to_first_edit_seconds"], 7.0)
        self.assertEqual(
            result["blocking_assistant_requests_before_first_edit"],
            1,
        )
        self.assertEqual(result["first_edit_evidence"]["executor"], "fresh")
        self.assertEqual(
            result["first_edit_evidence"]["path"],
            "src/fixture.py",
        )
        self.assertEqual(result["all_total_input_tokens"], 150)
        self.assertEqual(result["all_output_tokens"], 17)

    def test_process_start_falls_back_before_fresh_edit_when_root_duration_is_short(self) -> None:
        with TemporaryDirectory() as td:
            trace = Path(td) / "fresh-no-user.jsonl"
            rows = [
                {
                    "type": "assistant",
                    "timestamp": "2026-07-20T00:00:01Z",
                    "request_id": "launch",
                    "parent_tool_use_id": None,
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "thinking", "thinking": "launch"}],
                    },
                },
                {
                    "type": "assistant",
                    "timestamp": "2026-07-20T00:00:09Z",
                    "request_id": "fresh-edit",
                    "parent_tool_use_id": "agent",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Write",
                                "input": {"file_path": "fixture.py"},
                            }
                        ],
                    },
                },
                {
                    "type": "assistant",
                    "timestamp": "2026-07-20T00:00:12Z",
                    "request_id": "done",
                    "parent_tool_use_id": None,
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "done"}],
                    },
                },
                {
                    "type": "result",
                    "duration_ms": 2_000,
                    "usage": {},
                },
            ]
            trace.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )

            result = parse_session(trace)

        self.assertEqual(result["time_to_first_edit_seconds"], 8.0)
        self.assertEqual(result["start_evidence"]["kind"], "earliest_timed_event")

    def test_repeated_screening_compares_same_runtime_and_keeps_main_default(self) -> None:
        with TemporaryDirectory() as td:
            base = Path(td)
            baselines = []
            variants = []
            for index, seconds in enumerate((10, 12, 11), start=1):
                path = base / f"baseline-{index}.jsonl"
                self._action_trace(
                    path,
                    edit_second=seconds,
                    fresh=False,
                    input_tokens=120,
                )
                baselines.append(parse_session(path))
            for index, seconds in enumerate((5, 6, 4), start=1):
                path = base / f"variant-{index}.jsonl"
                self._action_trace(
                    path,
                    edit_second=seconds,
                    fresh=True,
                    input_tokens=80,
                )
                variants.append(parse_session(path))

            outcome = {
                "runtime": {
                    "model": "claude-sonnet-5",
                    "effort": "medium",
                    "provider": "claude-main",
                },
                "product_ac": {"passed": 2, "total": 2},
                "must_fix_count": 0,
                "regression_count": 0,
                "human_intervention_count": 0,
            }
            outcomes = {
                "fixture": {"id": "decision-heavy", "sha256": "b" * 64},
                "trials": {
                    "baseline": [
                        json.loads(json.dumps(outcome)) for _ in range(3)
                    ],
                    "variant": [
                        json.loads(json.dumps(outcome)) for _ in range(3)
                    ],
                },
            }

            screening = build_repeated_screening(
                baselines,
                variants,
                outcomes,
            )

        self.assertEqual(screening["trial_count_per_variant"], 3)
        self.assertEqual(
            screening["summary"]["baseline"]["time_to_first_edit_seconds"][
                "median"
            ],
            11.0,
        )
        self.assertEqual(
            screening["summary"]["variant"]["time_to_first_edit_seconds"][
                "median"
            ],
            5.0,
        )
        self.assertEqual(screening["adoption"]["default"], "main-direct")
        self.assertTrue(
            screening["adoption"]["conditional_fresh_executor"]
        )

        broken = json.loads(json.dumps(outcomes))
        broken["trials"]["variant"][1]["runtime"]["effort"] = "high"
        with self.assertRaisesRegex(ValueError, "same model/effort/provider"):
            build_repeated_screening(baselines, variants, broken)


if __name__ == "__main__":
    unittest.main()

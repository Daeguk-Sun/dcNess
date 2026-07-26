"""Contracts for issue #1201 impl-validator delta re-review."""
from __future__ import annotations

import json
import statistics
from contextlib import redirect_stdout
from io import StringIO
import sys
from tempfile import TemporaryDirectory
import unittest
from pathlib import Path
from unittest.mock import patch

from evals import replay_impl_validator_delta as replay


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class ImplValidatorDeltaReviewContractTests(unittest.TestCase):
    def test_impl_loop_reentry_supplies_receipt_identity_and_candidate_delta(
        self,
    ) -> None:
        finish = read("skills/impl-loop/impl-loop-finish.md")

        for needle in (
            "첫 라운드",
            "전체 holistic",
            "`prose_file` + `sha256`",
            "직전 candidate HEAD/tree/workspace root",
            "현재 candidate HEAD/tree/workspace root",
            "직전 candidate HEAD..현재 candidate HEAD",
            "재리뷰 한도는 현행 3회",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, finish)

    def test_claude_and_codex_reviewers_define_bounded_delta_mode(self) -> None:
        prompts = (
            read("docs/plugin/agents/impl-validator/impl-validator-agent.md"),
            read("codex/skills/dcness-impl-validator/SKILL.md"),
        )

        for prompt in prompts:
            with self.subTest(prompt=prompt[:40]):
                for needle in (
                    "재리뷰 delta mode",
                    "`prose_file` + `sha256`",
                    "직전 candidate HEAD/tree/workspace root",
                    "현재 candidate HEAD/tree/workspace root",
                    "직전 candidate HEAD..현재 candidate HEAD",
                    "전체 재독으로 승격",
                    "판정 범위와 그 근거",
                    "안 본 영역을 새로 통과 처리",
                ):
                    self.assertIn(needle, prompt)

    def test_two_round_replay_records_material_speedup_without_quality_loss(
        self,
    ) -> None:
        evidence = json.loads(
            read("evals/impl-validator-delta-replay-metadata.json")
        )
        rounds = evidence["rounds"]

        self.assertGreaterEqual(len(rounds), 2)
        self.assertEqual(rounds[0]["review_scope"], "full")
        baseline = rounds[0]["elapsed_seconds"]
        reductions = []
        for replay_round in rounds[1:]:
            with self.subTest(round=replay_round["round"]):
                self.assertEqual(replay_round["review_scope"], "delta")
                self.assertTrue(replay_round["quality_contract_preserved"])
                self.assertLess(replay_round["elapsed_seconds"], baseline)
                reductions.append(
                    100
                    * (baseline - replay_round["elapsed_seconds"])
                    / baseline
                )

        self.assertGreaterEqual(statistics.median(reductions), 15)
        self.assertGreaterEqual(
            baseline
            - statistics.median(
                replay_round["elapsed_seconds"]
                for replay_round in rounds[1:]
            ),
            30,
        )
        self.assertIn("replay_command", evidence)
        self.assertTrue(evidence["limitations"])

    def test_live_replay_hides_future_delta_until_round_one_finishes(self) -> None:
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "replay"
            calls = 0

            def fake_run(
                prompt: str, model: str, case_dir: Path
            ) -> tuple[str, float]:
                nonlocal calls
                calls += 1
                self.assertEqual(model, "sonnet")
                candidate_files = list(
                    case_dir.joinpath("candidate-round1").glob("*.md")
                )
                self.assertEqual(len(candidate_files), 110)
                if calls == 1:
                    self.assertFalse(case_dir.joinpath("candidate-delta").exists())
                    return "three findings\n\nFAIL", 200.0
                self.assertEqual(
                    len(list(case_dir.joinpath("candidate-delta").glob("*.md"))),
                    4,
                )
                return "resolved and one new finding\n\nFAIL", 100.0

            argv = [
                "replay_impl_validator_delta.py",
                "--output-dir",
                str(output),
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(replay.shutil, "which", return_value="/bin/claude"),
                patch.object(replay, "_run_claude", side_effect=fake_run),
                patch.object(replay, "_judge", return_value=(True, "RESULT: PASS")),
                redirect_stdout(StringIO()),
            ):
                self.assertEqual(replay.main(), 0)

            self.assertEqual(calls, 2)
            metadata = json.loads(
                output.joinpath("metadata.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadata["fixture"]["first_candidate_files"], 110)
            self.assertEqual(metadata["fixture"]["first_candidate_lines"], 5500)
            self.assertEqual(metadata["fixture"]["delta_files"], 4)
            self.assertEqual(metadata["reduction_seconds"], 100.0)
            self.assertEqual(metadata["reduction_percent"], 50.0)

    def test_live_replay_rejects_fixture_too_small_for_seeded_findings(
        self,
    ) -> None:
        argv = [
            "replay_impl_validator_delta.py",
            "--modules",
            "102",
            "--output-dir",
            "/tmp/not-created-by-replay-test",
        ]
        with (
            patch.object(sys, "argv", argv),
            patch.object(replay.shutil, "which", return_value="/bin/claude"),
            redirect_stdout(StringIO()),
            self.assertRaises(SystemExit),
        ):
            replay.main()


if __name__ == "__main__":
    unittest.main()

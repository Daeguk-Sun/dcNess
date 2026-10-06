"""Judgment inputs a journey run leaves for the agent that decides what to re-run."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess  # nosec B404
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harness import epic_outcome
from harness.outcome_scorecard import build_scorecard
from harness.product_journey import (
    JourneyConfigError,
    journey_history,
    main,
    read_receipts,
    record_skip,
    run_from_config,
)


CONFIG_PATH = Path("app/.maestro/dcness-journey.json")
EVIDENCE = Path(".dcness-work/product-journey")


def _command(code: str) -> dict[str, object]:
    return {"argv": [sys.executable, "-c", code], "timeout_sec": 10}


def _scenario(scenario_id: str, target_ac: list[str], exit_code: int = 0) -> dict[str, object]:
    return {
        "scenario_id": scenario_id,
        "description": f"{scenario_id} 화면 흐름",
        **_command(f"raise SystemExit({exit_code})"),
        "target_ac": target_ac,
    }


def _config(*, exits: tuple[int, int] = (0, 0), epic: bool = False) -> dict[str, object]:
    payload: dict[str, object] = {
        "version": 1,
        "journey_id": "fixture-judgment-journey",
        "target_ac": ["AC-1", "AC-2"],
        "boundary": "cli",
        "assertion": {
            "description": "각 시나리오 명령이 담당 AC 동작을 판정한다",
            "source": "journey_exit",
        },
        "human_intervention_count": 0,
        "commands": {
            "start": {**_command("print('started')"), "mode": "command"},
            "health": _command("print('healthy')"),
            "cleanup": _command("print('cleaned')"),
        },
        "scenarios": [
            _scenario("scenario-one", ["AC-1"], exits[0]),
            _scenario("scenario-two", ["AC-2"], exits[1]),
        ],
        "evidence_dir": EVIDENCE.as_posix(),
    }
    if epic:
        payload["epic_scope"] = {
            "epic": "epic-01-messaging",
            "representative_story": "story-04-compose-and-send",
            "selection_rationale": "작성과 발신이 한 흐름으로 통과한다",
            "execution_environment": "fixture-cli",
        }
    return payload


def _write_config(root: Path, payload: dict[str, object]) -> Path:
    path = root / CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _git(root: Path, *argv: str) -> str:
    return subprocess.run(  # nosec B603 B607
        ["git", *argv], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()


def _git_project(root: Path) -> str:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "fixture@example.com")
    _git(root, "config", "user.name", "fixture")
    (root / ".gitignore").write_text(".dcness-work/\n", encoding="utf-8")
    _write_config(root, _config())
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    return _git(root, "rev-parse", "HEAD")


def _run(root: Path, run_id: str, **kwargs: object):  # type: ignore[no-untyped-def]
    return run_from_config(root, config_path=root / CONFIG_PATH, run_id=run_id, **kwargs)  # type: ignore[arg-type]


class CodeRevisionTests(unittest.TestCase):
    def test_receipt_records_the_commit_the_journey_ran_against(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            head = _git_project(root)
            clean = _run(root, "clean-run").receipt
            (root / "README.md").write_text("uncommitted", encoding="utf-8")
            dirty = _run(root, "dirty-run").receipt
            valid = read_receipts(root)

        self.assertEqual(clean["code_revision"], head)
        self.assertIs(clean["uncommitted_changes"], False)
        self.assertEqual(dirty["code_revision"], head)
        self.assertIs(dirty["uncommitted_changes"], True)
        self.assertEqual(len(valid), 2)

    def test_project_without_git_records_unknown_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_config(root, _config())
            receipt = _run(root, "no-git-run").receipt
            valid = read_receipts(root)

        self.assertEqual(receipt["code_revision"], "unknown")
        self.assertIsNone(receipt["uncommitted_changes"])
        self.assertEqual(len(valid), 1)

    def test_receipt_written_before_the_field_existed_is_still_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_config(root, _config())
            path = _run(root, "old-run").receipt_path
            receipt = json.loads(path.read_text(encoding="utf-8"))
            del receipt["code_revision"]
            del receipt["uncommitted_changes"]
            path.write_text(json.dumps(receipt), encoding="utf-8")
            valid = read_receipts(root)

        self.assertEqual([item["run_id"] for item in valid], ["old-run"])
        self.assertNotIn("code_revision", valid[0])

    def test_receipt_with_a_malformed_revision_is_discarded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_config(root, _config())
            path = _run(root, "bad-run").receipt_path
            receipt = json.loads(path.read_text(encoding="utf-8"))
            receipt["code_revision"] = "not a revision"
            path.write_text(json.dumps(receipt), encoding="utf-8")
            valid = read_receipts(root)

        self.assertEqual(valid, [])


class JourneyHistoryTests(unittest.TestCase):
    def test_history_accumulates_runs_and_duration_of_one_journey(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_config(root, _config(exits=(0, 3)))
            first = _run(root, "run-1", measured_at="2026-07-10T00:00:00Z").receipt
            _run(root, "run-2", measured_at="2026-07-10T00:01:00Z")
            _run(
                root,
                "run-3",
                measured_at="2026-07-10T00:02:00Z",
                scenarios=["scenario-two"],
            )
            other = _config()
            other["journey_id"] = "another-journey"
            _write_config(root, other)
            _run(root, "run-other", measured_at="2026-07-10T00:03:00Z")
            history = journey_history(root, "fixture-judgment-journey")

        first_ms = sum(
            item["duration_ms"]
            for item in [*first["commands"].values(), *first["scenarios"]]
        )
        self.assertEqual(history["runs"], 3)
        self.assertEqual(history["failed"], 3)
        self.assertEqual(history["partial"], 1)
        self.assertGreaterEqual(history["duration_ms"], first_ms)
        self.assertEqual(history["consecutive_failures"], 3)

    def test_same_failure_signal_is_counted_across_full_and_partial_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_config(root, _config(exits=(0, 3)))
            _run(root, "run-1", measured_at="2026-07-10T00:00:00Z")
            _run(
                root,
                "run-2",
                measured_at="2026-07-10T00:01:00Z",
                scenarios=["scenario-two"],
            )
            same = journey_history(root, "fixture-judgment-journey")
            _write_config(root, _config(exits=(4, 0)))
            _run(root, "run-3", measured_at="2026-07-10T00:02:00Z")
            different = journey_history(root, "fixture-judgment-journey")
            _write_config(root, _config())
            _run(root, "run-4", measured_at="2026-07-10T00:03:00Z")
            passed = journey_history(root, "fixture-judgment-journey")

        self.assertEqual(same["same_signal_streak"], 2)
        self.assertEqual(same["previous_outcome"], "FAIL")
        self.assertEqual(different["same_signal_streak"], 1)
        self.assertEqual(different["previous_outcome"], "FAIL")
        self.assertEqual(different["consecutive_failures"], 3)
        self.assertEqual(passed["same_signal_streak"], 0)
        self.assertEqual(passed["consecutive_failures"], 0)
        self.assertEqual(passed["runs"], 4)

    def test_malformed_past_receipts_never_change_the_run_result(self) -> None:
        malformed: list[dict[str, object]] = [
            {"outcome": []},
            {"failure_reasons": 5},
            {"commands": {"start": {"duration_ms": "slow"}}, "scenarios": [7]},
            {"scenarios": "none", "ux_integrity": {"snapshots": [{"elements": 3}]}},
            {"measured_at": {"when": "never"}},
            {"partial": "yes", "ui_evidence": {"steps": [{"evidence": [{"path": 9}]}]}},
            {"commands": {"start": {"duration_ms": float("nan")}}},
            {"commands": {"start": {"duration_ms": float("inf")}}},
            {"commands": {"start": {"duration_ms": 10**400}}},
            {"commands": {"start": {"duration_ms": -5}}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_config(root, _config(exits=(0, 3)))
            _run(root, "run-1", measured_at="2026-07-10T00:00:00Z")
            template = json.loads(
                (root / EVIDENCE / "run-1/receipt.json").read_text(encoding="utf-8")
            )
            for index, override in enumerate(malformed):
                broken_dir = root / EVIDENCE / f"broken-{index}"
                broken_dir.mkdir()
                (broken_dir / "receipt.json").write_text(
                    json.dumps({**template, "run_id": f"broken-{index}", **override}),
                    encoding="utf-8",
                )
            (root / EVIDENCE / "broken-text").mkdir()
            (root / EVIDENCE / "broken-text/receipt.json").write_text("[1, 2", encoding="utf-8")
            _write_config(root, _config())
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                code = main(
                    [
                        "run",
                        "--project-root", str(root),
                        "--config", str(root / CONFIG_PATH),
                        "--run-id", "run-2",
                    ]
                )
            history = journey_history(root, "fixture-judgment-journey")

        self.assertEqual(code, 0)
        self.assertIn("outcome=PASS", stream.getvalue())
        self.assertIn("cumulative runs=", stream.getvalue())
        self.assertLess(history["duration_ms"], 600_000)
        # Each record is judged on its own: unreadable ones are dropped, and a
        # readable one with an odd optional field still counts as a run.
        self.assertGreaterEqual(history["runs"], 2)
        self.assertLessEqual(history["runs"], 2 + len(malformed))
        self.assertEqual(history["consecutive_failures"], 0)

    def test_history_failure_never_changes_the_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_config(root, _config())
            argv = ["run", "--project-root", str(root), "--config", str(root / CONFIG_PATH)]
            out, err = io.StringIO(), io.StringIO()
            with (
                mock.patch(
                    "harness.product_journey.journey_history",
                    side_effect=RuntimeError("boom"),
                ),
                contextlib.redirect_stdout(out),
                contextlib.redirect_stderr(err),
            ):
                code = main([*argv, "--run-id", "run-1"])

        self.assertEqual(code, 0)
        self.assertTrue(out.getvalue().splitlines()[0].endswith("run-1/receipt.json"))
        self.assertIn("history unavailable", err.getvalue())

    def test_missing_screen_evidence_is_compared_by_its_path_inside_the_run(self) -> None:
        def _receipt(run_id: str, minute: int, missing: str) -> dict[str, object]:
            run_dir = f"{EVIDENCE.as_posix()}/{run_id}"
            return {
                "receipt_type": "dcness.product-journey",
                "journey_id": "fixture-judgment-journey",
                "run_id": run_id,
                "measured_at": f"2026-07-10T00:0{minute}:00Z",
                "outcome": "FAIL",
                "failure_reasons": ["ui_evidence_missing"],
                "evidence_paths": {"receipt": f"{run_dir}/receipt.json"},
                "ui_evidence": {
                    "steps": [
                        {
                            "step_id": "result",
                            "evidence": [
                                {
                                    "path": f"{run_dir}/{name}/screenshot.png",
                                    "present": name != missing,
                                }
                                for name in ("before", "after")
                            ],
                        }
                    ]
                },
            }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, missing in enumerate(("before", "before", "after")):
                run_dir = root / EVIDENCE / f"run-{index}"
                run_dir.mkdir(parents=True)
                (run_dir / "receipt.json").write_text(
                    json.dumps(_receipt(f"run-{index}", index, missing)), encoding="utf-8"
                )
                if index == 1:
                    same = journey_history(root, "fixture-judgment-journey")
            different = journey_history(root, "fixture-judgment-journey")

        self.assertEqual(same["same_signal_streak"], 2)
        self.assertEqual(different["same_signal_streak"], 1)
        self.assertEqual(different["consecutive_failures"], 3)

    def test_runs_of_the_same_second_keep_the_order_they_were_written_in(self) -> None:
        same_second = "2026-07-10T00:00:00Z"
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch("harness.product_journey._now_iso", return_value=same_second),
        ):
            root = Path(directory)
            _write_config(root, _config(exits=(0, 3)))
            _run(root, "before-fix", measured_at=same_second)
            _write_config(root, _config())
            _run(root, "b-first-pass", measured_at=same_second)
            _run(root, "after-fix", measured_at=same_second)
            history = journey_history(root, "fixture-judgment-journey")

        self.assertEqual(history["consecutive_failures"], 0)
        self.assertEqual(history["previous_outcome"], "PASS")
        self.assertEqual(history["failed"], 1)

    def test_run_prints_cumulative_history_after_the_receipt_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_config(root, _config(exits=(0, 3)))
            argv = ["run", "--project-root", str(root), "--config", str(root / CONFIG_PATH)]
            outputs: list[str] = []
            for run_id in ("run-1", "run-2"):
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    code = main([*argv, "--run-id", run_id])
                self.assertEqual(code, 1)
                outputs.append(stream.getvalue())
            receipt_path = (root / EVIDENCE / "run-2/receipt.json").resolve()

        first, second = (text.splitlines() for text in outputs)
        self.assertEqual(Path(second[0]), receipt_path)
        self.assertIn("runs=1", outputs[0])
        self.assertIn("no previous run", outputs[0])
        self.assertIn("runs=2", outputs[1])
        self.assertIn("failed=2", outputs[1])
        self.assertIn("duration=", outputs[1])
        self.assertIn("same as the previous run", outputs[1])
        self.assertIn("2 runs in a row", outputs[1])
        self.assertTrue(all(line.startswith("[product-journey] ") for line in first[1:]))


class SkipRecordTests(unittest.TestCase):
    def test_skip_record_keeps_the_reason_and_the_pass_it_relies_on(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            head = _git_project(root)
            _run(root, "pass-run", measured_at="2026-07-10T00:00:00Z")
            path = record_skip(
                root,
                config_path=root / CONFIG_PATH,
                reason="문서만 바뀌어 이 흐름이 지나는 화면 코드에 닿지 않는다",
                run_id="skip-1",
            )
            record = json.loads(path.read_text(encoding="utf-8"))
            valid = read_receipts(root)

        self.assertEqual(path.name, "skip.json")
        self.assertEqual(record["record_type"], "dcness.product-journey-skip")
        self.assertEqual(record["journey_id"], "fixture-judgment-journey")
        self.assertEqual(record["code_revision"], head)
        self.assertIn("문서만 바뀌어", record["reason"])
        self.assertEqual(record["scenarios"], ["scenario-one", "scenario-two"])
        self.assertEqual(record["basis"]["run_id"], "pass-run")
        self.assertEqual(record["basis"]["code_revision"], head)
        self.assertEqual([item["run_id"] for item in valid], ["pass-run"])

    def test_skip_relies_on_the_pass_written_last_within_one_second(self) -> None:
        same_second = "2026-07-10T00:00:00Z"
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch("harness.product_journey._now_iso", return_value=same_second),
        ):
            root = Path(directory)
            _write_config(root, _config())
            _run(root, "b-first-pass", measured_at=same_second)
            _run(root, "a-second-pass", measured_at=same_second)
            record = json.loads(
                record_skip(
                    root, config_path=root / CONFIG_PATH, reason="문서만 바뀌었다"
                ).read_text(encoding="utf-8")
            )

        self.assertEqual(record["basis"]["run_id"], "a-second-pass")

    def test_a_later_failure_of_the_target_leaves_the_skip_without_a_basis(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_config(root, _config())
            _run(root, "full-pass", measured_at="2026-07-10T00:00:00Z")
            _write_config(root, _config(exits=(0, 3)))
            _run(root, "later-fail", measured_at="2026-07-10T00:01:00Z")
            _run(
                root,
                "later-partial-fail",
                measured_at="2026-07-10T00:02:00Z",
                scenarios=["scenario-two"],
            )

            def _skip(run_id: str, scenarios: list[str] | None) -> dict[str, object]:
                path = record_skip(
                    root,
                    config_path=root / CONFIG_PATH,
                    reason="변경이 닿지 않는다",
                    scenarios=scenarios,
                    run_id=run_id,
                )
                return json.loads(path.read_text(encoding="utf-8"))

            whole = _skip("skip-whole", None)
            failed_one = _skip("skip-two", ["scenario-two"])
            untouched_one = _skip("skip-one", ["scenario-one"])
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                code = main(
                    [
                        "skip",
                        "--project-root", str(root),
                        "--config", str(root / CONFIG_PATH),
                        "--reason", "변경이 닿지 않는다",
                    ]
                )

        # The journey and scenario-two failed after the pass: the pass no longer backs them.
        self.assertIsNone(whole["basis"])
        self.assertEqual(whole["unresolved_failure"]["run_id"], "later-partial-fail")
        self.assertIsNone(failed_one["basis"])
        self.assertEqual(failed_one["unresolved_failure"]["run_id"], "later-partial-fail")
        # scenario-one passed in every run that executed it.
        self.assertEqual(untouched_one["basis"]["run_id"], "full-pass")
        self.assertNotIn("unresolved_failure", untouched_one)
        self.assertEqual(code, 0)
        self.assertIn("failed after the last full PASS", stream.getvalue())

    def test_a_run_level_failure_after_the_pass_blocks_every_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_config(root, _config())
            _run(root, "full-pass", measured_at="2026-07-10T00:00:00Z")
            broken = _config()
            commands = broken["commands"]
            assert isinstance(commands, dict)
            commands["health"] = _command("raise SystemExit(7)")
            _write_config(root, broken)
            _run(root, "health-fail", measured_at="2026-07-10T00:01:00Z")
            _write_config(root, _config())
            record = json.loads(
                record_skip(
                    root,
                    config_path=root / CONFIG_PATH,
                    reason="변경이 닿지 않는다",
                    scenarios=["scenario-one"],
                ).read_text(encoding="utf-8")
            )

        self.assertIsNone(record["basis"])
        self.assertEqual(record["unresolved_failure"]["run_id"], "health-fail")

    def test_only_a_target_that_passed_again_gets_its_basis_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_config(root, _config())
            _run(root, "full-pass", measured_at="2026-07-10T00:00:00Z")
            broken = _config(exits=(0, 3))
            commands = broken["commands"]
            assert isinstance(commands, dict)
            commands["cleanup"] = _command("raise SystemExit(5)")
            _write_config(root, broken)
            # scenario-two fails and cleanup fails in the same run.
            _run(root, "two-and-cleanup-fail", measured_at="2026-07-10T00:01:00Z")
            _write_config(root, _config(exits=(0, 3)))
            _run(
                root,
                "one-passes-again",
                measured_at="2026-07-10T00:02:00Z",
                scenarios=["scenario-one"],
            )

            def _skip(run_id: str, scenarios: list[str]) -> dict[str, object]:
                path = record_skip(
                    root,
                    config_path=root / CONFIG_PATH,
                    reason="변경이 닿지 않는다",
                    scenarios=scenarios,
                    run_id=run_id,
                )
                return json.loads(path.read_text(encoding="utf-8"))

            still_failing = _skip("skip-two", ["scenario-two"])
            passed_again = _skip("skip-one", ["scenario-one"])
            both = _skip("skip-both", ["scenario-one", "scenario-two"])

        self.assertIsNone(still_failing["basis"])
        self.assertEqual(
            still_failing["unresolved_failure"]["run_id"], "two-and-cleanup-fail"
        )
        self.assertEqual(passed_again["basis"]["run_id"], "full-pass")
        self.assertIsNone(both["basis"])

    def test_journey_without_scenarios_needs_a_later_pass_to_clear_a_failure(self) -> None:
        def _plain(exit_code: int) -> dict[str, object]:
            payload = _config()
            del payload["scenarios"]
            commands = payload["commands"]
            assert isinstance(commands, dict)
            commands["journey"] = _command(f"raise SystemExit({exit_code})")
            return payload

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_config(root, _plain(0))
            _run(root, "pass-1", measured_at="2026-07-10T00:00:00Z")
            _write_config(root, _plain(4))
            _run(root, "fail-2", measured_at="2026-07-10T00:01:00Z")
            blocked = json.loads(
                record_skip(
                    root, config_path=root / CONFIG_PATH, reason="변경이 닿지 않는다", run_id="skip-a"
                ).read_text(encoding="utf-8")
            )
            _write_config(root, _plain(0))
            _run(root, "pass-3", measured_at="2026-07-10T00:03:00Z")
            cleared = json.loads(
                record_skip(
                    root, config_path=root / CONFIG_PATH, reason="변경이 닿지 않는다", run_id="skip-b"
                ).read_text(encoding="utf-8")
            )

        self.assertIsNone(blocked["basis"])
        self.assertEqual(blocked["unresolved_failure"]["run_id"], "fail-2")
        self.assertEqual(cleared["basis"]["run_id"], "pass-3")
        self.assertNotIn("unresolved_failure", cleared)

    def test_skip_record_can_name_only_some_scenarios(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_config(root, _config())
            path = record_skip(
                root,
                config_path=root / CONFIG_PATH,
                reason="scenario-one 화면은 바뀌지 않았다",
                scenarios=["scenario-one"],
            )
            record = json.loads(path.read_text(encoding="utf-8"))
            with self.assertRaises(JourneyConfigError):
                record_skip(
                    root,
                    config_path=root / CONFIG_PATH,
                    reason="없는 시나리오",
                    scenarios=["scenario-missing"],
                )
            with self.assertRaises(JourneyConfigError):
                record_skip(root, config_path=root / CONFIG_PATH, reason="  ")

        self.assertEqual(record["scenarios"], ["scenario-one"])
        # No full PASS exists yet, so the record says it has nothing to rely on.
        self.assertIsNone(record["basis"])

    def test_cli_skip_writes_the_record_and_reports_a_missing_basis(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_config(root, _config())
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                code = main(
                    [
                        "skip",
                        "--project-root", str(root),
                        "--config", str(root / CONFIG_PATH),
                        "--reason", "문서만 바뀌었다",
                        "--run-id", "cli-skip",
                    ]
                )
            written = (root / EVIDENCE / "cli-skip/skip.json").is_file()
            missing_reason = main(
                ["skip", "--project-root", str(root), "--config", str(root / CONFIG_PATH), "--reason", ""]
            )

        self.assertEqual(code, 0)
        self.assertTrue(written)
        self.assertIn("no earlier full PASS", stream.getvalue())
        self.assertEqual(missing_reason, 2)


class NotRerunIsNotAPassTests(unittest.TestCase):
    def test_epic_summary_ignores_partial_reruns_and_skip_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_config(root, _config(exits=(0, 3), epic=True))
            _run(root, "full-fail", measured_at="2026-07-10T00:00:00Z")
            _write_config(root, _config(epic=True))
            partial = _run(
                root,
                "partial-pass",
                measured_at="2026-07-10T00:01:00Z",
                scenarios=["scenario-two"],
            )
            record_skip(
                root,
                config_path=root / CONFIG_PATH,
                reason="scenario-one 은 바뀌지 않았다",
                scenarios=["scenario-one"],
                run_id="skip-one",
                recorded_at="2026-07-10T00:02:00Z",
            )
            summary = epic_outcome.collect(root, "epic-01-messaging")

        self.assertEqual(partial.exit_code, 0)
        self.assertFalse(summary["close_ready"])
        self.assertEqual(summary["confirmed_criteria"], 1)
        self.assertEqual(summary["total_criteria"], 2)
        self.assertEqual(
            [flow["evidence_path"] for flow in summary["flows"]],
            [(EVIDENCE / "full-fail/receipt.json").as_posix()],
        )

    def test_scorecard_ignores_partial_reruns_and_skip_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "project"
            root.mkdir()
            _write_config(root, _config(exits=(0, 3)))
            _run(root, "full-fail", measured_at="2026-07-10T00:00:00Z")
            _write_config(root, _config())
            _run(
                root,
                "partial-pass",
                measured_at="2026-07-10T00:01:00Z",
                scenarios=["scenario-two"],
            )
            record_skip(
                root,
                config_path=root / CONFIG_PATH,
                reason="scenario-one 은 바뀌지 않았다",
                scenarios=["scenario-one"],
                run_id="skip-one",
                recorded_at="2026-07-10T00:02:00Z",
            )
            projects_file = base / "projects.json"
            projects_file.write_text(
                json.dumps({"version": 1, "projects": [str(root)]}), encoding="utf-8"
            )
            outcome = build_scorecard(
                projects_file,
                measured_at="2026-07-11T00:00:00Z",
                as_of="2026-07-11T00:00:00Z",
                redact_paths=True,
            )["product_outcome"]

        self.assertEqual(outcome["numerator"], 0)
        self.assertEqual(outcome["denominator"], 1)
        self.assertEqual(outcome["product_ac"], {"passed": 1, "total": 2})


if __name__ == "__main__":
    unittest.main()

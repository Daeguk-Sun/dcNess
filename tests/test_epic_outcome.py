"""Epic 종료 실제 제품 확인 — 대표 흐름 범위 보존과 결과 요약 계약 테스트."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from harness import epic_outcome
from harness.product_journey import JourneyConfigError, read_receipts, run_from_config


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path("app/.maestro/dcness-journey.json")


def _command(code: str) -> dict[str, object]:
    return {"argv": [sys.executable, "-c", code], "timeout_sec": 10}


def _epic_scope(
    *,
    epic: str = "epic-01-messaging",
    representative_story: str = "story-04-compose-and-send",
) -> dict[str, object]:
    return {
        "epic": epic,
        "representative_story": representative_story,
        "selection_rationale": (
            "새 메시지 작성과 발신이 앱 진입·대화 목록·대화 화면·발신 상태를 "
            "한 흐름으로 통과한다"
        ),
        "execution_environment": "android-emulator-api34",
    }


def _config(
    *,
    journey_id: str = "compose-and-send",
    target_ac: tuple[str, ...] = ("AC-MSG-4-1",),
    boundary: str = "cli",
    journey_code: str = "print('assertion passed')",
    epic_scope: object = "default",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "version": 1,
        "journey_id": journey_id,
        "target_ac": list(target_ac),
        "boundary": boundary,
        "assertion": {
            "description": "새 번호와 본문으로 메시지를 보내면 같은 화면이 대화 상태로 바뀐다",
            "source": "journey_exit",
        },
        "human_intervention_count": 0,
        "commands": {
            "start": {**_command("print('started')"), "mode": "command"},
            "health": _command("print('healthy')"),
            "journey": _command(journey_code),
            "cleanup": _command("print('cleaned')"),
        },
        "evidence_dir": ".dcness-work/product-journey",
    }
    if epic_scope == "default":
        payload["epic_scope"] = _epic_scope()
    elif epic_scope is not None:
        payload["epic_scope"] = epic_scope
    return payload


def _write_config(root: Path, payload: dict[str, object], name: str = "dcness-journey.json") -> Path:
    path = root / CONFIG_PATH.parent / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class EpicScopeContractTests(unittest.TestCase):
    """AC5 — Epic별 확인 설정이 Epic·대표 Story·대상 AC·code revision·실행 환경을 보존한다."""

    def test_run_preserves_epic_story_ac_revision_and_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _write_config(root, _config())
            result = run_from_config(root, config_path=config)
            self.assertEqual(0, result.exit_code)
            scope = result.receipt["epic_scope"]
            self.assertEqual("epic-01-messaging", scope["epic"])
            self.assertEqual("story-04-compose-and-send", scope["representative_story"])
            self.assertEqual("android-emulator-api34", scope["execution_environment"])
            self.assertIn("새 메시지 작성", scope["selection_rationale"])
            self.assertEqual("unknown", scope["code_revision"])
            self.assertEqual(["AC-MSG-4-1"], result.receipt["target_ac"])

    def test_code_revision_records_the_tracked_head_of_the_project(self) -> None:
        summary = epic_outcome.collect(ROOT, "epic-zz-absent")
        self.assertEqual([], summary["flows"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            import subprocess  # nosec B404

            for argv in (
                ["git", "init", "-q"],
                ["git", "config", "user.email", "fixture@example.com"],
                ["git", "config", "user.name", "fixture"],
            ):
                subprocess.run(argv, cwd=root, check=True)  # nosec B603 B607
            (root / "README.md").write_text("fixture", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=root, check=True)  # nosec B603 B607
            subprocess.run(  # nosec B603 B607
                ["git", "commit", "-q", "-m", "fixture"], cwd=root, check=True
            )
            head = subprocess.run(  # nosec B603 B607
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            config = _write_config(root, _config())
            result = run_from_config(root, config_path=config)
            self.assertEqual(head, result.receipt["epic_scope"]["code_revision"])

    def test_incomplete_epic_scope_is_a_contract_error(self) -> None:
        for broken in (
            {"epic": "epic-01-messaging"},
            {**_epic_scope(), "representative_story": ""},
            {**_epic_scope(), "epic": "Epic One"},
            {**_epic_scope(), "execution_environment": "   "},
            "epic-01-messaging",
        ):
            with self.subTest(broken=broken):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    config = _write_config(root, _config(epic_scope=broken))
                    with self.assertRaises(JourneyConfigError):
                        run_from_config(root, config_path=config)

    def test_journey_without_epic_scope_still_runs_and_is_unattributed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _write_config(root, _config(epic_scope=None))
            result = run_from_config(root, config_path=config)
            self.assertEqual(0, result.exit_code)
            self.assertNotIn("epic_scope", result.receipt)
            summary = epic_outcome.collect(root, "epic-01-messaging")
            self.assertEqual([], summary["flows"])
            self.assertFalse(summary["close_ready"])

    def test_tampered_epic_scope_invalidates_the_receipt(self) -> None:
        for mutation in (
            {"epic": "epic-02-other"},
            {"code_revision": "not-a-revision"},
            {"representative_story": ""},
        ):
            with self.subTest(mutation=mutation):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    config = _write_config(root, _config())
                    result = run_from_config(root, config_path=config)
                    payload = json.loads(result.receipt_path.read_text(encoding="utf-8"))
                    payload["epic_scope"].update(mutation)
                    if mutation == {"epic": "epic-02-other"}:
                        payload["epic_scope"].pop("code_revision")
                    result.receipt_path.write_text(
                        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                    )
                    self.assertEqual([], read_receipts(root))


class EpicSeparationTests(unittest.TestCase):
    """AC5 — 여러 Epic 결과를 서로 섞지 않는다."""

    def test_each_epic_only_sees_its_own_representative_flow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = _write_config(
                root,
                _config(journey_id="compose-and-send", target_ac=("AC-MSG-4-1",)),
                name="epic1.json",
            )
            second = _write_config(
                root,
                _config(
                    journey_id="settings-export",
                    target_ac=("AC-SET-2-1", "AC-SET-2-2"),
                    epic_scope=_epic_scope(
                        epic="epic-02-settings",
                        representative_story="story-02-export",
                    ),
                ),
                name="epic2.json",
            )
            run_from_config(root, config_path=first)
            run_from_config(root, config_path=second)

            messaging = epic_outcome.collect(root, "epic-01-messaging")
            settings = epic_outcome.collect(root, "epic-02-settings")

            self.assertEqual(
                ["compose-and-send"], [flow["journey_id"] for flow in messaging["flows"]]
            )
            self.assertEqual(1, messaging["total_criteria"])
            self.assertEqual(
                ["settings-export"], [flow["journey_id"] for flow in settings["flows"]]
            )
            self.assertEqual(2, settings["total_criteria"])
            self.assertNotIn("AC-SET-2-1", epic_outcome.render(messaging))

    def test_a_failing_epic_does_not_block_another_epic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_from_config(
                root,
                config_path=_write_config(root, _config(), name="epic1.json"),
            )
            run_from_config(
                root,
                config_path=_write_config(
                    root,
                    _config(
                        journey_id="settings-export",
                        journey_code="raise SystemExit(3)",
                        epic_scope=_epic_scope(
                            epic="epic-02-settings",
                            representative_story="story-02-export",
                        ),
                    ),
                    name="epic2.json",
                ),
            )
            self.assertTrue(epic_outcome.collect(root, "epic-01-messaging")["close_ready"])
            self.assertFalse(epic_outcome.collect(root, "epic-02-settings")["close_ready"])

    def test_unknown_epic_id_shape_is_a_contract_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                epic_outcome.collect(Path(directory), "Epic One")


class EpicCloseJudgmentTests(unittest.TestCase):
    """AC7 — 모의 구현·앱 미기동·흐름 미실행·성공 조건 미평가는 종료 가능으로 집계되지 않는다."""

    def _summary_for(self, root: Path, **config_kwargs: object) -> dict[str, object]:
        config = _write_config(root, _config(**config_kwargs))  # type: ignore[arg-type]
        run_from_config(root, config_path=config)
        return epic_outcome.collect(root, "epic-01-messaging")

    def test_mock_boundary_is_not_a_real_product_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = self._summary_for(root, boundary="mock")
            self.assertFalse(summary["close_ready"])
            self.assertEqual(0, summary["confirmed_criteria"])
            self.assertIn(
                "실제 제품이 아니라 모의 구현만 실행했다", summary["close_blockers"]
            )

    def test_app_not_started_blocks_close(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _config()
            commands = config["commands"]
            assert isinstance(commands, dict)
            commands["start"] = {**_command("raise SystemExit(9)"), "mode": "command"}
            run_from_config(root, config_path=_write_config(root, config))
            summary = epic_outcome.collect(root, "epic-01-messaging")
            self.assertFalse(summary["close_ready"])
            self.assertIn("앱이 기동되지 않았다", summary["close_blockers"])
            self.assertIn(
                "대표 사용자 흐름을 실행하지 못했다", summary["close_blockers"]
            )
            self.assertIn("성공 조건을 평가하지 않았다", summary["close_blockers"])

    def test_assertion_not_evaluated_blocks_close(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _config()
            assertion = config["assertion"]
            assert isinstance(assertion, dict)
            assertion["source"] = "none"
            run_from_config(root, config_path=_write_config(root, config))
            summary = epic_outcome.collect(root, "epic-01-messaging")
            self.assertFalse(summary["close_ready"])
            self.assertEqual(0, summary["confirmed_criteria"])
            self.assertIn("성공 조건을 평가하지 않았다", summary["close_blockers"])

    def test_no_run_at_all_is_not_close_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            summary = epic_outcome.collect(Path(directory), "epic-01-messaging")
            self.assertFalse(summary["close_ready"])
            self.assertEqual([epic_outcome.NO_RUN_REASON], summary["close_blockers"])

    def test_a_fixed_rerun_supersedes_the_earlier_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            broken = _write_config(
                root, _config(journey_code="raise SystemExit(4)"), name="broken.json"
            )
            run_from_config(
                root, config_path=broken, run_id="run-001", measured_at="2026-09-20T00:00:00Z"
            )
            self.assertFalse(epic_outcome.collect(root, "epic-01-messaging")["close_ready"])
            fixed = _write_config(root, _config(), name="fixed.json")
            run_from_config(
                root, config_path=fixed, run_id="run-002", measured_at="2026-09-21T00:00:00Z"
            )
            summary = epic_outcome.collect(root, "epic-01-messaging")
            self.assertTrue(summary["close_ready"])
            self.assertEqual(1, len(summary["flows"]))

    def test_a_later_failure_supersedes_an_earlier_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_from_config(
                root,
                config_path=_write_config(root, _config(), name="good.json"),
                run_id="run-001",
                measured_at="2026-09-20T00:00:00Z",
            )
            run_from_config(
                root,
                config_path=_write_config(
                    root, _config(journey_code="raise SystemExit(5)"), name="bad.json"
                ),
                run_id="run-002",
                measured_at="2026-09-21T00:00:00Z",
            )
            self.assertFalse(epic_outcome.collect(root, "epic-01-messaging")["close_ready"])


class EpicSummaryReportTests(unittest.TestCase):
    """AC8·AC9 — 결과 요약은 제품 언어로 나오고, 실패 시 관련 story·AC를 제시한다."""

    def test_summary_uses_product_language_without_internal_terms(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_from_config(root, config_path=_write_config(root, _config()))
            text = epic_outcome.render(epic_outcome.collect(root, "epic-01-messaging"))
            self.assertIn("Epic 결과 요약", text)
            self.assertIn("대표 사용자 흐름", text)
            self.assertIn("Epic 종료 가능: 예", text)
            self.assertIn("완료 기준 확인: 1 / 1", text)
            self.assertIn("android-emulator-api34", text)
            prose = "\n".join(
                line for line in text.splitlines() if "실행 기록:" not in line
            )
            for internal_term in (
                "journey",
                "receipt",
                "scorecard",
                "boundary",
                "manifest",
                "assertion",
                "{",
                "}",
            ):
                self.assertNotIn(internal_term, prose)

    def test_failed_summary_names_the_story_the_criteria_and_the_reason(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_from_config(
                root,
                config_path=_write_config(
                    root,
                    _config(
                        target_ac=("AC-MSG-4-1", "AC-MSG-4-2"),
                        journey_code="raise SystemExit(7)",
                    ),
                ),
            )
            text = epic_outcome.render(epic_outcome.collect(root, "epic-01-messaging"))
            self.assertIn("Epic 종료 가능: 아니오", text)
            self.assertIn("대표 사용자 흐름이 성공 조건을 만족하지 못했다", text)
            self.assertIn("story-04-compose-and-send", text)
            self.assertIn("AC-MSG-4-1, AC-MSG-4-2", text)

    def test_cli_exit_code_reports_close_readiness(self) -> None:
        from harness import product_journey

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(
                1,
                product_journey.main(
                    ["epic-summary", "--project-root", str(root), "--epic", "epic-01-messaging"]
                ),
            )
            run_from_config(root, config_path=_write_config(root, _config()))
            self.assertEqual(
                0,
                product_journey.main(
                    ["epic-summary", "--project-root", str(root), "--epic", "epic-01-messaging"]
                ),
            )
            self.assertEqual(
                2,
                product_journey.main(
                    ["epic-summary", "--project-root", str(root), "--epic", "Epic One"]
                ),
            )


if __name__ == "__main__":
    unittest.main()

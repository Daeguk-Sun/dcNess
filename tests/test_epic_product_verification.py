"""Epic-close product verification workflow regressions (#1087)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from harness.product_journey import JourneyConfigError, read_receipts, run_from_config


ROOT = Path(__file__).resolve().parents[1]


def _command(code: str) -> dict[str, object]:
    return {"argv": [sys.executable, "-c", code], "timeout_sec": 10}


def _init_git(root: Path) -> str:
    subprocess.run(["git", "init", "-q", root], check=True)
    subprocess.run(["git", "-C", root, "config", "user.name", "fixture"], check=True)
    subprocess.run(
        ["git", "-C", root, "config", "user.email", "fixture@example.com"],
        check=True,
    )
    (root / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", root, "add", "README.md"], check=True)
    subprocess.run(["git", "-C", root, "commit", "-qm", "fixture"], check=True)
    return subprocess.run(
        ["git", "-C", root, "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _epic_config(revision: str, epic_id: str = "epic-01-sms-messaging") -> dict[str, object]:
    return {
        "version": 1,
        "journey_id": "compose-and-send",
        "epic": {
            "id": epic_id,
            "representative_story": "story-04-compose-new-message",
            "code_revision": revision,
            "execution_environment": "Android emulator API 35",
            "test_data_cleanup": "테스트 전화번호와 발신 메시지를 제거한다",
        },
        "target_ac": ["AC-015"],
        "boundary": "ui",
        "assertion": {
            "description": "새 번호와 본문을 보내면 같은 화면에 전송 중 메시지가 나타난다",
            "source": "journey_exit",
        },
        "human_intervention_count": 0,
        "commands": {
            "start": {**_command("print('app started')"), "mode": "command"},
            "health": _command("print('app visible')"),
            "journey": _command(
                "import os; from pathlib import Path; "
                "run=Path(os.environ['DCNESS_PRODUCT_JOURNEY_RUN_DIR']); "
                "(run/'compose.png').write_bytes(b'compose-screen'); "
                "(run/'sending.png').write_bytes(b'sending-screen'); "
                "(run/'sending.log').write_text('evt=sms_send_queued')"
            ),
            "cleanup": _command("print('fixture removed')"),
        },
        "ui_evidence": {
            "steps": [
                {
                    "step_id": "compose",
                    "description": "새 번호와 본문을 입력한다",
                    "target_ac": ["AC-015"],
                    "final": False,
                    "evidence": [{"path": "compose.png", "type": "screenshot"}],
                },
                {
                    "step_id": "sending",
                    "description": "같은 화면의 전송 중 메시지를 확인한다",
                    "target_ac": ["AC-015"],
                    "final": True,
                    "evidence": [
                        {"path": "sending.png", "type": "screenshot"},
                        {"path": "sending.log", "type": "log"},
                    ],
                },
            ]
        },
        "evidence_dir": f".dcness-work/product-journey/{epic_id}",
    }


def _write_epic_config(root: Path, config: dict[str, object]) -> Path:
    epic = config["epic"]
    assert isinstance(epic, dict)
    path = (
        root
        / ".dcness-work"
        / "product-journey-contracts"
        / str(epic["id"])
        / f"{config['journey_id']}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return path


class EpicProductJourneyContractTests(unittest.TestCase):
    def test_epic_receipt_preserves_scope_revision_environment_and_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            revision = _init_git(root)
            config = _epic_config(revision)
            config_path = _write_epic_config(root, config)

            result = run_from_config(
                root,
                config_path=config_path,
                run_id="epic-one-pass",
                measured_at="2026-07-13T08:00:00Z",
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.receipt["boundary"], "ui")
            self.assertEqual(
                {item["type"] for item in result.receipt["ui_evidence"]["steps"][1]["evidence"]},
                {"screenshot", "log"},
            )
            self.assertEqual(
                result.receipt["epic"],
                {
                    "id": "epic-01-sms-messaging",
                    "representative_story": "story-04-compose-new-message",
                    "code_revision": revision,
                    "execution_environment": "Android emulator API 35",
                    "test_data_cleanup": "테스트 전화번호와 발신 메시지를 제거한다",
                },
            )
            self.assertEqual(result.receipt["target_ac"], ["AC-015"])
            self.assertEqual(
                result.receipt_path.relative_to(root.resolve()).parts[:3],
                (".dcness-work", "product-journey", "epic-01-sms-messaging"),
            )
            self.assertEqual(
                [item["run_id"] for item in read_receipts(root, epic_id="epic-01-sms-messaging")],
                ["epic-one-pass"],
            )
            self.assertEqual(read_receipts(root, epic_id="epic-02-mms"), [])

    def test_epic_contract_rejects_stale_revision_before_starting_product(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            revision = _init_git(root)
            config = _epic_config("0" * len(revision))
            config_path = _write_epic_config(root, config)

            with self.assertRaisesRegex(JourneyConfigError, "code_revision"):
                run_from_config(root, config_path=config_path, run_id="stale-revision")

            self.assertFalse((root / ".dcness-work" / "product-journey").exists())

    def test_epic_contract_rejects_uncommitted_product_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            revision = _init_git(root)
            config_path = _write_epic_config(root, _epic_config(revision))
            (root / "README.md").write_text("changed product\n", encoding="utf-8")

            with self.assertRaisesRegex(JourneyConfigError, "working tree"):
                run_from_config(root, config_path=config_path, run_id="dirty-product")

            self.assertFalse((root / ".dcness-work" / "product-journey").exists())

    def test_epic_contract_cannot_write_into_another_epic_evidence_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            revision = _init_git(root)
            config = _epic_config(revision)
            config["evidence_dir"] = ".dcness-work/product-journey/epic-02-mms"
            config_path = _write_epic_config(root, config)

            with self.assertRaisesRegex(JourneyConfigError, "evidence_dir"):
                run_from_config(root, config_path=config_path, run_id="mixed-epic")


class EpicProductVerificationWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.impl_loop = (ROOT / "skills/impl-loop/SKILL.md").read_text(encoding="utf-8")
        self.acceptance = (ROOT / "skills/acceptance/SKILL.md").read_text(encoding="utf-8")
        self.product_acceptance = (
            ROOT / "docs/plugin/agents/product-acceptance/product-acceptance-agent.md"
        ).read_text(encoding="utf-8")
        self.init_command = (ROOT / "commands/init-dcness.md").read_text(encoding="utf-8")

    def test_epic_close_selects_one_or_at_most_two_flows_after_all_stories(self) -> None:
        for workflow in (self.impl_loop, self.acceptance):
            self.assertIn("모든 Story", workflow)
            self.assertIn("Epic 목표", workflow)
            self.assertIn("Story AC", workflow)
            self.assertIn("최신 결정", workflow)
            self.assertIn("기본 1개", workflow)
            self.assertIn("최대 2개", workflow)
            self.assertIn("실제 제품 실행 전에 승인", workflow)

    def test_user_approval_and_result_summary_stay_in_product_language(self) -> None:
        for workflow in (self.impl_loop, self.acceptance):
            for phrase in (
                "실행할 내용",
                "성공으로 볼 결과",
                "정리할 테스트 데이터",
                "JSON",
                "내부 helper 명령",
                "대표 흐름 결과",
                "전체 Story AC evidence",
                "회귀",
                "사람 확인",
                "남은 gap",
                "Epic 종료 가능 여부",
            ):
                self.assertIn(phrase, workflow)

        self.assertIn("관련 Story·AC", self.product_acceptance)
        self.assertIn("다음 구현 경로", self.product_acceptance)

    def test_blank_project_init_reports_no_executable_epic_without_prompting(self) -> None:
        self.assertIn("실행 가능한 Epic 없음", self.init_command)
        self.assertIn("대표 흐름", self.init_command)
        self.assertIn("제품 확인 설정", self.init_command)
        self.assertIn("묻지 않는다", self.init_command)

    def test_representative_android_fixture_requires_story_four_cross_story_choice(self) -> None:
        case = ROOT / "evals/cases/epic-product-verification-selection"
        expected = (case / "expected.md").read_text(encoding="utf-8")
        prompt = (case / "prompt.md").read_text(encoding="utf-8")
        stories = (case / "stories.md").read_text(encoding="utf-8")

        self.assertIn("Story 4", expected)
        self.assertIn("Story 1~3", expected)
        self.assertIn("같은 화면", expected)
        self.assertIn("Sending", expected)
        self.assertIn("최대 2개", prompt)
        self.assertIn("Story 4", stories)


if __name__ == "__main__":
    unittest.main()

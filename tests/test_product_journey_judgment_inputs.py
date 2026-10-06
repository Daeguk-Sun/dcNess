"""Judgment inputs a journey run leaves for the agent that decides what to re-run."""

from __future__ import annotations

import json
import subprocess  # nosec B404
import sys
import tempfile
import unittest
from pathlib import Path

from harness.product_journey import (
    read_receipts,
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


if __name__ == "__main__":
    unittest.main()

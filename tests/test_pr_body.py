"""Regression tests for the PR-body trailer gate (scripts/check_pr_body.mjs).

규칙 SSOT = docs/plugin/git-spec.md 의 PR 트레일러. task 는 local commit 이고
PR 경계는 story 이므로 gate 는 task_index 로 close 시점을 추론하지 않는다. issue
트레일러 1건 또는 명시적 exception 만 강제한다.

node 미설치 환경에서는 skip.
"""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_pr_body.mjs"
NODE = shutil.which("node")


def _run(body: str) -> int:
    proc = subprocess.run(
        [NODE, str(SCRIPT), "--body", body],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode


@unittest.skipUnless(NODE, "node not installed — pr-body gate is a node script")
class PrBodyGateTests(unittest.TestCase):
    def assertPass(self, body: str) -> None:
        self.assertEqual(_run(body), 0, f"기대 PASS 인데 FAIL:\n{body}")

    def assertFail(self, body: str) -> None:
        self.assertEqual(_run(body), 1, f"기대 FAIL 인데 PASS:\n{body}")

    def test_part_of_passes(self) -> None:
        self.assertPass("## 작업내용\n공통 task — 테마 토큰\n\nPart of #42\n")

    def test_legacy_task_index_does_not_change_story_pr_rule(self) -> None:
        self.assertPass("작업\n\ntask-index: 3/3\nCloses #42\n")
        self.assertPass("작업\n\ntask-index: 1/3\nPart of #42\n")
        self.assertPass("작업\n\ntask-index: 3/3\nPart of #42\n")

    def test_empty_body_fails(self) -> None:
        self.assertFail("")

    def test_document_exception_marker_passes(self) -> None:
        self.assertPass("infra-only 변경\n\nDocument-Exception-PR-Close: 이슈 없음\n")

    def test_retired_integration_branch_exception_fails(self) -> None:
        self.assertFail(
            "story 변경\n\n"
            "Document-Exception-PR-Close: 통합 브랜치 story sub-PR — "
            "main 머지 시 일괄 close\n"
        )

    def test_no_trailer_fails(self) -> None:
        self.assertFail("## 작업내용\n트레일러 없음\n")


if __name__ == "__main__":
    unittest.main()

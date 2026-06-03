"""Regression tests for the PR-body trailer gate (scripts/check_pr_body.mjs).

규칙 SSOT = docs/plugin/git-spec.md 의 PR 트레일러. 본 테스트는 게이트가 task-index 트레일러 기반
분기를 올바로 강제하는지 검증한다 — 특히 codex 리뷰 F2-b 회귀:
  - 공통 task (task_index: —) 는 task-index trailer 가 omit 되고 `Part of #N` 으로 통과해야 함
    (Story 마지막 task 로 오판돼 Closes 강제되면 안 됨)
  - Story 마지막 task (i == total) 는 Closes/Fixes/Resolves 강제, Part of 단독 FAIL
  - 중간 task (i < total) 는 트레일러 1건이면 통과

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

    def test_common_task_part_of_passes(self) -> None:
        # 공통 task — task-index trailer 없음 + Part of → fallback path 통과 (F2-b 회귀)
        self.assertPass("## 작업내용\n공통 task — 테마 토큰\n\nPart of #42\n")

    def test_story_last_task_requires_close(self) -> None:
        # i == total → Closes 강제
        self.assertPass("작업\n\ntask-index: 3/3\nCloses #42\n")
        self.assertFail("작업\n\ntask-index: 3/3\nPart of #42\n")  # Part of 단독 FAIL

    def test_mid_task_part_of_passes(self) -> None:
        self.assertPass("작업\n\ntask-index: 1/3\nPart of #42\n")

    def test_empty_body_fails(self) -> None:
        self.assertFail("")

    def test_document_exception_marker_passes(self) -> None:
        self.assertPass("infra-only 변경\n\nDocument-Exception-PR-Close: 이슈 없음\n")

    def test_no_trailer_fails(self) -> None:
        self.assertFail("## 작업내용\n트레일러 없음\n")


if __name__ == "__main__":
    unittest.main()

"""Regression tests for the git-naming gate (scripts/check_git_naming.mjs).

규칙 SSOT = docs/plugin/git-spec.md §1/§2. 본 테스트는 게이트가 그 SSOT 를
실제로 강제하는지 검증한다 — 특히:
  - feat/ · chore/ · fix/<slug>(issue 없는) 같은 invalid prefix 거부 (PR #566 회귀)
  - story 형태 malformed 브랜치(desc<3자 / story 비숫자)가 generic feature 로 새지 않음
    (check_git_naming.mjs 부정선행 (?!epic\\d+_story))
  - 공통 task 의 feature/epic{N}_common_{desc} 는 generic 으로 통과

node 미설치 환경에서는 skip (게이트는 node 스크립트).
"""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_git_naming.mjs"
NODE = shutil.which("node")


def _run(mode: str, value: str) -> int:
    """check_git_naming.mjs 를 호출하고 exit code 반환 (0 = PASS, 1 = FAIL)."""
    proc = subprocess.run(
        [NODE, str(SCRIPT), mode, value],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode


@unittest.skipUnless(NODE, "node not installed — git-naming gate is a node script")
class BranchNamingTests(unittest.TestCase):
    def assertBranchPass(self, branch: str) -> None:
        self.assertEqual(_run("--branch", branch), 0, f"기대 PASS 인데 FAIL: {branch}")

    def assertBranchFail(self, branch: str) -> None:
        self.assertEqual(_run("--branch", branch), 1, f"기대 FAIL 인데 PASS: {branch}")

    def test_valid_story_branch(self) -> None:
        self.assertBranchPass("feature/epic7_story2_revival-button")
        self.assertBranchPass("feature/epic07_story02_revival-button")  # zero-pad

    def test_valid_common_task_branch(self) -> None:
        # 공통 task (story: 공통 / task_index: —) — epic-traceable, generic 통과
        self.assertBranchPass("feature/epic7_common_theme_tokens")

    def test_valid_generic_feature_and_integration(self) -> None:
        self.assertBranchPass("feature/local_dsp")
        self.assertBranchPass("feature/integration_branch_pattern")

    def test_valid_fix_and_docs(self) -> None:
        self.assertBranchPass("fix/issue32_duplicate_touch")
        self.assertBranchPass("fix/issue32_45_duplicate_touch")  # 복수 이슈
        self.assertBranchPass("docs/ssot-drift-cleanup")

    def test_invalid_conventional_prefixes(self) -> None:
        # PR #566 회귀: feat/ · chore/ · fix/<slug>(issue 없음) 은 SSOT 에 없음
        self.assertBranchFail("feat/foo-bar")
        self.assertBranchFail("chore/foo-bar")
        self.assertBranchFail("fix/foo-bar")
        self.assertBranchFail("bugfix/foo-bar")

    def test_malformed_story_does_not_leak_to_generic(self) -> None:
        # 부정선행 (?!epic\\d+_story) — story 형태인데 strict 패턴 위반이면 거부
        self.assertBranchFail("feature/epic7_story2_ui")            # desc < 3자
        self.assertBranchFail("feature/epic7_story2_x")             # desc 1자
        self.assertBranchFail("feature/epic7_story_common_theme")   # story 비숫자

    def test_desc_constraints(self) -> None:
        self.assertBranchFail("feature/UpperCase")   # 대문자 금지
        self.assertBranchFail("feature/ab")          # 최소 3자 미만
        self.assertBranchFail("feature/9start")      # 숫자 시작 금지


@unittest.skipUnless(NODE, "node not installed — git-naming gate is a node script")
class TitleNamingTests(unittest.TestCase):
    def assertTitlePass(self, title: str) -> None:
        self.assertEqual(_run("--title", title), 0, f"기대 PASS 인데 FAIL: {title}")

    def assertTitleFail(self, title: str) -> None:
        self.assertEqual(_run("--title", title), 1, f"기대 FAIL 인데 PASS: {title}")

    def test_valid_titles(self) -> None:
        self.assertTitlePass("[epic1][story2] mcp 세팅")
        self.assertTitlePass("[epic19] Local DSP 통합 머지")
        self.assertTitlePass("[issue-32] 중복 터치 수정")
        self.assertTitlePass("[docs] API 스펙 업데이트")
        self.assertTitlePass("[feature] 통합 브랜치 패턴 지원")

    def test_invalid_titles(self) -> None:
        self.assertTitleFail("feat: add thing")        # conventional-commits 금지
        self.assertTitleFail("[chore] cleanup")        # 미허용 태그
        self.assertTitleFail("no prefix at all")


if __name__ == "__main__":
    unittest.main()

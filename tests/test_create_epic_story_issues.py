"""create_epic_story_issues.sh GitHub Project board registration tests (#669).

fake `gh` + fake `node` 를 PATH 앞에 주입해 스크립트의 보드 등록/좌표조회/멱등
분기를 통합 검증한다. register-issue 자체 동작은 test_github_project_lifecycle.py
(planRegistration 단위) 가 담당하고, 여기서는 create_epic_story_issues.sh 가
'올바른 인자로 register-issue 를 호출하는가 / 좌표 없으면 skip 하는가 / 이슈는
항상 생성하는가' 를 본다.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "create_epic_story_issues.sh"

# 스크립트가 직접 부르는 gh 호출 stub. 인자 분기 + 호출 로그.
FAKE_GH = """#!/bin/sh
echo "$*" >> "$GH_LOG"
cmd="$1 $2"
case "$cmd" in
"repo view") echo "testowner/testrepo" ;;
"variable get")
  if [ "$VARS_PRESENT" = "1" ]; then
    case "$3" in
      DCNESS_PROJECT_NUMBER) echo "7" ;;
      DCNESS_PROJECT_OWNER) echo "testowner" ;;
      *) echo "" ;;
    esac
  else
    echo "variable $3 was not found" >&2
    exit 1
  fi
  ;;
"api -X") exit 0 ;;
"api "*)
  case "$*" in
    *sub_issues*) exit 0 ;;
    *Epics*) echo "Epics" ;;
    *Story*) echo "Story" ;;
    *) echo "999" ;;
  esac
  ;;
"issue create")
  n=$(cat "$CNT_FILE" 2>/dev/null || echo 100)
  echo "https://github.com/testowner/testrepo/issues/$n"
  echo $((n + 1)) > "$CNT_FILE"
  ;;
*) exit 0 ;;
esac
"""

# register-issue 호출 가로채기. mjs 실행 대신 인자 로그 + 선택적 실패.
FAKE_NODE = """#!/bin/sh
echo "$*" >> "$NODE_LOG"
issue=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--issue" ]; then issue="$2"; fi
  shift
done
if [ -n "$FAIL_ISSUE" ] && [ "$FAIL_ISSUE" = "$issue" ]; then
  echo "issue #$issue: Project IssueType option not found." >&2
  exit 1
fi
exit 0
"""

STORIES_NEW = """**Base Branch:** feature/test_epic

## Epic — 테스트 에픽

에픽 본문 설명.

### Story 1 — 첫 스토리

스토리 1 본문.

### Story 2 — 둘째 스토리

스토리 2 본문.
"""

STORIES_REGISTERED = """**GitHub Epic Issue:** [#100](https://github.com/testowner/testrepo/issues/100)

## Epic — 테스트 에픽

에픽 본문 설명.

### Story 1 — 첫 스토리

**GitHub Issue:** [#101](https://github.com/testowner/testrepo/issues/101)

스토리 1 본문.

### Story 2 — 둘째 스토리

**GitHub Issue:** [#102](https://github.com/testowner/testrepo/issues/102)

스토리 2 본문.
"""


class CreateEpicStoryBoardTests(unittest.TestCase):
    def _run(self, stories_content, env_extra=None):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            bin_dir = tdp / "bin"
            bin_dir.mkdir()
            (bin_dir / "gh").write_text(FAKE_GH)
            (bin_dir / "gh").chmod(0o755)
            (bin_dir / "node").write_text(FAKE_NODE)
            (bin_dir / "node").chmod(0o755)
            stories = tdp / "stories.md"
            stories.write_text(stories_content, encoding="utf-8")
            gh_log = tdp / "gh.log"
            node_log = tdp / "node.log"
            cnt = tdp / "cnt"
            env = {
                **os.environ,
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "GH_LOG": str(gh_log),
                "NODE_LOG": str(node_log),
                "CNT_FILE": str(cnt),
            }
            # 좌표 env 가 부모 환경에서 새지 않도록 제거 (테스트 격리)
            env.pop("DCNESS_PROJECT_NUMBER", None)
            env.pop("DCNESS_PROJECT_OWNER", None)
            if env_extra:
                env.update(env_extra)
            result = subprocess.run(
                ["bash", str(SCRIPT), str(stories)],
                cwd=td,
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )
            return (
                result,
                gh_log.read_text() if gh_log.exists() else "",
                node_log.read_text() if node_log.exists() else "",
                stories.read_text(encoding="utf-8"),
            )

    def test_registers_each_issue_when_coords_present(self):
        result, gh_log, node_log, _ = self._run(STORIES_NEW, {"VARS_PRESENT": "1"})
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(3, gh_log.count("issue create"))
        self.assertEqual(3, node_log.count("register-issue"))
        self.assertEqual(1, node_log.count("--issue-type epic"))
        self.assertEqual(2, node_log.count("--issue-type story"))
        # fresh 경로(새 이슈)는 strict 등록 — preserve 안 함 (Todo/major 강제 + 검증).
        self.assertEqual(0, node_log.count("--preserve-existing"))

    def test_skips_board_when_no_coords_but_still_creates_issues(self):
        result, gh_log, node_log, _ = self._run(STORIES_NEW, {})
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(3, gh_log.count("issue create"))
        self.assertEqual(0, node_log.count("register-issue"))
        self.assertIn("보드", result.stdout + result.stderr)

    def test_partial_board_failure_reported_issues_still_created(self):
        result, gh_log, node_log, _ = self._run(
            STORIES_NEW, {"VARS_PRESENT": "1", "FAIL_ISSUE": "102"}
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(3, gh_log.count("issue create"))
        self.assertEqual(3, node_log.count("register-issue"))
        out = result.stdout + result.stderr
        self.assertIn("102", out)
        self.assertRegex(out, r"(partial|실패|WARN)")

    def test_idempotent_backfill_registers_board_without_creating_issues(self):
        result, gh_log, node_log, _ = self._run(
            STORIES_REGISTERED, {"VARS_PRESENT": "1"}
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(0, gh_log.count("issue create"))
        self.assertEqual(3, node_log.count("register-issue"))
        self.assertIn("--issue 100", node_log)
        self.assertIn("--issue 101", node_log)
        self.assertIn("--issue 102", node_log)
        # 백필 회귀 가드 (#669): 기존 item 의 triage 상태(In progress/Done/priority)를
        # 되돌리지 않도록 백필 경로는 register-issue 에 --preserve-existing 를 넘긴다.
        self.assertEqual(3, node_log.count("--preserve-existing"))


if __name__ == "__main__":
    unittest.main()

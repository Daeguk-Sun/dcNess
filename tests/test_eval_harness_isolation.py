"""evals/run.sh 의 claude -p 호출이 dcNess 하네스(CLAUDE.md / skills / hooks / MCP /
user settings / tool schema)를 주입당하지 않도록 격리하는 계약 테스트 (#1073).

행동 eval 은 케이스마다 claude -p 를 검수·채점 2회 부른다. 이 호출이 customization 을
지고 돌면 세션당 ~43k baseline 을 짊어져(실측) fan-out 시 quota 를 폭식한다. --safe-mode
가 CLAUDE.md·skills·hooks·MCP·user settings 를 전부 끄면서(OAuth 인증 유지) baseline 을
무너뜨리고, --tools 가 도구 schema 를 제한한다.

- 검수자: {{REPO_ROOT}} agent 지침 Read + 일부 케이스의 {{CASE_DIR}} fixture 열거(Glob)
  가 필요하므로 --tools Read Glob + --add-dir "$ROOT" + --add-dir "$sandbox" 로 접근 유지.
- 채점자: 정답표+보고가 프롬프트에 인라인 → repo 접근 0, --tools "" 로 도구 전체 제거.

실측 baseline: 43,455 → 검수자(--tools Read Glob) 3,067 / 채점자(--tools "") 1,857.

role-specific 계약은 스크립트 전체가 아니라 각 호출 라인에 대해 검사한다 — 그래야
검수자/채점자 플래그가 뒤바뀌는 회귀를 잡는다.
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN_SH = ROOT / "evals" / "run.sh"


class EvalHarnessIsolationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = RUN_SH.read_text(encoding="utf-8")
        cls.claude_calls = [
            line
            for line in cls.src.splitlines()
            if "claude -p" in line and not line.lstrip().startswith("#")
        ]

    def _reviewer(self):
        cands = [c for c in self.claude_calls if '"$prompt"' in c]
        self.assertEqual(len(cands), 1, "검수자 호출('$prompt')은 정확히 1개")
        return cands[0]

    def _judge(self):
        cands = [c for c in self.claude_calls if '"$judge_prompt"' in c]
        self.assertEqual(len(cands), 1, "채점자 호출('$judge_prompt')은 정확히 1개")
        return cands[0]

    def test_run_sh_exists(self):
        self.assertTrue(RUN_SH.is_file(), "evals/run.sh 가 있어야 한다")

    def test_two_claude_calls(self):
        self.assertEqual(len(self.claude_calls), 2, "검수·채점 두 claude -p 호출")

    def test_reviewer_isolation(self):
        r = self._reviewer()
        self.assertIn("--safe-mode", r, "검수자 customization 차단")
        # fixture 열거(Glob) + agent 지침 Read
        self.assertIn("--tools Read Glob", r)
        self.assertIn('--add-dir "$ROOT"', r, "agent 지침 접근")
        self.assertIn('--add-dir "$sandbox"', r, "fixture 접근")
        self.assertNotIn("--allowedTools", r, "permission-only 플래그로 schema 못 줄임")
        self.assertNotIn("--bare", r, "구독 인증 유지")

    def test_judge_isolation(self):
        j = self._judge()
        self.assertIn("--safe-mode", j, "채점자 customization 차단")
        self.assertIn('--tools ""', j, "도구 schema 전체 제거")
        self.assertNotIn("--add-dir", j, "채점자는 repo 접근 불필요")
        self.assertNotIn("--allowedTools", j)
        self.assertNotIn("--bare", j)


if __name__ == "__main__":
    unittest.main()

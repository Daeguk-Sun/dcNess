"""evals/run.sh 의 claude -p 호출이 dcNess 하네스(CLAUDE.md / skills / hooks / MCP /
user settings / tool schema)를 주입당하지 않도록 격리하는 계약 테스트 (#1073).

행동 eval 은 케이스마다 claude -p 를 검수·채점 2회 부른다. 이 호출이 customization 을
지고 돌면 세션당 ~43k baseline 을 짊어져(실측) fan-out 시 quota 를 폭식한다. --safe-mode
가 CLAUDE.md·skills·hooks·MCP·user settings 를 전부 끄면서(OAuth 인증은 유지) baseline
을 무너뜨리고, --tools 가 도구 schema 를 제한한다. 검수자는 agent 지침 Read 를 위해
--tools "Read" + --add-dir "$ROOT" 로 repo 접근만 유지한다.

실측 baseline: 43,455 → --safe-mode 19,287 → --tools "" 10,493 →
--safe-mode --tools "" 1,529 (repo cwd 에서도 1,857). 검수자(--tools "Read") 2,755.
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

    def test_run_sh_exists(self):
        self.assertTrue(RUN_SH.is_file(), "evals/run.sh 가 있어야 한다")

    def test_two_claude_calls(self):
        self.assertEqual(len(self.claude_calls), 2, "검수·채점 두 claude -p 호출")

    def test_both_calls_use_safe_mode(self):
        # 두 호출 모두 --safe-mode 로 CLAUDE.md/skills/hooks/MCP/user settings 차단.
        for call in self.claude_calls:
            self.assertIn("--safe-mode", call, f"--safe-mode 누락: {call}")

    def test_reviewer_keeps_repo_access_with_read_tool(self):
        # 검수자는 {{REPO_ROOT}}/docs/plugin/agents/... 를 Read 하므로 repo 접근 + Read 도구 유지.
        self.assertIn('--add-dir "$ROOT"', self.src)
        self.assertIn('--tools "Read"', self.src)

    def test_judge_disables_all_tools(self):
        # 채점자는 정답표+보고 인라인 — 도구 schema 를 전부 제거.
        self.assertIn('--tools ""', self.src)

    def test_no_allowedtools_empty(self):
        # --allowedTools "" 는 permission 만 비우고 tool schema 는 남아 baseline 을 못 줄인다.
        # 도구 제거는 --tools 로 한다 (codex P2). 주석 설명 언급은 허용; 호출 라인만 검사.
        for call in self.claude_calls:
            self.assertNotIn(
                "--allowedTools", call, f"claude -p 호출에 --allowedTools 금지: {call}"
            )

    def test_no_bare_flag(self):
        # --bare 는 구독 인증(OAuth/keychain)을 못 읽어 "Not logged in" — 실제 호출에서 금지.
        for call in self.claude_calls:
            self.assertNotIn("--bare", call, f"claude -p 호출에 --bare 금지: {call}")


if __name__ == "__main__":
    unittest.main()

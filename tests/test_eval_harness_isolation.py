"""evals/run.sh 의 claude -p 호출이 dcNess 하네스(CLAUDE.md / hook / skills / tool
정의)를 주입당하지 않도록 격리하는 계약 테스트 (#1073).

행동 eval 은 케이스마다 claude -p 를 검수·채점 2회 부른다. 이 호출이 repo cwd 에서
돌면 CLAUDE.md auto-discovery + hook + skills 가 매번 주입돼 세션당 ~43k baseline 을
짊어진다(실측). fan-out 실행에서는 이 baseline 이 quota 를 폭식한다. 검수자는 agent
지침 Read 를 위해 repo 접근만 유지하고, 채점자는 순수 텍스트 판정이라 도구가 0 필요하다.
이 테스트는 격리 계약이 run.sh 에서 회귀하지 않도록 박는다.
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN_SH = ROOT / "evals" / "run.sh"


class EvalHarnessIsolationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = RUN_SH.read_text(encoding="utf-8")

    def test_run_sh_exists(self):
        self.assertTrue(RUN_SH.is_file(), "evals/run.sh 가 있어야 한다")

    def test_both_claude_calls_use_neutral_cwd(self):
        # 검수자·채점자 두 claude -p 모두 CLAUDE.md 없는 중립 cwd 에서 실행해
        # auto-discovery / hook / skills 주입을 차단한다.
        count = self.src.count('cd "$neutral_cwd" && claude -p')
        self.assertEqual(
            count, 2,
            "검수자·채점자 두 claude -p 호출 모두 중립 cwd 를 써야 한다",
        )

    def test_reviewer_keeps_repo_access(self):
        # 검수자는 {{REPO_ROOT}}/docs/plugin/agents/... 를 Read 하므로 repo 접근 유지.
        self.assertIn('--add-dir "$ROOT"', self.src)

    def test_judge_removes_tools(self):
        # 채점자는 정답표+보고가 프롬프트에 인라인 — 도구 schema 주입 제거.
        self.assertIn('--allowedTools ""', self.src)

    def test_no_bare_flag(self):
        # --bare 는 구독 인증(OAuth/keychain)을 못 읽어 "Not logged in" — 실제 claude -p
        # 호출에서 금지한다. (주석의 설명 언급은 허용; 호출 라인만 검사)
        for line in self.src.splitlines():
            if line.lstrip().startswith("#"):
                continue
            if "claude -p" in line:
                self.assertNotIn("--bare", line, f"claude -p 호출에 --bare 금지: {line}")

    def test_neutral_cwd_created_and_cleaned(self):
        self.assertIn('neutral_cwd="$(mktemp -d', self.src)
        self.assertIn('rm -rf "$sandbox" "$neutral_cwd"', self.src)


if __name__ == "__main__":
    unittest.main()

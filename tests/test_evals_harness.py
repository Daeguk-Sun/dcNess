"""행동 eval 하네스 구조 계약 테스트.

evals/ 의 러너·케이스·정답표가 구조 계약(계약 수준 정답표 — agent 이름/지침 문구
미포함, 블라인드 prompt, placeholder)을 지키는지 회귀로 보존한다.
실제 LLM 실행은 하지 않는다 — 그건 `bash evals/run.sh` 의 영역이다.
"""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "evals"


class EvalsHarnessContractTests(unittest.TestCase):
    def test_runner_exists_and_parses(self) -> None:
        run_sh = EVALS / "run.sh"
        self.assertTrue(run_sh.is_file())
        result = subprocess.run(
            ["bash", "-n", str(run_sh)], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_every_case_has_required_files(self) -> None:
        case_dirs = sorted((EVALS / "cases").iterdir())
        self.assertGreaterEqual(len(case_dirs), 2)
        for case_dir in case_dirs:
            for name in ("prompt.md", "expected.md"):
                with self.subTest(case=case_dir.name, file=name):
                    self.assertTrue((case_dir / name).is_file())

    def test_prompts_use_placeholders_and_do_not_leak_expectations(self) -> None:
        for case_dir in sorted((EVALS / "cases").iterdir()):
            prompt = (case_dir / "prompt.md").read_text(encoding="utf-8")
            with self.subTest(case=case_dir.name):
                self.assertIn("{{REPO_ROOT}}", prompt)
                self.assertIn("{{CASE_DIR}}", prompt)
                # 블라인드 — 기대 결과(정답표 어휘)를 prompt 에 누설하지 않는다.
                for leak in ("MUST", "정답", "기대", "expected"):
                    self.assertNotIn(leak, prompt)

    def test_expected_files_stay_at_contract_level(self) -> None:
        """정답표는 계약 수준만 — agent 이름/지침 고유 문구에 묶이면 역할 개편 때 깨진다."""
        forbidden = (
            "product-acceptance",
            "architecture-validator",
            "module-architect",
            "system-architect",
            "SPEC_ACCEPTANCE",
            "SYSTEM_BOUNDARY",
            "TASK_LOCAL",
            "agents/",
            "skills/",
        )
        for case_dir in sorted((EVALS / "cases").iterdir()):
            expected = (case_dir / "expected.md").read_text(encoding="utf-8")
            with self.subTest(case=case_dir.name):
                self.assertRegex(expected, r"\[(MUST|MUST_NOT)\]")
                for token in forbidden:
                    self.assertNotIn(token, expected)

    def test_story_slice_case_pair_exists(self) -> None:
        partfirst = EVALS / "cases" / "story-slice-partfirst"
        skeleton = EVALS / "cases" / "story-slice-skeleton"
        for case_dir in (partfirst, skeleton):
            for name in ("prd.md", "stories.md"):
                with self.subTest(case=case_dir.name, file=name):
                    self.assertTrue((case_dir / name).is_file())
        self.assertIn(
            "[MUST]", (partfirst / "expected.md").read_text(encoding="utf-8")
        )
        self.assertIn(
            "[MUST_NOT]", (skeleton / "expected.md").read_text(encoding="utf-8")
        )

    def test_readme_documents_when_to_run_and_case_addition(self) -> None:
        readme = (EVALS / "README.md").read_text(encoding="utf-8")
        for needle in (
            "머지 전 1회",
            "플러그인 릴리즈 직전 1회",
            "CI 차단 게이트가 아니다",
            "계약 수준",
            "사고 1건 = 케이스 1개",
            "bash evals/run.sh",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, readme)

    def test_claude_md_recommends_eval_before_merge(self) -> None:
        claude_md = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("bash evals/run.sh", claude_md)
        self.assertIn("행동 eval (권고 — CI 차단 아님)", claude_md)


if __name__ == "__main__":
    unittest.main()

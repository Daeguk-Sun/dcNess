"""impl-validator 가 계획이 지정한 state owner 를 실제 클래스 구조와 대조하는 계약 회귀."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CLAUDE_VALIDATOR = "docs/plugin/agents/impl-validator/impl-validator-agent.md"
CODEX_VALIDATOR = "codex/skills/dcness-impl-validator/SKILL.md"
FINDING_CLASSES = "docs/plugin/agents/impl-validator/references/finding-classes.md"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class ValidatorStateOwnerContractTests(unittest.TestCase):
    def test_both_providers_cross_check_designated_state_owner(self) -> None:
        for relative in (CLAUDE_VALIDATOR, CODEX_VALIDATOR):
            text = read(relative)
            for needle in (
                "state owner 대조 고정 항목",
                "지정한 state owner",
                "public interface 이름",
                "실제 클래스 구조",
                "하나씩 대조",
                "지정에 없는 새 상태 소유 클래스",
                "동작이 맞아도",
            ):
                with self.subTest(file=relative, needle=needle):
                    self.assertIn(needle, text)

    def test_finding_classes_list_state_owner_drift_as_spec_gap(self) -> None:
        text = read(FINDING_CLASSES)
        spec_gap = text.split("## spec-gap", 1)[1].split("## quality-gap", 1)[0]

        self.assertIn("지정한 state owner", spec_gap)
        self.assertIn("지정에 없는 새 상태 소유 클래스", spec_gap)

    def test_behavior_eval_pair_exists(self) -> None:
        for case, marker in (
            ("state-owner-designated-bad", "[MUST]"),
            ("state-owner-designated-good", "[MUST_NOT]"),
        ):
            case_dir = ROOT / "evals" / "cases" / case
            with self.subTest(case=case):
                for name in ("prompt.md", "impl.md", "diff.md", "expected.md"):
                    self.assertTrue((case_dir / name).is_file(), name)
                self.assertIn(marker, (case_dir / "expected.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

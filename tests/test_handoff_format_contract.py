"""`/smart-compact` 와 `/handoff` 인계 형식 계약 (#1333).

인계 형식은 작업 경위 서술이 아니라 다음 세션이 바로 착수하는 데 필요한 사실을 담는다:
과제 원문(AC 원문은 명령 출력으로 붙임), 현재 하던 일과 다음 단계, 완료 판정 조건,
사용자 지시·선호, 포인터. 출력 형식을 검사·차단하지 않는 안내 문서이므로 항목 존재만 고정한다.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class HandoffFormatContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.smart_compact = (ROOT / "commands" / "smart-compact.md").read_text(
            encoding="utf-8"
        )
        self.handoff = (ROOT / "commands" / "handoff.md").read_text(encoding="utf-8")

    def test_smart_compact_format_sections(self) -> None:
        for section in (
            "# 과제 원문",
            "# 현재 하던 일과 다음 단계",
            "# 완료 판정 조건",
            "# 사용자 지시·선호",
            "# 포인터",
        ):
            self.assertIn(section, self.smart_compact, f"smart-compact 항목 누락: {section}")
        # 작업 경위(최근 PR 목록)는 필수 항목이 아니다
        self.assertNotIn("# 최근 진행", self.smart_compact)

    def test_handoff_format_sections_keep_short_principle(self) -> None:
        for section in (
            "## 과제 원문",
            "## 완료 판정 조건",
            "## 사용자 지시·선호",
        ):
            self.assertIn(section, self.handoff, f"handoff 항목 누락: {section}")
        self.assertIn("**단문 원칙**", self.handoff)
        self.assertIn("세션 전체 요약 덤프 금지", self.handoff)

    def test_both_formats_paste_ac_as_command_output(self) -> None:
        for name, text in (("smart-compact", self.smart_compact), ("handoff", self.handoff)):
            self.assertIn("gh issue view", text, f"{name}: AC 원문 명령 출력 안내 누락")
            self.assertIn("다시 쓰지 않는다", text, f"{name}: 모델 재작성 금지 안내 누락")


if __name__ == "__main__":
    unittest.main()

"""재실행 범위와 반복 중단을 agent 판단으로 정한다는 지침 계약 테스트."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHARED = "docs/plugin/agents/_shared/rerun-judgment.md"

NUMERIC_LIMIT = re.compile(r"(≤\s*\d|\d\s*cycle|cycle\s*≤)")


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class SharedCriteriaTests(unittest.TestCase):
    def test_shared_doc_states_the_four_scope_behaviours(self) -> None:
        text = read(SHARED)
        for needle in (
            "변경분을 읽고 고른다",
            "스스로 전체로 올린다",
            "다시 하지 않은 이유를 적는다",
            "기록이 없으면 전체로 한다",
            "호출자는 범위를 좁혀 처방하지 않고, 전체로 올리는 것도 막지 않는다",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)

    def test_shared_doc_states_the_stop_judgment_without_a_numeric_limit(self) -> None:
        text = read(SHARED)
        for needle in (
            "다시 실행하기 전에 답한다",
            "같은 신호가 다시 나오면 신호를 먼저 의심한다",
            "검사 도구의 오판, 실행 환경, 제품 결함 순서",
            "더 싼 관찰을 먼저 쓴다",
            "관찰 수단부터 보강한다",
            "새 정보가 없으면 멈춘다",
            "서로 다른 실패의 순차 노출은 진전이다",
            "분류만 바꿔 계속 재시도하지 않는다",
            "숫자 한도를 중단 조건으로 쓰지 않는다",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        self.assertIsNone(NUMERIC_LIMIT.search(text))

    def test_shared_doc_does_not_force_an_output_format(self) -> None:
        text = read(SHARED)
        self.assertIn("형식이 아니라 의미 요구", text)
        self.assertIn("문장 형식은 자유다", text)

    def test_shared_doc_keeps_the_hook_order_untouched(self) -> None:
        text = read(SHARED)
        self.assertIn("harness 가 강제하는 것은 순서", text)
        self.assertIn("검수 agent 는 새 커밋에서 계속 호출된다", text)


if __name__ == "__main__":
    unittest.main()

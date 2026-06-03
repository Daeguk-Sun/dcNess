"""test_sub_eval — 자율 친화 재설계 (#272 W1).

기존 anomaly 룰 (임계값 / prose-only 화이트리스트 / promised_write) 자체 제거 →
hook 은 *raw 측정 데이터* 만 inject. 메인 LLM 이 loop-procedure.md 의 표준 1 step 시퀀스 보고 자율 판단.

Coverage:
    format_histogram — raw 데이터 포맷 (자율 친화 inject 의 핵심)
    summarize_input_repeats — 같은 input 반복 카운트 (raw 신호)
    format_input_repeats — inject 한 줄 포맷
"""
from __future__ import annotations

import unittest

from harness.sub_eval import (
    format_histogram,
    format_input_repeats,
    summarize_input_repeats,
)


class FormatHistogramTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(format_histogram({}), "(none)")

    def test_normal(self):
        s = format_histogram({"Read": 4, "Bash": 2, "Write": 0})
        # sorted alphabetical
        self.assertEqual(s, "Bash:2 Read:4 Write:0")


class SummarizeInputRepeatsTests(unittest.TestCase):
    """같은 input 반복 — 메인 자율 판단용 raw 신호.

    *동일 파일* Read 5번 vs *다른 파일 5개* Read 5번 — 후자는 정상, 전자는 의심.
    임계 hardcode 안 함. 메인이 보고 알아서 판단.
    """

    def test_empty(self):
        self.assertEqual(summarize_input_repeats([]), [])

    def test_below_min_count_excluded(self):
        # min_count=2 default — 1번만 나온 input 은 noise
        entries = [
            {"phase": "pre", "input": "src/Foo.tsx"},
            {"phase": "pre", "input": "src/Bar.tsx"},
        ]
        self.assertEqual(summarize_input_repeats(entries), [])

    def test_repeated_input_counted(self):
        entries = [
            {"phase": "pre", "input": "src/Foo.tsx"},
            {"phase": "pre", "input": "src/Foo.tsx"},
            {"phase": "pre", "input": "src/Foo.tsx"},
            {"phase": "pre", "input": "src/Bar.tsx"},
        ]
        result = summarize_input_repeats(entries)
        self.assertEqual(result, [("src/Foo.tsx", 3)])

    def test_post_phase_excluded(self):
        # post entry 는 pre 와 짝 — 중복 카운트 회피
        entries = [
            {"phase": "pre", "input": "src/Foo.tsx"},
            {"phase": "post", "input": "src/Foo.tsx"},  # skip
            {"phase": "pre", "input": "src/Foo.tsx"},
        ]
        result = summarize_input_repeats(entries)
        self.assertEqual(result, [("src/Foo.tsx", 2)])

    def test_top_n_limit(self):
        entries = []
        for inp in ["a", "b", "c", "d"]:
            entries.extend([{"phase": "pre", "input": inp}] * 3)
        result = summarize_input_repeats(entries, top_n=2)
        self.assertEqual(len(result), 2)

    def test_descending_count_order(self):
        entries = (
            [{"phase": "pre", "input": "low"}] * 2
            + [{"phase": "pre", "input": "high"}] * 5
            + [{"phase": "pre", "input": "mid"}] * 3
        )
        result = summarize_input_repeats(entries)
        self.assertEqual([k for k, _ in result], ["high", "mid", "low"])


class FormatInputRepeatsTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(format_input_repeats([]), "")

    def test_one(self):
        self.assertEqual(format_input_repeats([("foo.py", 4)]), "foo.py ×4")

    def test_multiple(self):
        s = format_input_repeats([("a.py", 5), ("b.py", 3)])
        self.assertEqual(s, "a.py ×5, b.py ×3")


if __name__ == "__main__":
    unittest.main()

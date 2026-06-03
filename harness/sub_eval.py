"""sub_eval — sub 측정 데이터 (DCN-CHG-20260501-13, 자율 친화 재설계 #272).

PostToolUse Agent hook 가 sub 종료 시 trace 집계 → tool histogram + 같은 input
반복 카운트 → additionalContext inject. *결정 X — raw data 만*.

CLAUDE.md 의 dcness 강제 원칙 정합 (가이드레일만, 메인 LLM 자율 판단):
    - 임계값 hardcode X (Read 15 같은 우리 가정 쓰지 X)
    - "REDO_SUSPECT" 자동 결정 X (메인이 loop-procedure.md 의 표준 1 step 시퀀스 가이드 보고 자율)
    - 화이트리스트 / 약속-실측 검사 X (룰 쓸수록 자율 침해)

이전 (PR #274 시점) anomaly 룰 (임계 차등 / prose-only 화이트리스트 /
promised_write) 은 *결정을 hook 에 박는* 패턴이라 자율 영역 침해 — false positive
4/5 step 매번 메인이 echo 부담 (#272 W1 보고). 본 재설계는 hook 의 책임을
*가이드레일/측정* 으로 한정.

API 정합 — 기존 호출자 (`harness/hooks.py`) 는 raw measurement 만 사용.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple


__all__ = [
    "format_histogram",
    "format_input_repeats",
    "summarize_input_repeats",
]


def format_histogram(histogram: Dict[str, int]) -> str:
    """histogram → result-옆 inject 용 짧은 문자열.

    Returns:
        "Read:4 Bash:2 Write:0" 형식. 빈 dict → "(none)".
    """
    if not histogram:
        return "(none)"
    return " ".join(f"{tool}:{count}" for tool, count in sorted(histogram.items()))


def summarize_input_repeats(
    trace_entries: List[Dict[str, Any]],
    *,
    top_n: int = 3,
    min_count: int = 2,
) -> List[Tuple[str, int]]:
    """trace pre entry 의 `input` 필드 (file_path / command 요약) 반복 카운트.

    "같은 도구 N 반복" 만 봐선 정상 다중 파일 read 와 비정상 *동일 파일* 반복을
    구분 X. 같은 input 반복 = 의미 있는 신호 (raw data) — 메인이 보고 자율 판단.

    Args:
        trace_entries: agent_trace.read_all 결과 (또는 시각 범위 필터링된 subset).
        top_n: 반환 항목 수 상한.
        min_count: 이 카운트 미만은 제외 (signal-to-noise).

    Returns:
        [(input, count), ...] 카운트 내림차순. min_count 미만 제외, top_n 상한.
    """
    counts: Dict[str, int] = {}
    for entry in trace_entries:
        if entry.get("phase") != "pre":
            continue
        inp = str(entry.get("input", "") or "").strip()
        if not inp:
            continue
        counts[inp] = counts.get(inp, 0) + 1
    return sorted(
        ((k, v) for k, v in counts.items() if v >= min_count),
        key=lambda x: -x[1],
    )[:top_n]


def format_input_repeats(repeats: List[Tuple[str, int]]) -> str:
    """summarize_input_repeats 결과 → inject 용 한 줄. 빈 리스트 → ""."""
    if not repeats:
        return ""
    parts = [f"{inp} ×{n}" for inp, n in repeats]
    return ", ".join(parts)

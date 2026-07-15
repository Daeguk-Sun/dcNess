"""agent_trace — sub-agent 행동 사후 추적 trace (DCN-CHG-20260501-11).

PreToolUse / PostToolUse hook 에서 sub 내부 도구 호출마다 1줄 append.
저장 위치: `.sessions/{sid}/runs/{rid}/agent-trace.jsonl`.

cover (행동만):
    - 도구 호출 + 입력 (Pre)
    - 도구 결과 metadata (Post — exit code 등)

cover 안 함 (한계):
    - sub 의 thinking / 중간 assistant message (`.output` 가공 helper 별도)
    - 도구 0번 쓰는 sub turn (trace 텅 빔)

Schema (강제 X — 권장 필드):
    ts          (auto)  ISO8601 UTC, 미지정 시 자동 추가
    phase               "pre" | "post"
    agent_id            sub task id (메인 hook 발화 시 비어있을 수 있음)
    agent               subagent type (build-worker / module-architect / ...)
    tool                Edit / Write / Read / Bash / NotebookEdit
    input               (pre)  tool_input 의 핵심 (file_path / command 앞부분)
    exit                (post) exit code (Bash) 또는 0/1 (Edit/Write)
    stdout_size         (post) 결과 크기 (Bash)

규약:
    - jsonl, POSIX O_APPEND atomic (4096 bytes 이내)
    - read 시 malformed line skip
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from harness.session_state import run_dir


__all__ = [
    "append", "read_all", "tail", "histogram", "histogram_since",
    "last_agent_id", "TRACE_NAME",
]


TRACE_NAME = "agent-trace.jsonl"


def _trace_path(
    session_id: str, run_id: str, *, base_dir: Optional[Path] = None
) -> Path:
    return run_dir(session_id, run_id, base_dir=base_dir, create=True) / TRACE_NAME


def append(
    session_id: str,
    run_id: str,
    entry: Dict[str, Any],
    *,
    base_dir: Optional[Path] = None,
) -> None:
    """agent-trace.jsonl 에 1줄 append. ts 미지정 시 자동.

    POSIX O_APPEND atomic — 4096 bytes 이내 entry 동시 write 안전.
    """
    if not isinstance(entry, dict):
        raise TypeError(f"entry must be dict, got {type(entry).__name__}")
    if "ts" not in entry:
        entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **entry}
    line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
    target = _trace_path(session_id, run_id, base_dir=base_dir)
    fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def read_all(
    session_id: str,
    run_id: str,
    *,
    base_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """모든 entry 반환. 비존재 / 빈 → []. malformed skip."""
    target = _trace_path(session_id, run_id, base_dir=base_dir)
    if not target.exists():
        return []
    entries: List[Dict[str, Any]] = []
    with open(target, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def tail(
    session_id: str,
    run_id: str,
    n: int = 10,
    *,
    base_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """마지막 n entry."""
    if n <= 0:
        return []
    return read_all(session_id, run_id, base_dir=base_dir)[-n:]


def histogram(
    session_id: str,
    run_id: str,
    *,
    agent_id: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> Dict[str, int]:
    """tool 호출 종류별 카운트 (DCN-CHG-20260501-13).

    pre phase 만 카운트 (post 와 짝이라 중복 회피). agent_id 명시 시 해당 sub 만,
    None 이면 run 전체.

    Args:
        agent_id: 특정 sub 의 trace 만 집계. None = run 전체.

    Returns:
        {"Read": 4, "Bash": 2, "Write": 0, "Edit": 0} 등.
    """
    counts: Dict[str, int] = {}
    for entry in read_all(session_id, run_id, base_dir=base_dir):
        if entry.get("phase") != "pre":
            continue
        if agent_id is not None and entry.get("agent_id") != agent_id:
            continue
        tool = entry.get("tool", "") or "?"
        counts[tool] = counts.get(tool, 0) + 1
    return counts


def histogram_since(
    session_id: str,
    run_id: str,
    since_ts: str,
    *,
    agent: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> Dict[str, int]:
    """`since_ts` (ISO8601) *이후* pre phase 의 tool 카운트 (#272 W3 진짜 fix).

    PreToolUse Agent 시각 ~ PostToolUse Agent 시각 사이 trace = 그 sub 의 행동.
    `agent_id` 폴백 (직전 step 오기록 위험) 대신 *시각 범위* 로 정확히 매칭.

    issue #598 finding1 — `agent` 명시 시 시각 범위 *AND* `entry.agent == agent`
    로 좁힌다. file-op trace 가 payload self-attribution 으로 정확한 agent 를
    담으므로 (commit1), 동시 sub-agent 의 시각대 겹침에도 다른 sub 의 행동이
    histogram 에 섞이지 않는다. `agent` None 이면 시각 범위만 (기존 동작).

    Args:
        since_ts: ISO8601 UTC ("2026-05-08T01:23:45Z"). 이 시각 *이상* 의 entry 포함.
        agent: 지정 시 해당 agent 의 entry 만 카운트 (동시 sub 분리).

    Returns:
        {"Read": 4, ...}. since_ts 빈 문자열이면 빈 dict (안전 폴백 X — 호출자가
        시각 범위 보장).
    """
    if not since_ts:
        return {}
    counts: Dict[str, int] = {}
    for entry in read_all(session_id, run_id, base_dir=base_dir):
        if entry.get("phase") != "pre":
            continue
        ts = entry.get("ts", "") or ""
        if not ts or ts < since_ts:
            continue
        if agent and (entry.get("agent", "") or "") != agent:
            continue
        tool = entry.get("tool", "") or "?"
        counts[tool] = counts.get(tool, 0) + 1
    return counts


def last_agent_id(
    session_id: str,
    run_id: str,
    *,
    base_dir: Optional[Path] = None,
) -> str:
    """가장 마지막 entry 의 agent_id (DCN-CHG-20260501-13).

    PostToolUse Agent hook 발화 시점에 직전 sub 식별용. 빈 trace → "".
    """
    entries = read_all(session_id, run_id, base_dir=base_dir)
    for entry in reversed(entries):
        aid = entry.get("agent_id", "") or ""
        if aid:
            return aid
    return ""

#!/usr/bin/env python3
"""measure_main_turns.py — Claude Code 세션 JSONL 의 메인 assistant turn 분포 측정.

용도
----
`/impl-loop` Hybrid A 트랙 (#446) 의 메인 컨텍스트 누적 측정:
- 이전 multi-agent baseline: jajang 실측 ~280 turn/task (impl 1-task 세션 3개 평균)
- Hybrid A 목표: 메인 turn/task ~30 (~85-90% 감소). gate = Step 3 프로토타입.
- 동일 frozen 1-task baseline/variant 1+1에서 request/tool/wall-clock/token과
  제품 AC/MUST-FIX/regression/사람 개입을 함께 묶는 paired screening.
- 각 디렉터리에 같은 수의 JSONL을 두면 request→첫 Edit/Write 시간,
  첫 edit 전 main blocking request, main/전체 executor token, 정확성을 같은
  정의로 반복 비교한다. fresh executor edit는 parent tool event에서도 찾는다.

JSONL 위치: `~/.claude/projects/<project-id>/<session-id>.jsonl` (Claude Code 가 자동 기록).
한 줄 = 한 event. 메인 assistant turn = `type=assistant` + `message.role=assistant`.

분류
----
한 assistant turn 안 `message.content` list 의 block 들로 분류:
- `tool_use` block 1+ → **tool turn**
- `tool_use` 없고 `text` block 1+ → **text-only turn**
- `tool_use` 없고 `text` 없고 `thinking` block 1+ → **thinking-only turn**

Tool histogram 은 tool_use block 의 `name` 빈도. Agent 호출은 `name=Task` + `input.subagent_type`.

사용
----
    python3 scripts/measure_main_turns.py <jsonl-path>
    python3 scripts/measure_main_turns.py <jsonl-path> --json
    python3 scripts/measure_main_turns.py <directory>     # 모든 *.jsonl 일괄
    python3 scripts/measure_main_turns.py baseline.jsonl \
      --paired-with variant.jsonl --outcomes outcomes.json --json
    python3 scripts/measure_main_turns.py baseline-trials/ \
      --paired-with fresh-trials/ --outcomes repeated-outcomes.json --json
    python3 scripts/measure_main_turns.py <project-session-directory> \
      --flow-health --plugin-version 0.29.0 --json

예시 (jajang impl 1-task 세션 측정):
    python3 scripts/measure_main_turns.py \\
      ~/.claude/projects/-Users-dc-kim-project-jajang/<sid>.jsonl

#446 트랙 Step 3 gate: 메인 turn ≤ 50 → Step 4 진행 / 50-100 → 부분 성공 / >100 → 단념.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


_TOKEN_FIELDS = (
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "output_tokens",
)
_FLOW_COMMAND_PATTERN = re.compile(
    r"<command-name>\s*/?(?P<name>[^<\s]+)\s*</command-name>"
)
_FLOW_PLUGIN_VERSION_PATTERN = re.compile(
    r"/dcness/dcness/(?P<version>[^/]+)/skills/(?:impl|impl-loop)(?:/|\s|$)"
)
_FLOW_WORKER_LAUNCH_PATTERN = re.compile(
    r"""(?mx)
    ^\s*
    (?:
        ["']?\$(?:\{?[A-Z_][A-Z0-9_]*\}?)["']?
        |
        ["']?[^\s\n]*dcness-implementation-chain["']?
    )
    \s+build-worker(?:\s|\\|$)
    """
)
_FLOW_DEFAULT_COMMANDS = ("dcness:impl", "dcness:impl-loop")
_FLOW_EDIT_TOOLS = {"Edit", "Write", "NotebookEdit"}
_FLOW_MAX_FIRST_ACTION_SECONDS = 60.0
_FLOW_MAX_BLOCKING_REQUESTS = 2
_FLOW_MAX_PROGRESS_SILENCE_SECONDS = 60.0
_FLOW_MINIMUM_CONFIDENT_SAMPLES = 3
_FLOW_OPERATIONAL_PATHS = {".claude", ".dcness-work", ".git", ".metrics"}


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_direct_user_request(content: Any) -> bool:
    if isinstance(content, str):
        return True
    if not isinstance(content, list):
        return False
    has_text = any(
        isinstance(block, dict) and block.get("type") == "text"
        for block in content
    )
    has_tool_result = any(
        isinstance(block, dict) and block.get("type") == "tool_result"
        for block in content
    )
    return has_text and not has_tool_result


def _update_token_max(target: dict[str, Any], usage: Any) -> None:
    if not isinstance(usage, dict):
        return
    for field in _TOKEN_FIELDS:
        target[field] = max(target[field], int(usage.get(field) or 0))


def _result_observation(
    event: dict[str, Any],
    line_number: int,
    result_usage: dict[str, Any],
    result_duration_seconds: float | None,
    result_line_number: int | None,
) -> tuple[dict[str, Any], float | None, int | None]:
    usage = event.get("usage")
    if isinstance(usage, dict):
        result_usage = usage
    duration_ms = event.get("duration_ms")
    if isinstance(duration_ms, (int, float)) and duration_ms >= 0:
        duration_seconds = float(duration_ms) / 1000
        if (
            result_duration_seconds is None
            or duration_seconds > result_duration_seconds
        ):
            result_duration_seconds = duration_seconds
            result_line_number = line_number
    return result_usage, result_duration_seconds, result_line_number


def _first_edit_observation(
    content: list[Any],
    timestamp: datetime | None,
    line_number: int,
    parent_tool_use_id: Any,
) -> dict[str, Any] | None:
    if timestamp is None:
        return None
    for block in content:
        if (
            isinstance(block, dict)
            and block.get("type") == "tool_use"
            and block.get("name") in {"Edit", "Write", "NotebookEdit"}
        ):
            tool_input = block.get("input") or {}
            return {
                "timestamp": timestamp.isoformat(),
                "line": line_number,
                "tool": block.get("name"),
                "path": tool_input.get("file_path") or tool_input.get("path") or "",
                "executor": (
                    "main" if parent_tool_use_id in (None, "") else "fresh"
                ),
            }
    return None


def _event_text(event: dict[str, Any]) -> str:
    content = (event.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        str(block.get("text") or "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


def _normalize_flow_command(value: str) -> str:
    command = value.strip().lstrip("/")
    if command in {"impl", "impl-loop"}:
        return f"dcness:{command}"
    return command


def _flow_command(event: dict[str, Any]) -> str | None:
    if event.get("type") != "user":
        return None
    match = _FLOW_COMMAND_PATTERN.search(_event_text(event))
    if match is None:
        return None
    return _normalize_flow_command(match.group("name"))


def _load_timed_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open() as source:
        for line_number, line in enumerate(source, start=1):
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue
            event = dict(raw)
            event["_line"] = line_number
            event["_at"] = _parse_timestamp(raw.get("timestamp"))
            events.append(event)
    return events


def _assistant_content(event: dict[str, Any]) -> list[Any]:
    if event.get("type") != "assistant":
        return []
    message = event.get("message") or {}
    if message.get("role") != "assistant":
        return []
    content = message.get("content")
    return content if isinstance(content, list) else []


def _is_root_assistant_event(event: dict[str, Any]) -> bool:
    return (
        bool(_assistant_content(event))
        and event.get("parent_tool_use_id") in (None, "")
    )


def _assistant_request_key(event: dict[str, Any]) -> str:
    message = event.get("message") or {}
    return str(
        event.get("request_id")
        or message.get("id")
        or event.get("uuid")
        or f"line-{event['_line']}"
    )


def _is_implementation_path(path_value: Any, cwd_value: Any) -> bool:
    if not isinstance(path_value, str) or not path_value:
        return True
    path = Path(path_value)
    if not path.is_absolute():
        relative = path
    elif isinstance(cwd_value, str) and cwd_value:
        try:
            relative = path.relative_to(Path(cwd_value))
        except ValueError:
            return False
    else:
        return False
    return not relative.parts or relative.parts[0] not in _FLOW_OPERATIONAL_PATHS


def _flow_edit_observation(
    event: dict[str, Any],
    project_root: Any = None,
) -> dict[str, Any] | None:
    timestamp = event.get("_at")
    if not isinstance(timestamp, datetime):
        return None
    for block in _assistant_content(event):
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        if block.get("name") not in _FLOW_EDIT_TOOLS:
            continue
        tool_input = block.get("input") or {}
        path = tool_input.get("file_path") or tool_input.get("path") or ""
        if not _is_implementation_path(
            path,
            event.get("cwd") or project_root,
        ):
            continue
        return {
            "timestamp": timestamp.isoformat(),
            "line": event["_line"],
            "tool": block.get("name"),
            "path": path,
            "executor": (
                "main"
                if event.get("parent_tool_use_id") in (None, "")
                else "fresh"
            ),
        }
    return None


def _flow_worker_observation(
    event: dict[str, Any],
) -> dict[str, Any] | None:
    timestamp = event.get("_at")
    if not isinstance(timestamp, datetime):
        return None
    for block in _assistant_content(event):
        if (
            not isinstance(block, dict)
            or block.get("type") != "tool_use"
            or block.get("name") != "Bash"
        ):
            continue
        command = str((block.get("input") or {}).get("command") or "")
        if (
            "dcness-implementation-chain" not in command
            or _FLOW_WORKER_LAUNCH_PATTERN.search(command) is None
        ):
            continue
        return {
            "timestamp": timestamp.isoformat(),
            "line": event["_line"],
            "tool": "WorkerLaunch",
            "path": "",
            "executor": "headless",
        }
    return None


def _tool_result_ids(event: dict[str, Any]) -> list[str]:
    if event.get("type") != "user":
        return []
    content = (event.get("message") or {}).get("content")
    if not isinstance(content, list):
        return []
    return [
        str(block["tool_use_id"])
        for block in content
        if (
            isinstance(block, dict)
            and block.get("type") == "tool_result"
            and block.get("tool_use_id")
        )
    ]


def _merged_interval_seconds(
    intervals: list[tuple[datetime, datetime]],
) -> float:
    if not intervals:
        return 0.0
    merged: list[list[datetime]] = []
    for start, end in sorted(intervals):
        if end < start:
            continue
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return sum((end - start).total_seconds() for start, end in merged)


def _pre_action_tool_observations(
    events: list[dict[str, Any]],
    start_at: datetime,
    stop_at: datetime,
) -> tuple[float, list[dict[str, Any]]]:
    calls: dict[str, tuple[datetime, int]] = {}
    intervals: list[tuple[datetime, datetime]] = []
    results: list[dict[str, Any]] = []
    for event in events:
        timestamp = event.get("_at")
        if not isinstance(timestamp, datetime):
            continue
        for block in _assistant_content(event):
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            tool_id = block.get("id")
            if tool_id and start_at <= timestamp < stop_at:
                calls[str(tool_id)] = (timestamp, int(event["_line"]))
        if not start_at <= timestamp < stop_at:
            continue
        for tool_id in _tool_result_ids(event):
            call = calls.get(tool_id)
            if call is None:
                continue
            call_at, call_line = call
            intervals.append((call_at, timestamp))
            results.append(
                {
                    "timestamp": timestamp,
                    "line": event["_line"],
                    "tool_use_line": call_line,
                }
            )
    return _merged_interval_seconds(intervals), results


def _has_visible_progress(event: dict[str, Any]) -> bool:
    if not _is_root_assistant_event(event):
        return False
    for block in _assistant_content(event):
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use":
            return True
        if block.get("type") == "text" and str(block.get("text") or "").strip():
            return True
    return False


def _next_visible_progress(
    events: list[dict[str, Any]],
    after: datetime,
    stop_at: datetime,
) -> dict[str, Any] | None:
    for event in events:
        timestamp = event.get("_at")
        if (
            isinstance(timestamp, datetime)
            and after < timestamp <= stop_at
            and _has_visible_progress(event)
        ):
            return event
    return None


def _progress_activity_evidence(
    events: list[dict[str, Any]],
    progress: dict[str, Any],
) -> dict[str, Any]:
    request_key = _assistant_request_key(progress)
    has_thinking = False
    output_tokens = 0
    for event in events:
        event_at = event.get("_at")
        if (
            not _is_root_assistant_event(event)
            or _assistant_request_key(event) != request_key
            or not isinstance(event_at, datetime)
            or event_at > progress["_at"]
        ):
            continue
        has_thinking = has_thinking or any(
            isinstance(block, dict) and block.get("type") == "thinking"
            for block in _assistant_content(event)
        )
        message = event.get("message") or {}
        usage = message.get("usage") or event.get("usage") or {}
        if isinstance(usage, dict):
            output_tokens = max(
                output_tokens,
                int(usage.get("output_tokens") or 0),
            )
    return {
        "next_progress_has_thinking": has_thinking,
        "next_progress_output_tokens": output_tokens,
    }


def _flow_silence_observations(
    events: list[dict[str, Any]],
    start_at: datetime,
    stop_at: datetime,
    tool_results: list[dict[str, Any]],
) -> tuple[
    float | None,
    dict[str, Any] | None,
    float | None,
    list[dict[str, Any]],
]:
    first_progress = _next_visible_progress(events, start_at, stop_at)
    time_to_first_progress = None
    long_silences: list[dict[str, Any]] = []
    if first_progress is not None:
        time_to_first_progress = (
            first_progress["_at"] - start_at
        ).total_seconds()
        if time_to_first_progress >= _FLOW_MAX_PROGRESS_SILENCE_SECONDS:
            long_silences.append(
                {
                    "source": "command_start",
                    "seconds": time_to_first_progress,
                    "next_progress_line": first_progress["_line"],
                    "next_progress_timestamp": first_progress["_at"].isoformat(),
                    **_progress_activity_evidence(events, first_progress),
                }
            )

    longest_seconds: float | None = None
    longest_evidence: dict[str, Any] | None = None
    for result in tool_results:
        progress = _next_visible_progress(events, result["timestamp"], stop_at)
        if progress is None:
            continue
        seconds = (progress["_at"] - result["timestamp"]).total_seconds()
        evidence = {
            "source": "tool_result",
            "seconds": seconds,
            "tool_result_line": result["line"],
            "tool_result_timestamp": result["timestamp"].isoformat(),
            "next_progress_line": progress["_line"],
            "next_progress_timestamp": progress["_at"].isoformat(),
            **_progress_activity_evidence(events, progress),
        }
        if longest_seconds is None or seconds > longest_seconds:
            longest_seconds = seconds
            longest_evidence = evidence
        if seconds >= _FLOW_MAX_PROGRESS_SILENCE_SECONDS:
            long_silences.append(evidence)
    return (
        time_to_first_progress,
        longest_evidence,
        longest_seconds,
        long_silences,
    )


def _flow_plugin_version(events: list[dict[str, Any]]) -> str | None:
    for event in events:
        match = _FLOW_PLUGIN_VERSION_PATTERN.search(_event_text(event))
        if match is not None:
            return match.group("version")
    return None


def _flow_invocation(
    path: Path,
    command: str,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    start_event = events[0]
    start_at = start_event.get("_at")
    if not isinstance(start_at, datetime):
        raise ValueError("flow command timestamp is required")
    timed_events = [
        event for event in events if isinstance(event.get("_at"), datetime)
    ]
    observed_end_at = max(
        (event["_at"] for event in timed_events),
        default=start_at,
    )
    first_action: dict[str, Any] | None = None
    first_action_event: dict[str, Any] | None = None
    for event in events[1:]:
        first_action = _flow_edit_observation(event, start_event.get("cwd"))
        if first_action is None:
            first_action = _flow_worker_observation(event)
        if first_action is not None:
            first_action_event = event
            break
    stop_at = (
        first_action_event["_at"]
        if first_action_event is not None
        else observed_end_at
    )
    elapsed_seconds = max((stop_at - start_at).total_seconds(), 0.0)
    last_user_input_at = max(
        (
            event["_at"]
            for event in events[1:]
            if (
                isinstance(event.get("_at"), datetime)
                and event["_at"] < stop_at
                and event.get("type") == "user"
                and event.get("parent_tool_use_id") in (None, "")
                and event.get("isMeta") is not True
                and event.get("isSynthetic") is not True
                and _flow_command(event) is None
                and _is_direct_user_request(
                    (event.get("message") or {}).get("content")
                )
            )
        ),
        default=None,
    )
    first_action_request_key = (
        _assistant_request_key(first_action_event)
        if first_action_event is not None
        and _is_root_assistant_event(first_action_event)
        else None
    )
    request_first_seen: dict[str, datetime] = {}
    for event in events:
        timestamp = event.get("_at")
        if (
            not isinstance(timestamp, datetime)
            or timestamp < start_at
            or timestamp >= stop_at
            or not _is_root_assistant_event(event)
        ):
            continue
        request_first_seen.setdefault(_assistant_request_key(event), timestamp)
    blocking_requests = sum(
        request_key != first_action_request_key
        for request_key in request_first_seen
    )
    tool_seconds, tool_results = _pre_action_tool_observations(
        events,
        start_at,
        stop_at,
    )
    (
        time_to_first_progress,
        longest_silence_evidence,
        longest_silence_seconds,
        long_silence_evidence,
    ) = _flow_silence_observations(
        events,
        start_at,
        stop_at,
        tool_results,
    )
    non_tool_elapsed_ratio = (
        max(elapsed_seconds - tool_seconds, 0.0) / elapsed_seconds
        if elapsed_seconds
        else None
    )
    failure_reasons: list[str] = []
    if elapsed_seconds >= _FLOW_MAX_FIRST_ACTION_SECONDS:
        failure_reasons.append("time_to_first_action")
    if blocking_requests > _FLOW_MAX_BLOCKING_REQUESTS:
        failure_reasons.append("blocking_assistant_requests")
    if first_action is not None:
        result = "FAIL" if failure_reasons else "PASS"
    else:
        result = "FAIL" if failure_reasons else "INCOMPLETE"
    return {
        "session": path.name,
        "command": command,
        "plugin_version": _flow_plugin_version(events),
        "result": result,
        "failure_reasons": failure_reasons,
        "startup_target": (
            "headless_worker_launch"
            if first_action is not None
            and first_action["tool"] == "WorkerLaunch"
            else "implementation_edit"
        ),
        "time_to_first_action_seconds": (
            round(elapsed_seconds, 3) if first_action is not None else None
        ),
        "last_user_input_to_first_action_seconds": (
            round((stop_at - last_user_input_at).total_seconds(), 3)
            if first_action is not None and last_user_input_at is not None
            else None
        ),
        "time_to_first_edit_seconds": (
            round(elapsed_seconds, 3)
            if first_action is not None
            and first_action["tool"] != "WorkerLaunch"
            else None
        ),
        "observed_without_action_seconds": (
            round(elapsed_seconds, 3) if first_action is None else None
        ),
        "blocking_assistant_requests_before_first_action": blocking_requests,
        "pre_action_tool_execution_seconds": round(tool_seconds, 3),
        "pre_action_non_tool_elapsed_ratio": (
            round(non_tool_elapsed_ratio, 6)
            if non_tool_elapsed_ratio is not None
            else None
        ),
        "time_to_first_progress_seconds": (
            round(time_to_first_progress, 3)
            if time_to_first_progress is not None
            else None
        ),
        "max_post_tool_silence_seconds": (
            round(longest_silence_seconds, 3)
            if longest_silence_seconds is not None
            else None
        ),
        "max_post_tool_silence_evidence": longest_silence_evidence,
        "long_silence_count": len(long_silence_evidence),
        "reasoning_observed_long_silence_count": sum(
            bool(evidence["next_progress_has_thinking"])
            for evidence in long_silence_evidence
        ),
        "long_silence_evidence": long_silence_evidence,
        "start_evidence": {
            "timestamp": start_at.isoformat(),
            "line": start_event["_line"],
            "kind": "command_invocation",
        },
        "first_action_evidence": first_action,
        "first_edit_evidence": (
            first_action
            if first_action is not None
            and first_action["tool"] != "WorkerLaunch"
            else None
        ),
    }


def parse_flow_invocations(
    path: Path,
    command_names: tuple[str, ...] | list[str] | None = None,
) -> list[dict[str, Any]]:
    """Measure each selected /impl command inside a session independently."""
    selected = {
        _normalize_flow_command(value)
        for value in (command_names or _FLOW_DEFAULT_COMMANDS)
    }
    events = _load_timed_events(path)
    command_indexes = [
        (index, command)
        for index, event in enumerate(events)
        if (command := _flow_command(event)) is not None
    ]
    rows: list[dict[str, Any]] = []
    for position, (start_index, command) in enumerate(command_indexes):
        if command not in selected:
            continue
        end_index = (
            command_indexes[position + 1][0]
            if position + 1 < len(command_indexes)
            else len(events)
        )
        window = events[start_index:end_index]
        if isinstance(window[0].get("_at"), datetime):
            rows.append(_flow_invocation(path, command, window))
    return rows


def build_flow_health(
    paths: list[Path],
    *,
    command_names: tuple[str, ...] | list[str] | None = None,
    plugin_version: str | None = None,
) -> dict[str, Any]:
    """Aggregate command traces without conflating speed, visibility, and activity."""
    observed = [
        row
        for path in paths
        for row in parse_flow_invocations(path, command_names)
    ]
    if plugin_version is None:
        invocations = observed
        excluded_version_count = 0
    else:
        invocations = [
            row for row in observed if row["plugin_version"] == plugin_version
        ]
        excluded_version_count = len(observed) - len(invocations)
    evaluated = [
        row for row in invocations if row["result"] in {"PASS", "FAIL"}
    ]
    pass_count = sum(row["result"] == "PASS" for row in evaluated)
    fail_count = sum(row["result"] == "FAIL" for row in evaluated)
    if fail_count:
        startup_status = "MISS"
    elif pass_count >= _FLOW_MINIMUM_CONFIDENT_SAMPLES:
        startup_status = "PASS"
    else:
        startup_status = "UNVERIFIED"

    visibility_evaluated = [
        row
        for row in evaluated
        if row["time_to_first_progress_seconds"] is not None
    ]
    visibility_degraded_count = sum(
        (
            row["time_to_first_progress_seconds"]
            >= _FLOW_MAX_PROGRESS_SILENCE_SECONDS
            or (
                row["max_post_tool_silence_seconds"] is not None
                and row["max_post_tool_silence_seconds"]
                >= _FLOW_MAX_PROGRESS_SILENCE_SECONDS
            )
        )
        for row in visibility_evaluated
    )
    if visibility_degraded_count:
        visibility_status = "DEGRADED"
    elif len(visibility_evaluated) >= _FLOW_MINIMUM_CONFIDENT_SAMPLES:
        visibility_status = "CLEAR"
    else:
        visibility_status = "UNVERIFIED"

    long_silences = [
        evidence
        for row in visibility_evaluated
        for evidence in row["long_silence_evidence"]
    ]
    reasoning_observed_count = sum(
        bool(evidence["next_progress_has_thinking"])
        for evidence in long_silences
    )
    unattributed_count = len(long_silences) - reasoning_observed_count
    if not visibility_evaluated:
        activity_status = "UNVERIFIED"
    elif not long_silences:
        activity_status = "NO_LONG_SILENCE_OBSERVED"
    elif unattributed_count:
        activity_status = "UNATTRIBUTED_WAIT_OBSERVED"
    else:
        activity_status = "ACTIVE_REASONING_OBSERVED"

    return {
        "plugin_version": plugin_version,
        "sample_count": len(evaluated),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "incomplete_count": sum(
            row["result"] == "INCOMPLETE" for row in invocations
        ),
        "excluded_version_count": excluded_version_count,
        "startup_slo": {
            "status": startup_status,
            "sample_count": len(evaluated),
            "pass_count": pass_count,
            "miss_count": fail_count,
        },
        "flow_visibility": {
            "status": visibility_status,
            "sample_count": len(visibility_evaluated),
            "clear_count": (
                len(visibility_evaluated) - visibility_degraded_count
            ),
            "degraded_count": visibility_degraded_count,
        },
        "agent_activity": {
            "status": activity_status,
            "long_silence_count": len(long_silences),
            "reasoning_observed_count": reasoning_observed_count,
            "unattributed_count": unattributed_count,
        },
        "relative_speed": {
            "status": "UNPROVEN",
            "basis": (
                "Command-scoped Flow Health has no matched baseline. Relative "
                "speed requires repeated same-fixture, same-runtime paired "
                "trials with non-regressed quality."
            ),
        },
        "thresholds": {
            "time_to_first_action_seconds": "<60",
            "blocking_assistant_requests_before_first_action": "<=2",
            "time_to_first_progress_seconds": "<60",
            "max_post_tool_silence_seconds": "<60",
            "minimum_confident_samples": _FLOW_MINIMUM_CONFIDENT_SAMPLES,
        },
        "invocations": invocations,
        "claim_boundary": (
            "Current-version external command traces only. Startup SLO and "
            "visibility are separate absolute observations. Thinking blocks "
            "prove model activity, not productivity. Relative speed remains "
            "UNPROVEN without matched repeated trials."
        ),
    }


def parse_session(path: Path) -> dict:
    """JSONL 한 파일 분석. 결과 dict 반환."""
    requests: dict[str, dict[str, Any]] = {}
    all_requests: dict[str, dict[str, int]] = {}
    tool_hist: collections.Counter = collections.Counter()
    agent_invocations: list[str] = []
    seen_tool_uses: set[str] = set()
    timestamps: list[datetime] = []
    first_timestamp_line: int | None = None
    models: set[str] = set()
    effort_levels: set[str] = set()
    providers: set[str] = set()
    result_duration_seconds: float | None = None
    result_usage: dict[str, Any] = {}
    result_line_number: int | None = None
    start_evidence: dict[str, Any] | None = None
    first_edit_evidence: dict[str, Any] | None = None
    first_edit_request_key: str | None = None
    request_first_seen: dict[str, datetime] = {}

    with path.open() as f:
        for line_number, line in enumerate(f, start=1):
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            timestamp = _parse_timestamp(d.get("timestamp"))
            if timestamp is not None:
                if not timestamps:
                    first_timestamp_line = line_number
                timestamps.append(timestamp)
            message = d.get("message") or {}
            user_content = message.get("content")
            if (
                start_evidence is None
                and d.get("type") == "user"
                and d.get("parent_tool_use_id") in (None, "")
                and timestamp is not None
                and _is_direct_user_request(user_content)
                and d.get("isSynthetic") is not True
            ):
                start_evidence = {
                    "timestamp": timestamp.isoformat(),
                    "line": line_number,
                    "kind": "root_user_request",
                }
            if d.get("type") == "result":
                (
                    result_usage,
                    result_duration_seconds,
                    result_line_number,
                ) = _result_observation(
                    d,
                    line_number,
                    result_usage,
                    result_duration_seconds,
                    result_line_number,
                )
                continue
            if d.get("type") != "assistant":
                continue
            msg = d.get("message") or {}
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content")
            if not isinstance(content, list):
                continue

            request_key = d.get("request_id") or msg.get("id") or f"line-{line_number}"
            parent_tool_use_id = d.get("parent_tool_use_id")
            all_request_key = f"{parent_tool_use_id or 'root'}:{request_key}"
            all_request = all_requests.setdefault(
                all_request_key,
                {
                    "input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "output_tokens": 0,
                },
            )
            usage = msg.get("usage") or d.get("usage") or {}
            _update_token_max(all_request, usage)

            if first_edit_evidence is None:
                first_edit_evidence = _first_edit_observation(
                    content,
                    timestamp,
                    line_number,
                    parent_tool_use_id,
                )
                if first_edit_evidence is not None:
                    first_edit_request_key = str(request_key)

            # stream-json forwards fresh-executor assistant events with their parent
            # Agent tool id. Their edit/token evidence is end-to-end, but they are
            # not counted as main assistant requests.
            if parent_tool_use_id not in (None, ""):
                continue
            if timestamp is not None:
                request_first_seen.setdefault(str(request_key), timestamp)
            request = requests.setdefault(
                str(request_key),
                {
                    "has_tool": False,
                    "has_text": False,
                    "has_thinking": False,
                    "input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "output_tokens": 0,
                },
            )
            _update_token_max(request, usage)
            model = msg.get("model") or d.get("model")
            if isinstance(model, str) and model:
                models.add(model)
            effort = d.get("effort") or msg.get("effort")
            if isinstance(effort, dict):
                effort = effort.get("level")
            if isinstance(effort, str) and effort:
                effort_levels.add(effort)
            provider = d.get("provider") or msg.get("provider")
            if isinstance(provider, str) and provider:
                providers.add(provider)

            for blk in content:
                if not isinstance(blk, dict):
                    continue
                bt = blk.get("type")
                if bt == "tool_use":
                    request["has_tool"] = True
                    tool_use_id = blk.get("id") or f"{request_key}:{len(seen_tool_uses)}"
                    if tool_use_id in seen_tool_uses:
                        continue
                    seen_tool_uses.add(str(tool_use_id))
                    name = blk.get("name", "?")
                    tool_hist[name] += 1
                    if name in {"Agent", "Task"}:
                        inp = blk.get("input") or {}
                        agent_invocations.append(inp.get("subagent_type", "?"))
                elif bt == "text":
                    request["has_text"] = True
                elif bt == "thinking":
                    request["has_thinking"] = True

    total = len(requests)
    tool_turns = sum(bool(row["has_tool"]) for row in requests.values())
    text_only_turns = sum(
        not row["has_tool"] and bool(row["has_text"])
        for row in requests.values()
    )
    thinking_only_turns = sum(
        not row["has_tool"] and not row["has_text"] and bool(row["has_thinking"])
        for row in requests.values()
    )
    input_tokens = sum(row["input_tokens"] for row in requests.values())
    cache_creation_input_tokens = sum(
        row["cache_creation_input_tokens"] for row in requests.values()
    )
    cache_read_input_tokens = sum(
        row["cache_read_input_tokens"] for row in requests.values()
    )
    output_tokens = sum(row["output_tokens"] for row in requests.values())
    total_input_tokens = (
        input_tokens + cache_creation_input_tokens + cache_read_input_tokens
    )
    all_input_tokens = sum(row["input_tokens"] for row in all_requests.values())
    all_cache_creation_input_tokens = sum(
        row["cache_creation_input_tokens"] for row in all_requests.values()
    )
    all_cache_read_input_tokens = sum(
        row["cache_read_input_tokens"] for row in all_requests.values()
    )
    all_total_input_tokens = (
        all_input_tokens
        + all_cache_creation_input_tokens
        + all_cache_read_input_tokens
    )
    all_output_tokens = sum(row["output_tokens"] for row in all_requests.values())
    if result_usage:
        result_total_input = sum(
            int(result_usage.get(field) or 0)
            for field in (
                "input_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
            )
        )
        all_total_input_tokens = max(all_total_input_tokens, result_total_input)
        all_output_tokens = max(
            all_output_tokens,
            int(result_usage.get("output_tokens") or 0),
        )
    if (
        start_evidence is None
        and result_duration_seconds is not None
        and timestamps
    ):
        derived = max(timestamps) - timedelta(seconds=result_duration_seconds)
        earliest = min(timestamps)
        fallback_start = min(derived, earliest)
        start_evidence = {
            "timestamp": fallback_start.isoformat(),
            "line": (
                result_line_number
                if fallback_start == derived
                else first_timestamp_line
            ),
            "kind": (
                "result_duration_derived_process_start"
                if fallback_start == derived
                else "earliest_timed_event"
            ),
        }
    time_to_first_edit_seconds: float | None = None
    blocking_assistant_requests_before_first_edit: int | None = None
    if start_evidence is not None and first_edit_evidence is not None:
        parsed_start = _parse_timestamp(start_evidence["timestamp"])
        edit_at = _parse_timestamp(first_edit_evidence["timestamp"])
        if (
            parsed_start is not None
            and edit_at is not None
            and edit_at >= parsed_start
        ):
            time_to_first_edit_seconds = (edit_at - parsed_start).total_seconds()
            blocking_assistant_requests_before_first_edit = sum(
                request_key != first_edit_request_key
                and parsed_start <= request_at < edit_at
                for request_key, request_at in request_first_seen.items()
            )
    observed_wall_clock = (
        max((max(timestamps) - min(timestamps)).total_seconds(), 0.0)
        if timestamps
        else 0.0
    )
    wall_clock = max(result_duration_seconds or 0.0, observed_wall_clock)
    return {
        "session": path.name,
        "path": str(path),
        "main_assistant_requests": total,
        "tool_calls": len(seen_tool_uses),
        "wall_clock_seconds": wall_clock,
        "input_tokens": input_tokens,
        "cache_creation_input_tokens": cache_creation_input_tokens,
        "cache_read_input_tokens": cache_read_input_tokens,
        "total_input_tokens": total_input_tokens,
        "output_tokens": output_tokens,
        "all_total_input_tokens": all_total_input_tokens,
        "all_output_tokens": all_output_tokens,
        "time_to_first_edit_seconds": time_to_first_edit_seconds,
        "blocking_assistant_requests_before_first_edit": (
            blocking_assistant_requests_before_first_edit
        ),
        "start_evidence": start_evidence,
        "first_edit_evidence": first_edit_evidence,
        "models": sorted(models),
        "effort_levels": sorted(effort_levels),
        "providers": sorted(providers),
        "total_turns": total,
        "tool_turns": tool_turns,
        "text_only_turns": text_only_turns,
        "thinking_only_turns": thinking_only_turns,
        "tool_histogram": dict(tool_hist.most_common()),
        "agent_total": len(agent_invocations),
        "agent_invocations": collections.Counter(agent_invocations).most_common(),
    }


_QUALITY_FIELDS = (
    "product_ac",
    "must_fix_count",
    "regression_count",
    "human_intervention_count",
)
_RUNTIME_FIELDS = ("model", "effort", "provider")


def _validated_trial_outcome(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} trial outcome must be an object")
    for field in _QUALITY_FIELDS:
        if field not in value:
            raise ValueError(f"{label}.{field} is required")
    product_ac = value["product_ac"]
    if not isinstance(product_ac, dict) or not all(
        isinstance(product_ac.get(key), int) for key in ("passed", "total")
    ):
        raise ValueError(f"{label}.product_ac requires integer passed/total")
    if product_ac["passed"] < 0 or product_ac["total"] < product_ac["passed"]:
        raise ValueError(f"{label}.product_ac is invalid")
    for field in _QUALITY_FIELDS[1:]:
        if not isinstance(value[field], int) or value[field] < 0:
            raise ValueError(f"{label}.{field} must be a non-negative integer")
    runtime = value.get("runtime")
    if not isinstance(runtime, dict) or not all(
        isinstance(runtime.get(field), str) and runtime[field]
        for field in _RUNTIME_FIELDS
    ):
        raise ValueError(
            f"{label}.runtime requires non-empty model/effort/provider strings"
        )
    return dict(value)


def build_paired_screening(
    baseline: dict[str, Any],
    variant: dict[str, Any],
    outcomes: dict[str, Any],
) -> dict[str, Any]:
    """Join one baseline + one variant trace with the same frozen task quality axes."""
    if not isinstance(outcomes, dict):
        raise ValueError("outcomes must be an object")
    fixture = outcomes.get("fixture")
    if (
        not isinstance(fixture, dict)
        or not fixture.get("id")
        or not isinstance(fixture.get("sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", fixture["sha256"])
    ):
        raise ValueError("fixture.id and fixture.sha256 are required")
    trials = outcomes.get("trials")
    if not isinstance(trials, dict):
        raise ValueError("trials must be an object")
    joined: list[dict[str, Any]] = []
    for label, metrics in (("baseline", baseline), ("variant", variant)):
        quality = _validated_trial_outcome(trials.get(label), label)
        joined.append({"variant": label, **metrics, **quality})

    quality_regressed = (
        joined[1]["product_ac"]["total"] != joined[0]["product_ac"]["total"]
        or joined[1]["product_ac"]["passed"] < joined[0]["product_ac"]["passed"]
        or joined[1]["must_fix_count"] > joined[0]["must_fix_count"]
        or joined[1]["regression_count"] > joined[0]["regression_count"]
        or joined[1]["human_intervention_count"]
        > joined[0]["human_intervention_count"]
    )
    metric_names = (
        "main_assistant_requests",
        "tool_calls",
        "wall_clock_seconds",
        "time_to_first_edit_seconds",
        "blocking_assistant_requests_before_first_edit",
        "input_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "total_input_tokens",
        "output_tokens",
        "all_total_input_tokens",
        "all_output_tokens",
    )
    delta = {
        name: round(
            float(variant.get(name) or 0) - float(baseline.get(name) or 0), 6
        )
        for name in metric_names
    }
    for name in (
        "main_assistant_requests",
        "tool_calls",
        "input_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "total_input_tokens",
        "output_tokens",
        "blocking_assistant_requests_before_first_edit",
        "all_total_input_tokens",
        "all_output_tokens",
    ):
        delta[name] = int(delta[name])
    return {
        "fixture": fixture,
        "trials": joined,
        "delta": delta,
        "quality_regressed": quality_regressed,
        "claim_boundary": (
            "single frozen 1-task baseline/variant 1+1 screening; "
            "not statistical or public superiority evidence"
        ),
    }


def _metric_summary(values: list[float]) -> dict[str, float]:
    return {
        "min": round(min(values), 6),
        "median": round(statistics.median(values), 6),
        "mean": round(statistics.fmean(values), 6),
        "max": round(max(values), 6),
    }


def build_repeated_screening(
    baselines: list[dict[str, Any]],
    variants: list[dict[str, Any]],
    outcomes: dict[str, Any],
) -> dict[str, Any]:
    """Compare repeated main-direct and slim fresh-executor frozen trials."""
    if len(baselines) != len(variants) or len(baselines) < 2:
        raise ValueError(
            "repeated screening requires equal baseline/variant counts of at least 2"
        )
    if not isinstance(outcomes, dict):
        raise ValueError("outcomes must be an object")
    fixture = outcomes.get("fixture")
    if (
        not isinstance(fixture, dict)
        or not fixture.get("id")
        or not isinstance(fixture.get("sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", fixture["sha256"])
    ):
        raise ValueError("fixture.id and fixture.sha256 are required")
    outcomes_trials = outcomes.get("trials")
    if not isinstance(outcomes_trials, dict):
        raise ValueError("trials must be an object")

    joined: dict[str, list[dict[str, Any]]] = {"baseline": [], "variant": []}
    runtime_identity: dict[str, str] | None = None
    for label, metrics_rows in (
        ("baseline", baselines),
        ("variant", variants),
    ):
        quality_rows = outcomes_trials.get(label)
        if not isinstance(quality_rows, list) or len(quality_rows) != len(metrics_rows):
            raise ValueError(
                f"{label} outcomes must be a list matching its trace count"
            )
        for index, (metrics, quality_raw) in enumerate(
            zip(metrics_rows, quality_rows, strict=True),
            start=1,
        ):
            quality = _validated_trial_outcome(
                quality_raw, f"{label}[{index - 1}]"
            )
            if metrics.get("time_to_first_edit_seconds") is None:
                raise ValueError(
                    f"{label}[{index - 1}] has no root-user to first-edit evidence"
                )
            if (
                metrics.get("blocking_assistant_requests_before_first_edit")
                is None
            ):
                raise ValueError(
                    f"{label}[{index - 1}] has no blocking-turn evidence"
                )
            if runtime_identity is None:
                runtime_identity = quality["runtime"]
            elif quality["runtime"] != runtime_identity:
                raise ValueError(
                    "all repeated trials must use the same model/effort/provider"
                )
            joined[label].append(
                {
                    "variant": label,
                    "trial": index,
                    **metrics,
                    **quality,
                }
            )

    metric_names = (
        "time_to_first_edit_seconds",
        "blocking_assistant_requests_before_first_edit",
        "main_assistant_requests",
        "total_input_tokens",
        "output_tokens",
        "all_total_input_tokens",
        "all_output_tokens",
    )
    summaries: dict[str, dict[str, dict[str, float]]] = {}
    for label, rows in joined.items():
        summaries[label] = {
            metric: _metric_summary([float(row[metric]) for row in rows])
            for metric in metric_names
        }
        passed = sum(row["product_ac"]["passed"] for row in rows)
        total = sum(row["product_ac"]["total"] for row in rows)
        summaries[label]["product_ac"] = {
            "passed": float(passed),
            "total": float(total),
            "rate": round(passed / total, 6) if total else 0.0,
        }

    baseline_quality = {
        field: sum(row[field] for row in joined["baseline"])
        for field in _QUALITY_FIELDS[1:]
    }
    variant_quality = {
        field: sum(row[field] for row in joined["variant"])
        for field in _QUALITY_FIELDS[1:]
    }
    quality_regressed = (
        summaries["variant"]["product_ac"]["total"]
        != summaries["baseline"]["product_ac"]["total"]
        or summaries["variant"]["product_ac"]["passed"]
        < summaries["baseline"]["product_ac"]["passed"]
        or any(
            variant_quality[field] > baseline_quality[field]
            for field in _QUALITY_FIELDS[1:]
        )
    )
    baseline_edit = summaries["baseline"]["time_to_first_edit_seconds"]["median"]
    variant_edit = summaries["variant"]["time_to_first_edit_seconds"]["median"]
    baseline_blocking = summaries["baseline"][
        "blocking_assistant_requests_before_first_edit"
    ]["median"]
    variant_blocking = summaries["variant"][
        "blocking_assistant_requests_before_first_edit"
    ]["median"]
    enough_trials = len(baselines) >= 3
    materially_faster = variant_edit <= baseline_edit * 0.8
    no_more_blocking = variant_blocking <= baseline_blocking
    conditional_candidate = (
        enough_trials
        and not quality_regressed
        and materially_faster
        and no_more_blocking
    )
    return {
        "fixture": fixture,
        "runtime": runtime_identity,
        "trial_count_per_variant": len(baselines),
        "trials": joined,
        "summary": summaries,
        "quality_regressed": quality_regressed,
        "adoption": {
            "default": "main-direct",
            "conditional_fresh_executor": conditional_candidate,
            "decision": (
                "fresh executor is a narrow conditional candidate"
                if conditional_candidate
                else "retain main-direct; fresh executor evidence is insufficient"
            ),
            "threshold": (
                "at least 3 paired trials, no quality regression, "
                "fresh median time-to-first-edit at least 20% lower, "
                "and no higher median blocking-turn count"
            ),
        },
        "claim_boundary": (
            "repeated frozen-fixture screening with identical declared runtime; "
            "supports only this narrow routing decision, not default or public "
            "provider/model superiority"
        ),
    }


def format_text(r: dict) -> str:
    lines = []
    lines.append(f"session: {r['session']}")
    lines.append(f"  main assistant requests: {r['main_assistant_requests']}")
    lines.append(f"  tool calls             : {r['tool_calls']}")
    lines.append(f"  wall-clock             : {r['wall_clock_seconds']:.3f}s")
    lines.append(
        "  input tokens (uncached/cache-create/cache-read/total): "
        f"{r['input_tokens']} / {r['cache_creation_input_tokens']} / "
        f"{r['cache_read_input_tokens']} / {r['total_input_tokens']}"
    )
    lines.append(f"  output tokens           : {r['output_tokens']}")
    lines.append(
        "  request→first edit / blocking requests: "
        f"{r['time_to_first_edit_seconds']}s / "
        f"{r['blocking_assistant_requests_before_first_edit']}"
    )
    lines.append(
        "  all-executor input/output tokens: "
        f"{r['all_total_input_tokens']} / {r['all_output_tokens']}"
    )
    lines.append(f"  model / effort / provider: {r['models']} / {r['effort_levels']} / {r['providers']}")
    lines.append(f"  total assistant turns : {r['total_turns']}")
    lines.append(f"    - tool turns        : {r['tool_turns']}")
    lines.append(f"    - text-only turns   : {r['text_only_turns']}")
    lines.append(f"    - thinking-only     : {r['thinking_only_turns']}")
    lines.append(f"  Agent (Task) invocations: {r['agent_total']}")
    if r["agent_invocations"]:
        for name, n in r["agent_invocations"]:
            lines.append(f"    - {name}: {n}")
    if r["tool_histogram"]:
        lines.append("  tool histogram:")
        for name, n in r["tool_histogram"].items():
            lines.append(f"    - {name}: {n}")
    return "\n".join(lines)


def format_flow_health_text(report: dict[str, Any]) -> str:
    lines = [
        f"Startup SLO: {report['startup_slo']['status']}",
        f"Flow Visibility: {report['flow_visibility']['status']}",
        f"Agent Activity: {report['agent_activity']['status']}",
        f"Relative Speed: {report['relative_speed']['status']}",
        (
            "  samples (pass/fail/incomplete): "
            f"{report['sample_count']} "
            f"({report['pass_count']}/{report['fail_count']}/"
            f"{report['incomplete_count']})"
        ),
        (
            "  contract: first edit or headless worker launch <60s, "
            "blocking assistant requests <=2; "
            "PASS/CLEAR require >=3 current-version samples"
        ),
    ]
    if report["plugin_version"]:
        lines.append(f"  plugin version: {report['plugin_version']}")
    for row in report["invocations"]:
        lines.append(
            "  - "
            f"{row['session']} {row['command']} {row['result']}: "
            f"first_action={row['time_to_first_action_seconds']}s "
            f"({row['startup_target']}), "
            "blocking="
            f"{row['blocking_assistant_requests_before_first_action']}, "
            f"tool_time={row['pre_action_tool_execution_seconds']}s, "
            "non_tool_elapsed="
            f"{row['pre_action_non_tool_elapsed_ratio']}, "
            f"max_silence={row['max_post_tool_silence_seconds']}s"
        )
    return "\n".join(lines)


def _session_files(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("*.jsonl"))
    if path.is_file():
        return [path]
    return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("path", help="JSONL file or directory of *.jsonl")
    ap.add_argument(
        "--json",
        action="store_true",
        help="JSON output instead of text (machine-readable)",
    )
    ap.add_argument(
        "--paired-with",
        help="Variant session JSONL for one baseline/variant paired screening",
    )
    ap.add_argument(
        "--outcomes",
        help="JSON with frozen fixture identity and product AC/MUST-FIX/regression/human-intervention axes",
    )
    ap.add_argument(
        "--flow-health",
        action="store_true",
        help="Measure command-scoped /impl and /impl-loop startup flow",
    )
    ap.add_argument(
        "--command-name",
        action="append",
        help="Command to include in Flow Health (repeatable; default: dcness:impl and dcness:impl-loop)",
    )
    ap.add_argument(
        "--plugin-version",
        help="Only include Flow Health invocations expanded from this dcNess version",
    )
    args = ap.parse_args(argv)

    p = Path(args.path).expanduser()
    if args.flow_health and args.paired_with:
        print(
            "ERROR: --flow-health cannot be combined with --paired-with",
            file=sys.stderr,
        )
        return 2
    if args.plugin_version and not args.flow_health:
        print(
            "ERROR: --plugin-version requires --flow-health",
            file=sys.stderr,
        )
        return 2
    if args.command_name and not args.flow_health:
        print(
            "ERROR: --command-name requires --flow-health",
            file=sys.stderr,
        )
        return 2
    if args.paired_with:
        baseline_files = _session_files(p)
        if not baseline_files:
            print(f"ERROR: baseline not found: {p}", file=sys.stderr)
            return 2
        variant_path = Path(args.paired_with).expanduser()
        variant_files = _session_files(variant_path)
        if not variant_files:
            print(f"ERROR: variant not found: {variant_path}", file=sys.stderr)
            return 2
        if not args.outcomes:
            print("ERROR: --outcomes is required with --paired-with", file=sys.stderr)
            return 2
        try:
            outcomes = json.loads(Path(args.outcomes).read_text(encoding="utf-8"))
            if len(baseline_files) == len(variant_files) == 1:
                paired = build_paired_screening(
                    parse_session(baseline_files[0]),
                    parse_session(variant_files[0]),
                    outcomes,
                )
            else:
                paired = build_repeated_screening(
                    [parse_session(path) for path in baseline_files],
                    [parse_session(path) for path in variant_files],
                    outcomes,
                )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"ERROR: paired screening invalid: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(paired, ensure_ascii=False, indent=2))
        return 0
    files = _session_files(p)
    if not files:
        print(f"ERROR: not found: {p}", file=sys.stderr)
        return 2

    if args.flow_health:
        report = build_flow_health(
            files,
            command_names=args.command_name,
            plugin_version=args.plugin_version,
        )
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(format_flow_health_text(report))
        return 0

    results = [parse_session(f) for f in files]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(format_text(r))
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

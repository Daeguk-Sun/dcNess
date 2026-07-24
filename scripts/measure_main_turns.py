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
    args = ap.parse_args(argv)

    p = Path(args.path).expanduser()
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

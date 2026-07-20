#!/usr/bin/env python3
"""measure_main_turns.py — Claude Code 세션 JSONL 의 메인 assistant turn 분포 측정.

용도
----
`/impl-loop` Hybrid A 트랙 (#446) 의 메인 컨텍스트 누적 측정:
- 이전 multi-agent baseline: jajang 실측 ~280 turn/task (impl 1-task 세션 3개 평균)
- Hybrid A 목표: 메인 turn/task ~30 (~85-90% 감소). gate = Step 3 프로토타입.
- 동일 frozen 1-task baseline/variant 1+1에서 request/tool/wall-clock/token과
  제품 AC/MUST-FIX/regression/사람 개입을 함께 묶는 paired screening.

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
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_session(path: Path) -> dict:
    """JSONL 한 파일 분석. 결과 dict 반환."""
    requests: dict[str, dict[str, Any]] = {}
    tool_hist: collections.Counter = collections.Counter()
    agent_invocations: list[str] = []
    seen_tool_uses: set[str] = set()
    timestamps: list[datetime] = []
    models: set[str] = set()
    effort_levels: set[str] = set()
    providers: set[str] = set()
    result_duration_seconds: float | None = None

    with path.open() as f:
        for line_number, line in enumerate(f, start=1):
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            timestamp = _parse_timestamp(d.get("timestamp"))
            if timestamp is not None:
                timestamps.append(timestamp)
            if d.get("type") == "result":
                duration_ms = d.get("duration_ms")
                if isinstance(duration_ms, (int, float)) and duration_ms >= 0:
                    result_duration_seconds = float(duration_ms) / 1000
                continue
            if d.get("type") != "assistant":
                continue
            # stream-json forwards sub-agent assistant events with their parent Agent
            # tool id. They are useful end-to-end evidence but are not main requests.
            if d.get("parent_tool_use_id") not in (None, ""):
                continue
            msg = d.get("message") or {}
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content")
            if not isinstance(content, list):
                continue

            request_key = d.get("request_id") or msg.get("id") or f"line-{line_number}"
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
            usage = msg.get("usage") or d.get("usage") or {}
            if isinstance(usage, dict):
                for field in (
                    "input_tokens",
                    "cache_creation_input_tokens",
                    "cache_read_input_tokens",
                    "output_tokens",
                ):
                    request[field] = max(
                        request[field], int(usage.get(field) or 0)
                    )
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
    wall_clock = result_duration_seconds or 0.0
    if result_duration_seconds is None and timestamps:
        wall_clock = max((max(timestamps) - min(timestamps)).total_seconds(), 0.0)
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
        "input_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "total_input_tokens",
        "output_tokens",
    )
    delta = {
        name: round(float(variant.get(name, 0)) - float(baseline.get(name, 0)), 6)
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
        if not p.is_file():
            print(f"ERROR: baseline not found: {p}", file=sys.stderr)
            return 2
        variant_path = Path(args.paired_with).expanduser()
        if not variant_path.is_file():
            print(f"ERROR: variant not found: {variant_path}", file=sys.stderr)
            return 2
        if not args.outcomes:
            print("ERROR: --outcomes is required with --paired-with", file=sys.stderr)
            return 2
        try:
            outcomes = json.loads(Path(args.outcomes).read_text(encoding="utf-8"))
            paired = build_paired_screening(
                parse_session(p), parse_session(variant_path), outcomes
            )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"ERROR: paired screening invalid: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(paired, ensure_ascii=False, indent=2))
        return 0
    if p.is_dir():
        files = sorted(p.glob("*.jsonl"))
    elif p.is_file():
        files = [p]
    else:
        print(f"ERROR: not found: {p}", file=sys.stderr)
        return 2

    if not files:
        print(f"ERROR: no *.jsonl in {p}", file=sys.stderr)
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

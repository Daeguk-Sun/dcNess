#!/usr/bin/env python3
"""measure_main_turns.py — Claude Code 세션 JSONL 의 메인 assistant turn 분포 측정.

용도
----
`/impl-loop` Hybrid A 트랙 (#446) 의 메인 컨텍스트 누적 측정:
- baseline (기존 4-agent 모델): jajang 실측 ~280 turn/task (impl 1-task 세션 3개 평균)
- Hybrid A 목표: 메인 turn/task ~30 (~85-90% 감소). gate = Step 3 프로토타입.

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

예시 (jajang impl 1-task 세션 측정):
    python3 scripts/measure_main_turns.py \\
      ~/.claude/projects/-Users-dc-kim-project-jajang/<sid>.jsonl

#446 트랙 Step 3 gate: 메인 turn ≤ 50 → Step 4 진행 / 50-100 → 부분 성공 / >100 → 단념.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path


def parse_session(path: Path) -> dict:
    """JSONL 한 파일 분석. 결과 dict 반환."""
    total = 0
    tool_turns = 0
    text_only_turns = 0
    thinking_only_turns = 0
    tool_hist: collections.Counter = collections.Counter()
    agent_invocations: list[str] = []

    with path.open() as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") != "assistant":
                continue
            msg = d.get("message") or {}
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content")
            if not isinstance(content, list):
                continue

            total += 1
            has_tool = False
            has_text = False
            has_thinking = False
            for blk in content:
                if not isinstance(blk, dict):
                    continue
                bt = blk.get("type")
                if bt == "tool_use":
                    has_tool = True
                    name = blk.get("name", "?")
                    tool_hist[name] += 1
                    # sub-agent invocation: "Agent" (current) or "Task" (legacy schema)
                    if name in ("Agent", "Task"):
                        inp = blk.get("input") or {}
                        agent_invocations.append(inp.get("subagent_type", "?"))
                elif bt == "text":
                    has_text = True
                elif bt == "thinking":
                    has_thinking = True

            if has_tool:
                tool_turns += 1
            elif has_text:
                text_only_turns += 1
            elif has_thinking:
                thinking_only_turns += 1

    return {
        "session": path.name,
        "path": str(path),
        "total_turns": total,
        "tool_turns": tool_turns,
        "text_only_turns": text_only_turns,
        "thinking_only_turns": thinking_only_turns,
        "tool_histogram": dict(tool_hist.most_common()),
        "agent_total": len(agent_invocations),
        "agent_invocations": collections.Counter(agent_invocations).most_common(),
    }


def format_text(r: dict) -> str:
    lines = []
    lines.append(f"session: {r['session']}")
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
    args = ap.parse_args(argv)

    p = Path(args.path).expanduser()
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

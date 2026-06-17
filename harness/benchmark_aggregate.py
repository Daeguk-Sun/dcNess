#!/usr/bin/env python3
"""benchmark_aggregate.py — 여러 run(ledger.jsonl N개)을 가로질러 집계하는 fleet 레이어.

#766. `run_review.py` 는 run 1개만 분석한다. 본 모듈은 그 위에 fleet 레이어를 얹어
N run 을 한 번에 집계한다 — public benchmark (성공률/FAIL/escalate/waste) 표의 데이터
소스. run_review 의 검증된 파싱(parse_steps / conclusion_enum / detect_wastes)을
*재사용* 한다 (재발명 금지).

산출 지표
--------
- run 수 (entry_point 별 분포)
- agent 별 결론(conclusion enum) 분포
- pr-reviewer FAIL 비율 (= FAIL / (PASS+FAIL+LGTM))
- escalate 결론 수 (전 agent)
- `blocked` 이벤트 수
- waste finding top-N (detect_wastes 합산)

PR 머지 **성공률**은 ledger 의 `pr_merged` 이벤트가 *선택 기록* 이라 대부분 비어있다.
따라서 본 집계기는 성공률을 산출하지 않고 "측정 불가(이벤트 미계측)" 로 정직 표기한다
(#766 작업② — GitHub PR 파생 — 별도 범위).

사용
----
    python3 harness/benchmark_aggregate.py [sessions-root]
    python3 harness/benchmark_aggregate.py [sessions-root] --entry-point impl
    python3 harness/benchmark_aggregate.py [sessions-root] --json
    python3 harness/benchmark_aggregate.py --top 8

sessions-root 미지정 시 cwd 기준 `.claude/harness-state/.sessions` 자동 탐색.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# repo root 를 path 에 추가 (CLI `python3 harness/benchmark_aggregate.py` 직접 실행 대비)
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from harness import ledger  # noqa: E402
from harness import run_review  # noqa: E402

# pr-reviewer FAIL 비율 — 실패로 세는 verdict (FAIL + 옛 CHANGES_REQUESTED).
# CHANGES_REQUESTED 는 현 파서가 FAIL 로 흡수했으나 legacy .steps.jsonl enum 폴백
# 경로에서 원형으로 등장할 수 있어 fail 버킷에 포함한다.
_PR_REVIEWER_FAIL = {"FAIL", "CHANGES_REQUESTED"}
# FAIL 비율 분모 — 결론으로 인정하는 verdict 전체.
_PR_REVIEWER_VERDICTS = {"PASS", "LGTM"} | _PR_REVIEWER_FAIL

# verdict 로 세지 않는 sentinel — PROSE_LOGGED(#284 prose-only advance) / AMBIGUOUS
# (helper 모호 prose 마커). prose 결론(conclusion_enum) 부재 시 stored enum 으로
# 폴백하되 이 값들은 verdict 가 아니므로 제외한다.
_NON_VERDICT_ENUMS = {"PROSE_LOGGED", "AMBIGUOUS", ""}


def _step_verdict(step) -> str:
    """step 의 진짜 verdict — stored enum 이 실제 결론이면 그것을 우선한다.

    신규 ledger 는 enum 이 sentinel(PROSE_LOGGED)이라 prose 결론(conclusion_enum)이
    유일 신호 → prose 사용. legacy .steps.jsonl row 는 enum 에 실제 verdict
    (FAIL / CHANGES_REQUESTED 등)가 저장돼 있고, 이쪽이 regex 로 prose 를 재파싱하는
    conclusion_enum 보다 신뢰도가 높다 (예: "MUST FIX ...\\nLGTM 후보 X" prose 가
    LGTM 으로 오파싱돼 거부된 리뷰를 LGTM 으로 둔갑시키는 회귀 방지). 따라서 stored
    enum 이 non-sentinel 이면 그것을, 아니면 prose 결론을 쓴다.
    """
    if step.enum and step.enum not in _NON_VERDICT_ENUMS:
        return step.enum
    return step.conclusion_enum or ""


def _repo_path_for_run(run_dir: Path) -> Optional[Path]:
    """run_dir(...<repo>/.claude/harness-state/.sessions/<sid>/runs/<rid>)에서
    repo root 추출 — build_report 의 invocation/cost 산출 입력."""
    for p in run_dir.parents:
        if p.name == ".claude":
            return p.parent
    return None


@dataclass
class FleetReport:
    run_count: int
    by_entry_point: dict
    agent_conclusions: dict  # agent -> {enum: count}
    pr_reviewer_fail_ratio: Optional[float]
    escalate_count: int
    blocked_event_count: int
    waste_top: list  # [(pattern, count), ...] count desc
    success_measurable: bool
    waste_limit: int = 10


def _run_entry_point(run_dir: Path) -> Optional[str]:
    """run_started 이벤트에서 entry_point(없으면 mode) 추출."""
    for ev in ledger.read_events_at(run_dir):
        if ev.get("event") == "run_started":
            return ev.get("entry_point") or ev.get("mode")
    return None


def _run_event_counts(run_dir: Path) -> tuple[int, bool]:
    """(blocked 이벤트 수, pr_merged 존재 여부) — 1회 스캔."""
    blocked = 0
    pr_merged = False
    for ev in ledger.read_events_at(run_dir):
        e = ev.get("event")
        if e == "blocked":
            blocked += 1
        elif e == "pr_merged":
            pr_merged = True
    return blocked, pr_merged


def aggregate_runs(run_dirs: list, *, top: int = 10, repo_override=None) -> FleetReport:
    """run_dir 목록을 fleet 집계한다.

    repo_override: build_report 의 invocation/cost 산출 기준 repo. 지정 시 모든 run 에
    적용. **worktree 한계** — run_dir(ledger)은 git-common-dir 때문에 항상 main repo
    의 .claude/harness-state 아래 있지만, Claude 세션 JSONL 은 *실행 cwd*(worktree
    경로)로 키잉된다. 따라서 worktree run 은 run_dir 에서 repo 를 유추하면 세션 JSONL
    을 못 찾아 cost·invocation 의존 waste(END_STEP_SKIP)가 누락된다. prose/agent-trace
    기반 지표(결론 분포 / FAIL 비율 / escalate / blocked / MUST_FIX·TOOL_REPEAT waste)
    는 run_dir 만으로 산출되어 영향 없다. cost/invocation 정확도가 필요하면 그 run 이
    실행된 cwd(worktree 포함)를 --repo 로 지정한다 (run_started 가 cwd 미기록 — #766).
    """
    by_entry_point: Counter = Counter()
    agent_conclusions: dict = defaultdict(Counter)
    escalate_count = 0
    blocked_event_count = 0
    waste_counter: Counter = Counter()
    success_measurable = False

    run_count = 0
    for run_dir in run_dirs:
        # 절대경로화 — 상대 sessions-root 로 호출되면 run_dir 도 상대라
        # _repo_path_for_run 이 "." 를 반환, build_report→find_session_jsonls 의
        # Claude project key 인코딩이 어긋나 cost/invocation waste 가 누락된다.
        run_dir = Path(run_dir).resolve()
        run_count += 1

        ep = _run_entry_point(run_dir)
        if ep:
            by_entry_point[ep] += 1

        blocked, pr_merged = _run_event_counts(run_dir)
        blocked_event_count += blocked
        if pr_merged:
            success_measurable = True

        # build_report 재사용 — parse_steps + invocation 조립(window/repo_path) +
        # detect_wastes 를 per-run review 와 동일하게 수행. 수동 parse_steps +
        # detect_wastes 만 하면 invocation 의존 waste(END_STEP_SKIP 등)가 누락된다.
        repo_path = repo_override or _repo_path_for_run(run_dir) or run_dir
        report = run_review.build_report(run_dir, Path(repo_path))
        for s in report.steps:
            verdict = _step_verdict(s)
            if verdict:
                agent_conclusions[s.agent][verdict] += 1
                # ESCALATE / IMPLEMENTATION_ESCALATE / UX_FLOW_ESCALATE 등 변종 포함.
                if "ESCALATE" in verdict:
                    escalate_count += 1

        for w in report.wastes:
            waste_counter[w.pattern] += 1

    # pr-reviewer FAIL 비율 (FAIL + 옛 CHANGES_REQUESTED) / (PASS+FAIL+LGTM+CR)
    pr = agent_conclusions.get("pr-reviewer", {})
    denom = sum(c for v, c in pr.items() if v in _PR_REVIEWER_VERDICTS)
    fail_n = sum(c for v, c in pr.items() if v in _PR_REVIEWER_FAIL)
    fail_ratio = (fail_n / denom) if denom else None

    return FleetReport(
        run_count=run_count,
        by_entry_point=dict(by_entry_point),
        agent_conclusions={a: dict(c) for a, c in agent_conclusions.items()},
        pr_reviewer_fail_ratio=fail_ratio,
        escalate_count=escalate_count,
        blocked_event_count=blocked_event_count,
        waste_top=waste_counter.most_common(top),
        success_measurable=success_measurable,
        waste_limit=top,
    )


def aggregate_sessions(sessions_root, *, entry_point: Optional[str] = None,
                       top: int = 10, repo_override=None) -> FleetReport:
    """sessions-root 아래 모든 run 을 집계한다. entry_point 지정 시 그 진입점만."""
    sessions_root = Path(sessions_root)
    run_dirs = run_review.list_runs(sessions_root)
    if entry_point:
        run_dirs = [r for r in run_dirs if _run_entry_point(r) == entry_point]
    return aggregate_runs(run_dirs, top=top, repo_override=repo_override)


def _fmt_ratio(r: Optional[float]) -> str:
    return "측정 불가 (표본 0)" if r is None else f"{r * 100:.1f}%"


def render_markdown(report: FleetReport) -> str:
    lines: list = []
    lines.append("# dcNess fleet 집계 (cross-run)")
    lines.append("")
    lines.append(f"- 총 run: **{report.run_count}**")
    if report.by_entry_point:
        ep = " / ".join(f"{k} {v}" for k, v in
                        sorted(report.by_entry_point.items(),
                               key=lambda kv: -kv[1]))
        lines.append(f"- entry_point 분포: {ep}")
    lines.append(f"- pr-reviewer FAIL 비율: "
                 f"**{_fmt_ratio(report.pr_reviewer_fail_ratio)}**")
    lines.append(f"- escalate 결론 수: {report.escalate_count}")
    lines.append(f"- blocked 이벤트 수: {report.blocked_event_count}")
    lines.append("- PR 머지 성공률: 측정 불가 (pr_merged 이벤트 미계측 — #766 작업②)")
    lines.append("")

    lines.append("## agent 별 결론 분포")
    lines.append("")
    lines.append("| agent | 결론 (count) |")
    lines.append("|---|---|")
    for agent in sorted(report.agent_conclusions):
        dist = report.agent_conclusions[agent]
        cell = ", ".join(f"{k}:{v}" for k, v in
                         sorted(dist.items(), key=lambda kv: -kv[1]))
        lines.append(f"| {agent} | {cell} |")
    lines.append("")

    lines.append(f"## waste finding top {report.waste_limit}")
    lines.append("")
    if report.waste_top:
        lines.append("| pattern | count |")
        lines.append("|---|---|")
        for pattern, count in report.waste_top:
            lines.append(f"| {pattern} | {count} |")
    else:
        lines.append("(검출된 waste 없음)")
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="여러 run(ledger.jsonl)을 fleet 집계 (#766)")
    ap.add_argument("sessions_root", nargs="?", default=None,
                    help=".claude/harness-state/.sessions 경로 "
                         "(생략 시 cwd 기준 자동 탐색)")
    ap.add_argument("--entry-point", default=None,
                    help="impl / design 등 특정 진입점만 집계")
    ap.add_argument("--top", type=int, default=10, help="waste top-N (기본 10)")
    ap.add_argument("--repo", default=None,
                    help="cost/invocation 산출 기준 repo (세션 JSONL 위치). "
                         "worktree run 의 정확한 cost/END_STEP_SKIP 가 필요할 때 "
                         "그 run 이 실행된 cwd 지정. 미지정 시 run 경로에서 유추.")
    ap.add_argument("--json", action="store_true", help="JSON 출력")
    args = ap.parse_args(argv)

    sessions_root: Optional[Path]
    if args.sessions_root:
        sessions_root = Path(args.sessions_root)
    else:
        sessions_root = run_review._detect_sessions_root(Path.cwd())
        if sessions_root is None:
            print("sessions-root 를 찾지 못했습니다. 경로를 인자로 지정하세요.",
                  file=sys.stderr)
            return 2

    # --repo 는 절대경로로 resolve — find_session_jsonls 가 Claude project key 를
    # 절대 cwd 기준으로 인코딩하므로 `--repo .` 같은 상대경로는 키가 어긋난다.
    repo_override = Path(args.repo).resolve() if args.repo else None
    report = aggregate_sessions(sessions_root, entry_point=args.entry_point,
                                top=args.top, repo_override=repo_override)

    if args.json:
        print(json.dumps({
            "run_count": report.run_count,
            "by_entry_point": report.by_entry_point,
            "agent_conclusions": report.agent_conclusions,
            "pr_reviewer_fail_ratio": report.pr_reviewer_fail_ratio,
            "escalate_count": report.escalate_count,
            "blocked_event_count": report.blocked_event_count,
            "waste_top": report.waste_top,
            "success_measurable": report.success_measurable,
        }, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

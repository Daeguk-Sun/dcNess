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
- impl-validator FAIL 비율 (= review rejection = FAIL / (PASS+FAIL+LGTM))
- escalate 결론 수 (전 agent)
- `blocked` 이벤트 수
- PR 머지 성공률 (= pr_created 중 pr_merged 로 확인된 PR 비율, 이벤트 있을 때만)
- waste finding top-N (detect_wastes 합산)
- 재발 기반 개선 후보 (동일 waste pattern 이 임계 이상 반복될 때만 표면화)

사용
----
    python3 harness/benchmark_aggregate.py [sessions-root]
    python3 harness/benchmark_aggregate.py [sessions-root] --entry-point impl
    python3 harness/benchmark_aggregate.py [sessions-root] --json
    python3 harness/benchmark_aggregate.py --top 8
    python3 harness/benchmark_aggregate.py --recurrence-threshold 2

sessions-root 미지정 시 cwd 기준 `.claude/harness-state/.sessions` 자동 탐색.
"""
from __future__ import annotations

import argparse
import json
import re
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

# impl-validator FAIL 비율 — 실패로 세는 verdict (FAIL + 옛 CHANGES_REQUESTED).
# CHANGES_REQUESTED 는 현 파서가 FAIL 로 흡수했으나 legacy .steps.jsonl enum 폴백
# 경로에서 원형으로 등장할 수 있어 fail 버킷에 포함한다.
_PR_REVIEWER_FAIL = {"FAIL", "CHANGES_REQUESTED"}
# FAIL 비율 분모 — 결론으로 인정하는 verdict 전체.
_PR_REVIEWER_VERDICTS = {"PASS", "LGTM"} | _PR_REVIEWER_FAIL

# verdict 로 세지 않는 sentinel — PROSE_LOGGED(#284 prose-only advance) / AMBIGUOUS
# (helper 모호 prose 마커). prose 결론(conclusion_enum) 부재 시 stored enum 으로
# 폴백하되 이 값들은 verdict 가 아니므로 제외한다.
_NON_VERDICT_ENUMS = {"PROSE_LOGGED", "AMBIGUOUS", ""}

DEFAULT_RECURRENCE_THRESHOLD = 3

_IMPROVEMENT_SUGGESTION = (
    "자동 박제 없음. 재발 원인을 확인한 뒤 룰 추가, skill 박제, 또는 기존 룰 제거 "
    "중 하나를 사용자 결정으로 분리합니다."
)


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
class ImprovementCandidate:
    pattern: str
    count: int
    threshold: int
    source: str
    suggestion: str


@dataclass
class FleetReport:
    run_count: int
    by_entry_point: dict
    agent_conclusions: dict  # agent -> {enum: count}
    pr_reviewer_fail_ratio: Optional[float]
    pr_reviewer_rejection_count: int
    pr_reviewer_review_count: int
    escalate_count: int
    blocked_event_count: int
    pr_created_count: int
    pr_merged_count: int
    pr_merge_success_count: int
    pr_merge_orphan_count: int
    pr_merge_success_ratio: Optional[float]
    waste_top: list  # [(pattern, count), ...] count desc
    success_measurable: bool
    recurrence_threshold: int
    improvement_candidates: list[ImprovementCandidate]
    waste_limit: int = 10


def _build_improvement_candidates(
    waste_counter: Counter,
    *,
    threshold: int = DEFAULT_RECURRENCE_THRESHOLD,
) -> list[ImprovementCandidate]:
    """Return recurrent waste candidates only.

    GOOD 사례나 raw note 는 입력 자체가 아니므로 집계되지 않는다. 후보는 제안일 뿐이며
    CLAUDE.md·룰·스킬·문서를 자동 수정하지 않는다.
    """
    threshold = max(int(threshold), 1)
    candidates: list[ImprovementCandidate] = []
    for pattern, count in sorted(waste_counter.items(), key=lambda kv: (-kv[1], kv[0])):
        if count < threshold:
            continue
        candidates.append(ImprovementCandidate(
            pattern=pattern,
            count=count,
            threshold=threshold,
            source="run_review.waste",
            suggestion=_IMPROVEMENT_SUGGESTION,
        ))
    return candidates


def _run_entry_point(run_dir: Path) -> Optional[str]:
    """run_started 이벤트에서 entry_point(없으면 mode) 추출."""
    for ev in ledger.read_events_at(run_dir):
        if ev.get("event") == "run_started":
            return ev.get("entry_point") or ev.get("mode")
    return None


_PR_URL_NUMBER_RE = re.compile(r"/pull/([0-9]+)(?:\b|$)")


def _pr_event_key(event: dict, run_dir: Path, index: int) -> str:
    """PR lifecycle event dedupe/match key.

    `pr_number` 가 있으면 repo 경로와 조합해 cross-project #1 충돌을 피한다.
    URL 이 있으면 repo slug 가 이미 들어 있으므로 URL 또는 URL 의 PR 번호를 쓴다.
    둘 다 없으면 ratio 매칭에 쓸 수 없는 orphan event 로 고유화한다.
    """
    url = event.get("url")
    if isinstance(url, str) and url:
        m = _PR_URL_NUMBER_RE.search(url)
        if m:
            return f"url-pr:{url[:url.index('/pull/')]}#pr:{m.group(1)}"
        return f"url:{url}"

    pr_number = event.get("pr_number")
    if pr_number is not None and str(pr_number).strip():
        repo = _repo_path_for_run(run_dir) or run_dir
        return f"repo:{Path(repo).resolve()}#pr:{pr_number}"

    return f"event:{run_dir}:{index}"


def _run_event_counts(run_dir: Path) -> tuple[int, set[str], set[str]]:
    """(blocked 이벤트 수, pr_created keys, pr_merged keys) — 1회 스캔."""
    blocked = 0
    pr_created: set[str] = set()
    pr_merged: set[str] = set()
    for idx, ev in enumerate(ledger.read_events_at(run_dir)):
        e = ev.get("event")
        if e == "blocked":
            blocked += 1
        elif e == "pr_created":
            pr_created.add(_pr_event_key(ev, run_dir, idx))
        elif e == "pr_merged":
            pr_merged.add(_pr_event_key(ev, run_dir, idx))
    return blocked, pr_created, pr_merged


def aggregate_runs(
    run_dirs: list,
    *,
    top: int = 10,
    recurrence_threshold: int = DEFAULT_RECURRENCE_THRESHOLD,
    repo_override=None,
) -> FleetReport:
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
    pr_created_keys: set[str] = set()
    pr_merged_keys: set[str] = set()
    waste_counter: Counter = Counter()

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

        blocked, created, merged = _run_event_counts(run_dir)
        blocked_event_count += blocked
        pr_created_keys.update(created)
        pr_merged_keys.update(merged)

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

    # impl-validator FAIL 비율 (FAIL + 옛 CHANGES_REQUESTED) / (PASS+FAIL+LGTM+CR)
    pr = agent_conclusions.get("impl-validator", {})
    denom = sum(c for v, c in pr.items() if v in _PR_REVIEWER_VERDICTS)
    fail_n = sum(c for v, c in pr.items() if v in _PR_REVIEWER_FAIL)
    fail_ratio = (fail_n / denom) if denom else None

    pr_success_keys = pr_created_keys & pr_merged_keys
    pr_created_count = len(pr_created_keys)
    pr_merged_count = len(pr_merged_keys)
    pr_merge_success_count = len(pr_success_keys)
    pr_merge_orphan_count = len(pr_merged_keys - pr_created_keys)
    pr_merge_success_ratio = (
        pr_merge_success_count / pr_created_count if pr_created_count else None
    )
    recurrence_threshold = max(int(recurrence_threshold), 1)

    return FleetReport(
        run_count=run_count,
        by_entry_point=dict(by_entry_point),
        agent_conclusions={a: dict(c) for a, c in agent_conclusions.items()},
        pr_reviewer_fail_ratio=fail_ratio,
        pr_reviewer_rejection_count=fail_n,
        pr_reviewer_review_count=denom,
        escalate_count=escalate_count,
        blocked_event_count=blocked_event_count,
        pr_created_count=pr_created_count,
        pr_merged_count=pr_merged_count,
        pr_merge_success_count=pr_merge_success_count,
        pr_merge_orphan_count=pr_merge_orphan_count,
        pr_merge_success_ratio=pr_merge_success_ratio,
        waste_top=waste_counter.most_common(top),
        success_measurable=pr_merge_success_ratio is not None,
        recurrence_threshold=recurrence_threshold,
        improvement_candidates=_build_improvement_candidates(
            waste_counter,
            threshold=recurrence_threshold,
        ),
        waste_limit=top,
    )


def aggregate_sessions(sessions_root, *, entry_point: Optional[str] = None,
                       top: int = 10,
                       recurrence_threshold: int = DEFAULT_RECURRENCE_THRESHOLD,
                       repo_override=None) -> FleetReport:
    """sessions-root 아래 모든 run 을 집계한다. entry_point 지정 시 그 진입점만."""
    sessions_root = Path(sessions_root)
    run_dirs = run_review.list_runs(sessions_root)
    if entry_point:
        run_dirs = [r for r in run_dirs if _run_entry_point(r) == entry_point]
    return aggregate_runs(
        run_dirs,
        top=top,
        recurrence_threshold=recurrence_threshold,
        repo_override=repo_override,
    )


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
    lines.append(
        f"- review rejection(impl-validator FAIL) 비율: "
        f"**{_fmt_ratio(report.pr_reviewer_fail_ratio)}** "
        f"({report.pr_reviewer_rejection_count}/{report.pr_reviewer_review_count})"
    )
    lines.append(f"- escalate 결론 수: {report.escalate_count}")
    lines.append(f"- blocked 이벤트 수: {report.blocked_event_count}")
    if report.pr_merge_success_ratio is None:
        lines.append(
            "- PR 머지 성공률: 측정 불가 "
            f"(pr_created 이벤트 0, pr_merged 이벤트 {report.pr_merged_count}; "
            "synthetic 추정 없음)"
        )
    else:
        lines.append(
            f"- PR 머지 성공률: **{_fmt_ratio(report.pr_merge_success_ratio)}** "
            f"({report.pr_merge_success_count}/{report.pr_created_count}; "
            f"pr_merged 이벤트 {report.pr_merged_count})"
        )
    if report.pr_merge_orphan_count:
        lines.append(
            f"- PR 머지 orphan 이벤트: {report.pr_merge_orphan_count} "
            "(matching pr_created 없음 — 성공률 분자에서 제외)"
        )
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

    lines.append(f"## 재발 기반 개선 후보 (threshold {report.recurrence_threshold})")
    lines.append("")
    if report.improvement_candidates:
        lines.append("| pattern | count | suggestion |")
        lines.append("|---|---:|---|")
        for candidate in report.improvement_candidates:
            lines.append(
                f"| {candidate.pattern} | {candidate.count} | {candidate.suggestion} |"
            )
    else:
        lines.append("(임계 도달 후보 없음 — GOOD 사례는 집계 대상이 아닙니다.)")
    lines.append("")
    lines.append("자동 수정 없음 — 후보 표면화까지만 수행하고 박제 여부는 사용자가 결정합니다.")
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
    ap.add_argument(
        "--recurrence-threshold",
        type=int,
        default=DEFAULT_RECURRENCE_THRESHOLD,
        help="개선 후보로 표면화할 동일 waste pattern 반복 임계값 (기본 3)",
    )
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
                                top=args.top,
                                recurrence_threshold=args.recurrence_threshold,
                                repo_override=repo_override)

    if args.json:
        print(json.dumps({
            "run_count": report.run_count,
            "by_entry_point": report.by_entry_point,
            "agent_conclusions": report.agent_conclusions,
            "pr_reviewer_fail_ratio": report.pr_reviewer_fail_ratio,
            "pr_reviewer_rejection_count": report.pr_reviewer_rejection_count,
            "pr_reviewer_review_count": report.pr_reviewer_review_count,
            "escalate_count": report.escalate_count,
            "blocked_event_count": report.blocked_event_count,
            "pr_created_count": report.pr_created_count,
            "pr_merged_count": report.pr_merged_count,
            "pr_merge_success_count": report.pr_merge_success_count,
            "pr_merge_orphan_count": report.pr_merge_orphan_count,
            "pr_merge_success_ratio": report.pr_merge_success_ratio,
            "waste_top": report.waste_top,
            "success_measurable": report.success_measurable,
            "recurrence_threshold": report.recurrence_threshold,
            "improvement_candidates": [
                {
                    "pattern": candidate.pattern,
                    "count": candidate.count,
                    "threshold": candidate.threshold,
                    "source": candidate.source,
                    "suggestion": candidate.suggestion,
                }
                for candidate in report.improvement_candidates
            ],
        }, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

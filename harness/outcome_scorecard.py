#!/usr/bin/env python3
"""Cross-project process, effectiveness, and product-outcome scorecard.

Run ledgers provide process evidence. Project-local journey receipts provide product
outcomes. Agent-effectiveness and complete legacy trial metadata stay unmeasured until
their own evidence exists; no axis substitutes for another.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from harness import agent_effectiveness, ledger, product_journey, run_review  # noqa: E402
from harness.benchmark_aggregate import FleetReport, aggregate_runs  # noqa: E402


DEFAULT_PROJECTS_FILE = (
    Path.home() / ".claude" / "plugins" / "data" / "dcness-dcness" / "projects.json"
)
UNMEASURED = "측정 불가"


class SourceRefNotFound(ValueError):
    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(f"source ref not found: {', '.join(missing)}")


class SourceDataUnavailable(ValueError):
    def __init__(self, unavailable: list[str]) -> None:
        self.unavailable = unavailable
        super().__init__(f"source data unavailable: {', '.join(unavailable)}")


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_projects(path: Path) -> list[Path]:
    try:
        payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw_projects = payload.get("projects") if isinstance(payload, dict) else None
    if not isinstance(raw_projects, list):
        return []

    projects: list[Path] = []
    seen: set[str] = set()
    for raw in raw_projects:
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            project = Path(raw).expanduser().resolve()
        except (OSError, ValueError):
            continue
        key = str(project)
        if key in seen:
            continue
        seen.add(key)
        projects.append(project)
    return projects


def _source_ref(project: Path) -> str:
    digest = hashlib.sha256(str(project).encode("utf-8")).hexdigest()[:10]
    return f"source-{digest}"


def _candidate_run_dirs(sessions_root: Path) -> list[Path]:
    if not sessions_root.is_dir():
        return []
    candidates: set[Path] = set()
    for filename in ("ledger.jsonl", ".steps.jsonl"):
        for path in sessions_root.glob(f"*/runs/*/{filename}"):
            candidates.add(path.parent)
    return sorted(candidates)


def _run_event_times(run_dir: Path) -> list[datetime]:
    values = [
        parsed
        for event in ledger.read_events_at(run_dir)
        if (parsed := _parse_ts(event.get("ts"))) is not None
    ]
    if values or not (run_dir / ".steps.jsonl").is_file():
        return values
    try:
        lines = (run_dir / ".steps.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and (parsed := _parse_ts(row.get("ts"))) is not None:
            values.append(parsed)
    return values


def _started_by(run_dir: Path, cutoff: Optional[datetime]) -> bool:
    if cutoff is None:
        return True
    times = _run_event_times(run_dir)
    return bool(times) and min(times) <= cutoff


def _finished_by(run_dir: Path, cutoff: Optional[datetime]) -> bool:
    if cutoff is None:
        return True
    events = ledger.read_events_at(run_dir)
    finished = [
        parsed
        for event in events
        if event.get("event") == "run_finished"
        if (parsed := _parse_ts(event.get("ts"))) is not None
    ]
    if finished:
        return any(parsed <= cutoff for parsed in finished)
    times = _run_event_times(run_dir)
    # Legacy .steps.jsonl has no run_finished marker: every readable step receipt is
    # historically a finished-run signal. Later appends must not remove the earlier
    # snapshot; parse_steps(event_cutoff=...) filters the post-cutoff rows themselves.
    return any(parsed <= cutoff for parsed in times)


def _metric(
    *,
    measured_at: str,
    source_project_count: int,
    numerator: int,
    denominator: int,
    value: Any,
    unit: str,
    evidence: str,
    measurable: bool = True,
) -> dict[str, Any]:
    return {
        "status": "관측" if measurable else UNMEASURED,
        "value": value if measurable else None,
        "numerator": numerator,
        "denominator": denominator,
        "unit": unit,
        "source_project_count": source_project_count,
        "measured_at": measured_at,
        "evidence": evidence,
    }


def _fleet_json(report: FleetReport) -> dict[str, Any]:
    return {
        "run_count": report.run_count,
        "by_entry_point": report.by_entry_point,
        "agent_conclusions": report.agent_conclusions,
        "pr_reviewer_rejection_count": report.pr_reviewer_rejection_count,
        "pr_reviewer_review_count": report.pr_reviewer_review_count,
        "pr_created_count": report.pr_created_count,
        "pr_merge_success_count": report.pr_merge_success_count,
        "pr_merged_count": report.pr_merged_count,
        "blocked_event_count": report.blocked_event_count,
        "waste_top": report.waste_top,
        "waste_counts": report.waste_counts,
    }


def build_scorecard(
    projects_file: Path | str = DEFAULT_PROJECTS_FILE,
    *,
    measured_at: Optional[str] = None,
    as_of: Optional[str] = None,
    source_refs: Optional[list[str]] = None,
    redact_paths: bool = False,
    agent_effectiveness_record: Path | str | None = None,
) -> dict[str, Any]:
    """Aggregate finished runs from every configured project with observable data."""
    measured_at = measured_at or _now_iso()
    cutoff = _parse_ts(as_of)
    if as_of and cutoff is None:
        raise ValueError(f"invalid --as-of timestamp: {as_of}")
    projects_file = Path(projects_file).expanduser().resolve()
    configured = _load_projects(projects_file)
    configured_with_refs = [(_source_ref(project), project) for project in configured]
    if source_refs is not None:
        requested = list(dict.fromkeys(source_refs))
        by_ref = {source_ref: project for source_ref, project in configured_with_refs}
        missing = [source_ref for source_ref in requested if source_ref not in by_ref]
        if missing:
            raise SourceRefNotFound(missing)
        selected = [(source_ref, by_ref[source_ref]) for source_ref in requested]
    else:
        selected = configured_with_refs
    registry_indexes = {
        source_ref: index
        for index, (source_ref, _project) in enumerate(configured_with_refs, start=1)
    }

    journey_receipts: list[tuple[str, dict[str, Any]]] = []
    for source_ref, project in selected:
        for receipt in product_journey.read_receipts(project, cutoff=cutoff):
            journey_receipts.append((source_ref, receipt))

    sources: list[dict[str, Any]] = []
    fleets: list[FleetReport] = []
    candidate_run_count = 0
    unavailable_sources: list[str] = []
    for source_ref, project in selected:
        index = registry_indexes[source_ref]
        sessions_root = project / ".claude" / "harness-state" / ".sessions"
        candidate_dirs = [
            run_dir
            for run_dir in _candidate_run_dirs(sessions_root)
            if _started_by(run_dir, cutoff)
        ]
        if not candidate_dirs:
            if source_refs is not None:
                unavailable_sources.append(source_ref)
            continue
        finished_dirs = [
            run_dir
            for run_dir in run_review.list_runs(sessions_root)
            if _finished_by(run_dir, cutoff)
        ]
        fleet = aggregate_runs(finished_dirs, event_cutoff=cutoff)
        if fleet.run_count == 0:
            if source_refs is not None:
                unavailable_sources.append(source_ref)
            continue
        candidates = len(candidate_dirs)
        candidate_run_count += candidates
        fleets.append(fleet)
        source = {
            "source_ref": source_ref,
            "projects_file_index": index,
            "source_location": f"active-project registry entry #{index}",
            "candidate_run_count": candidates,
            "finished_run_count": fleet.run_count,
            "fleet": _fleet_json(fleet),
        }
        if not redact_paths:
            source["project_path"] = str(project)
            source["sessions_root"] = str(sessions_root)
        sources.append(source)

    if unavailable_sources:
        raise SourceDataUnavailable(unavailable_sources)

    source_count = len(sources)
    finished_runs = sum(fleet.run_count for fleet in fleets)
    pr_created = sum(fleet.pr_created_count for fleet in fleets)
    pr_merged = sum(fleet.pr_merge_success_count for fleet in fleets)
    review_rejections = sum(fleet.pr_reviewer_rejection_count for fleet in fleets)
    review_verdicts = sum(fleet.pr_reviewer_review_count for fleet in fleets)
    blocked_events = sum(fleet.blocked_event_count for fleet in fleets)

    conclusions: dict[str, Counter[str]] = defaultdict(Counter)
    waste: Counter[str] = Counter()
    for fleet in fleets:
        for agent, distribution in fleet.agent_conclusions.items():
            conclusions[agent].update(distribution)
        waste.update(fleet.waste_counts)
    validator_conclusions = {
        agent: dict(sorted(distribution.items()))
        for agent, distribution in sorted(conclusions.items())
        if agent.endswith("validator")
    }
    validator_verdict_count = sum(
        sum(distribution.values()) for distribution in validator_conclusions.values()
    )
    waste_count = sum(waste.values())

    process = {
        "finished_runs": _metric(
            measured_at=measured_at,
            source_project_count=source_count,
            numerator=finished_runs,
            denominator=candidate_run_count,
            value=(finished_runs / candidate_run_count if candidate_run_count else None),
            unit="finished runs / candidate run directories",
            evidence="run_finished plus a valid readable receipt",
            measurable=candidate_run_count > 0,
        ),
        "pr_merge_success": _metric(
            measured_at=measured_at,
            source_project_count=source_count,
            numerator=pr_merged,
            denominator=pr_created,
            value=(pr_merged / pr_created if pr_created else None),
            unit="matching pr_merged / pr_created",
            evidence="PR lifecycle events; orphan merges never enter the numerator",
            measurable=pr_created > 0,
        ),
        "blocked_events": _metric(
            measured_at=measured_at,
            source_project_count=source_count,
            numerator=blocked_events,
            denominator=finished_runs,
            value=(blocked_events / finished_runs if finished_runs else None),
            unit="blocked events / finished-run exposure",
            evidence="blocked lifecycle events at or before the snapshot cutoff",
            measurable=finished_runs > 0,
        ),
        "guard_results": _metric(
            measured_at=measured_at,
            source_project_count=source_count,
            numerator=0,
            denominator=0,
            value=None,
            unit="guard results / eligible guard executions",
            evidence="guard telemetry is not part of the selected ledger baseline",
            measurable=False,
        ),
        "regressions": _metric(
            measured_at=measured_at,
            source_project_count=source_count,
            numerator=0,
            denominator=0,
            value=None,
            unit="product regressions / repeated product journeys",
            evidence="repeated product-journey evidence is absent from the ledger",
            measurable=False,
        ),
        "impl_validator_rework": _metric(
            measured_at=measured_at,
            source_project_count=source_count,
            numerator=review_rejections,
            denominator=review_verdicts,
            value=(review_rejections / review_verdicts if review_verdicts else None),
            unit="FAIL / impl-validator review verdicts",
            evidence="impl-validator conclusion prose or compatible legacy verdict",
            measurable=review_verdicts > 0,
        ),
        "validator_verdicts": _metric(
            measured_at=measured_at,
            source_project_count=source_count,
            numerator=validator_verdict_count,
            denominator=finished_runs,
            value=validator_conclusions,
            unit="validator conclusions over finished-run exposure",
            evidence="validator step conclusion distribution",
            measurable=finished_runs > 0,
        ),
        "waste_signals": _metric(
            measured_at=measured_at,
            source_project_count=source_count,
            numerator=waste_count,
            denominator=finished_runs,
            value=dict(waste.most_common()),
            unit="waste findings over finished-run exposure",
            evidence="run_review waste detector reused by benchmark_aggregate",
            measurable=finished_runs > 0,
        ),
    }

    unmeasured_context = {
        "status": UNMEASURED,
        "source_project_count": source_count,
        "measured_at": measured_at,
        "as_of": as_of,
    }
    product_outcome = _product_outcome(
        journey_receipts,
        measured_at=measured_at,
        as_of=as_of,
    )
    effectiveness = (
        agent_effectiveness.load_record(agent_effectiveness_record)
        if agent_effectiveness_record is not None
        else {
            **unmeasured_context,
            "reason": (
                "현재 ledger는 SSOT·entrypoint·owner 탐색 정확도, 첫 올바른 대상까지의 "
                "비용, 오경로, 영향 누락, context 기인 재작업, cross-session 복구를 "
                "비교 가능한 trial로 기록하지 않는다."
            ),
        }
    )
    trial_metadata = (
        {
            "status": "관측",
            "source_project_count": effectiveness["source_count"],
            "measured_at": effectiveness["measured_at"],
            "denominator": effectiveness["denominator"],
            "conditions": effectiveness["conditions"],
            "cost": effectiveness["cost"],
            "new_llm_trials": effectiveness["new_llm_trials"],
            "reason": "agent-effectiveness replay record의 frozen trial identity와 비용 근거",
        }
        if agent_effectiveness_record is not None
        else {
            **unmeasured_context,
            "reason": (
                "legacy run은 task/repo 유형, model/provider, harness variant, trial "
                "identity, 사람 개입, wall-clock, token, cost를 하나의 비교 가능한 "
                "record로 일관되게 보존하지 않는다."
            ),
        }
    )
    return {
        "measured_at": measured_at,
        "as_of": as_of,
        "projects_file": (
            "active-project registry (path redacted)"
            if redact_paths
            else str(projects_file)
        ),
        "configured_project_count": len(configured),
        "source_project_count": source_count,
        "sources": sources,
        "process_evidence": process,
        "agent_effectiveness": effectiveness,
        "product_outcome": product_outcome,
        "trial_metadata": trial_metadata,
        "claim_boundaries": {
            "personal_screening": (
                "같은 task/fixture의 1+1 paired screening은 개인 keep/remove/hold "
                "판단에만 사용할 수 있다."
            ),
            "public_superiority": (
                "최소 2개 source 프로젝트, 총 20개 finished run, 지표별 명시적 "
                "denominator, 비교 variant별 반복 trial이 필요하며 1+1 결과만으로는 "
                "주장할 수 없다."
            ),
        },
    }


def _product_outcome(
    receipts: list[tuple[str, dict[str, Any]]],
    *,
    measured_at: str,
    as_of: Optional[str],
) -> dict[str, Any]:
    if not receipts:
        return {
            "status": UNMEASURED,
            "source_project_count": 0,
            "measured_at": measured_at,
            "as_of": as_of,
            "reason": (
                "project-local product journey receipt가 없다. guard·validator·PR "
                "evidence는 실제 제품 outcome을 대체하지 않는다."
            ),
        }

    passed_journeys = sum(
        1 for _source_ref_value, receipt in receipts if receipt["outcome"] == "PASS"
    )
    ac_passed = sum(int(receipt["product_ac"]["passed"]) for _, receipt in receipts)
    ac_total = sum(int(receipt["product_ac"]["total"]) for _, receipt in receipts)
    human_interventions = sum(
        int(receipt.get("human_intervention_count") or 0) for _, receipt in receipts
    )
    evidence_types = sorted(
        {
            evidence_type
            for _, receipt in receipts
            for evidence_type in receipt.get("evidence_types", [])
            if isinstance(evidence_type, str)
        }
    )
    source_count = len({source_ref_value for source_ref_value, _ in receipts})
    journeys = [
        {
            "source_ref": source_ref_value,
            "run_id": receipt["run_id"],
            "journey_id": receipt["journey_id"],
            "measured_at": receipt["measured_at"],
            "outcome": receipt["outcome"],
            "boundary": receipt["boundary"],
            "target_ac": receipt["target_ac"],
            "product_ac": receipt["product_ac"],
            "human_intervention_count": receipt.get("human_intervention_count", 0),
            "evidence_types": receipt.get("evidence_types", []),
            "receipt_path": receipt["receipt_path"],
        }
        for source_ref_value, receipt in receipts
    ]
    return {
        "status": "관측",
        "source_project_count": source_count,
        "measured_at": measured_at,
        "as_of": as_of,
        "numerator": passed_journeys,
        "denominator": len(receipts),
        "value": passed_journeys / len(receipts),
        "product_ac": {"passed": ac_passed, "total": ac_total},
        "human_intervention_count": human_interventions,
        "evidence_types": evidence_types,
        "journeys": journeys,
        "reason": (
            "helper-generated project-local receipt만 집계했다. 과정·merge 지표는 "
            "분자나 분모에 포함하지 않았다."
        ),
    }


def _ratio_cell(metric: dict[str, Any]) -> str:
    numerator = int(metric.get("numerator") or 0)
    denominator = int(metric.get("denominator") or 0)
    if metric.get("status") == UNMEASURED:
        return f"{UNMEASURED} ({numerator}/{denominator})"
    value = metric.get("value")
    if isinstance(value, float):
        return f"{value * 100:.1f}% ({numerator}/{denominator})"
    return f"{numerator}/{denominator}"


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Cross-project outcome scorecard",
        "",
        f"- 측정 시각: `{report['measured_at']}`",
        f"- 관측 cutoff: `{report.get('as_of') or '없음 (현재 전체)'}`",
        f"- source 프로젝트: {report['source_project_count']}",
        f"- 활성 registry 항목: {report['configured_project_count']}",
        f"- 원천 registry: `{report['projects_file']}`",
        "",
        "## 과정·merge 지표",
        "",
        "| 지표 | 값 (분자/분모) | source 수 | 측정일 |",
        "|---|---|---:|---|",
    ]
    labels = {
        "finished_runs": "완료 run 포함률",
        "pr_merge_success": "PR merge 성공률",
        "blocked_events": "blocked event 노출률",
        "guard_results": "guard 결과",
        "regressions": "제품 regression",
        "impl_validator_rework": "impl-validator 재작업률",
        "validator_verdicts": "validator verdict 분포",
        "waste_signals": "waste 신호",
    }
    for key, metric in report["process_evidence"].items():
        value = _ratio_cell(metric)
        if isinstance(metric.get("value"), dict):
            details = json.dumps(metric["value"], ensure_ascii=False, sort_keys=True)
            value = f"{value}; `{details}`"
        lines.append(
            f"| {labels[key]} | {value} | {metric['source_project_count']} | "
            f"`{metric['measured_at']}` |"
        )

    lines.extend(
        [
            "",
            "과정 지표는 하네스·리뷰·PR 흐름의 관측값이다. 제품 성공률이 아니다.",
            "",
            "## Agent effectiveness",
            "",
            f"- 상태: **{report['agent_effectiveness']['status']}**",
            f"- 이유: {report['agent_effectiveness']['reason']}",
            "",
            "## 실제 제품 outcome",
            "",
            f"- 상태: **{report['product_outcome']['status']}**",
            f"- 이유: {report['product_outcome']['reason']}",
            "",
            "## Trial metadata",
            "",
            f"- 상태: **{report['trial_metadata']['status']}**",
            f"- 이유: {report['trial_metadata']['reason']}",
            "",
            "## 주장 가능 범위",
            "",
            f"- 개인 판단: {report['claim_boundaries']['personal_screening']}",
            f"- 공개 우위: {report['claim_boundaries']['public_superiority']}",
            "",
            "## 원천",
            "",
            "| source | registry 위치 | finished/candidate |",
            "|---|---|---:|",
        ]
    )
    outcome = report["product_outcome"]
    effectiveness = report["agent_effectiveness"]
    if effectiveness["status"] != UNMEASURED:
        lines[lines.index("## 실제 제품 outcome"):lines.index("## 실제 제품 outcome")] = [
            f"- 비교 trial: {effectiveness['denominator']}",
            f"- source fixture: {effectiveness['source_count']}",
            f"- 개선 관측: {'YES' if effectiveness['improved'] else 'NO'}",
            f"- 품질 비열화: {'YES' if effectiveness['quality_worse'] else 'NO'}",
            (
                "- baseline → current: "
                f"tool {effectiveness['baseline']['tool_calls']}→"
                f"{effectiveness['current']['tool_calls']}, "
                f"read bytes {effectiveness['baseline']['read_bytes']}→"
                f"{effectiveness['current']['read_bytes']}, "
                f"오경로 {effectiveness['baseline']['wrong_paths']}→"
                f"{effectiveness['current']['wrong_paths']}, "
                f"영향 누락 {effectiveness['baseline']['missed_impact']}→"
                f"{effectiveness['current']['missed_impact']}, "
                f"context 재작업 {effectiveness['baseline']['context_rework']}→"
                f"{effectiveness['current']['context_rework']}"
            ),
            (
                "- token/cost: "
                f"input {effectiveness['cost']['input_tokens']}, "
                f"output {effectiveness['cost']['output_tokens']}, "
                f"USD {effectiveness['cost']['cost_usd']:.2f}"
            ),
            "",
        ]
    if outcome["status"] != UNMEASURED:
        lines[lines.index("## Trial metadata"):lines.index("## Trial metadata")] = [
            f"- journey PASS: {outcome['numerator']}/{outcome['denominator']}",
            (
                "- 제품 AC: "
                f"{outcome['product_ac']['passed']}/{outcome['product_ac']['total']}"
            ),
            f"- source 프로젝트: {outcome['source_project_count']}",
            f"- 사람 개입: {outcome['human_intervention_count']}",
            f"- 실행 증거 종류: {', '.join(outcome['evidence_types'])}",
            "",
        ]
    for source in report["sources"]:
        lines.append(
            f"| `{source['source_ref']}` | {source['source_location']} | "
            f"{source['finished_run_count']}/{source['candidate_run_count']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="active projects의 process/effectiveness/product outcome scorecard"
    )
    parser.add_argument(
        "--projects-file",
        default=str(DEFAULT_PROJECTS_FILE),
        help="active projects registry JSON",
    )
    parser.add_argument(
        "--measured-at",
        default=None,
        help="reproducible snapshot timestamp (ISO-8601; default: now UTC)",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        help="이 시각 이하에서 시작·완료된 run만 포함하는 snapshot cutoff",
    )
    parser.add_argument(
        "--source-ref",
        action="append",
        default=None,
        help="registry reorder/addition과 무관하게 포함할 stable source ref (repeatable)",
    )
    parser.add_argument(
        "--redact-paths",
        action="store_true",
        help="project and registry absolute paths를 stable source ref로 대체",
    )
    parser.add_argument(
        "--agent-effectiveness-record",
        default=None,
        help="frozen agent-effectiveness replay record JSON",
    )
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    args = parser.parse_args(argv)

    try:
        report = build_scorecard(
            args.projects_file,
            measured_at=args.measured_at,
            as_of=args.as_of,
            source_refs=args.source_ref,
            redact_paths=args.redact_paths,
            agent_effectiveness_record=args.agent_effectiveness_record,
        )
    except SourceRefNotFound as exc:
        print(json.dumps(
            {"error": "source_ref_not_found", "missing": exc.missing},
            ensure_ascii=False,
        ))
        return 2
    except SourceDataUnavailable as exc:
        print(json.dumps(
            {"error": "source_data_unavailable", "unavailable": exc.unavailable},
            ensure_ascii=False,
        ))
        return 2
    except agent_effectiveness.AgentEffectivenessRecordInvalid as exc:
        for error in exc.errors:
            print(error, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

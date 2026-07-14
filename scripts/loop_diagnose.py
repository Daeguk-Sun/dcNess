#!/usr/bin/env python3
"""Cross-project Diagnose sweep for the dcNess self-improvement loop (#902)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from harness import ledger  # noqa: E402
from harness import run_review  # noqa: E402
from harness.benchmark_aggregate import aggregate_sessions  # noqa: E402
from harness.loop_lessons import list_active_lessons  # noqa: E402
from harness.guard_telemetry import (  # noqa: E402
    DEFAULT_REPORT_SINCE_DAYS,
    collect_eval_summary,
    collect_guard_summary,
    read_events,
)


DEFAULT_PROJECTS_FILE = (
    Path.home() / ".claude" / "plugins" / "data" / "dcness-dcness" / "projects.json"
)
SWEEP_PATH = Path(".metrics") / "loop-diagnose" / "sweeps.jsonl"
DIGEST_FILENAME = "digest-latest.md"
SWEEP_LOG_FILENAME = "sweep-log.jsonl"
DIGEST_NOTE = (
    "> 스케줄 sweep 이 남긴 최신 digest. sweep 은 read-only 관측만 하며 Decide 는 사람 몫이다.\n"
    "> 후보 소비는 `record-decision` 으로 남긴다.\n\n"
)
DECISIONS_PATH = Path("docs") / "internal" / "loop-decisions.jsonl"
VALID_DECISIONS = {"fixed", "hold", "rejected"}
DECISION_LABELS = {
    "fixed": "고침",
    "hold": "보류",
    "rejected": "기각",
}
NO_OBSERVATION = "관측 이력 없음(미배포 또는 무발화)"
ACTION_PRIORITY = {
    "waste": 0,
    "lesson-rule": 1,
    "lesson": 2,
    "eval": 3,
    "guard": 4,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_ts(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _max_ts(values: list[Any]) -> Optional[str]:
    best_value: Optional[str] = None
    best_dt: Optional[datetime] = None
    for value in values:
        parsed = _parse_ts(value)
        if parsed is None:
            continue
        if best_dt is None or parsed > best_dt:
            best_dt = parsed
            best_value = str(value)
    return best_value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        return []
    return rows


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _project_name(path: Path) -> str:
    name = path.name.strip()
    return name if name else str(path)


def _load_projects(path: Path) -> list[Path]:
    try:
        data = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict) or not isinstance(data.get("projects"), list):
        return []
    projects: list[Path] = []
    seen: set[str] = set()
    for item in data["projects"]:
        if not isinstance(item, str) or not item.strip():
            continue
        try:
            resolved = Path(item).expanduser().resolve()
        except (OSError, ValueError):
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        projects.append(resolved)
    return projects


def _latest_run_event_ts(sessions_root: Path) -> Optional[str]:
    values: list[Any] = []
    for run_dir in run_review.list_runs(sessions_root):
        for event in ledger.read_events_at(run_dir):
            values.append(event.get("ts"))
    return _max_ts(values)


def _latest_project_ts(events: list[dict[str, Any]], sessions_root: Path) -> Optional[str]:
    values = [event.get("ts") for event in events]
    run_ts = _latest_run_event_ts(sessions_root)
    if run_ts:
        values.append(run_ts)
    return _max_ts(values)


def _candidate(
    *,
    key: str,
    kind: str,
    project: str,
    scope_path: Path,
    detail: str,
    last_ts: Optional[str],
) -> dict[str, Any]:
    return {
        "key": key,
        "kind": kind,
        "project": project,
        "scope_path": str(scope_path),
        "detail": detail,
        "last_ts": last_ts,
    }


def _guard_candidates(
    project_name: str,
    project_path: Path,
    guard_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    guards = guard_summary.get("guards")
    if not isinstance(guards, dict):
        return candidates
    for guard, raw in sorted(guards.items()):
        row = raw if isinstance(raw, dict) else {}
        count = int(row.get("count") or 0)
        if not row.get("reassessment_candidate"):
            continue
        last = row.get("last_ts") if isinstance(row.get("last_ts"), str) else None
        detail = f"{count} hit(s), last={last or '-'}"
        observation_since = row.get("observation_since")
        if count == 0 and isinstance(observation_since, str) and observation_since:
            detail += f", observed_since={observation_since}"
        candidates.append(
            _candidate(
                key=f"guard:{guard}@{project_name}",
                kind="guard",
                project=project_name,
                scope_path=project_path,
                detail=detail,
                last_ts=last,
            )
        )
    return candidates


def _fleet_to_json(report: Any) -> dict[str, Any]:
    return {
        "run_count": report.run_count,
        "by_entry_point": report.by_entry_point,
        "pr_reviewer_fail_ratio": report.pr_reviewer_fail_ratio,
        "escalate_count": report.escalate_count,
        "blocked_event_count": report.blocked_event_count,
        "waste_top": report.waste_top,
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
    }


def _waste_candidates(
    project_name: str,
    project_path: Path,
    fleet: dict[str, Any],
    last_event_ts: Optional[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for candidate in fleet["improvement_candidates"]:
        pattern = str(candidate["pattern"])
        detail = f"{candidate['count']} occurrence(s), threshold={candidate['threshold']}"
        out.append(
            _candidate(
                key=f"waste:{pattern}@{project_name}",
                kind="waste",
                project=project_name,
                scope_path=project_path,
                detail=detail,
                last_ts=last_event_ts,
            )
        )
    return out


def _lesson_candidates(
    project_name: str,
    project_path: Path,
    lessons: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for lesson in lessons:
        pattern = str(lesson.get("pattern") or "")
        agent = str(lesson.get("agent") or "")
        mode = lesson.get("mode")
        label = agent + (f"-{mode}" if mode else "")
        hits = int(lesson.get("hits") or 0)
        last = lesson.get("last") if isinstance(lesson.get("last"), str) else None
        out.append(
            _candidate(
                key=f"lesson:{pattern}@{project_name}/{label}",
                kind="lesson",
                project=project_name,
                scope_path=project_path,
                detail=f"{pattern} active for {label}, hits={hits}",
                last_ts=last,
            )
        )
    return out


def _collect_project(path: Path, args: argparse.Namespace) -> dict[str, Any]:
    name = _project_name(path)
    events = read_events(cwd=path, since_days=args.since_days)
    sessions_root = path / ".claude" / "harness-state" / ".sessions"
    last_event_ts = _latest_project_ts(events, sessions_root)
    guard_summary = collect_guard_summary(
        cwd=path,
        idle_days=args.idle_days,
        since_days=args.since_days,
    )
    fleet_report = aggregate_sessions(
        sessions_root,
        top=args.waste_top,
        recurrence_threshold=args.recurrence_threshold,
        repo_override=path,
    )
    fleet = _fleet_to_json(fleet_report)
    candidates = _guard_candidates(name, path, guard_summary)
    candidates.extend(_waste_candidates(name, path, fleet, last_event_ts))
    # loop_diagnose only observes swept projects — never mutate their lesson files
    # (archiving is left to each project's own write path).
    lessons = list_active_lessons(path, archive=False)
    candidates.extend(_lesson_candidates(name, path, lessons))
    return {
        "name": name,
        "path": str(path),
        "telemetry_event_count": len(events),
        "last_event_ts": last_event_ts,
        "observation": "observed" if events else NO_OBSERVATION,
        "guard_summary": guard_summary,
        "fleet": fleet,
        "lessons": lessons,
        "candidates": candidates,
    }


def _cross_project_lesson_candidates(
    repo_root: Path,
    projects: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_pattern: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for project in projects:
        for lesson in project.get("lessons", []):
            if not isinstance(lesson, dict):
                continue
            pattern = str(lesson.get("pattern") or "")
            if pattern:
                row = dict(lesson)
                row["project_name"] = project["name"]
                by_pattern[pattern].append(row)

    out: list[dict[str, Any]] = []
    for pattern, rows in sorted(by_pattern.items()):
        projects_with_pattern = sorted({str(row["project_name"]) for row in rows})
        if len(projects_with_pattern) < 2:
            continue
        last = _max_ts([row.get("last") for row in rows])
        detail = (
            f"active in {len(projects_with_pattern)} project(s): "
            + ", ".join(projects_with_pattern)
        )
        out.append(
            _candidate(
                key=f"lesson-rule:{pattern}",
                kind="lesson-rule",
                project="cross-project",
                scope_path=repo_root,
                detail=detail,
                last_ts=last,
            )
        )
    return out


def _collect_self_evals(repo_root: Path, args: argparse.Namespace) -> dict[str, Any]:
    summary = collect_eval_summary(
        cwd=repo_root,
        saturation_days=args.saturation_days,
        saturation_min_runs=args.saturation_min_runs,
    )
    candidates: list[dict[str, Any]] = []
    cases = summary.get("cases")
    if isinstance(cases, dict):
        for case, raw in sorted(cases.items()):
            row = raw if isinstance(raw, dict) else {}
            if not row.get("saturation_candidate"):
                continue
            attempts = int(row.get("attempts") or 0)
            passes = int(row.get("passes") or 0)
            accuracy = float(row.get("accuracy") or 0.0)
            detail = f"{passes}/{attempts} pass, accuracy={accuracy:.0%}"
            last = row.get("last_ts") if isinstance(row.get("last_ts"), str) else None
            candidates.append(
                _candidate(
                    key=f"eval:{case}",
                    kind="eval",
                    project="dcness-self",
                    scope_path=repo_root,
                    detail=detail,
                    last_ts=last,
                )
            )
    return {
        "repo_root": str(repo_root),
        "summary": summary,
        "candidates": candidates,
        "last_event_ts": _max_ts([c.get("last_ts") for c in candidates]),
    }


def _latest_sweep(repo_root: Path) -> Optional[dict[str, Any]]:
    rows = _read_jsonl(repo_root / SWEEP_PATH)
    return rows[-1] if rows else None


def _previous_records(previous: Optional[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not isinstance(previous, dict) or not isinstance(previous.get("projects"), list):
        return {}
    records: dict[str, dict[str, Any]] = {}
    for raw in previous["projects"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("path"), str):
            continue
        records[raw["path"]] = raw
    return records


def _freshness(candidate: dict[str, Any], previous: Optional[dict[str, Any]]) -> str:
    records = _previous_records(previous)
    record = records.get(str(candidate.get("scope_path") or ""))
    if record is None:
        return "신규"
    previous_ts = record.get("last_event_ts") if isinstance(record.get("last_event_ts"), str) else None
    previous_keys = record.get("candidates") if isinstance(record.get("candidates"), list) else []
    key = str(candidate.get("key") or "")
    if key not in previous_keys:
        return f"신규 발생 since {previous_ts}" if previous_ts else "신규"
    current_dt = _parse_ts(candidate.get("last_ts"))
    previous_dt = _parse_ts(previous_ts)
    if current_dt is not None and previous_dt is not None and current_dt > previous_dt:
        return f"신규 발생 since {previous_ts}"
    return "기왕"


def _load_decisions(repo_root: Path) -> dict[str, dict[str, Any]]:
    decisions: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(repo_root / DECISIONS_PATH):
        key = row.get("key")
        decision = row.get("decision")
        ref = row.get("ref")
        if not isinstance(key, str) or decision not in VALID_DECISIONS:
            continue
        if not isinstance(ref, str) or not ref.strip():
            continue
        decisions[key] = row
    return decisions


def _decision_annotation(decision: Optional[dict[str, Any]]) -> str:
    if not decision:
        return "-"
    label = DECISION_LABELS.get(str(decision.get("decision")), str(decision.get("decision")))
    decided_at = str(decision.get("decided_at") or "")
    date = decided_at[:10] if decided_at else "-"
    ref = str(decision.get("ref") or "-")
    return f"이전 결정: {label} {date} {ref}"


def _attach_status(
    candidates: list[dict[str, Any]],
    *,
    previous: Optional[dict[str, Any]],
    decisions: dict[str, dict[str, Any]],
) -> None:
    for candidate in candidates:
        candidate["freshness"] = _freshness(candidate, previous)
        decision = decisions.get(str(candidate.get("key") or ""))
        candidate["decision"] = decision
        candidate["decision_annotation"] = _decision_annotation(decision)


def _visible_candidates(candidates: list[dict[str, Any]], hide_decided: bool) -> list[dict[str, Any]]:
    if not hide_decided:
        return candidates
    visible: list[dict[str, Any]] = []
    for candidate in candidates:
        decision = candidate.get("decision")
        if isinstance(decision, dict) and decision.get("decision") in {"fixed", "rejected"}:
            continue
        visible.append(candidate)
    return visible


def _sweep_project_records(
    projects: list[dict[str, Any]],
    evals: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_path: dict[str, dict[str, Any]] = {}
    for project in projects:
        by_path[str(project["path"])] = {
            "path": project["path"],
            "last_event_ts": project.get("last_event_ts"),
            "candidates": [],
        }
    eval_path = str(evals["repo_root"])
    by_path.setdefault(
        eval_path,
        {
            "path": eval_path,
            "last_event_ts": evals.get("last_event_ts"),
            "candidates": [],
        },
    )
    grouped: dict[str, list[str]] = defaultdict(list)
    for candidate in candidates:
        grouped[str(candidate["scope_path"])].append(str(candidate["key"]))
    for path, keys in grouped.items():
        by_path.setdefault(path, {"path": path, "last_event_ts": None, "candidates": []})
        by_path[path]["candidates"] = sorted(set(keys))
    return [by_path[path] for path in sorted(by_path)]


def _append_sweep(
    repo_root: Path,
    *,
    swept_at: str,
    projects: list[dict[str, Any]],
    evals: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> None:
    payload = {
        "swept_at": swept_at,
        "projects": _sweep_project_records(projects, evals, candidates),
    }
    _append_jsonl(repo_root / SWEEP_PATH, payload)


def _digest_dir(args: argparse.Namespace) -> Path:
    if getattr(args, "digest_dir", ""):
        return Path(args.digest_dir).expanduser()
    repo_root = Path(args.repo_root).expanduser().resolve()
    return repo_root / SWEEP_PATH.parent


def _write_digest(digest_dir: Path, markdown: str) -> Path:
    digest_dir.mkdir(parents=True, exist_ok=True)
    target = digest_dir / DIGEST_FILENAME
    tmp = digest_dir / (DIGEST_FILENAME + ".tmp")
    tmp.write_text(markdown, encoding="utf-8")
    os.replace(tmp, target)
    return target


def _append_sweep_log(digest_dir: Path, entry: dict[str, Any]) -> None:
    _append_jsonl(digest_dir / SWEEP_LOG_FILENAME, entry)


def build_payload(args: argparse.Namespace, *, write_watermark: bool = True) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    projects_file = Path(args.projects_file).expanduser().resolve()
    swept_at = _now_iso()
    previous = _latest_sweep(repo_root)
    decisions = _load_decisions(repo_root)
    projects = [_collect_project(path, args) for path in _load_projects(projects_file)]
    evals = _collect_self_evals(repo_root, args)

    candidates: list[dict[str, Any]] = []
    for project in projects:
        candidates.extend(project["candidates"])
    candidates.extend(_cross_project_lesson_candidates(repo_root, projects))
    candidates.extend(evals["candidates"])
    _attach_status(candidates, previous=previous, decisions=decisions)
    if write_watermark:
        _append_sweep(
            repo_root,
            swept_at=swept_at,
            projects=projects,
            evals=evals,
            candidates=candidates,
        )

    payload = {
        "swept_at": swept_at,
        "projects_file": str(projects_file),
        "state_file": str(repo_root / SWEEP_PATH),
        "decisions_file": str(repo_root / DECISIONS_PATH),
        "projects": projects,
        "evals": evals,
        "candidates": _visible_candidates(candidates, bool(args.hide_decided)),
    }
    if not write_watermark:
        # The caller advances the watermark itself, after the digest is durable, so a
        # persistence failure never marks these candidates as seen (freshness would drop
        # to 기왕 and the signal would be lost). Full candidate list — not the visibility
        # filtered view — so the watermark records every key observed this sweep.
        payload["_pending_watermark"] = {
            "repo_root": repo_root,
            "swept_at": swept_at,
            "projects": projects,
            "evals": evals,
            "candidates": candidates,
        }
    return payload


def _md_cell(value: Any) -> str:
    text = str(value if value is not None else "-")
    return text.replace("|", "\\|").replace("\n", " ")


def _render_project(project: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    lines.append(f"## 프로젝트: {project['name']}")
    lines.append("")
    lines.append(f"- path: `{project['path']}`")
    if project["observation"] == NO_OBSERVATION:
        lines.append(f"- telemetry: {NO_OBSERVATION}")
    else:
        lines.append(
            f"- telemetry: {project['telemetry_event_count']} event(s), "
            f"last={project.get('last_event_ts') or '-'}"
        )
    fleet = project["fleet"]
    lines.append(
        f"- fleet runs: {fleet['run_count']}, "
        f"recurrent waste candidates: {len(fleet['improvement_candidates'])}"
    )
    lessons = project.get("lessons") if isinstance(project.get("lessons"), list) else []
    lines.append(f"- active lessons: {len(lessons)}")
    lines.append("")
    lines.append("| guard | count | last | status |")
    lines.append("|---|---:|---|---|")
    guards = project["guard_summary"].get("guards", {})
    if isinstance(guards, dict):
        for guard, raw in sorted(guards.items()):
            row = raw if isinstance(raw, dict) else {}
            status = _guard_status_label(row)
            lines.append(
                f"| {_md_cell(guard)} | {int(row.get('count') or 0)} | "
                f"{_md_cell(row.get('last_ts') or '-')} | {status} |"
            )
    lines.append("")
    if lessons:
        lines.append("| lesson pattern | agent/mode | hits | last |")
        lines.append("|---|---|---:|---|")
        for lesson in lessons:
            agent = str(lesson.get("agent") or "")
            mode = lesson.get("mode")
            label = agent + (f"/{mode}" if mode else "")
            lines.append(
                f"| `{_md_cell(lesson.get('pattern'))}` | {_md_cell(label)} | "
                f"{int(lesson.get('hits') or 0)} | {_md_cell(lesson.get('last') or '-')} |"
            )
        lines.append("")
    return lines


def _guard_status_label(row: dict[str, Any]) -> str:
    status = row.get("observation_status")
    if status == "no_observation":
        return "관측 없음"
    if status == "insufficient_observation":
        return "관측 부족"
    return "재평가 후보" if row.get("reassessment_candidate") else "active"


def render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# loop-diagnose report")
    lines.append("")
    lines.append(f"- swept_at: `{payload['swept_at']}`")
    lines.append(f"- projects_file: `{payload['projects_file']}`")
    lines.append(f"- state_file: `{payload['state_file']}`")
    lines.append(f"- decisions_file: `{payload['decisions_file']}`")
    lines.append("")
    for project in payload["projects"]:
        lines.extend(_render_project(project))

    lines.append("## 통합 후보")
    lines.append("")
    candidates = payload["candidates"]
    if candidates:
        lines.append("| key | kind | project | detail | last | 상태 | 결정 |")
        lines.append("|---|---|---|---|---|---|---|")
        for candidate in candidates:
            lines.append(
                f"| `{_md_cell(candidate['key'])}` | {_md_cell(candidate['kind'])} | "
                f"{_md_cell(candidate['project'])} | {_md_cell(candidate['detail'])} | "
                f"{_md_cell(candidate.get('last_ts') or '-')} | "
                f"{_md_cell(candidate.get('freshness') or '-')} | "
                f"{_md_cell(candidate.get('decision_annotation') or '-')} |"
            )
    else:
        lines.append("(후보 없음)")
    lines.append("")
    lines.append("## 수동 절차")
    lines.append("")
    lines.append(
        "- judge 보정은 자동 수집하지 않습니다. 필요 시 `evals/calibrate_judge.py`를 "
        "수동 실행하고 결과를 별도 Decide 입력으로 남깁니다."
    )
    lines.append(
        "- 자동 수정과 자동 이슈 생성은 하지 않습니다. 후보를 이슈로 남길 때는 "
        "직접 gh issue create 대신 /to-issue 를 사용하고, 검토 뒤 "
        "`record-decision`으로 소비 표식을 남깁니다."
    )
    lines.append("")
    return "\n".join(lines)


def _action_candidate(candidates: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    actionable = [
        row
        for row in candidates
        if not (
            isinstance(row.get("decision"), dict)
            and row["decision"].get("decision") in {"fixed", "rejected"}
        )
    ]
    if not actionable:
        return None
    return min(
        actionable,
        key=lambda row: (
            0 if str(row.get("freshness") or "").startswith("신규") else 1,
            ACTION_PRIORITY.get(str(row.get("kind") or ""), 99),
            str(row.get("key") or ""),
        ),
    )


def render_action_brief(payload: dict[str, Any]) -> str:
    """Render the one decision worth putting in front of the user now.

    This deliberately avoids exposing the sweep table or internal research terms. The
    detailed report remains available for audit, while /run-review only asks for the
    approval that can spend LLM trials.
    """
    candidate = _action_candidate(payload["candidates"])
    if candidate is None:
        return "지금 검토할 하네스 개선 후보가 없습니다. 다음 run을 진행해도 됩니다."

    kind = str(candidate.get("kind") or "")
    if kind == "waste":
        expected = "반복 탐색이나 재시도를 줄이면서 같은 품질 경계를 유지하는지 확인"
    elif kind in {"lesson", "lesson-rule"}:
        expected = "반복 안내를 더 짧게 만들어도 재발 방지 효과가 유지되는지 확인"
    elif kind == "eval":
        expected = "포화된 검사를 줄여도 핵심 사고 회귀 검출력이 유지되는지 확인"
    else:
        expected = "반복 비용을 줄일 여지가 있는지 shadow fixture에서 먼저 확인"

    return "\n".join(
        [
            "우선 검토 후보가 1건 있습니다.",
            f"- 대상 구성요소: {candidate['key']}",
            f"- 반복 근거: {candidate['detail']}",
            f"- 기대 효과: {expected}",
            (
                "- 안전 경계: 작업 순서·파일 경계·외부 상태 변경·TDD 보호는 "
                "live run에서 그대로 유지하고 격리 fixture만 비교"
            ),
            "- 예상 LLM trial: 2회(동일 task baseline 1회 + 경량 variant 1회)",
            "이 하네스 경량화 실험을 실행할까요? 결과는 유지 / 줄이기 후보 / 보류로 보고합니다.",
        ]
    )


def record_decision(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).expanduser().resolve()
    key = str(args.key or "").strip()
    ref = str(args.ref or "").strip()
    if not key:
        print("record-decision: --key is required", file=sys.stderr)
        return 2
    if args.decision not in VALID_DECISIONS:
        print("record-decision: invalid --decision", file=sys.stderr)
        return 2
    if not ref:
        print("record-decision: --ref is required", file=sys.stderr)
        return 2
    payload = {
        "key": key,
        "decision": args.decision,
        "ref": ref,
        "decided_at": args.decided_at or _now_iso(),
    }
    note = str(args.note or "").strip()
    if note:
        payload["note"] = note
    _append_jsonl(repo_root / DECISIONS_PATH, payload)
    print(f"recorded decision: {key} -> {args.decision} {ref}")
    return 0


def _projects_file_default() -> str:
    return os.environ.get("DCNESS_PROJECTS_FILE") or str(DEFAULT_PROJECTS_FILE)


def _add_common_report_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo-root", default=str(Path.cwd()))
    parser.add_argument("--projects-file", default=_projects_file_default())
    parser.add_argument("--idle-days", type=int, default=30)
    parser.add_argument("--since-days", type=int, default=DEFAULT_REPORT_SINCE_DAYS)
    parser.add_argument("--saturation-days", type=int, default=30)
    parser.add_argument("--saturation-min-runs", type=int, default=3)
    parser.add_argument("--waste-top", type=int, default=10)
    parser.add_argument("--recurrence-threshold", type=int, default=3)
    parser.add_argument("--hide-decided", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--action-brief", action="store_true")
    parser.add_argument("--no-watermark", action="store_true")


def _build_report_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loop_diagnose.py",
        description="Sweep active dcNess projects and surface Diagnose candidates.",
    )
    _add_common_report_args(parser)
    return parser


def _build_sweep_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loop_diagnose.py sweep",
        description="Run an unattended sweep and persist a digest for later human review.",
    )
    _add_common_report_args(parser)
    parser.add_argument("--digest-dir", default="")
    return parser


def _build_decision_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loop_diagnose.py record-decision")
    parser.add_argument("--repo-root", default=str(Path.cwd()))
    parser.add_argument("--key", required=True)
    parser.add_argument("--decision", required=True, choices=sorted(VALID_DECISIONS))
    parser.add_argument("--ref", required=True)
    parser.add_argument("--note", default="")
    parser.add_argument("--decided-at", default="")
    return parser


def _run_report(argv: list[str]) -> int:
    args = _build_report_parser().parse_args(argv)
    payload = build_payload(args, write_watermark=not args.no_watermark)
    payload.pop("_pending_watermark", None)
    if args.action_brief:
        print(render_action_brief(payload))
    elif args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(payload))
    return 0


def _run_sweep(args: argparse.Namespace) -> int:
    """Unattended sweep: persist a digest, then advance the watermark, always leaving a
    trace. The watermark is written only after the digest is durable so a persistence
    failure neither hides fresh signal nor vanishes without a status:error entry."""
    digest_dir = _digest_dir(args)
    swept_at = _now_iso()
    try:
        payload = build_payload(args, write_watermark=False)
        pending = payload.pop("_pending_watermark")
        target = _write_digest(digest_dir, DIGEST_NOTE + render_markdown(payload))
        _append_sweep(
            pending["repo_root"],
            swept_at=pending["swept_at"],
            projects=pending["projects"],
            evals=pending["evals"],
            candidates=pending["candidates"],
        )
        _append_sweep_log(
            digest_dir,
            {
                "swept_at": payload["swept_at"],
                "status": "ok",
                "candidate_count": len(payload["candidates"]),
                "digest_path": str(target),
            },
        )
    except Exception as exc:  # noqa: BLE001 - a failed scheduled sweep must leave a trace
        print(f"loop sweep failed: {exc!r}", file=sys.stderr)
        try:
            _append_sweep_log(digest_dir, {"swept_at": swept_at, "status": "error", "error": repr(exc)})
        except OSError as log_exc:
            print(f"loop sweep: could not write failure log: {log_exc!r}", file=sys.stderr)
        return 1
    print(f"loop sweep ok: digest -> {target}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "record-decision":
        args = _build_decision_parser().parse_args(argv[1:])
        return record_decision(args)
    if argv and argv[0] == "sweep":
        args = _build_sweep_parser().parse_args(argv[1:])
        return _run_sweep(args)
    if argv and argv[0] == "report":
        argv = argv[1:]
    return _run_report(argv)


if __name__ == "__main__":
    raise SystemExit(main())

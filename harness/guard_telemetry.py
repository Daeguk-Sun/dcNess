"""Guard/eval telemetry append log (#875).

The log is append-only JSONL. Guard hits are written next to run artifacts when
session/run context is known, and to the project state root as a fallback. Eval
case results use the same event schema and aggregation helpers.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from harness.session_state import RUN_ID_RE, run_dir, valid_session_id


TELEMETRY_NAME = "guard-telemetry.jsonl"
DEFAULT_IDLE_DAYS = 30
DEFAULT_REPORT_SINCE_DAYS = 90
DEFAULT_SATURATION_DAYS = 30
DEFAULT_SATURATION_MIN_RUNS = 3
OUTPUT_ESTIMATE_BASIS = "utf8_bytes/4_lower_bound"

DISTRIBUTED_KNOWN_GUARDS: tuple[str, ...] = (
    "catastrophic-gate",
    "file-guard",
    "tdd-guard",
    "git-commit-msg",
    "git-pre-push",
    "git-pre-commit",
)
SELF_ONLY_KNOWN_GUARDS: tuple[str, ...] = ()
KNOWN_GUARDS: tuple[str, ...] = DISTRIBUTED_KNOWN_GUARDS

_DETAIL_MAX = 500


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


def _resolve_project_root(cwd: Optional[Path] = None) -> Path:
    probe = Path(cwd or Path.cwd()).resolve()
    try:
        import subprocess  # nosec B404

        result = subprocess.run(  # nosec B603, B607
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(probe),
            capture_output=True,
            text=True,
            check=True,
            timeout=2.0,
        )
        root = result.stdout.strip()
        if root:
            return Path(root).resolve()
    except Exception:  # noqa: BLE001 # nosec B110
        pass
    return probe


def _project_log_path(cwd: Optional[Path] = None, *, base_dir: Optional[Path] = None) -> Path:
    if base_dir is not None:
        return Path(base_dir).resolve() / TELEMETRY_NAME
    return _resolve_project_root(cwd) / ".claude" / "harness-state" / TELEMETRY_NAME


def _event_path(
    *,
    session_id: Optional[str] = None,
    run_id: Optional[str] = None,
    cwd: Optional[Path] = None,
    base_dir: Optional[Path] = None,
) -> Path:
    if (
        isinstance(session_id, str)
        and valid_session_id(session_id)
        and isinstance(run_id, str)
        and RUN_ID_RE.match(run_id)
    ):
        try:
            return run_dir(session_id, run_id, base_dir=base_dir, create=True) / TELEMETRY_NAME
        except Exception:  # noqa: BLE001 # nosec B110
            pass
    return _project_log_path(cwd, base_dir=base_dir)


def append_event(
    event: Dict[str, Any],
    *,
    session_id: Optional[str] = None,
    run_id: Optional[str] = None,
    cwd: Optional[Path] = None,
    base_dir: Optional[Path] = None,
) -> None:
    """Append one telemetry event.

    Raises TypeError for caller bugs. I/O failures stay silent because hook
    telemetry must never change the original guard decision.
    """
    if not isinstance(event, dict):
        raise TypeError(f"event must be dict, got {type(event).__name__}")
    try:
        payload = dict(event)
        payload.setdefault("ts", _now_iso())
        if session_id and valid_session_id(session_id):
            payload.setdefault("session_id", session_id)
        if run_id and isinstance(run_id, str) and RUN_ID_RE.match(run_id):
            payload.setdefault("run_id", run_id)
        target = _event_path(
            session_id=session_id,
            run_id=run_id,
            cwd=cwd,
            base_dir=base_dir,
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        needs_epoch = (
            payload.get("kind") != "telemetry_epoch"
            and (not target.exists() or target.stat().st_size == 0)
        )
        lines: list[Dict[str, Any]] = []
        if needs_epoch:
            lines.append({"kind": "telemetry_epoch", "ts": payload["ts"]})
        lines.append(payload)
        fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            for item in lines:
                line = json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
                os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
    except Exception:  # noqa: BLE001 # nosec B110
        pass


def record_guard_hit(
    guard: str,
    *,
    category: str = "block",
    detail: str = "",
    source: str = "git_hook",
    session_id: Optional[str] = None,
    run_id: Optional[str] = None,
    cwd: Optional[Path] = None,
    base_dir: Optional[Path] = None,
) -> None:
    guard_s = str(guard or "unknown")[:120]
    category_s = str(category or "block")[:120]
    detail_s = str(detail or "").replace("\n", " ")[:_DETAIL_MAX]
    source_s = str(source or "unknown")[:80]
    append_event(
        {
            "kind": "guard_hit",
            "guard": guard_s,
            "category": category_s,
            "source": source_s,
            "detail": detail_s,
        },
        session_id=session_id,
        run_id=run_id,
        cwd=cwd,
        base_dir=base_dir,
    )


def record_eval_case_result(
    case: str,
    *,
    passed: bool,
    run_index: Optional[int] = None,
    total_runs: Optional[int] = None,
    report_file: str = "",
    judge_file: str = "",
    model: str = "",
    llm_turns: Optional[int] = None,
    report_chars: Optional[int] = None,
    judge_chars: Optional[int] = None,
    estimated_output_tokens: Optional[int] = None,
    failure_stage: str = "",
    failure_detail: str = "",
    token_estimate_basis: str = "",
    cwd: Optional[Path] = None,
    base_dir: Optional[Path] = None,
) -> None:
    event: Dict[str, Any] = {
        "kind": "eval_case_result",
        "case": str(case or "unknown")[:160],
        "passed": bool(passed),
    }
    if run_index is not None:
        event["run_index"] = int(run_index)
    if total_runs is not None:
        event["total_runs"] = int(total_runs)
    if report_file:
        event["report_file"] = str(report_file)
    if judge_file:
        event["judge_file"] = str(judge_file)
    if model:
        event["model"] = str(model)
    if failure_stage:
        event["failure_stage"] = str(failure_stage)[:80]
    if failure_detail:
        event["failure_detail"] = str(failure_detail).replace("\n", " ")[:_DETAIL_MAX]
    if token_estimate_basis:
        event["token_estimate_basis"] = str(token_estimate_basis)[:120]
    for key, value in (
        ("llm_turns", llm_turns),
        ("report_chars", report_chars),
        ("judge_chars", judge_chars),
        ("estimated_output_tokens", estimated_output_tokens),
    ):
        if value is not None:
            event[key] = max(int(value), 0)
    append_event(event, cwd=cwd, base_dir=base_dir)


def _candidate_log_paths(cwd: Optional[Path] = None, *, base_dir: Optional[Path] = None) -> list[Path]:
    project_root = _resolve_project_root(cwd)
    root = (
        Path(base_dir).resolve()
        if base_dir is not None
        else project_root / ".claude" / "harness-state"
    )
    paths: list[Path] = [root / TELEMETRY_NAME]
    sessions = root / ".sessions"
    if sessions.is_dir():
        try:
            for path in sessions.glob("*/runs/*/" + TELEMETRY_NAME):
                paths.append(path)
        except OSError:
            pass
    if base_dir is None:
        evals_root = project_root / ".metrics" / "evals"
        if evals_root.is_dir():
            try:
                for path in evals_root.glob("*/" + TELEMETRY_NAME):
                    paths.append(path)
            except OSError:
                pass
    # Preserve deterministic order while avoiding duplicate paths.
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def _has_nonempty_log_path(
    cwd: Optional[Path] = None, *, base_dir: Optional[Path] = None
) -> bool:
    for path in _candidate_log_paths(cwd, base_dir=base_dir):
        try:
            if path.is_file() and path.stat().st_size > 0:
                return True
        except OSError:
            continue
    return False


def read_events(
    cwd: Optional[Path] = None,
    *,
    base_dir: Optional[Path] = None,
    since_days: Optional[int] = None,
    limit: Optional[int] = None,
) -> list[Dict[str, Any]]:
    cutoff = None
    if since_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)

    events: list[Dict[str, Any]] = []
    for path in _candidate_log_paths(cwd, base_dir=base_dir):
        try:
            if not path.exists():
                continue
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(row, dict):
                        continue
                    if cutoff is not None:
                        parsed = _parse_ts(row.get("ts"))
                        if parsed is None or parsed < cutoff:
                            continue
                    events.append(row)
        except OSError:
            continue
    events.sort(key=lambda row: str(row.get("ts") or ""))
    if limit == 0:
        return []
    if limit is not None and limit > 0:
        return events[-limit:]
    return events


def collect_guard_summary(
    cwd: Optional[Path] = None,
    *,
    base_dir: Optional[Path] = None,
    known_guards: Iterable[str] = KNOWN_GUARDS,
    idle_days: int = DEFAULT_IDLE_DAYS,
    since_days: Optional[int] = None,
) -> Dict[str, Any]:
    all_events = read_events(cwd, base_dir=base_dir, since_days=since_days)
    events = [
        event for event in all_events
        if event.get("kind") == "guard_hit"
    ]
    rows: dict[str, Dict[str, Any]] = {}
    for guard in known_guards:
        rows[str(guard)] = {
            "count": 0,
            "last_ts": None,
            "categories": {},
            "sources": [],
            "reassessment_candidate": True,
            "observation_since": None,
            "observation_days": None,
            "observation_status": "no_observation",
        }
    for event in events:
        guard = str(event.get("guard") or "unknown")
        row = rows.setdefault(
            guard,
            {
                "count": 0,
                "last_ts": None,
                "categories": {},
                "sources": [],
                "reassessment_candidate": True,
                "observation_since": None,
                "observation_days": None,
                "observation_status": "no_observation",
            },
        )
        row["count"] += 1
        ts = str(event.get("ts") or "")
        if ts and (row["last_ts"] is None or ts > row["last_ts"]):
            row["last_ts"] = ts
        category = str(event.get("category") or "unknown")
        row["categories"][category] = row["categories"].get(category, 0) + 1
        source = str(event.get("source") or "unknown")
        if source not in row["sources"]:
            row["sources"].append(source)

    now = datetime.now(timezone.utc)
    idle_days_i = max(int(idle_days), 0)
    cutoff = now - timedelta(days=idle_days_i)
    epoch_candidates = [
        _parse_ts(event.get("ts"))
        for event in all_events
        if event.get("kind") == "telemetry_epoch"
    ]
    epoch = min((ts for ts in epoch_candidates if ts is not None), default=None)
    if epoch is None:
        event_candidates = [_parse_ts(event.get("ts")) for event in all_events]
        epoch = min((ts for ts in event_candidates if ts is not None), default=None)
    if epoch is None and since_days is not None and _has_nonempty_log_path(cwd, base_dir=base_dir):
        epoch = now - timedelta(days=max(int(since_days), 0))

    observation_days: Optional[int] = None
    observation_since: Optional[str] = None
    if epoch is not None:
        observation_days = max((now - epoch).days, 0)
        observation_since = epoch.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    for row in rows.values():
        parsed = _parse_ts(row.get("last_ts"))
        if epoch is None:
            status = "no_observation"
        elif int(row.get("count") or 0) == 0 and (observation_days or 0) < idle_days_i:
            status = "insufficient_observation"
        else:
            status = "observed"
        row["observation_since"] = observation_since
        row["observation_days"] = observation_days
        row["observation_status"] = status
        if parsed is not None:
            row["reassessment_candidate"] = parsed < cutoff
        else:
            row["reassessment_candidate"] = (
                status == "observed" and (observation_days or 0) >= idle_days_i
            )
        row["sources"] = sorted(row["sources"])
    return {"idle_days": idle_days, "since_days": since_days, "guards": rows}


def collect_eval_summary(
    cwd: Optional[Path] = None,
    *,
    base_dir: Optional[Path] = None,
    saturation_days: int = DEFAULT_SATURATION_DAYS,
    saturation_min_runs: int = DEFAULT_SATURATION_MIN_RUNS,
) -> Dict[str, Any]:
    events = [
        event for event in read_events(cwd, base_dir=base_dir, since_days=saturation_days)
        if event.get("kind") == "eval_case_result"
    ]
    rows: dict[str, Dict[str, Any]] = {}
    for event in events:
        case = str(event.get("case") or "unknown")
        row = rows.setdefault(
            case,
            {
                "attempts": 0,
                "passes": 0,
                "accuracy": 0.0,
                "llm_turns": 0,
                "estimated_output_tokens": 0,
                "report_chars": 0,
                "judge_chars": 0,
                "avg_llm_turns": 0.0,
                "avg_estimated_output_tokens": 0.0,
                "failure_stages": {},
                "last_ts": None,
                "saturation_candidate": False,
            },
        )
        row["attempts"] += 1
        if event.get("passed") is True:
            row["passes"] += 1
        row["llm_turns"] += max(int(event.get("llm_turns") or 0), 0)
        row["estimated_output_tokens"] += max(
            int(event.get("estimated_output_tokens") or 0), 0
        )
        row["report_chars"] += max(int(event.get("report_chars") or 0), 0)
        row["judge_chars"] += max(int(event.get("judge_chars") or 0), 0)
        failure_stage = str(event.get("failure_stage") or "")
        if failure_stage:
            row["failure_stages"][failure_stage] = (
                row["failure_stages"].get(failure_stage, 0) + 1
            )
        ts = str(event.get("ts") or "")
        if ts and (row["last_ts"] is None or ts > row["last_ts"]):
            row["last_ts"] = ts

    min_runs = max(int(saturation_min_runs), 1)
    for row in rows.values():
        attempts = int(row["attempts"])
        passes = int(row["passes"])
        row["accuracy"] = (passes / attempts) if attempts else 0.0
        row["avg_llm_turns"] = (
            row["llm_turns"] / attempts if attempts else 0.0
        )
        row["avg_estimated_output_tokens"] = (
            row["estimated_output_tokens"] / attempts if attempts else 0.0
        )
        row["saturation_candidate"] = attempts >= min_runs and attempts == passes
    return {
        "saturation_days": saturation_days,
        "saturation_min_runs": saturation_min_runs,
        "token_estimate_basis": OUTPUT_ESTIMATE_BASIS,
        "cases": rows,
    }


def format_telemetry_report(
    guard_summary: Dict[str, Any],
    eval_summary: Optional[Dict[str, Any]] = None,
) -> str:
    lines: list[str] = []
    idle_days = int(guard_summary.get("idle_days") or DEFAULT_IDLE_DAYS)
    guard_header = f"[guard telemetry] guard hits — idle threshold: {idle_days}d"
    since_days = guard_summary.get("since_days")
    if since_days is not None:
        guard_header += f", scan window: {int(since_days)}d"
    lines.append(guard_header)
    guards = guard_summary.get("guards") if isinstance(guard_summary, dict) else {}
    if isinstance(guards, dict) and guards:
        for guard, row_any in sorted(guards.items()):
            row = row_any if isinstance(row_any, dict) else {}
            status = row.get("observation_status")
            if status == "no_observation":
                marker = "관측 없음"
            elif status == "insufficient_observation":
                marker = "관측 부족"
            else:
                marker = "재평가 후보" if row.get("reassessment_candidate") else "active"
            last = row.get("last_ts") or "-"
            count = int(row.get("count") or 0)
            lines.append(f"- {guard}: {count} hit(s), last={last}, {marker}")
    else:
        lines.append("- no guard telemetry events")

    if eval_summary is not None:
        saturation_days = int(eval_summary.get("saturation_days") or DEFAULT_SATURATION_DAYS)
        min_runs = int(eval_summary.get("saturation_min_runs") or DEFAULT_SATURATION_MIN_RUNS)
        lines.append(
            f"[guard telemetry] eval saturation — window: {saturation_days}d, min_runs={min_runs}"
        )
        if eval_summary.get("token_estimate_basis"):
            lines.append("[guard telemetry] 토큰 추정 하한 — UTF-8 bytes/4 기준")
        cases = eval_summary.get("cases") if isinstance(eval_summary, dict) else {}
        if isinstance(cases, dict) and cases:
            for case, row_any in sorted(cases.items()):
                row = row_any if isinstance(row_any, dict) else {}
                marker = "노후 후보" if row.get("saturation_candidate") else "active"
                attempts = int(row.get("attempts") or 0)
                passes = int(row.get("passes") or 0)
                accuracy = float(row.get("accuracy") or 0.0)
                avg_turns = float(row.get("avg_llm_turns") or 0.0)
                avg_tokens = float(row.get("avg_estimated_output_tokens") or 0.0)
                last = row.get("last_ts") or "-"
                failures = row.get("failure_stages") if isinstance(row, dict) else {}
                failure_note = ""
                if isinstance(failures, dict) and failures:
                    failure_note = ", failures=" + ",".join(
                        f"{stage}:{count}" for stage, count in sorted(failures.items())
                    )
                lines.append(
                    f"- {case}: {passes}/{attempts} ({accuracy:.0%}), "
                    f"avg_turns={avg_turns:.1f}, avg_tokens≈{avg_tokens:.0f}, "
                    f"last={last}, {marker}{failure_note}"
                )
        else:
            lines.append("- no eval case telemetry events")
    lines.append("자동 비활성화 없음 — 판단과 제거는 사람이 한다.")
    return "\n".join(lines)


def _cli_record_hit(args: argparse.Namespace) -> int:
    record_guard_hit(
        args.guard,
        category=args.category,
        detail=args.detail,
        source=args.source,
        session_id=args.session_id,
        run_id=args.run_id,
        cwd=Path(args.cwd) if args.cwd else None,
        base_dir=Path(args.base_dir) if args.base_dir else None,
    )
    return 0


def _cli_record_eval(args: argparse.Namespace) -> int:
    record_eval_case_result(
        args.case,
        passed=args.passed,
        run_index=args.run_index,
        total_runs=args.total_runs,
        report_file=args.report_file or "",
        judge_file=args.judge_file or "",
        model=args.model or "",
        llm_turns=args.llm_turns,
        report_chars=args.report_chars,
        judge_chars=args.judge_chars,
        estimated_output_tokens=args.estimated_output_tokens,
        failure_stage=args.failure_stage or "",
        failure_detail=args.failure_detail or "",
        token_estimate_basis=args.token_estimate_basis or "",
        cwd=Path(args.cwd) if args.cwd else None,
        base_dir=Path(args.base_dir) if args.base_dir else None,
    )
    return 0


def _cli_report(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd) if args.cwd else None
    base_dir = Path(args.base_dir) if args.base_dir else None
    since_days = args.since_days if args.since_days and args.since_days > 0 else None
    guard_summary = collect_guard_summary(
        cwd,
        base_dir=base_dir,
        idle_days=args.idle_days,
        since_days=since_days,
    )
    eval_summary = collect_eval_summary(
        cwd,
        base_dir=base_dir,
        saturation_days=args.saturation_days,
        saturation_min_runs=args.saturation_min_runs,
    )
    if args.json:
        print(json.dumps({"guards": guard_summary, "evals": eval_summary}, ensure_ascii=False))
    else:
        print(format_telemetry_report(guard_summary, eval_summary))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m harness.guard_telemetry")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_hit = sub.add_parser("record-hit", help="internal: append guard hit event")
    p_hit.add_argument("--guard", required=True)
    p_hit.add_argument("--category", default="block")
    p_hit.add_argument("--detail", default="")
    p_hit.add_argument("--source", default="git_hook")
    p_hit.add_argument("--session-id", default="")
    p_hit.add_argument("--run-id", default="")
    p_hit.add_argument("--cwd", default="")
    p_hit.add_argument("--base-dir", default="")
    p_hit.set_defaults(func=_cli_record_hit)

    p_eval = sub.add_parser("record-eval", help="internal: append eval case result")
    p_eval.add_argument("--case", required=True)
    p_eval.add_argument("--passed", action="store_true")
    p_eval.add_argument("--failed", dest="passed", action="store_false")
    p_eval.set_defaults(passed=False)
    p_eval.add_argument("--run-index", type=int, default=None)
    p_eval.add_argument("--total-runs", type=int, default=None)
    p_eval.add_argument("--report-file", default="")
    p_eval.add_argument("--judge-file", default="")
    p_eval.add_argument("--model", default="")
    p_eval.add_argument("--llm-turns", type=int, default=None)
    p_eval.add_argument("--report-chars", type=int, default=None)
    p_eval.add_argument("--judge-chars", type=int, default=None)
    p_eval.add_argument("--estimated-output-tokens", type=int, default=None)
    p_eval.add_argument("--failure-stage", default="")
    p_eval.add_argument("--failure-detail", default="")
    p_eval.add_argument("--token-estimate-basis", default="")
    p_eval.add_argument("--cwd", default="")
    p_eval.add_argument("--base-dir", default="")
    p_eval.set_defaults(func=_cli_record_eval)

    p_report = sub.add_parser("report", help="summarize guard hits and eval saturation")
    p_report.add_argument("--idle-days", type=int, default=DEFAULT_IDLE_DAYS)
    p_report.add_argument("--since-days", type=int, default=DEFAULT_REPORT_SINCE_DAYS)
    p_report.add_argument("--saturation-days", type=int, default=DEFAULT_SATURATION_DAYS)
    p_report.add_argument("--saturation-min-runs", type=int, default=DEFAULT_SATURATION_MIN_RUNS)
    p_report.add_argument("--cwd", default="")
    p_report.add_argument("--base-dir", default="")
    p_report.add_argument("--json", action="store_true")
    p_report.set_defaults(func=_cli_report)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

"""Append-only receipts for guard blocks and source-checkout eval runs.

Runtime callers only record or read events. Aggregation and effectiveness
interpretation belong to repository-only tooling.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from harness.session_state import RUN_ID_RE, run_dir, valid_session_id


TELEMETRY_NAME = "guard-telemetry.jsonl"
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


def _project_log_path(cwd: Optional[Path], base_dir: Optional[Path]) -> Path:
    if base_dir is not None:
        return Path(base_dir).resolve() / TELEMETRY_NAME
    return _resolve_project_root(cwd) / ".claude" / "harness-state" / TELEMETRY_NAME


def _event_path(
    *,
    session_id: Optional[str],
    run_id: Optional[str],
    cwd: Optional[Path],
    base_dir: Optional[Path],
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
    return _project_log_path(cwd, base_dir)


def append_event(
    event: Dict[str, Any],
    *,
    session_id: Optional[str] = None,
    run_id: Optional[str] = None,
    cwd: Optional[Path] = None,
    base_dir: Optional[Path] = None,
) -> None:
    """Append one receipt without changing the caller's policy outcome."""
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
        rows = []
        if payload.get("kind") != "telemetry_epoch" and (
            not target.exists() or target.stat().st_size == 0
        ):
            rows.append({"kind": "telemetry_epoch", "ts": payload["ts"]})
        rows.append(payload)
        fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            for row in rows:
                encoded = (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
                os.write(fd, encoded)
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
    append_event(
        {
            "kind": "guard_hit",
            "guard": str(guard or "unknown")[:120],
            "category": str(category or "block")[:120],
            "source": str(source or "unknown")[:80],
            "detail": str(detail or "").replace("\n", " ")[:_DETAIL_MAX],
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
    for key, value, limit in (
        ("report_file", report_file, None),
        ("judge_file", judge_file, None),
        ("model", model, None),
        ("failure_stage", failure_stage, 80),
        ("token_estimate_basis", token_estimate_basis, 120),
    ):
        if value:
            rendered = str(value)
            event[key] = rendered[:limit] if limit else rendered
    if failure_detail:
        event["failure_detail"] = str(failure_detail).replace("\n", " ")[:_DETAIL_MAX]
    for key, index_value in (("run_index", run_index), ("total_runs", total_runs)):
        if index_value is not None:
            event[key] = int(index_value)
    for key, numeric_value in (
        ("llm_turns", llm_turns),
        ("report_chars", report_chars),
        ("judge_chars", judge_chars),
        ("estimated_output_tokens", estimated_output_tokens),
    ):
        if numeric_value is not None:
            event[key] = max(int(numeric_value), 0)
    append_event(event, cwd=cwd, base_dir=base_dir)


def _candidate_log_paths(cwd: Optional[Path], base_dir: Optional[Path]) -> list[Path]:
    project_root = _resolve_project_root(cwd)
    root = Path(base_dir).resolve() if base_dir is not None else project_root / ".claude" / "harness-state"
    paths = [root / TELEMETRY_NAME]
    sessions = root / ".sessions"
    if sessions.is_dir():
        try:
            paths.extend(sessions.glob(f"*/runs/*/{TELEMETRY_NAME}"))
        except OSError:
            pass
    if base_dir is None:
        metrics = project_root / ".metrics" / "evals"
        if metrics.is_dir():
            try:
                paths.extend(metrics.glob(f"*/{TELEMETRY_NAME}"))
            except OSError:
                pass
    return list(dict.fromkeys(path.resolve() for path in paths))


def read_events(
    cwd: Optional[Path] = None,
    *,
    base_dir: Optional[Path] = None,
    since_days: Optional[int] = None,
    limit: Optional[int] = None,
) -> list[Dict[str, Any]]:
    cutoff = None if since_days is None else datetime.now(timezone.utc) - timedelta(days=since_days)
    events: list[Dict[str, Any]] = []
    for path in _candidate_log_paths(cwd, base_dir):
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                if cutoff is not None:
                    timestamp = _parse_ts(row.get("ts"))
                    if timestamp is None or timestamp < cutoff:
                        continue
                events.append(row)
        except OSError:
            continue
    events.sort(key=lambda row: str(row.get("ts") or ""))
    if limit == 0:
        return []
    return events[-limit:] if limit is not None and limit > 0 else events


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m harness.guard_telemetry")
    sub = parser.add_subparsers(dest="cmd", required=True)
    hit = sub.add_parser("record-hit")
    hit.add_argument("--guard", required=True)
    hit.add_argument("--category", default="block")
    hit.add_argument("--detail", default="")
    hit.add_argument("--source", default="git_hook")
    hit.add_argument("--session-id", default="")
    hit.add_argument("--run-id", default="")
    hit.add_argument("--cwd", default="")
    hit.add_argument("--base-dir", default="")
    evaluation = sub.add_parser("record-eval")
    evaluation.add_argument("--case", required=True)
    evaluation.add_argument("--passed", action="store_true")
    evaluation.add_argument("--failed", dest="passed", action="store_false")
    evaluation.set_defaults(passed=False)
    for name in ("run-index", "total-runs", "llm-turns", "report-chars", "judge-chars", "estimated-output-tokens"):
        evaluation.add_argument(f"--{name}", type=int, default=None)
    for name in ("report-file", "judge-file", "model", "failure-stage", "failure-detail", "token-estimate-basis", "cwd", "base-dir"):
        evaluation.add_argument(f"--{name}", default="")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    cwd = Path(args.cwd) if args.cwd else None
    base_dir = Path(args.base_dir) if args.base_dir else None
    if args.cmd == "record-hit":
        record_guard_hit(
            args.guard,
            category=args.category,
            detail=args.detail,
            source=args.source,
            session_id=args.session_id,
            run_id=args.run_id,
            cwd=cwd,
            base_dir=base_dir,
        )
    else:
        record_eval_case_result(
            args.case,
            passed=args.passed,
            run_index=args.run_index,
            total_runs=args.total_runs,
            report_file=args.report_file,
            judge_file=args.judge_file,
            model=args.model,
            llm_turns=args.llm_turns,
            report_chars=args.report_chars,
            judge_chars=args.judge_chars,
            estimated_output_tokens=args.estimated_output_tokens,
            failure_stage=args.failure_stage,
            failure_detail=args.failure_detail,
            token_estimate_basis=args.token_estimate_basis,
            cwd=cwd,
            base_dir=base_dir,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

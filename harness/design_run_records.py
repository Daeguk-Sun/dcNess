"""Durable design run records.

`ledger.jsonl` remains the run-local source of truth, but it lives under
`.claude/harness-state/` and can be removed by local cleanup. This module writes
a compact design-run index into `docs/metrics/design-runs.jsonl` so a later
session can compare design baselines without the original session transcript or
run directory.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess  # nosec B404
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from harness import ledger
from harness import run_review


DESIGN_RUN_RECORD_REL = Path("docs/metrics/design-runs.jsonl")
SCHEMA_VERSION = 1
FINDING_CLASSES = ("SYSTEM_BOUNDARY", "CONTRACT_PROPAGATION", "TASK_LOCAL")
_NON_VERDICT_ENUMS = {"PROSE_LOGGED", "AMBIGUOUS", ""}


def _parse_iso(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_s(start: str, end: str) -> int:
    a = _parse_iso(start)
    b = _parse_iso(end)
    if not a or not b:
        return 0
    return max(0, int((b - a).total_seconds()))


def _repo_root_from_cwd(cwd: Optional[Path] = None) -> Path:
    probe = Path(cwd or Path.cwd()).resolve()
    try:
        result = subprocess.run(  # nosec B603, B607
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(probe),
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return probe
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return probe


def resolve_repo_root(path: Optional[Path] = None) -> Path:
    return _repo_root_from_cwd(path)


def design_record_path(repo_path: Path) -> Path:
    return resolve_repo_root(Path(repo_path)) / DESIGN_RUN_RECORD_REL


def _event_ts(events: list[dict[str, Any]], event_name: str, *, last: bool = False) -> str:
    iterable = reversed(events) if last else events
    for event in iterable:
        if event.get("event") == event_name:
            ts = event.get("ts")
            return ts if isinstance(ts, str) else ""
    return ""


def _entry_point(events: list[dict[str, Any]]) -> str:
    for event in events:
        if event.get("event") == "run_started":
            value = event.get("entry_point") or event.get("mode")
            return value if isinstance(value, str) else ""
    return ""


def _step_verdict(step: run_review.StepRecord) -> str:
    if step.enum and step.enum not in _NON_VERDICT_ENUMS:
        return step.enum
    return step.conclusion_enum or ""


def _finding_class_counts(text: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for klass in FINDING_CLASSES:
        hits = re.findall(rf"\b{re.escape(klass)}\b", text or "")
        if hits:
            counts[klass] = len(hits)
    return dict(counts)


def _unit_key(step: run_review.StepRecord) -> str:
    return f"{step.agent}:{step.mode}" if step.mode else step.agent


def _unit_records(steps: list[run_review.StepRecord]) -> list[dict[str, Any]]:
    seen: Counter[tuple[str, Optional[str]]] = Counter()
    units: list[dict[str, Any]] = []
    for step in steps:
        key = (step.agent, step.mode)
        cycle = seen[key]
        seen[key] += 1
        verdict = _step_verdict(step)
        finding_classes = (
            _finding_class_counts(step.prose_full)
            if ("FAIL" in verdict or "ESCALATE" in verdict)
            else {}
        )
        units.append(
            {
                "index": step.idx,
                "unit": _unit_key(step),
                "agent": step.agent,
                "mode": step.mode,
                "verdict": verdict,
                "cycle": cycle,
                "revalidation_cycle": max(0, cycle),
                "ts": step.ts,
                "elapsed_s": step.elapsed_s,
                "duration_ms": step.duration_ms,
                "output_tokens": step.output_tokens,
                "total_tokens": step.total_tokens,
                "finding_classes": finding_classes,
            }
        )
    return units


def build_design_record(run_dir: Path, repo_path: Optional[Path] = None) -> Optional[dict]:
    """Build one durable record from a finished design run.

    Returns None for non-design runs. `repo_path` controls where session JSONL is
    looked up for optional token/cost enrichment; when omitted, current cwd's git
    root is used.
    """
    run_dir = Path(run_dir)
    events = ledger.read_events_at(run_dir)
    if _entry_point(events) != "design":
        return None

    repo_root = resolve_repo_root(repo_path) if repo_path else resolve_repo_root()
    report = run_review.build_report(run_dir, repo_root)
    started_at = _event_ts(events, "run_started") or (report.steps[0].ts if report.steps else "")
    finished_at = (
        _event_ts(events, "run_finished", last=True)
        or (report.steps[-1].ts if report.steps else "")
    )
    units = _unit_records(report.steps)
    finding_totals: Counter[str] = Counter()
    for unit in units:
        finding_totals.update(unit["finding_classes"])

    occurrences: Counter[str] = Counter(unit["unit"] for unit in units)
    revalidation_cycles = {
        unit: count - 1 for unit, count in sorted(occurrences.items()) if count > 1
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": "design_run",
        "run_id": report.run_id,
        "session_id": report.session_id,
        "entry_point": "design",
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_s": _duration_s(started_at, finished_at),
        "step_count": len(report.steps),
        "final_verdict": report.final_enum,
        "clean": report.final_clean,
        "finding_classes": dict(finding_totals),
        "revalidation_cycles": revalidation_cycles,
        "total_input_tokens": report.total_input_tokens,
        "total_output_tokens": report.total_output_tokens,
        "total_cost_usd": report.total_cost_usd,
        "units": units,
    }


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(value)
    except OSError:
        return []
    return records


def load_records(repo_path: Path) -> list[dict]:
    return _read_jsonl(design_record_path(repo_path))


def write_design_record(
    run_dir: Path, repo_path: Optional[Path] = None
) -> Optional[dict]:
    """Create/update the durable design-run JSONL record for `run_dir`."""
    repo_root = resolve_repo_root(repo_path) if repo_path else resolve_repo_root()
    record = build_design_record(run_dir, repo_root)
    if record is None:
        return None

    path = design_record_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [
        existing
        for existing in _read_jsonl(path)
        if existing.get("run_id") != record["run_id"]
    ]
    records.append(record)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records),
        encoding="utf-8",
    )
    tmp.replace(path)
    return record


def render_records(records: list[dict], *, limit: Optional[int] = None) -> str:
    rows = records[-limit:] if limit else records
    lines = ["# design run records", ""]
    if not rows:
        lines.append("(records 없음)")
        return "\n".join(lines)
    lines.append("| run_id | started_at | verdict | steps | duration_s | findings | cycles |")
    lines.append("|---|---|---:|---:|---:|---|---|")
    for rec in rows:
        findings = rec.get("finding_classes") or {}
        finding_cell = ", ".join(f"{k}:{v}" for k, v in sorted(findings.items())) or "-"
        cycles = rec.get("revalidation_cycles") or {}
        cycle_cell = ", ".join(f"{k}:{v}" for k, v in sorted(cycles.items())) or "-"
        lines.append(
            f"| {rec.get('run_id', '')} | {rec.get('started_at', '')} | "
            f"{rec.get('final_verdict', '') or '-'} | {rec.get('step_count', 0)} | "
            f"{rec.get('duration_s', 0)} | {finding_cell} | {cycle_cell} |"
        )
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="design run durable record 조회")
    parser.add_argument("--repo", default=".", help="활성 프로젝트 root (기본 cwd)")
    parser.add_argument("--json", action="store_true", help="JSON array 출력")
    parser.add_argument("--limit", type=int, default=None, help="최근 N개만 출력")
    args = parser.parse_args(argv)

    repo = resolve_repo_root(Path(args.repo))
    records = load_records(repo)
    if args.limit:
        records = records[-args.limit :]
    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
    else:
        print(render_records(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

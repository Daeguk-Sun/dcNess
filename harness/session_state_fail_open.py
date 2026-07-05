"""Hook fail-open diagnostics for :mod:`harness.session_state`."""
from __future__ import annotations

import importlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

FAIL_OPEN_EVENTS_NAME = "fail-open-events.jsonl"
FAIL_OPEN_RECENT_HOURS = 24
FAIL_OPEN_RECENT_LIMIT = 5
_FAIL_OPEN_DETAIL_MAX = 500
_resolve_project_root = importlib.import_module("harness.session_state_activation")._resolve_project_root

def fail_open_events_path(
    cwd: Optional[Path] = None,
    *,
    base_dir: Optional[Path] = None,
) -> Path:
    """현재 프로젝트의 hook fail-open 진단 JSONL 경로."""
    if base_dir is not None:
        return Path(base_dir) / FAIL_OPEN_EVENTS_NAME
    return _resolve_project_root(cwd) / ".claude" / "harness-state" / FAIL_OPEN_EVENTS_NAME


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_fail_open_ts(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def record_fail_open_event(
    *,
    hook: str,
    category: str,
    detail: str = "",
    severity: str = "WARN",
    cwd: Optional[Path] = None,
    base_dir: Optional[Path] = None,
) -> None:
    """enforcement-relevant hook fail-open 을 JSONL 로 기록한다.

    기록 실패는 hook 본동작을 막지 않는다. inactive-project no-op 같은 benign skip 은
    호출자가 이 함수를 부르지 않는 방식으로 조용히 유지한다.
    """
    try:
        hook_s = str(hook or "unknown")[:80]
        category_s = str(category or "unknown")[:120]
        detail_s = str(detail or "").replace("\n", " ")[:_FAIL_OPEN_DETAIL_MAX]
        severity_s = str(severity or "WARN").upper()[:20]
        event: Dict[str, Any] = {
            "ts": _utc_now_iso(),
            "hook": hook_s,
            "category": category_s,
            "severity": severity_s,
            "detail": detail_s,
        }
        if base_dir is None:
            try:
                event["project_root"] = str(_resolve_project_root(cwd).resolve())
            except (OSError, ValueError):
                pass
        target = fail_open_events_path(cwd, base_dir=base_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
    except Exception:  # noqa: BLE001 # nosec B110
        pass


def read_fail_open_events(
    cwd: Optional[Path] = None,
    *,
    base_dir: Optional[Path] = None,
    since_hours: Optional[int] = None,
    limit: Optional[int] = None,
) -> list[Dict[str, Any]]:
    """hook fail-open JSONL 을 읽는다. malformed row 는 진단 자체를 깨지 않게 skip."""
    target = fail_open_events_path(cwd, base_dir=base_dir)
    try:
        if not target.exists():
            return []
    except OSError:
        return []

    cutoff = None
    if since_hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)

    events: list[Dict[str, Any]] = []
    try:
        with open(target, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                if cutoff is not None:
                    parsed = _parse_fail_open_ts(row.get("ts"))
                    if parsed is None or parsed < cutoff:
                        continue
                events.append(row)
    except OSError:
        return []

    if limit == 0:
        return []
    if limit is not None and limit > 0:
        return events[-limit:]
    return events


def collect_fail_open_summary(
    cwd: Optional[Path] = None,
    *,
    base_dir: Optional[Path] = None,
    since_hours: int = FAIL_OPEN_RECENT_HOURS,
    recent_limit: int = FAIL_OPEN_RECENT_LIMIT,
) -> Dict[str, Any]:
    """status 진단용 최근 fail-open count/reason category 요약."""
    events = read_fail_open_events(cwd, base_dir=base_dir, since_hours=since_hours)
    by_category: Dict[str, int] = {}
    by_hook: Dict[str, int] = {}
    for event in events:
        category = str(event.get("category") or "unknown")
        hook = str(event.get("hook") or "unknown")
        by_category[category] = by_category.get(category, 0) + 1
        by_hook[hook] = by_hook.get(hook, 0) + 1
    return {
        "total": len(events),
        "since_hours": since_hours,
        "by_category": by_category,
        "by_hook": by_hook,
        "recent": list(reversed(events[-recent_limit:])) if recent_limit > 0 else [],
    }


def _format_fail_open_summary(summary: Dict[str, Any]) -> str:
    total = int(summary.get("total") or 0)
    since_hours = int(summary.get("since_hours") or FAIL_OPEN_RECENT_HOURS)
    if total <= 0:
        return f"최근 {since_hours}h 0건"
    by_category = summary.get("by_category") if isinstance(summary, dict) else {}
    if not isinstance(by_category, dict):
        by_category = {}
    category_text = ", ".join(
        f"{k}={v}" for k, v in sorted(by_category.items(), key=lambda item: str(item[0]))
    )
    recent = summary.get("recent") if isinstance(summary, dict) else []
    latest_text = ""
    if isinstance(recent, list) and recent:
        latest = recent[0]
        if isinstance(latest, dict):
            hook = latest.get("hook") or "unknown"
            category = latest.get("category") or "unknown"
            detail = latest.get("detail") or ""
            latest_text = f"; latest: {hook}/{category}"
            if detail:
                latest_text += f" — {detail}"
    return f"최근 {since_hours}h {total}건 — {category_text}{latest_text}"


def format_fail_open_warning(summary: Dict[str, Any]) -> str:
    """최근 hook fail-open 을 run 종료/review 표면에 노출하는 공통 문구."""
    total = int(summary.get("total") or 0) if isinstance(summary, dict) else 0
    if total <= 0:
        return ""
    return "\n".join(
        [
            "## ⚠️ hook fail-open warning",
            "",
            f"- {_format_fail_open_summary(summary)}",
            "- enforcement hook 이 정책 판단을 완료하지 못해 allow 한 이벤트입니다.",
            "- 반복되면 `dcness-helper status` 의 `hook fail-open 진단`과 hook stderr 로그를 확인하세요.",
        ]
    )

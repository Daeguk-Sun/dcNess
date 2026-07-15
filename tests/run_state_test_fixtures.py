"""Test-only builders for current run-state fixtures.

The production compatibility writers were intentionally removed. These adapters keep
the broad regression matrix while routing behavior through the canonical transition;
they are installed only for the lifetime of a test module.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from harness import ledger, session_state as state


_SESSION_NAMES = (
    "start_run",
    "update_current_step",
    "complete_run",
    "cleanup_stale_runs",
    "mark_run_blocked",
    "update_live",
    "_read_steps_jsonl",
    "set_pending_agent",
    "clear_pending_agent",
    "clear_current_step",
)
_LEDGER_NAMES = ("append_event", "append_step_completed", "_append_event_raw")


def start_run(
    sid: str,
    rid: str,
    entry_point: str,
    *,
    base_dir: Optional[Path] = None,
    **fields: Any,
) -> None:
    state.transition(
        sid,
        "run_started",
        run_id=rid,
        base_dir=base_dir,
        entry_point=entry_point,
        **fields,
    )


def update_current_step(
    sid: str,
    rid: str,
    agent: str,
    mode: Optional[str],
    *,
    base_dir: Optional[Path] = None,
) -> None:
    state.transition(
        sid,
        "step_started",
        run_id=rid,
        base_dir=base_dir,
        agent=agent,
        mode=mode,
    )


def complete_run(
    sid: str, rid: str, *, base_dir: Optional[Path] = None
) -> None:
    state.transition(sid, "run_completed", run_id=rid, base_dir=base_dir)


def cleanup_stale_runs(
    sid: str, *, base_dir: Optional[Path] = None, ttl_sec: int = state.DEFAULT_RUN_TTL_SEC
) -> int:
    return int(
        state.transition(
            sid, "stale_runs_cleaned", base_dir=base_dir, ttl_sec=ttl_sec
        )
    )


def mark_run_blocked(
    sid: str,
    rid: str,
    *,
    category: str,
    base_dir: Optional[Path] = None,
    **fields: Any,
) -> dict[str, Any]:
    return state.transition(
        sid,
        "run_blocked",
        run_id=rid,
        base_dir=base_dir,
        category=category,
        **fields,
    )


def update_live(
    sid: str, *, base_dir: Optional[Path] = None, **fields: Any
) -> None:
    """Write a current-format fixture without reintroducing a product writer."""
    with state._session_lock(sid, base_dir=base_dir):
        live = state.read_live(sid, base_dir=base_dir) or state._empty_live(sid)
        for key, value in fields.items():
            if value is None:
                live.pop(key, None)
            else:
                live[key] = value
        state._write_live(sid, live, base_dir=base_dir)


def append_event(
    sid: str,
    rid: str,
    event: str,
    *,
    base_dir: Optional[Path] = None,
    **fields: Any,
) -> dict[str, Any]:
    if event == "step_completed":
        raise ValueError("step_completed requires a receipt")
    return state._append_ledger_record(
        sid, rid, event, base_dir=base_dir, **fields
    )


def append_step_completed(
    sid: str,
    rid: str,
    agent: str,
    mode: Optional[str],
    enum: str,
    prose: str,
    prose_path: Any,
    *,
    base_dir: Optional[Path] = None,
    provider: Optional[str] = None,
) -> dict[str, Any]:
    return state.transition(
        sid,
        "step_completed",
        run_id=rid,
        base_dir=base_dir,
        agent=agent,
        mode=mode,
        enum=enum,
        prose=prose,
        prose_path=prose_path,
        provider=provider,
    )


def read_steps_jsonl(
    sid: str, rid: str, *, base_dir: Optional[Path] = None
) -> list[dict[str, Any]]:
    """Legacy fixture spelling for the current ledger reader."""
    return ledger.read_step_completed(sid, rid, base_dir=base_dir)


def set_pending_agent(
    sid: str,
    rid: str,
    *,
    tool_use_id: str,
    sub_type: str,
    mode: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> None:
    state.transition(
        sid,
        "pending_agent_set",
        run_id=rid,
        base_dir=base_dir,
        tool_use_id=tool_use_id,
        sub_type=sub_type,
        mode=mode,
    )


def clear_pending_agent(
    sid: str,
    rid: str,
    *,
    tool_use_id: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    result = state.transition(
        sid,
        "pending_agent_cleared",
        run_id=rid,
        base_dir=base_dir,
        tool_use_id=tool_use_id,
    )
    return result if isinstance(result, dict) else None


def clear_current_step(
    sid: str,
    rid: str,
    *,
    agent: Optional[str] = None,
    mode: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> None:
    """Construct the pre-existing no-current-step fixture state."""
    live = state.read_live(sid, base_dir=base_dir)
    active = dict(live.get("active_runs") or {})
    slot = dict(active[rid])
    current = slot.get("current_step")
    if isinstance(current, dict) and (
        (agent is None or current.get("agent") == agent)
        and (mode is None or current.get("mode") == mode)
    ):
        slot["current_step"] = None
        active[rid] = slot
        update_live(sid, base_dir=base_dir, active_runs=active)


def append_event_raw(
    sid: str,
    rid: str,
    event: str,
    *,
    base_dir: Optional[Path] = None,
    **fields: Any,
) -> dict[str, Any]:
    """Build a raw current-schema ledger fixture through the sole owner."""
    return state._append_ledger_record(
        sid, rid, event, base_dir=base_dir, **fields
    )


def install() -> None:
    values = {
        "start_run": start_run,
        "update_current_step": update_current_step,
        "complete_run": complete_run,
        "cleanup_stale_runs": cleanup_stale_runs,
        "mark_run_blocked": mark_run_blocked,
        "update_live": update_live,
        "_read_steps_jsonl": read_steps_jsonl,
        "set_pending_agent": set_pending_agent,
        "clear_pending_agent": clear_pending_agent,
        "clear_current_step": clear_current_step,
    }
    for name, value in values.items():
        setattr(state, name, value)
    ledger.append_event = append_event  # type: ignore[attr-defined]
    ledger.append_step_completed = append_step_completed  # type: ignore[attr-defined]
    ledger._append_event_raw = append_event_raw  # type: ignore[attr-defined]


def uninstall() -> None:
    for name in _SESSION_NAMES:
        if hasattr(state, name):
            delattr(state, name)
    for name in _LEDGER_NAMES:
        if hasattr(ledger, name):
            delattr(ledger, name)

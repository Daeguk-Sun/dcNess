"""CLI handlers for peer parallelism — wave board + merge lock (#636 / #641).

Split out of ``session_state_cli`` to keep the CLI dispatcher cohesive. The
public CLI surface is unchanged: ``session_state_cli`` re-exposes these names so
``python3 -m harness.session_state <wave-*|merge-lock|normalize-scope>`` keeps
working.
"""
from __future__ import annotations

import json
import os
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any


def _parent_state_module():
    module = sys.modules.get("harness.session_state")
    if module is not None and hasattr(module, "read_live"):
        return module
    main = sys.modules.get("__main__")
    if main is not None and hasattr(main, "read_live"):
        return main
    import harness.session_state as module

    return module


_state = _parent_state_module()
_default_base = _state._default_base
auto_detect_run_id = _state.auto_detect_run_id
auto_detect_session_id = _state.auto_detect_session_id


def _cli_wave_plan(args: Any) -> int:
    """impl task 들의 opt-in 병렬 wave 계획 계산 → JSON stdout (#636).

    `/impl-loop` chain dry preview 가 호출해 병렬 wave 후보를 표에 echo 한다.
    정책 SSOT = docs/plugin/parallel-policy.md (독립 interactive peer sessions).
    내부 helper (run-dir / run-status 류) — 새 공개 진입점 아님.
    """
    import json as _json

    from harness import parallel_wave

    high_risk = parallel_wave._split_csv(getattr(args, "high_risk", ""))
    plan = parallel_wave.wave_plan_from_paths(
        args.paths, args.max_parallel, high_risk
    )
    payload = plan.to_dict()
    payload["execution_model"] = "independent_interactive_sessions"
    payload["worker_command"] = "/impl-loop <canonical-impl-path>"
    payload["merge_model"] = "per-session PR finalize guarded by merge-lock"
    payload["registered_count"] = 0
    if getattr(args, "register", False):
        board = _current_wave_board()
        paths = [
            task.path
            for step in plan.parallel_steps
            for task in step.tasks
        ]
        records = board.register(paths, plan_id=getattr(args, "plan_id", None))
        payload["registered_count"] = len(records)
        payload["registered"] = [
            {
                "key": r["key"],
                "canonical_impl_path": r["canonical_impl_path"],
                "impl_name": r["impl_name"],
            }
            for r in records
        ]
    print(_json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cli_normalize_scope(args: Any) -> int:
    """Mechanically normalize impl `### 수정 허용` bullets (#833)."""
    from harness import parallel_wave

    payload = parallel_wave.normalize_scope_paths(args.paths)
    _json_stdout(payload)
    return 0


def _repo_root_from_state_root() -> Path:
    state_root = _default_base().resolve()
    # state_root = <repo>/.claude/harness-state
    try:
        return state_root.parent.parent.resolve()
    except IndexError:
        return Path.cwd().resolve()


def _current_wave_board() -> Any:
    from harness.wave_board import WaveBoard

    state_root = _default_base().resolve()
    return WaveBoard(_repo_root_from_state_root(), state_root=state_root)


def _current_merge_lock() -> Any:
    from harness.merge_lock import MergeLock

    state_root = _default_base().resolve()
    return MergeLock(_repo_root_from_state_root(), state_root=state_root)


def _current_branch_fallback() -> str:
    try:
        result = subprocess.run(  # nosec B603, B607
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(Path.cwd()),
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return "unknown"


def _merge_order_base_ref(repo_root: Path) -> str:
    try:
        result = subprocess.run(  # nosec B603, B607
            ["git", "rev-parse", "--verify", "--quiet", "origin/main"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "main"
    return "origin/main" if result.returncode == 0 else "main"


def _json_stdout(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _cli_wave_claim(args: Any) -> int:
    from harness.wave_board import ClaimConflict

    board = _current_wave_board()
    session_id = args.session_id or auto_detect_session_id() or "unknown-session"
    run_id = args.run_id or auto_detect_run_id() or "unknown-run"
    worktree = args.worktree or str(Path.cwd().resolve())
    branch = args.branch or _current_branch_fallback()
    try:
        result = board.claim_if_registered(
            args.impl_path,
            session_id=session_id,
            run_id=run_id,
            worktree=worktree,
            branch=branch,
            stale_after_seconds=args.stale_after,
        )
    except ClaimConflict as exc:
        _json_stdout(
            {
                "ok": False,
                "error": str(exc),
                "stale": exc.stale,
                "record": exc.record,
            }
        )
        return 1
    payload = {
        "ok": True,
        "mode": result.mode,
        "claimed": result.claimed,
        "key": result.key,
        "canonical_impl_path": result.canonical_impl_path,
        "record": result.record,
    }
    _json_stdout(payload)
    return 0


def _cli_wave_heartbeat(args: Any) -> int:
    session_id = args.session_id or auto_detect_session_id() or "unknown-session"
    run_id = args.run_id or auto_detect_run_id() or "unknown-run"
    try:
        record = _current_wave_board().heartbeat(
            args.key_or_path,
            session_id=session_id,
            run_id=run_id,
        )
    except Exception as exc:
        print(f"[wave-heartbeat] {exc}", file=sys.stderr)
        return 1
    _json_stdout({"ok": True, "record": record})
    return 0


def _cli_wave_release(args: Any) -> int:
    board = _current_wave_board()
    try:
        if args.state == "completed":
            record = board.complete(args.key_or_path, pr_number=args.pr, url=args.url)
        else:
            record = board.release(args.key_or_path, state=args.state, reason=args.reason or "")
    except Exception as exc:
        print(f"[wave-release] {exc}", file=sys.stderr)
        return 1
    _json_stdout({"ok": True, "record": record})
    return 0


def _cli_wave_reclaim(args: Any) -> int:
    try:
        record = _current_wave_board().reclaim(args.key_or_path, reason=args.reason)
    except Exception as exc:
        print(f"[wave-reclaim] {exc}", file=sys.stderr)
        return 1
    _json_stdout({"ok": True, "record": record})
    return 0


def _cli_wave_status(args: Any) -> int:
    board = _current_wave_board()
    if getattr(args, "json", False):
        _json_stdout({"records": board.status_records()})
    else:
        print(board.status_text())
    return 0


def _cli_merge_lock(args: Any) -> int:
    from harness.merge_lock import (
        LockBusy,
        MergeOrderBlocked,
        acquire_peer_merge_guard,
        external_git_completed,
    )

    board = _current_wave_board()
    lock = _current_merge_lock()
    repo_root = _repo_root_from_state_root()
    base_ref = _merge_order_base_ref(repo_root)
    action = args.merge_lock_cmd
    if action == "acquire":
        branch = args.branch or _current_branch_fallback()
        owner = (
            args.owner
            or f"{auto_detect_session_id() or 'unknown-session'}:"
            f"{auto_detect_run_id() or 'unknown-run'}:{os.getpid()}"
        )
        try:
            guard = acquire_peer_merge_guard(
                board,
                lock,
                branch=branch,
                pr_number=args.pr,
                owner=owner,
                external_completed=lambda p: external_git_completed(
                    repo_root,
                    p,
                    base_ref=base_ref,
                ),
            )
        except MergeOrderBlocked as exc:
            _json_stdout(
                {
                    "ok": False,
                    "error": str(exc),
                    "blocked_prior_paths": list(exc.result.evidence),
                }
            )
            return 1
        except LockBusy as exc:
            _json_stdout({"ok": False, "error": str(exc)})
            return 1
        _json_stdout(
            {
                "ok": True,
                "mode": guard.mode,
                "token": guard.token,
                "claim_key": guard.claim_key,
                "impl_path": guard.impl_path,
                "order_reason": guard.order.reason,
            }
        )
        return 0
    if action == "release":
        try:
            claim_record = None
            if getattr(args, "claim_key", None):
                claim_record = board.release(
                    args.claim_key,
                    state=args.state,
                    reason=args.reason or "",
                )
            record = lock.release(args.token, state=args.state, reason=args.reason or "")
        except Exception as exc:
            print(f"[merge-lock] {exc}", file=sys.stderr)
            return 1
        payload: dict[str, Any] = {"ok": True, "record": record}
        if claim_record is not None:
            payload["claim"] = claim_record
        _json_stdout(payload)
        return 0
    if action == "complete":
        try:
            claim = board.complete(args.claim_key, pr_number=args.pr, url=args.url)
            lock_record = lock.release(args.token, state="completed")
        except Exception as exc:
            print(f"[merge-lock] {exc}", file=sys.stderr)
            return 1
        _json_stdout({"ok": True, "claim": claim, "lock": lock_record})
        return 0
    if action == "break":
        owner = args.owner or f"operator:{os.getpid()}"
        try:
            record = lock.break_stale(
                owner=owner,
                stale_after_seconds=args.stale_after,
                reason=args.reason or "",
            )
        except LockBusy as exc:
            _json_stdout({"ok": False, "error": str(exc)})
            return 1
        except Exception as exc:
            print(f"[merge-lock] {exc}", file=sys.stderr)
            return 1
        _json_stdout({"ok": True, "record": record})
        return 0
    print(f"[merge-lock] unknown action: {action}", file=sys.stderr)
    return 1

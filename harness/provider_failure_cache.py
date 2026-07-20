"""Chain-scoped capability failure memoization for implementation providers.

The story-runner state supplies the chain identity. Cache entries live in a
sidecar file next to that state so single ``/impl`` calls and unrelated
projects/worktrees never share provider health. Only deterministic capability
failures are recordable; transient execution failures remain retryable.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sys
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence


CACHEABLE_CATEGORIES = frozenset(
    {"cli_missing", "auth_unavailable", "config_unavailable"}
)
NON_CACHEABLE_CATEGORIES = frozenset(
    {
        "timeout",
        "idle_timeout",
        "empty_output",
        "interrupt",
        "network_transient",
        "provider_error",
    }
)
FAILURE_CATEGORIES = CACHEABLE_CATEGORIES | NON_CACHEABLE_CATEGORIES
_CHAIN_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


@dataclass(frozen=True)
class CacheScope:
    state_path: Path
    cache_path: Path
    chain_id: str
    project_root: Path
    active: bool

    @property
    def label(self) -> str:
        return f"chain:{self.chain_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _scope(state_path: Path, project_root: Path) -> CacheScope | None:
    resolved_state = Path(state_path).resolve()
    resolved_project = Path(project_root).resolve()
    if not resolved_state.is_file():
        return None
    state = _read_json(resolved_state)
    if state.get("schema_version") != 2 or state.get("kind") != "dcness-story-run":
        return None
    state_project_raw = state.get("project_root")
    if not isinstance(state_project_raw, str) or not state_project_raw:
        return None
    state_project = Path(state_project_raw).resolve()
    if state_project != resolved_project:
        raise ValueError(
            "provider cache project_root mismatch: "
            f"state={state_project} requested={resolved_project}"
        )
    chain_id = state.get("chain_id")
    if not isinstance(chain_id, str) or not _CHAIN_ID.fullmatch(chain_id):
        return None
    tasks = state.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return None
    active = any(
        isinstance(task, dict) and task.get("status") != "completed"
        for task in tasks
    )
    cache_path = (
        resolved_state.parent / "provider-failure-cache" / f"{chain_id}.json"
    )
    return CacheScope(
        state_path=resolved_state,
        cache_path=cache_path,
        chain_id=chain_id,
        project_root=resolved_project,
        active=active,
    )


def cache_path_for_state(state_path: Path, project_root: Path) -> Path | None:
    scope = _scope(state_path, project_root)
    return scope.cache_path if scope else None


@contextmanager
def _cache_lock(cache_path: Path, *, exclusive: bool) -> Iterator[None]:
    lock_path = cache_path.with_suffix(f"{cache_path.suffix}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def classify_failure(
    *,
    provider: str,
    exit_code: int,
    raw_log: Path,
    cause: str = "",
) -> str:
    """Map a worker failure to a stable internal category conservatively."""
    if cause in FAILURE_CATEGORIES:
        return cause
    if exit_code == 124:
        return "timeout"
    if exit_code in {130, 143, 241, 254}:
        return "interrupt"
    try:
        text = Path(raw_log).read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        text = ""

    auth_patterns = (
        "authentication required",
        "not logged in",
        "unauthorized",
        "invalid api key",
        "api key is missing",
        "api key not set",
    )
    if any(pattern in text for pattern in auth_patterns):
        return "auth_unavailable"

    config_patterns = (
        "failed to load configuration",
        "invalid configuration",
        "malformed config",
        "failed to parse config",
        "configuration parse error",
    )
    if any(pattern in text for pattern in config_patterns):
        return "config_unavailable"

    network_patterns = (
        "connection reset",
        "connection refused",
        "temporary failure in name resolution",
        "service unavailable",
        "network is unreachable",
        "rate limit",
    )
    if any(pattern in text for pattern in network_patterns):
        return "network_transient"
    return "provider_error"


def emit_failure(
    output: Path,
    *,
    provider: str,
    category: str,
    raw_log: Path,
) -> dict[str, Any]:
    if category not in FAILURE_CATEGORIES:
        raise ValueError(f"unsupported provider failure category: {category}")
    payload = {
        "schema_version": 1,
        "kind": "dcness-provider-failure",
        "provider": provider,
        "category": category,
        "cacheable": category in CACHEABLE_CATEGORIES,
        "raw_log": str(Path(raw_log).resolve()),
        "recorded_at": _now_iso(),
    }
    _atomic_write_json(Path(output), payload)
    return payload


def _load_failure(path: Path, expected_provider: str) -> dict[str, Any]:
    failure = _read_json(Path(path))
    if (
        failure.get("schema_version") != 1
        or failure.get("kind") != "dcness-provider-failure"
    ):
        raise ValueError(f"invalid provider failure contract: {path}")
    if failure.get("provider") != expected_provider:
        raise ValueError(
            "provider failure identity mismatch: "
            f"expected={expected_provider} actual={failure.get('provider')}"
        )
    category = failure.get("category")
    if category not in FAILURE_CATEGORIES:
        raise ValueError(f"invalid provider failure category: {category}")
    expected_cacheable = category in CACHEABLE_CATEGORIES
    if failure.get("cacheable") is not expected_cacheable:
        raise ValueError("provider failure cacheable flag does not match category")
    return failure


def _empty_cache(scope: CacheScope) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "dcness-provider-failure-cache",
        "chain_id": scope.chain_id,
        "project_root": str(scope.project_root),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "entries": {},
    }


def _load_cache(scope: CacheScope) -> dict[str, Any] | None:
    if not scope.cache_path.is_file():
        return None
    try:
        payload = _read_json(scope.cache_path)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if (
        payload.get("schema_version") != 1
        or payload.get("kind") != "dcness-provider-failure-cache"
        or payload.get("chain_id") != scope.chain_id
        or payload.get("project_root") != str(scope.project_root)
        or not isinstance(payload.get("entries"), dict)
    ):
        return None
    return payload


def check_cached_failure(
    state_path: Path,
    project_root: Path,
    provider: str,
) -> dict[str, Any] | None:
    scope = _scope(state_path, project_root)
    if scope is None or not scope.active:
        return None
    with _cache_lock(scope.cache_path, exclusive=False):
        payload = _load_cache(scope)
        if payload is None:
            return None
        entry = payload["entries"].get(provider)
        return dict(entry) if isinstance(entry, dict) else None


def record_failure(
    state_path: Path,
    project_root: Path,
    failure_file: Path,
    *,
    expected_provider: str,
) -> dict[str, Any] | None:
    failure = _load_failure(failure_file, expected_provider)
    if not failure["cacheable"]:
        return None
    scope = _scope(state_path, project_root)
    if scope is None or not scope.active:
        return None
    with _cache_lock(scope.cache_path, exclusive=True):
        payload = _load_cache(scope) or _empty_cache(scope)
        entries = payload["entries"]
        existing = entries.get(expected_provider)
        if isinstance(existing, dict):
            return dict(existing)
        entry = {
            "provider": expected_provider,
            "category": failure["category"],
            "first_failed_at": failure["recorded_at"],
            "raw_log": failure["raw_log"],
            "scope": scope.label,
        }
        entries[expected_provider] = entry
        payload["updated_at"] = _now_iso()
        _atomic_write_json(scope.cache_path, payload)
        return dict(entry)


def clear_cached_failure(
    state_path: Path,
    project_root: Path,
    provider: str,
) -> bool:
    scope = _scope(state_path, project_root)
    if scope is None:
        return False
    with _cache_lock(scope.cache_path, exclusive=True):
        payload = _load_cache(scope)
        if payload is None or provider not in payload["entries"]:
            return False
        del payload["entries"][provider]
        if payload["entries"]:
            payload["updated_at"] = _now_iso()
            _atomic_write_json(scope.cache_path, payload)
        else:
            scope.cache_path.unlink(missing_ok=True)
        return True


def invalidate_state_cache(state_path: Path, state: dict[str, Any]) -> bool:
    chain_id = state.get("chain_id")
    if not isinstance(chain_id, str) or not _CHAIN_ID.fullmatch(chain_id):
        return False
    cache_path = Path(state_path).resolve().parent / "provider-failure-cache" / f"{chain_id}.json"
    with _cache_lock(cache_path, exclusive=True):
        existed = cache_path.exists()
        cache_path.unlink(missing_ok=True)
        return existed


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    emit = sub.add_parser("emit")
    emit.add_argument("--output", required=True)
    emit.add_argument("--provider", required=True)
    emit.add_argument("--category", default="")
    emit.add_argument("--exit-code", type=int, default=1)
    emit.add_argument("--raw-log", required=True)
    emit.add_argument("--cause", default="")

    for name in ("check", "clear"):
        command = sub.add_parser(name)
        command.add_argument("--state", required=True)
        command.add_argument("--project-root", required=True)
        command.add_argument("--provider", required=True)

    record = sub.add_parser("record")
    record.add_argument("--state", required=True)
    record.add_argument("--project-root", required=True)
    record.add_argument("--provider", required=True)
    record.add_argument("--failure-file", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        if args.cmd == "emit":
            category = args.category or classify_failure(
                provider=args.provider,
                exit_code=args.exit_code,
                raw_log=Path(args.raw_log),
                cause=args.cause,
            )
            _print_json(
                emit_failure(
                    Path(args.output),
                    provider=args.provider,
                    category=category,
                    raw_log=Path(args.raw_log),
                )
            )
            return 0
        if args.cmd == "check":
            entry = check_cached_failure(
                Path(args.state), Path(args.project_root), args.provider
            )
            if entry is None:
                return 3
            _print_json(entry)
            return 0
        if args.cmd == "record":
            entry = record_failure(
                Path(args.state),
                Path(args.project_root),
                Path(args.failure_file),
                expected_provider=args.provider,
            )
            if entry is None:
                return 3
            _print_json(entry)
            return 0
        if args.cmd == "clear":
            clear_cached_failure(
                Path(args.state), Path(args.project_root), args.provider
            )
            return 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[provider-failure-cache] {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

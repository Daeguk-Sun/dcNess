"""wave_board — peer /impl-loop task claim board (#641).

The claim unit is the canonical impl file path.  A coordinator registers
parallel candidates first; a later `/impl-loop <impl-path>` invocation only
enters peer flow when that path is registered.  Unregistered single invocations
fall back to the existing serial flow.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

__all__ = [
    "DEFAULT_STALE_AFTER_SECONDS",
    "ClaimConflict",
    "ClaimResult",
    "WaveBoard",
]

DEFAULT_STALE_AFTER_SECONDS = 2 * 60 * 60
_JSON_MODE = 0o600


class ClaimConflict(RuntimeError):
    """Raised when a registered impl path cannot be claimed."""

    def __init__(self, message: str, *, stale: bool = False, record: Optional[dict] = None):
        super().__init__(message)
        self.stale = stale
        self.record = record or {}


@dataclass(frozen=True)
class ClaimResult:
    """Result of `claim_if_registered`."""

    mode: str  # "serial" | "peer"
    claimed: bool
    key: str
    canonical_impl_path: str
    record: dict[str, Any]


def _now_iso(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    os.chmod(path, _JSON_MODE)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _direct_create_json(path: Path, payload: dict[str, Any]) -> None:
    """Create JSON with O_EXCL on the target path itself."""

    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _JSON_MODE)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


class WaveBoard:
    """File-backed task claim board for independent peer sessions."""

    def __init__(self, repo_root: str | Path, *, state_root: str | Path | None = None):
        self.repo_root = Path(repo_root).resolve()
        self.state_root = (
            Path(state_root).resolve()
            if state_root is not None
            else self.repo_root / ".claude" / "harness-state"
        )
        self.root = self.state_root / "wave-board"
        self.registrations_dir = self.root / "registrations"
        self.claims_dir = self.root / "claims"
        self.archive_dir = self.root / "archive"

    def canonical_path(self, path: str | Path) -> str:
        p = Path(path)
        if not p.is_absolute():
            p = self.repo_root / p
        return str(p.resolve(strict=False))

    def key_for_path(self, path: str | Path) -> str:
        canonical = self.canonical_path(path)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]

    def _registration_path(self, key: str) -> Path:
        return self.registrations_dir / f"{key}.json"

    def _claim_path(self, key: str) -> Path:
        return self.claims_dir / f"{key}.json"

    def _key_from_key_or_path(self, key_or_path: str | Path) -> str:
        value = str(key_or_path)
        if len(value) == 24 and all(c in "0123456789abcdef" for c in value):
            return value
        return self.key_for_path(value)

    def register(
        self,
        paths: Iterable[str | Path],
        *,
        plan_id: str | None = None,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for raw in paths:
            canonical = self.canonical_path(raw)
            key = self.key_for_path(canonical)
            record = {
                "key": key,
                "canonical_impl_path": canonical,
                "impl_name": Path(canonical).name,
                "impl_slug": Path(canonical).stem,
                "plan_id": plan_id,
                "state": "registered",
                "registered_at": _now_iso(now),
            }
            _atomic_write_json(self._registration_path(key), record)
            records.append(record)
        return records

    def is_registered(self, path: str | Path) -> bool:
        return self._registration_path(self.key_for_path(path)).exists()

    def claim_if_registered(
        self,
        path: str | Path,
        *,
        session_id: str,
        run_id: str,
        worktree: str,
        branch: str,
        now: datetime | None = None,
        stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
    ) -> ClaimResult:
        canonical = self.canonical_path(path)
        key = self.key_for_path(canonical)
        if not self._registration_path(key).exists():
            return ClaimResult("serial", False, key, canonical, {})

        claim_path = self._claim_path(key)
        record = {
            "key": key,
            "canonical_impl_path": canonical,
            "impl_name": Path(canonical).name,
            "impl_slug": Path(canonical).stem,
            "session_id": session_id,
            "run_id": run_id,
            "worktree": worktree,
            "branch": branch,
            "state": "claimed",
            "claimed_at": _now_iso(now),
            "heartbeat_at": _now_iso(now),
            "heartbeat_pid": os.getpid(),
        }
        try:
            _direct_create_json(claim_path, record)
        except FileExistsError:
            existing = _read_json(claim_path)
            state = existing.get("state")
            if state == "completed":
                raise ClaimConflict(
                    f"{Path(canonical).name} already completed",
                    stale=False,
                    record=existing,
                )
            if state == "failed":
                raise ClaimConflict(
                    f"{Path(canonical).name} failed claim requires explicit reclaim",
                    stale=False,
                    record=existing,
                )
            stale = self._is_stale(existing, now=now, stale_after_seconds=stale_after_seconds)
            suffix = "stale claim requires explicit reclaim" if stale else "already claimed"
            raise ClaimConflict(
                f"{Path(canonical).name} {suffix}",
                stale=stale,
                record=existing,
            )
        return ClaimResult("peer", True, key, canonical, record)

    def _is_stale(
        self,
        record: dict[str, Any],
        *,
        now: datetime | None = None,
        stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
    ) -> bool:
        heartbeat = _parse_iso(str(record.get("heartbeat_at", "")))
        if heartbeat is None:
            return False
        now_dt = now or datetime.now(timezone.utc)
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc)
        return (now_dt.astimezone(timezone.utc) - heartbeat).total_seconds() > stale_after_seconds

    def get_record(self, key_or_path: str | Path) -> dict[str, Any]:
        key = self._key_from_key_or_path(key_or_path)
        return _read_json(self._claim_path(key))

    def heartbeat(
        self,
        key_or_path: str | Path,
        *,
        session_id: str,
        run_id: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        key = self._key_from_key_or_path(key_or_path)
        record = self.get_record(key)
        if record.get("session_id") != session_id or record.get("run_id") != run_id:
            raise ClaimConflict("heartbeat identity mismatch", record=record)
        record["heartbeat_at"] = _now_iso(now)
        record["heartbeat_pid"] = os.getpid()
        _atomic_write_json(self._claim_path(key), record)
        return record

    def complete(
        self,
        key_or_path: str | Path,
        *,
        pr_number: int | None = None,
        url: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        key = self._key_from_key_or_path(key_or_path)
        record = self.get_record(key)
        record["state"] = "completed"
        record["completed_at"] = _now_iso(now)
        if pr_number is not None:
            record["pr_number"] = pr_number
        if url:
            record["url"] = url
        _atomic_write_json(self._claim_path(key), record)
        return record

    def release(
        self,
        key_or_path: str | Path,
        *,
        state: str = "released",
        reason: str = "",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        key = self._key_from_key_or_path(key_or_path)
        record = self.get_record(key)
        if record.get("state") == "completed":
            return record
        record["state"] = state
        record["released_at"] = _now_iso(now)
        if reason:
            record["reason"] = reason
        if state == "released":
            self._archive_record(key, record)
            self._claim_path(key).unlink()
            return record
        _atomic_write_json(self._claim_path(key), record)
        return record

    def reclaim(
        self,
        key_or_path: str | Path,
        *,
        reason: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        key = self._key_from_key_or_path(key_or_path)
        claim_path = self._claim_path(key)
        record = _read_json(claim_path)
        if record.get("state") == "completed":
            raise ClaimConflict("completed claim cannot be reclaimed", record=record)
        record["state"] = "stale_reclaimed"
        record["reclaimed_at"] = _now_iso(now)
        record["reason"] = reason
        self._archive_record(key, record)
        claim_path.unlink()
        return record

    def _archive_record(self, key: str, record: dict[str, Any]) -> Path:
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        archive_path = self.archive_dir / f"{key}.{stamp}.json"
        _atomic_write_json(archive_path, record)
        return archive_path

    def is_completed(self, path: str | Path) -> bool:
        key = self.key_for_path(path)
        claim_path = self._claim_path(key)
        if not claim_path.exists():
            return False
        try:
            return _read_json(claim_path).get("state") == "completed"
        except (OSError, json.JSONDecodeError):
            return False

    def find_claim_by_branch(self, branch: str) -> Optional[dict[str, Any]]:
        for record in self.status_records(include_registered=False):
            if record.get("branch") == branch and record.get("state") != "stale_reclaimed":
                return record
        return None

    def status_records(self, *, include_registered: bool = True) -> list[dict[str, Any]]:
        records: dict[str, dict[str, Any]] = {}
        if include_registered and self.registrations_dir.exists():
            for path in sorted(self.registrations_dir.glob("*.json")):
                try:
                    rec = _read_json(path)
                except (OSError, json.JSONDecodeError):
                    continue
                records[rec["key"]] = rec
        if self.claims_dir.exists():
            for path in sorted(self.claims_dir.glob("*.json")):
                try:
                    rec = _read_json(path)
                except (OSError, json.JSONDecodeError):
                    continue
                records[rec["key"]] = rec
        return sorted(records.values(), key=lambda r: str(r.get("canonical_impl_path", "")))

    def status_text(self) -> str:
        records = self.status_records()
        if not records:
            return "wave board: empty"
        lines = ["wave board:"]
        for rec in records:
            line = (
                f"- {rec.get('impl_name', '?')} state={rec.get('state', '?')}"
                f" session={rec.get('session_id', '-')}"
                f" run={rec.get('run_id', '-')}"
                f" branch={rec.get('branch', '-')}"
                f" worktree={rec.get('worktree', '-')}"
                f" heartbeat={rec.get('heartbeat_at', '-')}"
            )
            lines.append(line)
        return "\n".join(lines)

    def reset(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

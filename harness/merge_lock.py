"""merge_lock — repo-level peer finalize mutex and task order gate (#641)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from harness.wave_board import WaveBoard

__all__ = [
    "LockBusy",
    "MergeLock",
    "MergeLockToken",
    "MergeOrderBlocked",
    "MergeOrderResult",
    "PeerMergeGuard",
    "check_merge_order",
    "external_git_completed",
]

_JSON_MODE = 0o600


class LockBusy(RuntimeError):
    """Raised when another peer session holds the merge lock."""


class MergeOrderBlocked(RuntimeError):
    """Raised when prior sibling task completion cannot be proven."""

    def __init__(self, result: "MergeOrderResult"):
        super().__init__(result.reason)
        self.result = result


@dataclass(frozen=True)
class MergeLockToken:
    token: str
    path: str
    record: dict


@dataclass(frozen=True)
class MergeOrderResult:
    allowed: bool
    reason: str
    blocked_prior_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class PeerMergeGuard:
    mode: str  # "serial" | "peer"
    token: str
    claim_key: str
    impl_path: str
    order: MergeOrderResult


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _direct_create_json(path: Path, payload: dict) -> None:
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


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    os.chmod(path, _JSON_MODE)


class MergeLock:
    """Repo-level O_EXCL mutex for PR finalize."""

    def __init__(self, repo_root: str | Path, *, state_root: str | Path | None = None):
        self.repo_root = Path(repo_root).resolve()
        self.state_root = (
            Path(state_root).resolve()
            if state_root is not None
            else self.repo_root / ".claude" / "harness-state"
        )
        self.root = self.state_root / "merge-lock"
        self.lock_path = self.root / "merge.lock"
        self.archive_dir = self.root / "archive"

    def acquire(self, *, owner: str, branch: str, pr_number: int | None = None) -> MergeLockToken:
        token = uuid.uuid4().hex
        record = {
            "token": token,
            "owner": owner,
            "branch": branch,
            "pr_number": pr_number,
            "pid": os.getpid(),
            "state": "locked",
            "acquired_at": _now_iso(),
        }
        try:
            _direct_create_json(self.lock_path, record)
        except FileExistsError:
            try:
                existing = _read_json(self.lock_path)
            except (OSError, json.JSONDecodeError):
                existing = {}
            holder = existing.get("owner") or existing.get("branch") or "unknown"
            raise LockBusy(f"merge lock is held by {holder}")
        return MergeLockToken(token, str(self.lock_path), record)

    def release(self, token: str, *, state: str = "released", reason: str = "") -> dict:
        if not self.lock_path.exists():
            return {"state": "missing"}
        record = _read_json(self.lock_path)
        if record.get("token") != token:
            raise LockBusy("merge lock token mismatch")
        record["state"] = state
        record["released_at"] = _now_iso()
        if reason:
            record["reason"] = reason
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = self.archive_dir / f"{record['token']}.json"
        _atomic_write_json(archive_path, record)
        self.lock_path.unlink()
        return record


def _extract_frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        out[key.strip()] = value.strip().strip("'\"")
    return out


def _task_index_i(value: str) -> Optional[int]:
    m = re.fullmatch(r"(\d+)/(\d+)", value.strip())
    if not m:
        return None
    return int(m.group(1))


def _story_is_numeric(value: str) -> bool:
    return bool(re.fullmatch(r"\d+", value.strip()))


def _prior_sibling_impls(current: Path) -> tuple[Path, ...]:
    current_fm = _extract_frontmatter(current)
    story = current_fm.get("story", "")
    current_i = _task_index_i(current_fm.get("task_index", ""))
    if not _story_is_numeric(story) or current_i is None:
        return ()
    prior: list[Path] = []
    for path in sorted(current.parent.glob("*.md")):
        if path.resolve(strict=False) == current.resolve(strict=False):
            continue
        fm = _extract_frontmatter(path)
        if fm.get("story", "").strip() != story.strip():
            continue
        idx = _task_index_i(fm.get("task_index", ""))
        if idx is not None and idx < current_i:
            prior.append(path)
    return tuple(prior)


def check_merge_order(
    board: WaveBoard,
    impl_path: str | Path,
    *,
    external_completed: Callable[[str], bool] | None = None,
) -> MergeOrderResult:
    current = Path(board.canonical_path(impl_path))
    prior = _prior_sibling_impls(current)
    if not prior:
        return MergeOrderResult(True, "story order gate not applicable")
    external_completed = external_completed or (lambda _path: False)
    blocked: list[str] = []
    for path in prior:
        canonical = board.canonical_path(path)
        if board.is_completed(canonical) or external_completed(canonical):
            continue
        blocked.append(canonical)
    if blocked:
        names = ", ".join(Path(p).name for p in blocked)
        return MergeOrderResult(
            False,
            f"prior task completion not proven: {names}",
            tuple(blocked),
        )
    return MergeOrderResult(True, "all prior story tasks completed")


def external_git_completed(
    repo_root: str | Path,
    impl_path: str | Path,
    *,
    base_ref: str = "origin/main",
) -> bool:
    """Best-effort merged evidence for prior task completion outside the board."""

    root = Path(repo_root)
    slug = Path(impl_path).stem
    try:
        result = subprocess.run(
            ["git", "log", base_ref, "--grep", slug, "--format=%H", "-n", "1"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def acquire_peer_merge_guard(
    board: WaveBoard,
    lock: MergeLock,
    *,
    branch: str,
    pr_number: int | None,
    owner: str,
    external_completed: Callable[[str], bool] | None = None,
) -> PeerMergeGuard:
    claim = board.find_claim_by_branch(branch)
    if not claim:
        return PeerMergeGuard(
            "serial",
            "",
            "",
            "",
            MergeOrderResult(True, "peer claim not registered for branch"),
        )
    if claim.get("state") != "claimed":
        raise MergeOrderBlocked(
            MergeOrderResult(
                False,
                (
                    f"peer claim state is {claim.get('state', 'unknown')}; "
                    "explicit wave-reclaim is required before finalize"
                ),
                (claim.get("canonical_impl_path", ""),),
            )
        )
    order = check_merge_order(
        board,
        claim["canonical_impl_path"],
        external_completed=external_completed,
    )
    if not order.allowed:
        raise MergeOrderBlocked(order)
    token = lock.acquire(owner=owner, branch=branch, pr_number=pr_number)
    return PeerMergeGuard(
        "peer",
        token.token,
        claim["key"],
        claim["canonical_impl_path"],
        order,
    )

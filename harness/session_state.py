"""session_state.py — 세션/run 격리 상태 API (멀티세션 기본 가정).

발상 (`docs/archive/conveyor-design.md` §4 / §6 / §9):
    Claude Code 가 세션 단위 동작 → 한 사용자가 동시 다중 세션 띄울 수 있음.
    각 세션 안에서 컨베이어가 다중 run 가능 (예: 백그라운드 ralph + foreground impl).
    sid × run_id 별 격리된 디렉토리 구조 + `_meta` envelope 으로 leftover 방어.

본 모듈은 다음을 단일 책임으로 묶는다:
    1. session_id 검증 + env/by-pid/active-run resolution
    2. run_id 생성 (`run-{token_hex(4)}`)
    3. atomic write (O_EXCL+fsync+rename+dir fsync, 0o600 — RWH 패턴)
    4. live.json 스키마 + active_runs map 조작 (OMC `SkillActiveStateV2` 차용)

OMC + RWH 차용 매핑:
    - regex `^[a-zA-Z0-9][a-zA-Z0-9_-]{0,255}$`           ← OMC SESSION_ID_ALLOWLIST
    - stdin 3 변형 fallback (sessionId/session_id/sessionid) ← OMC
    - resolution (env > by-pid > active run scan)
    - `_meta` envelope + 자기참조 sessionId 검증            ← RWH
    - atomic write O_EXCL+fsync+rename+dir fsync           ← RWH
    - active_runs map + soft tombstone                     ← OMC SkillActiveStateV2

핵심 상수:
    SESSION_ID_RE       : path traversal 방어
    DEFAULT_RUN_TTL_SEC : run 슬롯 stale 기준 (24h)
    LIVE_JSON_VERSION   : 스키마 진화 추적
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import secrets
import select
import shutil
# Fixed git/gh/ps argv probes in this module run without shell and with timeouts.
import subprocess  # nosec B404
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Literal, Optional, overload

__all__ = [
    "SESSION_ID_RE",
    "DEFAULT_RUN_TTL_SEC",
    "DEFAULT_PID_TTL_SEC",
    "DEFAULT_RUN_DIR_TTL_SEC",
    "LIVE_JSON_VERSION",
    "StateFormatError",
    "STDIN_TIMEOUT_SEC",
    "valid_cc_pid",
    "pid_session_path",
    "pid_run_path",
    "write_pid_session",
    "read_pid_session",
    "write_pid_current_run",
    "read_pid_current_run",
    "clear_pid_current_run",
    "cleanup_stale_pid_files",
    "get_cc_pid_via_ppid_chain",
    "auto_detect_session_id",
    "auto_detect_run_id",
    "valid_session_id",
    "session_id_from_stdin",
    "current_session_id",
    "generate_run_id",
    "atomic_write",
    "session_dir",
    "run_dir",
    "live_path",
    "read_live",
    "transition",
    "evaluate_order_gate_for_step",
    "impl_scope_paths_for_run",
    "run_prose_has_pass",
    "cleanup_stale_run_dirs",
]

# ── 상수 ─────────────────────────────────────────────────────────────
SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,255}$")
RUN_ID_RE = re.compile(r"^run-[a-z0-9]{8}$")

DEFAULT_RUN_TTL_SEC = 24 * 60 * 60        # 24h — completed slot 보관 후 cleanup
DEFAULT_PID_TTL_SEC = 24 * 60 * 60        # 24h — by-pid 파일 stale 기준 (PID 재사용 보호)
DEFAULT_RUN_DIR_TTL_SEC = 7 * 24 * 60 * 60  # 7d — run 디렉토리(prose/ledger) 보관. /run-review 원자료라 슬롯(24h)보다 길게
STALE_STEP_TTL_SEC = 30 * 60              # 30min — current_step heartbeat stale 기준 (DCN-30-30)
LIVE_JSON_VERSION = 1                      # 스키마 진화 추적
STDIN_TIMEOUT_SEC = 2.0                    # 훅 stdin 읽기 hang 방지
_ATOMIC_FILE_MODE = 0o600
_PPID_LOOKUP_TIMEOUT_SEC = 2.0
FAIL_OPEN_EVENTS_NAME = "fail-open-events.jsonl"
FAIL_OPEN_RECENT_HOURS = 24
FAIL_OPEN_RECENT_LIMIT = 5
_FAIL_OPEN_DETAIL_MAX = 500


class StateFormatError(ValueError):
    """Current persisted state is malformed and must be recreated."""


# ── 경로 유틸 ───────────────────────────────────────────────────────


_DEFAULT_BASE_CACHE: Dict[str, Path] = {}
_REPO_ROOT_CACHE: Dict[str, Path] = {}


def _resolve_state_root_for_cwd(cwd_str: str) -> Path:
    """git rev-parse --git-common-dir 으로 main repo 의 state root 해석.

    worktree 진입 (cwd = `.claude/worktrees/{name}/`) 후에도 `git rev-parse
    --git-common-dir` 은 main repo `.git` 를 가리킨다 (git 표준). 그래서 main repo
    의 `.claude/harness-state/` 가 단일 source 가 됨 → SessionStart 훅이 main
    repo 에서 쓴 by-pid / live.json 을 worktree 안 helper 도 그대로 본다.

    git 미설치 / git 리포 아님 / subprocess 실패 → cwd 기준으로 동작한다.
    cwd 별 캐시 (subprocess 반복 호출 회피).
    """
    if cwd_str in _DEFAULT_BASE_CACHE:
        return _DEFAULT_BASE_CACHE[cwd_str]
    cwd = Path(cwd_str)
    try:
        result = subprocess.run(  # nosec B603, B607
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd_str,
            timeout=_PPID_LOOKUP_TIMEOUT_SEC,
        )
        common_str = result.stdout.strip()
        if common_str:
            common_path = Path(common_str)
            if not common_path.is_absolute():
                common_path = cwd / common_path
            main_root = common_path.parent.resolve()
            base = main_root / ".claude" / "harness-state"
            _DEFAULT_BASE_CACHE[cwd_str] = base
            return base
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
        OSError,
    ):
        pass
    base = cwd / ".claude" / "harness-state"
    _DEFAULT_BASE_CACHE[cwd_str] = base
    return base


def _clear_default_base_cache() -> None:
    """테스트 보조 — git path probe cache 무력화."""
    _DEFAULT_BASE_CACHE.clear()
    _REPO_ROOT_CACHE.clear()


def _default_base() -> Path:
    return _resolve_state_root_for_cwd(str(Path.cwd().resolve()))


def _git_show_toplevel_cached(cwd: Path) -> Optional[Path]:
    """Return git repo root for cwd, caching the rev-parse probe per process."""
    cwd_key = str(cwd.resolve())
    if cwd_key in _REPO_ROOT_CACHE:
        return _REPO_ROOT_CACHE[cwd_key]
    try:
        result = subprocess.run(  # nosec B603, B607
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd_key,
            timeout=_PPID_LOOKUP_TIMEOUT_SEC,
        )
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
        OSError,
    ):
        return None
    root = result.stdout.strip()
    if not root:
        return None
    root_path = Path(root).resolve()
    _REPO_ROOT_CACHE[cwd_key] = root_path
    return root_path


def _resolve_base(base_dir: Optional[Path]) -> Path:
    if base_dir is None:
        return _default_base().resolve()
    if not isinstance(base_dir, (str, Path)):
        raise TypeError(f"base_dir must be Path or str, got {type(base_dir).__name__}")
    return Path(base_dir).resolve()


def session_dir(
    session_id: str, *, base_dir: Optional[Path] = None, create: bool = False
) -> Path:
    """`.sessions/{sid}/` 절대 경로."""
    if not valid_session_id(session_id):
        raise ValueError(f"invalid session_id: {session_id!r}")
    base = _resolve_base(base_dir)
    target = (base / ".sessions" / session_id).resolve()
    # path traversal 방어
    try:
        target.relative_to(base)
    except ValueError as e:
        raise ValueError(f"path escape: {target} not under {base}") from e
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target


def run_dir(
    session_id: str,
    run_id: str,
    *,
    base_dir: Optional[Path] = None,
    create: bool = False,
) -> Path:
    """`.sessions/{sid}/runs/{run_id}/` 절대 경로."""
    if not RUN_ID_RE.match(run_id):
        raise ValueError(
            f"invalid run_id: {run_id!r} (expected format: run-{{8 hex chars}})"
        )
    target = (session_dir(session_id, base_dir=base_dir) / "runs" / run_id).resolve()
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target


def live_path(session_id: str, *, base_dir: Optional[Path] = None) -> Path:
    """`.sessions/{sid}/live.json` 경로 — 읽기 전용 (디렉토리 미생성)."""
    return session_dir(session_id, base_dir=base_dir) / "live.json"


# ── session_id 검증 ─────────────────────────────────────────────────


def valid_session_id(sid: Any) -> bool:
    """OMC 패턴 — path traversal 방어."""
    if not isinstance(sid, str):
        return False
    return bool(SESSION_ID_RE.match(sid))


def session_id_from_stdin(
    data: Optional[Dict[str, Any]] = None,
    timeout_sec: float = STDIN_TIMEOUT_SEC,
) -> str:
    """훅 stdin 또는 파싱된 dict 에서 session_id 추출.

    OMC 패턴 — 3 변형 fallback (sessionId / session_id / sessionid).
    검증 실패 시 빈 문자열.

    Args:
        data: 이미 파싱된 dict. None 이면 stdin 직접 read.
        timeout_sec: stdin 읽기 타임아웃 (hang 방지).
    """
    d: Optional[Dict[str, Any]] = data
    if d is None:
        try:
            if sys.stdin.isatty():
                return ""
            if timeout_sec > 0:
                ready, _, _ = select.select([sys.stdin], [], [], timeout_sec)
                if not ready:
                    return ""
            raw = sys.stdin.read()
            d = json.loads(raw) if raw.strip() else {}
        except (json.JSONDecodeError, OSError, ValueError):
            return ""
    if not isinstance(d, dict):
        return ""
    sid = d.get("session_id") or d.get("sessionId") or d.get("sessionid") or ""
    return sid if valid_session_id(sid) else ""


def current_session_id(*, base_dir: Optional[Path] = None) -> str:
    """`DCNESS_SESSION_ID` 환경변수의 유효한 현재 세션 ID를 반환한다."""
    del base_dir
    sid = os.environ.get("DCNESS_SESSION_ID", "")
    return sid if valid_session_id(sid) else ""


# ── run_id 생성 ──────────────────────────────────────────────────────


def generate_run_id() -> str:
    """`run-{token_hex(4)}` — 16M 조합, sid 안 충돌 사실상 0."""
    return f"run-{secrets.token_hex(4)}"


# ── atomic write (O_EXCL+fsync+rename+dir fsync, 0o600) ─────────────


def atomic_write(
    target: Path, content: bytes, *, mode: int = _ATOMIC_FILE_MODE
) -> None:
    """RWH 패턴 — POSIX atomic 보장.

    1. tmp 파일 (O_EXCL — 같은 이름 충돌 시 raise)
    2. write + fsync
    3. close
    4. rename (atomic)
    5. dir fsync (POSIX 강제)

    Args:
        target: 최종 파일 경로.
        content: bytes.
        mode: 0o600 기본 (소유자만).
    """
    if not isinstance(content, (bytes, bytearray)):
        raise TypeError(f"content must be bytes, got {type(content).__name__}")
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    # unique tmp 이름 — O_EXCL 충돌 회피 + race-safe
    tmp_name = f"{target.name}.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}"
    tmp = target.parent / tmp_name

    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        os.write(fd, bytes(content))
        os.fsync(fd)
    finally:
        os.close(fd)

    try:
        os.replace(tmp, target)  # POSIX atomic rename
    except OSError:
        # 정리: tmp 가 남았으면 제거
        try:
            tmp.unlink()
        except OSError:
            pass
        raise

    # dir fsync — 새 entry 가 디스크에 박히도록 (POSIX 권장)
    try:
        dir_fd = os.open(str(target.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        # 일부 파일시스템 (tmpfs 등) 은 dir fsync 미지원 — 무시
        pass


# ── live.json read / update ──────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _make_meta(session_id: str) -> Dict[str, Any]:
    return {
        "sessionId": session_id,
        "writtenAt": _now_iso(),
        "version": LIVE_JSON_VERSION,
    }


def read_live(
    session_id: str, *, base_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """Read the only supported live.json schema; missing state is empty."""
    if not valid_session_id(session_id):
        return {}
    path = live_path(session_id, base_dir=base_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise _state_format_error(path, f"unreadable JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise _state_format_error(path, "root must be an object")
    meta = data.get("_meta")
    if not isinstance(meta, dict):
        raise _state_format_error(path, "missing _meta object")
    if meta.get("version") != LIVE_JSON_VERSION:
        raise _state_format_error(
            path,
            f"unsupported version={meta.get('version')!r}; expected {LIVE_JSON_VERSION}",
        )
    if meta.get("sessionId") != session_id or data.get("session_id") != session_id:
        raise _state_format_error(path, "session identity mismatch")
    if not isinstance(data.get("active_runs"), dict):
        raise _state_format_error(path, "missing active_runs object")
    return data


def _state_format_error(path: Path, detail: str) -> StateFormatError:
    return StateFormatError(
        f"current run state is invalid at {path}: {detail}; "
        "remove that session state and rerun the workflow to recreate it"
    )


def _empty_live(session_id: str) -> Dict[str, Any]:
    return {
        "session_id": session_id,
        "active_runs": {},
        "_meta": _make_meta(session_id),
    }


def _write_live(
    session_id: str, state: Dict[str, Any], *, base_dir: Optional[Path] = None
) -> None:
    """Canonical live.json writer. Call only while holding the session lock."""
    state["session_id"] = session_id
    state["active_runs"] = state.get("active_runs", {})
    state["_meta"] = _make_meta(session_id)
    payload = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True)
    atomic_write(live_path(session_id, base_dir=base_dir), payload.encode("utf-8"))


@contextmanager
def _session_lock(
    session_id: str, *, base_dir: Optional[Path] = None
) -> Iterator[None]:
    lock_path = session_dir(session_id, base_dir=base_dir, create=True) / ".state.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _append_ledger_record(
    session_id: str,
    run_id: str,
    event: str,
    *,
    base_dir: Optional[Path] = None,
    **fields: Any,
) -> Dict[str, Any]:
    """Canonical append-only ledger writer; transition() owns every call."""
    from harness import ledger

    if event not in ledger.EVENT_TYPES:
        raise ValueError(f"unknown ledger event: {event!r}")
    record = {"event": event, "ts": _now_iso()}
    record.update({key: value for key, value in fields.items() if key not in {"event", "ts"}})
    path = ledger.ledger_path(session_id, run_id, base_dir=base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return record


# ── active_runs map 조작 ────────────────────────────────────────────


def _resolve_run_dir_str(
    session_id: str, run_id: str, base_dir: Optional[Path]
) -> str:
    """run_dir 의 문자열 표현 — base_dir 가 cwd 안이면 상대경로, 아니면 절대."""
    rd = run_dir(session_id, run_id, base_dir=base_dir)
    try:
        return str(rd.relative_to(Path.cwd()))
    except ValueError:
        return str(rd)


# design_doc 으로 인정하는 설계 산출물 표준 경로 prefix (impl 문서).
# 기록 시점에 repo-root 상대 prefix 앵커로 검증해 임의
# .md(README 등)·traversal(`..`)·repo 밖 경로가 implementation gate 사전 조건
# 증거가 되지 못하게 한다 (#701).
_DESIGN_DOC_DIR_MARKERS = (
    "docs/epics/",
)


def _validate_design_doc(design_doc: str) -> str:
    """begin-run `--design-doc` 경로 fail-fast 검증 (#701) — resolve 절대경로 반환.

    implementation gate 의 사전 조건 증거로 쓰이므로 기록 시점에 (1) .md 파일,
    (2) repo root(= helper 호출 cwd) 기준 설계 산출물 규약 경로 *안*, (3)
    디스크 실존을 확인한다. 게이트는 호출 시점에 실존을 재확인한다 (기록 후
    삭제 방어).

    상대경로를 받은 그대로 기록하면 begin-run cwd(worktree)와 hook 프로세스
    cwd 가 달라 게이트가 false-block 하므로 resolve 된 절대경로로 기록한다.
    prefix 앵커 비교(substring 아님)라 traversal/symlink/repo 밖 경로는
    resolve 후 거부된다.
    """
    if not isinstance(design_doc, str) or not design_doc.strip():
        raise ValueError("design_doc must be non-empty str")
    doc = design_doc.strip()
    if not doc.endswith(".md"):
        raise ValueError(f"design_doc must be a .md file: {doc!r}")
    resolved = Path(doc).resolve()
    root = Path.cwd().resolve()
    try:
        rel_posix = resolved.relative_to(root).as_posix()
    except ValueError:
        raise ValueError(
            f"design_doc must live under the repo root ({root}): {doc!r}"
        ) from None
    if not any(rel_posix.startswith(marker) for marker in _DESIGN_DOC_DIR_MARKERS):
        raise ValueError(
            "design_doc must be a design artifact path under "
            f"{' | '.join(_DESIGN_DOC_DIR_MARKERS)}: {doc!r}"
        )
    if not resolved.is_file():
        raise ValueError(f"design_doc not found on disk: {doc!r}")
    return str(resolved)


# /impl lane(설계도 유무) 닫힌 enum (#714). lite = 설계도 없음,
# standard = 설계도 있음. implementation gate 가 lane=lite 를 설계 산출물
# 사전 조건 면제 신호로 인정하므로, 임의 문자열이 면제를 유발하지 못하게
# 기록 시점에 이 집합으로 fail-fast 검증한다.
_VALID_LANES = ("lite", "standard")
_VALID_DESIGN_STAGES = ("design-ux", "design-system")
_RUN_TRANSITIONS = {
    "run_started",
    "run_blocked",
    "run_finalized",
    "run_completed",
    "ledger_checkpoint",
}
_STEP_TRANSITIONS = {"step_started", "step_aborted", "step_completed"}
_RUNTIME_TRANSITIONS = {
    "pending_agent_set",
    "pending_agent_spawned",
    "pending_agent_cleared",
    "step_identity_bound",
    "active_agent_set",
    "prose_staged",
    "stop_block_recorded",
    "post_task_marked",
    "stale_runs_cleaned",
}
_TRANSITIONS_WITHOUT_RUN_ID = {
    "session_initialized",
    "active_agent_set",
    "post_task_marked",
    "stale_runs_cleaned",
}


def transition(
    session_id: str,
    action: str,
    *,
    run_id: Optional[str] = None,
    base_dir: Optional[Path] = None,
    **data: Any,
) -> Any:
    """Canonical writer boundary for current session state and run ledger."""
    if not valid_session_id(session_id):
        raise ValueError(f"invalid session_id: {session_id!r}")
    if action not in _TRANSITIONS_WITHOUT_RUN_ID:
        if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
            raise ValueError(f"invalid run_id: {run_id!r}")

    result: Any = None
    state_changed = False
    with _session_lock(session_id, base_dir=base_dir):
        live = read_live(session_id, base_dir=base_dir) or _empty_live(session_id)
        active = dict(live["active_runs"])
        if action == "session_initialized":
            state_changed = not live_path(session_id, base_dir=base_dir).exists()
        elif action in _RUN_TRANSITIONS:
            run_id = _required_run_id(run_id)
            result, state_changed = _apply_run_transition(
                session_id, run_id, action, active, base_dir, data
            )
        elif action in _STEP_TRANSITIONS:
            run_id = _required_run_id(run_id)
            result, state_changed = _apply_step_transition(
                session_id, run_id, action, active, base_dir, data
            )
        elif action in _RUNTIME_TRANSITIONS:
            result, state_changed = _apply_runtime_transition(
                run_id, action, live, active, data
            )
        else:
            raise ValueError(f"unknown run state transition: {action!r}")
        if state_changed:
            live["active_runs"] = active
            _write_live(session_id, live, base_dir=base_dir)
    return result


def _apply_run_transition(
    session_id: str,
    run_id: str,
    action: str,
    active: Dict[str, Any],
    base_dir: Optional[Path],
    data: Dict[str, Any],
) -> tuple[Any, bool]:
    from harness import ledger

    if action == "run_started":
        entry_point = data.get("entry_point")
        lane = data.get("lane")
        stage = data.get("stage")
        design_doc = data.get("design_doc")
        acceptance_required = bool(data.get("acceptance_required", False))
        if not isinstance(entry_point, str) or not entry_point:
            raise ValueError("entry_point must be non-empty str")
        if lane is not None and (entry_point != "impl" or lane not in _VALID_LANES):
            raise ValueError(f"lane must be one of {_VALID_LANES} for entry_point=impl")
        if stage is not None and (
            entry_point != "design" or stage not in _VALID_DESIGN_STAGES
        ):
            raise ValueError(
                f"stage must be one of {_VALID_DESIGN_STAGES} for entry_point=design"
            )
        if acceptance_required and entry_point != "impl":
            raise ValueError("acceptance_required is only valid for entry_point=impl")
        if design_doc is not None:
            if entry_point != "impl":
                raise ValueError("design_doc is only valid for entry_point=impl")
            design_doc = _validate_design_doc(design_doc)
        if run_id in active:
            raise ValueError(f"run_id already active: {run_id}")
        now = _now_iso()
        active[run_id] = {
            "run_id": run_id,
            "entry_point": entry_point,
            "started_at": now,
            "last_confirmed_at": now,
            "completed_at": None,
            "run_dir": _resolve_run_dir_str(session_id, run_id, base_dir),
            "current_step": None,
            "issue_num": data.get("issue_num"),
            "design_doc": design_doc,
            "lane": lane,
            "stage": stage,
            "acceptance_required": acceptance_required,
        }
        run_dir(session_id, run_id, base_dir=base_dir, create=True)
        event_fields = {
            key: value
            for key, value in {
                "entry_point": entry_point,
                "issue_num": data.get("issue_num"),
                "design_doc": design_doc,
                "lane": lane,
                "stage": stage,
                "acceptance_required": True if acceptance_required else None,
            }.items()
            if value is not None
        }
        _append_ledger_record(
            session_id, run_id, "run_started", base_dir=base_dir, **event_fields
        )
        return None, True
    if action == "run_blocked":
        slot = _active_slot(active, run_id)
        category = data.get("category")
        if not isinstance(category, str) or not category:
            raise ValueError("category must be non-empty str")
        marker = {"category": category, "at": _now_iso()}
        for key in ("agent", "mode", "provider", "reason", "raw_log"):
            if data.get(key) is not None:
                marker[key] = data[key]
        slot["blocked"] = marker
        slot["last_confirmed_at"] = marker["at"]
        active[run_id] = slot
        _append_ledger_record(session_id, run_id, "blocked", base_dir=base_dir, **data)
        return marker, True
    if action == "run_finalized":
        slot = _active_slot(active, run_id)
        slot["finalized_at"] = _now_iso()
        active[run_id] = slot
        return None, True
    if action == "run_completed":
        if run_id not in active:
            return None, False
        slot = dict(active[run_id])
        if slot.get("completed_at"):
            return None, False
        now = _now_iso()
        slot.update(completed_at=now, last_confirmed_at=now, current_step=None)
        active[run_id] = slot
        _append_ledger_record(session_id, run_id, "run_finished", base_dir=base_dir)
        return None, True

    _active_slot(active, run_id)
    event = data.pop("event", None)
    if event not in ledger.MANUAL_EVENT_TYPES:
        raise ValueError(f"manual event must be one of {sorted(ledger.MANUAL_EVENT_TYPES)}")
    return (
        _append_ledger_record(session_id, run_id, event, base_dir=base_dir, **data),
        False,
    )


def _apply_step_transition(
    session_id: str,
    run_id: str,
    action: str,
    active: Dict[str, Any],
    base_dir: Optional[Path],
    data: Dict[str, Any],
) -> tuple[Any, bool]:
    from harness import ledger
    from harness.agent_names import normalize_agent_type

    slot = _active_slot(active, run_id)
    raw_agent = data.get("agent")
    if not isinstance(raw_agent, str) or not raw_agent:
        raise ValueError("agent must be non-empty str")
    agent = normalize_agent_type(raw_agent) or raw_agent
    data["agent"] = agent

    def identity_mismatch(current: Dict[str, Any]) -> str:
        expected = (agent, data.get("mode"))
        actual = (current.get("agent"), current.get("mode"))
        if actual != expected:
            return f"agent/mode expected={expected!r} current={actual!r}"
        for key in ("tool_use_id", "agent_id"):
            value = data.get(key)
            if value and current.get(key) != value:
                return (
                    f"{key} expected={value!r} current={current.get(key)!r}"
                )
        return ""

    if action == "step_started":
        current = slot.get("current_step")
        if data.get("strict_identity") and isinstance(current, dict):
            mismatch = identity_mismatch(current)
            if mismatch:
                raise ValueError(f"lifecycle identity mismatch: {mismatch}")
            return current, False
        _warn_stale_step(slot)
        now = _now_iso()
        next_step = {
            "agent": agent,
            "mode": data.get("mode"),
            "started_at": now,
            "steps_count_at_begin": len(
                ledger.read_step_completed(session_id, run_id, base_dir=base_dir)
            ),
            **{
                key: data[key]
                for key in (
                    "tool_use_id",
                    "agent_id",
                    "lifecycle_owner",
                    "candidate_head",
                    "candidate_tree",
                    "candidate_root",
                )
                if data.get(key)
            },
        }
        slot["current_step"] = next_step
        slot["last_confirmed_at"] = now
        active[run_id] = slot
        event_fields = {
            "agent": agent,
            "mode": data.get("mode"),
            **{
                key: data[key]
                for key in (
                    "tool_use_id",
                    "agent_id",
                    "lifecycle_owner",
                    "candidate_head",
                    "candidate_tree",
                    "candidate_root",
                )
                if data.get(key)
            },
        }
        _append_ledger_record(
            session_id, run_id, "step_started", base_dir=base_dir,
            **event_fields,
        )
        return None, True

    if action == "step_aborted":
        current = slot.get("current_step")
        if not isinstance(current, dict):
            if data.get("strict_identity"):
                raise ValueError("lifecycle identity mismatch: current_step missing")
            return None, False
        mismatch = identity_mismatch(current)
        if mismatch:
            if data.get("strict_identity"):
                raise ValueError(f"lifecycle identity mismatch: {mismatch}")
            return None, False
        event_fields = {
            key: data[key]
            for key in (
                "agent",
                "mode",
                "tool_use_id",
                "agent_id",
                "category",
                "detail",
            )
            if data.get(key) is not None
        }
        result = _append_ledger_record(
            session_id,
            run_id,
            "step_aborted",
            base_dir=base_dir,
            **event_fields,
        )
        slot["current_step"] = None
        slot["last_confirmed_at"] = _now_iso()
        active[run_id] = slot
        return result, True

    if data.get("strict_identity") and data.get("tool_use_id"):
        for event in reversed(
            ledger.read_events(session_id, run_id, base_dir=base_dir)
        ):
            if (
                event.get("event") == "step_completed"
                and event.get("tool_use_id") == data["tool_use_id"]
            ):
                return event, False

    current = slot.get("current_step")
    if data.get("strict_identity"):
        if not isinstance(current, dict):
            raise ValueError("lifecycle identity mismatch: current_step missing")
        mismatch = identity_mismatch(current)
        if mismatch:
            raise ValueError(f"lifecycle identity mismatch: {mismatch}")

    receipt = ledger.build_receipt(
        agent, data.get("mode"), data.get("enum", "PROSE_LOGGED"),
        data.get("prose", ""), data.get("prose_path"), provider=data.get("provider"),
        tool_use_id=data.get("tool_use_id"), agent_id=data.get("agent_id"),
    )
    if isinstance(current, dict):
        for key in ("candidate_head", "candidate_tree", "candidate_root"):
            if current.get(key):
                receipt[key] = current[key]
    result = _append_ledger_record(
        session_id, run_id, "step_completed", base_dir=base_dir, **receipt
    )
    _record_headless_validation_block(session_id, run_id, base_dir, data)
    if not isinstance(current, dict) or (
        current.get("agent"), current.get("mode")
    ) != (agent, data.get("mode")):
        return result, False
    slot["current_step"] = None
    slot["last_confirmed_at"] = _now_iso()
    active[run_id] = slot
    return result, True


def _record_headless_validation_block(
    session_id: str,
    run_id: str,
    base_dir: Optional[Path],
    data: Dict[str, Any],
) -> None:
    if data.get("agent") != "build-worker" or data.get("provider") not in {
        "codex-headless",
        "claude-headless",
    }:
        return
    from harness.run_review import _extract_conclusion_enum

    if _extract_conclusion_enum(data.get("prose", "")) != "VALIDATION_BLOCKED":
        return
    _append_ledger_record(
        session_id,
        run_id,
        "blocked",
        base_dir=base_dir,
        agent=data.get("agent"),
        mode=data.get("mode"),
        provider=data.get("provider"),
        category="headless_validation_blocked",
        prose_file=str(data.get("prose_path")),
        detail=(
            "headless build-worker reported VALIDATION_BLOCKED; "
            "main must run the validation command fallback"
        ),
    )


def _claim_pending_agent_spawn(
    run_id: Optional[str],
    active: Dict[str, Any],
    data: Dict[str, Any],
) -> tuple[Any, bool]:
    """Bind a SubagentStart agent_id to the newest matching PreToolUse intent."""
    from harness.agent_names import normalize_agent_type

    resolved_run_id = _required_run_id(run_id)
    slot = _active_slot(active, resolved_run_id, missing_ok=True)
    agent_id = data.get("agent_id")
    agent = normalize_agent_type(data.get("agent") or "") or ""
    if slot is None or not agent_id or not agent:
        return None, False
    pending = dict(slot.get("pending_agents") or {})
    for record in pending.values():
        if isinstance(record, dict) and record.get("agent_id") == agent_id:
            return dict(record), False
    candidates = [
        (tool_use_id, record)
        for tool_use_id, record in pending.items()
        if isinstance(record, dict)
        and not record.get("agent_id")
        and (
            normalize_agent_type(record.get("sub_type") or "")
            or record.get("sub_type")
        )
        == agent
    ]
    if not candidates:
        return None, False
    tool_use_id, record = max(
        candidates, key=lambda item: str(item[1].get("started_at") or "")
    )
    claimed = dict(record)
    claimed["agent_id"] = agent_id
    claimed["spawned_at"] = _now_iso()
    pending[tool_use_id] = claimed
    slot["pending_agents"] = pending
    active[resolved_run_id] = slot
    return claimed, True


def _bind_current_step_identity(
    run_id: Optional[str],
    active: Dict[str, Any],
    data: Dict[str, Any],
) -> tuple[Any, bool]:
    """Attach hook correlation identity to an explicit current step."""
    from harness.agent_names import normalize_agent_type

    resolved_run_id = _required_run_id(run_id)
    slot = _active_slot(active, resolved_run_id)
    current = slot.get("current_step")
    if not isinstance(current, dict):
        raise ValueError("lifecycle identity mismatch: current_step missing")
    expected_agent = normalize_agent_type(data.get("agent") or "") or data.get("agent")
    expected = (expected_agent, data.get("mode"))
    actual = (current.get("agent"), current.get("mode"))
    if actual != expected:
        raise ValueError(
            f"lifecycle identity mismatch: agent/mode expected={expected!r} "
            f"current={actual!r}"
        )
    for key in ("tool_use_id", "agent_id"):
        value = data.get(key)
        existing = current.get(key)
        if existing and value and existing != value:
            raise ValueError(
                f"lifecycle identity mismatch: {key} expected={value!r} "
                f"current={existing!r}"
            )
        if value:
            current[key] = value
    current["lifecycle_owner"] = data.get("lifecycle_owner") or "hook"
    slot["current_step"] = current
    active[resolved_run_id] = slot
    return dict(current), True


def _apply_runtime_transition(
    run_id: Optional[str],
    action: str,
    live: Dict[str, Any],
    active: Dict[str, Any],
    data: Dict[str, Any],
) -> tuple[Any, bool]:
    if action == "pending_agent_set":
        run_id = _required_run_id(run_id)
        slot = _active_slot(active, run_id, missing_ok=True)
        tool_use_id = data.get("tool_use_id")
        if slot is None or not tool_use_id:
            return None, False
        pending = dict(slot.get("pending_agents") or {})
        pending[tool_use_id] = {
            "tool_use_id": tool_use_id,
            "sub_type": data.get("sub_type") or "",
            "mode": data.get("mode") or None,
            "background": bool(data.get("background", False)),
            "auto_start": bool(data.get("auto_start", False)),
            "started_at": _now_iso(),
        }
        slot["pending_agents"] = pending
        active[run_id] = slot
        return None, True
    if action == "pending_agent_spawned":
        return _claim_pending_agent_spawn(run_id, active, data)
    if action == "pending_agent_cleared":
        run_id = _required_run_id(run_id)
        slot = _active_slot(active, run_id, missing_ok=True)
        if slot is None:
            return None, False
        pending = dict(slot.get("pending_agents") or {})
        tool_use_id = data.get("tool_use_id")
        result = None
        if tool_use_id in pending:
            result = pending.pop(tool_use_id)
        elif not data.get("require_exact") and len(pending) == 1:
            result = pending.popitem()[1]
        if result is None:
            return None, False
        if pending:
            slot["pending_agents"] = pending
        else:
            slot.pop("pending_agents", None)
        active[run_id] = slot
        return result, True
    if action == "step_identity_bound":
        return _bind_current_step_identity(run_id, active, data)
    if action == "active_agent_set":
        agent = data.get("agent")
        if agent:
            live["active_agent"] = agent
            if data.get("mode"):
                live["active_mode"] = data["mode"]
            else:
                live.pop("active_mode", None)
        else:
            live.pop("active_agent", None)
            live.pop("active_mode", None)
        return None, True
    if action == "prose_staged":
        run_id = _required_run_id(run_id)
        slot = _active_slot(active, run_id)
        current = slot.get("current_step")
        if not isinstance(current, dict):
            return None, False
        current = dict(current)
        current["prose_file"] = str(data["prose_file"])
        slot["current_step"] = current
        active[run_id] = slot
        return None, True
    if action == "stop_block_recorded":
        run_id = _required_run_id(run_id)
        slot = _active_slot(active, run_id)
        counts = dict(slot.get("stop_block_count") or {})
        key = str(data["step_key"])
        counts[key] = int(counts.get(key, 0)) + 1
        slot["stop_block_count"] = counts
        active[run_id] = slot
        return counts[key], True
    if action == "post_task_marked":
        markers = list(live.get("post_task_markers") or [])
        markers.append({"at": _now_iso(), "reason": str(data.get("reason") or "")})
        live["post_task_markers"] = markers[-20:]
        return len(live["post_task_markers"]), True

    now = datetime.now(timezone.utc)
    ttl_sec = int(data.get("ttl_sec", DEFAULT_RUN_TTL_SEC))
    survivors: Dict[str, Any] = {}
    for candidate_rid, candidate in active.items():
        if not isinstance(candidate, dict):
            continue
        stamp = candidate.get("completed_at") or candidate.get("last_confirmed_at")
        try:
            age = (now - datetime.fromisoformat(str(stamp))).total_seconds()
        except (TypeError, ValueError):
            survivors[candidate_rid] = candidate
            continue
        if age <= ttl_sec:
            survivors[candidate_rid] = candidate
    removed = len(active) - len(survivors)
    if not removed:
        return 0, False
    active.clear()
    active.update(survivors)
    return removed, True


def _required_run_id(run_id: Optional[str]) -> str:
    if run_id is None:
        raise ValueError("run_id is required for this transition")
    return run_id


@overload
def _active_slot(
    active: Dict[str, Any], run_id: str, *, missing_ok: Literal[False] = False
) -> Dict[str, Any]: ...


@overload
def _active_slot(
    active: Dict[str, Any], run_id: str, *, missing_ok: Literal[True]
) -> Optional[Dict[str, Any]]: ...


def _active_slot(
    active: Dict[str, Any], run_id: str, *, missing_ok: bool = False
) -> Optional[Dict[str, Any]]:
    slot = active.get(run_id)
    if not isinstance(slot, dict):
        if missing_ok:
            return None
        raise ValueError(f"run_id not active: {run_id}")
    return dict(slot)


def _warn_stale_step(slot: Dict[str, Any]) -> None:
    current = slot.get("current_step")
    confirmed = slot.get("last_confirmed_at")
    if not isinstance(current, dict) or not isinstance(confirmed, str):
        return
    try:
        age = (
            datetime.now(timezone.utc)
            - datetime.fromisoformat(confirmed.replace("Z", "+00:00"))
        ).total_seconds()
    except ValueError:
        return
    if age > STALE_STEP_TTL_SEC:
        mode = current.get("mode")
        label = f"{current.get('agent', '?')}{':' + mode if mode else ''}"
        print(
            f"[session_state] STALE STEP WARN — previous current_step={label} "
            f"stale {int(age)}s (> {STALE_STEP_TTL_SEC}s). "
            "end-step 누락 의심 — ledger.jsonl 에 직전 step 기록 안 됨.",
            file=sys.stderr,
        )


def _read_or_empty(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError:
        return ""


_PROSE_OCCURRENCE_SUFFIX_RE = re.compile(r"^[1-9][0-9]*$")
_PROSE_MODE_SUFFIX_RE = re.compile(
    r"^(?:[A-Z][A-Z0-9_]{0,63}|[a-z][a-z0-9-]{0,63})"
    r"(?:-[1-9][0-9]*)?$"
)


def _run_prose_paths_for_agent(rd: Path, agent: str) -> list[Path]:
    """Return prose paths that `signal_io.signal_path` can create for an agent."""
    paths = [rd / f"{agent}.md"]
    try:
        for prose in sorted(rd.glob(f"{agent}-*.md")):
            name = prose.name
            suffix = name[len(agent) + 1:-3]
            if (
                _PROSE_OCCURRENCE_SUFFIX_RE.match(suffix)
                or _PROSE_MODE_SUFFIX_RE.match(suffix)
            ):
                paths.append(prose)
    except OSError:
        pass
    return paths


def run_prose_has_pass(rd: Path, agent: str) -> bool:
    """PASS marker lookup aligned with end-step prose filenames.

    Accepted names are `<agent>.md`, numeric occurrence files such as
    `<agent>-1.md`, mode-suffixed files such as
    `<agent>-CODE_VALIDATION.md` or `<agent>-epic-batch.md`, and mode
    occurrence files such as `<agent>-CODE_VALIDATION-1.md`.
    """
    for prose in _run_prose_paths_for_agent(rd, agent):
        if "PASS" in _read_or_empty(prose):
            return True
    return False


def _run_has_module_architect_pass(rd: Path) -> bool:
    """설계 gate 를 충족하는 module-architect PASS 확인.

    폐기된 ``CARTOGRAPHY_REFRESH`` mode는 설계 산출물이 아니었다. 업그레이드
    중 이어진 legacy run의 해당 PASS를 build-worker 설계 증거로 승격하지 않는다.
    """
    agent = "module-architect"
    refresh_stem = f"{agent}-CARTOGRAPHY_REFRESH"
    for prose in _run_prose_paths_for_agent(rd, agent):
        stem = prose.stem
        if stem == refresh_stem or re.fullmatch(
            rf"{re.escape(refresh_stem)}-[1-9][0-9]*", stem
        ):
            continue
        if "PASS" in _read_or_empty(prose):
            return True
    return False


def _slot_for_run(
    session_id: str,
    run_id: str,
    *,
    base_dir: Optional[Path] = None,
) -> dict:
    live = read_live(session_id, base_dir=base_dir) or {}
    active = live.get("active_runs", {}) if isinstance(live, dict) else {}
    slot = active.get(run_id, {}) if isinstance(active, dict) else {}
    return slot if isinstance(slot, dict) else {}


def _run_design_doc_exists(
    session_id: str,
    run_id: str,
    *,
    base_dir: Optional[Path] = None,
) -> bool:
    """현재 run 슬롯에 기록된 design_doc 이 디스크에 실존하는지."""
    doc = _run_design_doc_path(session_id, run_id, base_dir=base_dir)
    return bool(doc and doc.is_file())


def _run_design_doc_path(
    session_id: str,
    run_id: str,
    *,
    base_dir: Optional[Path] = None,
) -> Optional[Path]:
    """현재 run 슬롯의 design_doc 절대경로를 반환한다."""
    try:
        doc = _slot_for_run(session_id, run_id, base_dir=base_dir).get("design_doc")
        if not isinstance(doc, str) or not doc:
            return None
        return Path(doc)
    except (OSError, ValueError):
        return None


def impl_scope_paths_for_run(
    session_id: str,
    run_id: str,
    *,
    base_dir: Optional[Path] = None,
) -> tuple[str, ...]:
    """Return normalized `### 수정 허용` paths for the active impl run.

    Missing or stale plans intentionally yield no extra authority. If a task
    mixes exact paths with ambiguous prose, only the exact parsed paths are
    reused; ambiguity never widens authority.
    """
    doc = _run_design_doc_path(session_id, run_id, base_dir=base_dir)
    if doc is None or not doc.is_file():
        return ()
    try:
        from harness.parallel_wave import parse_impl_task

        parsed = parse_impl_task(doc)
    except (OSError, ValueError):
        return ()
    if not parsed.scope_paths:
        return ()
    return tuple(sorted(parsed.scope_paths))


def _run_lane(
    session_id: str,
    run_id: str,
    *,
    base_dir: Optional[Path] = None,
) -> Optional[str]:
    """현재 run 슬롯에 기록된 lane(설계도 유무) 반환."""
    try:
        lane = _slot_for_run(session_id, run_id, base_dir=base_dir).get("lane")
        return lane if isinstance(lane, str) else None
    except (OSError, ValueError):
        return None


def _run_entry_point(
    session_id: str,
    run_id: str,
    *,
    base_dir: Optional[Path] = None,
) -> str:
    try:
        entry = _slot_for_run(session_id, run_id, base_dir=base_dir).get("entry_point")
        return entry if isinstance(entry, str) else ""
    except (OSError, ValueError):
        return ""


def _run_worker_boundary_block_marker(
    session_id: str,
    run_id: str,
    *,
    base_dir: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    try:
        marker = _slot_for_run(session_id, run_id, base_dir=base_dir).get("blocked")
        if isinstance(marker, dict) and marker.get("category") == "worker_boundary":
            return marker
    except (OSError, ValueError):
        pass

    try:
        from harness import ledger

        for event in reversed(ledger.read_events(session_id, run_id, base_dir=base_dir)):
            if (
                event.get("event") == "blocked"
                and event.get("category") == "worker_boundary"
            ):
                return event
    except Exception:  # nosec B110
        pass
    return None


def _boundary_block_gate_message(marker: Dict[str, Any]) -> str:
    reason = marker.get("reason")
    raw_log = marker.get("raw_log")
    detail = ""
    if isinstance(reason, str) and reason:
        detail += f" reason={reason}"
    if isinstance(raw_log, str) and raw_log:
        detail += f" raw_log={raw_log}"
    return (
        "[순서 차단 훅: headless boundary BLOCK] 이 run 은 "
        "headless worker boundary BLOCK(category=worker_boundary) 기록이 있어 "
        "다음 step 을 시작할 수 없습니다. workspace diff 와 ledger marker 를 확인한 뒤 "
        "새 run 또는 명시적 수동 복구로 진행하세요."
        f"{detail}"
    )


_IMPLEMENTATION_ORDER_GATE_AGENTS = frozenset({"build-worker"})


def evaluate_order_gate_for_step(
    session_id: str,
    run_id: str,
    agent: str,
    mode: Optional[str] = None,
    *,
    base_dir: Optional[Path] = None,
    candidate_head: Optional[str] = None,
    candidate_tree: Optional[str] = None,
    candidate_root: Optional[str] = None,
) -> Optional[str]:
    """provider-independent step start order gate.

    Claude Agent 경로는 PreToolUse hook 에서, Codex/headless 경로는 helper
    `begin-step` 에서 같은 불변식을 평가한다. 반환값이 있으면 차단 메시지다.
    """
    from harness.agent_names import normalize_agent_type

    norm_agent = normalize_agent_type(agent) or agent
    rd = run_dir(session_id, run_id, base_dir=base_dir)

    boundary_block = _run_worker_boundary_block_marker(
        session_id, run_id, base_dir=base_dir
    )
    if boundary_block:
        return _boundary_block_gate_message(boundary_block)

    slot = _slot_for_run(session_id, run_id, base_dir=base_dir)
    if (
        norm_agent == "product-acceptance"
        and mode in {"STORY_ACCEPTANCE", "EPIC_ACCEPTANCE"}
        and slot.get("entry_point") == "impl"
        and slot.get("acceptance_required") is True
    ):
        from harness import ledger
        from harness.run_review import _extract_conclusion_enum

        validator = next(
            (
                step
                for step in reversed(
                    ledger.read_step_completed(
                        session_id, run_id, base_dir=base_dir
                    )
                )
                if step.get("agent") == "impl-validator"
                and step.get("mode") is None
            ),
            None,
        )
        if not isinstance(validator, dict):
            return (
                "[순서 차단 훅: close fail-fast] product-acceptance는 같은 frozen "
                "candidate의 holistic impl-validator 완료 뒤에만 시작할 수 있습니다."
            )
        try:
            prose = Path(str(validator.get("prose_file"))).read_text(
                encoding="utf-8", errors="ignore"
            )
        except OSError:
            prose = ""
        conclusion = _extract_conclusion_enum(prose)
        if conclusion != "PASS":
            return (
                "[순서 차단 훅: close fail-fast] holistic impl-validator가 terminal "
                f"PASS가 아닙니다(conclusion={conclusion or 'MISSING'}). finding을 "
                "수정하고 새 candidate에서 validator부터 재실행하세요."
            )
        requested_identity = (candidate_head, candidate_tree)
        requested_root = candidate_root
        if not all(requested_identity) or not requested_root:
            current = slot.get("current_step")
            if isinstance(current, dict) and (
                current.get("agent"),
                current.get("mode"),
            ) == (norm_agent, mode):
                if not all(requested_identity):
                    requested_identity = (
                        current.get("candidate_head"),
                        current.get("candidate_tree"),
                    )
                if not requested_root:
                    requested_root = current.get("candidate_root")
        validator_identity = (
            validator.get("candidate_head"),
            validator.get("candidate_tree"),
        )
        if any(validator_identity) and (
            not all(requested_identity)
            or requested_identity != validator_identity
        ):
            return (
                "[순서 차단 훅: close fail-fast] validator PASS candidate와 현재 "
                "acceptance candidate HEAD/tree가 다릅니다. Cartography sync와 "
                "candidate freeze 뒤 validator부터 재실행하세요."
            )
        validator_root = validator.get("candidate_root")
        if any(validator_identity) and not validator_root:
            return (
                "[순서 차단 훅: close fail-fast] validator PASS receipt에 frozen "
                "candidate workspace root가 없습니다. validator부터 새 candidate "
                "freeze로 재실행하세요."
            )
        if validator_root and (
            not requested_root or requested_root != validator_root
        ):
            return (
                "[순서 차단 훅: close fail-fast] validator PASS candidate와 현재 "
                "acceptance candidate workspace root가 다릅니다. 같은 worktree에서 "
                "candidate freeze 뒤 validator부터 재실행하세요."
            )

    if norm_agent in _IMPLEMENTATION_ORDER_GATE_AGENTS:
        lane_lite = _run_lane(session_id, run_id, base_dir=base_dir) == "lite"
        if (
            not lane_lite
            and not _run_has_module_architect_pass(rd)
            and not _run_design_doc_exists(session_id, run_id, base_dir=base_dir)
        ):
            return (
                "[순서 차단 훅: implementation gate] build-worker 호출은 "
                "설계 산출물 확보 후만 — "
                "같은 run 의 module-architect PASS prose (module-architect*.md 안 "
                "PASS 마커) 또는 begin-run "
                "--design-doc 으로 기록된 설계 문서 실존. "
                "충족 방법: module-architect step 을 PASS 로 완료하거나, 구현 run 을 "
                "시작할 때 `begin-run impl --design-doc <설계문서>` 를 기록하세요. "
                "명시적 direct 구현 경로라면 `begin-run impl --lane lite` 로 시작하세요."
            )
    return None


def _is_dcness_worktree_path(path: Path) -> bool:
    parts = path.resolve().parts
    for idx in range(len(parts) - 1):
        if parts[idx] == ".claude" and parts[idx + 1] == "worktrees":
            return True
    return False


def _active_worktree_root_for_prompt(*, cwd: Optional[Path] = None) -> Optional[str]:
    """Return the git worktree root when cwd is inside `.claude/worktrees/`.

    The value is a prompt-writing hint only. Failure stays silent so begin-step
    never blocks the loop for an advisory reminder.
    """
    probe_cwd = Path(cwd or Path.cwd()).resolve()
    root_path = _git_show_toplevel_cached(probe_cwd)
    if root_path is None:
        return None
    return str(root_path) if _is_dcness_worktree_path(root_path) else None


def cleanup_stale_run_dirs(
    *,
    ttl_sec: int = DEFAULT_RUN_DIR_TTL_SEC,
    base_dir: Optional[Path] = None,
) -> int:
    """오래된 run 디렉토리(prose/ledger) 삭제 — 모든 세션 공통.

    `.sessions/*/runs/<rid>/` 중 디렉토리·직계 파일의 최신 mtime 이 ttl_sec
    (기본 7일)을 초과한 run 디렉토리를 통째로 제거한다.

    run 슬롯(24h)·by-pid(24h)와 달리 prose 는 `/run-review` 사후 분석의
    원자료라 더 길게 보관한다. heartbeat TTL(24h)의 7배 여유 + 최신 mtime
    기준이라 7일 안에 쓰기가 한 번이라도 있던 run 은 보존된다 — 살아있는
    run 을 지울 일은 없다.

    Returns: 삭제된 run 디렉토리 수. 개별 실패는 건너뛴다 (best-effort).
    """
    base = _resolve_base(base_dir)
    sessions = base / ".sessions"
    if not sessions.exists():
        return 0
    now = datetime.now(timezone.utc).timestamp()
    removed = 0
    try:
        session_dirs = list(sessions.iterdir())
    except OSError:
        return 0
    for sdir in session_dirs:
        runs = sdir / "runs"
        if not runs.is_dir():
            continue
        try:
            run_dirs = list(runs.iterdir())
        except OSError:
            continue
        for rdir in run_dirs:
            if not rdir.is_dir():
                continue
            try:
                newest = rdir.stat().st_mtime
                for child in rdir.iterdir():
                    newest = max(newest, child.stat().st_mtime)
            except OSError:
                continue
            if now - newest > ttl_sec:
                try:
                    shutil.rmtree(rdir)
                    removed += 1
                except OSError:
                    pass
    return removed


# ── by-pid 레지스트리 (멀티세션 정합 핵심) ─────────────────────────


def valid_cc_pid(cc_pid: Any) -> bool:
    """양수 정수만 유효."""
    return isinstance(cc_pid, int) and cc_pid > 0


def pid_session_path(cc_pid: int, *, base_dir: Optional[Path] = None) -> Path:
    """`.by-pid/{cc_pid}` 절대 경로."""
    if not valid_cc_pid(cc_pid):
        raise ValueError(f"invalid cc_pid: {cc_pid!r}")
    return _resolve_base(base_dir) / ".by-pid" / str(cc_pid)


def pid_run_path(cc_pid: int, *, base_dir: Optional[Path] = None) -> Path:
    """`.by-pid-current-run/{cc_pid}` 절대 경로."""
    if not valid_cc_pid(cc_pid):
        raise ValueError(f"invalid cc_pid: {cc_pid!r}")
    return _resolve_base(base_dir) / ".by-pid-current-run" / str(cc_pid)


def write_pid_session(
    cc_pid: int, session_id: str, *, base_dir: Optional[Path] = None
) -> Path:
    """`.by-pid/{cc_pid}` ← session_id atomic 작성."""
    if not valid_session_id(session_id):
        raise ValueError(f"invalid session_id: {session_id!r}")
    target = pid_session_path(cc_pid, base_dir=base_dir)
    atomic_write(target, session_id.encode("utf-8"))
    return target


def read_pid_session(cc_pid: int, *, base_dir: Optional[Path] = None) -> str:
    """`.by-pid/{cc_pid}` 읽기. 미존재 / 잘못된 sid → 빈 문자열."""
    try:
        path = pid_session_path(cc_pid, base_dir=base_dir)
    except ValueError:
        return ""
    try:
        if not path.exists():
            return ""
        sid = path.read_text(encoding="utf-8").strip()
        return sid if valid_session_id(sid) else ""
    except OSError:
        return ""


def write_pid_current_run(
    cc_pid: int, run_id: str, *, base_dir: Optional[Path] = None
) -> Path:
    """`.by-pid-current-run/{cc_pid}` ← run_id atomic 작성."""
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"invalid run_id: {run_id!r}")
    target = pid_run_path(cc_pid, base_dir=base_dir)
    atomic_write(target, run_id.encode("utf-8"))
    return target


def read_pid_current_run(cc_pid: int, *, base_dir: Optional[Path] = None) -> str:
    """`.by-pid-current-run/{cc_pid}` 읽기. 미존재 → 빈 문자열."""
    try:
        path = pid_run_path(cc_pid, base_dir=base_dir)
    except ValueError:
        return ""
    try:
        if not path.exists():
            return ""
        rid = path.read_text(encoding="utf-8").strip()
        return rid if RUN_ID_RE.match(rid) else ""
    except OSError:
        return ""


def clear_pid_current_run(
    cc_pid: int, *, base_dir: Optional[Path] = None
) -> bool:
    """`.by-pid-current-run/{cc_pid}` 삭제. 성공 여부 반환."""
    try:
        path = pid_run_path(cc_pid, base_dir=base_dir)
    except ValueError:
        return False
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def cleanup_stale_pid_files(
    *,
    ttl_sec: int = DEFAULT_PID_TTL_SEC,
    base_dir: Optional[Path] = None,
) -> int:
    """오래된 by-pid 파일 삭제 (PID 재사용 보호).

    `.by-pid/*` 와 `.by-pid-current-run/*` 의 mtime 기준 ttl_sec 초과 파일 제거.
    Returns: 삭제된 파일 수.
    """
    base = _resolve_base(base_dir)
    now = datetime.now(timezone.utc).timestamp()
    removed = 0
    for sub in (".by-pid", ".by-pid-current-run"):
        d = base / sub
        if not d.exists():
            continue
        for f in d.iterdir():
            try:
                age = now - f.stat().st_mtime
                if age > ttl_sec:
                    f.unlink()
                    removed += 1
            except OSError:
                pass
    return removed


# ── PPID chain — Bash 에서 호출된 helper 의 cc_pid 추출 ───────────


def get_cc_pid_via_ppid_chain() -> Optional[int]:
    """python helper 가 자신의 grandparent (CC main) PID 추출.

    호출 chain: CC main → Bash subprocess → python helper.
    `os.getppid()` = Bash pid. `ps -o ppid= -p <bash_pid>` = CC main pid.

    Returns None if can't determine (e.g. ps 실패, 단독 실행).
    """
    try:
        bash_pid = os.getppid()
        result = subprocess.run(  # nosec B603, B607
            ["ps", "-o", "ppid=", "-p", str(bash_pid)],
            capture_output=True,
            text=True,
            check=True,
            timeout=_PPID_LOOKUP_TIMEOUT_SEC,
        )
        cc_pid = int(result.stdout.strip())
        if cc_pid > 0:
            return cc_pid
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
        ValueError,
    ):
        pass
    return None


def auto_detect_session_id(*, base_dir: Optional[Path] = None) -> str:
    """helper 컨텍스트 — env > by-pid (멀티세션 정합) > active_runs scan 폴백.

    issue #469 결함 B (DCN-CHG-20260522): PPID chain mismatch 시
    (bash subprocess 재시작 / fork 등) sid 미해결 회귀 차단. env var 우선 +
    active_runs scan 폴백 추가.
    """
    # (a) DCNESS_RUN_ID 동반 강제 — env var 통한 명시 매핑 우선
    env_sid = os.environ.get("DCNESS_SESSION_ID", "")
    if valid_session_id(env_sid):
        return env_sid
    # (b) PPID chain (기존 매커니즘)
    cc_pid = get_cc_pid_via_ppid_chain()
    if cc_pid is not None:
        sid = read_pid_session(cc_pid, base_dir=base_dir)
        if sid:
            return sid
    # (c) active_runs scan 폴백 — 가장 최근 미완료 run 의 session_id
    slot_info = _scan_recent_active_run_slot(base_dir=base_dir)
    if slot_info:
        return slot_info[0]  # (sid, rid)
    return ""


def auto_detect_run_id(*, base_dir: Optional[Path] = None) -> str:
    """helper 컨텍스트 — env > by-pid-current-run > active_runs scan 폴백.

    issue #469 결함 B (DCN-CHG-20260522): rid 폴백 영역 신설. env var
    `DCNESS_RUN_ID` 우선 + active_runs scan (`_scan_recent_active_run_slot`)
    폴백 추가.
    """
    # (a) env var 우선 — 사용자 명시 매핑
    env_rid = os.environ.get("DCNESS_RUN_ID", "")
    if env_rid:
        return env_rid
    # (b) PPID chain (기존 매커니즘)
    cc_pid = get_cc_pid_via_ppid_chain()
    if cc_pid is not None:
        rid = read_pid_current_run(cc_pid, base_dir=base_dir)
        if rid:
            return rid
        sid = read_pid_session(cc_pid, base_dir=base_dir)
        if sid:
            slot_info = _scan_recent_active_run_slot(base_dir=base_dir, session_id=sid)
            if slot_info:
                return slot_info[1]
    # (c) env sid 가 있으면 해당 세션 active_runs 를 먼저 scan
    sid = current_session_id(base_dir=base_dir)
    if sid:
        slot_info = _scan_recent_active_run_slot(base_dir=base_dir, session_id=sid)
        if slot_info:
            return slot_info[1]
    # (d) active_runs scan 폴백 — 가장 최근 미완료 run 의 run_id
    slot_info = _scan_recent_active_run_slot(base_dir=base_dir)
    if slot_info:
        return slot_info[1]
    return ""


def diagnose_sid_rid_resolution(
    *, base_dir: Optional[Path] = None, mode: str = "both"
) -> str:
    """sid/rid 미해결 시 각 해상도 layer 어디서 fail 했나 진단 + escape hatch 안내.

    issue #483 (DCN-CHG-20260523): 기존 `[session_state] sid/rid 미해결` 한 줄
    stderr 만으로는 (env / PPID / scan) 어느 영역에서 fail 했는지 추적 불가.
    helper 호출 시점 진단을 즉시 사용자에게 노출 + 우회 escape hatch 안내.

    Args:
        mode: "sid" / "rid" / "both" — 진단 출력 범위. CLI 호출 영역에 따라 분기.

    Returns:
        multi-line string (stderr 직접 출력 형태). 각 layer 의 상태 + 우회 명령 1줄씩.
    """
    env_sid = os.environ.get("DCNESS_SESSION_ID", "")
    env_rid = os.environ.get("DCNESS_RUN_ID", "")
    cc_pid = get_cc_pid_via_ppid_chain()
    sid_hint = env_sid if valid_session_id(env_sid) else ""

    lines: list[str] = []
    header = "sid/rid" if mode == "both" else mode
    lines.append(f"[session_state] {header} 미해결 — 진단:")

    # (a) env var layer
    if mode in ("sid", "both"):
        sid_status = "있음" if valid_session_id(env_sid) else "미설정"
        lines.append(f"  (a) env DCNESS_SESSION_ID: {sid_status}")
    if mode in ("rid", "both"):
        rid_status = "있음" if env_rid else "미설정"
        lines.append(f"  (a) env DCNESS_RUN_ID: {rid_status}")

    # (b) PPID chain layer
    if cc_pid is None:
        lines.append(
            "  (b) PPID chain: 미해결 — helper 가 메인 CC PID 추적 실패 "
            "(bash subprocess 재시작 / fork / EnterWorktree 후 PID context 변경 의심)"
        )
    else:
        lines.append(f"  (b) PPID chain cc_pid: {cc_pid}")
        sid_from_pid = read_pid_session(cc_pid, base_dir=base_dir)
        if sid_from_pid and not sid_hint:
            sid_hint = sid_from_pid
        if mode in ("sid", "both"):
            lines.append(
                f"  (b) by-pid/{cc_pid}: "
                f"{'sid 있음' if sid_from_pid else 'sid 없음 (SessionStart 훅 미실행 또는 stale by-pid 파일)'}"
            )
        if mode in ("rid", "both"):
            rid_from_pid = read_pid_current_run(cc_pid, base_dir=base_dir)
            lines.append(
                f"  (b) by-pid-current-run/{cc_pid}: "
                f"{'rid 있음' if rid_from_pid else 'rid 없음 (begin-run 호출 안 됨 또는 stale)'}"
            )

    # (c) active_runs scan layer (rid 영역만 의미 — sid 도 같이 매칭)
    slot = _scan_recent_active_run_slot(
        base_dir=base_dir,
        session_id=sid_hint or None,
    )
    if slot is None:
        lines.append("  (c) active_runs scan: 매치 없음 (모든 run completed 또는 sessions dir 비어있음)")
    else:
        lines.append(f"  (c) active_runs scan best-guess: sid={slot[0]} rid={slot[1]}")

    lines.append("")
    lines.append("우회 (escape hatch):")
    if mode in ("sid", "both"):
        lines.append("  export DCNESS_SESSION_ID=<sid>  # JSONL 디렉토리명 또는 begin-run stdout 참조")
    if mode in ("rid", "both"):
        lines.append("  export DCNESS_RUN_ID=<rid>      # begin-run stdout 의 run_id 값")
    lines.append("관련: dcness#483 / dcness#469 결함 B (helper sid/rid 회귀)")
    return "\n".join(lines)


def _is_open_active_run_slot(slot: Any) -> bool:
    """active_runs 슬롯이 helper fallback 후보인지 판정.

    `finalized_at` 은 finalize-run/review snapshot 완료 신호이고, run 종료 신호는
    `completed_at` 이다. 같은 run 의 fix round 재진입과 PPID mapping 단절 복구를
    위해 `completed_at` 전까지는 전역/sid-scoped scan 모두 후보로 유지한다 (#730).
    """
    if not isinstance(slot, dict):
        return False
    return slot.get("completed_at") is None


def _scan_live_file_for_active_run(
    live_file: Path,
    *,
    session_id: Optional[str] = None,
) -> Optional[tuple[str, str, str]]:
    """live.json 하나에서 최신 open active_run 후보 반환.

    Returns:
        (started_at, sid, rid) 또는 None.
    """
    try:
        data = json.loads(live_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    sid = data.get("session_id")
    meta = data.get("_meta")
    meta_sid = meta.get("sessionId") if isinstance(meta, dict) else None
    if session_id:
        if not valid_session_id(session_id):
            return None
        if isinstance(sid, str) and sid != session_id:
            return None
        if isinstance(meta_sid, str) and meta_sid != session_id:
            return None
        sid = session_id
    else:
        if isinstance(sid, str) and isinstance(meta_sid, str) and sid != meta_sid:
            return None
        sid = sid or meta_sid
    if not isinstance(sid, str) or not valid_session_id(sid):
        return None

    active_runs = data.get("active_runs", {})
    if not isinstance(active_runs, dict):
        return None
    best: Optional[tuple[str, str, str]] = None
    for rid, slot in active_runs.items():
        if not isinstance(rid, str) or not RUN_ID_RE.match(rid):
            continue
        if not _is_open_active_run_slot(slot):
            continue
        started = slot.get("started_at") or slot.get("last_confirmed_at") or ""
        if not isinstance(started, str):
            started = ""
        if best is None or started > best[0]:
            best = (started, sid, rid)
    return best


def _scan_recent_active_run_slot(
    *,
    base_dir: Optional[Path] = None,
    max_sessions: int = 5,
    session_id: Optional[str] = None,
) -> Optional[tuple[str, str]]:
    """.sessions/ 디렉토리 scan 후 가장 최근 미완료 active_run slot 의 (sid, rid).

    issue #469 결함 B 의 best-effort 폴백 — PPID chain 미해결 시 사용.
    다음 우선순위:
    1. `session_id` 가 주어지면 그 세션 live.json 을 직접 검사 (#684/#730)
    2. live.json mtime 최신 `max_sessions` 개만 검사 (비용 가드)
    3. 각 live.json 의 `active_runs` 중 `completed_at` 부재 + `started_at` 최신 slot 반환
    4. `finalized_at` 은 review snapshot 신호일 뿐 종료 신호가 아니므로 제외 조건이 아니다

    Returns:
        (session_id, run_id) tuple — best-guess.
        None — 매치 부재 (clean session 또는 모든 run completed).

    주의: multi-session 환경에서 잘못된 매핑 위험 있음. 본 폴백은 PPID chain
    실패 케이스의 무대응 (= helper 동작 X) 대신 best-guess 제공. 정확 매핑 필요시
    `DCNESS_SESSION_ID` / `DCNESS_RUN_ID` env var 명시 권장.
    """
    base = _resolve_base(base_dir)
    sessions_dir = base / ".sessions"
    if not sessions_dir.is_dir():
        return None

    if session_id:
        slot = _scan_live_file_for_active_run(
            sessions_dir / session_id / "live.json",
            session_id=session_id,
        )
        if slot is None:
            return None
        return (slot[1], slot[2])

    # live.json mtime 최신 max_sessions 개만 추출 (비용 가드)
    candidates: list[tuple[float, Path]] = []
    try:
        for entry in sessions_dir.iterdir():
            if not entry.is_dir():
                continue
            live_file = entry / "live.json"
            try:
                stat = live_file.stat()
            except OSError:
                continue
            candidates.append((stat.st_mtime, live_file))
    except OSError:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    candidates = candidates[:max_sessions]

    # 각 live.json 의 미완료 active_run 중 started_at 최신 후보 수집
    best_slot: Optional[tuple[str, str, str]] = None  # (started_at, sid, rid)
    for _, live_file in candidates:
        slot = _scan_live_file_for_active_run(live_file)
        if slot and (best_slot is None or slot[0] > best_slot[0]):
            best_slot = slot
    if best_slot is None:
        return None
    return (best_slot[1], best_slot[2])


_CONCLUSION_HEADER_RE = re.compile(
    r"^\s{0,3}#{1,6}\s*(결론|결과|요약|변경\s*요약|변경\s*사항|변경\s*내용|"
    r"conclusion|summary|result|key\s*changes?|outcome|verdict)(\s|$|:|—|-)",
    re.IGNORECASE,
)
_MUST_FIX_RE = re.compile(r"\bMUST[\s_-]?FIX\b", re.IGNORECASE)
_MUST_FIX_NEGATION_RE = re.compile(
    r"\bMUST[\s_-]?FIX\b[^\n]{0,30}?(?:\b0(?!\s*\d)|없[음다]|해당\s*없[음다])"
    r"|\bno\s+MUST[\s_-]?FIX\b",
    re.IGNORECASE,
)
_MUST_FIX_HEADER_ONLY_RE = re.compile(
    r"^\s*#{1,6}\s*MUST[\s_-]?FIX\s*$", re.IGNORECASE
)
_NEXT_LINE_NEGATION_RE = re.compile(
    r"^(?:없[음다]\.?|0건|0개|해당\s*없[음다]\.?|없습니다\.?)\s*$",
    re.IGNORECASE,
)


def _extract_prose_summary(prose: str, *, max_lines: int = 12) -> str:
    lines = prose.splitlines()
    start = next(
        (index + 1 for index, line in enumerate(lines) if _CONCLUSION_HEADER_RE.match(line)),
        None,
    )
    candidates = lines[start:] if start is not None else lines
    out: list[str] = []
    char_cap = max_lines * 100
    for raw in candidates:
        line = raw.rstrip()
        if start is not None and out and line.lstrip().startswith("#"):
            break
        if not line.strip():
            continue
        if start is None and not out and line.lstrip().startswith("#") and len(line) < 40:
            continue
        out.append(line)
        if len(out) >= max_lines or sum(len(item) + 1 for item in out) >= char_cap:
            break
    return "\n".join(out)


def _has_positive_must_fix(prose: str) -> bool:
    lines = prose.splitlines()
    for index, line in enumerate(lines):
        if not _MUST_FIX_RE.search(line) or _MUST_FIX_NEGATION_RE.search(line):
            continue
        if _MUST_FIX_HEADER_ONLY_RE.match(line):
            following = next((item.strip() for item in lines[index + 1 :] if item.strip()), "")
            if not following or _NEXT_LINE_NEGATION_RE.match(following):
                continue
        return True
    return False


def _main(argv: Optional[list] = None) -> int:
    from harness.session_state_cli import _main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    sys.exit(_main())

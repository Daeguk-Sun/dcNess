"""session_state.py — 세션/run 격리 상태 API (멀티세션 기본 가정).

발상 (`docs/archive/conveyor-design.md` §4 / §6 / §9):
    Claude Code 가 세션 단위 동작 → 한 사용자가 동시 다중 세션 띄울 수 있음.
    각 세션 안에서 컨베이어가 다중 run 가능 (예: 백그라운드 ralph + foreground impl).
    sid × run_id 별 격리된 디렉토리 구조 + `_meta` envelope 으로 leftover 방어.

본 모듈은 다음을 단일 책임으로 묶는다:
    1. session_id 검증 + resolution (3-tier: env → project pointer; 글로벌 폴백 제외)
    2. session pointer 파일 (`.session-id`) 읽기/쓰기
    3. run_id 생성 (`run-{token_hex(4)}`)
    4. atomic write (O_EXCL+fsync+rename+dir fsync, 0o600 — RWH 패턴)
    5. live.json 스키마 + active_runs map 조작 (OMC `SkillActiveStateV2` 차용)

OMC + RWH 차용 매핑:
    - regex `^[a-zA-Z0-9][a-zA-Z0-9_-]{0,255}$`           ← OMC SESSION_ID_ALLOWLIST
    - stdin 3 변형 fallback (sessionId/session_id/sessionid) ← OMC
    - 3-tier resolution (env > pointer)                    ← RWH (글로벌 폴백 제외)
    - `_meta` envelope + 자기참조 sessionId 검증            ← RWH
    - atomic write O_EXCL+fsync+rename+dir fsync           ← RWH
    - active_runs map + soft tombstone                     ← OMC SkillActiveStateV2

핵심 상수:
    SESSION_ID_RE       : path traversal 방어
    DEFAULT_RUN_TTL_SEC : run 슬롯 stale 기준 (24h)
    LIVE_JSON_VERSION   : 스키마 진화 추적
"""
from __future__ import annotations

import json
import os
import re
import secrets
import select
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

__all__ = [
    "SESSION_ID_RE",
    "DEFAULT_RUN_TTL_SEC",
    "DEFAULT_PID_TTL_SEC",
    "LIVE_JSON_VERSION",
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
    "read_session_pointer",
    "write_session_pointer",
    "generate_run_id",
    "atomic_write",
    "session_dir",
    "run_dir",
    "live_path",
    "read_live",
    "update_live",
    "start_run",
    "update_current_step",
    "set_pending_agent",
    "clear_pending_agent",
    "complete_run",
    "cleanup_stale_runs",
    "is_project_active",
    "enable_project",
    "disable_project",
    "list_active_projects",
    "whitelist_path",
]

# ── 상수 ─────────────────────────────────────────────────────────────
SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,255}$")
RUN_ID_RE = re.compile(r"^run-[a-z0-9]{8}$")

DEFAULT_RUN_TTL_SEC = 24 * 60 * 60        # 24h — completed slot 보관 후 cleanup
DEFAULT_PID_TTL_SEC = 24 * 60 * 60        # 24h — by-pid 파일 stale 기준 (PID 재사용 보호)
STALE_STEP_TTL_SEC = 30 * 60              # 30min — current_step heartbeat stale 기준 (DCN-30-30)
LIVE_JSON_VERSION = 1                      # 스키마 진화 추적
STDIN_TIMEOUT_SEC = 2.0                    # 훅 stdin 읽기 hang 방지
_ATOMIC_FILE_MODE = 0o600
_PPID_LOOKUP_TIMEOUT_SEC = 2.0


# ── 경로 유틸 ───────────────────────────────────────────────────────


_DEFAULT_BASE_CACHE: Dict[str, Path] = {}


def _resolve_state_root_for_cwd(cwd_str: str) -> Path:
    """git rev-parse --git-common-dir 으로 main repo 의 state root 해석.

    worktree 진입 (cwd = `.claude/worktrees/{name}/`) 후에도 `git rev-parse
    --git-common-dir` 은 main repo `.git` 를 가리킨다 (git 표준). 그래서 main repo
    의 `.claude/harness-state/` 가 단일 source 가 됨 → SessionStart 훅이 main
    repo 에서 박은 by-pid / live.json 을 worktree 안 helper 도 그대로 본다.

    git 미설치 / git 리포 아님 / subprocess 실패 → cwd 폴백 (legacy 동작).
    cwd 별 캐시 (subprocess 반복 호출 회피).
    """
    if cwd_str in _DEFAULT_BASE_CACHE:
        return _DEFAULT_BASE_CACHE[cwd_str]
    cwd = Path(cwd_str)
    try:
        result = subprocess.run(
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
    """테스트 보조 — _DEFAULT_BASE_CACHE 무력화."""
    _DEFAULT_BASE_CACHE.clear()


def _default_base() -> Path:
    return _resolve_state_root_for_cwd(str(Path.cwd().resolve()))


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


def _pointer_path(base_dir: Optional[Path] = None) -> Path:
    return _resolve_base(base_dir) / ".session-id"


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
    """현재 세션 ID resolution — 2-tier (RWH 3-tier 의 글로벌 폴백 제외).

    1. `DCNESS_SESSION_ID` env (subprocess 전파, 가장 권위)
    2. `.claude/harness-state/.session-id` pointer (SessionStart 훅이 작성)

    실패 시 빈 문자열. 호출자가 빈 문자열 처리 책임.
    """
    sid = os.environ.get("DCNESS_SESSION_ID", "")
    if valid_session_id(sid):
        return sid
    return read_session_pointer(base_dir=base_dir)


def read_session_pointer(*, base_dir: Optional[Path] = None) -> str:
    """`.session-id` pointer 파일 읽기. 검증 실패 시 빈 문자열."""
    path = _pointer_path(base_dir)
    try:
        if not path.exists():
            return ""
        sid = path.read_text(encoding="utf-8").strip()
        return sid if valid_session_id(sid) else ""
    except OSError:
        return ""


def write_session_pointer(
    session_id: str, *, base_dir: Optional[Path] = None
) -> Path:
    """`.session-id` pointer atomic 작성."""
    if not valid_session_id(session_id):
        raise ValueError(f"invalid session_id: {session_id!r}")
    target = _pointer_path(base_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(target, session_id.encode("utf-8"))
    return target


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
    """live.json 읽기 + `_meta.sessionId` 자기참조 검증.

    소유자 불일치 (`_meta.sessionId` ≠ session_id) 면 빈 dict 반환 — leftover 방어.
    파일 미존재 / 파싱 실패 시 빈 dict.
    """
    if not valid_session_id(session_id):
        return {}
    path = live_path(session_id, base_dir=base_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    meta = data.get("_meta", {})
    if not isinstance(meta, dict):
        return {}
    meta_sid = meta.get("sessionId", "")
    if meta_sid and meta_sid != session_id:
        # 다른 세션이 같은 경로에 덮어쓰기 시도 → 거부
        return {}
    return data


def update_live(
    session_id: str,
    *,
    base_dir: Optional[Path] = None,
    **fields: Any,
) -> None:
    """live.json 의 top-level 필드 read-merge-atomic-write.

    `_meta` 와 `session_id` 자기참조는 항상 갱신.
    값이 None 이면 필드 삭제 (단 `active_runs` 같은 dict 는 그대로 유지 — `**fields` 가 None 일 때만 pop).
    """
    if not valid_session_id(session_id):
        raise ValueError(f"invalid session_id: {session_id!r}")

    current = read_live(session_id, base_dir=base_dir) or {}
    # `_meta` 는 항상 새로 작성. 옛 envelope 신뢰 안 함.
    current.pop("_meta", None)

    for k, v in fields.items():
        if v is None:
            current.pop(k, None)
        else:
            current[k] = v

    current["session_id"] = session_id
    current["_meta"] = _make_meta(session_id)
    if "active_runs" not in current:
        current["active_runs"] = {}

    payload = json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True)
    target = live_path(session_id, base_dir=base_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(target, payload.encode("utf-8"))


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


def start_run(
    session_id: str,
    run_id: str,
    entry_point: str,
    *,
    base_dir: Optional[Path] = None,
    issue_num: Optional[int] = None,
) -> None:
    """`active_runs[run_id]` 슬롯 추가 + run 디렉토리 생성.

    이미 존재하면 ValueError (중복 run_id 방어).
    """
    if not valid_session_id(session_id):
        raise ValueError(f"invalid session_id: {session_id!r}")
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"invalid run_id: {run_id!r}")
    if not isinstance(entry_point, str) or not entry_point:
        raise ValueError("entry_point must be non-empty str")

    live = read_live(session_id, base_dir=base_dir) or {}
    active = live.get("active_runs", {})
    if not isinstance(active, dict):
        active = {}
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
        "issue_num": issue_num,
    }
    update_live(session_id, base_dir=base_dir, active_runs=active)
    # run 디렉토리 생성
    run_dir(session_id, run_id, base_dir=base_dir, create=True)


def update_current_step(
    session_id: str,
    run_id: str,
    agent: str,
    mode: Optional[str],
    *,
    base_dir: Optional[Path] = None,
) -> None:
    """`active_runs[run_id].current_step` 갱신 + heartbeat (`last_confirmed_at`)."""
    live = read_live(session_id, base_dir=base_dir) or {}
    active = live.get("active_runs", {})
    if not isinstance(active, dict) or run_id not in active:
        raise ValueError(f"run_id not active: {run_id}")
    slot = dict(active[run_id])

    # DCN-CHG-20260430-30: stale current_step WARN — begin-step 호출 시 *기존*
    # current_step 의 last_confirmed_at 가 STALE_STEP_TTL_SEC 초과면 stderr WARN.
    # I4 사례 — engineer step 후 end-step 누락 → 다음 begin-step 시 .steps.jsonl
    # 의 직전 step 누락 신호. 자동 보정 X (안전).
    prev_step = slot.get("current_step")
    prev_confirmed = slot.get("last_confirmed_at")
    if prev_step and isinstance(prev_step, dict) and prev_confirmed:
        try:
            from datetime import datetime, timezone
            prev_dt = datetime.fromisoformat(prev_confirmed.replace("Z", "+00:00"))
            now_dt = datetime.now(timezone.utc)
            stale_sec = (now_dt - prev_dt).total_seconds()
            if stale_sec > STALE_STEP_TTL_SEC:
                prev_agent = prev_step.get("agent", "?")
                prev_mode = prev_step.get("mode")
                label = f"{prev_agent}{':' + prev_mode if prev_mode else ''}"
                print(
                    f"[session_state] STALE STEP WARN — previous current_step={label} "
                    f"stale {int(stale_sec)}s (> {STALE_STEP_TTL_SEC}s). "
                    f"end-step 누락 의심 — .steps.jsonl 에 직전 step 기록 안 됨.",
                    file=sys.stderr,
                )
        except Exception:
            # 시간 파싱 등 실패 silent — begin-step 동작 우선
            pass

    now = _now_iso()
    slot["current_step"] = {
        "agent": agent,
        "mode": mode,
        "started_at": now,
    }
    slot["last_confirmed_at"] = now
    active[run_id] = slot
    update_live(session_id, base_dir=base_dir, active_runs=active)


def set_pending_agent(
    session_id: str,
    run_id: str,
    *,
    tool_use_id: str,
    sub_type: str,
    mode: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> None:
    """`active_runs[run_id].pending_agent` 갱신 — PreToolUse Agent 시점.

    PostToolUse Agent 가 *시각 범위* 로 sub trace 를 식별 (#272 W3 진짜 fix).
    기존 `agent_id` 폴백은 sub 가 file-op 안 한 경우 직전 step 의 ID 가 들어와
    오기록 (#272 W3) — CC docs 상 PostToolUse Agent (메인 컨텍스트) 에 agent_id
    가 *없을 수 있음*. `tool_use_id` (PreToolUse↔PostToolUse 매칭 키) + 시작 시각
    으로 정확히 식별.

    Args:
        tool_use_id: CC PreToolUse Agent payload 의 tool_use_id (필수)
        sub_type: subagent_type (검증/디버그용)
        mode: 옵션 mode hint
    """
    if not tool_use_id:
        return  # tool_use_id 없으면 매칭 불가 — 폴백 의존 (시각 범위 X)
    live = read_live(session_id, base_dir=base_dir) or {}
    active = live.get("active_runs", {})
    if not isinstance(active, dict) or run_id not in active:
        return  # idempotent — run 미시작 케이스 (컨베이어 외부 Agent 호출)
    slot = dict(active[run_id])
    slot["pending_agent"] = {
        "tool_use_id": tool_use_id,
        "sub_type": sub_type or "",
        "mode": mode or None,
        "started_at": _now_iso(),
    }
    active = dict(active)
    active[run_id] = slot
    update_live(session_id, base_dir=base_dir, active_runs=active)


def clear_pending_agent(
    session_id: str,
    run_id: str,
    *,
    base_dir: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """`active_runs[run_id].pending_agent` 제거 + 직전 값 반환.

    PostToolUse Agent 가 호출. 반환값으로 sub_type / started_at / tool_use_id
    검증 → trace 시각 범위 집계 + tool_use_id 매칭.
    """
    live = read_live(session_id, base_dir=base_dir) or {}
    active = live.get("active_runs", {})
    if not isinstance(active, dict) or run_id not in active:
        return None
    slot = dict(active[run_id])
    pending = slot.pop("pending_agent", None)
    active = dict(active)
    active[run_id] = slot
    update_live(session_id, base_dir=base_dir, active_runs=active)
    return pending if isinstance(pending, dict) else None


def complete_run(
    session_id: str,
    run_id: str,
    *,
    base_dir: Optional[Path] = None,
) -> None:
    """`active_runs[run_id].completed_at` 채움 (soft tombstone — 즉시 삭제 X)."""
    live = read_live(session_id, base_dir=base_dir) or {}
    active = live.get("active_runs", {})
    if not isinstance(active, dict) or run_id not in active:
        return  # idempotent — 이미 없으면 noop
    slot = dict(active[run_id])
    now = _now_iso()
    slot["completed_at"] = now
    slot["last_confirmed_at"] = now
    slot["current_step"] = None
    active[run_id] = slot
    update_live(session_id, base_dir=base_dir, active_runs=active)


def cleanup_stale_runs(
    session_id: str,
    *,
    ttl_sec: int = DEFAULT_RUN_TTL_SEC,
    base_dir: Optional[Path] = None,
) -> int:
    """다음 슬롯 삭제:
        1. `completed_at` 채워진 + ttl_sec 초과한 슬롯
        2. `last_confirmed_at` 이 ttl_sec 초과한 슬롯 (heartbeat dead)

    Returns: 삭제된 슬롯 수.
    """
    live = read_live(session_id, base_dir=base_dir) or {}
    active = live.get("active_runs", {})
    if not isinstance(active, dict):
        return 0

    now = datetime.now(timezone.utc)
    removed = 0
    survivors: Dict[str, Any] = {}

    for rid, slot in active.items():
        if not isinstance(slot, dict):
            continue
        completed_at = slot.get("completed_at")
        last_confirmed = slot.get("last_confirmed_at")

        candidate_iso = completed_at or last_confirmed
        if not candidate_iso:
            survivors[rid] = slot
            continue
        try:
            ts = datetime.fromisoformat(str(candidate_iso))
        except ValueError:
            survivors[rid] = slot
            continue
        age_sec = (now - ts).total_seconds()
        if age_sec > ttl_sec:
            removed += 1
        else:
            survivors[rid] = slot

    if removed:
        update_live(session_id, base_dir=base_dir, active_runs=survivors)
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
        result = subprocess.run(
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
    """helper 컨텍스트 — env > by-pid (멀티세션 정합) > pointer > active_runs scan 폴백.

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
    # (c) pointer 폴백 (기존 — current_session_id 가 env+pointer 2-tier)
    sid = current_session_id(base_dir=base_dir)
    if sid:
        return sid
    # (d) active_runs scan 폴백 — 가장 최근 미finalized run 의 session_id
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
    # (c) active_runs scan 폴백 — 가장 최근 미finalized run 의 run_id
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
        if mode in ("sid", "both"):
            sid_from_pid = read_pid_session(cc_pid, base_dir=base_dir)
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
    slot = _scan_recent_active_run_slot(base_dir=base_dir)
    if slot is None:
        lines.append("  (c) active_runs scan: 매치 없음 (모든 run finalized 또는 sessions dir 비어있음)")
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


def _scan_recent_active_run_slot(
    *,
    base_dir: Optional[Path] = None,
    max_sessions: int = 5,
) -> Optional[tuple[str, str]]:
    """sessions/ 디렉토리 scan 후 가장 최근 미finalized active_run slot 의 (sid, rid).

    issue #469 결함 B 의 best-effort 폴백 — PPID chain 미해결 시 사용.
    다음 우선순위:
    1. live.json mtime 최신 `max_sessions` 개만 검사 (비용 가드)
    2. 각 live.json 의 `active_runs` 중 `finalized_at` 부재 + `started_at`
       가장 최근 slot 박힌 (sid, rid) 반환

    Returns:
        (session_id, run_id) tuple — best-guess.
        None — 매치 부재 (clean session 또는 모든 run finalized).

    주의: multi-session 환경에서 잘못된 매핑 위험 있음. 본 폴백은 PPID chain
    실패 케이스의 무대응 (= helper 동작 X) 대신 best-guess 제공. 정확 매핑 필요시
    `DCNESS_SESSION_ID` / `DCNESS_RUN_ID` env var 명시 권장.
    """
    base = _resolve_base(base_dir)
    sessions_dir = base / "sessions"
    if not sessions_dir.is_dir():
        return None

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

    # 각 live.json 의 미finalized active_run 중 started_at 최신 후보 수집
    best: Optional[tuple[str, str, str]] = None  # (started_at, sid, rid)
    for _, live_file in candidates:
        try:
            data = json.loads(live_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        sid = data.get("session_id")
        if not isinstance(sid, str) or not valid_session_id(sid):
            continue
        active_runs = data.get("active_runs", {})
        if not isinstance(active_runs, dict):
            continue
        for rid, slot in active_runs.items():
            if not isinstance(slot, dict):
                continue
            if slot.get("finalized_at"):
                continue
            started = slot.get("started_at", "")
            if not isinstance(started, str):
                continue
            if best is None or started > best[0]:
                best = (started, sid, rid)
    if best is None:
        return None
    return (best[1], best[2])


# ── 프로젝트 활성화 (whitelist) ─────────────────────────────────────


_DEFAULT_WHITELIST_PATH = (
    Path.home() / ".claude" / "plugins" / "data" / "dcness-dcness" / "projects.json"
)


def whitelist_path() -> Path:
    """Plugin-scoped whitelist 경로.

    기본: `~/.claude/plugins/data/dcness-dcness/projects.json` (CC 공식 plugin-state
    컨벤션 — plugin install 시 자동 생성, plugin 제거 시 자동 정리).
    `DCNESS_WHITELIST_PATH` env 로 override (테스트 / 도그푸딩).
    """
    override = os.environ.get("DCNESS_WHITELIST_PATH")
    if override:
        return Path(override)
    return _DEFAULT_WHITELIST_PATH


def _load_whitelist() -> list:
    """projects.json 의 `projects` 배열 → resolved real path 리스트."""
    path = whitelist_path()
    try:
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    raw = data.get("projects", [])
    if not isinstance(raw, list):
        return []
    out = []
    for p in raw:
        if not isinstance(p, str):
            continue
        try:
            out.append(str(Path(p).expanduser().resolve()))
        except (OSError, ValueError):
            continue
    return out


def _save_whitelist(paths: list) -> None:
    """projects.json atomic 작성. 중복 제거 + 정렬."""
    deduped = sorted(set(str(p) for p in paths))
    payload = json.dumps(
        {"version": 1, "projects": deduped},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    target = whitelist_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(target, payload.encode("utf-8"))


def _resolve_project_root(cwd: Optional[Path] = None) -> Path:
    """cwd 의 main repo root (γ resolution).

    `_resolve_state_root_for_cwd` 가 `<main_root>/.claude/harness-state` 반환 →
    parent.parent = main_root. git 미사용 환경 폴백 시 cwd 자체 반환.
    """
    cwd_str = str((cwd or Path.cwd()).resolve())
    base = _resolve_state_root_for_cwd(cwd_str)
    return base.parent.parent


def is_project_active(cwd: Optional[Path] = None) -> bool:
    """현재 cwd (또는 인자) 가 dcNess whitelist 에 등록됐는지 판정.

    - 기본 disabled — whitelist 없거나 cwd 가 목록 밖이면 False
    - whitelist 경로의 서브디렉토리 (worktree 포함) 도 True (γ resolution 으로 main repo 추출)
    - `DCNESS_FORCE_ENABLE=1` env 로 임시 활성 (디버깅)
    """
    if os.environ.get("DCNESS_FORCE_ENABLE") == "1":
        return True
    try:
        project_root = _resolve_project_root(cwd).resolve()
    except OSError:
        return False
    project_root_str = str(project_root)
    for entry in _load_whitelist():
        if project_root_str == entry or project_root_str.startswith(entry + os.sep):
            return True
    return False


def enable_project(cwd: Optional[Path] = None) -> Path:
    """cwd 의 main repo root 를 whitelist 에 추가. 이미 있으면 noop."""
    project_root = _resolve_project_root(cwd).resolve()
    project_root_str = str(project_root)
    paths = _load_whitelist()
    if project_root_str not in paths:
        paths.append(project_root_str)
        _save_whitelist(paths)
    return project_root


def disable_project(cwd: Optional[Path] = None) -> Path:
    """cwd 의 main repo root 를 whitelist 에서 제거. 없으면 noop."""
    project_root = _resolve_project_root(cwd).resolve()
    project_root_str = str(project_root)
    paths = _load_whitelist()
    if project_root_str in paths:
        paths = [p for p in paths if p != project_root_str]
        _save_whitelist(paths)
    return project_root


def list_active_projects() -> list:
    """현재 whitelist 의 projects 배열 (resolved path 들)."""
    return _load_whitelist()


# ── CLI (python3 -m harness.session_state <subcommand>) ─────────────


def _cli_init_session(args: Any) -> int:
    """SessionStart 훅이 호출. by-pid 작성 + live.json 초기화."""
    if not valid_session_id(args.sid):
        print(f"[session_state] invalid sid: {args.sid!r}", file=sys.stderr)
        return 1
    if not valid_cc_pid(args.cc_pid):
        print(f"[session_state] invalid cc_pid: {args.cc_pid!r}", file=sys.stderr)
        return 1
    write_pid_session(args.cc_pid, args.sid)
    if not read_live(args.sid):
        update_live(args.sid)  # 빈 active_runs 로 초기화
    return 0


def _cli_begin_run(args: Any) -> int:
    """sid auto-detect → rid 생성 → start_run + by-pid-current-run."""
    sid = auto_detect_session_id()
    if not sid:
        print(diagnose_sid_rid_resolution(mode="sid"), file=sys.stderr)
        return 1
    rid = generate_run_id()
    issue_num = args.issue_num if args.issue_num is not None else None
    start_run(sid, rid, args.entry_point, issue_num=issue_num)
    cc_pid = get_cc_pid_via_ppid_chain()
    if cc_pid is not None:
        write_pid_current_run(cc_pid, rid)
    print(rid)
    return 0


def _cli_end_run(args: Any) -> int:
    """sid+rid auto-detect → complete_run + clear by-pid-current-run."""
    sid = auto_detect_session_id()
    rid = auto_detect_run_id()
    if not sid or not rid:
        print(diagnose_sid_rid_resolution(mode="both"), file=sys.stderr)
        return 1

    # finalize-run 미호출 시 자동 실행 — 모델이 Step 7 건너뛴 경우 안전망.
    try:
        import argparse as _ap
        _live = read_live(sid)
        _active = _live.get("active_runs", {}) if _live else {}
        _slot = _active.get(rid, {}) if isinstance(_active, dict) else {}
        if not _slot.get("finalized_at"):
            print(
                "[session_state] finalize-run 미호출 감지 — auto-running finalize-run --auto-review",
                file=sys.stderr,
            )
            _fake = _ap.Namespace(
                expected_steps=None,
                auto_review=True,
            )
            _cli_finalize_run(_fake)
    except Exception as exc:
        print(f"[session_state] end-run finalize guard FAIL — {exc}", file=sys.stderr)

    complete_run(sid, rid)
    cc_pid = get_cc_pid_via_ppid_chain()
    if cc_pid is not None:
        clear_pid_current_run(cc_pid)
    return 0


def _cli_post_task_begin(args: Any) -> int:
    """issue #472 — `/impl-loop` 종료 후 메인 자율 작업 영역 진입 marker.

    /impl-loop task 영역 (begin-run → build-worker → pr-reviewer → end-run) *외*
    자율 작업 (이슈 등록 / cleanup / 분석) 의 turn 을 task ROI 측정과 분리하기
    위한 marker. 본 호출 후 JSONL parser / run_review 가 marker timestamp 이후
    turn 을 *post-task 영역* 으로 분리 측정 → task당 평균 turn 왜곡 (jajang #446
    2차 측정 task3 사례 99 vs 81 = 18 turn 차이) 해소.

    동작:
    1. sid auto-detect (없으면 silent 0 — /impl-loop 외 호출 가능)
    2. live.json 에 `post_task_markers` list append (timestamp + reason)
    3. stdout = 메인이 자율 진입 self-aware 메시지

    Usage:
        dcness-helper post-task-begin [--reason "이슈 등록 / cleanup / 분석"]

    Exit codes:
        0 — 정상 (marker 박힘) 또는 sid 미해결 (silent skip)
    """
    sid = auto_detect_session_id()
    if not sid:
        print(
            "[post-task-begin] sid 미해결 — marker skip "
            "(SessionStart 훅 미실행 또는 비활성 프로젝트)",
            file=sys.stderr,
        )
        return 0

    reason = (getattr(args, "reason", "") or "").strip()
    now = _now_iso()

    try:
        live = read_live(sid) or {}
    except Exception:
        live = {}
    markers = live.get("post_task_markers") if isinstance(live, dict) else None
    if not isinstance(markers, list):
        markers = []
    markers.append({"at": now, "reason": reason})
    # FIFO cap 20 (오래된 marker 자동 trim)
    if len(markers) > 20:
        markers = markers[-20:]

    try:
        update_live(sid, post_task_markers=markers)
    except Exception as exc:
        print(f"[post-task-begin] live.json update FAIL — {exc}", file=sys.stderr)
        return 0

    print("=== post-task area begin (issue #472) ===")
    print(f"timestamp: {now}")
    print(f"session_id: {sid}")
    print(f"marker count: {len(markers)}")
    if reason:
        print(f"reason: {reason}")
    print(
        "본 marker 후 turn 영역 = /impl-loop task 영역 외 (자율 이슈 등록 / "
        "cleanup / 분석 등). 측정 도구가 marker timestamp 이후 turn 분리."
    )
    print("=== /post-task area begin ===")
    return 0


def _cli_next_task(args: Any) -> int:
    """issue #471 — multi-task 사이 영역 (review echo + 다음 task 진입) 자동화.

    이전 run end-run + 새 run begin-run + previous review.md 본문 stdout 통합 →
    /impl-loop driver 의 task 경계 ~27 turn 영역을 1 helper 호출로 압축.

    동작:
    1. 현재 sid 해결 (없으면 exit 1)
    2. 이전 run (있으면) end-run 자동 호출 (finalize-run guard + complete_run + clear)
    3. 이전 run 의 review.md 본문 stdout (메인이 echo 만, 본문은 디스크 보존)
    4. 새 run begin-run + by-pid-current-run 갱신
    5. stdout = previous review + 새 run_id + 새 run_dir

    Usage:
        dcness-helper next-task [--entry-point impl]

    Exit codes:
        0 — 정상 (이전 run finalize + 새 run 발급)
        1 — sid 미해결
    """
    sid = auto_detect_session_id()
    if not sid:
        print(diagnose_sid_rid_resolution(mode="sid"), file=sys.stderr)
        return 1

    prev_rid = auto_detect_run_id()
    prev_review_path: Optional[Path] = None
    if prev_rid:
        try:
            prev_run_dir = run_dir(sid, prev_rid)
            prev_review_path = prev_run_dir / "review.md"
        except (ValueError, OSError):
            prev_review_path = None
        # end-run 자동 호출 (in-process, _cli_end_run 의 finalize guard 가 알아서 처리)
        try:
            import argparse as _ap
            _cli_end_run(_ap.Namespace())
        except Exception as exc:
            print(f"[next-task] end-run FAIL — {exc}", file=sys.stderr)

    entry_point = getattr(args, "entry_point", "impl") or "impl"
    new_rid = generate_run_id()
    try:
        start_run(sid, new_rid, entry_point, issue_num=None)
    except Exception as exc:
        print(f"[next-task] begin-run FAIL — {exc}", file=sys.stderr)
        return 1
    cc_pid = get_cc_pid_via_ppid_chain()
    if cc_pid is not None:
        write_pid_current_run(cc_pid, new_rid)
    try:
        new_run_dir_path = run_dir(sid, new_rid, create=True)
    except (ValueError, OSError):
        new_run_dir_path = Path("(unknown)")

    print("=== next-task transition ===")
    print(f"[previous] run_id: {prev_rid or '(없음)'}")
    if prev_review_path and prev_review_path.is_file():
        try:
            content = prev_review_path.read_text(encoding="utf-8", errors="ignore")
            print(f"\n[previous review.md ({prev_review_path.name})]")
            print(content)
        except OSError as exc:
            print(f"[next-task] previous review.md read FAIL — {exc}", file=sys.stderr)
    elif prev_rid:
        print(
            "[previous review.md 부재 — finalize-run --auto-review 가 review 생성 "
            "안 했거나 run-dir 누락]"
        )

    print(f"\n[new] run_id: {new_rid}")
    print(f"[new] run_dir: {new_run_dir_path}")
    print(f"[new] entry_point: {entry_point}")
    print("=== /next-task transition ===")
    return 0


def _cli_insight(args: Any) -> int:
    """issue #396 — 메인 자율 인사이트 1줄 append.

    Usage: dcness-helper insight <agent>[-<mode>] "<자연어 한 줄>"

    예시:
        dcness-helper insight engineer-IMPL "🚨 stub 파일로 TDD guard 우회 시도 — 절대 반복 X"
        dcness-helper insight code-validator "PR 후 prose 결론 enum 빠뜨림 — 다음엔 IMPL_DONE 명시"
    """
    from harness.loop_insights import append_insight

    raw = (args.agent_mode or "").strip()
    if not raw:
        print("[session_state] agent_mode 미지정", file=sys.stderr)
        return 1

    # "agent-mode" 또는 "agent" 분리
    if "-" in raw:
        # 정식 agent 이름에 - 있을 수 있음 (code-validator / module-architect 등).
        # 매트릭스 매칭: 정식 이름 prefix 시도.
        from harness.run_review import DCNESS_AGENT_NAMES, LEGACY_AGENT_ALIASES
        agent = None
        mode = None
        for known in sorted(DCNESS_AGENT_NAMES | set(LEGACY_AGENT_ALIASES.keys()), key=len, reverse=True):
            if raw == known:
                agent, mode = known, None
                break
            if raw.startswith(known + "-"):
                agent = known
                mode = raw[len(known) + 1:]
                break
        if not agent:
            # fallback: 첫 - 분리
            parts = raw.split("-", 1)
            agent, mode = parts[0], parts[1] if len(parts) > 1 else None
    else:
        agent, mode = raw, None

    path = append_insight(agent, mode, args.text, cwd=Path.cwd())
    print(f"[insight] appended → {path}", file=sys.stderr)
    return 0


def _prior_engineer_tool_use_count(sid: str) -> Optional[int]:
    """현재 sid 의 CC session JSONL 에서 직전 engineer sub-agent invocation 의
    `totalToolUseCount` 추출 (DCN-CHG-20260430-36).

    LLM 은 자기 tool use count self-monitor 불가 (CC API 미노출) — helper 가
    측정해 stderr hint 로 흘려 IMPL_PARTIAL 자율 판단 *조건* 보강. 자율 침해 X.

    return: 직전 engineer invocation count (int) / 측정 실패 None.
    """
    try:
        from harness.run_review import encode_repo_path_dcness
    except Exception:
        return None
    try:
        cwd = Path.cwd()
        encoded = encode_repo_path_dcness(str(cwd))
        jsonl = Path.home() / ".claude" / "projects" / encoded / f"{sid}.jsonl"
        if not jsonl.exists():
            return None
        latest_count: Optional[int] = None
        latest_ts = ""
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if '"totalToolUseCount"' not in line or '"agentType"' not in line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            tur = rec.get("toolUseResult") or {}
            agent_type = (tur.get("agentType") or "").lower()
            if "engineer" not in agent_type:
                continue
            cnt = tur.get("totalToolUseCount")
            if not isinstance(cnt, int):
                continue
            ts = rec.get("timestamp", "")
            if ts > latest_ts:
                latest_ts = ts
                latest_count = cnt
        return latest_count
    except Exception:
        return None


def _cli_begin_step(args: Any) -> int:
    """sid+rid auto-detect → update_current_step."""
    sid = auto_detect_session_id()
    rid = auto_detect_run_id()
    if not sid or not rid:
        print(diagnose_sid_rid_resolution(mode="both"), file=sys.stderr)
        return 1
    mode = args.mode if args.mode else None
    update_current_step(sid, rid, args.agent, mode)

    # DCN-CHG-20260430-36: agent="engineer" 시 직전 engineer invocation 의
    # tool_use_count stderr hint. LLM self-monitor 불가 영역 정보 보강.
    # 측정 실패 silent (노이즈 회피).
    if args.agent == "engineer":
        prior = _prior_engineer_tool_use_count(sid)
        if prior is not None and prior > 0:
            print(
                f"[hint] prior engineer tool_use_count={prior} — "
                f"단일 호출 capacity 압박 인지 시 IMPL_PARTIAL 분할 자율 판단 권고. "
                f"강제 X (정보만).",
                file=sys.stderr,
            )

    print("ok")

    # DCN-CHG-20260502-02: 해당 agent/mode 의 loop insights 있으면 stdout 주입.
    # 메인 Claude 가 Bash 결과로 읽고 Agent prompt 에 포함시킨다.
    try:
        from harness.loop_insights import read as _li_read
        _insights = _li_read(args.agent, mode or None)
        if _insights:
            label = f"{args.agent}/{mode}" if mode else args.agent
            print(f"\n[INSIGHTS: {label}]\n{_insights}")
    except Exception:
        pass  # insights 주입 실패는 silent — 본 step 차단 X

    return 0


def _cli_run_dir(args: Any) -> int:
    """현재 active run 의 run_dir 절대 경로 stdout (DCN-CHG-20260430-21).

    skill prompt 가 prose-file path 를 /tmp 대신 run-dir 안에 박을 때 사용.
    멀티세션 격리 + stale prose 회피.
    """
    sid = auto_detect_session_id()
    rid = auto_detect_run_id()
    if not sid or not rid:
        print(diagnose_sid_rid_resolution(mode="both"), file=sys.stderr)
        return 1
    rd = run_dir(sid, rid)
    print(str(rd))
    return 0


_SUMMARY_LINE_LIMIT = 12      # prose 요약 최대 줄 수 (DCN-CHG-30-11: 8 → 12)
_SUMMARY_CHAR_LIMIT = 1200    # 요약 총 길이 cap (DCN-CHG-30-11: 600 → 1200)

# 결론/요약 섹션 헤더 후보 — case-insensitive 매칭 (한국어 + 영어 혼용).
# `\b` 는 한국어에 잘못 동작 (word boundary 가 ASCII 만) — 사용 X. 대신 끝에
# 공백/끝 또는 한국어 조사 후속 허용 패턴.
_CONCLUSION_HEADER_RE = re.compile(
    r"^\s{0,3}#{1,6}\s*"
    r"(결론|결과|요약|변경\s*요약|변경\s*사항|변경\s*내용|"
    r"conclusion|summary|result|key\s*changes?|outcome|verdict)"
    r"(\s|$|:|—|-)",
    re.IGNORECASE,
)


def _extract_section_after_header(prose: str, max_lines: int, char_cap: int) -> str:
    """결론/요약 섹션 헤더를 찾아 그 다음 본문 추출.

    헤더 부재 시 빈 문자열 반환 (caller 가 fallback 사용).
    """
    lines = prose.splitlines()
    start = -1
    for i, line in enumerate(lines):
        if _CONCLUSION_HEADER_RE.match(line):
            start = i + 1
            break
    if start < 0:
        return ""
    out: list = []
    total = 0
    for line in lines[start:]:
        rstripped = line.rstrip()
        stripped = rstripped.lstrip()
        # 다음 동급 이상 헤더 만나면 종료
        if stripped.startswith("#"):
            if out:  # 본문이 시작된 후 만나는 다음 헤더 = 섹션 종료
                break
            continue
        if not stripped and not out:
            continue  # 헤더 직후 빈 줄 skip
        out.append(rstripped)
        total += len(rstripped) + 1
        if len(out) >= max_lines or total >= char_cap:
            break
    # 끝 trailing 빈 줄 제거
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)


def _extract_prose_summary(prose: str, *, max_lines: int = _SUMMARY_LINE_LIMIT) -> str:
    """prose 의 결론/요약 섹션 우선 추출, 없으면 첫 의미 있는 N 줄 fallback.

    의도: skill bash 에서 helper 호출 후 stderr 로 흘려 사용자 가시성 ↑. agent prose 가
    대개 마지막에 `## 결론` / `## Summary` / `## 변경 요약` 섹션 박음 — 그 섹션이 가장
    정보 밀도 높음. 첫 N 줄 무차별 추출보다 효과적.

    DCN-CHG-30-11 (이전 8 줄 / 600 char → 12 줄 / 1200 char) — 사용자 가시성 ↑ 위해 cap 확장.
    """
    char_cap = _SUMMARY_CHAR_LIMIT if max_lines == _SUMMARY_LINE_LIMIT else max_lines * 100
    # 1단계: 결론/요약 섹션 우선
    section = _extract_section_after_header(prose, max_lines, char_cap)
    if section:
        return section
    # 2단계: fallback — 첫 의미 있는 줄
    out_lines: list = []
    total_chars = 0
    for raw in prose.splitlines():
        line = raw.rstrip()
        stripped = line.lstrip()
        if not stripped:
            continue
        # skip 첫 markdown 헤더만 (정보 부족)
        if stripped.startswith("#") and len(stripped) < 40 and len(out_lines) == 0:
            continue
        out_lines.append(line)
        total_chars += len(line) + 1
        if len(out_lines) >= max_lines or total_chars >= char_cap:
            break
    return "\n".join(out_lines)


def _find_prose_fallback(sid: str, rid: str, agent: str, mode: Optional[str]) -> Optional[str]:
    """hook staging 실패 시 run_dir 에서 prose 파일 패턴 탐색 fallback."""
    try:
        rd = run_dir(sid, rid)
        stem = f"{agent}-{mode}" if mode else agent
        base_path = rd / f"{stem}.md"
        if base_path.exists():
            return str(base_path)
        candidates = sorted(rd.glob(f"{stem}-*.md"), key=lambda p: p.stat().st_mtime)
        if candidates:
            return str(candidates[-1])
    except Exception:
        pass
    return None


def _cli_end_step(args: Any) -> int:
    """sid+rid auto-detect → write_prose + interpret_with_fallback.

    부수 출력: stderr 로 `[agent:mode = ENUM]` 헤더 + prose 요약 ~5줄. 모든 skill 자동
    수혜 — skill prompt 안에 별도 요약 instruction 박을 필요 0.
    """
    # 지연 import — interpret_strategy 는 telemetry 등 무거움
    from harness.signal_io import write_prose
    from harness.interpret_strategy import interpret_with_fallback
    from harness.signal_io import MissingSignal

    sid = auto_detect_session_id()
    rid = auto_detect_run_id()
    if not sid or not rid:
        print(diagnose_sid_rid_resolution(mode="both"), file=sys.stderr)
        return 1

    mode = args.mode if args.mode else None

    # DCN-CHG-20260430-25: drift detector — current_step 와 args.agent 불일치 시 WARN.
    # 메인 Claude 가 begin-step 안 부르고 end-step 호출하거나, 다른 agent 에 대한
    # begin-step 이후 다른 agent end-step 부르는 경우 잡음. 자동 보정 X (안전).
    try:
        live = read_live(sid)
        slot = live.get("active_runs", {}).get(rid, {}) if live else {}
        cur_step = slot.get("current_step") if slot else None
        if cur_step:
            cur_agent = cur_step.get("agent")
            cur_mode = cur_step.get("mode")
            if cur_agent and cur_agent != args.agent:
                print(
                    f"[session_state] DRIFT WARN — current_step={cur_agent}"
                    f"{':' + cur_mode if cur_mode else ''} but end-step={args.agent}"
                    f"{':' + mode if mode else ''}. begin-step 누락 의심.",
                    file=sys.stderr,
                )
            elif cur_mode and mode and cur_mode != mode:
                print(
                    f"[session_state] DRIFT WARN — current_step mode={cur_mode} "
                    f"but end-step mode={mode}. begin-step 누락 의심.",
                    file=sys.stderr,
                )
        else:
            # current_step 자체 부재 — begin-step 안 부른 경우 (engineer auto-PR 후 등).
            print(
                f"[session_state] DRIFT WARN — current_step 부재. "
                f"end-step={args.agent}{':' + mode if mode else ''}. "
                f"begin-step 안 호출하고 end-step 호출. .steps.jsonl 에 기록은 됨.",
                file=sys.stderr,
            )
    except Exception:
        # drift detector 자체 실패는 silent — end-step 동작 우선
        pass

    # DCN-CHG-20260501-15: prose 로딩 — --prose-file 제공 시 legacy 경로, 없으면 hook auto-stage.
    if args.prose_file:
        prose = Path(args.prose_file).read_text(encoding="utf-8")
        if not prose.strip():
            print("[session_state] empty prose", file=sys.stderr)
            return 1
        base = session_dir(sid) / "runs"
        occ = _count_step_occurrences(sid, rid, args.agent, mode)
        prose_path = write_prose(args.agent, rid, prose, mode=mode, base_dir=base, occurrence=occ)
    else:
        # hook auto-staged prose — live.json.current_step.prose_file 에서 경로 읽기
        try:
            _live = read_live(sid)
            _slot = _live.get("active_runs", {}).get(rid, {}) if _live else {}
            _cur = _slot.get("current_step") if isinstance(_slot, dict) else None
            _staged = _cur.get("prose_file") if isinstance(_cur, dict) else None
        except Exception:
            _staged = None
        if not _staged:
            _staged = _find_prose_fallback(sid, rid, args.agent, mode)
            if _staged:
                print(
                    f"[session_state] hook staging fallback → {Path(_staged).name}",
                    file=sys.stderr,
                )
        if not _staged:
            print("[session_state] --prose-file 미제공 + hook staging 없음", file=sys.stderr)
            return 1
        prose_path = Path(_staged)
        if not prose_path.exists():
            print(f"[session_state] hook staged prose_file 없음: {prose_path}", file=sys.stderr)
            return 1
        prose = prose_path.read_text(encoding="utf-8")
        if not prose.strip():
            print("[session_state] empty prose (hook staged)", file=sys.stderr)
            return 1

    # 이슈 #284 — `--allowed-enums` optional. 미지정 / 빈 값 = prose-only mode
    # (휴리스틱 추출 호출 zero, telemetry 기록 zero — issue #284 acceptance).
    allowed_raw = (args.allowed_enums or "").strip()
    allowed = [s.strip() for s in allowed_raw.split(",") if s.strip()] if allowed_raw else []

    agent_label = args.agent if not mode else f"{args.agent}:{mode}"

    if not allowed:
        # Prose-only mode — 메인 Claude 가 prose 직접 읽고 routing 결정.
        # stdout 은 sentinel "PROSE_LOGGED" 로 통일 — 외부 skill 이 enum 기대 없는
        # 경우용. 메인은 이 출력 무시하고 prose 자체를 routing 입력으로.
        print("PROSE_LOGGED")
        print(f"[{agent_label} = PROSE_LOGGED]", file=sys.stderr)
        summary = _extract_prose_summary(prose)
        if summary:
            print(summary, file=sys.stderr)
        _append_step_status(
            sid, rid, args.agent, mode, "PROSE_LOGGED", prose, prose_path,
        )
        return 0

    # legacy compat — 외부 skill 이 `--allowed-enums` 박은 경우 휴리스틱 호출 보존.
    # interpret_strategy 의 신규 telemetry 기록은 이미 중단됨 (issue #284).
    try:
        enum = interpret_with_fallback(prose, allowed)
    except MissingSignal as e:
        # AMBIGUOUS — stdout 으로 enum, stderr 로 detail + 요약 (사용자 가시)
        print("AMBIGUOUS", file=sys.stdout)
        print(f"[{agent_label} = AMBIGUOUS]", file=sys.stderr)
        print(f"  interpret fail: {e.detail[:200]}", file=sys.stderr)
        summary = _extract_prose_summary(prose)
        if summary:
            print(summary, file=sys.stderr)
        return 0  # ambiguous 자체는 정상 결과 — 메인이 이 신호 보고 pause 결정

    # 정상 enum — stdout (skill 이 캡처) + stderr 요약 (사용자 가시)
    print(enum)
    print(f"[{agent_label} = {enum}]", file=sys.stderr)
    summary = _extract_prose_summary(prose)
    if summary:
        print(summary, file=sys.stderr)
    # step status append — finalize-run / 회고용
    _append_step_status(sid, rid, args.agent, mode, enum, prose, prose_path)
    return 0


# ── step status log + finalize-run + auto-resolve ────────────────────


_MUST_FIX_RE = re.compile(r"\bMUST[\s_-]?FIX\b", re.IGNORECASE)

# 같은 줄 부정 패턴 — "MUST FIX 0" / "MUST FIX 없음" / "no must fix"
# DCN-CHG-20260523 (#484 Case 2): between 영역 `[\s:=]*` → `[^\n]{0,30}?` 로 일반화.
# jajang `**MUST FIX 항목**: 없음` 패턴 (한국어 라벨 + markdown bold + 콜론 끼임)
# 회귀 차단. 30자 한도 = `MUST FIX` 직후 같은 라인 안 짧은 라벨 + 부정 어휘만 흡수.
_MUST_FIX_NEGATION_RE = re.compile(
    r"\bMUST[\s_-]?FIX\b[^\n]{0,30}?"
    r"(?:\b0(?!\s*\d)|없[음다]|해당\s*없[음다])"
    r"|\bno\s+MUST[\s_-]?FIX\b",
    re.IGNORECASE,
)
# Markdown 헤더 단독 줄 — "## MUST FIX" 처럼 내용 없이 헤더만
_MUST_FIX_HEADER_ONLY_RE = re.compile(r'^\s*#{1,6}\s*MUST[\s_-]?FIX\s*$', re.IGNORECASE)
# 헤더 다음 줄 부정 패턴 — "없음." / "0건" / "해당 없음" 등
_NEXT_LINE_NEGATION_RE = re.compile(
    r'^(?:없[음다]\.?|0건|0개|해당\s*없[음다]\.?|없습니다\.?)\s*$',
    re.IGNORECASE,
)


def _has_positive_must_fix(prose: str) -> bool:
    """prose 안 MUST FIX 가 *positive* (실제 fix 요청) 의미로 등장했는지.

    검사 절차:
      1. MUST FIX 매칭 0개 → False
      2. 라인 단위 — 같은 줄 부정 컨텍스트 → skip
      3. Markdown 헤더 단독 줄 (## MUST FIX) → 다음 비어있지 않은 줄이 부정이면 skip
      4. 위 조건 모두 통과 → True (실제 fix 항목 존재)
    """
    if not _MUST_FIX_RE.search(prose):
        return False
    lines = prose.splitlines()
    for i, line in enumerate(lines):
        if not _MUST_FIX_RE.search(line):
            continue
        if _MUST_FIX_NEGATION_RE.search(line):
            continue  # 같은 줄 부정
        if _MUST_FIX_HEADER_ONLY_RE.match(line):
            # 헤더 단독 줄 — 다음 의미있는 줄 확인
            next_content = next(
                (l.strip() for l in lines[i + 1:] if l.strip()), ""
            )
            if not next_content or _NEXT_LINE_NEGATION_RE.match(next_content):
                continue  # 다음 줄이 없거나 부정 → false positive
        return True
    return False


def _steps_jsonl_path(sid: str, rid: str, *, base_dir: Optional[Path] = None) -> Path:
    return run_dir(sid, rid, base_dir=base_dir) / ".steps.jsonl"


def _count_step_occurrences(
    sid: str,
    rid: str,
    agent: str,
    mode: Optional[str],
    *,
    base_dir: Optional[Path] = None,
) -> int:
    """`.steps.jsonl` 에 기록된 (agent, mode) 쌍의 수 반환 (write_prose occurrence 계산용)."""
    target = _steps_jsonl_path(sid, rid, base_dir=base_dir)
    if not target.exists():
        return 0
    count = 0
    for line in target.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            if r.get("agent") == agent and r.get("mode") == mode:
                count += 1
        except json.JSONDecodeError:
            pass
    return count


def _append_step_status(
    sid: str,
    rid: str,
    agent: str,
    mode: Optional[str],
    enum: str,
    prose: str,
    prose_path: "Path",
) -> None:
    """end-step 호출마다 jsonl 에 한 줄 append. atomic 보장 X (append-only)."""
    record = {
        "ts": _now_iso(),
        "agent": agent,
        "mode": mode,
        "enum": enum,
        "prose_excerpt": _extract_prose_summary(prose, max_lines=12),
        "must_fix": _has_positive_must_fix(prose),
        "prose_file": str(prose_path),
    }
    target = _steps_jsonl_path(sid, rid)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with open(target, "a", encoding="utf-8") as f:
        f.write(line)


def _latest_step_per_role(steps: list) -> list:
    """`steps` 의 같은 (agent, mode) 쌍 중 *마지막* entry 만 골라 반환 (#272 W4).

    POLISH/retry 사이클 완료 후 PASS 으로 해소된 must_fix 가 has_must_fix 에 sticky
    되는 문제 해결용. 최신 step 만 봄으로써 step #N 이 FAIL → step #M
    이 PASS 이면 latest = PASS (must_fix=False) 로 평가.

    입력 순서 (시간 순) 유지 — 같은 키 마지막 발생.
    """
    out: dict = {}
    for s in steps:
        if not isinstance(s, dict):
            continue
        key = (s.get("agent"), s.get("mode"))
        out[key] = s
    return list(out.values())


def _read_steps_jsonl(sid: str, rid: str) -> list:
    """`.steps.jsonl` 전체 읽기. 파일 없으면 빈 리스트."""
    target = _steps_jsonl_path(sid, rid)
    if not target.exists():
        return []
    out = []
    try:
        for line in target.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return out


def _cli_finalize_run(args: Any) -> int:
    """현재 run 의 step status JSON 출력 (skill 이 clean 판정용으로 소비).

    출력 (stdout, JSON 한 줄):
        {
          "run_id": "...",
          "session_id": "...",
          "steps": [{agent, mode, enum, must_fix, prose_excerpt}, ...],
          "has_ambiguous": bool,
          "has_must_fix": bool,
          "step_count": N
        }

    skill 이 expected enum 매트릭스와 비교해 clean/caveat 결정.
    """
    sid = auto_detect_session_id()
    rid = auto_detect_run_id()
    if not sid or not rid:
        print(json.dumps({"error": "sid/rid 미해결"}), file=sys.stderr)
        return 1
    steps = _read_steps_jsonl(sid, rid)
    # #272 W4 — has_must_fix sticky on PASS 수정. POLISH/retry 로 해소된 must_fix 가
    # sticky 로 남아 PASS final step 임에도 caveat 진입했음. 같은 (agent, mode) 의
    # *마지막* 발생만 평가해서 후속 step 에서 해소된 신호를 정합 처리.
    latest_steps = _latest_step_per_role(steps)
    has_ambiguous = any(s.get("enum") == "AMBIGUOUS" for s in latest_steps)
    has_must_fix = any(s.get("must_fix") for s in latest_steps)

    # DCN-CHG-20260430-25: --expected-steps 검증 — skill 이 정상 시퀀스 step 수
    # 명시 시 .steps.jsonl row count 미만이면 stderr WARN. /impl-loop 자기검증.
    expected = getattr(args, "expected_steps", None)
    if expected is not None and len(steps) < expected:
        print(
            f"[session_state] STEP COUNT WARN — .steps.jsonl row={len(steps)} < "
            f"expected={expected}. inner step 누락 의심 — Agent 호출 후 end-step "
            f"안 부른 케이스 (drift). /run-review 로 진단 권고.",
            file=sys.stderr,
        )

    payload = {
        "run_id": rid,
        "session_id": sid,
        "steps": steps,
        "has_ambiguous": has_ambiguous,
        "has_must_fix": has_must_fix,
        "step_count": len(steps),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    # finalized_at 플래그 — end-run 이 미호출 감지용.
    try:
        _live = read_live(sid)
        _active = _live.get("active_runs", {}) if _live else {}
        if isinstance(_active, dict) and rid in _active:
            _slot = dict(_active[rid])
            _slot["finalized_at"] = _now_iso()
            _active[rid] = _slot
            update_live(sid, active_runs=_active)
    except Exception:
        pass

    # DCN-CHG-20260430-29: --auto-review flag — in-process /run-review chained.
    # 메인 Claude 가 finalize-run 호출만 하면 review 자동 piggy-back. 의도적 skip 불가.
    # SessionEnd 훅 reject (cross-session run false positive 우려).
    if getattr(args, "auto_review", False):
        print()
        print("--- /run-review (auto) ---")
        try:
            import io
            from harness import run_review as _rv  # lazy import (test mock 용이)
            _buf = io.StringIO()
            _old_stdout = sys.stdout
            sys.stdout = _buf
            try:
                _rv.main(["--run-id", rid, "--repo", str(Path.cwd())])
            except SystemExit:
                pass
            finally:
                sys.stdout = _old_stdout
            review_text = _buf.getvalue()
            if review_text:
                print(review_text)
                try:
                    review_path = run_dir(sid, rid) / "review.md"
                    review_path.write_text(review_text, encoding="utf-8")
                    print(
                        f"[REVIEW_READY] {review_path} — 위 리뷰를 세션에 그대로 출력할 것 (loop-procedure.md §6)",
                        file=sys.stderr,
                    )
                except Exception:
                    pass
        except Exception as exc:
            print(
                f"[session_state] AUTO_REVIEW_FAIL — {type(exc).__name__}: {exc}. "
                f"수동 `dcness-review --run-id {rid}` 1회 재시도 권장.",
                file=sys.stderr,
            )

    # issue #392 — auto accumulate 매커니즘 폐기. 자동 redo/wastes/goods 누적이
    # jajang 실측 100% baseline 노이즈 (PROSE_ECHO_OK) 만 만들어냄. 메인 자율
    # 평가는 PR3 의 `insight` CLI 로 대체.

    return 0


# yolo 모드 폴백 매트릭스 — agent + ESCALATE/CLARITY 시 권장 행동
_YOLO_FALLBACKS: Dict[str, Dict[str, str]] = {
    "ux-architect:UX_FLOW_ESCALATE": {
        "action": "re-invoke",
        "hint": (
            "NoUI 프로젝트 케이스 — minimal UX_FLOW_PATCHED prose 작성 (UI 없음 1줄 ack) "
            "후 advance"
        ),
        "next_enum": "UX_FLOW_PATCHED",
    },
    "product-planner:CLARITY_INSUFFICIENT": {
        "action": "re-invoke",
        "hint": "agent 권고 그대로 채택 — 모든 항목 default 채택 + 재호출",
        "next_enum": "PRODUCT_PLAN_READY",
    },
    "architect:SPEC_GAP_FOUND": {
        "action": "escalate-or-architect-spec-gap",
        "hint": "SPEC_GAP cycle 진입 (architect SPEC_GAP) 또는 사용자 위임",
        "next_enum": "SPEC_GAP_RESOLVED",
    },
    "code-validator:FAIL": {
        "action": "re-invoke-prev",
        "hint": "engineer 재호출 (FAIL 본문 보고) — attempt < 3",
        "next_enum": None,
    },
    "code-validator:ESCALATE": {
        "action": "escalate-or-architect-spec-gap",
        "hint": "본문 사유 prose 확인: spec 부재면 architect SPEC_GAP, 그 외면 사용자 위임",
        "next_enum": None,
    },
    "architecture-validator:FAIL": {
        "action": "re-invoke-prev",
        "hint": "architect SYSTEM_DESIGN 재진입 (cycle ≤ 2)",
        "next_enum": None,
    },
    "*:AMBIGUOUS": {
        "action": "user-delegate",
        "hint": "재호출 1회 시도. 그래도 모호 → 사용자 위임 (yolo 도 hard safety 보존)",
        "next_enum": None,
    },
}


def _cli_auto_resolve(args: Any) -> int:
    """yolo 모드 — enum + agent[:mode] 받아 권장 액션 JSON 반환.

    skill 이 yolo keyword 검출 시 호출. 권장 액션 = {action, hint, next_enum}.
    매핑 없으면 `unmapped` 반환 — skill 이 사용자 위임 fallback.

    catastrophic 룰 우회 X — yolo 는 skill-level 확인 prompt 자동화만.
    """
    key = args.agent_mode  # 예: "ux-architect:UX_FLOW_ESCALATE" 또는 "code-validator:FAIL"
    fallback = _YOLO_FALLBACKS.get(key)
    if fallback is None:
        # AMBIGUOUS 통합 케이스 — 어떤 agent 든 동일 권장
        if key.endswith(":AMBIGUOUS"):
            fallback = _YOLO_FALLBACKS["*:AMBIGUOUS"]
    if fallback is None:
        print(json.dumps({"action": "unmapped", "key": key}, ensure_ascii=False))
        return 1
    print(json.dumps({"key": key, **fallback}, ensure_ascii=False))
    return 0


def _cli_enable(args: Any) -> int:
    """현재 cwd 의 main repo 를 whitelist 에 추가."""
    root = enable_project()
    print(f"[dcness] enabled: {root}")
    print(f"[dcness] whitelist: {whitelist_path()}")
    return 0


def _cli_disable(args: Any) -> int:
    """현재 cwd 의 main repo 를 whitelist 에서 제거."""
    root = disable_project()
    print(f"[dcness] disabled: {root}")
    return 0


def _cli_is_active(args: Any) -> int:
    """현재 cwd 활성 여부 — 활성=exit 0, 비활성=exit 1 (silent, hook 게이트용)."""
    return 0 if is_project_active() else 1


def _cli_status(args: Any) -> int:
    """whitelist + 현재 cwd 활성 상태 출력."""
    active = is_project_active()
    cwd_root = _resolve_project_root().resolve()
    print(f"[dcness] cwd project root: {cwd_root}")
    print(f"[dcness] active: {'YES' if active else 'NO'}")
    print(f"[dcness] whitelist file: {whitelist_path()}")
    projects = list_active_projects()
    if projects:
        print(f"[dcness] {len(projects)} active project(s):")
        for p in projects:
            mark = "*" if p == str(cwd_root) else " "
            print(f"  {mark} {p}")
    else:
        print("[dcness] no active projects (whitelist empty)")
    return 0


def _build_arg_parser() -> Any:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python3 -m harness.session_state",
        description="dcNess 세션/run 격리 helper CLI",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init-session", help="SessionStart 훅 보조")
    p_init.add_argument("sid")
    p_init.add_argument("cc_pid", type=int)
    p_init.set_defaults(func=_cli_init_session)

    p_br = sub.add_parser("begin-run", help="run_id 발급 + start_run")
    p_br.add_argument("entry_point")
    p_br.add_argument("--issue-num", type=int, default=None)
    p_br.set_defaults(func=_cli_begin_run)

    p_er = sub.add_parser("end-run", help="complete_run + clear by-pid-current-run")
    p_er.set_defaults(func=_cli_end_run)

    p_nt = sub.add_parser(
        "next-task",
        help="이전 run end-run + 새 run begin-run + previous review.md stdout (issue #471)",
    )
    p_nt.add_argument(
        "--entry-point", default="impl",
        help="새 run 의 entry_point (default: impl)",
    )
    p_nt.set_defaults(func=_cli_next_task)

    p_ptb = sub.add_parser(
        "post-task-begin",
        help="/impl-loop 종료 후 메인 자율 작업 영역 진입 marker (issue #472)",
    )
    p_ptb.add_argument(
        "--reason", default="",
        help='자율 진입 사유 ("이슈 등록 / cleanup / 분석" 등)',
    )
    p_ptb.set_defaults(func=_cli_post_task_begin)

    # issue #396 — insight CLI (메인 자율 평가 매커니즘)
    p_in = sub.add_parser(
        "insight",
        help="agent+mode 별 인사이트 한 줄 append (FIFO 10 cap, 메인 자율 평가)",
    )
    p_in.add_argument("agent_mode", help='agent 또는 "agent-mode" (예: engineer, engineer-IMPL)')
    p_in.add_argument("text", help="자연어 한 줄 (예: \"🚨 stub 파일로 TDD guard 우회 시도 — 절대 반복 X\")")
    p_in.set_defaults(func=_cli_insight)

    p_bs = sub.add_parser("begin-step", help="current_step + heartbeat 갱신")
    p_bs.add_argument("agent")
    p_bs.add_argument("mode", nargs="?", default="")
    p_bs.set_defaults(func=_cli_begin_step)

    p_es = sub.add_parser(
        "end-step",
        help="prose 저장 (issue #284 — `--allowed-enums` 미지정 시 prose-only mode)",
    )
    p_es.add_argument("agent")
    p_es.add_argument("mode", nargs="?", default="")
    p_es.add_argument(
        "--allowed-enums", required=False, default="",
        help=(
            "comma-separated. legacy compat — 미지정 시 prose-only mode "
            "(stdout=PROSE_LOGGED). 이슈 #284."
        ),
    )
    p_es.add_argument(
        "--prose-file", required=False, default=None,
        help="prose 본문 파일 경로 (미제공 시 hook auto-stage 경로 사용)",
    )
    p_es.set_defaults(func=_cli_end_step)

    p_rd = sub.add_parser("run-dir", help="현재 active run 의 run_dir 절대 경로 (DCN-30-21)")
    p_rd.set_defaults(func=_cli_run_dir)

    p_en = sub.add_parser("enable", help="현재 cwd 의 main repo 활성화 (whitelist 추가)")
    p_en.set_defaults(func=_cli_enable)

    p_di = sub.add_parser("disable", help="현재 cwd 비활성화 (whitelist 제거)")
    p_di.set_defaults(func=_cli_disable)

    p_ia = sub.add_parser("is-active", help="활성 여부 (silent, exit 0/1) — hook 게이트용")
    p_ia.set_defaults(func=_cli_is_active)

    p_st = sub.add_parser("status", help="whitelist + 현재 cwd 상태")
    p_st.set_defaults(func=_cli_status)

    p_fr = sub.add_parser(
        "finalize-run",
        help="현재 run 의 step status JSON 출력 (clean 판정용)",
    )
    p_fr.add_argument(
        "--expected-steps",
        type=int,
        default=None,
        help="정상 시퀀스 step 수 (예: /impl 5). 미만이면 stderr WARN (DCN-30-25)",
    )
    p_fr.add_argument(
        "--auto-review",
        action="store_true",
        help="finalize 직후 in-process 로 /run-review 호출 — STATUS JSON 뒤에 chained (DCN-30-29)",
    )
    # issue #392 — --accumulate / --no-accumulate flag 폐기 (auto accumulate 폐기와 정합).
    p_fr.set_defaults(func=_cli_finalize_run)

    p_ar = sub.add_parser(
        "auto-resolve",
        help="yolo 모드 권장 액션 JSON 반환 (agent:mode_or_enum 매핑)",
    )
    p_ar.add_argument(
        "agent_mode",
        help='"ux-architect:UX_FLOW_ESCALATE", "code-validator:FAIL", "*:AMBIGUOUS" 등',
    )
    p_ar.set_defaults(func=_cli_auto_resolve)

    return parser


def _main(argv: Optional[list] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(_main())

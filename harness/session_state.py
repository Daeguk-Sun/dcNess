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
import shutil
# Fixed git/gh/ps argv probes in this module run without shell and with timeouts.
import subprocess  # nosec B404
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

__all__ = [
    "SESSION_ID_RE",
    "DEFAULT_RUN_TTL_SEC",
    "DEFAULT_PID_TTL_SEC",
    "DEFAULT_RUN_DIR_TTL_SEC",
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
    "clear_current_step",
    "set_pending_agent",
    "clear_pending_agent",
    "complete_run",
    "cleanup_stale_runs",
    "cleanup_stale_run_dirs",
    "is_project_active",
    "enable_project",
    "disable_project",
    "list_active_projects",
    "whitelist_path",
    "fail_open_events_path",
    "record_fail_open_event",
    "read_fail_open_events",
    "collect_fail_open_summary",
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
_PROMPT_SLOT_CHECK_ENTRY_POINTS = {"impl", "design"}
_PROMPT_SLOT_TEMPLATE_REL = Path("docs/plugin/templates/agent-prompt-slots.md")


# ── 경로 유틸 ───────────────────────────────────────────────────────


_DEFAULT_BASE_CACHE: Dict[str, Path] = {}


def _resolve_state_root_for_cwd(cwd_str: str) -> Path:
    """git rev-parse --git-common-dir 으로 main repo 의 state root 해석.

    worktree 진입 (cwd = `.claude/worktrees/{name}/`) 후에도 `git rev-parse
    --git-common-dir` 은 main repo `.git` 를 가리킨다 (git 표준). 그래서 main repo
    의 `.claude/harness-state/` 가 단일 source 가 됨 → SessionStart 훅이 main
    repo 에서 쓴 by-pid / live.json 을 worktree 안 helper 도 그대로 본다.

    git 미설치 / git 리포 아님 / subprocess 실패 → cwd 폴백 (legacy 동작).
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
    2. `.claude/harness-state/.session-id` pointer (legacy 폴백 — 현재
       SessionStart 훅은 `.by-pid/<cc_pid>` 만 작성하고 본 pointer 는 쓰지
       않는다. `write_session_pointer` 프로덕션 호출자 부재 → 사실상 미사용
       폴백, 멀티세션 정합은 `auto_detect_session_id` 의 by-pid 단계가 담당)

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


# design_doc 으로 인정하는 설계 산출물 표준 경로 prefix (impl 문서 / compact
# plan). 기록 시점에 repo-root 상대 prefix 앵커로 검증해 임의
# .md(README 등)·traversal(`..`)·repo 밖 경로가 engineer 게이트 사전 조건
# 증거가 되지 못하게 한다 (#701).
_DESIGN_DOC_DIR_MARKERS = (
    "docs/epics/",
    "docs/compact-plans/",
)


def _validate_design_doc(design_doc: str) -> str:
    """begin-run `--design-doc` 경로 fail-fast 검증 (#701) — resolve 절대경로 반환.

    engineer 게이트의 사전 조건 증거로 쓰이므로 기록 시점에 (1) .md 파일,
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


# /impl 2축 모델의 lane(설계도 유무) 닫힌 enum (#714). lite = 설계도 없음,
# standard = 설계도 있음. engineer 게이트가 lane=lite 를 설계 산출물
# 사전 조건 면제 신호로 인정하므로, 임의 문자열이 면제를 유발하지 못하게
# 기록 시점에 이 집합으로 fail-fast 검증한다.
_VALID_LANES = ("lite", "standard")


def start_run(
    session_id: str,
    run_id: str,
    entry_point: str,
    *,
    base_dir: Optional[Path] = None,
    issue_num: Optional[int] = None,
    design_doc: Optional[str] = None,
    lane: Optional[str] = None,
    acceptance_required: bool = False,
) -> None:
    """`active_runs[run_id]` 슬롯 추가 + run 디렉토리 생성.

    이미 존재하면 ValueError (중복 run_id 방어).

    design_doc — 이 run 이 참조하는 머지된 설계 문서 경로 (#701). 기록 시
    engineer 게이트가 같은-run module-architect PASS 의 등가 사전 조건
    증거로 인정한다 (impl-loop 풀 4-agent 처럼 설계가 별도 run 에서 머지된
    뒤 진입하는 경우).

    lane — /impl 2축 모델의 lane(설계도 유무: "lite" / "standard", #714).
    lane="lite" 는 설계도 없는 Lite 구현 경로로, engineer 게이트가 설계 산출물
    사전 조건을 면제하는 신호다. 면제 누수 방지를 위해 (1) 닫힌 enum 만
    수용하고 (2) design_doc 과 동일하게 entry_point=impl run 에서만 기록을
    허용한다 — design/architect-loop run 의 module-architect PASS 강제는 코드
    보장으로 유지된다.

    acceptance_required — story/epic 마감 task 로, pr-reviewer PASS 뒤 inline
    product-acceptance 를 거쳐야 정상 종료되는 run 이라는 신호 (#722).
    Stop hook 이 이 marker 를 읽어 pr-reviewer 를 종료 agent 로 취급하지 않는다.
    """
    if not valid_session_id(session_id):
        raise ValueError(f"invalid session_id: {session_id!r}")
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"invalid run_id: {run_id!r}")
    if not isinstance(entry_point, str) or not entry_point:
        raise ValueError("entry_point must be non-empty str")
    if lane is not None:
        if entry_point != "impl":
            raise ValueError(
                f"lane is only valid for entry_point=impl (got {entry_point!r})"
            )
        if lane not in _VALID_LANES:
            raise ValueError(
                f"lane must be one of {_VALID_LANES} (got {lane!r})"
            )
    if acceptance_required and entry_point != "impl":
        raise ValueError(
            "acceptance_required is only valid for entry_point=impl "
            f"(got {entry_point!r})"
        )
    if design_doc is not None:
        # design_doc 은 impl 구현 run 전용 — design/architect-loop run 의
        # engineer ← module-architect PASS 강제가 코드 보장으로 유지되도록
        # 다른 entry_point 의 기록 자체를 거부한다.
        if entry_point != "impl":
            raise ValueError(
                f"design_doc is only valid for entry_point=impl (got {entry_point!r})"
            )
        design_doc = _validate_design_doc(design_doc)

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
        "design_doc": design_doc,
        "lane": lane,
        "acceptance_required": bool(acceptance_required),
    }
    update_live(session_id, base_dir=base_dir, active_runs=active)
    # run 디렉토리 생성
    run_dir(session_id, run_id, base_dir=base_dir, create=True)


def _ledger_run_started(
    session_id: str,
    run_id: str,
    entry_point: str,
    *,
    issue_num: Optional[int] = None,
    design_doc: Optional[str] = None,
    lane: Optional[str] = None,
    acceptance_required: bool = False,
    base_dir: Optional[Path] = None,
) -> None:
    """start_run 직후 ledger run_started checkpoint 기록 (이슈 #587).

    begin-run / next-task 등 *모든 run 시작 경로* 의 공유 path — 한 곳에서만
    run_started 를 쓰게 해 chain task run 의 run-level audit invariant 누락을
    막는다 (codex review). 기록 실패가 run 시작을 막지 않게 silent.
    """
    try:
        from harness import ledger

        extra: Dict[str, Any] = {"entry_point": entry_point}
        if issue_num is not None:
            extra["issue_num"] = issue_num
        if design_doc is not None:
            extra["design_doc"] = design_doc
        if lane is not None:
            extra["lane"] = lane
        if acceptance_required:
            extra["acceptance_required"] = True
        ledger.append_event(session_id, run_id, "run_started", base_dir=base_dir, **extra)
    except Exception:  # nosec B110
        pass


def update_current_step(
    session_id: str,
    run_id: str,
    agent: str,
    mode: Optional[str],
    *,
    base_dir: Optional[Path] = None,
) -> None:
    """`active_runs[run_id].current_step` 갱신 + heartbeat (`last_confirmed_at`)."""
    # #700 — current_step.agent 를 canonical 로 정규화 저장. namespaced(`dcness:engineer`)
    # / legacy alias 를 bare 로 통일해 strict-conveyor 게이트 비교 + prose 파일명(staging/
    # end-step)이 표기 무관하게 일관되도록. agent 이름 검증 정규식(콜론 거부)을 바꾸지 않고
    # 정규화로 해소 (이슈 out-of-scope: 정규식 정책 변경).
    from harness.agent_names import normalize_agent_type
    agent = normalize_agent_type(agent) or agent
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
                    f"end-step 누락 의심 — ledger.jsonl 에 직전 step 기록 안 됨.",
                    file=sys.stderr,
                )
        except Exception:  # nosec B110
            # 시간 파싱 등 실패 silent — begin-step 동작 우선
            pass

    now = _now_iso()
    try:
        steps_count_at_begin = len(
            _read_steps_jsonl(session_id, run_id, base_dir=base_dir)
        )
    except Exception:
        steps_count_at_begin = None
    slot["current_step"] = {
        "agent": agent,
        "mode": mode,
        "started_at": now,
    }
    if steps_count_at_begin is not None:
        slot["current_step"]["steps_count_at_begin"] = steps_count_at_begin
    slot["last_confirmed_at"] = now
    active[run_id] = slot
    update_live(session_id, base_dir=base_dir, active_runs=active)


def clear_current_step(
    session_id: str,
    run_id: str,
    *,
    agent: Optional[str] = None,
    mode: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> bool:
    """`active_runs[run_id].current_step` 제거.

    agent/mode 가 주어지면 현재 step 이 같은 step 일 때만 제거한다. end-step 성공
    후 stale current_step 이 남아 다음 Agent 호출을 잘못 통과시키는 회귀를 막기 위한
    좁은 정리 경로다.
    """
    live = read_live(session_id, base_dir=base_dir) or {}
    active = live.get("active_runs", {})
    if not isinstance(active, dict) or run_id not in active:
        return False
    slot = dict(active[run_id])
    cur_step = slot.get("current_step")
    if not isinstance(cur_step, dict):
        return False
    if agent is not None:
        cur_agent = cur_step.get("agent")
        cur_mode = cur_step.get("mode")
        if cur_agent != agent or cur_mode != mode:
            return False
    slot["current_step"] = None
    slot["last_confirmed_at"] = _now_iso()
    active = dict(active)
    active[run_id] = slot
    update_live(session_id, base_dir=base_dir, active_runs=active)
    return True


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
    try:
        result = subprocess.run(  # nosec B603, B607
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(probe_cwd),
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
    return str(root_path) if _is_dcness_worktree_path(root_path) else None


def _prompt_slot_check_text(
    session_id: str,
    run_id: str,
    *,
    base_dir: Optional[Path] = None,
    cwd: Optional[Path] = None,
) -> str:
    """Advisory self-check emitted immediately before Agent prompt writing."""
    try:
        live = read_live(session_id, base_dir=base_dir) or {}
        active = live.get("active_runs", {})
        slot = active.get(run_id, {}) if isinstance(active, dict) else {}
        entry_point = slot.get("entry_point") if isinstance(slot, dict) else None
    except Exception:  # nosec B110
        return ""
    if entry_point not in _PROMPT_SLOT_CHECK_ENTRY_POINTS:
        return ""

    template_path = Path(__file__).resolve().parents[1] / _PROMPT_SLOT_TEMPLATE_REL
    worktree_root = _active_worktree_root_for_prompt(cwd=cwd)
    if worktree_root:
        worktree_line = (
            f"- worktree: 활성 — Agent prompt 에 worktree 절대경로 `{worktree_root}` 포함. "
            "main repo 절대경로 금지."
        )
    else:
        worktree_line = (
            "- worktree: 비활성이 확실하면 생략. 활성 여부가 애매하면 "
            "`pwd` / `git rev-parse --show-toplevel` 확인 후 절대경로 포함."
        )
    return "\n".join(
        [
            "[PROMPT_SLOT_CHECK]",
            f"- template: `{template_path}`",
            "- 대상+읽을 진본: 이번 호출 단위와 agent 가 자체 read 할 SSOT 경로만 둔다.",
            worktree_line,
            "- 이 호출 특유: 진본에 없는 제약/신호만 둔다. 정규식·구현 단계·알고리즘·테스트 assert 방식 등 방법 처방 금지.",
        ]
    )


def set_pending_agent(
    session_id: str,
    run_id: str,
    *,
    tool_use_id: str,
    sub_type: str,
    mode: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> None:
    """`active_runs[run_id].pending_agents[tool_use_id]` 갱신 — PreToolUse Agent 시점.

    PostToolUse Agent 가 *시각 범위* 로 sub trace 를 식별 (#272 W3 진짜 fix).
    기존 `agent_id` 폴백은 sub 가 file-op 안 한 경우 직전 step 의 ID 가 들어와
    오기록 (#272 W3) — CC docs 상 PostToolUse Agent (메인 컨텍스트) 에 agent_id
    가 *없을 수 있음*. `tool_use_id` (PreToolUse↔PostToolUse 매칭 키) + 시작 시각
    으로 정확히 식별.

    issue #598 — **multi-slot**: `pending_agents` 를 `tool_use_id` 키 dict 로 유지.
    동시 Agent 호출 시 각 호출이 독립 슬롯을 차지 (단일 슬롯이면 둘째가 첫째를
    덮어써 prose-staging 시각 범위/trace 귀속이 섞임).

    ⚠️ **알려진 한계 (cross-process lost-write, follow-up)**: live.json 은 lock
    없는 atomic_write(원자적 rename) 설계라 read-modify-write 가 프로세스 간
    원자적이지 않다. 두 PreToolUse Agent hook 프로세스가 *동시에* 실행되면 각자
    자기 `tool_use_id` 만 추가 후 active_runs 전체를 덮어써, last-writer 가 상대
    슬롯을 잃을 수 있다 (전 mutator 공통 기존 속성 — 본 함수만의 결함 아님).
    영향 범위는 prose-staging 시각 범위/histogram 라는 *측정 신호* 한정 —
    file-guard 권한 경계는 payload self-attribution(`_resolve_acting_agent`)으로
    판정하므로 이 race 와 **무관**(보안 영향 0). 시스템 차원 live.json lock 은
    별도 follow-up.

    Args:
        tool_use_id: CC PreToolUse Agent payload 의 tool_use_id (필수, multi-slot 키)
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
    pending = slot.get("pending_agents")
    pending = dict(pending) if isinstance(pending, dict) else {}
    pending[tool_use_id] = {
        "tool_use_id": tool_use_id,
        "sub_type": sub_type or "",
        "mode": mode or None,
        "started_at": _now_iso(),
    }
    slot["pending_agents"] = pending
    active = dict(active)
    active[run_id] = slot
    update_live(session_id, base_dir=base_dir, active_runs=active)


def clear_pending_agent(
    session_id: str,
    run_id: str,
    *,
    tool_use_id: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """`active_runs[run_id].pending_agents[tool_use_id]` 제거 + 그 값 반환.

    PostToolUse Agent 가 호출. 반환값으로 sub_type / started_at / tool_use_id
    검증 → trace 시각 범위 집계 + tool_use_id 매칭.

    issue #598 multi-slot 매칭 정책:
      - `tool_use_id` 명시 + 매칭 슬롯 존재 → 그 슬롯만 pop (동시 Agent 정확 귀속).
      - `tool_use_id` 미매칭/None + 슬롯 *1개뿐* → 그 1개 pop (단일/구버전·drift 폴백).
      - `tool_use_id` 미매칭/None + 슬롯 여러 개 → 모호 → pop 안 함 (None 반환).
      - `pending_agents` 비었고 구버전 단일 슬롯(`pending_agent`) 잔존 → 흡수 (업그레이드 호환).
    """
    live = read_live(session_id, base_dir=base_dir) or {}
    active = live.get("active_runs", {})
    if not isinstance(active, dict) or run_id not in active:
        return None
    slot = dict(active[run_id])
    pending = slot.get("pending_agents")
    pending = dict(pending) if isinstance(pending, dict) else {}

    popped: Optional[Dict[str, Any]] = None
    changed = False
    if pending:
        if tool_use_id and tool_use_id in pending:
            popped = pending.pop(tool_use_id)
            changed = True
        elif len(pending) == 1:
            # tool_use_id 미매칭/None 인데 슬롯 1개 — drift 시각 범위 폴백 pop.
            popped = pending.popitem()[1]
            changed = True
        # else: 여러 개 + 매칭 없음 → 모호 → pop 안 함.
    elif isinstance(slot.get("pending_agent"), dict):
        # 구버전 단일 슬롯(pending_agent) 잔존분 흡수 (in-flight 업그레이드 호환).
        popped = slot.pop("pending_agent")
        changed = True

    if not changed:
        return None  # 변경 없음 — write skip
    if pending:
        slot["pending_agents"] = pending
    else:
        slot.pop("pending_agents", None)  # 빈 dict 제거 (깔끔)
    active = dict(active)
    active[run_id] = slot
    update_live(session_id, base_dir=base_dir, active_runs=active)
    return popped if isinstance(popped, dict) else None


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
    # (d) active_runs scan 폴백 — 가장 최근 미완료 run 의 session_id
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
    # (c) pointer/env sid 가 있으면 해당 세션 active_runs 를 먼저 scan
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
    if not sid_hint:
        sid_hint = current_session_id(base_dir=base_dir)
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
    session_roots = [base / ".sessions", base / "sessions"]  # legacy fallback
    session_roots = [p for p in session_roots if p.is_dir()]
    if not session_roots:
        return None

    if session_id:
        best: Optional[tuple[str, str, str]] = None
        for sessions_dir in session_roots:
            slot = _scan_live_file_for_active_run(
                sessions_dir / session_id / "live.json",
                session_id=session_id,
            )
            if slot and (best is None or slot[0] > best[0]):
                best = slot
        if best is None:
            return None
        return (best[1], best[2])

    # live.json mtime 최신 max_sessions 개만 추출 (비용 가드)
    candidates: list[tuple[float, Path]] = []
    for sessions_dir in session_roots:
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
            continue
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


# ── hook fail-open diagnostics (#784) ────────────────────────────────


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
    design_doc = getattr(args, "design_doc", None)
    lane = getattr(args, "lane", None)
    acceptance_required = bool(getattr(args, "acceptance_required", False))
    try:
        start_run(
            sid, rid, args.entry_point,
            issue_num=issue_num, design_doc=design_doc, lane=lane,
            acceptance_required=acceptance_required,
        )
    except ValueError as exc:
        print(f"[begin-run] FAIL — {exc}", file=sys.stderr)
        return 1
    _ledger_run_started(
        sid, rid, args.entry_point,
        issue_num=issue_num, design_doc=design_doc, lane=lane,
        acceptance_required=acceptance_required,
    )
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
    # 이슈 #587 — ledger run_finished checkpoint (complete_run 후 = run 종료 기록).
    try:
        from harness import ledger
        ledger.append_event(sid, rid, "run_finished")
    except Exception:  # nosec B110
        pass
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
        0 — 정상 (marker 있음) 또는 sid 미해결 (silent skip)
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
        dcness-helper next-task [--entry-point impl] [--design-doc <path>]

    Exit codes:
        0 — 정상 (이전 run finalize + 새 run 발급)
        1 — sid 미해결 / design_doc 검증 실패
    """
    sid = auto_detect_session_id()
    if not sid:
        print(diagnose_sid_rid_resolution(mode="sid"), file=sys.stderr)
        return 1

    entry_point = getattr(args, "entry_point", "impl") or "impl"
    design_doc = getattr(args, "design_doc", None)
    acceptance_required = bool(getattr(args, "acceptance_required", False))
    if acceptance_required and entry_point != "impl":
        print(
            "[next-task] begin-run FAIL — acceptance_required is only valid "
            f"for entry_point=impl (got {entry_point!r})",
            file=sys.stderr,
        )
        return 1
    if design_doc is not None:
        # 이전 run end-run(비가역) *전* 선검증 — 경로 오타로 이전 run 만 닫히고
        # 새 run 발급이 실패하는 어긋남(prev review echo 영구 소실) 방지.
        try:
            design_doc = _validate_design_doc(design_doc)
        except ValueError as exc:
            print(f"[next-task] begin-run FAIL — {exc}", file=sys.stderr)
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

    new_rid = generate_run_id()
    try:
        start_run(
            sid, new_rid, entry_point, issue_num=None, design_doc=design_doc,
            acceptance_required=acceptance_required,
        )
    except Exception as exc:
        print(f"[next-task] begin-run FAIL — {exc}", file=sys.stderr)
        return 1
    # 이슈 #587 (codex review) — chain task run 도 run_started checkpoint 남김.
    _ledger_run_started(
        sid, new_rid, entry_point, design_doc=design_doc,
        acceptance_required=acceptance_required,
    )
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
    if design_doc:
        print(f"[new] design_doc: {design_doc}")
    if acceptance_required:
        print("[new] acceptance_required: true")
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


def _cli_prev_tasks_append(args: Any) -> int:
    """#525 — build-worker 가 phase 3 종료 시 자기 task 산출 요약 한 줄 append.

    Usage: dcness-helper prev-tasks-append <slug> "<산출 요약 한 줄>"

    다음 task 진입 시 메인의 `begin-step build-worker` 가 [PREVIOUS_TASKS] 로
    emit → 메인이 build-worker prompt 에 포함. task 간 인터페이스 misalign 완화.
    """
    from harness.prev_tasks import append

    path = append(args.slug, args.summary, cwd=Path.cwd())
    print(f"[prev-tasks] appended → {path}", file=sys.stderr)
    return 0


def _cli_prev_tasks_reset(args: Any) -> int:
    """#525 — impl-loop chain 시작 시 누적 초기화 (skill 진입 1회 권장).

    Usage: dcness-helper prev-tasks-reset
    """
    from harness.prev_tasks import reset

    reset(cwd=Path.cwd())
    print("[prev-tasks] reset", file=sys.stderr)
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
    # #700 — agent 이름 canonical 정규화. update_current_step 도 내부 정규화하지만
    # ledger checkpoint / engineer hint 까지 같은 표기로 일관시킨다.
    from harness.agent_names import normalize_agent_type
    agent = normalize_agent_type(args.agent) or args.agent
    update_current_step(sid, rid, agent, mode)
    # 이슈 #587 — ledger step_started checkpoint. 기록 실패가 begin-step 막지 않게 silent.
    try:
        from harness import ledger
        ledger.append_event(sid, rid, "step_started", agent=agent, mode=mode)
    except Exception:  # nosec B110
        pass

    # DCN-CHG-20260430-36: agent="engineer" 시 직전 engineer invocation 의
    # tool_use_count stderr hint. LLM self-monitor 불가 영역 정보 보강.
    # 측정 실패 silent (노이즈 회피).
    if agent == "engineer":
        prior = _prior_engineer_tool_use_count(sid)
        if prior is not None and prior > 0:
            print(
                f"[hint] prior engineer tool_use_count={prior} — "
                f"단일 호출 capacity 압박 인지 시 IMPL_PARTIAL 분할 자율 판단 권고. "
                f"강제 X (정보만).",
                file=sys.stderr,
            )

    print("ok")

    prompt_slot_check = _prompt_slot_check_text(sid, rid)
    if prompt_slot_check:
        print(f"\n{prompt_slot_check}")

    # DCN-CHG-20260502-02: 해당 agent/mode 의 loop insights 있으면 stdout 주입.
    # 메인 Claude 가 Bash 결과로 읽고 Agent prompt 에 포함시킨다.
    try:
        from harness.loop_insights import read as _li_read
        _insights = _li_read(args.agent, mode or None)
        if _insights:
            label = f"{args.agent}/{mode}" if mode else args.agent
            print(f"\n[INSIGHTS: {label}]\n{_insights}")
    except Exception:  # nosec B110
        pass  # insights 주입 실패는 silent — 본 step 차단 X

    # #525: build-worker 진입 시 직전 task 산출 요약 stdout 주입. 메인 Claude 가
    # Bash 결과로 읽고 build-worker prompt 에 포함시킨다 (loop_insights 와 동일
    # 경로). 자기 task 는 phase 3 종료 시 append 되므로 여기선 직전까지만 보인다.
    if args.agent == "build-worker":
        try:
            from harness.prev_tasks import read as _pt_read
            _prev = _pt_read()
            if _prev:
                print(f"\n[PREVIOUS_TASKS]\n{_prev}")
        except Exception:  # nosec B110
            pass  # 주입 실패 silent — 본 step 차단 X

    return 0


def _cli_run_dir(args: Any) -> int:
    """현재 active run 의 run_dir 절대 경로 stdout (DCN-CHG-20260430-21).

    skill prompt 가 prose-file path 를 /tmp 대신 run-dir 안에 쓸 때 사용.
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


def _cli_run_status(args: Any) -> int:
    """현재 (또는 --run-id) run 의 ledger 기반 진행 상태 요약 (이슈 #587).

    compaction/resume 후 메인 Claude 가 긴 prose 재주입 없이 ledger 만 보고
    task / phase / last event / next action / evidence pointer 를 복원한다.
    """
    sid = auto_detect_session_id()
    rid = getattr(args, "run_id", None) or auto_detect_run_id()
    if not sid or not rid:
        print(diagnose_sid_rid_resolution(mode="both"), file=sys.stderr)
        return 1
    from harness import ledger

    print(ledger.render_status(sid, rid))
    return 0


def _cli_chain_view(args: Any) -> int:
    """impl-loop chain 진행 뷰 자동 렌더 → JSON stdout (#755).

    chain 모드에서 task 경계마다 메인이 진행 뷰를 손으로 다시 그리는 대신,
    task list + current index 를 입력받아 진행 뷰 표현 + Task operation
    시퀀스 + 비용 분기를 산출한다. 진행 뷰 규칙 SSOT = impl-loop SKILL 의
    "진행 뷰" 절 (본 helper 는 그 규칙을 코드로 옮길 뿐).

    **도구이지 게이트 아님** — run state 를 읽거나 쓰지 않는 순수 변환이라,
    미사용해도 chain 진행을 막지 않고 메인이 수동 rebuild 로 폴백할 수 있다.
    내부 helper (run-dir / run-status / wave-plan 류) — 새 공개 진입점 아님.
    """
    from harness import chain_view

    return chain_view.main(
        [
            "--tasks",
            args.tasks,
        ]
        + (["--current", str(args.current)] if args.current is not None else [])
        + (["--prev", str(args.prev)] if args.prev is not None else [])
        + (["--initial"] if getattr(args, "initial", False) else [])
    )


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
                    "blocked_prior_paths": list(exc.result.blocked_prior_paths),
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


def _cli_ledger_event(args: Any) -> int:
    """ledger 에 *수동* checkpoint event 한 줄 기록 (pr_created/pr_merged/task_completed/blocked 등 — 이슈 #587).

    강제 아님 — 메인/skill 이 PR 생성·머지·차단 같은 checkpoint 를 *선택적* 으로
    남기는 경로.

    🔴 helper-owned lifecycle event (run_started/step_started/step_completed/run_finished)
    는 거부한다 (codex review). 수동 CLI 로 receipt 필드 없는 가짜 step_completed 를
    넣으면 read_step_completed/list_runs/finalize-run 이 진짜 step 으로 취급해
    prose-as-SSOT invariant 가 깨진다 — lifecycle 은 begin-run/begin-step/end-step/
    end-run 코드 경로 전용.
    """
    sid = auto_detect_session_id()
    rid = auto_detect_run_id()
    if not sid or not rid:
        print(diagnose_sid_rid_resolution(mode="both"), file=sys.stderr)
        return 1
    from harness import ledger

    if args.event_type not in ledger.MANUAL_EVENT_TYPES:
        print(
            f"[session_state] ledger-event 는 수동 checkpoint 만 허용: "
            f"{sorted(ledger.MANUAL_EVENT_TYPES)}. "
            f"lifecycle event(run_started/step_started/step_completed/run_finished)는 "
            f"begin-run/begin-step/end-step/end-run 코드 경로 전용 — 수동 위조 차단.",
            file=sys.stderr,
        )
        return 1

    fields: Dict[str, Any] = {}
    for key in ("agent", "mode", "pr_number", "url", "issue_num", "reason"):
        val = getattr(args, key, None)
        if val is not None:
            fields[key] = val
    try:
        rec = ledger.append_event(sid, rid, args.event_type, **fields)
    except ValueError as exc:
        print(f"[session_state] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(rec, ensure_ascii=False))
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
    대개 마지막에 `## 결론` / `## Summary` / `## 변경 요약` 섹션 씀 — 그 섹션이 가장
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
    except Exception:  # nosec B110
        pass
    return None


def _cli_end_step(args: Any) -> int:
    """sid+rid auto-detect → write_prose → prose-only (PROSE_LOGGED).

    부수 출력: stderr 로 `[agent:mode = PROSE_LOGGED]` 헤더 + prose 요약 ~5줄. 모든
    skill 자동 수혜 — skill prompt 안에 별도 요약 instruction 쓸 필요 0.
    """
    from harness.signal_io import write_prose

    sid = auto_detect_session_id()
    rid = auto_detect_run_id()
    if not sid or not rid:
        print(diagnose_sid_rid_resolution(mode="both"), file=sys.stderr)
        return 1

    mode = args.mode if args.mode else None
    # #700 — end-step 의 agent 도 canonical 정규화. namespaced 로 begin-step+Agent 한 뒤
    # end-step 을 namespaced 로 호출해도 write_prose 이름 검증(콜론 거부)에 안 걸리고,
    # begin-step 이 정규화 저장한 current_step.agent(bare)와 DRIFT 오탐 없이 일치한다.
    from harness.agent_names import normalize_agent_type
    agent = normalize_agent_type(args.agent) or args.agent

    # DCN-CHG-20260430-25: drift detector — current_step 와 end-step agent 불일치 시 WARN.
    # 메인 Claude 가 begin-step 안 부르고 end-step 호출하거나, 다른 agent 에 대한
    # begin-step 이후 다른 agent end-step 부르는 경우 잡음. 자동 보정 X (안전).
    try:
        live = read_live(sid)
        slot = live.get("active_runs", {}).get(rid, {}) if live else {}
        cur_step = slot.get("current_step") if slot else None
        if cur_step:
            cur_agent = cur_step.get("agent")
            cur_mode = cur_step.get("mode")
            if cur_agent and cur_agent != agent:
                print(
                    f"[session_state] DRIFT WARN — current_step={cur_agent}"
                    f"{':' + cur_mode if cur_mode else ''} but end-step={agent}"
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
                f"end-step={agent}{':' + mode if mode else ''}. "
                f"begin-step 안 호출하고 end-step 호출. ledger.jsonl 에 기록은 됨.",
                file=sys.stderr,
            )
    except Exception:  # nosec B110
        # drift detector 자체 실패는 silent — end-step 동작 우선
        pass

    # DCN-CHG-20260501-15: prose 로딩 — --prose-file 제공 시 legacy 경로, 없으면 hook auto-stage.
    if args.prose_file:
        prose = Path(args.prose_file).read_text(encoding="utf-8")
        if not prose.strip():
            print("[session_state] empty prose", file=sys.stderr)
            return 1
        base = session_dir(sid) / "runs"
        occ = _count_step_occurrences(sid, rid, agent, mode)
        prose_path = write_prose(agent, rid, prose, mode=mode, base_dir=base, occurrence=occ)
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
            _staged = _find_prose_fallback(sid, rid, agent, mode)
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

    # 자유서술 방식 (이슈 #280/#284) — 메인 Claude 가 prose 자체를 직접 읽고 분기 결정.
    # stdout 은 sentinel "PROSE_LOGGED" 로 통일. 옛 enum 기계 추출은 폐기.
    agent_label = agent if not mode else f"{agent}:{mode}"

    print("PROSE_LOGGED")
    print(f"[{agent_label} = PROSE_LOGGED]", file=sys.stderr)
    summary = _extract_prose_summary(prose)
    if summary:
        print(summary, file=sys.stderr)
    # step status append — finalize-run / 회고용
    _append_step_status(
        sid, rid, agent, mode, "PROSE_LOGGED", prose, prose_path,
    )
    clear_current_step(sid, rid, agent=agent, mode=mode)
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
                (line.strip() for line in lines[i + 1:] if line.strip()), ""
            )
            if not next_content or _NEXT_LINE_NEGATION_RE.match(next_content):
                continue  # 다음 줄이 없거나 부정 → false positive
        return True
    return False


def _steps_jsonl_path(sid: str, rid: str, *, base_dir: Optional[Path] = None) -> Path:
    """[deprecated] 옛 `.steps.jsonl` 경로 — ledger.jsonl 로 흡수됨 (이슈 #587).

    `ledger.legacy_steps_path` 위임 (마이그레이션 폴백 참조 전용). 새 코드는
    `harness.ledger` 모듈을 직접 쓴다.
    """
    from harness import ledger

    return ledger.legacy_steps_path(sid, rid, base_dir=base_dir)


def _count_step_occurrences(
    sid: str,
    rid: str,
    agent: str,
    mode: Optional[str],
    *,
    base_dir: Optional[Path] = None,
) -> int:
    """(agent, mode) step_completed 수 반환 (write_prose occurrence 계산용 — 이슈 #587).

    `ledger.count_step_completed` 위임 (ledger.jsonl 우선, 옛 .steps.jsonl 폴백).
    """
    from harness import ledger

    return ledger.count_step_completed(sid, rid, agent, mode, base_dir=base_dir)


def _append_step_status(
    sid: str,
    rid: str,
    agent: str,
    mode: Optional[str],
    enum: str,
    prose: str,
    prose_path: "Path",
) -> None:
    """end-step 호출마다 ledger.jsonl 에 step_completed event append (이슈 #587).

    옛 단일 .steps.jsonl row → `ledger.append_step_completed` 위임. receipt
    (sha256 / evidence_paths / next_action) 가 옛 필드 (prose_excerpt / must_fix /
    prose_file) 의 superset 으로 기록된다. prose 가 SSOT, ledger 는 색인 장부.
    """
    from harness import ledger

    ledger.append_step_completed(sid, rid, agent, mode, enum, prose, prose_path)


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


def _read_steps_jsonl(
    sid: str,
    rid: str,
    *,
    base_dir: Optional[Path] = None,
) -> list:
    """run 의 step_completed event 를 시간순 반환 (옛 `.steps.jsonl` 호환 — 이슈 #587).

    `ledger.read_step_completed` 위임. ledger.jsonl 우선, 없으면 옛 .steps.jsonl
    폴백 (마이그레이션 셔틀). 반환 레코드는 옛 row 필드명 호환 — 소비처
    (finalize-run / strict-conveyor / Stop hook) 는 그대로 읽는다.
    """
    from harness import ledger

    return ledger.read_step_completed(sid, rid, base_dir=base_dir)


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
    # 명시 시 ledger.jsonl step_completed 수 미만이면 stderr WARN. /impl-loop 자기검증.
    expected = getattr(args, "expected_steps", None)
    if expected is not None and len(steps) < expected:
        print(
            f"[session_state] STEP COUNT WARN — ledger.jsonl step_completed={len(steps)} < "
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
    except Exception:  # nosec B110
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
                        f"[REVIEW_READY] {review_path} — 위 리뷰를 세션에 그대로 출력할 것 (loop-procedure.md 의 Step 8 review 결과 인지)",
                        file=sys.stderr,
                    )
                except Exception:  # nosec B110
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
_YOLO_FALLBACKS: Dict[str, Dict[str, Optional[str]]] = {
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
        # 분류 의존 분기 — 단일 정적 action 으로 target 을 못 정한다.
        # re-invoke(현재=read-only validator 재호출, 같은 FAIL 반복) X.
        # re-invoke-prev(직전 step 고정) X — Step 5 SYSTEM_BOUNDARY 는 직전이 module-architect
        # 라도 target 이 system-architect. 실제 target 은 finding 분류(hint)가 진본 —
        # 메인이 분류를 읽고 분기, 분류 모호하면 사용자 위임 (mechanical 재호출 금지).
        "action": "route-by-classification",
        "hint": (
            "validator 재호출 X — finding 분류로 architect 분기 (design-routing): "
            "SYSTEM_BOUNDARY → system-architect 재진입 / "
            "CONTRACT_PROPAGATION → module-architect mode=contract_sweep / "
            "TASK_LOCAL → module-architect 보강(해당 task). 분류 모호 시 사용자 위임 (cycle ≤ 2)"
        ),
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


def _cli_hook_fail_open(args: Any) -> int:
    """hook wrapper 내부용 fail-open 이벤트 기록."""
    record_fail_open_event(
        hook=args.hook,
        category=args.category,
        detail=args.detail or "",
        severity=args.severity,
    )
    return 0


# ── status 진단표 (#520) ────────────────────────────────────────────
#
# `dcness-helper status` 를 PASS/WARN/FAIL/INFO/NA 진단표로 확장한다. 별도 doctor
# 진입점을 추가하지 않고 (사용자가 외울 표면 최소화), init-dcness 가 셋업과 상태 점검을
# 겸하게 한다. 진단 수집은 deterministic 코드 (추측 누락 차단), 출력 종합/권유는
# init-dcness skill prose 가 담당. routing doctor 의 PASS/FAIL 관용구를 따른다.
#
# 배포 항목을 새로 추가할 때 (init-dcness 의 git hook / CI workflow / Read 권한 등)
# 아래 검사 항목도 함께 갱신해야 한다 (docs/plugin/init-dcness.md 의무 명시).

_READ_PERM = "Read(~/.claude/plugins/cache/dcness/**)"
_GIT_HOOK_SHIMS = ("commit-msg", "post-checkout", "pre-push")
# thin-shim 식별: 세 hook 모두 plugin cache 경로를 동적 resolve 한다.
_SHIM_MARKERS = ("plugins/cache/dcness", "CLAUDE_PLUGIN_ROOT")
_CI_WORKFLOWS = (
    "git-naming-validation.yml",
    "pr-body-validation.yml",
    "doc-path-integrity.yml",
    "doc-sync.yml",
    "github-project-lifecycle.yml",
)
_CODEX_VALIDATOR_SKILLS = (
    "dcness-code-validator",
    "dcness-architecture-validator",
    "dcness-pr-reviewer",
)


def _is_self_repo(project_root: Path) -> bool:
    """dcNess plugin 본체 repo 판정 — `.claude-plugin/plugin.json` name == dcness.

    외부 활성 프로젝트엔 이 파일이 없다. self repo 는 init-dcness 미적용이라
    외부 활성 규칙(whitelist/Read권한/hook/CI)을 검사 대상에서 제외한다 (#520 AC 5).
    """
    pj = project_root / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(pj.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and data.get("name") == "dcness"


def _plugin_root() -> Path:
    """설치된 plugin root.

    CLAUDE_PLUGIN_ROOT env 우선 — 단 그 경로의 manifest 가 *dcness* 일 때만 신뢰한다.
    다른 plugin/agent runtime 이 env 를 set 한 경우 그 plugin 의 version 을 dcNess
    version 으로 오보하지 않도록, env 가 비었거나 dcness 가 아니면 본 파일 기준
    (harness 의 부모) 으로 폴백.
    """
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        cand = Path(env)
        if _is_self_repo(cand):
            return cand
    return Path(__file__).resolve().parent.parent


def _installed_plugin_version(plugin_root: Path) -> Optional[str]:
    """설치된 plugin 의 manifest version. 읽기 실패 시 None."""
    pj = plugin_root / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(pj.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    v = data.get("version")
    return v if isinstance(v, str) else None


def _settings_path() -> Path:
    """CC 사용자 settings.json 경로."""
    return Path.home() / ".claude" / "settings.json"


def _check_read_permission(settings_path: Path) -> bool:
    """SessionStart 가 plugin SSOT 문서를 inject 하려면 필요한 Read allow 존재 여부."""
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    perms = data.get("permissions")
    allow = perms.get("allow") if isinstance(perms, dict) else None
    return isinstance(allow, list) and _READ_PERM in allow


def _resolve_git_hooks_dir(project_root: Path) -> Path:
    """git 이 실제로 실행하는 hooks 디렉토리.

    `core.hooksPath` (Husky 등) 가 설정되면 git 은 `.git/hooks` 를 무시한다. 진단이
    "git 이 정말 이 hook 을 실행하는가" 를 보려면 git 이 보는 경로를 따라야 한다.
    git 호출 실패 시 `.git/hooks` 폴백.
    """
    try:
        proc = subprocess.run(  # nosec B603, B607
            [
                "git", "-C", str(project_root),
                "rev-parse", "--path-format=absolute", "--git-path", "hooks",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
            text=True,
        )
        if proc.returncode == 0:
            out = proc.stdout.strip()
            if out:
                return Path(out)
    except (OSError, subprocess.SubprocessError):
        pass
    return project_root / ".git" / "hooks"


def _check_git_hooks(hooks_dir: Path) -> Dict[str, str]:
    """각 git hook 의 상태.

    git 이 그 hook 을 실제로 실행할 조건까지 본다:
    'ok' (thin shim + 실행권한) / 'missing' / 'foreign' (dcness shim 아님)
    / 'not-exec' (dcness shim 이지만 실행권한 없어 git 이 무시 — POSIX).
    """
    result: Dict[str, str] = {}
    for name in _GIT_HOOK_SHIMS:
        p = hooks_dir / name
        if not p.exists():
            result[name] = "missing"
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            result[name] = "foreign"
            continue
        if not any(m in content for m in _SHIM_MARKERS):
            result[name] = "foreign"
            continue
        if not os.access(p, os.X_OK):
            result[name] = "not-exec"
            continue
        result[name] = "ok"
    return result


def _check_ci_workflows(project_root: Path) -> Dict[str, bool]:
    """선택형 CI workflow yml 존재 여부 (선택이라 부재해도 FAIL 아님)."""
    wf_dir = project_root / ".github" / "workflows"
    return {name: (wf_dir / name).exists() for name in _CI_WORKFLOWS}


def _check_codex_validator_skills(plugin_root: Path, codex_home: Path) -> Dict[str, str]:
    """Codex validator skill 배포 상태.

    'ok' / 'missing' / 'stale' / 'missing-source'. target 이 plugin source 와
    byte-for-byte 같아야 core activation 이 실제 배포 완료라고 볼 수 있다.
    """
    result: Dict[str, str] = {}
    for name in _CODEX_VALIDATOR_SKILLS:
        source = plugin_root / "codex" / "skills" / name / "SKILL.md"
        target = codex_home / "skills" / name / "SKILL.md"
        try:
            source_content = source.read_text(encoding="utf-8")
        except OSError:
            result[name] = "missing-source"
            continue
        try:
            target_content = target.read_text(encoding="utf-8")
        except OSError:
            result[name] = "missing"
            continue
        result[name] = "ok" if target_content == source_content else "stale"
    return result


def _check_gh_auth() -> bool:
    """gh CLI 인증 여부 (read-only). gh 미설치/미인증 시 False."""
    try:
        proc = subprocess.run(  # nosec B603, B607
            ["gh", "auth", "status"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def collect_status_diagnostics(
    cwd: Optional[Path] = None,
    *,
    settings_path: Optional[Path] = None,
    plugin_root: Optional[Path] = None,
    codex_home: Optional[Path] = None,
    check_gh: bool = True,
    check_routing: bool = True,
) -> Dict[str, Any]:
    """현재 프로젝트 설치 상태를 검사해 진단 결과를 모은다 (read-only, deterministic).

    반환: {project_root, self_repo, checks: [{key,label,status,detail,fix}], summary}.
    status ∈ {PASS, FAIL, WARN, INFO, NA}. 외부 의존(gh / routing)은 toggle 로 분리해
    단위 테스트에서 부수효과를 끈다.
    """
    project_root = _resolve_project_root(cwd).resolve()
    self_repo = _is_self_repo(project_root)
    settings_path = settings_path or _settings_path()
    plugin_root = plugin_root or _plugin_root()
    codex_home = codex_home or Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))

    checks: list = []

    def add(key: str, label: str, status: str, detail: str, fix: Optional[str] = None) -> None:
        checks.append(
            {"key": key, "label": label, "status": status, "detail": detail, "fix": fix}
        )

    # 정보 항목 (self / 외부 공통)
    add("project_root", "cwd project root", "INFO", str(project_root))
    version = _installed_plugin_version(plugin_root)
    add("plugin_version", "installed plugin version", "INFO", version or "unknown")

    if self_repo:
        na_detail = "self repo — init-dcness 미적용 (CLAUDE.md + git-spec 만 적용)"
        for key, label in (
            ("whitelist", "whitelist 활성"),
            ("read_perm", "Read 권한 (~/.claude/settings.json)"),
            ("git_hooks", "git hook shim 3종"),
            ("codex_skills", "Codex validator skills"),
            ("ci_workflows", "선택형 CI workflow"),
        ):
            add(key, label, "NA", na_detail)
    else:
        # whitelist 활성
        active = is_project_active(cwd)
        add(
            "whitelist",
            "whitelist 활성",
            "PASS" if active else "FAIL",
            "활성" if active else "비활성 (이 프로젝트가 whitelist 에 없음)",
            None if active else 'dcness-helper enable',
        )
        # Read 권한
        has_perm = _check_read_permission(settings_path)
        add(
            "read_perm",
            "Read 권한 (~/.claude/settings.json)",
            "PASS" if has_perm else "FAIL",
            f"{_READ_PERM} {'존재' if has_perm else '없음'}",
            None if has_perm else f"init-dcness Step 3 으로 {_READ_PERM} 추가",
        )
        # git hook shim 3종 (git 이 실제 실행하는 경로 + 실행권한까지 검사)
        hooks_dir = _resolve_git_hooks_dir(project_root)
        hooks = _check_git_hooks(hooks_dir)
        all_ok = all(v == "ok" for v in hooks.values())
        custom_path = hooks_dir.resolve() != (project_root / ".git" / "hooks").resolve()
        hook_detail = ", ".join(f"{k}={v}" for k, v in hooks.items())
        if custom_path:
            hook_detail += f" (core.hooksPath={hooks_dir})"
        if all_ok:
            hook_fix = None
        elif custom_path:
            # init-dcness Step 4 는 .git/hooks 로 복사 → core.hooksPath 환경에선 무효.
            hook_fix = (
                f"core.hooksPath={hooks_dir} 설정됨 — Step 4(.git/hooks 복사)로는 해결 안 됨. "
                f"shim 을 {hooks_dir} 로 설치(chmod +x)하거나 core.hooksPath 를 해제하세요."
            )
        else:
            hook_fix = "init-dcness Step 4 로 thin shim 재설치 (chmod +x 포함)"
        add(
            "git_hooks",
            "git hook shim 3종",
            "PASS" if all_ok else "FAIL",
            hook_detail,
            hook_fix,
        )
        # Codex validator skills (core — source 와 target 일치까지 검사)
        codex_skills = _check_codex_validator_skills(plugin_root, codex_home)
        codex_all_ok = all(v == "ok" for v in codex_skills.values())
        add(
            "codex_skills",
            "Codex validator skills",
            "PASS" if codex_all_ok else "FAIL",
            ", ".join(f"{k}={v}" for k, v in codex_skills.items()),
            None if codex_all_ok else "init-dcness Core Step 5 로 Codex validator skills 재배포",
        )
        # 선택형 CI workflow (선택 — INFO)
        ci = _check_ci_workflows(project_root)
        installed = [k for k, present in ci.items() if present]
        add(
            "ci_workflows",
            "선택형 CI workflow",
            "INFO",
            f"설치됨: {', '.join(installed)}" if installed else "없음 (선택 사항)",
        )

    # Codex routing (self / 외부 공통 — INFO)
    if check_routing:
        try:
            from harness import agent_routing

            routing_detail = agent_routing.format_status().strip().replace("\n", " | ")
        except Exception:
            routing_detail = "조회 실패"
        add("routing", "Codex routing", "INFO", routing_detail)

    # gh CLI 인증 (self / 외부 공통 — WARN)
    if check_gh:
        gh_ok = _check_gh_auth()
        add(
            "gh_auth",
            "GitHub CLI 인증",
            "PASS" if gh_ok else "WARN",
            "인증됨" if gh_ok else "미인증/미설치 — PR·issue 자동화 제한",
            None if gh_ok else "gh auth login",
        )

    fail_open = collect_fail_open_summary(cwd=project_root)
    fail_open_total = int(fail_open.get("total") or 0)
    add(
        "hook_fail_open",
        "hook fail-open 진단",
        "WARN" if fail_open_total else "PASS",
        _format_fail_open_summary(fail_open),
        (
            "반복되면 hook stderr 로그와 fail-open reason category 를 확인하고 "
            "dcness 업데이트 또는 이슈 제보"
            if fail_open_total else None
        ),
    )

    status_labels = ("PASS", "WARN", "FAIL")
    summary = {status: 0 for status in status_labels}
    for c in checks:
        if c["status"] in summary:
            summary[c["status"]] += 1

    return {
        "project_root": str(project_root),
        "self_repo": self_repo,
        "checks": checks,
        "summary": summary,
    }


def format_status_report(diag: Dict[str, Any]) -> str:
    """진단 결과를 사람이 읽는 PASS/WARN/FAIL prose 로 포맷한다."""
    lines: list = []
    if diag["self_repo"]:
        lines.append("[dcness] === self repo (dcNess plugin 본체) 진단 ===")
        lines.append(
            "[dcness] init-dcness 미적용 — CLAUDE.md + docs/plugin/git-spec.md 만 적용"
        )
        lines.append("[dcness] 외부 활성 항목은 self repo 에 해당 없음 (N/A)")
    else:
        lines.append("[dcness] === 외부 활성 프로젝트 진단 ===")

    for c in diag["checks"]:
        line = f"  [{c['status']}] {c['label']}: {c['detail']}"
        lines.append(line)
        if c["status"] in ("FAIL", "WARN") and c["fix"]:
            lines.append(f"        → 해결: {c['fix']}")

    s = diag["summary"]
    lines.append(
        f"[dcness] 요약: {s['PASS']} PASS / {s['WARN']} WARN / {s['FAIL']} FAIL"
    )
    if s["FAIL"]:
        lines.append("[dcness] FAIL 항목을 위 해결 명령으로 처리한 뒤 status 를 재실행하세요.")
    elif s["WARN"]:
        lines.append("[dcness] WARN 항목은 선택 — 필요 시 해결 명령을 실행하세요.")
    elif not diag["self_repo"]:
        lines.append("[dcness] 모든 필수 항목 PASS — 활성화 정상.")
    return "\n".join(lines)


def _cli_status(args: Any) -> int:
    """whitelist + 현재 cwd 활성 상태를 진단표로 출력 (#520)."""
    diag = collect_status_diagnostics()
    print(format_status_report(diag))
    return 0


def _cli_routing(args: Any) -> int:
    """Local provider 분기 CLI.

    Provider 분기 state 는 plugin-scoped local config 다. Repository 는 의도적으로
    provider 분기 config 를 들고 있지 않다.
    """
    from harness import agent_routing

    action = args.routing_cmd
    if action == "status":
        print(agent_routing.format_status())
        return 0
    if action == "doctor":
        print(agent_routing.format_status())
        problems = agent_routing.doctor()
        if problems:
            return 1
        print("[dcness routing] doctor: PASS")
        return 0
    if action == "enable-codex-validation":
        path = agent_routing.enable_codex_validation()
        print(f"[dcness routing] enabled Codex validation: {path}")
        print(agent_routing.format_status())
        return 0
    if action == "disable-codex-validation":
        path = agent_routing.disable_codex_validation()
        print(f"[dcness routing] disabled Codex validation: {path}")
        print(agent_routing.format_status())
        return 0
    if action == "enable-codex-implementation":
        path = agent_routing.enable_codex_implementation()
        print(f"[dcness routing] enabled Codex implementation: {path}")
        print(agent_routing.format_status())
        return 0
    if action == "disable-codex-implementation":
        path = agent_routing.disable_codex_implementation()
        print(f"[dcness routing] disabled Codex implementation: {path}")
        print(agent_routing.format_status())
        return 0
    if action == "set":
        try:
            path = agent_routing.set_provider(args.agent, args.provider)
        except ValueError as exc:
            print(f"[dcness routing] {exc}", file=sys.stderr)
            return 1
        print(f"[dcness routing] set {args.agent}={args.provider}: {path}")
        return 0
    if action == "set-implementation":
        try:
            path = agent_routing.set_implementation_provider(args.agent, args.provider)
        except ValueError as exc:
            print(f"[dcness routing] {exc}", file=sys.stderr)
            return 1
        print(
            f"[dcness routing] set implementation {args.agent}={args.provider}: {path}"
        )
        return 0
    if action == "resolve":
        try:
            provider = agent_routing.resolve_provider(args.agent)
        except ValueError as exc:
            print(f"[dcness routing] {exc}", file=sys.stderr)
            return 1
        print(provider)
        return 0
    print(f"[dcness routing] unknown command: {action}", file=sys.stderr)
    return 1


def _build_arg_parser() -> Any:
    import argparse

    from harness import parallel_wave

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
    p_br.add_argument(
        "--design-doc", default=None, dest="design_doc",
        help="이 run 이 참조하는 머지된 설계 문서 경로 — engineer 게이트가 "
             "같은-run module-architect PASS 의 등가 사전 조건으로 인정",
    )
    p_br.add_argument(
        "--lane", default=None, choices=_VALID_LANES,
        help="/impl 2축 구현 경로(설계도 유무: lite / standard, #714) — lane=lite 는 "
             "설계도 없는 Lite 구현 경로로 engineer 게이트 설계 산출물 사전 조건 "
             "면제 신호. entry_point=impl 에서만 수용",
    )
    p_br.add_argument(
        "--acceptance-required", action="store_true",
        help="story/epic 마감 task run marker (#722) — pr-reviewer PASS 뒤 "
             "product-acceptance 전 Stop hook auto end-run 방지. entry_point=impl 전용",
    )
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
    p_nt.add_argument(
        "--design-doc", default=None, dest="design_doc",
        help="다음 task 가 참조하는 머지된 설계 문서 경로 (begin-run --design-doc 동일)",
    )
    p_nt.add_argument(
        "--acceptance-required", action="store_true",
        help="다음 task 가 story/epic 마감 acceptance 대상임을 기록 (#722)",
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

    # #525 — /impl-loop 직전 task 산출 요약 누적 (build-worker append → 다음 진입 emit)
    p_pta = sub.add_parser(
        "prev-tasks-append",
        help="#525 — build-worker task 산출 요약 append (다음 task [PREVIOUS_TASKS] emit)",
    )
    p_pta.add_argument("slug", help="task slug (예: 05-revival-button)")
    p_pta.add_argument("summary", help="산출 요약 한 줄")
    p_pta.set_defaults(func=_cli_prev_tasks_append)

    p_ptr = sub.add_parser(
        "prev-tasks-reset",
        help="#525 — impl-loop chain 시작 시 누적 초기화 (skill 진입 1회)",
    )
    p_ptr.set_defaults(func=_cli_prev_tasks_reset)

    p_bs = sub.add_parser("begin-step", help="current_step + heartbeat 갱신")
    p_bs.add_argument("agent")
    p_bs.add_argument("mode", nargs="?", default="")
    p_bs.set_defaults(func=_cli_begin_step)

    p_es = sub.add_parser(
        "end-step",
        help="prose 저장 (자유서술 방식 — stdout=PROSE_LOGGED, 이슈 #280/#284)",
    )
    p_es.add_argument("agent")
    p_es.add_argument("mode", nargs="?", default="")
    p_es.add_argument(
        "--prose-file", required=False, default=None,
        help="prose 본문 파일 경로 (미제공 시 hook auto-stage 경로 사용)",
    )
    p_es.set_defaults(func=_cli_end_step)

    p_rd = sub.add_parser("run-dir", help="현재 active run 의 run_dir 절대 경로 (DCN-30-21)")
    p_rd.set_defaults(func=_cli_run_dir)

    p_rs = sub.add_parser(
        "run-status",
        help="현재 run 의 phase/task/last event/next action/evidence 요약 (resume 복원 — 이슈 #587)",
    )
    p_rs.add_argument("--run-id", default=None, dest="run_id")
    p_rs.set_defaults(func=_cli_run_status)

    p_cv = sub.add_parser(
        "chain-view",
        help="impl-loop chain 진행 뷰 자동 렌더 JSON (task list + current → view/operations/strategy — #755)",
    )
    p_cv.add_argument(
        "--tasks",
        required=True,
        help="task list JSON 경로 ('-' = stdin). {tasks:[{name,engine,closes?}], current?}",
    )
    p_cv.add_argument(
        "--current",
        type=int,
        default=None,
        help="현재(in_progress) task 0-based index. 미지정 시 입력 JSON 의 current.",
    )
    p_cv.add_argument(
        "--prev",
        type=int,
        default=None,
        help="직전 완료 task 0-based index (transition, 반드시 current-1 인접). 미지정 시 current-1. 임의 점프는 --initial.",
    )
    p_cv.add_argument(
        "--initial",
        action="store_true",
        help="전체 task list 최초 생성 operation 산출 (transition 대신).",
    )
    p_cv.set_defaults(func=_cli_chain_view)

    p_wp = sub.add_parser(
        "wave-plan",
        help="impl task 들의 opt-in 병렬 wave 계획 JSON (chain dry preview — #636)",
    )
    p_wp.add_argument("paths", nargs="+", help="impl 파일 / 디렉토리 / glob")
    p_wp.add_argument(
        "--max-parallel",
        type=int,
        default=parallel_wave.DEFAULT_MAX_PARALLEL_WORKERS,
        dest="max_parallel",
        help=f"동시성 상한 (default {parallel_wave.DEFAULT_MAX_PARALLEL_WORKERS})",
    )
    p_wp.add_argument(
        "--high-risk",
        default="",
        dest="high_risk",
        help="메인 dry-preview 고위험 판정 slug (콤마 구분) → 직렬 강제",
    )
    p_wp.add_argument(
        "--register",
        action="store_true",
        help="#641 peer mode opt-in: wave 후보 impl path 를 claim board 에 등록",
    )
    p_wp.add_argument(
        "--plan-id",
        default=None,
        dest="plan_id",
        help="claim board 등록 묶음 식별자 (선택)",
    )
    p_wp.set_defaults(func=_cli_wave_plan)

    p_wc = sub.add_parser(
        "wave-claim",
        help="#641 peer mode: canonical impl path claim (unregistered면 serial flow)",
    )
    p_wc.add_argument("impl_path")
    p_wc.add_argument("--session-id", default=None, dest="session_id")
    p_wc.add_argument("--run-id", default=None, dest="run_id")
    p_wc.add_argument("--worktree", default=None)
    p_wc.add_argument("--branch", default=None)
    p_wc.add_argument(
        "--stale-after",
        type=int,
        default=2 * 60 * 60,
        dest="stale_after",
        help="stale 판정 초 (default 7200). 자동 reclaim 은 하지 않음.",
    )
    p_wc.set_defaults(func=_cli_wave_claim)

    p_wh = sub.add_parser("wave-heartbeat", help="#641 peer claim heartbeat 갱신")
    p_wh.add_argument("key_or_path")
    p_wh.add_argument("--session-id", default=None, dest="session_id")
    p_wh.add_argument("--run-id", default=None, dest="run_id")
    p_wh.set_defaults(func=_cli_wave_heartbeat)

    p_wrel = sub.add_parser("wave-release", help="#641 peer claim 상태 기록")
    p_wrel.add_argument("key_or_path")
    p_wrel.add_argument(
        "--state",
        choices=("completed", "failed", "released"),
        default="released",
    )
    p_wrel.add_argument("--pr", type=int, default=None)
    p_wrel.add_argument("--url", default=None)
    p_wrel.add_argument("--reason", default="")
    p_wrel.set_defaults(func=_cli_wave_release)

    p_wre = sub.add_parser("wave-reclaim", help="#641 stale claim 명시 reclaim")
    p_wre.add_argument("key_or_path")
    p_wre.add_argument("--reason", required=True)
    p_wre.set_defaults(func=_cli_wave_reclaim)

    p_ws = sub.add_parser("wave-status", help="#641 peer claim board 현황")
    p_ws.add_argument("--json", action="store_true")
    p_ws.set_defaults(func=_cli_wave_status)

    p_ml = sub.add_parser("merge-lock", help="#641 peer PR finalize mutex")
    ml_sub = p_ml.add_subparsers(dest="merge_lock_cmd", required=True)
    p_mla = ml_sub.add_parser("acquire", help="peer claim 이 있으면 merge lock 획득")
    p_mla.add_argument("--branch", default=None)
    p_mla.add_argument("--pr", type=int, default=None)
    p_mla.add_argument("--owner", default=None)
    p_mla.set_defaults(func=_cli_merge_lock)
    p_mlr = ml_sub.add_parser("release", help="merge lock 해제")
    p_mlr.add_argument("--token", required=True)
    p_mlr.add_argument("--claim-key", default=None, dest="claim_key")
    p_mlr.add_argument("--state", choices=("released", "failed"), default="released")
    p_mlr.add_argument("--reason", default="")
    p_mlr.set_defaults(func=_cli_merge_lock)
    p_mlc = ml_sub.add_parser("complete", help="PR merged 후 claim completed + lock release")
    p_mlc.add_argument("--token", required=True)
    p_mlc.add_argument("--claim-key", required=True, dest="claim_key")
    p_mlc.add_argument("--pr", type=int, default=None)
    p_mlc.add_argument("--url", default=None)
    p_mlc.set_defaults(func=_cli_merge_lock)
    p_mlb = ml_sub.add_parser(
        "break",
        help="#641 peer merge lock stale 복구 (tokenless, stale 확인 후)",
    )
    p_mlb.add_argument(
        "--stale-after",
        type=int,
        default=2 * 60 * 60,
        dest="stale_after",
        help="stale 판정 초 (default 7200). fresh lock 은 해제하지 않음.",
    )
    p_mlb.add_argument("--owner", default=None)
    p_mlb.add_argument("--reason", default="")
    p_mlb.set_defaults(func=_cli_merge_lock)

    p_le = sub.add_parser(
        "ledger-event",
        help="ledger 에 임의 event 기록 (pr_created/pr_merged/task_completed/blocked 등 — 이슈 #587)",
    )
    p_le.add_argument("event_type")
    p_le.add_argument("--agent", default=None)
    p_le.add_argument("--mode", default=None)
    p_le.add_argument("--pr", type=int, default=None, dest="pr_number")
    p_le.add_argument("--url", default=None)
    p_le.add_argument("--issue", type=int, default=None, dest="issue_num")
    p_le.add_argument("--reason", default=None)
    p_le.set_defaults(func=_cli_ledger_event)

    p_en = sub.add_parser("enable", help="현재 cwd 의 main repo 활성화 (whitelist 추가)")
    p_en.set_defaults(func=_cli_enable)

    p_di = sub.add_parser("disable", help="현재 cwd 비활성화 (whitelist 제거)")
    p_di.set_defaults(func=_cli_disable)

    p_ia = sub.add_parser("is-active", help="활성 여부 (silent, exit 0/1) — hook 게이트용")
    p_ia.set_defaults(func=_cli_is_active)

    p_hfo = sub.add_parser(
        "hook-fail-open",
        help="internal: enforcement hook fail-open diagnostic append",
    )
    p_hfo.add_argument("--hook", required=True)
    p_hfo.add_argument("--category", required=True)
    p_hfo.add_argument("--detail", default="")
    p_hfo.add_argument("--severity", default="WARN")
    p_hfo.set_defaults(func=_cli_hook_fail_open)

    p_st = sub.add_parser("status", help="whitelist + 현재 cwd 상태")
    p_st.set_defaults(func=_cli_status)

    p_rt = sub.add_parser(
        "routing",
        help="provider 분기 상태/설정 (local plugin data only)",
    )
    rt_sub = p_rt.add_subparsers(dest="routing_cmd", required=True)

    rt_status = rt_sub.add_parser("status", help="분기 config 출력")
    rt_status.set_defaults(func=_cli_routing)

    rt_doctor = rt_sub.add_parser("doctor", help="분기 config 검증")
    rt_doctor.set_defaults(func=_cli_routing)

    rt_enable = rt_sub.add_parser(
        "enable-codex-validation",
        help="code-validator / architecture-validator / pr-reviewer 를 Codex 로 보냄",
    )
    rt_enable.set_defaults(func=_cli_routing)

    rt_disable = rt_sub.add_parser(
        "disable-codex-validation",
        help="validation agent 분기를 Claude 로 되돌림",
    )
    rt_disable.set_defaults(func=_cli_routing)

    rt_set = rt_sub.add_parser("set", help="특정 validation agent provider 설정")
    rt_set.add_argument("agent")
    rt_set.add_argument("provider", choices=("claude", "codex"))
    rt_set.set_defaults(func=_cli_routing)

    rt_enable_impl = rt_sub.add_parser(
        "enable-codex-implementation",
        help="test-engineer / engineer / build-worker 를 Codex-first 로 보냄",
    )
    rt_enable_impl.set_defaults(func=_cli_routing)

    rt_disable_impl = rt_sub.add_parser(
        "disable-codex-implementation",
        help="implementation agent 분기를 Claude 로 되돌림",
    )
    rt_disable_impl.set_defaults(func=_cli_routing)

    rt_set_impl = rt_sub.add_parser(
        "set-implementation",
        help="특정 implementation agent provider 설정",
    )
    rt_set_impl.add_argument("agent")
    rt_set_impl.add_argument("provider", choices=("claude", "codex-first"))
    rt_set_impl.set_defaults(func=_cli_routing)

    rt_resolve = rt_sub.add_parser("resolve", help="agent provider resolve")
    rt_resolve.add_argument("agent")
    rt_resolve.set_defaults(func=_cli_routing)

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

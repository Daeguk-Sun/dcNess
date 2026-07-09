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

import importlib
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
    "mark_run_blocked",
    "evaluate_order_gate_for_step",
    "run_prose_has_pass",
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
    "format_fail_open_warning",
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
_DESIGN_SSOT_REMINDER_AGENTS = {"module-architect", "architecture-validator"}
_CONFIRMED_MOCKUP_DIR_REL = Path("docs/design-variants")


# ── 경로 유틸 ───────────────────────────────────────────────────────


_DEFAULT_BASE_CACHE: Dict[str, Path] = {}
_REPO_ROOT_CACHE: Dict[str, Path] = {}


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


# /impl legacy lane(설계도 유무) 닫힌 enum (#714). lite = 설계도 없음,
# standard = 설계도 있음. implementation gate 가 lane=lite 를 설계 산출물
# 사전 조건 면제 신호로 인정하므로, 임의 문자열이 면제를 유발하지 못하게
# 기록 시점에 이 집합으로 fail-fast 검증한다.
_VALID_LANES = ("lite", "standard")
_VALID_DESIGN_STAGES = ("design-ux", "design-system")


def start_run(
    session_id: str,
    run_id: str,
    entry_point: str,
    *,
    base_dir: Optional[Path] = None,
    issue_num: Optional[int] = None,
    design_doc: Optional[str] = None,
    lane: Optional[str] = None,
    stage: Optional[str] = None,
    acceptance_required: bool = False,
) -> None:
    """`active_runs[run_id]` 슬롯 추가 + run 디렉토리 생성.

    이미 존재하면 ValueError (중복 run_id 방어).

    design_doc — 이 run 이 참조하는 머지된 설계 문서 경로 (#701). 기록 시
    implementation gate 가 같은-run module-architect PASS 의 등가 사전 조건
    증거로 인정한다 (`/impl-loop` story/epic runner 처럼 설계가 별도 run 에서 머지된
    뒤 진입하는 경우).

    lane — /impl legacy lane(설계도 유무: "lite" / "standard", #714).
    lane="lite" 는 설계도 없는 direct 구현 경로로, implementation gate 가 설계 산출물
    사전 조건을 면제하는 신호다. 면제 누수 방지를 위해 (1) 닫힌 enum 만
    수용하고 (2) design_doc 과 동일하게 entry_point=impl run 에서만 기록을
    허용한다 — design/architect-loop run 의 module-architect PASS 강제는 코드
    보장으로 유지된다.

    acceptance_required — story/epic 마감 task 로, impl-validator PASS 뒤 inline
    product-acceptance 를 거쳐야 정상 종료되는 run 이라는 신호 (#722).
    Stop hook 이 이 marker 를 읽어 impl-validator 를 종료 agent 로 취급하지 않는다.

    stage — /design 내부 durable stage 기록(#958). 공개 entry_point 는 design 으로
    유지하고, design-runs.jsonl 에서 UX PR run 과 system PR run 을 구분한다.
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
    if stage is not None:
        if entry_point != "design":
            raise ValueError(
                f"stage is only valid for entry_point=design (got {entry_point!r})"
            )
        if stage not in _VALID_DESIGN_STAGES:
            raise ValueError(
                f"stage must be one of {_VALID_DESIGN_STAGES} (got {stage!r})"
            )
    if acceptance_required and entry_point != "impl":
        raise ValueError(
            "acceptance_required is only valid for entry_point=impl "
            f"(got {entry_point!r})"
        )
    if design_doc is not None:
        # design_doc 은 impl 구현 run 전용 — design/architect-loop run 의
        # build-worker ← module-architect PASS 강제가 코드 보장으로 유지되도록
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
        "stage": stage,
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
    stage: Optional[str] = None,
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
        if stage is not None:
            extra["stage"] = stage
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


def mark_run_blocked(
    session_id: str,
    run_id: str,
    *,
    category: str,
    agent: Optional[str] = None,
    mode: Optional[str] = None,
    provider: Optional[str] = None,
    reason: Optional[str] = None,
    raw_log: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Persist a run-level blocked marker in live.json.

    ledger.jsonl is the audit trail; this live marker gives the next step gate a
    cheap active-run signal. The marker is intentionally run-level, not
    current_step-level, because boundary BLOCK means the workspace needs explicit
    main/user intervention before any further sub-step can be trusted.
    """
    if not isinstance(category, str) or not category:
        raise ValueError("category must be non-empty str")
    live = read_live(session_id, base_dir=base_dir) or {}
    active = live.get("active_runs", {})
    if not isinstance(active, dict) or run_id not in active:
        raise ValueError(f"run_id not active: {run_id}")

    marker: Dict[str, Any] = {"category": category, "at": _now_iso()}
    for key, val in (
        ("agent", agent),
        ("mode", mode),
        ("provider", provider),
        ("reason", reason),
        ("raw_log", raw_log),
    ):
        if val is not None:
            marker[key] = val

    slot = dict(active[run_id])
    slot["blocked"] = marker
    slot["last_confirmed_at"] = marker["at"]
    active = dict(active)
    active[run_id] = slot
    update_live(session_id, base_dir=base_dir, active_runs=active)
    return marker


def _steps_jsonl_path(sid: str, rid: str, *, base_dir: Optional[Path] = None) -> Path:
    """[deprecated] 옛 `.steps.jsonl` 경로 — ledger.jsonl 로 흡수됨 (이슈 #587).

    `ledger.legacy_steps_path` 위임 (마이그레이션 폴백 참조 전용). 새 코드는
    `harness.ledger` 모듈을 직접 쓴다.
    """
    from harness import ledger

    return ledger.legacy_steps_path(sid, rid, base_dir=base_dir)


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


def _run_prose_has_pass(rd: Path, agent: str) -> bool:
    return run_prose_has_pass(rd, agent)


def _run_has_engineer_output(rd: Path) -> bool:
    """engineer 계열 prose 산출물 실존 여부."""
    if (rd / "engineer.md").exists():
        return True
    try:
        return any(rd.glob("engineer-*.md"))
    except OSError:
        return False


def _run_has_module_architect_pass(rd: Path) -> bool:
    """module-architect prose PASS — end-step 파일명 표기 전체 인정."""
    return run_prose_has_pass(rd, "module-architect")


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


def _project_root_from_design_doc(doc: Path) -> Optional[Path]:
    """`.../docs/...` 설계 산출물 경로에서 프로젝트 루트를 복원한다."""
    try:
        resolved = doc.resolve()
    except (OSError, RuntimeError):
        resolved = doc
    parts = resolved.parts
    for idx in range(len(parts) - 1, 0, -1):
        if parts[idx] == "docs":
            return Path(*parts[:idx])
    return None


def _is_dcness_self_project(project_root: Path) -> bool:
    manifest = project_root / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and data.get("name") == "dcness"


def _impl_run_project_root(
    session_id: str,
    run_id: str,
    *,
    base_dir: Optional[Path] = None,
) -> Path:
    doc = _run_design_doc_path(session_id, run_id, base_dir=base_dir)
    if doc is not None:
        root = _project_root_from_design_doc(doc)
        if root is not None:
            return root
    return Path.cwd().resolve()


def _impl_plan_boundary_preflight_message(
    session_id: str,
    run_id: str,
    *,
    base_dir: Optional[Path] = None,
) -> Optional[str]:
    doc = _run_design_doc_path(session_id, run_id, base_dir=base_dir)
    if doc is None or not doc.is_file():
        return None
    project_root = _project_root_from_design_doc(doc)
    if project_root is None:
        return None

    try:
        from harness.boundary_suggestions import (
            collect_boundary_suggestions,
            format_boundary_suggestions,
        )

        report = collect_boundary_suggestions(project_root, impl_plan=doc)
    except Exception as exc:
        return (
            "[순서 차단 훅: impl pre-flight boundary] impl 계획의 `### 수정 허용` "
            f"boundary 대조 실패: {exc}. 계획 scope 를 확인한 뒤 재시도하세요."
        )
    if not report.suggestions and not report.blocking_reasons:
        return None
    return (
        "[순서 차단 훅: impl pre-flight boundary] impl 계획의 `### 수정 허용` "
        "경로 중 build-worker boundary 로 커버되지 않거나 차단되는 항목이 "
        "있습니다. ALLOW_MATRIX 미커버 경로는 사람 승인 후 `.dcness/boundary.json` "
        "build-worker.add override 를 기록하고, INFRA/docs 등 되돌릴 수 없는 deny 경로는 "
        "계획 scope 를 수정하기 전까지 구현 step 을 시작할 수 없습니다.\n"
        f"{format_boundary_suggestions(report)}"
    )


def _generated_tdd_preflight_message(project_root: Path) -> Optional[str]:
    if _is_dcness_self_project(project_root):
        return None
    try:
        from harness.tdd_hooks import inspect_installation

        report = inspect_installation(project_root)
    except Exception as exc:
        return (
            "[순서 차단 훅: impl pre-flight TDD] generated TDD hook 상태 확인 실패: "
            f"{exc}. `scripts/dcness-tdd-hooks status --project-root <project>` 로 "
            "상태를 확인하세요."
        )

    platform = report.get("platform")
    if not platform:
        return None

    cc_registered = bool(report.get("cc_registered"))
    codex_registered = bool(report.get("codex_registered"))
    committed = bool(report.get("generated_files_committed"))
    commit_required = bool(report.get("generated_files_commit_required"))
    linked_worktree = bool(report.get("linked_worktree"))
    if cc_registered and codex_registered and (committed or not commit_required):
        return None

    uncommitted = report.get("uncommitted_generated_files") or []
    detail = ""
    if isinstance(uncommitted, list) and uncommitted:
        detail = f", uncommitted={', '.join(str(item) for item in uncommitted[:5])}"
    recovery = (
        "사람 승인 후 `scripts/dcness-tdd-hooks ensure --project-root <project> "
        "--targets cc,codex --plugin-root <plugin-root>` 를 실행하세요."
    )
    if commit_required:
        recovery = (
            "사람 승인 후 `scripts/dcness-tdd-hooks ensure --project-root <project> "
            "--targets cc,codex --plugin-root <plugin-root>` 를 실행하고 생성 파일을 "
            "linked worktree/headless 재사용 가능하도록 bootstrap commit 에 포함하세요."
        )
    return (
        "[순서 차단 훅: impl pre-flight TDD] generated TDD hook 이 구현 진입 전 "
        "준비되지 않았습니다. "
        f"platform={platform}, cc={cc_registered}, codex={codex_registered}, "
        f"generated_files_committed={committed}, linked_worktree={linked_worktree}, "
        f"generated_files_commit_required={commit_required}{detail}. "
        f"{recovery}"
    )


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


def _run_engineer_boundary_block_marker(
    session_id: str,
    run_id: str,
    *,
    base_dir: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    try:
        marker = _slot_for_run(session_id, run_id, base_dir=base_dir).get("blocked")
        if isinstance(marker, dict) and marker.get("category") == "engineer_boundary":
            return marker
    except (OSError, ValueError):
        pass

    try:
        from harness import ledger

        for event in reversed(ledger.read_events(session_id, run_id, base_dir=base_dir)):
            if (
                event.get("event") == "blocked"
                and event.get("category") == "engineer_boundary"
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
        "headless worker boundary BLOCK(category=engineer_boundary) 기록이 있어 "
        "다음 step 을 시작할 수 없습니다. workspace diff 와 ledger marker 를 확인한 뒤 "
        "새 run 또는 명시적 수동 복구로 진행하세요."
        f"{detail}"
    )


_IMPLEMENTATION_ORDER_GATE_AGENTS = frozenset({"engineer", "build-worker"})


def evaluate_order_gate_for_step(
    session_id: str,
    run_id: str,
    agent: str,
    mode: Optional[str] = None,
    *,
    base_dir: Optional[Path] = None,
) -> Optional[str]:
    """provider-independent step start order gate.

    Claude Agent 경로는 PreToolUse hook 에서, Codex/headless 경로는 helper
    `begin-step` 에서 같은 불변식을 평가한다. 반환값이 있으면 차단 메시지다.
    """
    from harness.agent_names import normalize_agent_type

    norm_agent = normalize_agent_type(agent) or agent
    effective_mode = mode if isinstance(mode, str) and mode else None
    rd = run_dir(session_id, run_id, base_dir=base_dir)

    boundary_block = _run_engineer_boundary_block_marker(
        session_id, run_id, base_dir=base_dir
    )
    if boundary_block:
        return _boundary_block_gate_message(boundary_block)

    if norm_agent in _IMPLEMENTATION_ORDER_GATE_AGENTS and effective_mode != "POLISH":
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
                "PASS 마커) 또는 begin-run --design-doc 으로 기록된 설계 문서 실존. "
                "충족 방법: module-architect step 을 PASS 로 완료하거나, 구현 run 을 "
                "시작할 때 `begin-run impl --design-doc <설계문서>` 를 기록하세요. "
                "명시적 direct 구현 경로라면 `begin-run impl --lane lite` 로 시작하세요."
            )
        boundary_message = _impl_plan_boundary_preflight_message(
            session_id, run_id, base_dir=base_dir,
        )
        if boundary_message:
            return boundary_message
        tdd_message = _generated_tdd_preflight_message(
            _impl_run_project_root(session_id, run_id, base_dir=base_dir)
        )
        if tdd_message:
            return tdd_message

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


def _repo_root_for_prompt_check(*, cwd: Optional[Path] = None) -> Path:
    """Return repo root for advisory prompt checks, falling back to cwd."""
    probe_cwd = Path(cwd or Path.cwd()).resolve()
    return _git_show_toplevel_cached(probe_cwd) or probe_cwd


def _confirmed_mockup_paths_for_prompt(*, cwd: Optional[Path] = None) -> tuple[str, ...]:
    """Find confirmed screen mockups for prompt-writing reminders.

    This is deliberately broad and advisory. It detects top-level confirmed screen
    HTML files under ``docs/design-variants/`` and ignores canvas/drafts seed files.
    """
    root = _repo_root_for_prompt_check(cwd=cwd)
    mockup_dir = root / _CONFIRMED_MOCKUP_DIR_REL
    if not mockup_dir.is_dir():
        return ()
    try:
        from harness.mockup_node_check import is_confirmed_mockup_html
    except Exception:  # nosec B110
        return ()
    paths: list[str] = []
    for path in sorted(mockup_dir.glob("*.html")):
        if not is_confirmed_mockup_html(path):
            continue
        try:
            paths.append(path.relative_to(root).as_posix())
        except ValueError:
            paths.append(str(path))
    return tuple(paths)


def _design_ssot_reminder_line(
    *,
    agent: Optional[str],
    cwd: Optional[Path] = None,
) -> Optional[str]:
    """Return a design SSOT advisory line for design agents when mockups exist."""
    if not agent:
        return None
    try:
        from harness.agent_names import normalize_agent_type

        agent_name = normalize_agent_type(agent) or agent
    except Exception:  # nosec B110
        agent_name = agent
    if agent_name not in _DESIGN_SSOT_REMINDER_AGENTS:
        return None
    mockups = _confirmed_mockup_paths_for_prompt(cwd=cwd)
    if not mockups:
        return None
    preview = ", ".join(f"`{path}`" for path in mockups[:3])
    if len(mockups) > 3:
        preview = f"{preview}, ..."
    return (
        "- design SSOT: 확정 목업 감지("
        f"{preview}). 확정 목업 존재 UI epic 이면 슬롯 1에 `docs/design.md`, "
        "확정 목업 파일, `docs/design-variants/canvas.html`, node-id 매핑 출처를 "
        "포함했는지 확인."
    )


def _prompt_slot_check_text(
    session_id: str,
    run_id: str,
    *,
    base_dir: Optional[Path] = None,
    cwd: Optional[Path] = None,
    agent: Optional[str] = None,
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
    lines = [
        "[PROMPT_SLOT_CHECK]",
        f"- template: `{template_path}`",
        "- 대상+읽을 진본: 이번 호출 단위와 agent 가 자체 read 할 SSOT 경로만 둔다.",
        worktree_line,
    ]
    design_line = _design_ssot_reminder_line(agent=agent, cwd=cwd)
    if design_line:
        lines.append(design_line)
    lines.append(
        "- 이 호출 특유: 진본에 없는 제약/신호만 둔다. 정규식·구현 단계·알고리즘·테스트 assert 방식 등 방법 처방 금지."
    )
    return "\n".join(lines)


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


# ── split-module compatibility re-exports ───────────────────────────
# Keep the historical ``harness.session_state`` import path stable while
# cohesive responsibilities live in smaller modules.
from harness.session_state_activation import (  # noqa: E402
    _resolve_project_root as _resolve_project_root,
    disable_project as disable_project,
    enable_project as enable_project,
    is_project_active as is_project_active,
    list_active_projects as list_active_projects,
    whitelist_path as whitelist_path,
)
from harness.session_state_fail_open import (  # noqa: E402
    collect_fail_open_summary as collect_fail_open_summary,
    fail_open_events_path as fail_open_events_path,
    format_fail_open_warning as format_fail_open_warning,
    read_fail_open_events as read_fail_open_events,
    record_fail_open_event as record_fail_open_event,
)


def _split_attr(module_name: str, name: str) -> Any:
    value = getattr(importlib.import_module(module_name), name)
    globals()[name] = value
    return value


def _extract_prose_summary(*args: Any, **kwargs: Any) -> Any:
    return _split_attr("harness.session_state_cli", "_extract_prose_summary")(
        *args, **kwargs
    )


def _has_positive_must_fix(*args: Any, **kwargs: Any) -> Any:
    return _split_attr("harness.session_state_cli", "_has_positive_must_fix")(
        *args, **kwargs
    )


def _count_step_occurrences(*args: Any, **kwargs: Any) -> Any:
    return _split_attr("harness.session_state_cli", "_count_step_occurrences")(
        *args, **kwargs
    )


def _cli_end_run(*args: Any, **kwargs: Any) -> Any:
    return _split_attr("harness.session_state_cli", "_cli_end_run")(*args, **kwargs)


def _main(argv: Optional[list] = None) -> int:
    return _split_attr("harness.session_state_cli", "_main")(argv)


_CLI_REEXPORT_NAMES = frozenset(
    {
        "_CONCLUSION_HEADER_RE",
        "_MUST_FIX_HEADER_ONLY_RE",
        "_MUST_FIX_NEGATION_RE",
        "_MUST_FIX_RE",
        "_NEXT_LINE_NEGATION_RE",
        "_YOLO_FALLBACKS",
        "_append_step_status",
        "_build_arg_parser",
        "_cli_auto_resolve",
        "_cli_begin_run",
        "_cli_begin_step",
        "_cli_boundary_suggestions",
        "_cli_chain_view",
        "_cli_design_records",
        "_cli_disable",
        "_cli_enable",
        "_cli_end_step",
        "_cli_finalize_run",
        "_cli_guard_telemetry",
        "_cli_hook_fail_open",
        "_cli_init_session",
        "_cli_insight",
        "_cli_is_active",
        "_cli_is_self",
        "_cli_ledger_event",
        "_cli_merge_lock",
        "_cli_mockup_node_check",
        "_cli_next_task",
        "_cli_normalize_scope",
        "_cli_post_task_begin",
        "_cli_prev_tasks_append",
        "_cli_prev_tasks_reset",
        "_cli_routing",
        "_cli_run_dir",
        "_cli_run_status",
        "_cli_status",
        "_cli_wave_claim",
        "_cli_wave_heartbeat",
        "_cli_wave_plan",
        "_cli_wave_reclaim",
        "_cli_wave_release",
        "_cli_wave_status",
        "_current_branch_fallback",
        "_current_merge_lock",
        "_current_wave_board",
        "_extract_section_after_header",
        "_find_prose_fallback",
        "_json_stdout",
        "_latest_step_per_role",
        "_merge_order_base_ref",
        "_prior_engineer_tool_use_count",
        "_record_design_run_if_applicable",
        "_repo_root_from_state_root",
    }
)


def __getattr__(name: str) -> Any:
    if name in _CLI_REEXPORT_NAMES:
        return _split_attr("harness.session_state_cli", name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _reexport(module_name: str, names: tuple[str, ...]) -> None:
    module = importlib.import_module(module_name)
    for name in names:
        globals()[name] = getattr(module, name)


_reexport(
    "harness.session_state_activation",
    (
        "_DEFAULT_WHITELIST_PATH",
        "_load_whitelist",
        "_resolve_project_root",
        "_save_whitelist",
        "disable_project",
        "enable_project",
        "is_project_active",
        "list_active_projects",
        "whitelist_path",
    ),
)
_reexport(
    "harness.session_state_fail_open",
    (
        "_format_fail_open_summary",
        "_parse_fail_open_ts",
        "_utc_now_iso",
        "collect_fail_open_summary",
        "fail_open_events_path",
        "format_fail_open_warning",
        "read_fail_open_events",
        "record_fail_open_event",
    ),
)
_reexport(
    "harness.session_state_status",
    (
        "_CODEX_VALIDATOR_SKILLS",
        "_CI_WORKFLOWS",
        "_GIT_HOOK_SHIMS",
        "_READ_PERM",
        "_SHIM_MARKERS",
        "_check_ci_workflows",
        "_check_codex_validator_skills",
        "_check_gh_auth",
        "_check_git_hooks",
        "_check_read_permission",
        "_installed_plugin_version",
        "_is_self_repo",
        "_plugin_root",
        "_resolve_git_hooks_dir",
        "_settings_path",
        "collect_status_diagnostics",
        "format_status_report",
    ),
)
if __name__ == "__main__":
    sys.exit(_main())

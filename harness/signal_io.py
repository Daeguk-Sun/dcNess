"""signal_io.py — agent prose 저장 단일 책임 모듈.

발상 (status-json-mutate-pattern.md §2):
    "agent 는 prose 자유롭게 emit. 형식 강제 0, flag 0, schema 0."

prose-only routing (이슈 #280/#284) 정착 후: agent 결론은 메인 Claude 가 prose
자체를 직접 읽고 판단한다. 따라서 본 모듈은 prose 파일 I/O 만 담당하며, 옛
enum 기계 추출 (`interpret_signal` 휴리스틱) 은 폐기됐다.

본 모듈은 RWHarness 의 `parse_marker` (regex + alias 사다리) + dcNess 의
이전 `state_io.py` (status JSON schema 강제) 를 모두 대체한다.

핵심 API:
    signal_path(agent, run_id, mode=None, base_dir=None) -> Path
    write_prose(agent, run_id, prose, mode=None, base_dir=None) -> Path
    read_prose(agent, run_id, mode=None, base_dir=None) -> str
    clear_run_state(run_id, base_dir=None) -> int

§4.2 폐기 항목 정합:
    - status JSON schema 강제 → prose .md 파일 (메인 Claude 직접 해석)
    - MissingStatus 5 reasons → MissingSignal 2 reasons (not_found/empty)
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

__all__ = [
    "MissingSignal",
    "signal_path",
    "write_prose",
    "read_prose",
    "clear_run_state",
    "DEFAULT_BASE",
]

_AGENT_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_MODE_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _default_base() -> Path:
    return Path.cwd() / ".claude" / "harness-state"


class _DefaultBaseProxy:
    def __fspath__(self) -> str:
        return str(_default_base())

    def __str__(self) -> str:
        return str(_default_base())

    def __repr__(self) -> str:
        return f"<DEFAULT_BASE → {_default_base()}>"

    def resolve(self) -> Path:
        return _default_base().resolve()


DEFAULT_BASE = _DefaultBaseProxy()


class MissingSignal(Exception):
    """prose 읽기 실패의 단일 normalize 예외.

    Attributes:
        reason: REASONS 중 하나.
        detail: 디버깅용 상세 메시지.
    """

    REASONS = (
        "not_found",
        "empty",
    )

    def __init__(self, reason: str, detail: str = "") -> None:
        if reason not in self.REASONS:
            raise ValueError(
                f"unknown MissingSignal reason: {reason!r} "
                f"(allowed: {self.REASONS})"
            )
        self.reason = reason
        self.detail = detail
        super().__init__(f"[{reason}] {detail}")


def _validate_agent(agent: str) -> None:
    if not isinstance(agent, str) or not _AGENT_NAME_RE.match(agent):
        raise ValueError(
            f"invalid agent name: {agent!r} "
            f"(must match {_AGENT_NAME_RE.pattern})"
        )


def _validate_mode(mode: Optional[str]) -> None:
    if mode is None:
        return
    if not isinstance(mode, str) or not _MODE_NAME_RE.match(mode):
        raise ValueError(
            f"invalid mode name: {mode!r} "
            f"(must match {_MODE_NAME_RE.pattern} or be None)"
        )


def _validate_run_id(run_id: str) -> None:
    if (
        not isinstance(run_id, str)
        or not _RUN_ID_RE.match(run_id)
        or ".." in run_id
    ):
        raise ValueError(
            f"invalid run_id: {run_id!r} "
            f"(must match {_RUN_ID_RE.pattern} and not contain '..')"
        )


def _resolve_base(base_dir: Optional[Path]) -> Path:
    if base_dir is None:
        return _default_base().resolve()
    if not isinstance(base_dir, (str, Path)):
        raise TypeError(f"base_dir must be Path or str, got {type(base_dir)!r}")
    return Path(base_dir).resolve()


def signal_path(
    agent: str,
    run_id: str,
    mode: Optional[str] = None,
    base_dir: Optional[Path] = None,
    *,
    occurrence: int = 0,
) -> Path:
    """prose 파일의 절대 경로 반환.

    경로 규칙: <base_dir>/<run_id>/<agent>[-<mode>][-<N>].md
      N=0 (기본): <agent>[-<mode>].md
      N>0       : <agent>[-<mode>]-<N>.md  (같은 step 반복 시 충돌 방지)

    화이트리스트 + path traversal 자기검증.
    """
    _validate_agent(agent)
    _validate_mode(mode)
    _validate_run_id(run_id)

    base = _resolve_base(base_dir)
    stem = f"{agent}-{mode}" if mode else agent
    name = f"{stem}-{occurrence}.md" if occurrence > 0 else f"{stem}.md"
    target = (base / run_id / name).resolve()

    try:
        target.relative_to(base)
    except ValueError as e:
        raise ValueError(
            f"path escape detected: {target} not under {base}"
        ) from e
    return target


def write_prose(
    agent: str,
    run_id: str,
    prose: str,
    *,
    mode: Optional[str] = None,
    base_dir: Optional[Path] = None,
    occurrence: int = 0,
) -> Path:
    """prose 작성. 형식 강제 없음. atomic rename 으로 race 회피.

    occurrence > 0 이면 <agent>[-mode]-<N>.md 로 저장 (같은 step 반복 충돌 방지).

    Returns: 작성된 파일의 절대 경로.

    Raises:
        TypeError: prose 가 str 아님.
        ValueError: 화이트리스트 위반.
        OSError: 디스크 I/O 실패.
    """
    if not isinstance(prose, str):
        raise TypeError(f"prose must be str, got {type(prose).__name__}")

    target = signal_path(agent, run_id, mode, base_dir, occurrence=occurrence)
    target.parent.mkdir(parents=True, exist_ok=True)

    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(prose, encoding="utf-8")
    os.replace(tmp, target)  # POSIX atomic rename
    return target


def read_prose(
    agent: str,
    run_id: str,
    *,
    mode: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> str:
    """prose 읽기. 미존재/빈 파일은 MissingSignal.

    Raises:
        MissingSignal(not_found): 파일 없음
        MissingSignal(empty): 빈 파일
    """
    target = signal_path(agent, run_id, mode, base_dir)

    if not target.exists():
        raise MissingSignal("not_found", str(target))

    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as e:
        raise MissingSignal("not_found", f"{target}: {e}") from e

    if not raw.strip():
        raise MissingSignal("empty", str(target))

    return raw


def clear_run_state(
    run_id: str,
    *,
    base_dir: Optional[Path] = None,
) -> int:
    """run 디렉토리 안의 *.md prose 파일 삭제.

    catastrophic 회피: base_dir/run_id 안만. 그 외 path 거부.

    Returns: 삭제된 파일 수.

    Raises:
        ValueError: run_id 화이트리스트 위반 / path traversal.
    """
    _validate_run_id(run_id)

    base = _resolve_base(base_dir)
    run_dir = (base / run_id).resolve()
    try:
        run_dir.relative_to(base)
    except ValueError as e:
        raise ValueError(f"path escape: {run_dir} not under {base}") from e

    if not run_dir.exists():
        return 0

    count = 0
    for f in run_dir.glob("*.md"):
        try:
            f.unlink()
            count += 1
        except OSError:
            pass
    return count

"""prev_tasks — /impl-loop chain 안에서 직전 완료 task 산출 요약 누적 (#525).

youTubeGenerator 자작 Codex executor 의 `_build_previous_context` (완료 step
summary 를 다음 step prompt 에 주입) 패턴 이식. build-worker 가 phase 3 종료 시
자기 산출 한 줄을 append → 다음 task 진입 시 메인의 `begin-step build-worker`
가 `[PREVIOUS_TASKS]` 로 emit → 메인이 build-worker prompt 에 포함. task 간
인터페이스 misalign 을 실행 시점에 저렴하게 완화한다.

저장 위치: <main_repo_root>/.claude/loop-insights/.prev-tasks.md
(`loop_insights` 와 같은 디렉토리, dot-prefix 로 구분). worktree 진입 후에도
main repo root 기준 — `_resolve_project_root` γ-resolution 재사용 (loop_insights
동일 패턴). git 미설치 / 리포 아님 시 cwd 폴백.

생명주기: append + FIFO cap. chain 시작 시 `reset()` 권장 (impl-loop skill 진입).
reset 을 까먹어도 FIFO cap 으로 이전 chain 잔재가 자연 제거된다 (안전망).
같은 slug 재append (재시도) 시 직전 항목 제거 후 최신만 보존.
"""
from __future__ import annotations

from pathlib import Path

from harness.session_state import _resolve_project_root


__all__ = ["prev_tasks_path", "read", "append", "reset", "PREV_TASKS_FIFO_CAP"]

_PREV_TASKS_FILE = Path(".claude") / "loop-insights" / ".prev-tasks.md"

# loop_insights 와 동일 컨벤션 — 직전 최대 N task 만 emit (컨텍스트 폭증 차단).
PREV_TASKS_FIFO_CAP = 10


def _normalize_cwd(cwd: Path) -> Path:
    """cwd 를 main repo root 로 정규화. worktree 안이면 main repo root 반환."""
    try:
        return _resolve_project_root(Path(cwd).resolve()).resolve()
    except OSError:
        return Path(cwd).resolve()


def prev_tasks_path(cwd: Path = Path(".")) -> Path:
    return _normalize_cwd(cwd) / _PREV_TASKS_FILE


def read(cwd: Path = Path(".")) -> str:
    """누적된 직전 task 요약 목록 stdout 용. 없으면 빈 문자열."""
    p = prev_tasks_path(cwd)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8").strip()


def append(
    slug: str,
    summary: str,
    cwd: Path = Path("."),
    fifo_cap: int = PREV_TASKS_FIFO_CAP,
) -> Path:
    """task 산출 요약 한 줄 append. 빈 slug/summary 면 noop.

    Args:
        slug: task slug (예: `05-revival-button`).
        summary: 산출 요약. multiline 들어와도 첫 줄만 보존.
        cwd: main repo root (worktree 자동 정규화).
        fifo_cap: 최대 항목 수 (default PREV_TASKS_FIFO_CAP=10).

    매커니즘:
        - slug 또는 summary 비면 noop (파일 미생성).
        - 같은 slug 기존 항목 제거 후 최신 append (재시도 시 중복 회피).
        - cap 초과 시 가장 오래된 항목 FIFO 제거.
    """
    slug = (slug or "").strip()
    lines = (summary or "").strip().splitlines()
    one_line = lines[0].strip() if lines else ""

    p = prev_tasks_path(cwd)
    if not slug or not one_line:
        return p

    p.parent.mkdir(parents=True, exist_ok=True)
    new_entry = f"- {slug}: {one_line}"

    entries: list[str] = []
    if p.exists():
        entries = [
            line for line in p.read_text(encoding="utf-8").splitlines()
            if line.startswith("- ")
        ]
    # 같은 slug 직전 항목 제거 — 재시도/재append 시 최신만
    prefix = f"- {slug}: "
    entries = [e for e in entries if not e.startswith(prefix)]
    entries.append(new_entry)
    while len(entries) > fifo_cap:
        entries.pop(0)

    p.write_text("\n".join(entries) + "\n", encoding="utf-8")
    return p


def reset(cwd: Path = Path(".")) -> None:
    """chain 시작 시 누적 초기화 (impl-loop skill 진입 1회 권장)."""
    p = prev_tasks_path(cwd)
    if p.exists():
        p.unlink()

"""loop_insights — 루프별 agent 학습 누적 (DCN-CHG-20260502-02).

issue #392 — 자동 누적 매커니즘 폐기. redo_log + WASTE/GOOD auto 누적 → 100% baseline
노이즈 (사용자 분노). 메인 자율 평가는 insight CLI (PR3) 로 대체.

본 모듈의 책무:
- `append_findings` (저수준): 본문 directly append. 외부 호출용 (PR3 insight CLI).
- `read`: begin-step 시 inject 읽기.
- `insights_path`: 파일 경로 계산.

저장 위치: <main_repo_root>/.claude/loop-insights/<agent>[-<mode>].md

worktree 진입 후에도 main repo root 기준으로 저장 — ExitWorktree(remove)
시 누적분 손실 회피 (#306 개선점 5). main repo root 해석은
`_resolve_project_root` (`session_state.py`) 의 git common-dir γ-resolution
재사용. git 미설치 / 리포 아님 시 cwd 폴백.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from harness.session_state import _resolve_project_root


__all__ = ["insights_path", "read", "append_findings", "append_insight", "INSIGHT_FIFO_CAP"]

_INSIGHTS_DIR = Path(".claude") / "loop-insights"

# issue #396 — agent+mode 별 인사이트 FIFO cap. 컨텍스트 폭증 차단.
# 100 run 돌려도 각 파일 ≤ 10줄 유지. 200 tokens / agent inject (sustainable).
INSIGHT_FIFO_CAP = 10


def _normalize_cwd(cwd: Path) -> Path:
    """cwd 를 main repo root 로 정규화 (#306 개선점 5).

    worktree 안 cwd 면 main repo root 반환. git 미사용 환경 폴백 시 cwd 자체.
    """
    try:
        return _resolve_project_root(Path(cwd).resolve()).resolve()
    except OSError:
        return Path(cwd).resolve()


def insights_path(
    agent: str, mode: Optional[str] = None, cwd: Path = Path(".")
) -> Path:
    name = agent if not mode else f"{agent}-{mode}"
    return _normalize_cwd(cwd) / _INSIGHTS_DIR / f"{name}.md"


def read(
    agent: str, mode: Optional[str] = None, cwd: Path = Path(".")
) -> str:
    p = insights_path(agent, mode, cwd)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8").strip()


def append_findings(
    agent: str,
    mode: Optional[str],
    bads: list[str],
    goods: list[str],
    cwd: Path = Path("."),
    date_str: Optional[str] = None,
) -> None:
    """bads/goods 항목을 agent 파일에 append. 이미 존재하는 항목은 스킵."""
    if not bads and not goods:
        return

    p = insights_path(agent, mode, cwd)
    p.parent.mkdir(parents=True, exist_ok=True)

    existing = p.read_text(encoding="utf-8") if p.exists() else ""

    header = f"# Loop Insights: {agent}" + (f" / {mode}" if mode else "") + "\n"
    if not existing:
        existing = header + "\n## 하지 말 것\n\n## 잘 됐던 것\n"

    lines_to_add: list[tuple[str, str]] = []  # (section, item)
    for item in bads:
        if item not in existing:
            lines_to_add.append(("하지 말 것", item))
    for item in goods:
        if item not in existing:
            lines_to_add.append(("잘 됐던 것", item))

    if not lines_to_add:
        return

    result = existing
    for section, item in lines_to_add:
        marker = f"## {section}"
        if marker in result:
            idx = result.index(marker) + len(marker)
            # 다음 ## 또는 끝 전에 삽입
            next_h = result.find("\n## ", idx)
            insert_at = next_h if next_h != -1 else len(result)
            result = result[:insert_at].rstrip() + f"\n- {item}\n" + result[insert_at:]
        else:
            result = result.rstrip() + f"\n\n## {section}\n- {item}\n"

    p.write_text(result, encoding="utf-8")


# issue #392 — `append_from_run` 폐기. PR3 의 `insight` CLI 로 대체.


def append_insight(
    agent: str,
    mode: Optional[str],
    text: str,
    cwd: Path = Path("."),
    fifo_cap: int = INSIGHT_FIFO_CAP,
) -> Path:
    """issue #396 — 메인 자율 인사이트 1줄 append. FIFO cap (가장 오래된 자동 제거).

    Args:
        agent: subagent_type (engineer / code-validator / ...)
        mode: optional mode (IMPL / POLISH / CODE_VALIDATION / ...)
        text: 자연어 한 줄. 줄바꿈 strip, 빈 텍스트면 noop.
        cwd: main repo root (worktree 자동 정규화).
        fifo_cap: 최대 줄 수 (default INSIGHT_FIFO_CAP=10).

    Returns:
        insights_path (변경된 파일).

    매커니즘:
        - text 1줄로 strip (multiline 들어와도 첫 줄만 보존, 공백 trim)
        - 빈 text → noop, 파일 미생성
        - 신규 파일: header + insight 1줄
        - 기존 파일: append + cap 초과 시 가장 오래된 줄 제거 (FIFO)
    """
    import time

    text_lines = (text or "").strip().splitlines()
    one_line = text_lines[0].strip() if text_lines else ""
    if not one_line:
        return insights_path(agent, mode, cwd)

    p = insights_path(agent, mode, cwd)
    p.parent.mkdir(parents=True, exist_ok=True)
    today = time.strftime("%Y-%m-%d", time.gmtime())
    new_entry = f"- {one_line} ({today})"

    if not p.exists():
        header = f"# Loop Insights: {agent}" + (f" / {mode}" if mode else "")
        body = f"{header}\n\n## 인사이트 (최신 {fifo_cap}개, FIFO)\n\n{new_entry}\n"
        p.write_text(body, encoding="utf-8")
        return p

    existing = p.read_text(encoding="utf-8")
    lines = existing.splitlines()

    # 본문에서 "- " 시작 줄만 entry 로 카운트
    entries = [line for line in lines if line.startswith("- ")]
    non_entries = [line for line in lines if not line.startswith("- ")]

    entries.append(new_entry)
    # cap 초과 시 FIFO (가장 오래된 = 앞부터 제거)
    while len(entries) > fifo_cap:
        entries.pop(0)

    # 본문 재구성: header / heading 보존 + entries
    # 단순화 — non_entries 다음에 entries 씀
    header_part = "\n".join(non_entries).rstrip() + "\n\n" if non_entries else ""
    body = header_part + "\n".join(entries) + "\n"
    p.write_text(body, encoding="utf-8")
    return p

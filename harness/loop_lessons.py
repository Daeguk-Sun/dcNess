"""Project-local recurrent waste lessons (#917).

Lessons are deterministic, project-local memory entries created from recurrent
``run_review`` WasteFinding signals. They intentionally do not consume
NoteFinding rows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from harness.session_state import _resolve_project_root


LESSONS_DIR = Path(".claude") / "loop-lessons"
LESSON_FILE_MARKER = "<!-- dcness-loop-lessons:v1 -->"
MAX_EVIDENCE_ITEMS = 10

LESSON_TEMPLATES: dict[str, str] = {
    "RETRY_SAME_FAIL": (
        "같은 실패 결론을 반복했다. 다음 호출은 같은 접근 재시도가 아니라 실패 원인 "
        "확인과 다른 해결 전략부터 시작한다."
    ),
    "MISSING_CONCLUSION_ENUM": (
        "engineer prose 마지막 단락에 요구된 결론 enum 을 명시한다. 메인은 enum 부재를 "
        "routing 신호로 쓰지 않는다."
    ),
    "STRAY_DIR_LEAK": (
        "인프라 디렉터리명 typo 또는 유사 경로를 추측하지 않는다. 실제 경로를 확인한 뒤 "
        "한 번만 접근한다."
    ),
    "MUST_FIX_GHOST": (
        "게이트 agent 가 미해결 MUST FIX 를 남겼으면 PASS/LGTM 으로 진행하지 않는다. "
        "메인은 blocker 를 해결하거나 FAIL 흐름으로 되돌린다."
    ),
    "MUST_FIX_LEAK": (
        "마지막 step 에 positive MUST FIX 가 남으면 종료하지 않고 caveat 를 사용자에게 "
        "드러낸 뒤 다음 행동을 분리한다."
    ),
    "SPEC_GAP_LOOP": (
        "SPEC_GAP 보강이 반복되면 같은 보강 호출을 계속하지 말고 설계 입력 자체를 "
        "재정리하거나 상위 설계로 되돌린다."
    ),
    "INFRA_READ": (
        "agent 는 harness-state, harness log, plugin infra 경로를 읽지 않는다. 필요한 "
        "상태는 메인이 요약해서 전달한다."
    ),
    "READONLY_BASH": (
        "read-only agent 는 Bash 를 쓰지 않는다. 필요한 실측 명령은 메인 또는 write 권한 "
        "agent 에게 넘긴다."
    ),
    "END_STEP_SKIP": (
        "Agent 호출 직후 같은 흐름에서 end-step 을 닫는다. 메인은 PR/검증 작업으로 "
        "분기하기 전에 ledger 기록을 먼저 완료한다."
    ),
    "TOOL_REPEAT_HIGH": (
        "같은 tool/input 반복 호출을 멈추고 첫 결과를 재사용한다. 재확인은 grep, offset, "
        "더 좁은 입력으로 수행한다."
    ),
}


@dataclass
class LessonEntry:
    pattern: str
    status: str = "active"
    hits: int = 0
    last: str = ""
    lesson: str = ""
    evidence: list[str] = field(default_factory=list)


def _normalize_cwd(cwd: Path) -> Path:
    try:
        return _resolve_project_root(Path(cwd).resolve()).resolve()
    except OSError:
        return Path(cwd).resolve()


def lessons_path(agent: str, mode: Optional[str] = None, cwd: Path = Path(".")) -> Path:
    name = agent if not mode else f"{agent}-{mode}"
    return _normalize_cwd(cwd) / LESSONS_DIR / f"{name}.md"


def _header(agent: str, mode: Optional[str]) -> str:
    return f"# Loop Lessons: {agent}" + (f" / {mode}" if mode else "")


def _template(pattern: str) -> str:
    return LESSON_TEMPLATES.get(
        pattern,
        f"{pattern} 재발이 확인됐다. 같은 패턴을 반복하지 않도록 직전 evidence 를 먼저 확인한다.",
    )


def _parse_entries(text: str) -> dict[str, LessonEntry]:
    entries: dict[str, LessonEntry] = {}
    current: Optional[LessonEntry] = None
    for line in text.splitlines():
        if line.startswith("### "):
            pattern = line[4:].strip()
            current = LessonEntry(pattern=pattern, lesson=_template(pattern))
            entries[pattern] = current
            continue
        if current is None:
            continue
        if line.startswith("- status:"):
            current.status = line.split(":", 1)[1].strip() or "active"
        elif line.startswith("- hits:"):
            raw = line.split(":", 1)[1].strip()
            try:
                current.hits = int(raw)
            except ValueError:
                current.hits = 0
        elif line.startswith("- last:"):
            current.last = line.split(":", 1)[1].strip()
        elif line.startswith("- lesson:"):
            current.lesson = line.split(":", 1)[1].strip() or _template(current.pattern)
        elif line.startswith("  - "):
            evidence = line[4:].strip()
            if evidence and evidence not in current.evidence:
                current.evidence.append(evidence)
    return entries


def _render_entries(agent: str, mode: Optional[str], entries: dict[str, LessonEntry]) -> str:
    lines: list[str] = [
        _header(agent, mode),
        "",
        LESSON_FILE_MARKER,
        "",
        "## Active",
        "",
    ]

    def emit(entry: LessonEntry) -> None:
        lines.append(f"### {entry.pattern}")
        lines.append(f"- status: {entry.status}")
        lines.append(f"- hits: {entry.hits}")
        lines.append(f"- last: {entry.last}")
        lines.append(f"- lesson: {entry.lesson or _template(entry.pattern)}")
        lines.append("- evidence:")
        for evidence in entry.evidence:
            lines.append(f"  - {evidence}")
        lines.append("")

    active = [e for e in entries.values() if e.status == "active"]
    archived = [e for e in entries.values() if e.status == "archived"]
    for entry in sorted(active, key=lambda e: e.pattern):
        emit(entry)

    lines.append("## Archived")
    lines.append("")
    for entry in sorted(archived, key=lambda e: e.pattern):
        emit(entry)
    return "\n".join(lines).rstrip() + "\n"


def _read_entries(path: Path) -> dict[str, LessonEntry]:
    if not path.exists():
        return {}
    try:
        return _parse_entries(path.read_text(encoding="utf-8"))
    except OSError:
        return {}


def _infer_agent_mode(path: Path) -> tuple[str, Optional[str]]:
    stem = path.stem
    if "-" not in stem:
        return stem, None
    agent, mode = stem.rsplit("-", 1)
    # Modes are conventionally uppercase labels such as IMPL, POLISH, or
    # CODE_VALIDATION. Lowercase suffixes are part of hyphenated agent names.
    if mode and mode == mode.upper() and any(ch.isalpha() for ch in mode):
        return agent, mode
    return stem, None


def _write_entries(path: Path, entries: dict[str, LessonEntry]) -> None:
    agent, mode = _infer_agent_mode(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_entries(agent, mode, entries), encoding="utf-8")


def upsert_entry(
    agent: str,
    mode: Optional[str],
    pattern: str,
    *,
    hits: int,
    last: str,
    evidence: list[str],
    cwd: Path = Path("."),
) -> Path:
    path = lessons_path(agent, mode, cwd)
    entries = _read_entries(path)
    entry = entries.get(pattern) or LessonEntry(pattern=pattern, lesson=_template(pattern))
    entry.status = "active"
    entry.hits = max(int(hits), entry.hits)
    entry.last = last or entry.last
    entry.lesson = entry.lesson or _template(pattern)
    for item in evidence:
        if item and item not in entry.evidence:
            entry.evidence.append(item)
    entry.evidence = entry.evidence[-MAX_EVIDENCE_ITEMS:]
    entries[pattern] = entry
    _write_entries(path, entries)
    return path


def archive_removed_patterns(path: Path, *, active_patterns: set[str]) -> bool:
    entries = _read_entries(path)
    changed = False
    for entry in entries.values():
        if entry.status == "active" and entry.pattern not in active_patterns:
            entry.status = "archived"
            changed = True
    if changed:
        _write_entries(path, entries)
    return changed


def _active_patterns_default() -> set[str]:
    try:
        from harness.run_review import ACTIVE_WASTE_PATTERNS

        return set(ACTIVE_WASTE_PATTERNS)
    except Exception:
        return set(LESSON_TEMPLATES)


def read(
    agent: str,
    mode: Optional[str] = None,
    cwd: Path = Path("."),
    *,
    active_patterns: Optional[set[str]] = None,
) -> str:
    path = lessons_path(agent, mode, cwd)
    if not path.exists():
        return ""
    active = active_patterns if active_patterns is not None else _active_patterns_default()
    archive_removed_patterns(path, active_patterns=active)
    entries = _read_entries(path)
    lines: list[str] = []
    for entry in sorted(entries.values(), key=lambda e: e.pattern):
        if entry.status != "active" or entry.pattern not in active:
            continue
        evidence = entry.evidence[-1] if entry.evidence else "-"
        lines.append(
            f"- `{entry.pattern}`: {entry.lesson or _template(entry.pattern)} "
            f"(hits={entry.hits}, last={entry.last or '-'}, evidence={evidence})"
        )
    return "\n".join(lines)


def list_active_lessons(
    cwd: Path = Path("."),
    *,
    active_patterns: Optional[set[str]] = None,
) -> list[dict[str, object]]:
    root = _normalize_cwd(cwd)
    base = root / LESSONS_DIR
    if not base.exists():
        return []
    active = active_patterns if active_patterns is not None else _active_patterns_default()
    rows: list[dict[str, object]] = []
    for path in sorted(base.glob("*.md")):
        archive_removed_patterns(path, active_patterns=active)
        agent, mode = _infer_agent_mode(path)
        for entry in _read_entries(path).values():
            if entry.status != "active" or entry.pattern not in active:
                continue
            rows.append({
                "agent": agent,
                "mode": mode,
                "pattern": entry.pattern,
                "hits": entry.hits,
                "last": entry.last,
                "path": str(path),
            })
    return rows


def _sessions_root_for_run(run_dir: Path) -> Optional[Path]:
    for parent in Path(run_dir).resolve().parents:
        if parent.name == ".sessions":
            return parent
    return None


def _key_for_waste(report: object, waste: object) -> tuple[str, Optional[str], str]:
    agent = getattr(waste, "agent", "?")
    mode: Optional[str] = None
    step_idx = getattr(waste, "step_idx", -1)
    steps = getattr(report, "steps", [])
    if isinstance(step_idx, int) and 0 <= step_idx < len(steps):
        mode = getattr(steps[step_idx], "mode", None)
    return agent, mode, getattr(waste, "pattern", "")


def _evidence_for_waste(report: object, waste: object) -> str:
    run_id = getattr(report, "run_id", "")
    run_dir = getattr(report, "run_dir", Path("."))
    path = ""
    step_idx = getattr(waste, "step_idx", -1)
    steps = getattr(report, "steps", [])
    if isinstance(step_idx, int) and 0 <= step_idx < len(steps):
        path = getattr(steps[step_idx], "prose_file", "") or ""
    if not path:
        agent, mode, _pattern = _key_for_waste(report, waste)
        filename = f"{agent}-{mode}.md" if mode else f"{agent}.md"
        path = str(Path(run_dir) / filename)
    return f"run_id={run_id} path={path}"


def sync_from_run(
    run_dir: Path,
    *,
    repo_path: Path,
    recurrence_threshold: int = 3,
    active_patterns: Optional[set[str]] = None,
) -> list[Path]:
    """Create/update lessons for recurrent WasteFinding rows in ``run_dir``.

    Counts are scoped by ``(agent, mode, pattern)`` inside the same sessions root.
    Only keys present in the current run can create/update lessons.
    """
    from collections import Counter, defaultdict

    from harness import run_review

    active = active_patterns if active_patterns is not None else set(run_review.ACTIVE_WASTE_PATTERNS)
    current = run_review.build_report(Path(run_dir), Path(repo_path))
    current_keys = {
        _key_for_waste(current, waste)
        for waste in current.wastes
        if getattr(waste, "pattern", "") in active
    }
    if not current_keys:
        return []

    sessions_root = _sessions_root_for_run(Path(run_dir))
    if sessions_root is None:
        return []

    counts: Counter = Counter()
    evidence: dict[tuple[str, Optional[str], str], list[str]] = defaultdict(list)
    last: dict[tuple[str, Optional[str], str], str] = {}
    for candidate_run in run_review.list_runs(sessions_root):
        report = run_review.build_report(candidate_run, Path(repo_path))
        for waste in report.wastes:
            pattern = getattr(waste, "pattern", "")
            if pattern not in active:
                continue
            key = _key_for_waste(report, waste)
            counts[key] += 1
            ev = _evidence_for_waste(report, waste)
            if ev not in evidence[key]:
                evidence[key].append(ev)
            step_idx = getattr(waste, "step_idx", -1)
            steps = getattr(report, "steps", [])
            if isinstance(step_idx, int) and 0 <= step_idx < len(steps):
                ts = getattr(steps[step_idx], "ts", "")
            else:
                ts = ""
            if ts and ts > last.get(key, ""):
                last[key] = ts

    changed: set[Path] = set()
    threshold = max(int(recurrence_threshold), 1)
    for agent, mode, pattern in sorted(current_keys):
        key = (agent, mode, pattern)
        if counts[key] < threshold:
            continue
        changed.add(
            upsert_entry(
                agent,
                mode,
                pattern,
                hits=counts[key],
                last=last.get(key, ""),
                evidence=evidence.get(key, []),
                cwd=Path(repo_path),
            )
        )
    return sorted(changed)

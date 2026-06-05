"""parallel_wave — impl chain 의 opt-in 병렬 wave 계산 (#636).

정책 SSOT = `docs/plugin/parallel-policy.md` (모델 A: worktree 격리 fan-in).
본 모듈은 그 정책의 *판정 로직* 만 코드로 하강한다. 오케스트레이션
(worktree fan-out / git apply / aggregate test 실행 / PR·merge)은
`skills/impl-loop/SKILL.md` 절차 영역이며 본 모듈은 결정 로직만 담는다.

담는 것:

- `parse_impl_task` — impl task frontmatter `depends_on` (3-state) +
  `## Scope > 수정 허용` 파일 경로 집합 파싱.
- `compute_waves` — depends_on DAG 위상 + Scope 파일집합 disjoint +
  `max_parallel_workers` cap → 병렬 wave 후보. 불명확(미상 / scope 자유서술 /
  force_serial)은 직렬 강등 (정책 §3.1 · §4).
- `fan_in_check` — leader fan-in gate 의 최소 구조 판정 (scope 준수 +
  cross-worker 파일 충돌 + evidence 존재). aggregate test 실행 PASS 는
  이와 별개의 *절차적* 요건이라 leader 가 Bash 로 수행한다 (정책 §6).

3-state `depends_on` (정책 §3.1):

- `None`  = 미상(미작성 / placeholder 잔존) → 독립 확신 불가 → 직렬 강등.
- `()`    = 명시적 `[]` = 선행 없음 선언 → Scope 도 disjoint 면 병렬 후보.
- `(...)` = 그 선행 task 들에 의존.
"""
from __future__ import annotations

import fnmatch
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

__all__ = [
    "DEFAULT_MAX_PARALLEL_WORKERS",
    "ImplTask",
    "WaveStep",
    "WavePlan",
    "WorkerResult",
    "FanInResult",
    "parse_impl_task",
    "compute_waves",
    "fan_in_check",
    "scopes_disjoint",
]

# 정책 §7 — 첫 버전 동시성 상한. 상향은 실측 후 별도 이슈.
DEFAULT_MAX_PARALLEL_WORKERS = 2

# 병렬 후보 wave 의 기본 사유.
_PARALLEL_REASON = "독립 — depends_on 선후 없음 + Scope 파일집합 disjoint"


# ── 데이터 모델 ──────────────────────────────────────────────


@dataclass(frozen=True)
class ImplTask:
    """impl task 한 개의 병렬 판정 입력 (정규화 결과)."""

    slug: str
    path: str
    # 3-state: None=미상 / ()=명시적 선행 없음 / (...)=목록
    depends_on: Optional[tuple[str, ...]]
    scope_paths: frozenset[str]
    scope_ambiguous: bool
    # frontmatter `parallel: serial|false` 또는 고위험 명시 → 강제 직렬.
    force_serial: bool = False

    @property
    def serial_only(self) -> bool:
        """병렬 불가(직렬 강등) 조건 — 정책 §4 fallback."""
        return (
            self.depends_on is None
            or self.scope_ambiguous
            or not self.scope_paths
            or self.force_serial
        )

    @property
    def serial_reason(self) -> Optional[str]:
        """직렬 강등 사유 (병렬 불가일 때). 병렬 가능이면 None."""
        if self.force_serial:
            return "강제 직렬 (parallel: serial / 고위험)"
        if self.depends_on is None:
            return "depends_on 미상(미작성)"
        if self.scope_ambiguous or not self.scope_paths:
            return "Scope 파일 경로 미정규화(자유서술/빈값)"
        return None


@dataclass(frozen=True)
class WaveStep:
    """실행 계획의 한 단계 — 병렬 wave(≥2) 또는 직렬 단일(1)."""

    index: int
    mode: str  # "parallel" | "serial"
    tasks: tuple[ImplTask, ...]
    reason: str

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "mode": self.mode,
            "tasks": [t.slug for t in self.tasks],
            "reason": self.reason,
        }


@dataclass(frozen=True)
class WavePlan:
    """compute_waves 결과 — 순서 있는 단계 목록."""

    steps: tuple[WaveStep, ...]
    max_parallel_workers: int

    @property
    def has_parallel(self) -> bool:
        return any(s.mode == "parallel" for s in self.steps)

    @property
    def parallel_steps(self) -> tuple[WaveStep, ...]:
        return tuple(s for s in self.steps if s.mode == "parallel")

    def to_dict(self) -> dict:
        return {
            "max_parallel_workers": self.max_parallel_workers,
            "has_parallel": self.has_parallel,
            "steps": [s.to_dict() for s in self.steps],
        }


@dataclass(frozen=True)
class WorkerResult:
    """fan-in 시 worker 한 명이 반환한 산출물의 검증 입력."""

    slug: str
    changed_paths: frozenset[str]  # worker diff 가 실제로 건드린 파일
    declared_scope: frozenset[str]  # 해당 task 의 `수정 허용`
    evidence_present: bool = True


@dataclass(frozen=True)
class FanInResult:
    """leader fan-in gate 의 최소 구조 판정 결과."""

    verdict: str  # "PASS" | "FALLBACK"
    scope_violations: tuple[tuple[str, str], ...]  # (slug, scope 밖 path)
    conflicts: tuple[tuple[str, tuple[str, ...]], ...]  # (path, 그 path 건드린 slug 들)
    missing_evidence: tuple[str, ...]  # evidence 없는 slug
    reasons: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.verdict == "PASS"

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "passed": self.passed,
            "scope_violations": [list(v) for v in self.scope_violations],
            "conflicts": [[p, list(s)] for p, s in self.conflicts],
            "missing_evidence": list(self.missing_evidence),
            "reasons": list(self.reasons),
        }


# ── 파싱 ────────────────────────────────────────────────────


def _strip_inline_comment(value: str) -> str:
    """frontmatter 값에서 `#` 주석 제거. slug/경로는 `#` 미포함이라 안전."""
    idx = value.find("#")
    return value if idx < 0 else value[:idx]


def _extract_frontmatter_lines(text: str) -> list[str]:
    """첫 `---` … `---` 블록 안 줄 목록. 부재 시 빈 목록."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    out: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            return out
        out.append(line)
    return []  # 닫는 --- 없음 → frontmatter 아님


def _finalize_dep_items(items: Iterable[str]) -> Optional[tuple[str, ...]]:
    """파싱한 depends_on 원소들을 정리. placeholder 잔존 시 미상(None).

    block 리스트 원소의 inline 주석(`- 01-a  # produces X`)도 제거한다 — slug 는
    `#` 를 포함하지 않으므로 안전. 안 떼면 주석이 slug 에 섞여 `_deps_satisfied`
    가 선행 task 와 매칭 못 해 의존 task 를 같은 wave 로 잘못 올린다.
    """
    cleaned: list[str] = []
    for raw in items:
        it = _strip_inline_comment(raw).strip().strip("'\"").strip("`").strip()
        if not it:
            continue
        # placeholder 미충전 (`<NN-slug>`, `...`) → 미상으로 강등 (오판 방지).
        if "<" in it or ">" in it or it == "...":
            return None
        cleaned.append(it)
    if not cleaned:
        return None
    return tuple(cleaned)


def _parse_depends_on(fm_lines: list[str]) -> Optional[tuple[str, ...]]:
    """3-state depends_on 파싱 (정책 §3.1).

    반환: None(미상) / ()(명시적 선행 없음) / (slug, ...)(목록).
    """
    idx = None
    for i, line in enumerate(fm_lines):
        if re.match(r"^depends_on\s*:", line):
            idx = i
            break
    if idx is None:
        return None  # 키 부재 → 미상

    value = _strip_inline_comment(fm_lines[idx].split(":", 1)[1]).strip()

    if value == "":
        # same-line 값 없음 → 블록 리스트(`  - x`) 탐색.
        items: list[str] = []
        for j in range(idx + 1, len(fm_lines)):
            m = re.match(r"^\s+-\s+(.+)$", fm_lines[j])
            if m:
                items.append(m.group(1))
            elif fm_lines[j].strip() == "":
                continue
            else:
                break  # 다음 key → 블록 종료
        if not items:
            return None  # 값도 블록도 없음 → 미상
        return _finalize_dep_items(items)

    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if inner == "":
            return ()  # 명시적 [] → 선행 없음(독립 후보)
        return _finalize_dep_items(inner.split(","))

    # 스칼라/기타 malformed → 안전하게 미상.
    return None


def _parse_parallel_marker(fm_lines: list[str]) -> bool:
    """frontmatter `parallel:` 가 serial/false/no 면 강제 직렬."""
    for line in fm_lines:
        m = re.match(r"^parallel\s*:\s*(.+)$", line)
        if m:
            val = _strip_inline_comment(m.group(1)).strip().strip("'\"").lower()
            return val in {"serial", "false", "no", "off"}
    return False


def _is_path_like(token: str) -> bool:
    """repo-relative 파일/디렉토리 경로처럼 보이는 단일 토큰인가."""
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./*-]*", token):
        return False
    return ("/" in token) or bool(re.search(r"\.[A-Za-z0-9]+$", token))


def _normalize_path(token: str) -> str:
    """경로 정규화 — 선행 `./` 제거, 그 외 보존."""
    t = token.strip()
    while t.startswith("./"):
        t = t[2:]
    return t


def _parse_scope(text: str) -> tuple[frozenset[str], bool]:
    """`### 수정 허용` 섹션을 파일 경로 집합으로. (paths, ambiguous) 반환.

    엄격 규칙(정책 §3 "자유 서술 금지"): bullet 내용이 **단일 path-like 토큰**일
    때만 경로로 인정. 빈 bullet / 다중 토큰 / 산문 → ambiguous=True (직렬 강등).
    섹션/경로 부재도 ambiguous.
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(r"^###\s+수정\s*허용\s*$", line.strip()):
            start = i
            break
    if start is None:
        return frozenset(), True  # 섹션 부재 → 미상

    paths: list[str] = []
    has_nonpath = False
    for j in range(start + 1, len(lines)):
        s = lines[j].strip()
        if re.match(r"^#{2,4}\s", s):
            break  # 다음 헤더
        if s.startswith(">"):  # blockquote 안내문 무시
            continue
        if not s.startswith("-"):
            continue
        token = s[1:].strip()
        if token.startswith("`") and token.endswith("`") and len(token) >= 2:
            token = token[1:-1].strip()
        parts = token.split()
        if len(parts) == 1 and _is_path_like(parts[0]):
            paths.append(_normalize_path(parts[0]))
        else:
            has_nonpath = True  # 빈/산문/다중토큰 bullet

    if not paths:
        return frozenset(), True
    return frozenset(paths), has_nonpath


def parse_impl_task(path: str | Path) -> ImplTask:
    """impl task 파일을 ImplTask 로 파싱."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    fm_lines = _extract_frontmatter_lines(text)
    depends_on = _parse_depends_on(fm_lines)
    scope_paths, scope_ambiguous = _parse_scope(text)
    force_serial = _parse_parallel_marker(fm_lines)
    return ImplTask(
        slug=p.stem,
        path=str(p),
        depends_on=depends_on,
        scope_paths=scope_paths,
        scope_ambiguous=scope_ambiguous,
        force_serial=force_serial,
    )


# ── Scope 충돌 판정 ──────────────────────────────────────────


def _paths_overlap(a: str, b: str) -> bool:
    """두 경로가 충돌(동일/디렉토리 포함/glob 매치)하는가."""
    if a == b:
        return True
    a_dir = a.rstrip("/") + "/"
    b_dir = b.rstrip("/") + "/"
    if b.startswith(a_dir) or a.startswith(b_dir):
        return True
    if "*" in a or "*" in b:
        if fnmatch.fnmatch(b, a) or fnmatch.fnmatch(a, b):
            return True
    return False


def scopes_disjoint(a: Iterable[str], b: Iterable[str]) -> bool:
    """두 Scope 파일집합이 서로 충돌하지 않으면 True (병렬 가능)."""
    a = list(a)
    b = list(b)
    for pa in a:
        for pb in b:
            if _paths_overlap(pa, pb):
                return False
    return True


# ── wave 계산 ────────────────────────────────────────────────


def _deps_satisfied(task: ImplTask, done: set[str], in_batch: set[str]) -> bool:
    """task 의 batch 내 선행이 모두 done 인가 (batch 밖 선행은 머지됨으로 간주)."""
    if not task.depends_on:  # None(미상) 또는 ()(선행 없음)
        return True
    for dep in task.depends_on:
        if dep in in_batch and dep not in done:
            return False
    return True


def compute_waves(
    tasks: list[ImplTask],
    max_parallel_workers: int = DEFAULT_MAX_PARALLEL_WORKERS,
) -> WavePlan:
    """impl task 목록(직렬 순서)을 병렬 wave 계획으로.

    정책 §3 판정식:
        같은 wave 병렬 가능 = depends_on 위상상 선후 없음 AND Scope 파일집합 disjoint
    불명확(미상 / scope 자유서술 / force_serial)은 직렬 강등 (§4).
    동시성 상한 = max_parallel_workers (§7).
    """
    if max_parallel_workers < 1:
        max_parallel_workers = 1
    in_batch = {t.slug for t in tasks}
    remaining = list(tasks)
    done: set[str] = set()
    steps: list[WaveStep] = []
    step_index = 0

    while remaining:
        frontier = [t for t in remaining if _deps_satisfied(t, done, in_batch)]
        if not frontier:
            # 순환/미해결 의존 → 안전하게 첫 항목 직렬.
            head = remaining[0]
            step_index += 1
            steps.append(
                WaveStep(step_index, "serial", (head,), "의존 미해결/순환 → 직렬")
            )
            remaining.remove(head)
            done.add(head.slug)
            continue

        head = frontier[0]

        if head.serial_only:
            step_index += 1
            steps.append(
                WaveStep(step_index, "serial", (head,), head.serial_reason or "직렬")
            )
            remaining.remove(head)
            done.add(head.slug)
            continue

        # head 는 병렬 후보 — 다른 후보와 Scope disjoint 한 wave 구성 (cap 까지).
        wave = [head]
        for cand in frontier[1:]:
            if len(wave) >= max_parallel_workers:
                break
            if cand.serial_only:
                continue
            if all(scopes_disjoint(cand.scope_paths, w.scope_paths) for w in wave):
                wave.append(cand)

        step_index += 1
        if len(wave) >= 2:
            steps.append(
                WaveStep(step_index, "parallel", tuple(wave), _PARALLEL_REASON)
            )
            for t in wave:
                remaining.remove(t)
                done.add(t.slug)
        else:
            # 짝 없음 → head 단독 직렬.
            steps.append(
                WaveStep(
                    step_index,
                    "serial",
                    (head,),
                    "동시 가능한 짝 없음 (Scope 중첩 등) → 직렬",
                )
            )
            remaining.remove(head)
            done.add(head.slug)

    return WavePlan(tuple(steps), max_parallel_workers)


# ── fan-in 검증 ──────────────────────────────────────────────


def _path_in_scope(path: str, scope: Iterable[str]) -> bool:
    """changed path 가 declared scope 안인가."""
    for entry in scope:
        if path == entry:
            return True
        if path.startswith(entry.rstrip("/") + "/"):
            return True
        if "*" in entry and fnmatch.fnmatch(path, entry):
            return True
    return False


def fan_in_check(results: Iterable[WorkerResult]) -> FanInResult:
    """fan-in gate 의 최소 구조 판정 (정책 §6).

    PASS = 모든 worker diff 가 자기 Scope 안 + cross-worker 파일 충돌 없음 +
    evidence 전부 존재. 하나라도 어기면 FALLBACK (직렬 강등 신호).

    주의: aggregate tree 전체 테스트 PASS 는 별개의 절차적 요건이라 leader 가
    Bash 로 수행한다 — 본 함수는 그 *전* 의 구조 게이트만 본다.
    """
    results = list(results)

    scope_violations: list[tuple[str, str]] = []
    for r in results:
        for p in sorted(r.changed_paths):
            if not _path_in_scope(p, r.declared_scope):
                scope_violations.append((r.slug, p))

    owners: dict[str, list[str]] = {}
    for r in results:
        for p in r.changed_paths:
            owners.setdefault(p, []).append(r.slug)
    conflicts = [
        (p, tuple(sorted(s))) for p, s in sorted(owners.items()) if len(s) > 1
    ]

    missing = tuple(r.slug for r in results if not r.evidence_present)

    reasons: list[str] = []
    if scope_violations:
        reasons.append(f"scope 이탈 {len(scope_violations)}건")
    if conflicts:
        reasons.append(f"cross-worker 파일 충돌 {len(conflicts)}건")
    if missing:
        reasons.append(f"evidence 누락 {len(missing)}건")

    verdict = "PASS" if not reasons else "FALLBACK"
    return FanInResult(
        verdict=verdict,
        scope_violations=tuple(scope_violations),
        conflicts=tuple(conflicts),
        missing_evidence=missing,
        reasons=tuple(reasons),
    )


# ── CLI 보조 (wave-plan 서브커맨드에서 호출) ──────────────────


def _resolve_impl_paths(raw_paths: list[str]) -> list[Path]:
    """경로 인자(파일/디렉토리/glob)를 impl 파일 목록으로 전개 + NN- 순 정렬."""
    found: list[Path] = []
    seen: set[str] = set()
    for raw in raw_paths:
        p = Path(raw)
        candidates: list[Path]
        if p.is_dir():
            candidates = sorted(p.glob("*.md"))
        elif any(ch in raw for ch in "*?["):
            base = Path(".")
            candidates = sorted(base.glob(raw))
        elif p.exists():
            candidates = [p]
        else:
            candidates = []
        for c in candidates:
            key = str(c.resolve())
            if key not in seen:
                seen.add(key)
                found.append(c)
    return sorted(found, key=lambda x: x.name)


def wave_plan_from_paths(
    raw_paths: list[str], max_parallel_workers: int = DEFAULT_MAX_PARALLEL_WORKERS
) -> WavePlan:
    paths = _resolve_impl_paths(raw_paths)
    tasks = [parse_impl_task(p) for p in paths]
    return compute_waves(tasks, max_parallel_workers)


def main(argv: Optional[list[str]] = None) -> int:
    """`python -m harness.parallel_wave <paths...>` — wave plan JSON 출력."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="parallel_wave",
        description="impl task 들의 병렬 wave 계획 계산 (#636)",
    )
    parser.add_argument("paths", nargs="+", help="impl 파일 / 디렉토리 / glob")
    parser.add_argument(
        "--max-parallel",
        type=int,
        default=DEFAULT_MAX_PARALLEL_WORKERS,
        help=f"동시성 상한 (default {DEFAULT_MAX_PARALLEL_WORKERS})",
    )
    args = parser.parse_args(argv)
    plan = wave_plan_from_paths(args.paths, args.max_parallel)
    print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

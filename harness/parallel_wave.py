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

import glob as _globmod
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
    unexpected_workers: tuple[str, ...]  # wave 기대 slug 밖 worker 결과
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
            "unexpected_workers": list(self.unexpected_workers),
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
            stripped = fm_lines[j].strip()
            m = re.match(r"^\s+-\s+(.+)$", fm_lines[j])
            if m:
                items.append(m.group(1))
            elif stripped == "" or stripped.startswith("#"):
                continue  # 빈 줄·standalone 주석 → block 중간이라도 종료 X (#636 codex F6)
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


def _parse_risk_marker(fm_lines: list[str]) -> bool:
    """frontmatter `risk:` 가 high-risk 류면 강제 직렬 (architect 명시 시)."""
    for line in fm_lines:
        m = re.match(r"^risk\s*:\s*(.+)$", line)
        if m:
            val = _strip_inline_comment(m.group(1)).strip().strip("'\"").lower()
            return val in {"high", "high-risk", "highrisk", "critical"}
    return False


# 정책 §4 — 경로만으로 명백히 고위험인 패턴 (DB 마이그레이션 / 비밀·자격증명).
# 보수적·고정밀 safety net. 도메인 invariant·auth 로직 등 *의미* 기반 고위험은
# 경로로 신뢰성 있게 못 잡으므로 메인 dry-preview 판정(compute_waves high_risk_slugs)이
# 진본이고, 본 패턴은 메인이 놓쳐도 걸리는 backstop 이다.
_INHERENT_HIGH_RISK_RE = re.compile(
    r"(^|/)migrations?(/|$)"
    r"|(^|/)alembic(/|$)"
    # `.env` 계열 — `.env`, `.env.local`, `.env*`(glob), `.env-prod` 등. 뒤가
    # `. / * -` 또는 끝일 때만 → `.environment` 같은 무관 경로 오탐 방지 (#636 F15).
    r"|(^|/)\.env([./*\-]|$)"
    r"|(^|/)secrets?([./*\-]|$)"
    r"|(^|/)credentials?([./*\-]|$)"
)


def _scope_inherent_high_risk(scope_paths: Iterable[str]) -> bool:
    return any(_INHERENT_HIGH_RISK_RE.search(p) for p in scope_paths)


def _is_path_like(token: str) -> bool:
    """repo-relative 파일/디렉토리 경로처럼 보이는 단일 토큰인가.

    leading `.` 허용 — `./src/a.py`(상대), `.github/workflows/ci.yml`(dot-dir),
    `.env`(dotfile) 같은 흔한 경로가 ambiguous 로 오판돼 직렬 강등되지 않게 (#636 F14).
    bare `.`·`..`·`...` 는 `/` 도 확장자도 없어 아래 조건에서 걸러진다.
    """
    if not re.fullmatch(r"[A-Za-z0-9_.][A-Za-z0-9_./*-]*", token):
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
        if s == "":
            continue
        if s.startswith(">"):  # blockquote 안내문 무시
            continue
        if not s.startswith("-"):
            # bullet 아닌 자유서술 prose → 정규화 안 됨 → 미상(직렬) (#636 codex F7)
            has_nonpath = True
            continue
        # inline 주석 strip — depends_on 파싱과 일관 (`- src/a.py  # 핸들러` 허용).
        token = _strip_inline_comment(s[1:]).strip()
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
    force_serial = (
        _parse_parallel_marker(fm_lines)
        or _parse_risk_marker(fm_lines)
        or _scope_inherent_high_risk(scope_paths)
    )
    return ImplTask(
        slug=p.stem,
        path=str(p),
        depends_on=depends_on,
        scope_paths=scope_paths,
        scope_ambiguous=scope_ambiguous,
        force_serial=force_serial,
    )


# ── Scope 충돌 판정 ──────────────────────────────────────────


def _has_glob(p: str) -> bool:
    return "*" in p or "?" in p or "[" in p


def _glob_to_regex(pattern: str) -> str:
    """glob → regex. `*` 는 path segment 안에서만(`/` 안 넘음), `**` 는 `/` 넘음."""
    out: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                # globstar. `**/` 는 0개 이상 디렉토리 → `src/**/*.py` 가 `src/a.py`
                # (중간 디렉토리 0개)도 매치하도록 slash 를 optional 로 (#636 codex F8).
                if i + 2 < n and pattern[i + 2] == "/":
                    out.append("(?:.*/)?")
                    i += 3
                    continue
                out.append(".*")  # 끝의 ** → 나머지 전부
                i += 2
                continue
            out.append("[^/]*")  # * → segment-local (no /)
            i += 1
            continue
        if ch == "?":
            out.append("[^/]")
            i += 1
            continue
        if ch == "[":
            # char class `[abc]` / `[!abc]`(negation) — _has_glob 가 `[` 를 glob 으로
            # 인식하므로 리터럴로 두면 비일관. 닫는 `]` 까지 regex char class 로 옮긴다.
            j = i + 1
            if j < n and pattern[j] in "!^":
                j += 1
            if j < n and pattern[j] == "]":
                j += 1  # 첫 `]` 는 class 안 리터럴
            while j < n and pattern[j] != "]":
                j += 1
            if j >= n:  # 닫는 `]` 없음 → 리터럴 `[`
                out.append(re.escape("["))
                i += 1
                continue
            inner = pattern[i + 1 : j]
            if inner[:1] == "!":
                inner = "^" + inner[1:]
            out.append("[" + inner + "]")
            i = j + 1
            continue
        out.append(re.escape(ch))
        i += 1
    return "".join(out)


def _glob_match(path: str, pattern: str) -> bool:
    """구체 path 가 glob pattern 에 full-match (segment-aware). glob 없으면 정확 비교.

    `fnmatch` 와 달리 `*` 가 `/` 를 넘지 않는다 — `src/*.py` 는 `src/a.py` 만 매치하고
    `src/sub/a.py` 는 매치 안 함 (fan-in scope gate 우회 차단, #636 codex F4).
    `?`(단일 비-/ 문자)·`[...]`(char class)도 segment-aware.
    """
    if not _has_glob(pattern):
        return path == pattern
    try:
        return re.fullmatch(_glob_to_regex(pattern), path) is not None
    except re.error:
        return path == pattern  # 깨진 패턴 → 리터럴 비교 (안전)


def _glob_dir_prefix(p: str) -> str:
    """glob pattern 의 첫 `*`/`?`/`[` 이전 정적 디렉토리 prefix (trailing `/` 포함)."""
    idx = len(p)
    for ch in ("*", "?", "["):
        j = p.find(ch)
        if j >= 0:
            idx = min(idx, j)
    head = p[:idx]
    slash = head.rfind("/")
    return head[: slash + 1] if slash >= 0 else ""


def _paths_overlap(a: str, b: str) -> bool:
    """두 경로가 충돌(동일/디렉토리 포함/segment-aware glob)하는가."""
    if a == b:
        return True
    if b.startswith(a.rstrip("/") + "/") or a.startswith(b.rstrip("/") + "/"):
        return True
    a_glob, b_glob = _has_glob(a), _has_glob(b)
    if a_glob and not b_glob:
        return _glob_match(b, a)
    if b_glob and not a_glob:
        return _glob_match(a, b)
    if a_glob and b_glob:
        # glob-vs-glob: 정적 디렉토리 prefix 가 nested/equal 이면 보수적으로 충돌 가정.
        pa, pb = _glob_dir_prefix(a), _glob_dir_prefix(b)
        return pa == pb or pa.startswith(pb) or pb.startswith(pa)
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
    high_risk_slugs: Iterable[str] = (),
) -> WavePlan:
    """impl task 목록(직렬 순서)을 병렬 wave 계획으로.

    정책 §3 판정식:
        같은 wave 병렬 가능 = depends_on 위상상 선후 없음 AND Scope 파일집합 disjoint
    불명확(미상 / scope 자유서술 / force_serial)은 직렬 강등 (§4).
    동시성 상한 = max_parallel_workers (§7).

    `high_risk_slugs` = 메인 dry-preview 가 고위험으로 판정한 slug 집합 (정책 §4
    "migration/destructive/security/도메인 invariant → 직렬"의 *진본 판정*). 의미 기반
    고위험은 경로로 신뢰성 있게 못 잡으므로 메인이 판정해 전달한다. parse_impl_task 의
    inherent 경로 패턴(migrations/secrets 등)은 메인이 놓쳐도 걸리는 backstop.
    """
    if max_parallel_workers < 1:
        max_parallel_workers = 1
    hr = frozenset(high_risk_slugs)

    def _is_serial(t: ImplTask) -> bool:
        return t.serial_only or t.slug in hr

    def _serial_reason(t: ImplTask) -> str:
        if t.slug in hr and not t.serial_only:
            return "고위험 task (dry-preview 판정) → 직렬"
        return t.serial_reason or "직렬"

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

        if _is_serial(head):
            step_index += 1
            steps.append(
                WaveStep(step_index, "serial", (head,), _serial_reason(head))
            )
            remaining.remove(head)
            done.add(head.slug)
            continue

        # head 는 병렬 후보 — **remaining(NN/task_index) 순서의 *연속* prefix** 로만 묶는다.
        # frontier(준비된 것만) 가 아니라 remaining 을 순회하는 이유: 사이에 *blocked*
        # (아직 미준비) task 가 있으면 그것도 barrier 여야 한다. frontier 만 보면 blocked
        # task 를 건너뛰고 뒤 독립 task 를 당겨 순서가 뒤집힌다 (#636 codex F13 — F10 의
        # 미준비-intervening 변종). join 불가(blocked / serial·고위험 / Scope 겹침 / cap)를
        # 만나면 멈춘다. 그래야 실행/머지 순서 = task_index 순서가 보존돼 3/3 PR 이 story 를
        # 마지막에 닫는 invariant 가 유지된다.
        head_idx = remaining.index(head)
        wave = [head]
        for cand in remaining[head_idx + 1:]:
            if len(wave) >= max_parallel_workers:
                break
            if not _deps_satisfied(cand, done, in_batch):
                break  # blocked intervening task → 순서 barrier
            if _is_serial(cand):
                break  # serial_only / 고위험 → 순서 barrier
            if all(scopes_disjoint(cand.scope_paths, w.scope_paths) for w in wave):
                wave.append(cand)
            else:
                break  # Scope 겹침 → 순서 barrier

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
    """changed path 가 declared scope 안인가 (fan-in scope gate).

    - exact 파일 매치.
    - **명시적 디렉토리 scope(끝이 `/`)** 만 하위 파일을 허용. 확장자 없는 파일
      scope(`scripts/tool`)를 디렉토리로 오인해 `scripts/tool/x.py` 를 통과시키던
      구멍 차단 (#636 codex F12). 디렉토리 의도면 `scripts/tool/` 로 적는다.
    - glob entry 는 segment-aware 매칭 — `src/*.py` 는 `src/sub/a.py` 를 in-scope 로
      오인하지 않는다 (#636 codex F4: fnmatch 가 `/` 를 안 가려 scope 우회되던 구멍).
    """
    for entry in scope:
        if path == entry:
            return True
        if entry.endswith("/") and path.startswith(entry):
            return True  # 명시적 디렉토리 scope 만 하위 허용
        if _has_glob(entry) and _glob_match(path, entry):
            return True
    return False


def fan_in_check(
    results: Iterable[WorkerResult],
    *,
    expected_slugs: Iterable[str],
) -> FanInResult:
    """fan-in gate 의 최소 구조 판정 (정책 §6).

    PASS = 모든 worker diff 가 자기 Scope 안 + cross-worker 파일 충돌 없음 +
    evidence 전부 존재 + 결과 slug 가 기대 wave 와 일치. 하나라도 어기면
    FALLBACK (직렬 강등 신호). `expected_slugs` 는 필수 입력이다. caller 가
    wave 에 있어야 하는 worker 전체를 넘기지 않으면 부분 누락을 알 수 없기
    때문이다.

    주의: aggregate tree 전체 테스트 PASS 는 별개의 절차적 요건이라 leader 가
    Bash 로 수행한다 — 본 함수는 그 *전* 의 구조 게이트만 본다.
    """
    results = list(results)
    expected = tuple(dict.fromkeys(s for s in expected_slugs if s))
    expected_set = set(expected)
    present = {r.slug for r in results}

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

    missing = tuple(
        dict.fromkeys(
            [s for s in expected if s not in present]
            + [r.slug for r in results if not r.evidence_present]
        )
    )
    unexpected = tuple(
        dict.fromkeys(r.slug for r in results if r.slug not in expected_set)
    )

    reasons: list[str] = []
    if not results and not expected:
        reasons.append("worker 결과 없음")
    if scope_violations:
        reasons.append(f"scope 이탈 {len(scope_violations)}건")
    if conflicts:
        reasons.append(f"cross-worker 파일 충돌 {len(conflicts)}건")
    if missing:
        reasons.append(f"evidence 누락 {len(missing)}건")
    if unexpected:
        reasons.append(f"예상 밖 worker {len(unexpected)}건")

    verdict = "PASS" if not reasons else "FALLBACK"
    return FanInResult(
        verdict=verdict,
        scope_violations=tuple(scope_violations),
        conflicts=tuple(conflicts),
        missing_evidence=missing,
        unexpected_workers=unexpected,
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
            # glob 모듈은 절대/상대 패턴을 모두 처리 (Path.glob 은 절대 패턴에
            # NotImplementedError — #636 codex F5). recursive `**` 도 지원.
            candidates = sorted(Path(m) for m in _globmod.glob(raw, recursive=True))
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


def _split_csv(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


def wave_plan_from_paths(
    raw_paths: list[str],
    max_parallel_workers: int = DEFAULT_MAX_PARALLEL_WORKERS,
    high_risk_slugs: Iterable[str] = (),
) -> WavePlan:
    paths = _resolve_impl_paths(raw_paths)
    tasks = [parse_impl_task(p) for p in paths]
    return compute_waves(tasks, max_parallel_workers, high_risk_slugs)


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
    parser.add_argument(
        "--high-risk",
        default="",
        help="메인 dry-preview 가 고위험으로 판정한 task slug (콤마 구분) → 직렬 강제",
    )
    args = parser.parse_args(argv)
    plan = wave_plan_from_paths(
        args.paths, args.max_parallel, _split_csv(args.high_risk)
    )
    print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

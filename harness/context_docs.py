"""CLAUDE.md seed, migration, and quality audit helpers."""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


RECOMMENDED_SECTIONS = (
    "Commands",
    "Architecture",
    "Key Files",
    "Code Style",
    "Environment",
    "Testing",
    "Gotchas",
    "Workflow",
)

COLD_START_SECTION_TITLE = "## dcNess Cold Start"


@dataclass(frozen=True)
class AxisScore:
    name: str
    score: int
    maximum: int
    note: str


@dataclass(frozen=True)
class ClaudeAudit:
    path: Path
    exists: bool
    total_score: int
    grade: str
    line_count: int
    axis_scores: list[AxisScore] = field(default_factory=list)
    missing_sections: list[str] = field(default_factory=list)
    has_cold_start_anchor: bool = False
    broken_references: list[str] = field(default_factory=list)
    improvement_candidates: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EnsureResult:
    path: Path
    actions: list[str]
    audit: ClaudeAudit


def has_cold_start_anchor(text: str) -> bool:
    return bool(re.search(r"(?im)^##\s+dcNess\s+Cold\s+Start\s*$", text))


def build_cold_start_anchor() -> str:
    return "\n".join([
        COLD_START_SECTION_TITLE,
        "- 다음 작업 후보 확인: `/next`",
        "- 진행 상태 문서: docs/index.md 의 진행 상태 섹션을 사용합니다.",
        "- live 보드 좌표 확인: `gh variable get DCNESS_PROJECT_OWNER`",
        "- live 보드 번호 확인: `gh variable get DCNESS_PROJECT_NUMBER`",
        "- 보드 좌표가 없으면 `/init-dcness` custom Project bootstrap 을 실행합니다.",
    ])


def _package_manager(root: Path) -> str:
    if (root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (root / "yarn.lock").exists():
        return "yarn"
    return "npm"


def _detect_package_commands(root: Path) -> list[str]:
    package_json = root / "package.json"
    if not package_json.exists():
        return []
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    scripts = data.get("scripts")
    if not isinstance(scripts, dict):
        return []
    manager = _package_manager(root)
    commands: list[str] = []
    for script in ("dev", "build", "lint", "test"):
        if script in scripts:
            commands.append(f"- `{manager} run {script}`")
    return commands


def _detect_python_commands(root: Path) -> list[str]:
    commands: list[str] = []
    if (root / "tests").exists():
        commands.append("- `python3.11 -m unittest discover -s tests -v`")
    if (root / "scripts" / "check_static_quality.sh").exists():
        commands.append("- `bash scripts/check_static_quality.sh`")
    return commands


def _detect_commands(root: Path) -> list[str]:
    commands = _detect_package_commands(root)
    commands.extend(_detect_python_commands(root))
    if commands:
        return commands
    return [
        "- 실제 build/test/lint 명령을 확인한 뒤 copy-paste 가능한 형태로 기록합니다.",
    ]


def build_claude_seed(repo_path: Path) -> str:
    command_lines = "\n".join(_detect_commands(repo_path))
    return "\n".join([
        "# Project Instructions",
        "",
        "## Commands",
        command_lines,
        "",
        "## Architecture",
        "- 코드베이스 구조와 주요 런타임 경계를 짧게 유지합니다.",
        "- dcNess 문서 seed 를 쓰는 프로젝트는 docs/index.md 를 cold-start entrypoint 로 둡니다.",
        "",
        "## Key Files",
        "- `CLAUDE.md`: 모든 세션에 로드되는 프로젝트 지침입니다.",
        "- AGENTS.md: 외부 에이전트용 얇은 안내가 필요할 때 CLAUDE.md 를 참조합니다.",
        "",
        "## Code Style",
        "- formatter, linter, naming convention 은 확인된 사실만 기록합니다.",
        "- 모순되는 규칙은 남기지 말고 현재 코드와 일치하는 규칙만 유지합니다.",
        "",
        "## Environment",
        "- 필수 런타임, 패키지 매니저, 환경변수, 로컬 서비스만 기록합니다.",
        "- 개인 환경값은 공유 파일 대신 로컬 설정에 둡니다.",
        "",
        "## Testing",
        "- 테스트 명령은 실패 시 재현 가능한 copy-paste 형태로 유지합니다.",
        "- 회귀 검증에 필요한 fixture, seed data, 외부 서비스 조건을 기록합니다.",
        "",
        "## Gotchas",
        "- 반복 실수, 비직관적 설계 이유, 알려진 제한만 짧게 기록합니다.",
        "- 일회성 문제나 추측은 넣지 않습니다.",
        "",
        "## Workflow",
        "- dcNess 시작: `/spec`, `/design`, `/impl`, `/acceptance` 중 작업 성격에 맞게 진입합니다.",
        "- 다음 작업 확인은 `/next` 를 우선 사용합니다.",
        "",
        build_cold_start_anchor(),
        "",
    ])


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 70:
        return "B"
    if score >= 50:
        return "C"
    if score >= 30:
        return "D"
    return "F"


def _has_section(text: str, section: str) -> bool:
    return bool(re.search(rf"(?im)^##\s+{re.escape(section)}\s*$", text))


def _has_command_signal(text: str) -> bool:
    command_re = re.compile(
        r"```(?:bash|sh|shell)|"
        r"`[^`\n]*(?:/(?:next|spec|design|impl|acceptance|to-issue|run-review|"
        r"smart-compact|tech-review|impl-loop)|npm|pnpm|yarn|node|python3?(?:\.\d+)?|pytest|ruff|mypy|"
        r"make|go test|cargo|bash)[^`\n]*`",
        re.IGNORECASE,
    )
    return bool(command_re.search(text))


def _has_path_signal(text: str) -> bool:
    return bool(re.search(r"`(?:[A-Za-z0-9_.-]+/[^`\s]+|[A-Z_]+\.md)`", text))


def _score_commands(text: str) -> AxisScore:
    if _has_command_signal(text):
        return AxisScore("Commands", 20, 20, "copy-paste 가능한 명령이 있습니다.")
    if _has_section(text, "Commands"):
        return AxisScore("Commands", 10, 20, "Commands 섹션은 있으나 실제 명령이 부족합니다.")
    return AxisScore("Commands", 0, 20, "build/test/lint workflow 명령이 없습니다.")


def _score_architecture(text: str) -> AxisScore:
    has_arch = re.search(r"(?i)architecture|아키텍처|구조", text) is not None
    has_map = re.search(r"(?i)entrypoint|boundary|module|docs/index\.md", text) is not None
    if has_arch and has_map:
        return AxisScore("Architecture", 20, 20, "구조와 entrypoint 단서가 있습니다.")
    if _has_section(text, "Architecture") or has_arch:
        return AxisScore("Architecture", 10, 20, "구조 개요는 있으나 관계 설명이 부족합니다.")
    return AxisScore("Architecture", 0, 20, "코드베이스 구조 설명이 없습니다.")


def _score_gotchas(text: str) -> AxisScore:
    if re.search(r"(?i)^##\s+Gotchas\s*$|주의|함정|quirk|known issue", text, re.MULTILINE):
        return AxisScore("Gotchas", 15, 15, "비직관적 패턴을 담을 위치가 있습니다.")
    return AxisScore("Gotchas", 0, 15, "반복 실수와 비직관적 패턴 섹션이 없습니다.")


def _score_conciseness(line_count: int) -> AxisScore:
    if line_count < 200:
        return AxisScore("Conciseness", 15, 15, "200줄 미만입니다.")
    if line_count < 300:
        return AxisScore("Conciseness", 10, 15, "200줄 목표를 넘었습니다.")
    return AxisScore("Conciseness", 5, 15, "긴 파일이라 세션 준수율 저하 후보입니다.")


def _clean_candidate(value: str) -> str:
    out = value.strip().strip("'\"")
    out = re.sub(r"[),.;:!?]+$", "", out)
    out = out.split("#", 1)[0].split("?", 1)[0]
    if out.startswith("./"):
        out = out[2:]
    return out


def _should_ignore_candidate(value: str) -> bool:
    if not value or value.startswith(("#", "/", "~", "$", "@", "-")):
        return True
    if re.match(r"(?i)^(https?:|mailto:|tel:|ftp:)", value):
        return True
    if re.search(r"[\s<>{}*]", value):
        return True
    return False


def _looks_like_repo_path(value: str) -> bool:
    if value in {"CLAUDE.md", "AGENTS.md", "README.md", "PROGRESS.md"}:
        return True
    return bool(re.match(r"^(?:\.github|agents|app|commands|docs|harness|hooks|lib|"
                         r"scripts|skills|src|templates|tests)/", value))


def _candidate_paths(text: str) -> list[str]:
    candidates: list[str] = []
    for match in re.finditer(r"!?\[[^\]]*\]\(([^)\n]+)\)", text):
        candidates.append(match.group(1).split()[0])
    for match in re.finditer(r"`([^`\n]+)`", text):
        candidates.append(match.group(1))
    cleaned: list[str] = []
    for value in candidates:
        candidate = _clean_candidate(value)
        if _should_ignore_candidate(candidate) or not _looks_like_repo_path(candidate):
            continue
        cleaned.append(candidate)
    return cleaned


def _broken_references(repo_path: Path, text: str) -> list[str]:
    broken: list[str] = []
    for candidate in sorted(set(_candidate_paths(text))):
        target = (repo_path / candidate).resolve()
        try:
            target.relative_to(repo_path.resolve())
        except ValueError:
            broken.append(candidate)
            continue
        if not target.exists():
            broken.append(candidate)
    return broken


def _score_currency(text: str, broken_references: list[str]) -> AxisScore:
    if broken_references:
        return AxisScore("Currency", 5, 15, "존재하지 않는 path 참조가 있습니다.")
    if _candidate_paths(text):
        return AxisScore("Currency", 15, 15, "확인 가능한 path 참조가 깨지지 않았습니다.")
    return AxisScore("Currency", 10, 15, "검증 가능한 path 참조가 적어 freshness 판단이 제한됩니다.")


def _score_actionability(text: str) -> AxisScore:
    has_command = _has_command_signal(text)
    has_path = _has_path_signal(text) or bool(_candidate_paths(text))
    if has_command and has_path:
        return AxisScore("Actionability", 15, 15, "명령과 경로가 모두 구체적입니다.")
    if has_command or has_path:
        return AxisScore("Actionability", 10, 15, "구체 명령 또는 경로가 일부 있습니다.")
    return AxisScore("Actionability", 5, 15, "실행 가능한 명령과 경로가 부족합니다.")


def audit_claude_text(text: str, repo_path: Path, path: Optional[Path] = None) -> ClaudeAudit:
    path = path or (repo_path / "CLAUDE.md")
    line_count = len(text.splitlines())
    missing_sections = [section for section in RECOMMENDED_SECTIONS if not _has_section(text, section)]
    broken = _broken_references(repo_path, text)
    axis_scores = [
        _score_commands(text),
        _score_architecture(text),
        _score_gotchas(text),
        _score_conciseness(line_count),
        _score_currency(text, broken),
        _score_actionability(text),
    ]
    total = sum(axis.score for axis in axis_scores)
    candidates = _improvement_candidates(
        axis_scores=axis_scores,
        missing_sections=missing_sections,
        line_count=line_count,
        has_anchor=has_cold_start_anchor(text),
        broken_references=broken,
    )
    return ClaudeAudit(
        path=path,
        exists=True,
        total_score=total,
        grade=_grade(total),
        line_count=line_count,
        axis_scores=axis_scores,
        missing_sections=missing_sections,
        has_cold_start_anchor=has_cold_start_anchor(text),
        broken_references=broken,
        improvement_candidates=candidates,
    )


def _improvement_candidates(
    *,
    axis_scores: list[AxisScore],
    missing_sections: list[str],
    line_count: int,
    has_anchor: bool,
    broken_references: list[str],
) -> list[str]:
    candidates: list[str] = []
    if missing_sections:
        candidates.append("권장 섹션 추가 후보: " + ", ".join(missing_sections))
    if not has_anchor:
        candidates.append("dcNess Cold Start 앵커 additive append 후보")
    if line_count >= 200:
        candidates.append("200줄 미만으로 압축 후보")
    if broken_references:
        candidates.append("깨진 path 참조 수정 후보: " + ", ".join(broken_references[:5]))
    for axis in axis_scores:
        if axis.score < axis.maximum:
            candidates.append(f"{axis.name} {axis.score}/{axis.maximum}: {axis.note}")
    return candidates


def audit_claude_md_file(repo_path: Path) -> ClaudeAudit:
    repo_path = repo_path.resolve()
    path = repo_path / "CLAUDE.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ClaudeAudit(
            path=path,
            exists=False,
            total_score=0,
            grade="F",
            line_count=0,
            missing_sections=list(RECOMMENDED_SECTIONS),
            improvement_candidates=["CLAUDE.md 생성 후보"],
        )
    return audit_claude_text(text, repo_path, path)


def ensure_claude_context(repo_path: Path) -> EnsureResult:
    repo_path = repo_path.resolve()
    path = repo_path / "CLAUDE.md"
    actions: list[str] = []
    if not path.exists():
        path.write_text(build_claude_seed(repo_path), encoding="utf-8")
        actions.append("created")
    else:
        text = path.read_text(encoding="utf-8")
        if not has_cold_start_anchor(text):
            separator = "\n" if text.endswith("\n") else "\n\n"
            path.write_text(f"{text}{separator}{build_cold_start_anchor()}\n", encoding="utf-8")
            actions.append("appended-cold-start")
    if not actions:
        actions.append("noop")
    return EnsureResult(path=path, actions=actions, audit=audit_claude_md_file(repo_path))


def render_claude_audit(audit: ClaudeAudit, *, actions: Optional[list[str]] = None) -> str:
    action_text = ", ".join(actions or ["read-only"])
    lines = [
        "## CLAUDE.md seed/migration",
        "",
        f"- path: `{audit.path.name}`",
        f"- action: {action_text}",
        f"- score: {audit.total_score}/100 ({audit.grade})",
        f"- lines: {audit.line_count}",
        f"- cold-start anchor: {'present' if audit.has_cold_start_anchor else 'missing'}",
        "",
        "| axis | score | note |",
        "|---|---:|---|",
    ]
    for axis in audit.axis_scores:
        lines.append(f"| {axis.name} | {axis.score}/{axis.maximum} | {axis.note} |")
    lines.append("")
    if audit.improvement_candidates:
        lines.append("### Improvement Candidates")
        for candidate in audit.improvement_candidates:
            lines.append(f"- {candidate}")
    else:
        lines.append("- improvement candidate 없음")
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="dcness-context-docs")
    parser.add_argument("--repo", default=".", help="target repository root")
    parser.add_argument("--ensure", action="store_true", help="seed or append allowed safe context")
    parser.add_argument("--audit", action="store_true", help="read-only audit")
    args = parser.parse_args(argv)

    repo_path = Path(args.repo).resolve()
    if args.ensure:
        result = ensure_claude_context(repo_path)
        print(render_claude_audit(result.audit, actions=result.actions))
        return 0
    audit = audit_claude_md_file(repo_path)
    print(render_claude_audit(audit))
    return 0


if __name__ == "__main__":
    sys.exit(main())

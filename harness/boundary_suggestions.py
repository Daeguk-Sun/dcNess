"""Suggest project boundary overrides for nonstandard source layouts.

The suggestion path is deliberately read-only. `.dcness/boundary.json` changes
must still be made by the main agent or a human after explicit approval.
"""
from __future__ import annotations

import json
import os
import re
import subprocess  # nosec B404
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from harness.agent_boundary import check_write_allowed
from harness.parallel_wave import parse_impl_task


SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".c",
        ".astro",
        ".cc",
        ".cjs",
        ".clj",
        ".cljs",
        ".cpp",
        ".cs",
        ".dart",
        ".erl",
        ".ex",
        ".exs",
        ".fs",
        ".fsx",
        ".go",
        ".h",
        ".hpp",
        ".hrl",
        ".java",
        ".js",
        ".jsx",
        ".kt",
        ".kts",
        ".lua",
        ".m",
        ".mm",
        ".mjs",
        ".php",
        ".py",
        ".pyi",
        ".r",
        ".rb",
        ".rs",
        ".scala",
        ".svelte",
        ".swift",
        ".ts",
        ".tsx",
        ".vue",
    }
)

IGNORED_DIR_PARTS: frozenset[str] = frozenset(
    {
        ".claude",
        ".dcness",
        ".git",
        ".github",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "__tests__",
        "build",
        "coverage",
        "dist",
        "docs",
        "node_modules",
        "out",
        "spec",
        "target",
        "test",
        "tests",
        "third_party",
        "tmp",
        "vendor",
        "venv",
    }
)

PARTIAL_STANDARD_TOP_LEVELS: frozenset[str] = frozenset({"apps", "packages"})
MAX_EXAMPLES = 3


@dataclass
class BoundarySuggestion:
    directory: str
    pattern: str
    file_count: int
    examples: list[str]


@dataclass
class BoundarySuggestionReport:
    project_root: str
    scanned_files: int
    uncovered_files: int
    suggestions: list[BoundarySuggestion]
    reason: str
    blocking_reasons: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _git_toplevel(cwd: Path) -> Optional[Path]:
    try:
        proc = subprocess.run(  # nosec B603, B607
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = proc.stdout.strip()
    return Path(out).resolve() if out else None


def _project_root(cwd: Optional[Path]) -> Path:
    root = (cwd or Path.cwd()).resolve()
    return _git_toplevel(root) or root


def _is_dcness_self_repo(root: Path) -> bool:
    manifest = root / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and data.get("name") == "dcness"


def _ignored_by_directory(rel: Path) -> bool:
    for part in rel.parts[:-1]:
        if _should_skip_dir_name(part):
            return True
    return False


def _should_skip_dir_name(name: str) -> bool:
    return name in IGNORED_DIR_PARTS or name.startswith(".")


def _is_test_like_file(path: Path) -> bool:
    name = path.name.lower()
    return bool(
        name.startswith("test_")
        or re.search(r"(^|[_\-.])test\.", name)
        or re.search(r"(^|[_\-.])spec\.", name)
        or name.endswith("_test.py")
        or name.endswith("_test.go")
        or name.endswith("_test.rb")
        or name.endswith("_spec.rb")
    )


def _is_source_candidate(rel: Path) -> bool:
    if rel.suffix.lower() not in SOURCE_EXTENSIONS:
        return False
    if len(rel.parts) < 2:
        return False
    if _ignored_by_directory(rel):
        return False
    return not _is_test_like_file(rel)


def _iter_source_candidates(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if not _should_skip_dir_name(name)]
        base = Path(dirpath)
        for filename in filenames:
            path = base / filename
            try:
                rel = path.relative_to(root)
            except ValueError:
                continue
            if _is_source_candidate(rel):
                yield rel


def _pattern_for_directory(directory: str) -> str:
    return "^" + "/".join(re.escape(part) for part in directory.rstrip("/").split("/")) + "/"


def _pattern_for_scope_path(path: str) -> str:
    normalized = path.strip()
    if normalized.endswith("/"):
        return _pattern_for_directory(normalized)
    return "^" + "/".join(re.escape(part) for part in normalized.split("/")) + "$"


def _group_uncovered(uncovered: list[Path]) -> list[BoundarySuggestion]:
    grouped: dict[str, list[Path]] = {}
    for rel in uncovered:
        if len(rel.parts) < 2:
            continue
        directory = _suggestion_directory(rel)
        grouped.setdefault(directory, []).append(rel)

    suggestions: list[BoundarySuggestion] = []
    for directory, paths in grouped.items():
        examples = sorted(p.as_posix() for p in paths)[:MAX_EXAMPLES]
        suggestions.append(
            BoundarySuggestion(
                directory=directory,
                pattern=_pattern_for_directory(directory),
                file_count=len(paths),
                examples=examples,
            )
        )
    return sorted(suggestions, key=lambda item: item.directory)


def _suggestion_directory(rel: Path) -> str:
    if rel.parts[0] in PARTIAL_STANDARD_TOP_LEVELS:
        max_parts = 3 if len(rel.parts) >= 4 else 2
        return "/".join(rel.parts[:max_parts]) + "/"
    parent = rel.parent.as_posix()
    return parent.rstrip("/") + "/"


def _suggestions_for_impl_plan_scope(paths: Iterable[str]) -> list[BoundarySuggestion]:
    suggestions: list[BoundarySuggestion] = []
    for rel in sorted(set(paths)):
        suggestions.append(
            BoundarySuggestion(
                directory=rel,
                pattern=_pattern_for_scope_path(rel),
                file_count=1,
                examples=[rel],
            )
        )
    return suggestions


def collect_impl_plan_boundary_suggestions(
    cwd: Optional[Path],
    impl_plan: Path,
) -> BoundarySuggestionReport:
    """Detect `### 수정 허용` paths not covered by the build-worker boundary."""
    root = _project_root(cwd)
    if _is_dcness_self_repo(root):
        return BoundarySuggestionReport(
            project_root=str(root),
            scanned_files=0,
            uncovered_files=0,
            suggestions=[],
            reason="self_repo",
        )

    parsed = parse_impl_task(impl_plan)
    scope_paths = sorted(parsed.scope_paths)
    uncovered: list[str] = []
    blocking_reasons: dict[str, str] = {}
    for rel in scope_paths:
        reason = check_write_allowed("build-worker", rel, cwd=root)
        if reason is None:
            continue
        blocking_reasons[rel] = reason
        if "ALLOW_MATRIX" in reason:
            uncovered.append(rel)

    suggestions = _suggestions_for_impl_plan_scope(uncovered)
    if blocking_reasons:
        report_reason = "impl_plan_uncovered"
    elif not scope_paths:
        report_reason = "impl_plan_scope_ambiguous"
    else:
        report_reason = "impl_plan_covered"
    return BoundarySuggestionReport(
        project_root=str(root),
        scanned_files=len(scope_paths),
        uncovered_files=len(blocking_reasons),
        suggestions=suggestions,
        reason=report_reason,
        blocking_reasons=blocking_reasons,
    )


def collect_boundary_suggestions(
    cwd: Optional[Path] = None,
    *,
    impl_plan: Optional[Path] = None,
) -> BoundarySuggestionReport:
    """Detect source directories not covered by the effective build-worker boundary."""
    if impl_plan is not None:
        return collect_impl_plan_boundary_suggestions(cwd, impl_plan)

    root = _project_root(cwd)
    if _is_dcness_self_repo(root):
        return BoundarySuggestionReport(
            project_root=str(root),
            scanned_files=0,
            uncovered_files=0,
            suggestions=[],
            reason="self_repo",
        )

    source_files = sorted(_iter_source_candidates(root), key=lambda p: p.as_posix())
    uncovered: list[Path] = []
    for rel in source_files:
        reason = check_write_allowed("build-worker", rel.as_posix(), cwd=root)
        if reason is not None and "ALLOW_MATRIX" in reason:
            uncovered.append(rel)

    suggestions = _group_uncovered(uncovered)
    if not source_files:
        report_reason = "empty"
    elif suggestions:
        report_reason = "uncovered"
    else:
        report_reason = "covered"
    return BoundarySuggestionReport(
        project_root=str(root),
        scanned_files=len(source_files),
        uncovered_files=len(uncovered),
        suggestions=suggestions,
        reason=report_reason,
    )


def format_boundary_suggestions(report: BoundarySuggestionReport) -> str:
    """Human-readable read-only suggestion output."""
    if report.reason == "self_repo":
        return "[dcness boundary] no-op - dcNess self repo 는 boundary override 제안 대상이 아닙니다."
    if not report.suggestions:
        if report.blocking_reasons:
            lines = [
                "[dcness boundary] build-worker boundary 차단 경로:",
            ]
            for path, reason in sorted(report.blocking_reasons.items()):
                lines.append(f"- `{path}`: {reason}")
            lines.extend(
                [
                    "",
                    "ALLOW_MATRIX 미커버 경로는 사람 승인 후 `.dcness/boundary.json` "
                    "build-worker.add override 가 필요합니다.",
                    "INFRA/docs 등 되돌릴 수 없는 deny 경로는 impl 계획 scope 를 수정하세요.",
                ]
            )
            return "\n".join(lines)
        if report.reason == "empty":
            detail = "소스 파일 없음"
        elif report.reason == "impl_plan_scope_ambiguous":
            detail = "impl 계획의 `### 수정 허용` 경로를 확정할 수 없음"
        else:
            detail = "코어 ALLOW_MATRIX 또는 기존 .dcness/boundary.json 으로 모두 커버됨"
        return f"[dcness boundary] no-op - {detail}."

    add_patterns = [item.pattern for item in report.suggestions]
    sample = {"build-worker": {"add": add_patterns}}
    lines = [
        "[dcness boundary] 코어 ALLOW_MATRIX 미커버 경로 후보:",
    ]
    for item in report.suggestions:
        examples = ", ".join(f"`{example}`" for example in item.examples)
        lines.append(
            f"- `{item.directory}` ({item.file_count} files) -> "
            f"`{item.pattern}`; examples: {examples}"
        )
    suggested_paths = {
        example
        for item in report.suggestions
        for example in item.examples
    }
    non_override_blocks = {
        path: reason
        for path, reason in report.blocking_reasons.items()
        if path not in suggested_paths
    }
    if non_override_blocks:
        lines.extend(["", "override 로 열 수 없는 차단 경로:"])
        for path, reason in sorted(non_override_blocks.items()):
            lines.append(f"- `{path}`: {reason}")
    lines.extend(
        [
            "",
            "사람 승인 후에만 `.dcness/boundary.json` 에 add override 를 작성하세요.",
            "",
            json.dumps(sample, ensure_ascii=False, indent=2),
        ]
    )
    return "\n".join(lines)

#!/usr/bin/env python3
"""Measure the one-shot #1089 policy-cleanup baseline at a Git revision.

This is an internal comparison tool, not a CI gate or public plug-in command.
It reads the tracked Git tree so untracked receipts and working-copy files cannot
silently change the baseline.  The optional unit-suite timing must run at the
checked-out revision because tests execute from the working tree.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess  # nosec B404 - argv-only internal git and Python commands
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence


MAJOR_TEXT_SUFFIXES = frozenset(
    {".py", ".mjs", ".js", ".sh", ".md", ".json", ".yml", ".yaml", ".toml"}
)
CODE_ROOTS = frozenset({"harness", "scripts", "evals"})
CLASSIFICATIONS = ("현재 실사용", "제거 가능", "한시적 호환 필요", "퇴역 완료")
AREA_TO_FOLLOW_UP = {
    "design": 1093,
    "run-ledger": 1094,
    "routing": 1095,
    "install-path": 1096,
    "lifecycle": 1097,
}
TRACE_LIST_FIELDS = (
    "current_ssot",
    "implementation",
    "tests_fixtures",
    "docs_distribution",
)
COMPATIBILITY_FIELDS = (
    "consumer_or_format",
    "reason",
    "removal_trigger",
    "verification",
)


def _run_git(repo_root: Path, *args: str) -> bytes:
    return subprocess.run(  # nosec B603, B607
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
    ).stdout


def _tracked_paths(repo_root: Path, revision: str) -> list[str]:
    output = _run_git(repo_root, "ls-tree", "-r", "--name-only", "-z", revision)
    return sorted(
        item.decode("utf-8")
        for item in output.split(b"\0")
        if item
    )


def _blob(repo_root: Path, revision: str, path: str) -> bytes:
    return _run_git(repo_root, "show", f"{revision}:{path}")


def _line_count(content: bytes) -> int:
    if not content:
        return 0
    return content.count(b"\n") + (0 if content.endswith(b"\n") else 1)


def _is_major_text(path: str) -> bool:
    return Path(path).suffix.lower() in MAJOR_TEXT_SUFFIXES


def _is_code(path: str) -> bool:
    parts = Path(path).parts
    return bool(parts) and parts[0] in CODE_ROOTS and Path(path).suffix == ".py"


def _is_test(path: str) -> bool:
    parts = Path(path).parts
    return bool(parts) and parts[0] == "tests" and Path(path).suffix == ".py"


def _count_test_functions(source: bytes, path: str) -> int:
    tree = ast.parse(source.decode("utf-8"), filename=path)
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    )


def measure_revision(repo_root: Path, revision: str) -> dict[str, Any]:
    """Return stable size/count metrics for one tracked Git tree."""
    root = repo_root.resolve()
    resolved_revision = _run_git(root, "rev-parse", revision).decode().strip()
    paths = _tracked_paths(root, resolved_revision)
    major_text_loc = 0
    code_loc = 0
    test_loc = 0
    test_functions = 0
    major_text_lines: list[int] = []

    for path in paths:
        major = _is_major_text(path)
        code = _is_code(path)
        test = _is_test(path)
        if not (major or code or test):
            continue
        content = _blob(root, resolved_revision, path)
        line_count = _line_count(content)
        if major:
            major_text_loc += line_count
            major_text_lines.append(line_count)
        if code:
            code_loc += line_count
        if test:
            test_loc += line_count
            test_functions += _count_test_functions(content, path)

    return {
        "revision": resolved_revision,
        "tracked_files": len(paths),
        "major_text_files": len(major_text_lines),
        "major_text_loc": major_text_loc,
        "code_loc": code_loc,
        "test_loc": test_loc,
        "code_and_test_loc": code_loc + test_loc,
        "files_ge_500_loc": sum(lines >= 500 for lines in major_text_lines),
        "files_ge_1000_loc": sum(lines >= 1000 for lines in major_text_lines),
        "test_functions": test_functions,
    }


def _require_nonempty_string(entry_id: str, entry: dict[str, Any], field: str) -> None:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{entry_id}: {field} must be a non-empty string")


def _require_trace_lists(entry_id: str, entry: dict[str, Any]) -> None:
    for field in TRACE_LIST_FIELDS:
        value = entry.get(field)
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(item, str) or not item.strip() for item in value)
        ):
            raise ValueError(f"{entry_id}: {field} must be a non-empty string list")


def summarize_inventory(entries: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Validate inventory coverage and return comparison counts."""
    seen: set[str] = set()
    by_classification: Counter[str] = Counter()
    by_area: Counter[str] = Counter()
    by_follow_up_issue: Counter[str] = Counter()

    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("inventory entries must be JSON objects")
        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not entry_id.strip():
            raise ValueError("inventory id must be a non-empty string")
        if entry_id in seen:
            raise ValueError(f"duplicate inventory id: {entry_id}")
        seen.add(entry_id)

        _require_nonempty_string(entry_id, entry, "policy_slice")
        _require_nonempty_string(entry_id, entry, "consumer_evidence")
        _require_trace_lists(entry_id, entry)

        area = entry.get("area")
        if area not in AREA_TO_FOLLOW_UP:
            raise ValueError(f"{entry_id}: unknown area: {area!r}")
        expected_issue = AREA_TO_FOLLOW_UP[area]
        if entry.get("follow_up_issue") != expected_issue:
            raise ValueError(
                f"{entry_id}: follow_up_issue must be {expected_issue} for area={area}"
            )

        classification = entry.get("classification")
        if classification not in CLASSIFICATIONS:
            raise ValueError(
                f"{entry_id}: classification must be one of {CLASSIFICATIONS}"
            )

        compatibility = entry.get("compatibility")
        if classification == "한시적 호환 필요":
            if not isinstance(compatibility, dict):
                raise ValueError(f"{entry_id}: compatibility evidence is required")
            for field in COMPATIBILITY_FIELDS:
                _require_nonempty_string(entry_id, compatibility, field)
        elif compatibility not in (None, {}):
            raise ValueError(
                f"{entry_id}: compatibility evidence is only valid for 한시적 호환 필요"
            )

        by_classification[classification] += 1
        by_area[area] += 1
        by_follow_up_issue[str(expected_issue)] += 1

    return {
        "entries_total": len(entries),
        "compatibility_candidates": (
            by_classification["제거 가능"]
            + by_classification["한시적 호환 필요"]
        ),
        "by_classification": {
            name: by_classification[name] for name in CLASSIFICATIONS
        },
        "by_area": dict(sorted(by_area.items())),
        "by_follow_up_issue": dict(sorted(by_follow_up_issue.items())),
    }


def load_inventory(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("inventory schema_version must be 1")
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise ValueError("inventory entries must be a list")
    return entries


def run_unit_suite(repo_root: Path, revision: str) -> dict[str, Any]:
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    command_display = [
        Path(sys.executable).name,
        "-m",
        "unittest",
        "discover",
        "-s",
        "tests",
        "-v",
    ]
    with tempfile.TemporaryDirectory(prefix="dcness-policy-baseline-") as tmp:
        checkout = Path(tmp) / "tree"
        worktree_command = [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "worktree",
            "add",
            "--detach",
            str(checkout),
            revision,
        ]
        subprocess.run(  # nosec B603, B607
            worktree_command,
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
        try:
            started = time.perf_counter()
            completed = subprocess.run(  # nosec B603
                command,
                cwd=checkout,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            elapsed_seconds = round(time.perf_counter() - started, 3)
        finally:
            subprocess.run(  # nosec B603, B607
                [
                    "git",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "worktree",
                    "remove",
                    "--force",
                    str(checkout),
                ],
                cwd=repo_root,
                check=True,
                capture_output=True,
            )
    return {
        "command": " ".join(command_display) + " < /dev/null",
        "tree_mode": "detached_git_worktree",
        "exit_code": completed.returncode,
        "elapsed_seconds": elapsed_seconds,
        "failure_tail": completed.stderr[-4000:] if completed.returncode else "",
    }


def build_report(
    repo_root: Path,
    revision: str,
    inventory_path: Path,
    *,
    include_unit_suite: bool,
) -> dict[str, Any]:
    metrics = measure_revision(repo_root, revision)
    entries = load_inventory(inventory_path)
    report: dict[str, Any] = {
        "schema_version": 1,
        "purpose": "#1089 cleanup before/after comparison baseline",
        "definitions": {
            "tracked_files": "git ls-tree -r --name-only <revision>",
            "major_text_suffixes": sorted(MAJOR_TEXT_SUFFIXES),
            "code_loc": "*.py under harness/, scripts/, and evals/",
            "test_loc": "*.py under tests/",
            "test_functions": "Python AST FunctionDef/AsyncFunctionDef names starting test_",
            "large_files": "major text files with logical LOC >= threshold",
            "compatibility_candidates": "inventory entries classified 제거 가능 or 한시적 호환 필요",
        },
        "metrics": metrics,
        "inventory": summarize_inventory(entries),
    }
    if include_unit_suite:
        report["unit_suite"] = run_unit_suite(repo_root, metrics["revision"])
    return report


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path("docs/internal/policy-sunset-inventory.json"),
    )
    parser.add_argument("--run-unit-suite", action="store_true")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()
    inventory_path = args.inventory
    if not inventory_path.is_absolute():
        inventory_path = repo_root / inventory_path
    report = build_report(
        repo_root,
        args.revision,
        inventory_path,
        include_unit_suite=args.run_unit_suite,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return int(report.get("unit_suite", {}).get("exit_code", 0) != 0)


if __name__ == "__main__":
    raise SystemExit(main())

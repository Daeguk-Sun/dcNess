#!/usr/bin/env python3
"""Deterministic guard-efficacy evaluation suite.

This is a dcNess self-QA command. It exercises existing hook/function entry
points without invoking an LLM, then reports pass/fail counts by guard category.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess  # nosec B404 - deterministic local hook probes only
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Literal
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.agent_boundary import (  # noqa: E402
    check_bash_mutation,
    check_github_mcp_mutation,
    check_write_allowed,
    extract_bash_paths,
)
from harness.hooks import handle_pretooluse_agent  # noqa: E402
from harness.session_state import (  # noqa: E402
    start_run,
    update_current_step,
    update_live,
    write_pid_current_run,
    write_pid_session,
)


Decision = Literal["allow", "block"]
Probe = Callable[[], tuple[Decision, str]]


@dataclass(frozen=True)
class GuardCase:
    id: str
    category: str
    expected: Decision
    description: str
    probe: Probe


@dataclass(frozen=True)
class CaseResult:
    id: str
    category: str
    expected: Decision
    actual: str
    passed: bool
    description: str
    detail: str


@contextlib.contextmanager
def _external_project_boundary() -> Iterable[None]:
    """Force file-boundary probes to behave like an external activated project."""
    with (
        patch("harness.agent_boundary.is_infra_project", return_value=False),
        patch("harness.agent_boundary.is_opt_out", return_value=False),
    ):
        yield


def _reason_decision(reason: str | None) -> tuple[Decision, str]:
    return ("block", reason) if reason else ("allow", "")


def _file_write(agent: str, path: str) -> Probe:
    def probe() -> tuple[Decision, str]:
        with tempfile.TemporaryDirectory() as td, _external_project_boundary():
            return _reason_decision(check_write_allowed(agent, path, cwd=Path(td)))

    return probe


def _bash_mutation(command: str) -> Probe:
    def probe() -> tuple[Decision, str]:
        return _reason_decision(check_bash_mutation(command))

    return probe


def _mcp_mutation(tool_name: str) -> Probe:
    def probe() -> tuple[Decision, str]:
        return _reason_decision(check_github_mcp_mutation(tool_name))

    return probe


def _order_gate(subagent: str, *, current_step: str | None = None) -> Probe:
    def probe() -> tuple[Decision, str]:
        sid = "eval-sid"
        rid = "run-11111111"
        cc_pid = 45678
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            write_pid_session(cc_pid, sid, base_dir=base)
            update_live(sid, base_dir=base)
            start_run(sid, rid, "impl", base_dir=base, lane="lite")
            write_pid_current_run(cc_pid, rid, base_dir=base)
            if current_step:
                update_current_step(sid, rid, current_step, None, base_dir=base)
            payload = {
                "sessionId": sid,
                "tool_input": {"subagent_type": subagent},
            }
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                rc = handle_pretooluse_agent(
                    stdin_data=payload,
                    cc_pid=cc_pid,
                    base_dir=base,
                )
            return ("allow" if rc == 0 else "block", stderr.getvalue().strip())

    return probe


def _write_file(root: Path, rel: str, content: str = "// fixture\n") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _tdd_guard(rel_path: str, *, matching_test: bool = False) -> Probe:
    def probe() -> tuple[Decision, str]:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            target = _write_file(root, rel_path, "export const value = 1;\n")
            if matching_test:
                stem = target.with_suffix("").name
                _write_file(target.parent, f"{stem}.test.ts", "test('ok', () => {})\n")
            payload = {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            }
            result = subprocess.run(
                ["bash", str(ROOT / "hooks" / "tdd-guard.sh")],
                cwd=root,
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=10,
                env={
                    **os.environ,
                    "PYTHONPATH": str(ROOT),
                    "CLAUDE_PLUGIN_ROOT": str(ROOT),
                    "DCNESS_FORCE_ENABLE": "1",
                },
            )
            if result.returncode == 0:
                return ("allow", result.stdout.strip())
            if result.returncode == 2:
                return ("block", result.stderr.strip())
            return ("block", f"unexpected exit {result.returncode}: {result.stderr}")

    return probe


def _bash_write_tdd_boundary() -> tuple[Decision, str]:
    command = "printf 'export const value = 1' > src/untested.ts"
    with tempfile.TemporaryDirectory() as td, _external_project_boundary():
        cwd = Path(td)
        targets = extract_bash_paths(command)
        reasons = [
            check_write_allowed("engineer", target, cwd=cwd, shell_context=True)
            for target in targets
        ]
        blocked = [reason for reason in reasons if reason]
        if blocked:
            return ("block", "\n".join(blocked))
        return (
            "allow",
            "Bash write path is boundary-checked, but matching-test existence is "
            "outside tdd-guard scope.",
        )


def build_cases() -> list[GuardCase]:
    return [
        GuardCase(
            "file_boundary_allows_engineer_src",
            "file-boundary",
            "allow",
            "engineer can write implementation source.",
            _file_write("engineer", "src/service.ts"),
        ),
        GuardCase(
            "file_boundary_blocks_infra",
            "file-boundary",
            "block",
            "engineer cannot write dcNess-controlled hook paths.",
            _file_write("engineer", "hooks/file-guard.sh"),
        ),
        GuardCase(
            "file_boundary_blocks_code_agent_docs",
            "file-boundary",
            "block",
            "code agents cannot write architect-owned docs.",
            _file_write("engineer", "docs/architecture.md"),
        ),
        GuardCase(
            "file_boundary_allows_architect_docs",
            "file-boundary",
            "allow",
            "architect-owned docs remain writable by architect.",
            _file_write("architect", "docs/architecture.md"),
        ),
        GuardCase(
            "bash_mutation_blocks_git_push",
            "bash-mutation",
            "block",
            "direct git push is an external state mutation.",
            _bash_mutation("git push origin main"),
        ),
        GuardCase(
            "bash_mutation_blocks_nested_pr_merge",
            "bash-mutation",
            "block",
            "common shell nesting still exposes gh PR mutation.",
            _bash_mutation("bash -lc 'gh pr merge 12'"),
        ),
        GuardCase(
            "bash_mutation_blocks_gh_api_post",
            "bash-mutation",
            "block",
            "gh api field flags default to mutating POST.",
            _bash_mutation("gh api repos/owner/repo/issues -f title=x"),
        ),
        GuardCase(
            "bash_mutation_allows_readonly_pr_view",
            "bash-mutation",
            "allow",
            "read-only gh commands should not be false positives.",
            _bash_mutation("gh pr view 12 --json title"),
        ),
        GuardCase(
            "mcp_mutation_blocks_pr_merge",
            "mcp-mutation",
            "block",
            "GitHub MCP PR/repo mutation is main-owned.",
            _mcp_mutation("mcp__github__merge_pull_request"),
        ),
        GuardCase(
            "mcp_mutation_allows_read_tool",
            "mcp-mutation",
            "allow",
            "GitHub MCP read tools remain usable.",
            _mcp_mutation("mcp__github__get_pull_request"),
        ),
        GuardCase(
            "mcp_mutation_allows_issue_tool_exception",
            "mcp-mutation",
            "allow",
            "Issue MCP mutations are delegated to per-agent tool grants.",
            _mcp_mutation("mcp__github__update_issue"),
        ),
        GuardCase(
            "order_gate_blocks_missing_begin_step",
            "order-gate",
            "block",
            "strict impl runs require begin-step before Agent calls.",
            _order_gate("code-validator"),
        ),
        GuardCase(
            "order_gate_allows_matching_begin_step",
            "order-gate",
            "allow",
            "Agent call matching current_step is allowed.",
            _order_gate("code-validator", current_step="code-validator"),
        ),
        GuardCase(
            "order_gate_blocks_step_mismatch",
            "order-gate",
            "block",
            "Agent call cannot jump away from current_step.",
            _order_gate("pr-reviewer", current_step="code-validator"),
        ),
        GuardCase(
            "tdd_guard_blocks_impl_without_test",
            "tdd-guard",
            "block",
            "TS/JS implementation edit without matching test is blocked.",
            _tdd_guard("src/price.ts"),
        ),
        GuardCase(
            "tdd_guard_allows_impl_with_test",
            "tdd-guard",
            "allow",
            "Matching sibling test satisfies the TDD guard.",
            _tdd_guard("src/price.ts", matching_test=True),
        ),
        GuardCase(
            "tdd_guard_allows_config_false_positive",
            "tdd-guard",
            "allow",
            "Config files are intentionally outside TDD existence checks.",
            _tdd_guard("babel.config.js"),
        ),
        GuardCase(
            "known_boundary_tdd_bash_write_not_enforced",
            "known-bypass-boundary",
            "allow",
            "Bash-created implementation files are file-boundary checked, not TDD checked.",
            _bash_write_tdd_boundary,
        ),
        GuardCase(
            "known_boundary_command_substitution_not_scanned",
            "known-bypass-boundary",
            "allow",
            "Command substitution is a documented best-effort mutation-denylist boundary.",
            _bash_mutation("echo $(git push origin main)"),
        ),
    ]


def run_cases(cases: Iterable[GuardCase]) -> list[CaseResult]:
    results: list[CaseResult] = []
    for case in cases:
        try:
            actual, detail = case.probe()
        except Exception as exc:  # noqa: BLE001 - eval result should show probe failure
            actual, detail = "error", f"{type(exc).__name__}: {exc}"
        results.append(
            CaseResult(
                id=case.id,
                category=case.category,
                expected=case.expected,
                actual=actual,
                passed=actual == case.expected,
                description=case.description,
                detail=detail,
            )
        )
    return results


def summarize(results: Iterable[CaseResult]) -> dict:
    results = list(results)
    categories: dict[str, dict[str, int]] = {}
    for result in results:
        bucket = categories.setdefault(
            result.category,
            {"passed": 0, "failed": 0, "total": 0},
        )
        bucket["total"] += 1
        bucket["passed" if result.passed else "failed"] += 1
    total = {
        "passed": sum(1 for result in results if result.passed),
        "failed": sum(1 for result in results if not result.passed),
        "total": len(results),
    }
    return {
        "total": total,
        "categories": categories,
        "cases": [
            {
                "id": result.id,
                "category": result.category,
                "expected": result.expected,
                "actual": result.actual,
                "passed": result.passed,
                "description": result.description,
                "detail": result.detail,
            }
            for result in results
        ],
    }


def print_human(report: dict) -> None:
    for category, counts in sorted(report["categories"].items()):
        print(
            f"[guard-efficacy] {category}: "
            f"{counts['passed']}/{counts['total']} passed"
        )
    print(
        f"[guard-efficacy] total: "
        f"{report['total']['passed']}/{report['total']['total']} passed"
    )
    for result in report["cases"]:
        status = "PASS" if result["passed"] else "FAIL"
        print(
            f"  {status} {result['category']}/{result['id']} "
            f"expected={result['expected']} actual={result['actual']}"
        )
        if not result["passed"] and result["detail"]:
            print(f"    {result['detail']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic dcNess guard-efficacy fixtures."
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    report = summarize(run_cases(build_cases()))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_human(report)
    return 1 if report["total"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

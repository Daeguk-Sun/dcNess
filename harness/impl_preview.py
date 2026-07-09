"""Deterministic `/impl` entry preview.

The skill still owns natural-language judgment. This module owns the small,
repeatable mapping from already-classified signals to lane, implementation
owner, review provider, and begin-run command hints.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class ImplPreview:
    route: str
    lane: str | None
    implementation_owner: str
    review_provider: str
    begin_run_args: list[str]
    reasons: list[str]
    next_action: str
    design_doc: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "route": self.route,
            "lane": self.lane,
            "implementation_owner": self.implementation_owner,
            "review_provider": self.review_provider,
            "begin_run_args": self.begin_run_args,
            "reasons": self.reasons,
            "next_action": self.next_action,
            "design_doc": self.design_doc,
        }


def validate_design_doc(value: str, *, cwd: Path | None = None) -> str:
    """Validate the current Standard-entry design-doc surface."""
    cwd = (cwd or Path.cwd()).resolve()
    raw = Path(value)
    path = raw if raw.is_absolute() else cwd / raw
    if not path.is_file():
        raise ValueError(f"design_doc not found: {value}")
    rel = path.resolve().relative_to(cwd)
    parts = rel.parts
    if (
        len(parts) < 5
        or parts[0] != "docs"
        or parts[1] != "epics"
        or "impl" not in parts[2:-1]
        or rel.suffix != ".md"
    ):
        raise ValueError(
            "design_doc must be under docs/epics/**/impl/*.md: "
            f"{rel.as_posix()}"
        )
    return rel.as_posix()


def build_preview(
    *,
    design_doc: str | None = None,
    cwd: Path | None = None,
    concrete: bool = False,
    natural_language_only: bool = False,
    ambiguous: bool = False,
    needs_design: bool = False,
    workflow_risk: str = "normal",
    skip_design: bool = False,
    review_provider: str = "configured",
) -> ImplPreview:
    cwd = cwd or Path.cwd()
    reasons: list[str] = []
    normalized_doc: str | None = None

    if design_doc:
        normalized_doc = validate_design_doc(design_doc, cwd=cwd)
        route = "standard"
        lane = "standard"
        begin_run_args = ["begin-run", "impl", "--design-doc", normalized_doc]
        next_action = "start Standard implementation with the supplied design doc"
        reasons.append("design_doc present")
    elif skip_design:
        route = "lite"
        lane = "lite"
        begin_run_args = ["begin-run", "impl", "--lane", "lite"]
        next_action = "start Lite implementation; user explicitly skipped design"
        reasons.append("user skip-design override")
    elif workflow_risk == "high":
        route = "outside-design"
        lane = None
        begin_run_args = []
        next_action = "run /design or /spec before /impl"
        reasons.append("workflow risk=high")
    elif natural_language_only:
        route = "issue-intake"
        lane = None
        begin_run_args = []
        next_action = "ask whether to create a GitHub issue via /to-issue before implementation"
        reasons.append("natural language only; no concrete signal")
    elif needs_design:
        route = "outside-design"
        lane = None
        begin_run_args = []
        next_action = "run /design before /impl"
        reasons.append("implementation boundary or acceptance is not concrete")
    elif ambiguous:
        route = "clarify"
        lane = None
        begin_run_args = []
        next_action = "clarify target, scope, and success criteria"
        reasons.append("target or success criteria ambiguous")
    elif concrete:
        route = "lite"
        lane = "lite"
        begin_run_args = ["begin-run", "impl", "--lane", "lite"]
        next_action = "start Lite implementation"
        reasons.append("concrete signal present and no design_doc")
    else:
        route = "issue-intake"
        lane = None
        begin_run_args = []
        next_action = "ask whether to create a GitHub issue via /to-issue before implementation"
        reasons.append("no design_doc and no concrete signal")

    reasons.append("implementation owner=main")
    reasons.append(f"review provider={review_provider}")
    return ImplPreview(
        route=route,
        lane=lane,
        implementation_owner="main",
        review_provider=review_provider,
        begin_run_args=begin_run_args,
        reasons=reasons,
        next_action=next_action,
        design_doc=normalized_doc,
    )


def format_preview(preview: ImplPreview) -> str:
    lines = [
        f"route: {preview.route}",
        f"lane: {preview.lane or '-'}",
        f"implementation_owner: {preview.implementation_owner}",
        f"review_provider: {preview.review_provider}",
    ]
    if preview.begin_run_args:
        lines.append("begin-run: dcness-helper " + " ".join(preview.begin_run_args))
    else:
        lines.append("begin-run: -")
    lines.append(f"next: {preview.next_action}")
    lines.append("reasons:")
    lines.extend(f"- {reason}" for reason in preview.reasons)
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preview deterministic /impl routing.")
    parser.add_argument("--design-doc", default=None)
    parser.add_argument("--cwd", default=None)
    parser.add_argument("--concrete", action="store_true")
    parser.add_argument("--natural-language-only", action="store_true")
    parser.add_argument("--ambiguous", action="store_true")
    parser.add_argument("--needs-design", action="store_true")
    parser.add_argument("--workflow-risk", choices=["normal", "high"], default="normal")
    parser.add_argument("--skip-design", action="store_true")
    parser.add_argument("--review-provider", choices=["claude", "codex", "configured"], default="configured")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    cwd = Path(args.cwd).resolve() if args.cwd else Path.cwd()
    try:
        preview = build_preview(
            design_doc=args.design_doc,
            cwd=cwd,
            concrete=args.concrete,
            natural_language_only=args.natural_language_only,
            ambiguous=args.ambiguous,
            needs_design=args.needs_design,
            workflow_risk=args.workflow_risk,
            skip_design=args.skip_design,
            review_provider=args.review_provider,
        )
    except ValueError as exc:
        parser.exit(1, f"impl-preview: {exc}\n")
        return 1
    if args.json:
        print(json.dumps(preview.to_dict(), ensure_ascii=False))
    else:
        print(format_preview(preview))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

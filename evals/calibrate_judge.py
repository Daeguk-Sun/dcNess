#!/usr/bin/env python3
"""Compare saved eval judge output with human golden labels (#894)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_MIN_AGREEMENT = 1.0
LABEL_RE = re.compile(r"^\s*(?:[-*]\s*)?(OK|MISS)\s+(\S+)(?:\s.*)?$")
RESULT_RE = re.compile(r"^\s*RESULT:\s*(PASS|FAIL)\s*$")
VALID_EXPECTATION_LABELS = {"OK", "MISS"}
VALID_RESULTS = {"PASS", "FAIL"}


@dataclass(frozen=True)
class GoldenLabel:
    case: str
    run: int | None
    judge_file: str | None
    expectations: dict[str, str]
    result: str | None


@dataclass(frozen=True)
class JudgeOutput:
    expectations: dict[str, str]
    result: str | None


def _clean_expectation_id(raw: str) -> str:
    return raw.strip().strip("`").strip().strip("[]").strip(",:;.").strip()


def _normalize_expectation_label(raw: Any, *, field: str) -> str:
    value = str(raw or "").strip().upper()
    if value not in VALID_EXPECTATION_LABELS:
        raise ValueError(f"{field}: label must be OK or MISS")
    return value


def _normalize_result(raw: Any, *, field: str) -> str:
    value = str(raw or "").strip().upper()
    if value not in VALID_RESULTS:
        raise ValueError(f"{field}: result must be PASS or FAIL")
    return value


def parse_judge_output(text: str) -> JudgeOutput:
    expectations: dict[str, str] = {}
    result: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        result_match = RESULT_RE.match(line)
        if result_match:
            result = result_match.group(1)
            continue
        label_match = LABEL_RE.match(line)
        if not label_match:
            continue
        label = label_match.group(1)
        expectation_id = _clean_expectation_id(label_match.group(2))
        if not expectation_id:
            continue
        expectations[expectation_id] = label
    return JudgeOutput(expectations=expectations, result=result)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read golden labels: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in golden labels: {path}: {exc}") from exc


def load_golden_labels(path: Path) -> list[GoldenLabel]:
    payload = _load_json(path)
    if isinstance(payload, list):
        raw_labels = payload
    elif isinstance(payload, dict):
        raw_labels = payload.get("labels")
    else:
        raw_labels = None
    if not isinstance(raw_labels, list):
        raise ValueError("golden labels must be a JSON object with a labels array")

    labels: list[GoldenLabel] = []
    for idx, raw_item in enumerate(raw_labels, start=1):
        field = f"labels[{idx}]"
        if not isinstance(raw_item, dict):
            raise ValueError(f"{field}: must be an object")
        case = str(raw_item.get("case") or "").strip()
        if not case:
            raise ValueError(f"{field}.case is required")

        judge_file_raw = raw_item.get("judge_file")
        judge_file = str(judge_file_raw).strip() if judge_file_raw else None

        run: int | None = None
        if raw_item.get("run") is not None:
            try:
                run = int(raw_item["run"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field}.run must be a positive integer") from exc
            if run <= 0:
                raise ValueError(f"{field}.run must be a positive integer")
        if not judge_file and run is None:
            raise ValueError(f"{field}: either run or judge_file is required")

        raw_expectations = raw_item.get("expectations")
        if not isinstance(raw_expectations, dict) or not raw_expectations:
            raise ValueError(f"{field}.expectations must be a non-empty object")
        expectations = {
            _clean_expectation_id(str(expectation_id)): _normalize_expectation_label(
                label,
                field=f"{field}.expectations.{expectation_id}",
            )
            for expectation_id, label in raw_expectations.items()
        }
        if any(not expectation_id for expectation_id in expectations):
            raise ValueError(f"{field}.expectations contains an empty expectation id")

        result = None
        if raw_item.get("result") is not None:
            result = _normalize_result(raw_item["result"], field=f"{field}.result")

        labels.append(
            GoldenLabel(
                case=case,
                run=run,
                judge_file=judge_file,
                expectations=expectations,
                result=result,
            )
        )
    return labels


def _judge_path(run_dir: Path, label: GoldenLabel) -> Path:
    if label.judge_file:
        path = Path(label.judge_file)
        return path if path.is_absolute() else run_dir / path
    assert label.run is not None
    return run_dir / label.case / f"run-{label.run}-judge.md"


def _label_name(label: GoldenLabel) -> str:
    if label.run is not None:
        return f"{label.case} run {label.run}"
    return f"{label.case} {label.judge_file}"


def _derived_result(expectations: dict[str, str]) -> str:
    return "PASS" if all(label == "OK" for label in expectations.values()) else "FAIL"


def calibrate(
    run_dir: Path,
    golden_labels: list[GoldenLabel],
    *,
    min_agreement: float,
) -> dict[str, Any]:
    matches = 0
    comparisons = 0
    mismatches: list[dict[str, Any]] = []
    missing_artifacts: list[str] = []
    artifacts: list[dict[str, Any]] = []

    for label in golden_labels:
        path = _judge_path(run_dir, label)
        name = _label_name(label)
        if not path.is_file():
            missing_artifacts.append(str(path))
            continue
        actual = parse_judge_output(path.read_text(encoding="utf-8"))
        artifact_matches = 0
        artifact_comparisons = 0

        for expectation_id, human_label in sorted(label.expectations.items()):
            comparisons += 1
            artifact_comparisons += 1
            judge_label = actual.expectations.get(expectation_id, "MISSING")
            if judge_label == human_label:
                matches += 1
                artifact_matches += 1
                continue
            mismatches.append(
                {
                    "artifact": name,
                    "expectation": expectation_id,
                    "human": human_label,
                    "judge": judge_label,
                    "judge_file": str(path),
                }
            )

        expected_result = label.result or _derived_result(label.expectations)
        comparisons += 1
        artifact_comparisons += 1
        judge_result = actual.result or "MISSING"
        if judge_result == expected_result:
            matches += 1
            artifact_matches += 1
        else:
            mismatches.append(
                {
                    "artifact": name,
                    "expectation": "RESULT",
                    "human": expected_result,
                    "judge": judge_result,
                    "judge_file": str(path),
                }
            )

        artifacts.append(
            {
                "artifact": name,
                "judge_file": str(path),
                "matches": artifact_matches,
                "comparisons": artifact_comparisons,
            }
        )

    agreement = (matches / comparisons) if comparisons else 0.0
    return {
        "run_dir": str(run_dir),
        "threshold": min_agreement,
        "agreement": agreement,
        "totals": {"matches": matches, "comparisons": comparisons},
        "judge_review_candidate": agreement < min_agreement,
        "mismatches": mismatches,
        "missing_artifacts": missing_artifacts,
        "artifacts": artifacts,
        "note": "No judge settings were changed.",
    }


def format_report(report: dict[str, Any]) -> str:
    totals = report["totals"]
    matches = int(totals["matches"])
    comparisons = int(totals["comparisons"])
    agreement = float(report["agreement"])
    threshold = float(report["threshold"])
    lines = [
        "[judge calibration]",
        f"run_dir: {report['run_dir']}",
        f"agreement: {matches}/{comparisons} ({agreement:.1%})",
        f"threshold: {threshold:.1%}",
        f"judge_review_candidate: {'YES' if report['judge_review_candidate'] else 'no'}",
    ]
    artifacts = report.get("artifacts")
    if isinstance(artifacts, list) and artifacts:
        lines.append("artifacts:")
        for artifact in artifacts:
            lines.append(
                f"- {artifact['artifact']}: "
                f"{artifact['matches']}/{artifact['comparisons']} "
                f"({artifact['judge_file']})"
            )
    missing = report.get("missing_artifacts")
    if isinstance(missing, list) and missing:
        lines.append("missing_artifacts:")
        for path in missing:
            lines.append(f"- {path}")
    mismatches = report.get("mismatches")
    if isinstance(mismatches, list) and mismatches:
        lines.append("mismatches:")
        for mismatch in mismatches:
            lines.append(
                f"- {mismatch['artifact']} {mismatch['expectation']}: "
                f"human={mismatch['human']} judge={mismatch['judge']} "
                f"({mismatch['judge_file']})"
            )
    else:
        lines.append("mismatches: none")
    lines.append(str(report["note"]))
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare saved eval run-N-judge.md files with human golden labels."
    )
    parser.add_argument("run_dir", help="eval output directory, e.g. .metrics/evals/run-...")
    parser.add_argument(
        "--golden",
        default="",
        help="golden JSON path; defaults to <run_dir>/judge-golden.json",
    )
    parser.add_argument(
        "--min-agreement",
        type=float,
        default=DEFAULT_MIN_AGREEMENT,
        help="minimum acceptable agreement ratio, 0.0-1.0 (default: 1.0)",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--report-file", default="", help="also write a markdown report")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    run_dir = Path(args.run_dir).resolve()
    golden_path = Path(args.golden).resolve() if args.golden else run_dir / "judge-golden.json"
    if args.min_agreement < 0.0 or args.min_agreement > 1.0:
        parser.error("--min-agreement must be between 0.0 and 1.0")

    try:
        labels = load_golden_labels(golden_path)
        report = calibrate(run_dir, labels, min_agreement=float(args.min_agreement))
    except ValueError as exc:
        print(f"[judge calibration] ERROR: {exc}", file=sys.stderr)
        return 2

    if int(report["totals"]["comparisons"]) == 0:
        print("[judge calibration] ERROR: no comparison labels found", file=sys.stderr)
        return 2
    if report["missing_artifacts"]:
        output = json.dumps(report, ensure_ascii=False, indent=2) if args.json else format_report(report)
        print(output)
        return 2

    text_report = format_report(report)
    if args.report_file:
        report_path = Path(args.report_file)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text_report + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(text_report)
    return 1 if report["judge_review_candidate"] else 0


if __name__ == "__main__":
    sys.exit(main())

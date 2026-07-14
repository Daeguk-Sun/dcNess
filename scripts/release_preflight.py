#!/usr/bin/env python3
"""Run dcNess release evidence checks once, in an auditable fixed order."""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess  # nosec B404 - fixed, versioned internal command lists only
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_AXES = [
    "guard",
    "core_behavior",
    "judge_calibration",
    "product_outcome",
    "agent_effectiveness",
    "lightweight_decision",
    "public_evidence",
    "bundle_consumer",
]


class PreflightError(RuntimeError):
    """The release preflight configuration itself is invalid."""


def _latest_agent_effectiveness_record() -> Path:
    directory = ROOT / "evals" / "agent-effectiveness"
    candidates = sorted(directory.glob("*real*.json"), key=lambda path: path.stat().st_mtime)
    if candidates:
        return candidates[-1]
    return directory / "cartography-sanity-real.json"


def _latest_lightweight_record() -> Path:
    runtime = ROOT / ".metrics" / "harness-experiments"
    candidates = sorted(runtime.glob("**/record.json"), key=lambda path: path.stat().st_mtime)
    if candidates:
        return candidates[-1]
    return ROOT / "evals" / "lean-ablation" / "tool-repeat-lesson-metadata.json"


def _default_steps(output_dir: Path) -> list[dict[str, Any]]:
    python = sys.executable
    effectiveness_record = _latest_agent_effectiveness_record()
    lightweight_record = _latest_lightweight_record()
    product_scorecard = [
        python,
        str(ROOT / "harness" / "outcome_scorecard.py"),
        "--json",
    ]
    empty_projects = output_dir / "agent-effectiveness-projects.json"
    empty_projects.parent.mkdir(parents=True, exist_ok=True)
    empty_projects.write_text(
        json.dumps({"version": 1, "projects": []}) + "\n", encoding="utf-8"
    )
    effectiveness_scorecard = [
        python,
        str(ROOT / "harness" / "outcome_scorecard.py"),
        "--projects-file",
        str(empty_projects),
        "--agent-effectiveness-record",
        str(effectiveness_record),
        "--json",
    ]
    return [
        {
            "id": "guard",
            "command": [python, str(ROOT / "evals" / "guard_efficacy.py"), "--json"],
            "required": True,
        },
        {
            "id": "core_behavior",
            "command": ["bash", str(ROOT / "evals" / "run-core.sh")],
            "required": True,
            "env": {"EVAL_OUTPUT_DIR": str(output_dir / "core-behavior")},
        },
        {
            "id": "judge_calibration",
            "command": [
                python,
                str(ROOT / "evals" / "calibrate_judge.py"),
                str(ROOT / "evals" / "calibration" / "core-incidents-v1"),
                "--golden",
                str(ROOT / "evals" / "golden" / "core-incidents-v1.json"),
                "--expect-golden-version",
                "core-incidents-v1-human-v1",
                "--expect-subset-version",
                "core-incidents-v1",
            ],
            "required": True,
        },
        {
            "id": "product_outcome",
            "command": product_scorecard,
            "required": True,
        },
        {
            "id": "agent_effectiveness",
            "command": effectiveness_scorecard,
            "required": True,
        },
        {
            "id": "lightweight_decision",
            "command": [
                python,
                str(ROOT / "evals" / "lean_ablation.py"),
                str(lightweight_record),
                "--json",
            ],
            "required": True,
        },
        {
            "id": "public_evidence",
            "command": ["node", str(ROOT / "scripts" / "check_public_evidence.mjs")],
            "required": True,
        },
        {
            "id": "bundle_consumer",
            "command": [
                python,
                str(ROOT / "scripts" / "release_artifact.py"),
                "smoke",
                "--repo-root",
                str(ROOT),
                "--ref",
                "HEAD",
            ],
            "required": True,
        },
    ]


def _load_config(path: Path | None, output_dir: Path) -> list[dict[str, Any]]:
    if path is None:
        return _default_steps(output_dir)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PreflightError(f"config_unreadable: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise PreflightError("config_schema_version_must_be_one")
    steps = payload.get("steps")
    if not isinstance(steps, list) or not all(isinstance(step, dict) for step in steps):
        raise PreflightError("config_steps_must_be_array")
    return steps


def _validate_steps(steps: list[dict[str, Any]]) -> None:
    ids = [str(step.get("id") or "") for step in steps]
    if ids != EXPECTED_AXES:
        raise PreflightError(
            "release_axes_must_match_fixed_order:" + ",".join(EXPECTED_AXES)
        )
    for step in steps:
        command = step.get("command")
        if not isinstance(command, list) or not command or not all(
            isinstance(item, str) and item for item in command
        ):
            raise PreflightError(f"{step['id']}_command_must_be_string_array")
        if not isinstance(step.get("required"), bool):
            raise PreflightError(f"{step['id']}_required_must_be_boolean")
        env = step.get("env", {})
        if not isinstance(env, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in env.items()
        ):
            raise PreflightError(f"{step['id']}_env_must_be_string_object")


def _run_step(
    step: dict[str, Any], *, index: int, output_dir: Path, timeout: int
) -> dict[str, Any]:
    env = os.environ.copy()
    env.update(step.get("env", {}))
    started = datetime.datetime.now(datetime.timezone.utc)
    timed_out = False
    try:
        # Commands come from the versioned default or an explicit self-operator config.
        result = subprocess.run(  # nosec B603
            step["command"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
        returncode = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = 124
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        stderr += f"\npreflight step timed out after {timeout}s"
    finished = datetime.datetime.now(datetime.timezone.utc)
    stem = f"{index:02d}-{step['id']}"
    stdout_path = output_dir / f"{stem}.stdout.log"
    stderr_path = output_dir / f"{stem}.stderr.log"
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    return {
        "id": step["id"],
        "required": step["required"],
        "status": "PASS" if returncode == 0 else "FAIL",
        "returncode": returncode,
        "timed_out": timed_out,
        "duration_seconds": round((finished - started).total_seconds(), 3),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# dcNess release preflight",
        "",
        f"- 실행 시각: `{report['measured_at']}`",
        f"- 릴리즈 가능: {'YES' if report['releasable'] else 'NO'}",
        "",
        "| evidence 축 | 결과 | 종료코드 | 로그 |",
        "|---|---|---:|---|",
    ]
    for step in report["steps"]:
        lines.append(
            f"| {step['id']} | {step['status']} | {step['returncode']} | "
            f"`{step['stdout_log']}` |"
        )
    lines.extend(
        [
            "",
            (
                "사람 개입은 저장된 evidence 사이의 불일치나 새 사람 판정이 "
                "남았을 때만 필요합니다."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    steps = _load_config(args.config.resolve() if args.config else None, output_dir)
    _validate_steps(steps)
    results = [
        _run_step(step, index=index, output_dir=output_dir, timeout=args.timeout)
        for index, step in enumerate(steps, start=1)
    ]
    failed_required = [
        row["id"] for row in results if row["required"] and row["status"] != "PASS"
    ]
    report = {
        "schema_version": 1,
        "measured_at": datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "releasable": not failed_required,
        "failed_required": failed_required,
        "steps": results,
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "report.md").write_text(_render_markdown(report), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / ".metrics" / "release-preflight" / timestamp,
    )
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run(args)
    except PreflightError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_render_markdown(report), end="")
    return 0 if report["releasable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

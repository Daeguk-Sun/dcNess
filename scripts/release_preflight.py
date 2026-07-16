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
    "product_outcome_snapshot",
    "agent_effectiveness",
    "lightweight_decision",
    "public_evidence",
    "bundle_consumer",
]
MAX_AUTOMATED_BEHAVIOR_TRIALS = 4
MAX_DIAGNOSTIC_RUNS_PER_CASE = 2
PRODUCT_OUTCOME_INTERPRETATION = (
    "snapshot_collection_only_not_current_product_success"
)


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


def _core_behavior_cases() -> list[str]:
    manifest = ROOT / "evals" / "core-incident-subset.json"
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PreflightError(f"core_behavior_manifest_unreadable: {exc}") from exc
    selected = payload.get("selected_cases") if isinstance(payload, dict) else None
    if not isinstance(selected, list):
        raise PreflightError("core_behavior_selected_cases_must_be_array")
    cases = [item.get("case") for item in selected if isinstance(item, dict)]
    if (
        not cases
        or len(cases) != len(selected)
        or not all(isinstance(case, str) and case for case in cases)
        or len(set(cases)) != len(cases)
    ):
        raise PreflightError("core_behavior_cases_must_be_unique_nonempty_strings")
    if len(cases) > MAX_AUTOMATED_BEHAVIOR_TRIALS:
        raise PreflightError("core_behavior_cases_exceed_automatic_trial_budget")
    return cases


def _default_steps(output_dir: Path) -> list[dict[str, Any]]:
    python = sys.executable
    effectiveness_record = _latest_agent_effectiveness_record()
    lightweight_record = _latest_lightweight_record()
    behavior_cases = _core_behavior_cases()
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
            "diagnostic_command": ["bash", str(ROOT / "evals" / "run.sh")],
            "behavior_cases": behavior_cases,
            "required": True,
            "env": {
                "EVAL_OUTPUT_DIR": str(output_dir / "core-behavior" / "initial"),
                "EVAL_RUNS": "1",
            },
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
            "id": "product_outcome_snapshot",
            "command": product_scorecard,
            "required": True,
            "description": (
                "Collect the raw historical product outcome scorecard snapshot; "
                "command success is not a current product success verdict."
            ),
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
        behavior_cases = step.get("behavior_cases")
        diagnostic_command = step.get("diagnostic_command")
        if behavior_cases is None and diagnostic_command is None:
            continue
        if step["id"] != "core_behavior":
            raise PreflightError("behavior_diagnostics_only_allowed_for_core_behavior")
        if (
            not isinstance(behavior_cases, list)
            or not behavior_cases
            or not all(isinstance(case, str) and case for case in behavior_cases)
            or len(set(behavior_cases)) != len(behavior_cases)
        ):
            raise PreflightError("core_behavior_cases_must_be_unique_nonempty_strings")
        if len(behavior_cases) > MAX_AUTOMATED_BEHAVIOR_TRIALS:
            raise PreflightError("core_behavior_cases_exceed_automatic_trial_budget")
        if (
            not isinstance(diagnostic_command, list)
            or not diagnostic_command
            or not all(
                isinstance(item, str) and item for item in diagnostic_command
            )
        ):
            raise PreflightError("core_behavior_diagnostic_command_must_be_string_array")
        if env.get("EVAL_RUNS") != "1":
            raise PreflightError("core_behavior_initial_eval_runs_must_be_one")


def _run_step(
    step: dict[str, Any],
    *,
    index: int,
    output_dir: Path,
    timeout: int,
    stem_suffix: str = "",
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
    stem = f"{index:02d}-{step['id']}{stem_suffix}"
    stdout_path = output_dir / f"{stem}.stdout.log"
    stderr_path = output_dir / f"{stem}.stderr.log"
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    row = {
        "id": step["id"],
        "required": step["required"],
        "status": "PASS" if returncode == 0 else "FAIL",
        "returncode": returncode,
        "timed_out": timed_out,
        "duration_seconds": round((finished - started).total_seconds(), 3),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
    }
    if description := step.get("description"):
        row["description"] = description
    if step["id"] == "product_outcome_snapshot":
        row.update(
            {
                "snapshot_collection_succeeded": returncode == 0,
                "interpretation": PRODUCT_OUTCOME_INTERPRETATION,
            }
        )
    return row


def _judge_passed(output_dir: Path, case: str, run_index: int = 1) -> bool:
    judge_path = output_dir / case / f"run-{run_index}-judge.md"
    try:
        lines = judge_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    verdicts = [
        line.strip()
        for line in lines
        if line.strip() in {"RESULT: PASS", "RESULT: FAIL"}
    ]
    return bool(verdicts) and verdicts[-1] == "RESULT: PASS"


def _attach_behavior_trials(
    step: dict[str, Any],
    result: dict[str, Any],
    *,
    diagnose_core_misses: bool,
    index: int,
    output_dir: Path,
    timeout: int,
) -> None:
    cases = step.get("behavior_cases")
    if not isinstance(cases, list):
        return
    initial_output = Path(step["env"]["EVAL_OUTPUT_DIR"])
    initial_failed = [case for case in cases if not _judge_passed(initial_output, case)]
    initial_trial_count = len(cases)
    diagnostic_runs = 0
    diagnostic_trial_count = 0
    diagnostic_output: Path | None = None
    diagnostic_result: dict[str, Any] | None = None

    remaining_budget = MAX_AUTOMATED_BEHAVIOR_TRIALS - initial_trial_count
    if diagnose_core_misses and initial_failed and remaining_budget > 0:
        diagnostic_runs = min(
            MAX_DIAGNOSTIC_RUNS_PER_CASE,
            remaining_budget // len(initial_failed),
        )
        if diagnostic_runs > 0:
            diagnostic_output = initial_output.parent / "diagnostic"
            diagnostic_step = {
                "id": "core_behavior_diagnostic",
                "command": step["diagnostic_command"],
                "required": False,
                "env": {
                    **step.get("env", {}),
                    "EVAL_CASES": " ".join(initial_failed),
                    "EVAL_STRICT_CASES": " ".join(initial_failed),
                    "EVAL_RELEASE_CHECK": "1",
                    "EVAL_RUNS": str(diagnostic_runs),
                    "EVAL_OUTPUT_DIR": str(diagnostic_output),
                },
            }
            diagnostic_result = _run_step(
                diagnostic_step,
                index=index,
                output_dir=output_dir,
                timeout=timeout,
                stem_suffix="-diagnostic",
            )
            diagnostic_trial_count = len(initial_failed) * diagnostic_runs

    release_failure_latched = result["status"] != "PASS" or bool(initial_failed)
    if release_failure_latched:
        result["status"] = "FAIL"
    result["behavior_trials"] = {
        "automatic_trial_limit": MAX_AUTOMATED_BEHAVIOR_TRIALS,
        "initial_trial_count": initial_trial_count,
        "initial_output_dir": str(initial_output),
        "initial_failed_cases": initial_failed,
        "diagnostic_requested": diagnose_core_misses,
        "diagnostic_cases": initial_failed if diagnostic_trial_count else [],
        "diagnostic_runs_per_case": diagnostic_runs,
        "diagnostic_trial_count": diagnostic_trial_count,
        "diagnostic_output_dir": (
            str(diagnostic_output) if diagnostic_output is not None else None
        ),
        "diagnostic_command_result": diagnostic_result,
        "total_trial_count": initial_trial_count + diagnostic_trial_count,
        "release_failure_latched": release_failure_latched,
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
        display_status = step["status"]
        if step["id"] == "product_outcome_snapshot":
            display_status = (
                "SNAPSHOT COLLECTED"
                if step["snapshot_collection_succeeded"]
                else "SNAPSHOT COLLECTION FAILED"
            )
        lines.append(
            f"| {step['id']} | {display_status} | {step['returncode']} | "
            f"`{step['stdout_log']}` |"
        )
    core = next((step for step in report["steps"] if step["id"] == "core_behavior"), None)
    if core and "behavior_trials" in core:
        trials = core["behavior_trials"]
        lines.extend(
            [
                "",
                (
                    "- 행동 eval 자동 trial: "
                    f"`{trials['total_trial_count']}/{trials['automatic_trial_limit']}` "
                    f"(초기 `{trials['initial_trial_count']}`, "
                    f"추가 진단 `{trials['diagnostic_trial_count']}`)"
                ),
                (
                    "- 최초 MISS release FAIL 고정: "
                    f"`{'YES' if trials['release_failure_latched'] else 'NO'}`"
                ),
            ]
        )
    lines.extend(
        [
            "",
            (
                "`product_outcome_snapshot`의 command 성공은 기존 scorecard의 raw historical "
                "ratio·`측정 불가`·한계를 snapshot으로 수집했다는 뜻이며, 현재 제품 성공률이나 "
                "제품 PASS 판정이 아닙니다."
            ),
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
    results = []
    for index, step in enumerate(steps, start=1):
        result = _run_step(
            step, index=index, output_dir=output_dir, timeout=args.timeout
        )
        if step["id"] == "core_behavior":
            _attach_behavior_trials(
                step,
                result,
                diagnose_core_misses=args.diagnose_core_misses,
                index=index,
                output_dir=output_dir,
                timeout=args.timeout,
            )
        results.append(result)
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
    parser.add_argument(
        "--diagnose-core-misses",
        action="store_true",
        help=(
            "After an initial core MISS, use the remaining automatic four-trial "
            "budget for failed-case diagnosis without changing the release FAIL."
        ),
    )
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

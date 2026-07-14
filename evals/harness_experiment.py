#!/usr/bin/env python3
"""Run an approved, budget-capped harness-lightweight experiment.

This is an internal dcNess operator tool. /run-review owns the user approval; this
runner owns frozen inputs, isolated baseline/variant execution, raw trace provenance,
quality/cost comparison, and the monthly four-trial ceiling.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import sys
import uuid
from argparse import Namespace
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = (
    Path.home()
    / ".claude"
    / "plugins"
    / "data"
    / "dcness-dcness"
    / "harness-experiments"
    / "trial-ledger.jsonl"
)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals import agent_effectiveness_measure as execution  # noqa: E402
from evals.lean_ablation import ALLOWED_METRICS, evaluate  # noqa: E402


MONTHLY_CAP = 4
HARD_GUARDS = ["order", "file-boundary", "external-state", "tdd"]


class ExperimentError(RuntimeError):
    """The approved experiment could not safely produce a valid record."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExperimentError(f"plan_unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise ExperimentError("plan_must_be_object")
    return payload


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ExperimentError(f"{key}_required")
    return value


def _validate_plan(plan: dict[str, Any]) -> None:
    if plan.get("schema_version") != 1:
        raise ExperimentError("unsupported_plan_schema_version")
    if plan.get("safety_class") != "optional":
        raise ExperimentError("candidate_must_be_optional")
    candidate = plan.get("candidate")
    if not isinstance(candidate, dict):
        raise ExperimentError("candidate_must_be_object")
    _required_text(candidate, "id")
    _required_text(candidate, "component")
    _required_text(candidate, "optional_reason")
    telemetry = candidate.get("telemetry")
    if not isinstance(telemetry, dict) or not str(telemetry.get("pattern") or "").strip():
        raise ExperimentError("candidate_telemetry_required")
    for field in ("count", "finished_run_denominator", "source_project_count"):
        value = telemetry.get(field)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or value <= 0
        ):
            raise ExperimentError(f"candidate_telemetry_{field}_must_be_positive")
    metric = _required_text(candidate, "expected_saving_metric")
    if metric not in ALLOWED_METRICS:
        raise ExperimentError("unsupported_expected_saving_metric")
    threshold = candidate.get("meaningful_reduction")
    if not isinstance(threshold, dict):
        raise ExperimentError("meaningful_reduction_must_be_object")
    absolute = threshold.get("absolute")
    relative = threshold.get("relative")
    if (
        not isinstance(absolute, (int, float))
        or isinstance(absolute, bool)
        or absolute <= 0
        or not isinstance(relative, (int, float))
        or isinstance(relative, bool)
        or not 0 < relative < 1
    ):
        raise ExperimentError("meaningful_reduction_threshold_invalid")
    provider = plan.get("provider")
    if not isinstance(provider, dict):
        raise ExperimentError("provider_must_be_object")
    _required_text(provider, "name")
    _required_text(provider, "model")
    _required_text(plan, "task")
    _required_text(plan, "baseline_condition")
    _required_text(plan, "variant_condition")
    month = _required_text(plan, "execution_month")
    if (
        len(month) != 7
        or month[4] != "-"
        or not month[:4].isdigit()
        or not month[5:].isdigit()
        or not 1 <= int(month[5:]) <= 12
    ):
        raise ExperimentError("execution_month_invalid")
    fixture = Path(_required_text(plan, "fixture_source")).expanduser().resolve()
    if not fixture.is_dir():
        raise ExperimentError("fixture_source_must_be_directory")


def _read_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _used_trials(path: Path, month: str) -> int:
    return sum(
        1
        for row in _read_ledger(path)
        if row.get("execution_month") == month
        and row.get("kind") in {None, "trial_started"}
    )


def _append_ledger(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _start_trial(
    path: Path, *, month: str, candidate_id: str, pair: int, variant: str
) -> str:
    attempt_id = str(uuid.uuid4())
    payload = {
        "kind": "trial_started",
        "execution_month": month,
        "candidate_id": candidate_id,
        "pair": pair,
        "variant": variant,
        "attempt_id": attempt_id,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            stream.seek(0)
            used = 0
            for line in stream:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    isinstance(row, dict)
                    and row.get("execution_month") == month
                    and row.get("kind") in {None, "trial_started"}
                ):
                    used += 1
            if used + 1 > MONTHLY_CAP:
                raise ExperimentError("monthly_trial_cap_exceeded")
            stream.seek(0, os.SEEK_END)
            stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    return attempt_id


def _finish_trial(
    path: Path, *, month: str, attempt_id: str, trial: dict[str, Any]
) -> None:
    payload = {
        "kind": "trial_result",
        "execution_month": month,
        "candidate_id": trial["task_id"],
        "variant": trial["variant"],
        "attempt_id": attempt_id,
        "run_id": trial["run_id"],
        "raw_trace_sha256": trial["raw_trace_sha256"],
    }
    _append_ledger(path, payload)


def _rebuild_used_before(
    path: Path, month: str, trials: list[dict[str, Any]]
) -> int:
    rows = [
        row for row in _read_ledger(path) if row.get("execution_month") == month
    ]
    trace_hashes = {str(trial["raw_trace_sha256"]) for trial in trials}
    own_attempts = {
        str(row.get("attempt_id"))
        for row in rows
        if row.get("kind") == "trial_result"
        and row.get("raw_trace_sha256") in trace_hashes
        and row.get("attempt_id")
    }
    return sum(
        1
        for row in rows
        if row.get("kind") in {None, "trial_started"}
        and not (
            row.get("kind") == "trial_started"
            and str(row.get("attempt_id")) in own_attempts
        )
        and not (
            row.get("kind") is None
            and row.get("raw_trace_sha256") in trace_hashes
        )
    )


def _tree_hashes(directory: Path) -> dict[str, str]:
    return {
        str(path.relative_to(directory)): _sha256(path)
        for path in sorted(item for item in directory.rglob("*") if item.is_file())
    }


def _materialize(plan: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    fixture = output_dir / "fixture"
    fixture_source = Path(plan["fixture_source"]).expanduser().resolve()
    if not fixture.exists():
        shutil.copytree(fixture_source, fixture)
    elif not fixture.is_dir() or _tree_hashes(fixture) != _tree_hashes(fixture_source):
        raise ExperimentError("materialized_fixture_drift")
    task = output_dir / "task.md"
    baseline = output_dir / "baseline-prompt.md"
    variant = output_dir / "variant-prompt.md"
    task.write_text(str(plan["task"]).strip() + "\n", encoding="utf-8")
    baseline.write_text(
        str(plan["baseline_condition"]).strip() + "\n", encoding="utf-8"
    )
    variant.write_text(
        str(plan["variant_condition"]).strip() + "\n", encoding="utf-8"
    )
    if baseline.stat().st_size <= variant.stat().st_size:
        raise ExperimentError("variant_condition_must_be_smaller_than_baseline")
    return {
        "fixture": fixture,
        "task": task,
        "baseline": baseline,
        "variant": variant,
    }


def _prompt(task: str, condition: str) -> str:
    return (
        condition.strip()
        + "\n\n"
        + task.strip()
        + "\n\n"
        + "격리 fixture만 읽고 live 프로젝트나 외부 상태를 변경하지 마세요. "
        + "마지막 응답은 다음 필드를 가진 JSON code block으로 끝내세요: "
        + 'product_ac {passed,total}, must_fix_count, regression_count, '
        + "human_recovery_count. 관측하지 않은 품질 항목을 성공으로 만들지 마세요."
    )


def _quality_answer(parsed: dict[str, Any]) -> dict[str, Any]:
    answer = parsed.get("answer")
    if not isinstance(answer, dict):
        raise ExperimentError("trial_result_json_required")
    product_ac = answer.get("product_ac")
    if not isinstance(product_ac, dict):
        raise ExperimentError("trial_product_ac_required")
    required_numbers = (
        product_ac.get("passed"),
        product_ac.get("total"),
        answer.get("must_fix_count"),
        answer.get("regression_count"),
        answer.get("human_recovery_count"),
    )
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in required_numbers):
        raise ExperimentError("trial_quality_counts_must_be_integers")
    return answer


def _trial_from_trace(
    *,
    trace: Path,
    variant: str,
    plan: dict[str, Any],
    task_path: Path,
    expected_prompt_sha256: str,
) -> dict[str, Any]:
    parsed = execution.parse_trace(trace)
    answer = _quality_answer(parsed)
    provider = plan["provider"]
    actual_model = str(parsed["model"] or "").strip()
    if not actual_model:
        raise ExperimentError("trial_model_required")
    actual_prompt_sha256 = str(parsed["meta"].get("prompt_sha256") or "")
    if actual_prompt_sha256 != expected_prompt_sha256:
        raise ExperimentError("trace_prompt_sha256_mismatch")
    trace_sha = _sha256(trace)
    artifact = trace.with_name(f"{trace.stem}-artifact.json")
    artifact.write_text(
        json.dumps(answer, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    usage = parsed["usage"]
    return {
        "variant": variant,
        "task_id": str(plan["candidate"]["id"]),
        "input_sha256": _sha256(task_path),
        "prompt_sha256": expected_prompt_sha256,
        "model": actual_model,
        "requested_model": str(provider["model"]),
        "provider": execution.EXECUTION_PROVIDER,
        "requested_provider": str(provider["name"]),
        "run_id": str(parsed["session_id"]),
        "raw_trace": str(trace.resolve()),
        "raw_trace_sha256": trace_sha,
        "read_trace": parsed["visits"],
        "artifact": str(artifact.resolve()),
        "artifact_sha256": _sha256(artifact),
        "product_ac": answer["product_ac"],
        "must_fix_count": answer["must_fix_count"],
        "regression_count": answer["regression_count"],
        "human_intervention_count": answer["human_recovery_count"],
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "wall_clock_seconds": float(parsed["wall_clock_seconds"]),
        "cost_usd": float(parsed["total_cost_usd"]),
        "evidence": str(trace.resolve()),
        "evidence_sha256": trace_sha,
    }


def _quality_worse(baseline: dict[str, Any], variant: dict[str, Any]) -> bool:
    baseline_ac = baseline["product_ac"]
    variant_ac = variant["product_ac"]
    return bool(
        variant_ac["total"] != baseline_ac["total"]
        or variant_ac["passed"] < baseline_ac["passed"]
        or variant["must_fix_count"] > baseline["must_fix_count"]
        or variant["regression_count"] > baseline["regression_count"]
        or variant["human_intervention_count"]
        > baseline["human_intervention_count"]
    )


def _decision(candidate: dict[str, Any], trials: list[dict[str, Any]]) -> str:
    metric = str(candidate["expected_saving_metric"])
    baselines = trials[0::2]
    variants = trials[1::2]
    if any(_quality_worse(left, right) for left, right in zip(baselines, variants)):
        return "keep"
    baseline_mean = sum(float(row[metric]) for row in baselines) / len(baselines)
    variant_mean = sum(float(row[metric]) for row in variants) / len(variants)
    reduction = baseline_mean - variant_mean
    relative = reduction / baseline_mean if baseline_mean > 0 else 0.0
    threshold = candidate["meaningful_reduction"]
    if reduction <= 0:
        return "keep"
    if reduction >= float(threshold["absolute"]) and relative >= float(
        threshold["relative"]
    ):
        return "remove"
    return "hold" if len(trials) == 4 else "additional_pair_required"


def _run_pair(
    *,
    pair: int,
    plan: dict[str, Any],
    paths: dict[str, Path],
    output_dir: Path,
    timeout: int,
    from_traces: bool,
    ledger: Path,
) -> list[dict[str, Any]]:
    trials: list[dict[str, Any]] = []
    for variant in ("baseline", "variant"):
        trace = output_dir / f"pair{pair}-{variant}.jsonl"
        attempt_id = ""
        if not from_traces:
            attempt_id = _start_trial(
                ledger,
                month=str(plan["execution_month"]),
                candidate_id=str(plan["candidate"]["id"]),
                pair=pair,
                variant=variant,
            )
            args = Namespace(
                output_dir=output_dir,
                model=plan["provider"]["model"],
                timeout=timeout,
                fixture_dir=paths["fixture"],
            )
            condition = paths[variant].read_text(encoding="utf-8")
            trace = execution.run_agent(
                f"pair{pair}",
                variant,
                _prompt(paths["task"].read_text(encoding="utf-8"), condition),
                args,
            )
        if not trace.is_file():
            raise ExperimentError(f"trace_missing:{trace}")
        trial = _trial_from_trace(
            trace=trace,
            variant=variant,
            plan=plan,
            task_path=paths["task"],
            expected_prompt_sha256=hashlib.sha256(
                _prompt(
                    paths["task"].read_text(encoding="utf-8"),
                    paths[variant].read_text(encoding="utf-8"),
                ).encode("utf-8")
            ).hexdigest(),
        )
        trials.append(trial)
        if not from_traces:
            _finish_trial(
                ledger,
                month=str(plan["execution_month"]),
                attempt_id=attempt_id,
                trial=trial,
            )
    return trials


def _fixture_hashes(fixture: Path) -> dict[str, str]:
    return {
        str(path.resolve()): _sha256(path)
        for path in sorted(item for item in fixture.rglob("*") if item.is_file())
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    plan = _load_object(args.plan.resolve())
    _validate_plan(plan)
    month = str(plan["execution_month"])
    ledger = args.ledger.resolve()
    used_before = _used_trials(ledger, month)
    if not args.from_traces and used_before + 2 > MONTHLY_CAP:
        raise ExperimentError("monthly_trial_cap_exceeded")

    output_dir = args.output_dir.resolve()
    paths = _materialize(plan, output_dir)
    trials = _run_pair(
        pair=1,
        plan=plan,
        paths=paths,
        output_dir=output_dir,
        timeout=args.timeout,
        from_traces=args.from_traces,
        ledger=ledger,
    )
    decision = _decision(plan["candidate"], trials)
    if decision == "additional_pair_required":
        if not args.from_traces and used_before + 4 > MONTHLY_CAP:
            raise ExperimentError("monthly_trial_cap_exceeded")
        trials.extend(
            _run_pair(
                pair=2,
                plan=plan,
                paths=paths,
                output_dir=output_dir,
                timeout=args.timeout,
                from_traces=args.from_traces,
                ledger=ledger,
            )
        )
        decision = _decision(plan["candidate"], trials)
    if args.from_traces:
        used_before = _rebuild_used_before(ledger, month, trials)
        if used_before + len(trials) > MONTHLY_CAP:
            raise ExperimentError("monthly_trial_cap_exceeded")

    baseline = paths["baseline"]
    variant = paths["variant"]
    record = {
        "schema_version": 2,
        "candidate": plan["candidate"],
        "safety": {
            "hard_guards_excluded": HARD_GUARDS,
            "live_hard_guard_disabled": False,
        },
        "deterministic": {
            "passed": True,
            "command": "python3.11 evals/harness_experiment.py --plan <plan>",
            "baseline_prompt_path": str(baseline),
            "baseline_prompt_sha256": _sha256(baseline),
            "baseline_prompt_bytes": baseline.stat().st_size,
            "variant_prompt_path": str(variant),
            "variant_prompt_sha256": _sha256(variant),
            "variant_prompt_bytes": variant.stat().st_size,
            "fixture_hashes": _fixture_hashes(paths["fixture"]),
        },
        "shadow": {
            "passed": True,
            "live_product_affected": False,
            "baseline_prompt_sha256": _sha256(baseline),
            "variant_prompt_sha256": _sha256(variant),
        },
        "budget": {
            "execution_month": month,
            "monthly_cap": MONTHLY_CAP,
            "used_before": used_before,
        },
        "paired_screening": {
            "task_path": str(paths["task"]),
            "task_sha256": _sha256(paths["task"]),
            "trials": trials,
        },
        "decision": decision,
        "follow_up": "승인된 후보의 다음 Decide 단계에서 이 판정을 사용한다.",
        "limitations": [
            "격리 fixture의 개인 판단용 paired screening",
            "공개 우위 주장 근거가 아님",
        ],
    }
    report, errors = evaluate(record)
    if errors:
        raise ExperimentError("record_validation_failed:" + ",".join(errors))
    (output_dir / "record.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report["decision_label"] = {
        "keep": "유지",
        "remove": "줄이기 후보",
        "hold": "보류",
    }[str(report["decision"])]
    report["record"] = str(output_dir / "record.json")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--ledger",
        type=Path,
        default=DEFAULT_LEDGER,
    )
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--from-traces", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run(args)
    except ExperimentError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"{report['status']} {report['candidate_id']}: "
            f"{report['decision_label']} ({report['trial_count']} trial)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate one evidence-backed, budget-capped lean ablation record.

This is an internal evaluation surface, not a plugin command. It keeps the
deterministic-first, shadow-only safety, paired-screening budget, and
keep/remove/hold decision rules executable without invoking an LLM itself.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ALLOWED_DECISIONS = {"keep", "remove", "hold"}
ALLOWED_METRICS = {
    "input_tokens",
    "output_tokens",
    "wall_clock_seconds",
    "human_intervention_count",
}
REQUIRED_HARD_GUARDS = {"order", "file-boundary", "external-state", "tdd"}
ROOT = Path(__file__).resolve().parents[1]


def _mapping(value: Any, field: str, errors: list[str]) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    errors.append(f"{field}_must_be_object")
    return {}


def _number(value: Any, field: str, errors: list[str]) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    errors.append(f"{field}_must_be_number")
    return 0.0


def _verify_artifact(
    path_value: Any,
    expected_sha: Any,
    expected_bytes: Any,
    field: str,
    errors: list[str],
) -> None:
    if not isinstance(path_value, str) or not path_value:
        return
    path = ROOT / path_value
    try:
        content = path.read_bytes()
    except OSError:
        errors.append(f"{field}_artifact_unreadable")
        return
    actual_sha = hashlib.sha256(content).hexdigest()
    if expected_sha and actual_sha != expected_sha:
        errors.append(f"{field}_sha256_mismatch")
    if expected_bytes is not None and len(content) != int(expected_bytes):
        errors.append(f"{field}_byte_count_mismatch")


def _trial_quality(trial: dict[str, Any], errors: list[str], index: int) -> tuple:
    product_ac = _mapping(trial.get("product_ac"), f"trial_{index}_product_ac", errors)
    passed = _number(product_ac.get("passed"), f"trial_{index}_ac_passed", errors)
    total = _number(product_ac.get("total"), f"trial_{index}_ac_total", errors)
    must_fix = _number(
        trial.get("must_fix_count"), f"trial_{index}_must_fix_count", errors
    )
    regressions = _number(
        trial.get("regression_count"), f"trial_{index}_regression_count", errors
    )
    human = _number(
        trial.get("human_intervention_count"),
        f"trial_{index}_human_intervention_count",
        errors,
    )
    if passed < 0 or total <= 0 or passed > total:
        errors.append(f"trial_{index}_invalid_product_ac")
    if min(must_fix, regressions, human) < 0:
        errors.append(f"trial_{index}_negative_quality_count")
    return passed, total, must_fix, regressions, human


def _candidate_contract(
    record: dict[str, Any], errors: list[str]
) -> tuple[dict[str, Any], str, float, float]:
    candidate = _mapping(record.get("candidate"), "candidate", errors)
    telemetry = _mapping(candidate.get("telemetry"), "candidate_telemetry", errors)
    if telemetry.get("pattern") != "TOOL_REPEAT_HIGH":
        errors.append("candidate_not_linked_to_tool_repeat_high")
    if _number(telemetry.get("count"), "telemetry_count", errors) <= 0:
        errors.append("telemetry_count_must_be_positive")
    if _number(
        telemetry.get("finished_run_denominator"),
        "telemetry_finished_run_denominator",
        errors,
    ) <= 0:
        errors.append("telemetry_denominator_must_be_positive")
    if _number(
        telemetry.get("source_project_count"),
        "telemetry_source_project_count",
        errors,
    ) <= 0:
        errors.append("telemetry_source_count_must_be_positive")
    if not str(candidate.get("optional_reason") or "").strip():
        errors.append("optional_reason_required")

    metric = candidate.get("expected_saving_metric")
    if metric not in ALLOWED_METRICS:
        errors.append("unsupported_expected_saving_metric")
        metric = "input_tokens"
    threshold = _mapping(
        candidate.get("meaningful_reduction"), "meaningful_reduction", errors
    )
    absolute_threshold = _number(
        threshold.get("absolute"), "meaningful_reduction_absolute", errors
    )
    relative_threshold = _number(
        threshold.get("relative"), "meaningful_reduction_relative", errors
    )
    if absolute_threshold <= 0 or not 0 < relative_threshold < 1:
        errors.append("meaningful_reduction_threshold_invalid")
    return candidate, str(metric), absolute_threshold, relative_threshold


def _setup_contract(
    record: dict[str, Any], errors: list[str]
) -> tuple[float, float, str, int, int]:
    safety = _mapping(record.get("safety"), "safety", errors)
    excluded = set(safety.get("hard_guards_excluded") or [])
    missing_guards = sorted(REQUIRED_HARD_GUARDS - excluded)
    if missing_guards:
        errors.append("hard_guard_exclusions_missing:" + ",".join(missing_guards))
    if safety.get("live_hard_guard_disabled") is not False:
        errors.append("live_hard_guard_disabled")

    deterministic = _mapping(record.get("deterministic"), "deterministic", errors)
    if deterministic.get("passed") is not True:
        errors.append("deterministic_fixture_not_passed")
    baseline_bytes = _number(
        deterministic.get("baseline_prompt_bytes"),
        "deterministic_baseline_prompt_bytes",
        errors,
    )
    variant_bytes = _number(
        deterministic.get("variant_prompt_bytes"),
        "deterministic_variant_prompt_bytes",
        errors,
    )
    if baseline_bytes <= variant_bytes:
        errors.append("deterministic_variant_not_smaller")

    _verify_artifact(
        deterministic.get("baseline_prompt_path"),
        deterministic.get("baseline_prompt_sha256"),
        deterministic.get("baseline_prompt_bytes"),
        "baseline_prompt",
        errors,
    )
    _verify_artifact(
        deterministic.get("variant_prompt_path"),
        deterministic.get("variant_prompt_sha256"),
        deterministic.get("variant_prompt_bytes"),
        "variant_prompt",
        errors,
    )
    fixture_hashes = deterministic.get("fixture_hashes")
    if isinstance(fixture_hashes, dict):
        for fixture_path, expected_sha in fixture_hashes.items():
            _verify_artifact(
                fixture_path,
                expected_sha,
                None,
                "fixture_" + str(fixture_path).replace("/", "_"),
                errors,
            )

    shadow = _mapping(record.get("shadow"), "shadow", errors)
    if shadow.get("passed") is not True:
        errors.append("shadow_comparison_not_passed")
    if shadow.get("live_product_affected") is not False:
        errors.append("shadow_affected_live_product")

    budget = _mapping(record.get("budget"), "budget", errors)
    execution_month = str(budget.get("execution_month") or "")
    if len(execution_month) != 7 or execution_month[4:5] != "-":
        errors.append("execution_month_invalid")
    cap = int(_number(budget.get("monthly_cap"), "monthly_cap", errors))
    used_before = int(_number(budget.get("used_before"), "used_before", errors))
    if cap != 4:
        errors.append("monthly_cap_must_equal_four")
    if used_before < 0:
        errors.append("used_before_negative")
    if budget.get("agent_effectiveness_screening_month") == execution_month:
        errors.append("same_month_agent_effectiveness_screening")
    return baseline_bytes, variant_bytes, execution_month, cap, used_before


def _collect_trials(
    record: dict[str, Any], metric: str, errors: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    screening = _mapping(record.get("paired_screening"), "paired_screening", errors)
    trials_raw = screening.get("trials")
    trials = trials_raw if isinstance(trials_raw, list) else []
    if not isinstance(trials_raw, list):
        errors.append("paired_screening_trials_must_be_array")
    baselines: list[dict[str, Any]] = []
    variants: list[dict[str, Any]] = []
    conditions: set[tuple[Any, Any, Any, Any]] = set()
    for index, raw in enumerate(trials):
        trial = _mapping(raw, f"trial_{index}", errors)
        variant = trial.get("variant")
        if variant not in {"baseline", "variant"}:
            errors.append(f"trial_{index}_variant_invalid")
        elif variant == "baseline":
            baselines.append(trial)
        else:
            variants.append(trial)
        conditions.add(
            (
                trial.get("task_id"),
                trial.get("input_sha256"),
                trial.get("model"),
                trial.get("provider"),
            )
        )
        if not str(trial.get("evidence") or "").strip():
            errors.append(f"trial_{index}_evidence_required")
        _trial_quality(trial, errors, index)
        _number(trial.get(str(metric)), f"trial_{index}_{metric}", errors)
    if len(conditions) != 1:
        errors.append("paired_conditions_mismatch")
    if len(baselines) != len(variants) or len(baselines) not in {1, 2}:
        errors.append("baseline_variant_count_mismatch")
    return baselines, variants


def _variant_quality_worse(
    baselines: list[dict[str, Any]],
    variants: list[dict[str, Any]],
    errors: list[str],
) -> bool:
    quality_worse = False
    for index, (baseline, variant) in enumerate(zip(baselines, variants)):
        b_quality = _trial_quality(baseline, errors, index * 2)
        v_quality = _trial_quality(variant, errors, index * 2 + 1)
        b_passed, b_total, b_must_fix, b_regressions, b_human = b_quality
        v_passed, v_total, v_must_fix, v_regressions, v_human = v_quality
        if (
            v_total != b_total
            or v_passed < b_passed
            or v_must_fix > b_must_fix
            or v_regressions > b_regressions
            or v_human > b_human
        ):
            quality_worse = True
    return quality_worse


def _screening_contract(
    record: dict[str, Any],
    metric: str,
    absolute_threshold: float,
    relative_threshold: float,
    cap: int,
    used_before: int,
    errors: list[str],
) -> dict[str, Any]:
    baselines, variants = _collect_trials(record, metric, errors)
    trial_count = len(baselines) + len(variants)
    if trial_count not in {2, 4}:
        errors.append("trial_count_must_be_two_or_four")
    epic_total = used_before + trial_count
    if epic_total > cap:
        errors.append("monthly_trial_cap_exceeded")
    quality_worse = _variant_quality_worse(baselines, variants, errors)
    baseline_values = [float(trial.get(str(metric), 0)) for trial in baselines]
    variant_values = [float(trial.get(str(metric), 0)) for trial in variants]
    baseline_mean = sum(baseline_values) / len(baseline_values) if baselines else 0.0
    variant_mean = sum(variant_values) / len(variant_values) if variants else 0.0
    absolute_reduction = baseline_mean - variant_mean
    relative_reduction = (
        absolute_reduction / baseline_mean if baseline_mean > 0 else 0.0
    )
    meaningful = (
        absolute_reduction >= absolute_threshold
        and relative_reduction >= relative_threshold
    )

    if quality_worse or absolute_reduction <= 0:
        derived_decision = "keep"
    elif meaningful:
        derived_decision = "remove"
    elif trial_count == 2:
        derived_decision = "additional_pair_required"
        errors.append("additional_pair_required")
    else:
        derived_decision = "hold"
    return {
        "trial_count": trial_count,
        "epic_total": epic_total,
        "quality_worse": quality_worse,
        "baseline_mean": baseline_mean,
        "variant_mean": variant_mean,
        "absolute_reduction": absolute_reduction,
        "relative_reduction": relative_reduction,
        "derived_decision": derived_decision,
    }


def _validate_recorded_decision(
    record: dict[str, Any], derived_decision: str, errors: list[str]
) -> tuple[Any, list[Any]]:
    recorded_decision = record.get("decision")
    if recorded_decision not in ALLOWED_DECISIONS:
        errors.append("recorded_decision_invalid")
    elif derived_decision in ALLOWED_DECISIONS and recorded_decision != derived_decision:
        errors.append(
            f"recorded_decision_mismatch:{recorded_decision}!={derived_decision}"
        )
    if not str(record.get("follow_up") or "").strip():
        errors.append("follow_up_required")
    limitations = record.get("limitations")
    if not isinstance(limitations, list) or not limitations:
        errors.append("limitations_required")
    return recorded_decision, limitations if isinstance(limitations, list) else []


def evaluate(record: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if record.get("schema_version") != 1:
        errors.append("unsupported_schema_version")

    candidate, metric, absolute_threshold, relative_threshold = _candidate_contract(
        record, errors
    )
    baseline_bytes, variant_bytes, execution_month, cap, used_before = (
        _setup_contract(record, errors)
    )
    screening = _screening_contract(
        record,
        metric,
        absolute_threshold,
        relative_threshold,
        cap,
        used_before,
        errors,
    )
    derived_decision = str(screening["derived_decision"])
    recorded_decision, limitations = _validate_recorded_decision(
        record, derived_decision, errors
    )

    report = {
        "candidate_id": candidate.get("id"),
        "decision": (
            derived_decision if derived_decision in ALLOWED_DECISIONS else recorded_decision
        ),
        "trial_count": screening["trial_count"],
        "epic_monthly_trial_total": screening["epic_total"],
        "execution_month": execution_month,
        "quality_worse": screening["quality_worse"],
        "metric": metric,
        "baseline_mean": screening["baseline_mean"],
        "variant_mean": screening["variant_mean"],
        "absolute_reduction": screening["absolute_reduction"],
        "relative_reduction": screening["relative_reduction"],
        "deterministic_prompt_bytes_saved": baseline_bytes - variant_bytes,
        "limitations": limitations,
        "status": "PASS" if not errors else "FAIL",
    }
    return report, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="validate one lean ablation record")
    parser.add_argument("record", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.record.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"record_unreadable: {exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("record_must_be_object", file=sys.stderr)
        return 2

    report, errors = evaluate(payload)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"{report['status']} {report['candidate_id']}: {report['decision']} "
            f"({report['trial_count']} trial, {report['metric']} "
            f"{report['relative_reduction']:.1%})"
        )
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

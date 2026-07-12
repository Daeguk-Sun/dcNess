"""Validate deterministic agent-effectiveness replay evidence.

The record keeps navigation/change evidence separate from process ledgers and product
journey receipts.  It does not invoke an agent or an LLM; it only replays frozen,
evidence-backed observations and derives comparable metrics.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TASK_TYPES = {"cold_start", "refactor_replacement"}
EXPECTED_VARIANTS = ["baseline", "current"]
COORDINATE_KEYS = {"ssot", "runtime_entrypoint", "capability_owner", "decision"}
CLASSIFICATIONS = {"stale_old_path", "framework_reachable", "intentional_seam"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_MONTHLY_CAP = 4
MONTHLY_CAP_EXCEPTIONS = {"2026-07": {6}}
LIVE_PROVENANCE_RUNS = {
    "cold-start.baseline",
    "cold-start.current",
    "refactor.baseline",
    "refactor.current",
}
PRIVATE_TRACE_INIT_FIELDS = {"agents", "plugins", "skills", "slash_commands", "uuid"}
HOST_HOME_PATH_RE = re.compile(r"(?:/Users/|/home/|\\\\Users\\\\)")


class AgentEffectivenessRecordInvalid(ValueError):
    """Raised when a replay record cannot support the claimed comparison."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def _mapping(value: Any, field: str, errors: list[str]) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    errors.append(f"{field}_must_be_object")
    return {}


def _list(value: Any, field: str, errors: list[str]) -> list[Any]:
    if isinstance(value, list):
        return value
    errors.append(f"{field}_must_be_array")
    return []


def _text(value: Any, field: str, errors: list[str]) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    errors.append(f"{field}_required")
    return ""


def _number(value: Any, field: str, errors: list[str]) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return float(value)
    errors.append(f"{field}_must_be_nonnegative_number")
    return 0.0


def _integer(value: Any, field: str, errors: list[str]) -> int:
    number = _number(value, field, errors)
    if not number.is_integer():
        errors.append(f"{field}_must_be_integer")
    return int(number)


def _optional_integer(value: Any, field: str, errors: list[str]) -> int | None:
    if value is None:
        return None
    return _integer(value, field, errors)


def _verify_fixtures(
    fixtures: Any, fixture_root: Path, errors: list[str]
) -> set[str]:
    if not isinstance(fixtures, dict):
        errors.append("fixtures_must_be_object")
        return set()
    if not fixtures:
        errors.append("fixtures_required")
        return set()
    verified: set[str] = set()
    for relative, expected_sha in fixtures.items():
        if not isinstance(relative, str) or not relative:
            errors.append("fixture_path_required")
            continue
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            errors.append(f"fixture_path_must_be_relative:{relative}")
            continue
        if not isinstance(expected_sha, str) or not SHA256_RE.fullmatch(expected_sha):
            errors.append(f"fixture_sha256_invalid:{relative}")
            continue
        try:
            content = (fixture_root / relative_path).read_bytes()
        except OSError:
            errors.append(f"fixture_unreadable:{relative}")
            continue
        actual_sha = hashlib.sha256(content).hexdigest()
        if actual_sha != expected_sha:
            errors.append(f"fixture_sha256_mismatch:{relative}")
            continue
        verified.add(relative)
    return verified


def _quality(raw: Any, prefix: str, errors: list[str]) -> dict[str, Any]:
    quality = _mapping(raw, f"{prefix}_quality", errors)
    product_ac = _mapping(quality.get("product_ac"), f"{prefix}_product_ac", errors)
    passed = _integer(product_ac.get("passed"), f"{prefix}_product_ac_passed", errors)
    total = _integer(product_ac.get("total"), f"{prefix}_product_ac_total", errors)
    if total <= 0 or passed > total:
        errors.append(f"{prefix}_product_ac_invalid")
    result = {
        "product_ac": {"passed": passed, "total": total},
        "must_fix_count": _optional_integer(
            quality.get("must_fix_count"), f"{prefix}_must_fix_count", errors
        ),
        "regression_count": _optional_integer(
            quality.get("regression_count"), f"{prefix}_regression_count", errors
        ),
        "human_recovery_count": _optional_integer(
            quality.get("human_recovery_count"),
            f"{prefix}_human_recovery_count",
            errors,
        ),
        "context_rework_count": _optional_integer(
            quality.get("context_rework_count"),
            f"{prefix}_context_rework_count",
            errors,
        ),
        "cross_session_resume": quality.get("cross_session_resume"),
    }
    if result["cross_session_resume"] is not None and not isinstance(
        result["cross_session_resume"], bool
    ):
        errors.append(f"{prefix}_cross_session_resume_must_be_boolean")
        result["cross_session_resume"] = None
    return result


def _cost(raw: Any, prefix: str, errors: list[str]) -> dict[str, Any]:
    cost = _mapping(raw, f"{prefix}_cost", errors)
    return {
        "input_tokens": _integer(
            cost.get("input_tokens"), f"{prefix}_input_tokens", errors
        ),
        "output_tokens": _integer(
            cost.get("output_tokens"), f"{prefix}_output_tokens", errors
        ),
        "cost_usd": _number(cost.get("cost_usd"), f"{prefix}_cost_usd", errors),
        "basis": _text(cost.get("basis"), f"{prefix}_cost_basis", errors),
    }


def _quality_worse(baseline: dict[str, Any], current: dict[str, Any]) -> bool:
    baseline_ac = baseline["product_ac"]
    current_ac = current["product_ac"]
    if baseline_ac["total"] != current_ac["total"]:
        return True
    if current_ac["passed"] < baseline_ac["passed"]:
        return True
    for field in (
        "must_fix_count",
        "regression_count",
        "human_recovery_count",
        "context_rework_count",
    ):
        if (baseline[field] is None) != (current[field] is None):
            return True
        if baseline[field] is not None and current[field] > baseline[field]:
            return True
    if (baseline["cross_session_resume"] is None) != (
        current["cross_session_resume"] is None
    ):
        return True
    return bool(
        baseline["cross_session_resume"] is True
        and current["cross_session_resume"] is False
    )


def _cold_metrics(
    task: dict[str, Any],
    run: dict[str, Any],
    prefix: str,
    fixture_paths: set[str],
    errors: list[str],
) -> dict[str, Any]:
    expected = _mapping(
        task.get("expected_coordinates"), f"{prefix}_expected_coordinates", errors
    )
    if set(expected) != COORDINATE_KEYS:
        errors.append(f"{prefix}_coordinate_keys_invalid")
    reported = _mapping(
        run.get("reported_coordinates"), f"{prefix}_reported_coordinates", errors
    )
    matched = [key for key in COORDINATE_KEYS if reported.get(key) == expected.get(key)]
    if run.get("variant") == "current":
        if set(reported) != COORDINATE_KEYS:
            errors.append("current_coordinate_keys_invalid")
        for key in sorted(COORDINATE_KEYS - set(matched)):
            errors.append(f"current_coordinate_mismatch:{key}")

    visited = _list(run.get("visited"), f"{prefix}_visited", errors)
    expected_paths = {value for value in expected.values() if isinstance(value, str)}
    visited_paths: list[str] = []
    read_bytes = 0
    first_correct_ms: int | None = None
    first_correct_tool_count: int | None = None
    first_correct_read_bytes: int | None = None
    previous_elapsed = -1
    for index, raw_event in enumerate(visited):
        event = _mapping(raw_event, f"{prefix}_visited_{index}", errors)
        path = _text(event.get("path"), f"{prefix}_visited_{index}_path", errors)
        _text(event.get("tool"), f"{prefix}_visited_{index}_tool", errors)
        read_bytes += _integer(
            event.get("bytes"), f"{prefix}_visited_{index}_bytes", errors
        )
        elapsed = _integer(
            event.get("elapsed_ms"), f"{prefix}_visited_{index}_elapsed_ms", errors
        )
        if run.get("variant") == "current" and elapsed < previous_elapsed:
            errors.append("current_elapsed_not_monotonic")
        previous_elapsed = elapsed
        visited_paths.append(path)
        if path not in fixture_paths:
            errors.append(f"{prefix}_visited_fixture_missing:{path}")
        if path == expected.get("capability_owner") and first_correct_ms is None:
            first_correct_ms = elapsed
            first_correct_tool_count = index + 1
            first_correct_read_bytes = read_bytes
    missing_route = sorted(expected_paths - set(visited_paths))
    if run.get("variant") == "current" and missing_route:
        errors.append("current_expected_route_not_visited")
    wrong_paths = [path for path in visited_paths if path not in expected_paths]
    quality = _quality(run.get("quality"), prefix, errors)
    return {
        "coordinate_accuracy": f"{len(matched)}/{len(COORDINATE_KEYS)}",
        "tool_calls": _integer(run.get("tool_calls"), f"{prefix}_tool_calls", errors),
        "read_bytes": read_bytes,
        "wrong_path_count": len(wrong_paths),
        "wrong_paths": wrong_paths,
        "first_correct_target_ms": first_correct_ms,
        "first_correct_target_tool_count": first_correct_tool_count,
        "first_correct_target_read_bytes": first_correct_read_bytes,
        "missing_route": missing_route,
        "quality": quality,
        "cost": _cost(run.get("cost"), prefix, errors),
    }


def _refactor_metrics(
    task: dict[str, Any],
    run: dict[str, Any],
    prefix: str,
    fixture_paths: set[str],
    errors: list[str],
) -> dict[str, Any]:
    expected = _mapping(
        task.get("expected_classifications"),
        f"{prefix}_expected_classifications",
        errors,
    )
    for path, classification in expected.items():
        if not isinstance(path, str) or classification not in CLASSIFICATIONS:
            errors.append(f"{prefix}_expected_classification_invalid")
    reported = _mapping(
        run.get("classifications"), f"{prefix}_classifications", errors
    )
    for path in reported:
        if path not in fixture_paths:
            errors.append(f"{prefix}_classification_fixture_missing:{path}")
    matches = sum(1 for path, value in expected.items() if reported.get(path) == value)
    excess_classifications = sorted(set(reported) - set(expected))
    if run.get("variant") == "current":
        if set(reported) != set(expected):
            errors.append("current_classification_scope_mismatch")
        for path, value in sorted(expected.items()):
            if reported.get(path) != value:
                errors.append(f"current_classification_mismatch:{path}")

    expected_impact = set(
        str(item)
        for item in _list(task.get("expected_impact"), f"{prefix}_expected_impact", errors)
    )
    observed_impact = set(
        str(item)
        for item in _list(run.get("observed_impact"), f"{prefix}_observed_impact", errors)
    )
    for path in observed_impact:
        if path not in fixture_paths:
            errors.append(f"{prefix}_impact_fixture_missing:{path}")
    missed = sorted(expected_impact - observed_impact)
    excess = sorted(observed_impact - expected_impact)
    if run.get("variant") == "current" and (missed or excess):
        errors.append("current_impact_scope_mismatch")
    quality = _quality(run.get("quality"), prefix, errors)
    return {
        "classification_accuracy": f"{matches}/{len(expected)}",
        "excess_classifications": excess_classifications,
        "tool_calls": _integer(run.get("tool_calls"), f"{prefix}_tool_calls", errors),
        "read_bytes": _integer(run.get("read_bytes"), f"{prefix}_read_bytes", errors),
        "missed_impact": missed,
        "excess_impact": excess,
        "quality": quality,
        "cost": _cost(run.get("cost"), prefix, errors),
    }


def _task_report(
    raw: Any, index: int, fixture_paths: set[str], errors: list[str]
) -> dict[str, Any]:
    task = _mapping(raw, f"task_{index}", errors)
    task_id = _text(task.get("id"), f"task_{index}_id", errors)
    task_type = task.get("type")
    if task_type not in EXPECTED_TASK_TYPES:
        errors.append(f"task_{index}_type_invalid")
    runs = _list(task.get("runs"), f"task_{index}_runs", errors)
    variants = [run.get("variant") for run in runs if isinstance(run, dict)]
    if variants != EXPECTED_VARIANTS:
        errors.append(f"task_{index}_variant_sequence_invalid")

    expected_paths: set[str] = set()
    if task_type == "cold_start":
        coordinates = _mapping(
            task.get("expected_coordinates"),
            f"task_{index}_expected_coordinates",
            errors,
        )
        expected_paths.update(
            value for value in coordinates.values() if isinstance(value, str)
        )
    elif task_type == "refactor_replacement":
        classifications = _mapping(
            task.get("expected_classifications"),
            f"task_{index}_expected_classifications",
            errors,
        )
        expected_paths.update(
            path for path in classifications if isinstance(path, str)
        )
        expected_paths.update(
            item
            for item in _list(
                task.get("expected_impact"), f"task_{index}_expected_impact", errors
            )
            if isinstance(item, str)
        )
    for path in sorted(expected_paths - fixture_paths):
        errors.append(f"task_{index}_expected_fixture_missing:{path}")

    metrics: dict[str, dict[str, Any]] = {}
    for run_index, raw_run in enumerate(runs):
        run = _mapping(raw_run, f"task_{index}_run_{run_index}", errors)
        variant = str(run.get("variant") or f"run_{run_index}")
        prefix = f"task_{index}_{variant}"
        if task_type == "cold_start":
            metrics[variant] = _cold_metrics(
                task, run, prefix, fixture_paths, errors
            )
        elif task_type == "refactor_replacement":
            metrics[variant] = _refactor_metrics(
                task, run, prefix, fixture_paths, errors
            )
    if "baseline" not in metrics or "current" not in metrics:
        return {"id": task_id, "type": task_type}
    quality_worse = _quality_worse(
        metrics["baseline"]["quality"], metrics["current"]["quality"]
    )
    if quality_worse:
        errors.append("current_quality_worse")
    return {
        "id": task_id,
        "type": task_type,
        "baseline": metrics["baseline"],
        "current": metrics["current"],
        "quality_worse": quality_worse,
    }


def _budget(raw: Any, errors: list[str]) -> dict[str, Any]:
    budget = _mapping(raw, "budget", errors)
    execution_month = _text(budget.get("execution_month"), "execution_month", errors)
    cap = _integer(budget.get("monthly_cap"), "monthly_cap", errors)
    used_before = _integer(budget.get("used_before"), "used_before", errors)
    new_trials = _integer(budget.get("new_llm_trials"), "new_llm_trials", errors)
    lean_month = budget.get("lean_ablation_screening_month")
    allowed_caps = {DEFAULT_MONTHLY_CAP} | MONTHLY_CAP_EXCEPTIONS.get(
        execution_month, set()
    )
    if cap not in allowed_caps:
        errors.append("monthly_cap_policy_mismatch")
    total = used_before + new_trials
    if total > cap:
        errors.append("monthly_trial_cap_exceeded")
    return {
        "execution_month": execution_month,
        "monthly_cap": cap,
        "used_before": used_before,
        "new_llm_trials": new_trials,
        "monthly_llm_trial_total": total,
        "lean_ablation_screening_month": lean_month,
    }


def _metric_reduction(baseline: int | None, current: int | None) -> int | None:
    if baseline is None or current is None:
        return None
    return baseline - current


def _metric_worse(baseline: int | None, current: int | None) -> bool:
    if baseline is None or current is None:
        return False
    return current > baseline


def _trace_events(path: Path, field: str, errors: list[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            if not isinstance(entry, dict):
                errors.append(f"{field}_entry_must_be_object")
                continue
            events.append(entry)
    except (OSError, json.JSONDecodeError):
        errors.append(f"{field}_unreadable")
    return events


def _verify_live_provenance(
    raw: Any,
    *,
    record_root: Path,
    expected_model: str,
    errors: list[str],
) -> None:
    provenance = _mapping(raw, "provenance", errors)
    _text(provenance.get("generation_command"), "generation_command", errors)
    _text(provenance.get("rebuild_command"), "rebuild_command", errors)
    _text(provenance.get("trace_redaction"), "trace_redaction", errors)
    runs = _mapping(provenance.get("runs"), "provenance_runs", errors)
    if set(runs) != LIVE_PROVENANCE_RUNS:
        errors.append("provenance_run_set_invalid")
    session_ids: set[str] = set()
    for run_key, raw_run in runs.items():
        prefix = "provenance_" + str(run_key).replace(".", "_")
        run = _mapping(raw_run, prefix, errors)
        session_id = _text(run.get("session_id"), f"{prefix}_session_id", errors)
        if session_id in session_ids:
            errors.append("provenance_session_id_duplicate")
        session_ids.add(session_id)
        trace_value = _text(run.get("trace_file"), f"{prefix}_trace_file", errors)
        trace_relative = Path(trace_value)
        if trace_relative.is_absolute() or ".." in trace_relative.parts:
            errors.append(f"{prefix}_trace_path_invalid")
            continue
        trace_path = (record_root / trace_relative).resolve()
        try:
            trace_path.relative_to(record_root.resolve())
        except ValueError:
            errors.append(f"{prefix}_trace_path_escapes_record")
            continue
        expected_sha = _text(run.get("trace_sha256"), f"{prefix}_trace_sha256", errors)
        if not SHA256_RE.fullmatch(expected_sha):
            errors.append(f"{prefix}_trace_sha256_invalid")
        try:
            actual_sha = hashlib.sha256(trace_path.read_bytes()).hexdigest()
        except OSError:
            errors.append(f"{prefix}_trace_unreadable")
            continue
        if actual_sha != expected_sha:
            errors.append(f"{prefix}_trace_sha256_mismatch")
        events = _trace_events(trace_path, prefix, errors)
        init_events = [
            entry.get("event")
            for entry in events
            if isinstance(entry.get("event"), dict)
            and entry["event"].get("type") == "system"
            and entry["event"].get("subtype") == "init"
        ]
        if len(init_events) != 1:
            errors.append(f"{prefix}_init_event_invalid")
            continue
        init = _mapping(init_events[0], f"{prefix}_init_event", errors)
        if init.get("session_id") != session_id:
            errors.append(f"{prefix}_session_id_mismatch")
        if init.get("model") != expected_model:
            errors.append(f"{prefix}_model_mismatch")
        if PRIVATE_TRACE_INIT_FIELDS & set(init):
            errors.append(f"{prefix}_private_init_metadata_present")
        serialized = json.dumps(events, ensure_ascii=False)
        if HOST_HOME_PATH_RE.search(serialized):
            errors.append(f"{prefix}_host_home_path_present")


def evaluate_record(
    record: dict[str, Any], *, record_root: Path = ROOT
) -> tuple[dict[str, Any], list[str]]:
    """Derive scorecard-ready metrics and return any contract errors."""
    errors: list[str] = []
    if record.get("schema_version") != 1:
        errors.append("unsupported_schema_version")
    measurement = _mapping(record.get("measurement"), "measurement", errors)
    measurement_id = _text(measurement.get("id"), "measurement_id", errors)
    measured_at = _text(measurement.get("measured_at"), "measured_at", errors)
    source = _text(measurement.get("source"), "measurement_source", errors)
    source_count = _integer(measurement.get("source_count"), "source_count", errors)
    if source_count <= 0:
        errors.append("source_count_must_be_positive")
    limitations = _list(measurement.get("limitations"), "limitations", errors)
    if not limitations:
        errors.append("limitations_required")

    conditions = _mapping(record.get("conditions"), "conditions", errors)
    condition_report = {
        "repo_type": _text(conditions.get("repo_type"), "repo_type", errors),
        "provider": _text(conditions.get("provider"), "provider", errors),
        "model": _text(conditions.get("model"), "model", errors),
        "harness_variants": _list(
            conditions.get("harness_variants"), "harness_variants", errors
        ),
    }
    if condition_report["harness_variants"] != EXPECTED_VARIANTS:
        errors.append("harness_variants_invalid")
    evidence_kind = measurement.get("evidence_kind")
    if evidence_kind is None and condition_report["provider"] == "deterministic-replay":
        evidence_kind = "deterministic_replay"
    if evidence_kind not in {"deterministic_replay", "live_trace"}:
        errors.append("measurement_evidence_kind_invalid")
    budget = _budget(record.get("budget"), errors)
    fixture_root_value = _text(record.get("fixture_root"), "fixture_root", errors)
    fixture_root_path = Path(fixture_root_value)
    resolved_record_root = record_root.resolve()
    if fixture_root_path.is_absolute() or ".." in fixture_root_path.parts:
        errors.append("fixture_root_must_be_record_relative")
        resolved_fixture_root = resolved_record_root
    else:
        resolved_fixture_root = (resolved_record_root / fixture_root_path).resolve()
    try:
        resolved_fixture_root.relative_to(resolved_record_root)
    except ValueError:
        errors.append("fixture_root_escapes_record")
        resolved_fixture_root = resolved_record_root
    fixture_paths = _verify_fixtures(
        record.get("fixtures"), resolved_fixture_root, errors
    )
    if evidence_kind == "live_trace":
        _verify_live_provenance(
            record.get("provenance"),
            record_root=resolved_record_root,
            expected_model=str(condition_report["model"]),
            errors=errors,
        )

    tasks = [
        _task_report(raw, index, fixture_paths, errors)
        for index, raw in enumerate(_list(record.get("tasks"), "tasks", errors))
    ]
    task_types = {task.get("type") for task in tasks}
    if task_types != EXPECTED_TASK_TYPES:
        errors.append("required_task_types_missing")

    baseline_totals: dict[str, int | None] = {
        "tool_calls": 0,
        "read_bytes": 0,
        "wrong_paths": 0,
        "missed_impact": 0,
        "excess_impact": 0,
        "context_rework": 0,
    }
    current_totals = dict(baseline_totals)
    total_cost = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    quality_worse = False
    unmeasured_quality_fields: set[str] = set()
    for task in tasks:
        quality_worse = quality_worse or bool(task.get("quality_worse"))
        for variant, totals in (("baseline", baseline_totals), ("current", current_totals)):
            metrics = task.get(variant)
            if not isinstance(metrics, dict):
                continue
            totals["tool_calls"] = int(totals["tool_calls"] or 0) + int(
                metrics.get("tool_calls") or 0
            )
            totals["read_bytes"] = int(totals["read_bytes"] or 0) + int(
                metrics.get("read_bytes") or 0
            )
            totals["wrong_paths"] = int(totals["wrong_paths"] or 0) + int(
                metrics.get("wrong_path_count") or 0
            )
            totals["missed_impact"] = int(totals["missed_impact"] or 0) + len(
                metrics.get("missed_impact") or []
            )
            totals["excess_impact"] = int(totals["excess_impact"] or 0) + len(
                metrics.get("excess_impact") or []
            )
            quality = metrics.get("quality") or {}
            context_rework = quality.get("context_rework_count")
            if context_rework is None:
                unmeasured_quality_fields.add("context_rework_count")
            else:
                totals["context_rework"] = int(
                    totals["context_rework"] or 0
                ) + int(context_rework)
            for field in (
                "must_fix_count",
                "regression_count",
                "human_recovery_count",
                "cross_session_resume",
            ):
                if quality.get(field) is None:
                    unmeasured_quality_fields.add(field)
            cost = metrics.get("cost") or {}
            total_cost["input_tokens"] += int(cost.get("input_tokens") or 0)
            total_cost["output_tokens"] += int(cost.get("output_tokens") or 0)
            total_cost["cost_usd"] += float(cost.get("cost_usd") or 0)

    target_metrics = ("tool_calls", "read_bytes", "wrong_paths", "missed_impact", "context_rework")
    if "context_rework_count" in unmeasured_quality_fields:
        baseline_totals["context_rework"] = None
        current_totals["context_rework"] = None
    reductions = {
        metric: _metric_reduction(baseline_totals[metric], current_totals[metric])
        for metric in target_metrics
    }
    core_worse = quality_worse or any(
        _metric_worse(baseline_totals[metric], current_totals[metric])
        for metric in ("wrong_paths", "missed_impact", "excess_impact", "context_rework")
    )
    improved = any(
        isinstance(value, int) and value > 0 for value in reductions.values()
    ) and not core_worse
    if not improved:
        errors.append("no_effectiveness_improvement")

    report = {
        "status": "관측" if not errors else "FAIL",
        "measurement_id": measurement_id,
        "measured_at": measured_at,
        "source": source,
        "source_count": source_count,
        "task_count": len(tasks),
        "denominator": len(tasks) * 2,
        "conditions": condition_report,
        "tasks": tasks,
        "baseline": baseline_totals,
        "current": current_totals,
        "reductions": reductions,
        "improved": improved,
        "quality_worse": quality_worse,
        "unmeasured_quality_fields": sorted(unmeasured_quality_fields),
        "cost": total_cost,
        "execution_month": budget["execution_month"],
        "monthly_llm_trial_total": budget["monthly_llm_trial_total"],
        "new_llm_trials": budget["new_llm_trials"],
        "limitations": limitations,
        "reason": (
            "동일 frozen task의 baseline/current를 기대 좌표·분류·영향 집합과 "
            "대조했다. 문서·map·hook 수는 지표에 포함하지 않았고 실행하지 않은 "
            "downstream 품질 축은 측정 불가로 유지했다."
        ),
    }
    return report, errors


def load_record(path: Path | str) -> dict[str, Any]:
    """Read, validate, and evaluate one replay record."""
    record_path = Path(path).expanduser().resolve()
    try:
        payload = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentEffectivenessRecordInvalid([f"record_unreadable:{exc}"]) from exc
    if not isinstance(payload, dict):
        raise AgentEffectivenessRecordInvalid(["record_must_be_object"])
    report, errors = evaluate_record(payload, record_root=record_path.parent)
    if errors:
        raise AgentEffectivenessRecordInvalid(errors)
    return report

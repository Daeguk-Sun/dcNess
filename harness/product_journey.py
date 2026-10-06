#!/usr/bin/env python3
"""Run a project-local product journey and emit a verifiable receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import signal
import subprocess  # nosec B404
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Optional


EVIDENCE_ROOT_REL = Path(".dcness-work/product-journey")
SCHEMA_VERSION = 1
RECEIPT_TYPE = "dcness.product-journey"
SKIP_RECORD_TYPE = "dcness.product-journey-skip"
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_BOUNDARIES = {"api", "cli", "integration", "mock", "ui"}
# A device/emulator UI journey chains many screen flows and routinely runs past
# ten minutes; the other phases stay at the original cap (#1219).
_PHASE_TIMEOUT_MAX_SEC = {"journey": 1800}
_TIMEOUT_WARNING_RATIO = 0.8
_ASSERTION_SOURCES = {"journey_exit", "none"}
_PHASES = ("start", "health", "journey", "cleanup")
# A scenario manifest replaces the single journey command with declared scenarios.
_SCENARIO_PHASES = ("start", "health", "cleanup")
_AC_VERDICTS = frozenset({"PASS", "FAIL", "NOT_RUN"})
_SCENARIO_RECEIPT_KEYS = ("scenarios", "ac_results", "partial", "selected_scenarios")
_UI_EVIDENCE_TYPES = {"log", "screenshot", "state"}
_RUN_DIR_ENV = "DCNESS_PRODUCT_JOURNEY_RUN_DIR"
_EPIC_SCOPE_ID_FIELDS = ("epic", "representative_story")
_EPIC_SCOPE_TEXT_FIELDS = ("selection_rationale", "execution_environment")
_EPIC_SCOPE_RECEIPT_FIELDS = frozenset(
    _EPIC_SCOPE_ID_FIELDS + _EPIC_SCOPE_TEXT_FIELDS + ("code_revision",)
)
_REVISION_RE = re.compile(r"^[0-9a-f]{7,40}$")
_UNKNOWN_REVISION = "unknown"
_HISTORY_DURATION_MAX_MS = 24 * 60 * 60 * 1000


class JourneyConfigError(ValueError):
    """Raised when the project-local journey contract is invalid."""


@dataclass(frozen=True)
class JourneyRunResult:
    exit_code: int
    receipt_path: Path
    receipt: dict[str, Any]


@dataclass
class _ServiceHandle:
    process: subprocess.Popen[bytes]
    stream: BinaryIO
    started_at: float


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_ts(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise JourneyConfigError(f"cannot read config: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise JourneyConfigError(f"invalid JSON config: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise JourneyConfigError("config root must be an object")
    return payload


def _require_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise JourneyConfigError(f"{key} must be a non-empty string")
    return value.strip()


def _validated_epic_scope(config: dict[str, Any]) -> Optional[dict[str, str]]:
    """Validate the optional epic-close scope declaration and return it normalized."""
    scope = config.get("epic_scope")
    if scope is None:
        return None
    if not isinstance(scope, dict):
        raise JourneyConfigError("epic_scope must be an object")
    normalized: dict[str, str] = {}
    for key in _EPIC_SCOPE_ID_FIELDS + _EPIC_SCOPE_TEXT_FIELDS:
        value = scope.get(key)
        if not isinstance(value, str) or not value.strip():
            raise JourneyConfigError(f"epic_scope.{key} must be a non-empty string")
        normalized[key] = value.strip()
    for key in _EPIC_SCOPE_ID_FIELDS:
        if not _ID_RE.fullmatch(normalized[key]):
            raise JourneyConfigError(
                f"epic_scope.{key} must match [a-z0-9][a-z0-9._-]{{2,63}}"
            )
    return normalized


def _checked_runnable(raw: dict[str, Any], label: str, limit: float) -> None:
    argv = raw.get("argv")
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(item, str) or not item for item in argv)
    ):
        raise JourneyConfigError(f"{label}.argv must be non-empty strings")
    timeout = raw.get("timeout_sec", 60)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
        raise JourneyConfigError(f"{label}.timeout_sec must be numeric")
    if timeout <= 0 or timeout > limit:
        raise JourneyConfigError(f"{label}.timeout_sec must be in (0, {limit}]")


def _command_spec(commands: dict[str, Any], phase: str) -> dict[str, Any]:
    raw = commands.get(phase)
    if not isinstance(raw, dict):
        raise JourneyConfigError(f"commands.{phase} must be an object")
    _checked_runnable(raw, f"commands.{phase}", _PHASE_TIMEOUT_MAX_SEC.get(phase, 600))
    return raw


def _validated_scenarios(config: dict[str, Any]) -> Optional[list[dict[str, Any]]]:
    """Validate the optional scenario list that replaces the single journey command.

    Each scenario owns a subset of `target_ac`, and every AC must be owned so a
    per-AC verdict never credits an AC that no scenario actually exercised.
    """
    ui_steps = (config.get("ui_evidence") or {}).get("steps") or []
    if "scenarios" not in config:
        if any(isinstance(step, dict) and "scenario_id" in step for step in ui_steps):
            raise JourneyConfigError(
                "ui_evidence.steps[].scenario_id is only valid with scenarios"
            )
        return None
    raw = config["scenarios"]
    if not isinstance(raw, list) or not raw:
        raise JourneyConfigError("scenarios must declare at least one scenario")
    commands = config.get("commands")
    if isinstance(commands, dict) and "journey" in commands:
        raise JourneyConfigError(
            "scenarios and commands.journey cannot both be declared"
        )
    target_ac = {str(item).strip() for item in config["target_ac"]}
    # Per-AC verdicts are keyed by AC, so a repeated AC would split the
    # denominator from the verdicts and fail a fully passing run.
    if len(target_ac) != len(config["target_ac"]):
        raise JourneyConfigError("target_ac must not repeat an AC in scenario manifests")
    owned: set[str] = set()
    seen: set[str] = set()
    for index, scenario in enumerate(raw):
        prefix = f"scenarios[{index}]"
        if not isinstance(scenario, dict):
            raise JourneyConfigError(f"{prefix} must be an object")
        scenario_id = _require_text(scenario, "scenario_id")
        if not _ID_RE.fullmatch(scenario_id):
            raise JourneyConfigError(
                f"{prefix}.scenario_id must match [a-z0-9][a-z0-9._-]{{2,63}}"
            )
        if scenario_id in seen:
            raise JourneyConfigError(f"{prefix}.scenario_id must be unique")
        seen.add(scenario_id)
        _require_text(scenario, "description")
        _checked_runnable(scenario, prefix, _PHASE_TIMEOUT_MAX_SEC["journey"])
        scenario_ac = scenario.get("target_ac")
        if (
            not isinstance(scenario_ac, list)
            or not scenario_ac
            or any(not isinstance(item, str) or not item.strip() for item in scenario_ac)
        ):
            raise JourneyConfigError(f"{prefix}.target_ac must contain AC ids")
        normalized = {item.strip() for item in scenario_ac}
        if not normalized.issubset(target_ac):
            raise JourneyConfigError(f"{prefix}.target_ac must be declared in target_ac")
        owned.update(normalized)
    orphans = sorted(target_ac - owned)
    if orphans:
        raise JourneyConfigError(
            f"target_ac not owned by any scenario: {', '.join(orphans)}"
        )
    _validated_step_owners(ui_steps, raw)
    return raw


def _validated_step_owners(
    ui_steps: list[Any], scenarios: list[dict[str, Any]]
) -> None:
    """Tie every UI evidence step to the scenario that captures it.

    Without this a partial re-run cannot tell a screen its selected scenario
    failed to capture from one an unselected scenario was meant to capture.
    """
    owned_ac = {
        str(scenario["scenario_id"]).strip(): {
            str(item).strip() for item in scenario["target_ac"]
        }
        for scenario in scenarios
    }
    for index, step in enumerate(ui_steps):
        prefix = f"ui_evidence.steps[{index}]"
        scenario_id = _require_text(step, "scenario_id")
        if scenario_id not in owned_ac:
            raise JourneyConfigError(f"{prefix}.scenario_id must name a declared scenario")
        if not {str(item).strip() for item in step["target_ac"]}.issubset(
            owned_ac[scenario_id]
        ):
            raise JourneyConfigError(
                f"{prefix}.target_ac must be owned by its scenario {scenario_id}"
            )


def _ui_config_for(
    config: dict[str, Any], selected: set[str], partial: bool
) -> dict[str, Any]:
    """The UI declaration a run judges: every screen, or a re-run's own screens."""
    if not partial:
        return config
    # Compare ids the way the contract check normalized them; a raw comparison
    # would silently drop a padded screen and leave its AC unjudged.
    steps = [
        step
        for step in config["ui_evidence"]["steps"]
        if str(step["scenario_id"]).strip() in selected
    ]
    step_ids = {str(step["step_id"]).strip() for step in steps}
    return {
        **config,
        "ui_evidence": {**config["ui_evidence"], "steps": steps},
        "ux_integrity": {
            **config["ux_integrity"],
            "snapshots": [
                snapshot
                for snapshot in config["ux_integrity"]["snapshots"]
                if str(snapshot["step_id"]).strip() in step_ids
            ],
        },
    }


def _scenario_contract(scenarios: list[dict[str, Any]]) -> list[tuple[str, list[str]]]:
    """Scenario order and AC ownership, in a form manifest and receipt share."""
    return [
        (
            str(scenario["scenario_id"]).strip(),
            [str(item).strip() for item in scenario["target_ac"]],
        )
        for scenario in scenarios
    ]


def _resolve_evidence_root(project_root: Path, raw: object) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise JourneyConfigError("evidence_dir must be a non-empty relative path")
    relative = Path(raw)
    if relative.is_absolute():
        raise JourneyConfigError("evidence_dir must be project-relative")
    resolved = (project_root / relative).resolve()
    canonical = (project_root / EVIDENCE_ROOT_REL).resolve()
    try:
        resolved.relative_to(canonical)
    except ValueError as exc:
        raise JourneyConfigError(
            f"evidence_dir must stay under {EVIDENCE_ROOT_REL.as_posix()}"
        ) from exc
    return resolved


def _validated_ui_evidence(config: dict[str, Any]) -> None:
    boundary = config.get("boundary")
    raw_ui = config.get("ui_evidence")
    if boundary != "ui":
        if raw_ui is not None:
            raise JourneyConfigError("ui_evidence is only valid for boundary=ui")
        return
    if not isinstance(raw_ui, dict):
        raise JourneyConfigError("ui_evidence must be an object for boundary=ui")
    steps = raw_ui.get("steps")
    if not isinstance(steps, list) or len(steps) < 2:
        raise JourneyConfigError("ui_evidence.steps must contain at least two steps")
    target_ac = {str(item).strip() for item in config["target_ac"]}
    step_ids: set[str] = set()
    final_ac: set[str] = set()
    for index, step in enumerate(steps):
        prefix = f"ui_evidence.steps[{index}]"
        if not isinstance(step, dict):
            raise JourneyConfigError(f"{prefix} must be an object")
        step_id = _require_text(step, "step_id")
        if not _ID_RE.fullmatch(step_id):
            raise JourneyConfigError(f"{prefix}.step_id must be a valid id")
        if step_id in step_ids:
            raise JourneyConfigError(f"{prefix}.step_id must be unique")
        step_ids.add(step_id)
        _require_text(step, "description")
        step_ac = step.get("target_ac")
        if (
            not isinstance(step_ac, list)
            or not step_ac
            or any(not isinstance(item, str) or not item.strip() for item in step_ac)
        ):
            raise JourneyConfigError(f"{prefix}.target_ac must contain AC ids")
        normalized_ac = {item.strip() for item in step_ac}
        if not normalized_ac.issubset(target_ac):
            raise JourneyConfigError(f"{prefix}.target_ac must be declared in target_ac")
        is_final = step.get("final")
        if not isinstance(is_final, bool):
            raise JourneyConfigError(f"{prefix}.final must be boolean")
        if is_final:
            final_ac.update(normalized_ac)
        evidence = step.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise JourneyConfigError(f"{prefix}.evidence must not be empty")
        for evidence_index, item in enumerate(evidence):
            item_prefix = f"{prefix}.evidence[{evidence_index}]"
            if not isinstance(item, dict):
                raise JourneyConfigError(f"{item_prefix} must be an object")
            raw_path = _require_text(item, "path")
            relative = Path(raw_path)
            if relative.is_absolute() or ".." in relative.parts:
                raise JourneyConfigError(
                    f"{item_prefix}.path must stay inside the run directory"
                )
            if item.get("type") not in _UI_EVIDENCE_TYPES:
                raise JourneyConfigError(
                    f"{item_prefix}.type must be one of "
                    f"{sorted(_UI_EVIDENCE_TYPES)}"
                )
    if final_ac != target_ac:
        raise JourneyConfigError(
            "final UI steps must cover every AC declared in target_ac"
        )


def _validated_ux_elements(
    snapshot: dict[str, Any], prefix: str, step_ac: set[str], needs_node_id: bool
) -> set[str]:
    elements = snapshot.get("elements")
    if not isinstance(elements, list) or not elements:
        raise JourneyConfigError(
            f"{prefix}.elements must declare at least one screen element"
        )
    element_ids: set[str] = set()
    covered_ac: set[str] = set()
    for index, element in enumerate(elements):
        item_prefix = f"{prefix}.elements[{index}]"
        if not isinstance(element, dict):
            raise JourneyConfigError(f"{item_prefix} must be an object")
        element_id = _require_text(element, "element_id")
        if element_id in element_ids:
            raise JourneyConfigError(f"{item_prefix}.element_id must be unique")
        element_ids.add(element_id)
        element_ac = element.get("target_ac")
        if (
            not isinstance(element_ac, list)
            or not element_ac
            or any(not isinstance(item, str) or not item.strip() for item in element_ac)
        ):
            raise JourneyConfigError(f"{item_prefix}.target_ac must contain AC ids")
        normalized_ac = {item.strip() for item in element_ac}
        if not normalized_ac.issubset(step_ac):
            raise JourneyConfigError(
                f"{item_prefix}.target_ac must be declared by the referenced ui_evidence step"
            )
        covered_ac.update(normalized_ac)
        if needs_node_id or element.get("node_id") is not None:
            _require_text(element, "node_id")
    return covered_ac


def _validated_ux_integrity(config: dict[str, Any]) -> None:
    boundary = config.get("boundary")
    raw = config.get("ux_integrity")
    if boundary != "ui":
        if raw is not None:
            raise JourneyConfigError("ux_integrity is only valid for boundary=ui")
        return
    if not isinstance(raw, dict):
        raise JourneyConfigError("ux_integrity must be an object for boundary=ui")
    snapshots = raw.get("snapshots")
    if not isinstance(snapshots, list) or not snapshots:
        raise JourneyConfigError(
            "ux_integrity.snapshots must declare at least one screen snapshot"
        )
    declared_steps = {
        str(step["step_id"]): {str(item).strip() for item in step["target_ac"]}
        for step in config["ui_evidence"]["steps"]
    }
    final_steps = {
        step_id: declared_steps[step_id]
        for step in config["ui_evidence"]["steps"]
        if step["final"]
        for step_id in (str(step["step_id"]),)
    }
    snapshot_steps: set[str] = set()
    snapshot_reports: set[str] = set()
    snapshot_ac: dict[str, set[str]] = {}
    for index, snapshot in enumerate(snapshots):
        prefix = f"ux_integrity.snapshots[{index}]"
        if not isinstance(snapshot, dict):
            raise JourneyConfigError(f"{prefix} must be an object")
        step_id = _require_text(snapshot, "step_id")
        if step_id not in declared_steps:
            raise JourneyConfigError(
                f"{prefix}.step_id must name a declared ui_evidence step"
            )
        if step_id in snapshot_steps:
            raise JourneyConfigError(f"{prefix}.step_id must be unique")
        snapshot_steps.add(step_id)
        layout_report = Path(_require_text(snapshot, "layout_report"))
        if layout_report.is_absolute() or ".." in layout_report.parts:
            raise JourneyConfigError(
                f"{prefix}.layout_report must stay inside the run directory"
            )
        # casefold: on case-insensitive filesystems two spellings name one file,
        # which would let two screens be judged against a single report.
        report_key = layout_report.as_posix().casefold()
        if report_key in snapshot_reports:
            raise JourneyConfigError(
                f"{prefix}.layout_report must not be shared between snapshots"
            )
        snapshot_reports.add(report_key)
        mockup = snapshot.get("mockup_reference")
        if mockup is not None:
            reference = Path(_require_text(snapshot, "mockup_reference"))
            if reference.is_absolute() or ".." in reference.parts:
                raise JourneyConfigError(
                    f"{prefix}.mockup_reference must be project-relative"
                )
        snapshot_ac[step_id] = _validated_ux_elements(
            snapshot, prefix, declared_steps[step_id], mockup is not None
        )
    for step_id, required_ac in final_steps.items():
        if not required_ac.issubset(snapshot_ac.get(step_id, set())):
            raise JourneyConfigError(
                "ux_integrity must judge every AC of each final ui_evidence step "
                f"in that step's own snapshot: {step_id}"
            )


def _validated_config(
    project_root: Path, config_path: Path
) -> tuple[dict[str, Any], Path]:
    config = _read_object(config_path)
    if config.get("version") != SCHEMA_VERSION:
        raise JourneyConfigError(f"version must be {SCHEMA_VERSION}")
    journey_id = _require_text(config, "journey_id")
    if not _ID_RE.fullmatch(journey_id):
        raise JourneyConfigError("journey_id must match [a-z0-9][a-z0-9._-]{2,63}")
    target_ac = config.get("target_ac")
    if (
        not isinstance(target_ac, list)
        or not target_ac
        or any(not isinstance(item, str) or not item.strip() for item in target_ac)
    ):
        raise JourneyConfigError("target_ac must contain at least one non-empty AC id")
    boundary = config.get("boundary")
    if boundary not in _BOUNDARIES:
        raise JourneyConfigError(f"boundary must be one of {sorted(_BOUNDARIES)}")
    _validated_ui_evidence(config)
    _validated_ux_integrity(config)
    _validated_epic_scope(config)
    assertion = config.get("assertion")
    if not isinstance(assertion, dict):
        raise JourneyConfigError("assertion must be an object")
    _require_text(assertion, "description")
    if assertion.get("source") not in _ASSERTION_SOURCES:
        raise JourneyConfigError(
            f"assertion.source must be one of {sorted(_ASSERTION_SOURCES)}"
        )
    intervention = config.get("human_intervention_count", 0)
    if not isinstance(intervention, int) or isinstance(intervention, bool) or intervention < 0:
        raise JourneyConfigError("human_intervention_count must be a non-negative integer")
    commands = config.get("commands")
    if not isinstance(commands, dict):
        raise JourneyConfigError("commands must be an object")
    scenarios = _validated_scenarios(config)
    for phase in _SCENARIO_PHASES if scenarios is not None else _PHASES:
        _command_spec(commands, phase)
    start_mode = commands["start"].get("mode")
    if start_mode not in {"command", "service"}:
        raise JourneyConfigError("commands.start.mode must be command or service")
    grace = commands["start"].get("startup_grace_sec", 0.2)
    if not isinstance(grace, (int, float)) or isinstance(grace, bool):
        raise JourneyConfigError("commands.start.startup_grace_sec must be numeric")
    if grace < 0 or grace > 30:
        raise JourneyConfigError("commands.start.startup_grace_sec must be in [0, 30]")
    env = config.get("env", {})
    if not isinstance(env, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in env.items()
    ):
        raise JourneyConfigError("env must map strings to strings")
    evidence_root = _resolve_evidence_root(
        project_root, config.get("evidence_dir", EVIDENCE_ROOT_REL.as_posix())
    )
    return config, evidence_root


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _code_revision(project_root: Path) -> str:
    """Return the tracked HEAD revision the journey ran against, or "unknown"."""
    try:
        completed = subprocess.run(  # nosec B603 B607
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return _UNKNOWN_REVISION
    revision = completed.stdout.strip()
    if completed.returncode != 0 or not _REVISION_RE.fullmatch(revision):
        return _UNKNOWN_REVISION
    return revision


def _uncommitted_changes(project_root: Path) -> Optional[bool]:
    """Whether the working tree differs from HEAD; None when git cannot tell.

    A receipt of a dirty tree does not describe its `code_revision` alone, so a
    reader must not treat the commit diff as the whole change.
    """
    try:
        completed = subprocess.run(  # nosec B603 B607
            ["git", "status", "--porcelain"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return bool(completed.stdout.strip())


def _run_command(
    spec: dict[str, Any], project_root: Path, env: dict[str, str], log_path: Path
) -> dict[str, Any]:
    argv = list(spec["argv"])
    timeout = float(spec.get("timeout_sec", 60))
    started = time.monotonic()
    timed_out = False
    exit_code = 127
    with log_path.open("wb") as stream:
        try:
            completed = subprocess.run(  # nosec B603
                argv,
                cwd=project_root,
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
            exit_code = completed.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = 124
        except OSError as exc:
            stream.write(f"failed to execute: {exc}\n".encode("utf-8"))
    return {
        "argv": argv,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_ms": round((time.monotonic() - started) * 1000),
        "timeout_sec": spec.get("timeout_sec", 60),
        "log_path": _relative(log_path, project_root),
    }


def _timeout_warnings(command_results: dict[str, Any]) -> list[dict[str, Any]]:
    """Phases that passed but used most of their timeout — the next run may not."""
    warnings: list[dict[str, Any]] = []
    for phase, result in command_results.items():
        timeout = result.get("timeout_sec")
        if result.get("timed_out") or not isinstance(timeout, (int, float)) or timeout <= 0:
            continue
        ratio = round(result["duration_ms"] / (timeout * 1000), 3)
        if ratio >= _TIMEOUT_WARNING_RATIO:
            warnings.append(
                {
                    "phase": phase,
                    "duration_ms": result["duration_ms"],
                    "timeout_sec": timeout,
                    "ratio": ratio,
                }
            )
    return warnings


def _start_service(
    spec: dict[str, Any], project_root: Path, env: dict[str, str], log_path: Path
) -> tuple[_ServiceHandle | None, dict[str, Any]]:
    argv = list(spec["argv"])
    stream = log_path.open("wb")
    started = time.monotonic()
    try:
        process = subprocess.Popen(  # nosec B603
            argv,
            cwd=project_root,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as exc:
        stream.write(f"failed to execute: {exc}\n".encode("utf-8"))
        stream.close()
        return None, {
            "argv": argv,
            "exit_code": 127,
            "timed_out": False,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "log_path": _relative(log_path, project_root),
        }
    time.sleep(float(spec.get("startup_grace_sec", 0.2)))
    exit_code = process.poll()
    if exit_code is not None:
        stream.close()
        return None, {
            "argv": argv,
            "exit_code": exit_code,
            "timed_out": False,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "log_path": _relative(log_path, project_root),
        }
    return _ServiceHandle(process, stream, started), {
        "argv": argv,
        "exit_code": None,
        "timed_out": False,
        "duration_ms": round((time.monotonic() - started) * 1000),
        "log_path": _relative(log_path, project_root),
    }


def _stop_service(handle: _ServiceHandle, result: dict[str, Any]) -> None:
    process = handle.process
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
    handle.stream.close()
    result["exit_code"] = process.poll() if process.poll() is not None else 124
    result["duration_ms"] = round((time.monotonic() - handle.started_at) * 1000)


def _append_once(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _collect_ui_evidence(
    config: dict[str, Any], run_dir: Path, project_root: Path
) -> tuple[dict[str, Any], bool, set[str]]:
    collected_steps: list[dict[str, Any]] = []
    complete = True
    present_types: set[str] = set()
    for step in config["ui_evidence"]["steps"]:
        collected_evidence: list[dict[str, Any]] = []
        for declared in step["evidence"]:
            declared_path = run_dir / declared["path"]
            path = declared_path.resolve()
            try:
                path.relative_to(run_dir.resolve())
            except ValueError:
                present = False
            else:
                try:
                    present = (
                        declared_path.is_file()
                        and not declared_path.is_symlink()
                        and declared_path.stat().st_size > 0
                    )
                except OSError:
                    present = False
            evidence_hash: str | None = None
            if present:
                try:
                    evidence_hash = _sha256_file(declared_path)
                except OSError:
                    present = False
            if not present:
                complete = False
            else:
                present_types.add(declared["type"])
            collected_evidence.append(
                {
                    "path": declared_path.relative_to(project_root).as_posix(),
                    "type": declared["type"],
                    "present": present,
                    "sha256": evidence_hash,
                }
            )
        collected_steps.append(
            {
                "step_id": step["step_id"],
                "description": step["description"],
                "target_ac": [str(item).strip() for item in step["target_ac"]],
                "final": step["final"],
                "evidence": collected_evidence,
            }
        )
    return {"steps": collected_steps}, complete, present_types


def _number(payload: dict[str, Any], key: str, default: Any = None) -> Optional[float]:
    value = payload.get(key, default)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    if not math.isfinite(number):
        return None
    return number


def _bounds(payload: object) -> Optional[tuple[float, float, float, float]]:
    if not isinstance(payload, dict):
        return None
    x = _number(payload, "x")
    y = _number(payload, "y")
    width = _number(payload, "width")
    height = _number(payload, "height")
    if x is None or y is None or width is None or height is None:
        return None
    if width <= 0 or height <= 0:
        return None
    return (x, y, width, height)


def _within(inner: tuple[float, ...], outer: tuple[float, ...]) -> bool:
    return (
        inner[0] >= outer[0]
        and inner[1] >= outer[1]
        and inner[0] + inner[2] <= outer[0] + outer[2]
        and inner[1] + inner[3] <= outer[1] + outer[3]
    )


def _covers(rect: tuple[float, ...], x: float, y: float) -> bool:
    return rect[0] <= x < rect[0] + rect[2] and rect[1] <= y < rect[1] + rect[3]


def _parse_layout_report(path: Path) -> Optional[dict[str, Any]]:
    """Normalize a project-produced layout report into safe area and element bounds."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != SCHEMA_VERSION:
        return None
    viewport = payload.get("viewport")
    if not isinstance(viewport, dict):
        return None
    width = _number(viewport, "width")
    height = _number(viewport, "height")
    if width is None or height is None or width <= 0 or height <= 0:
        return None
    raw_safe_area = payload.get("safe_area")
    if not isinstance(raw_safe_area, dict):
        return None
    insets: dict[str, float] = {}
    for side in ("top", "right", "bottom", "left"):
        inset = _number(raw_safe_area, side)
        if inset is None or inset < 0:
            return None
        insets[side] = inset
    safe_area = (
        insets["left"],
        insets["top"],
        width - insets["left"] - insets["right"],
        height - insets["top"] - insets["bottom"],
    )
    if safe_area[2] <= 0 or safe_area[3] <= 0:
        return None
    raw_elements = payload.get("elements")
    if not isinstance(raw_elements, list) or not raw_elements:
        return None
    elements: dict[str, tuple[tuple[float, float, float, float], float]] = {}
    for item in raw_elements:
        if not isinstance(item, dict):
            return None
        element_id = item.get("element_id")
        if not isinstance(element_id, str) or not element_id.strip():
            return None
        element_id = element_id.strip()
        if element_id in elements:
            return None
        bounds = _bounds(item.get("bounds"))
        order = _number(item, "z")
        if bounds is None or order is None:
            return None
        elements[element_id] = (bounds, order)
    return {"safe_area": safe_area, "elements": elements}


def _judge_elements(
    report: Optional[dict[str, Any]], declared: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Derive per-element verdicts from one screen snapshot's real bounds.

    Both receipt generation and receipt validation call this so a recorded
    verdict can always be recomputed from the hashed layout report.
    """
    reasons: list[str] = []
    judged: list[dict[str, Any]] = []
    for element in declared:
        element_id = element["element_id"]
        entry: dict[str, Any] = {
            "element_id": element_id,
            "target_ac": [str(item).strip() for item in element["target_ac"]],
            "node_id": element.get("node_id"),
            "evaluated": False,
            "bounds": None,
            "within_safe_area": None,
            "occluded_by": [],
        }
        if report is not None:
            found = report["elements"].get(element_id)
            if found is None:
                _append_once(reasons, "ux_integrity_element_missing")
            else:
                bounds, order = found
                entry["evaluated"] = True
                entry["bounds"] = {
                    "x": bounds[0],
                    "y": bounds[1],
                    "width": bounds[2],
                    "height": bounds[3],
                }
                within = _within(bounds, report["safe_area"])
                entry["within_safe_area"] = within
                if not within:
                    _append_once(reasons, "ux_integrity_chrome_overlap")
                center_x = bounds[0] + bounds[2] / 2
                center_y = bounds[1] + bounds[3] / 2
                occluded_by = sorted(
                    other_id
                    for other_id, (
                        other_bounds,
                        other_order,
                    ) in report["elements"].items()
                    if other_id != element_id
                    and other_order > order
                    and _covers(other_bounds, center_x, center_y)
                    and not _within(other_bounds, bounds)
                )
                entry["occluded_by"] = occluded_by
                if occluded_by:
                    _append_once(reasons, "ux_integrity_occluded")
        judged.append(entry)
    return judged, reasons


def _canonical_ux_declaration(declaration: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize the manifest's UX declaration into the judged shape."""
    return [
        {
            "step_id": snapshot["step_id"].strip(),
            "layout_report": Path(snapshot["layout_report"].strip()).as_posix(),
            "mockup_reference": snapshot.get("mockup_reference"),
            "elements": [
                {
                    "element_id": element["element_id"].strip(),
                    "target_ac": [str(item).strip() for item in element["target_ac"]],
                    "node_id": element.get("node_id"),
                }
                for element in snapshot["elements"]
            ],
        }
        for snapshot in declaration["snapshots"]
    ]


def _declaration_digest(canonical: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _layout_report_state(
    declared_path: Path, run_dir: Path
) -> tuple[bool, Optional[str]]:
    try:
        declared_path.resolve().relative_to(run_dir.resolve())
    except ValueError:
        return False, None
    try:
        present = (
            declared_path.is_file()
            and not declared_path.is_symlink()
            and declared_path.stat().st_size > 0
        )
    except OSError:
        return False, None
    if not present:
        return False, None
    try:
        return True, _sha256_file(declared_path)
    except OSError:
        return False, None


def _evaluate_ux_integrity(
    config: dict[str, Any], run_dir: Path, project_root: Path
) -> tuple[dict[str, Any], list[str]]:
    """Judge each declared screen snapshot from its own layout report."""
    reasons: list[str] = []
    snapshots: list[dict[str, Any]] = []
    declaration = _canonical_ux_declaration(config["ux_integrity"])
    for snapshot in declaration:
        declared_path = run_dir / snapshot["layout_report"]
        present, report_hash = _layout_report_state(declared_path, run_dir)
        report: dict[str, Any] | None = None
        if present:
            report = _parse_layout_report(declared_path)
            if report is None:
                _append_once(reasons, "ux_integrity_report_invalid")
        else:
            _append_once(reasons, "ux_integrity_report_missing")
        judged, element_reasons = _judge_elements(report, snapshot["elements"])
        for reason in element_reasons:
            _append_once(reasons, reason)
        snapshots.append(
            {
                "step_id": snapshot["step_id"],
                "layout_report": {
                    "path": declared_path.relative_to(project_root).as_posix(),
                    "present": present,
                    "sha256": report_hash,
                },
                "mockup_reference": snapshot["mockup_reference"],
                "elements": judged,
            }
        )
    return (
        {
            "declaration_sha256": _declaration_digest(declaration),
            "snapshots": snapshots,
        },
        reasons,
    )


def _derive_ac_results(
    target_ac: list[str],
    scenarios: list[dict[str, Any]],
    run_ok: bool,
    ui_evidence: Optional[dict[str, Any]],
    ux_integrity: Optional[dict[str, Any]],
) -> dict[str, str]:
    """Per-AC verdicts from scenario results and the AC-tagged UI evidence.

    Both receipt generation and receipt validation call this, so a recorded
    verdict can always be recomputed from what the receipt itself proves.
    """
    results: dict[str, str] = {}
    for ac in target_ac:
        owners = [scenario for scenario in scenarios if ac in scenario["target_ac"]]
        executed = [scenario for scenario in owners if scenario["executed"]]
        if not run_ok or any(scenario["exit_code"] != 0 for scenario in executed):
            results[ac] = "FAIL"
            continue
        # The UI declaration only holds screens of executed scenarios, so a gap
        # found there is a real failure even while another owner has not run.
        evidence_ok = all(
            item["present"]
            for step in (ui_evidence or {}).get("steps", [])
            if ac in step["target_ac"]
            for item in step["evidence"]
        )
        layout_ok = all(
            element["evaluated"]
            and element["within_safe_area"] is True
            and not element["occluded_by"]
            for snapshot in (ux_integrity or {}).get("snapshots", [])
            for element in snapshot["elements"]
            if ac in element["target_ac"]
        )
        if not (evidence_ok and layout_ok):
            results[ac] = "FAIL"
        elif len(executed) != len(owners):
            results[ac] = "NOT_RUN"
        else:
            results[ac] = "PASS"
    return results


def _scenario_run_ok(
    boundary: object, app_started: object, commands: dict[str, Any], source: object
) -> bool:
    """Run-level conditions every scenario AC depends on, whatever its own exit."""

    def _passed(phase: str) -> bool:
        result = commands.get(phase)
        return isinstance(result, dict) and result.get("exit_code") == 0

    return (
        isinstance(commands, dict)
        and boundary != "mock"
        and app_started is True
        and _passed("health")
        and _passed("cleanup")
        and source == "journey_exit"
    )


def _selected_scenarios(
    declared: Optional[list[dict[str, Any]]], requested: Optional[list[str]]
) -> set[str]:
    """Scenario ids to run: every declared one, or a validated re-run subset."""
    declared_ids = {str(item["scenario_id"]).strip() for item in declared or []}
    if requested is None:
        return declared_ids
    if declared is None:
        raise JourneyConfigError("--scenario is only valid for scenario manifests")
    unknown = sorted(set(requested) - declared_ids)
    if unknown or not requested:
        raise JourneyConfigError(f"unknown scenario: {', '.join(unknown) or '(none)'}")
    return set(requested)


def _run_scenarios(
    declared: list[dict[str, Any]],
    selected: set[str],
    root: Path,
    env: dict[str, str],
    run_dir: Path,
) -> list[dict[str, Any]]:
    """Run the selected scenarios in declared order, continuing past failures."""
    results: list[dict[str, Any]] = []
    for scenario in declared:
        scenario_id = str(scenario["scenario_id"]).strip()
        if scenario_id in selected:
            result = _run_command(
                scenario, root, env, run_dir / f"scenario-{scenario_id}.log"
            )
            results.append({"scenario_id": scenario_id, **result})
    return results


def _scenario_entries(
    declared: list[dict[str, Any]], results: list[dict[str, Any]], root: Path
) -> list[dict[str, Any]]:
    """One receipt entry per declared scenario, executed or not, with log hash."""
    ran = {item["scenario_id"]: item for item in results}
    entries: list[dict[str, Any]] = []
    for scenario_id, scenario_ac in _scenario_contract(declared):
        entry: dict[str, Any] = {
            "scenario_id": scenario_id,
            "target_ac": scenario_ac,
            "executed": scenario_id in ran,
            "exit_code": None,
            "timed_out": False,
            "duration_ms": None,
            "timeout_sec": None,
            "log_path": None,
            "sha256": None,
        }
        if scenario_id in ran:
            result = ran[scenario_id]
            entry.update(
                {key: value for key, value in result.items() if key != "scenario_id"}
            )
            entry["sha256"] = _sha256_file(root / result["log_path"])
        entries.append(entry)
    return entries


def _next_run_id(evidence_root: Path) -> str:
    """Allocate a fresh default run id so same-second runs of one epic do not collide."""
    base = f"run-{int(time.time())}"
    candidate = base
    suffix = 1
    while (evidence_root / candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
        if suffix > 999:
            raise JourneyConfigError("could not allocate a unique run_id")
    return candidate


def validate_config(
    project_root: Path | str, *, config_path: Path | str
) -> tuple[Path, Path, dict[str, Any], Path]:
    """Check the journey contract without executing any command or writing evidence."""
    root = Path(project_root).expanduser().resolve()
    raw_config_path = Path(config_path).expanduser()
    resolved_config = (
        raw_config_path.resolve()
        if raw_config_path.is_absolute()
        else (root / raw_config_path).resolve()
    )
    try:
        resolved_config.relative_to(root)
    except ValueError as exc:
        raise JourneyConfigError("config must stay inside the project root") from exc
    config, evidence_root = _validated_config(root, resolved_config)
    return root, resolved_config, config, evidence_root


def run_from_config(
    project_root: Path | str,
    *,
    config_path: Path | str,
    run_id: Optional[str] = None,
    measured_at: Optional[str] = None,
    scenarios: Optional[list[str]] = None,
) -> JourneyRunResult:
    """Execute start/health/journey (or scenarios)/cleanup and return the receipt.

    `scenarios` selects a subset of a scenario manifest for a fix-loop re-run.
    Such a receipt is marked partial and never counts as acceptance evidence.
    """
    root, resolved_config, config, evidence_root = validate_config(
        project_root, config_path=config_path
    )
    declared_scenarios = _validated_scenarios(config)
    partial = scenarios is not None
    selected = _selected_scenarios(declared_scenarios, scenarios)
    selected_run_id = run_id or _next_run_id(evidence_root)
    if not _ID_RE.fullmatch(selected_run_id):
        raise JourneyConfigError("run_id must match [a-z0-9][a-z0-9._-]{2,63}")
    selected_measured_at = measured_at or _now_iso()
    if _parse_ts(selected_measured_at) is None:
        raise JourneyConfigError("measured_at must be ISO-8601")
    run_dir = evidence_root / selected_run_id
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise JourneyConfigError(f"run_id already exists: {selected_run_id}") from exc
    receipt_path = run_dir / "receipt.json"
    # Read before any command runs: the journey itself may leave files behind.
    code_revision = _code_revision(root)
    uncommitted_changes = _uncommitted_changes(root)
    env = os.environ.copy()
    env.update(config.get("env", {}))
    env[_RUN_DIR_ENV] = str(run_dir)
    commands = config["commands"]
    command_results: dict[str, dict[str, Any]] = {}
    phases = _SCENARIO_PHASES if declared_scenarios is not None else _PHASES
    log_paths = {phase: run_dir / f"{phase}.log" for phase in phases}
    scenario_results: list[dict[str, Any]] = []
    failures: list[str] = []
    service: _ServiceHandle | None = None

    if config["boundary"] == "mock":
        _append_once(failures, "mock_only_boundary")

    start_spec = commands["start"]
    if start_spec["mode"] == "service":
        service, command_results["start"] = _start_service(
            start_spec, root, env, log_paths["start"]
        )
        app_started = service is not None
    else:
        command_results["start"] = _run_command(
            start_spec, root, env, log_paths["start"]
        )
        app_started = command_results["start"]["exit_code"] == 0

    journey_executed = False
    assertion_evaluated = False
    assertion_passed = False
    if not app_started:
        _append_once(failures, "app_not_started")
        _append_once(failures, "journey_not_executed")
        _append_once(failures, "assertion_not_evaluated")
    else:
        command_results["health"] = _run_command(
            commands["health"], root, env, log_paths["health"]
        )
        if command_results["health"]["exit_code"] != 0:
            _append_once(failures, "health_failed")
            _append_once(failures, "journey_not_executed")
            _append_once(failures, "assertion_not_evaluated")
        elif declared_scenarios is not None:
            scenario_results = _run_scenarios(
                declared_scenarios, selected, root, env, run_dir
            )
            journey_executed = True
            if config["assertion"]["source"] == "journey_exit":
                assertion_evaluated = True
                assertion_passed = all(
                    item["exit_code"] == 0 for item in scenario_results
                )
                if not assertion_passed:
                    _append_once(failures, "journey_failed")
            else:
                _append_once(failures, "assertion_not_evaluated")
        else:
            command_results["journey"] = _run_command(
                commands["journey"], root, env, log_paths["journey"]
            )
            journey_executed = True
            if config["assertion"]["source"] == "journey_exit":
                assertion_evaluated = True
                assertion_passed = command_results["journey"]["exit_code"] == 0
                if not assertion_passed:
                    _append_once(failures, "journey_failed")
            else:
                _append_once(failures, "assertion_not_evaluated")

    command_results["cleanup"] = _run_command(
        commands["cleanup"], root, env, log_paths["cleanup"]
    )
    if command_results["cleanup"]["exit_code"] != 0:
        _append_once(failures, "cleanup_failed")
    if service is not None:
        _stop_service(service, command_results["start"])

    ui_evidence: dict[str, Any] | None = None
    ui_evidence_types: set[str] = set()
    ux_integrity: dict[str, Any] | None = None
    if config["boundary"] == "ui":
        ui_config = _ui_config_for(config, selected, partial)
        ui_evidence, ui_complete, ui_evidence_types = _collect_ui_evidence(
            ui_config, run_dir, root
        )
        if not ui_complete:
            _append_once(failures, "ui_evidence_missing")
        ux_integrity, ux_integrity_reasons = _evaluate_ux_integrity(
            ui_config, run_dir, root
        )
        for reason in ux_integrity_reasons:
            _append_once(failures, reason)

    target_ac = [str(item).strip() for item in config["target_ac"]]
    scenario_entries: list[dict[str, Any]] = []
    ac_results: dict[str, str] = {}
    if declared_scenarios is not None:
        scenario_entries = _scenario_entries(declared_scenarios, scenario_results, root)
        ac_results = _derive_ac_results(
            target_ac,
            scenario_entries,
            _scenario_run_ok(
                config["boundary"],
                app_started,
                command_results,
                config["assertion"]["source"],
            ),
            ui_evidence,
            ux_integrity,
        )

    if declared_scenarios is None:
        outcome = (
            "PASS"
            if not failures
            and app_started
            and journey_executed
            and assertion_evaluated
            and assertion_passed
            else "FAIL"
        )
        passed_ac = len(target_ac) if outcome == "PASS" else 0
    else:
        passed_ac = sum(1 for verdict in ac_results.values() if verdict == "PASS")
        if partial:
            # A re-run judges only what it ran; ACs it skipped stay NOT_RUN.
            outcome = (
                "PASS"
                if assertion_passed and "FAIL" not in ac_results.values()
                else "FAIL"
            )
        else:
            outcome = (
                "PASS"
                if not failures and passed_ac == len(target_ac)
                else "FAIL"
            )
    evidence_paths = {
        phase: _relative(path, root)
        for phase, path in log_paths.items()
        if path.is_file()
    }
    evidence_paths["receipt"] = _relative(receipt_path, root)
    evidence_sha256 = {
        phase: _sha256_file(path)
        for phase, path in log_paths.items()
        if path.is_file()
    }
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "receipt_type": RECEIPT_TYPE,
        "run_id": selected_run_id,
        "journey_id": config["journey_id"],
        "config_path": _relative(resolved_config, root),
        "measured_at": selected_measured_at,
        "finished_at": _now_iso(),
        "code_revision": code_revision,
        "uncommitted_changes": uncommitted_changes,
        "outcome": outcome,
        "boundary": config["boundary"],
        "target_ac": target_ac,
        "product_ac": {
            "passed": passed_ac,
            "total": len(target_ac),
        },
        "human_intervention_count": config.get("human_intervention_count", 0),
        "evidence_types": sorted(
            {"command", config["boundary"], "log", *ui_evidence_types}
        ),
        "evidence_paths": evidence_paths,
        "evidence_sha256": evidence_sha256,
        "app_started": app_started,
        "journey_executed": journey_executed,
        "assertion": {
            "description": config["assertion"]["description"],
            "source": config["assertion"]["source"],
            "evaluated": assertion_evaluated,
            "passed": assertion_passed,
        },
        "commands": command_results,
        "failure_reasons": failures,
        "timeout_warnings": _timeout_warnings(
            {
                **command_results,
                **{
                    f"scenario:{entry['scenario_id']}": entry
                    for entry in scenario_entries
                    if entry["executed"]
                },
            }
        ),
    }
    if declared_scenarios is not None:
        receipt["scenarios"] = scenario_entries
        receipt["ac_results"] = ac_results
        receipt["partial"] = partial
        receipt["selected_scenarios"] = [
            entry["scenario_id"]
            for entry in scenario_entries
            if entry["scenario_id"] in selected
        ]
    epic_scope = _validated_epic_scope(config)
    if epic_scope is not None:
        receipt["epic_scope"] = {**epic_scope, "code_revision": code_revision}
    if ui_evidence is not None:
        receipt["ui_evidence"] = ui_evidence
    if ux_integrity is not None:
        receipt["ux_integrity"] = ux_integrity
    _write_receipt(receipt_path, receipt)
    return JourneyRunResult(0 if outcome == "PASS" else 1, receipt_path, receipt)


def read_receipts(
    project_root: Path | str, *, cutoff: Optional[datetime] = None
) -> list[dict[str, Any]]:
    """Read structurally valid helper-generated receipts for scorecard aggregation."""
    root = Path(project_root).expanduser().resolve()
    evidence_root = root / EVIDENCE_ROOT_REL
    if not evidence_root.is_dir():
        return []
    receipts: list[dict[str, Any]] = []
    for path in sorted(evidence_root.rglob("receipt.json")):
        if path.is_symlink():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        # A malformed receipt is discarded on its own; it must not abort the
        # Epic summary or scorecard that aggregate every other receipt.
        try:
            valid = _is_valid_receipt(payload, root, path)
        except (AttributeError, KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            continue
        measured = _parse_ts(payload.get("measured_at"))
        if cutoff is not None and (measured is None or measured > cutoff):
            continue
        normalized = dict(payload)
        normalized["receipt_path"] = _relative(path, root)
        receipts.append(normalized)
    return receipts


def _is_valid_receipt(payload: object, project_root: Path, receipt_path: Path) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("schema_version") != SCHEMA_VERSION:
        return False
    if payload.get("receipt_type") != RECEIPT_TYPE:
        return False
    if payload.get("outcome") not in {"PASS", "FAIL"}:
        return False
    if _parse_ts(payload.get("measured_at")) is None or not _valid_revision_fields(
        payload
    ):
        return False
    for key in ("run_id", "journey_id"):
        value = payload.get(key)
        if not isinstance(value, str) or not _ID_RE.fullmatch(value):
            return False
    boundary = payload.get("boundary")
    if boundary not in _BOUNDARIES:
        return False
    target_ac = payload.get("target_ac")
    product_ac = payload.get("product_ac")
    if not isinstance(target_ac, list) or not target_ac or not isinstance(product_ac, dict):
        return False
    if any(not isinstance(item, str) or not item.strip() for item in target_ac):
        return False
    passed = product_ac.get("passed")
    total = product_ac.get("total")
    if (
        not isinstance(passed, int)
        or isinstance(passed, bool)
        or not isinstance(total, int)
        or isinstance(total, bool)
    ):
        return False
    if total != len(target_ac) or passed < 0 or passed > total:
        return False
    intervention = payload.get("human_intervention_count")
    if (
        not isinstance(intervention, int)
        or isinstance(intervention, bool)
        or intervention < 0
    ):
        return False
    evidence_types = payload.get("evidence_types")
    if not isinstance(evidence_types, list) or any(
        not isinstance(item, str) or not item for item in evidence_types
    ):
        return False
    failure_reasons = payload.get("failure_reasons")
    if not isinstance(failure_reasons, list) or any(
        not isinstance(item, str) or not item for item in failure_reasons
    ):
        return False
    required_bools = ("app_started", "journey_executed")
    if any(not isinstance(payload.get(key), bool) for key in required_bools):
        return False
    assertion = payload.get("assertion")
    if not isinstance(assertion, dict):
        return False
    if any(not isinstance(assertion.get(key), bool) for key in ("evaluated", "passed")):
        return False
    if not isinstance(assertion.get("description"), str) or not assertion["description"]:
        return False
    if assertion.get("source") not in _ASSERTION_SOURCES:
        return False
    if payload["outcome"] == "PASS" and not (
        boundary != "mock"
        and payload["app_started"]
        and payload["journey_executed"]
        and assertion["evaluated"]
        and assertion["passed"]
        and passed == total
        and not failure_reasons
    ):
        return False
    scenario_mode = "scenarios" in payload
    if not _scenario_flags_consistent(payload):
        return False
    # Without scenarios one exit judges every AC; scenario receipts are recomputed below.
    if payload["outcome"] == "FAIL" and (
        not failure_reasons or (not scenario_mode and passed != 0)
    ):
        return False
    if not _valid_epic_scope_receipt(payload):
        return False
    if boundary == "ui":
        if not _valid_ui_receipt(payload, project_root, receipt_path):
            return False
        if not _valid_ux_integrity_receipt(payload, project_root, receipt_path):
            return False
    elif "ui_evidence" in payload or "ux_integrity" in payload:
        return False
    if scenario_mode and not _valid_scenario_receipt(payload, project_root, receipt_path):
        return False
    return _evidence_matches_receipt(payload, project_root, receipt_path)


def _valid_revision_fields(payload: dict[str, Any]) -> bool:
    """Receipts written before these fields existed stay valid without them."""
    if "code_revision" in payload:
        revision = payload["code_revision"]
        if not isinstance(revision, str) or not (
            revision == _UNKNOWN_REVISION or _REVISION_RE.fullmatch(revision)
        ):
            return False
    return payload.get("uncommitted_changes") in (None, True, False)


def _scenario_flags_consistent(payload: dict[str, Any]) -> bool:
    if "scenarios" not in payload:
        return not any(key in payload for key in _SCENARIO_RECEIPT_KEYS)
    # A partial re-run (or a malformed flag) is fix-loop output, never evidence.
    return payload.get("partial") is False


def _receipt_manifest(
    payload: dict[str, Any], project_root: Path
) -> Optional[dict[str, Any]]:
    """Load the tracked manifest a receipt claims it ran, if it stays in the project."""
    config_path = payload.get("config_path")
    if not isinstance(config_path, str):
        return None
    path = (project_root / config_path).resolve()
    try:
        path.relative_to(project_root.resolve())
    except ValueError:
        return None
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return config if isinstance(config, dict) else None


def _valid_scenario_log(
    entry: dict[str, Any], project_root: Path, run_dir: Path
) -> bool:
    log_path = entry.get("log_path")
    declared_hash = entry.get("sha256")
    if not isinstance(log_path, str) or not isinstance(declared_hash, str):
        return False
    path = (project_root / log_path).resolve()
    try:
        path.relative_to((project_root / EVIDENCE_ROOT_REL).resolve())
        path.relative_to(run_dir)
    except ValueError:
        return False
    if path.is_symlink() or not path.is_file():
        return False
    try:
        return _sha256_file(path) == declared_hash
    except OSError:
        return False


def _valid_scenario_receipt(
    payload: dict[str, Any], project_root: Path, receipt_path: Path
) -> bool:
    """Bind scenario AC ownership to the manifest and recompute every AC verdict."""
    scenarios = payload.get("scenarios")
    ac_results = payload.get("ac_results")
    selected = payload.get("selected_scenarios")
    if (
        not isinstance(scenarios, list)
        or not isinstance(ac_results, dict)
        or not isinstance(selected, list)
        or any(not isinstance(entry, dict) for entry in scenarios)
    ):
        return False
    config = _receipt_manifest(payload, project_root)
    if config is None:
        return False
    try:
        declared = _validated_scenarios(config)
    except (JourneyConfigError, AttributeError, KeyError, TypeError):
        return False
    if declared is None:
        return False
    contract = _scenario_contract(declared)
    # Without this a receipt could hand a failing scenario's AC to a passing one.
    if [str(item).strip() for item in config["target_ac"]] != payload["target_ac"]:
        return False
    if [(entry.get("scenario_id"), entry.get("target_ac")) for entry in scenarios] != [
        (scenario_id, scenario_ac) for scenario_id, scenario_ac in contract
    ]:
        return False
    if selected != [scenario_id for scenario_id, _ in contract]:
        return False
    run_dir = receipt_path.parent.resolve()
    for entry in scenarios:
        executed = entry.get("executed")
        # A full run executes every scenario exactly when the journey phase ran.
        if executed is not payload["journey_executed"]:
            return False
        if executed:
            exit_code = entry.get("exit_code")
            if not isinstance(exit_code, int) or isinstance(exit_code, bool):
                return False
            if not _valid_scenario_log(entry, project_root, run_dir):
                return False
        elif any(entry.get(key) is not None for key in ("exit_code", "log_path", "sha256")):
            return False
    if set(ac_results) != set(payload["target_ac"]) or any(
        not isinstance(verdict, str) or verdict not in _AC_VERDICTS
        for verdict in ac_results.values()
    ):
        return False
    recomputed = _derive_ac_results(
        payload["target_ac"],
        scenarios,
        _scenario_run_ok(
            payload["boundary"],
            payload["app_started"],
            payload["commands"],
            payload["assertion"]["source"],
        ),
        payload.get("ui_evidence"),
        payload.get("ux_integrity"),
    )
    if recomputed != ac_results:
        return False
    passed = sum(1 for verdict in recomputed.values() if verdict == "PASS")
    return passed == payload["product_ac"]["passed"]


def _valid_epic_scope_receipt(payload: dict[str, Any]) -> bool:
    scope = payload.get("epic_scope")
    if scope is None:
        return True
    if not isinstance(scope, dict) or set(scope) != _EPIC_SCOPE_RECEIPT_FIELDS:
        return False
    for key in _EPIC_SCOPE_ID_FIELDS:
        value = scope.get(key)
        if not isinstance(value, str) or not _ID_RE.fullmatch(value):
            return False
    for key in _EPIC_SCOPE_TEXT_FIELDS:
        value = scope.get(key)
        if not isinstance(value, str) or not value.strip():
            return False
    revision = scope.get("code_revision")
    if not isinstance(revision, str):
        return False
    return revision == _UNKNOWN_REVISION or bool(_REVISION_RE.fullmatch(revision))


def _valid_ui_receipt(
    payload: dict[str, Any], project_root: Path, receipt_path: Path
) -> bool:
    ui_evidence = payload.get("ui_evidence")
    if not isinstance(ui_evidence, dict):
        return False
    steps = ui_evidence.get("steps")
    if not isinstance(steps, list) or len(steps) < 2:
        return False
    target_ac = set(payload["target_ac"])
    final_ac: set[str] = set()
    step_ids: set[str] = set()
    all_present = True
    declared_types: set[str] = set()
    run_dir = receipt_path.parent.resolve()
    canonical_root = (project_root / EVIDENCE_ROOT_REL).resolve()
    for step in steps:
        if not isinstance(step, dict):
            return False
        step_id = step.get("step_id")
        if (
            not isinstance(step_id, str)
            or not _ID_RE.fullmatch(step_id)
            or step_id in step_ids
        ):
            return False
        step_ids.add(step_id)
        if not isinstance(step.get("description"), str) or not step["description"]:
            return False
        step_ac = step.get("target_ac")
        if (
            not isinstance(step_ac, list)
            or not step_ac
            or any(not isinstance(item, str) or not item for item in step_ac)
            or not set(step_ac).issubset(target_ac)
        ):
            return False
        if not isinstance(step.get("final"), bool):
            return False
        if step["final"]:
            final_ac.update(step_ac)
        evidence = step.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            return False
        for item in evidence:
            if not isinstance(item, dict) or item.get("type") not in _UI_EVIDENCE_TYPES:
                return False
            declared_path = item.get("path")
            present = item.get("present")
            declared_hash = item.get("sha256")
            if not isinstance(declared_path, str) or not isinstance(present, bool):
                return False
            path = (project_root / declared_path).resolve()
            try:
                path.relative_to(canonical_root)
                path.relative_to(run_dir)
            except ValueError:
                return False
            if present:
                if (
                    not isinstance(declared_hash, str)
                    or path.is_symlink()
                    or not path.is_file()
                    or path.stat().st_size == 0
                ):
                    return False
                try:
                    actual_hash = _sha256_file(path)
                except OSError:
                    return False
                if actual_hash != declared_hash:
                    return False
                declared_types.add(item["type"])
            else:
                all_present = False
                if declared_hash is not None or path.exists():
                    return False
    if final_ac != target_ac:
        return False
    if payload["outcome"] == "PASS" and not all_present:
        return False
    expected_types = {"command", "log", "ui", *declared_types}
    return set(payload["evidence_types"]) == expected_types


def _ac_contract(payload: dict[str, Any]) -> tuple[Any, ...]:
    """The AC ownership a UI journey claims, in a form manifest and receipt share."""
    return (
        [str(item).strip() for item in payload["target_ac"]],
        [
            (
                str(step["step_id"]).strip(),
                [str(item).strip() for item in step["target_ac"]],
                bool(step["final"]),
            )
            for step in payload["ui_evidence"]["steps"]
        ],
    )


def _receipt_ux_declaration(
    payload: dict[str, Any], project_root: Path
) -> Optional[list[dict[str, Any]]]:
    """Re-derive the judged declaration from the tracked manifest, not the receipt.

    Recomputing verdicts only proves internal consistency. Binding the declaration
    to the manifest is what stops a receipt from re-pointing the lens at a
    different, unobstructed element after the fact.
    """
    lens = payload["ux_integrity"]
    digest = lens.get("declaration_sha256")
    if not isinstance(digest, str):
        return None
    config = _receipt_manifest(payload, project_root)
    if config is None:
        return None
    try:
        _validated_ui_evidence(config)
        _validated_ux_integrity(config)
    except (JourneyConfigError, AttributeError, KeyError, TypeError):
        return None
    canonical = _canonical_ux_declaration(config["ux_integrity"])
    if _declaration_digest(canonical) != digest:
        return None
    # Without this the receipt could restate which AC the journey closed while
    # keeping the manifest-bound snapshots intact, crediting an untested AC.
    if _ac_contract(config) != _ac_contract(payload):
        return None
    return canonical


def _valid_ux_snapshot_receipt(
    declared: dict[str, Any],
    snapshot: object,
    project_root: Path,
    run_dir: Path,
) -> Optional[bool]:
    """Recompute one snapshot's verdicts and confirm they match what was recorded."""
    if not isinstance(snapshot, dict):
        return None
    if snapshot.get("step_id") != declared["step_id"]:
        return None
    if snapshot.get("mockup_reference") != declared["mockup_reference"]:
        return None
    report_meta = snapshot.get("layout_report")
    if not isinstance(report_meta, dict):
        return None
    declared_path = report_meta.get("path")
    present = report_meta.get("present")
    declared_hash = report_meta.get("sha256")
    if not isinstance(declared_path, str) or not isinstance(present, bool):
        return None
    target = run_dir / declared["layout_report"]
    if (project_root / declared_path).resolve() != target.resolve():
        return None
    # Reuse the generation-side probe so symlink, boundary, and hash rules
    # cannot drift between writing a receipt and consuming it.
    actual_present, actual_hash = _layout_report_state(target, run_dir)
    if actual_present != present or actual_hash != declared_hash:
        return None
    report = _parse_layout_report(target) if actual_present else None
    recomputed, _ = _judge_elements(report, declared["elements"])
    if recomputed != snapshot.get("elements"):
        return None
    return all(
        element["evaluated"]
        and element["within_safe_area"] is True
        and not element["occluded_by"]
        for element in recomputed
    )


def _valid_ux_integrity_receipt(
    payload: dict[str, Any], project_root: Path, receipt_path: Path
) -> bool:
    lens = payload.get("ux_integrity")
    if not isinstance(lens, dict):
        return False
    snapshots = lens.get("snapshots")
    if not isinstance(snapshots, list):
        return False
    declaration = _receipt_ux_declaration(payload, project_root)
    if declaration is None or len(snapshots) != len(declaration):
        return False
    run_dir = receipt_path.parent.resolve()
    unobstructed = True
    for declared, snapshot in zip(declaration, snapshots):
        judged = _valid_ux_snapshot_receipt(declared, snapshot, project_root, run_dir)
        if judged is None:
            return False
        unobstructed = unobstructed and judged
    return not (payload["outcome"] == "PASS" and not unobstructed)


def _evidence_matches_receipt(
    payload: dict[str, Any], project_root: Path, receipt_path: Path
) -> bool:
    commands = payload.get("commands")
    evidence_paths = payload.get("evidence_paths")
    evidence_sha256 = payload.get("evidence_sha256")
    if not isinstance(commands, dict):
        return False
    if not isinstance(evidence_paths, dict):
        return False
    if not isinstance(evidence_sha256, dict):
        return False
    declared_receipt = evidence_paths.get("receipt")
    if not isinstance(declared_receipt, str):
        return False
    if (project_root / declared_receipt).resolve() != receipt_path.resolve():
        return False
    if set(commands) != set(evidence_sha256):
        return False
    if not {"start", "cleanup"}.issubset(commands):
        return False
    phases = _SCENARIO_PHASES if "scenarios" in payload else _PHASES
    if not set(commands).issubset(phases):
        return False
    if payload["outcome"] == "PASS" and set(commands) != set(phases):
        return False
    canonical_root = (project_root / EVIDENCE_ROOT_REL).resolve()
    for phase, result in commands.items():
        if phase not in _PHASES or not isinstance(result, dict):
            return False
        exit_code = result.get("exit_code")
        if not isinstance(exit_code, int) or isinstance(exit_code, bool):
            return False
        declared_log = evidence_paths.get(phase)
        declared_hash = evidence_sha256.get(phase)
        if not isinstance(declared_log, str) or not isinstance(declared_hash, str):
            return False
        log_path = (project_root / declared_log).resolve()
        try:
            log_path.relative_to(canonical_root)
        except ValueError:
            return False
        if log_path.is_symlink() or not log_path.is_file():
            return False
        if result.get("log_path") != declared_log:
            return False
        try:
            actual_hash = _sha256_file(log_path)
        except OSError:
            return False
        if actual_hash != declared_hash:
            return False
    if payload["outcome"] == "PASS":
        for phase in phases[1:]:
            if commands[phase].get("exit_code") != 0:
                return False
    return True


def _written_ns(path: Path) -> int:
    """When a receipt file was written; orders runs recorded within one second.

    Receipt timestamps hold whole seconds, so a fast journey can finish twice
    with equal `measured_at` and `finished_at`.
    """
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def _journey_runs(project_root: Path, journey_id: str) -> list[dict[str, Any]]:
    """Every recorded run of one journey, oldest first, partial runs included.

    This is the history an agent weighs before another run, not acceptance
    evidence, so it does not apply the structural checks of `read_receipts`.
    Each record is reduced to what the history needs while it is read, and a
    record that cannot be reduced is dropped on its own: history is advisory
    and must never change the result of the run that prints it.
    """
    evidence_root = project_root / EVIDENCE_ROOT_REL
    if not evidence_root.is_dir():
        return []
    runs: list[dict[str, Any]] = []
    for path in sorted(evidence_root.rglob("receipt.json")):
        if path.is_symlink():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            run = _run_summary(payload, journey_id)
        except (
            OSError,
            ValueError,
            AttributeError,
            KeyError,
            TypeError,
            ArithmeticError,
            RecursionError,
        ):
            continue
        if run is not None:
            runs.append({**run, "written_ns": _written_ns(path)})
    runs.sort(
        key=lambda item: (
            item["measured"],
            item["finished_at"],
            item["written_ns"],
            item["run_id"],
        )
    )
    return runs


def _run_summary(payload: object, journey_id: str) -> Optional[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("receipt_type") != RECEIPT_TYPE:
        return None
    outcome = payload.get("outcome")
    measured_at = payload.get("measured_at")
    if payload.get("journey_id") != journey_id or outcome not in ("PASS", "FAIL"):
        return None
    measured = _parse_ts(measured_at) if isinstance(measured_at, str) else None
    if measured is None:
        return None
    executed = [item for item in _dict_items(payload.get("scenarios")) if item.get("executed")]
    failed_scenarios = [
        str(item.get("scenario_id")) for item in executed if item.get("exit_code") != 0
    ]
    reasons = {str(item) for item in payload.get("failure_reasons") or []}
    return {
        "measured": measured,
        "measured_at": measured_at,
        "finished_at": str(payload.get("finished_at") or ""),
        "run_id": str(payload.get("run_id") or ""),
        "outcome": outcome,
        "partial": payload.get("partial") is True,
        "duration_ms": _run_duration_ms(payload),
        "failure_signal": _failure_signal(payload) if outcome == "FAIL" else None,
        "passed_scenarios": [
            str(item.get("scenario_id")) for item in executed if item.get("exit_code") == 0
        ],
        "failed_scenarios": failed_scenarios,
        "declared_scenarios": [
            str(item.get("scenario_id")) for item in _dict_items(payload.get("scenarios"))
        ],
        # A failure that is not just "these scenarios exited non-zero" (start,
        # health, cleanup, screen evidence, layout) is not tied to one scenario.
        "run_level_failure": outcome == "FAIL"
        and not (failed_scenarios and reasons <= {"journey_failed"}),
    }


def _dict_items(value: object) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _run_duration_ms(receipt: dict[str, Any]) -> int:
    commands = receipt.get("commands")
    timed = [
        *(commands.values() if isinstance(commands, dict) else []),
        *_dict_items(receipt.get("scenarios")),
    ]
    return sum(
        item["duration_ms"]
        for item in timed
        if isinstance(item, dict) and _plausible_duration_ms(item.get("duration_ms"))
    )


def _plausible_duration_ms(value: object) -> bool:
    """A recorded phase time that can be summed: a real number within one day."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return 0 <= value <= _HISTORY_DURATION_MAX_MS


def _failure_signal(receipt: dict[str, Any]) -> str:
    """What a failed run reported, comparable across full and partial runs.

    It holds failure reasons, failed phase and scenario exit codes, missing
    screen evidence and failing layout elements. Log text is not part of it,
    so two different defects behind one exit code share a signal.
    """
    commands = receipt.get("commands")
    ui_evidence = receipt.get("ui_evidence")
    ux_integrity = receipt.get("ux_integrity")
    evidence_paths = receipt.get("evidence_paths")
    receipt_rel = evidence_paths.get("receipt") if isinstance(evidence_paths, dict) else None
    # Evidence paths start with the run directory, which differs on every run.
    run_prefix = (
        receipt_rel.rsplit("/", 1)[0] + "/"
        if isinstance(receipt_rel, str) and "/" in receipt_rel
        else ""
    )
    signal_parts = {
        "reasons": sorted(str(item) for item in receipt.get("failure_reasons") or []),
        "phases": sorted(
            [phase, result.get("exit_code")]
            for phase, result in (commands.items() if isinstance(commands, dict) else [])
            if isinstance(result, dict) and result.get("exit_code") != 0
        ),
        "scenarios": sorted(
            [str(item.get("scenario_id")), item.get("exit_code")]
            for item in _dict_items(receipt.get("scenarios"))
            if item.get("executed") and item.get("exit_code") != 0
        ),
        "missing_evidence": sorted(
            [str(step.get("step_id")), str(item.get("path", "")).removeprefix(run_prefix)]
            for step in _dict_items(
                ui_evidence.get("steps") if isinstance(ui_evidence, dict) else None
            )
            for item in _dict_items(step.get("evidence"))
            if not item.get("present")
        ),
        "elements": sorted(
            [
                str(snapshot.get("step_id")),
                str(element.get("element_id")),
                bool(element.get("evaluated")),
                str(element.get("within_safe_area")),
                sorted(str(item) for item in element.get("occluded_by") or []),
            ]
            for snapshot in _dict_items(
                ux_integrity.get("snapshots") if isinstance(ux_integrity, dict) else None
            )
            for element in _dict_items(snapshot.get("elements"))
            if not element.get("evaluated")
            or element.get("within_safe_area") is not True
            or element.get("occluded_by")
        ),
    }
    return json.dumps(signal_parts, ensure_ascii=False, sort_keys=True)


def journey_history(project_root: Path | str, journey_id: str) -> dict[str, Any]:
    """Cumulative cost of one journey and whether its latest failure repeats."""
    root = Path(project_root).expanduser().resolve()
    runs = _journey_runs(root, journey_id)
    failing: list[dict[str, Any]] = []
    for run in reversed(runs):
        if run["outcome"] != "FAIL":
            break
        failing.append(run)
    same_signal = 0
    for run in failing:
        if run["failure_signal"] != failing[0]["failure_signal"]:
            break
        same_signal += 1
    return {
        "journey_id": journey_id,
        "runs": len(runs),
        "failed": sum(1 for run in runs if run["outcome"] == "FAIL"),
        "partial": sum(1 for run in runs if run["partial"]),
        "duration_ms": sum(run["duration_ms"] for run in runs),
        "consecutive_failures": len(failing),
        "consecutive_failure_duration_ms": sum(run["duration_ms"] for run in failing),
        "same_signal_streak": same_signal,
        "previous_outcome": runs[-2]["outcome"] if len(runs) > 1 else None,
    }


def _format_duration(duration_ms: float) -> str:
    seconds = round(duration_ms / 1000)
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{seconds:02d}s"
    return f"{seconds}s"


def _history_lines(receipt: dict[str, Any], history: dict[str, Any]) -> list[str]:
    """Lines an agent reads after each run to judge whether another run pays off."""
    uncommitted = receipt.get("uncommitted_changes")
    dirty = "unknown" if uncommitted is None else ("yes" if uncommitted else "no")
    lines = [
        f"journey={receipt['journey_id']} outcome={receipt['outcome']} "
        f"code_revision={receipt.get('code_revision', _UNKNOWN_REVISION)} "
        f"uncommitted_changes={dirty}",
        f"cumulative runs={history['runs']} failed={history['failed']} "
        f"partial={history['partial']} duration={_format_duration(history['duration_ms'])}",
    ]
    if receipt["outcome"] != "FAIL":
        return lines
    lines.append(
        f"consecutive failures={history['consecutive_failures']} "
        f"duration={_format_duration(history['consecutive_failure_duration_ms'])}"
    )
    if history["previous_outcome"] is None:
        relation = "no previous run"
    elif history["previous_outcome"] != "FAIL":
        relation = "previous run passed"
    elif history["same_signal_streak"] > 1:
        relation = (
            f"same as the previous run, {history['same_signal_streak']} runs in a row"
        )
    else:
        relation = "differs from the previous run"
    lines.append(
        f"failure signal: {relation} (compares failure reasons, failed phase and "
        "scenario exit codes, missing screen evidence and failing layout elements; "
        "log text is not compared)"
    )
    return lines


_WHOLE_JOURNEY = "*"


def _unresolved_failure(
    later_runs: list[dict[str, Any]], targets: Optional[list[str]]
) -> Optional[dict[str, Any]]:
    """The latest failure of the skip targets that the same target has not passed since.

    A pass only backs a skip while it is the target's most recent result, so the
    state is kept per target. A failure that is not tied to one scenario marks
    every target, and only a target that itself passes again is cleared.
    `targets` is the scenario list, or None for a journey without scenarios.
    """
    wanted = [_WHOLE_JOURNEY] if targets is None else list(targets)
    failing: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, run in enumerate(later_runs):
        if run["run_level_failure"]:
            for target in {*wanted, *run["declared_scenarios"]}:
                failing[target] = (index, run)
            continue
        if run["outcome"] == "PASS" and not run["declared_scenarios"]:
            failing.pop(_WHOLE_JOURNEY, None)
        for scenario_id in run["passed_scenarios"]:
            failing.pop(scenario_id, None)
        for scenario_id in run["failed_scenarios"]:
            failing[scenario_id] = (index, run)
    blocking = [failing[target] for target in wanted if target in failing]
    return max(blocking, key=lambda item: item[0])[1] if blocking else None


def record_skip(
    project_root: Path | str,
    *,
    config_path: Path | str,
    reason: str,
    scenarios: Optional[list[str]] = None,
    run_id: Optional[str] = None,
    recorded_at: Optional[str] = None,
) -> Path:
    """Record that a journey (or some scenarios) was deliberately not re-run.

    The record names the reason and the full PASS it relies on, so a later
    failure of a skipped target can be traced back to this decision. It is not
    a receipt: the Epic summary and the scorecard never read it.
    """
    root, resolved_config, config, evidence_root = validate_config(
        project_root, config_path=config_path
    )
    if not isinstance(reason, str) or not reason.strip():
        raise JourneyConfigError("reason must say why the change cannot reach the target")
    declared = _validated_scenarios(config)
    skipped: Optional[list[str]] = None
    if declared is not None or scenarios is not None:
        selected = _selected_scenarios(declared, scenarios)
        skipped = [
            scenario_id
            for scenario_id, _target_ac in _scenario_contract(declared or [])
            if scenario_id in selected
        ]
    selected_run_id = run_id or _next_run_id(evidence_root)
    if not _ID_RE.fullmatch(selected_run_id):
        raise JourneyConfigError("run_id must match [a-z0-9][a-z0-9._-]{2,63}")
    selected_recorded_at = recorded_at or _now_iso()
    if _parse_ts(selected_recorded_at) is None:
        raise JourneyConfigError("recorded_at must be ISO-8601")
    journey_id = config["journey_id"]
    passes = [
        receipt
        for receipt in read_receipts(root)
        if receipt["journey_id"] == journey_id and receipt["outcome"] == "PASS"
    ]
    basis: Optional[dict[str, Any]] = None
    if passes:
        latest = max(
            passes,
            key=lambda item: (
                _parse_ts(item["measured_at"]),
                str(item.get("finished_at") or ""),
                _written_ns(root / item["receipt_path"]),
                str(item["run_id"]),
            ),
        )
        basis = {
            "run_id": latest["run_id"],
            "measured_at": latest["measured_at"],
            "code_revision": latest.get("code_revision", _UNKNOWN_REVISION),
            "receipt_path": latest["receipt_path"],
        }
    unresolved: Optional[dict[str, Any]] = None
    if basis is not None:
        history = _journey_runs(root, journey_id)
        position = max(
            (index for index, run in enumerate(history) if run["run_id"] == basis["run_id"]),
            default=len(history) - 1,
        )
        failure = _unresolved_failure(history[position + 1 :], skipped)
        if failure is not None:
            unresolved = {
                "run_id": failure["run_id"],
                "measured_at": failure["measured_at"],
            }
            basis = None
    run_dir = evidence_root / selected_run_id
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise JourneyConfigError(f"run_id already exists: {selected_run_id}") from exc
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "record_type": SKIP_RECORD_TYPE,
        "run_id": selected_run_id,
        "journey_id": journey_id,
        "config_path": _relative(resolved_config, root),
        "recorded_at": selected_recorded_at,
        "code_revision": _code_revision(root),
        "uncommitted_changes": _uncommitted_changes(root),
        "reason": reason.strip(),
        "basis": basis,
    }
    if skipped is not None:
        record["scenarios"] = skipped
    if unresolved is not None:
        record["unresolved_failure"] = unresolved
    path = run_dir / "skip.json"
    _write_receipt(path, record)
    return path


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="project-local product journey runner"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="execute one journey contract")
    run_parser.add_argument("--project-root", default=".")
    run_parser.add_argument("--config", required=True)
    run_parser.add_argument("--run-id", default=None)
    run_parser.add_argument("--measured-at", default=None)
    run_parser.add_argument(
        "--scenario",
        dest="scenarios",
        action="append",
        default=None,
        help="re-run only this scenario (repeatable); the receipt is partial",
    )
    skip_parser = subparsers.add_parser(
        "skip", help="record why a journey or scenario was not re-run"
    )
    skip_parser.add_argument("--project-root", default=".")
    skip_parser.add_argument("--config", required=True)
    skip_parser.add_argument("--reason", required=True)
    skip_parser.add_argument("--run-id", default=None)
    skip_parser.add_argument(
        "--scenario",
        dest="scenarios",
        action="append",
        default=None,
        help="scenario that was not re-run (repeatable); omit for the whole journey",
    )
    validate_parser = subparsers.add_parser(
        "validate", help="check one journey contract without running it"
    )
    validate_parser.add_argument("--project-root", default=".")
    validate_parser.add_argument("--config", required=True)
    summary_parser = subparsers.add_parser(
        "epic-summary", help="report one epic's representative-flow result"
    )
    summary_parser.add_argument("--project-root", default=".")
    summary_parser.add_argument("--epic", required=True)
    args = parser.parse_args(argv)
    if args.command == "epic-summary":
        from harness import epic_outcome

        return epic_outcome.cli_epic_summary(args.project_root, args.epic)
    if args.command == "validate":
        try:
            validate_config(args.project_root, config_path=args.config)
        except JourneyConfigError as exc:
            print(f"[product-journey] contract error: {exc}", file=sys.stderr)
            return 2
        print("[product-journey] contract PASS")
        return 0
    if args.command == "skip":
        try:
            skip_path = record_skip(
                args.project_root,
                config_path=args.config,
                reason=args.reason,
                scenarios=args.scenarios,
                run_id=args.run_id,
            )
        except JourneyConfigError as exc:
            print(f"[product-journey] contract error: {exc}", file=sys.stderr)
            return 2
        print(skip_path)
        skip_record = json.loads(skip_path.read_text(encoding="utf-8"))
        basis = skip_record["basis"]
        if "unresolved_failure" in skip_record:
            print(
                "[product-journey] this target failed after the last full PASS "
                f"(run={skip_record['unresolved_failure']['run_id']}) and has not "
                "passed since: nothing backs this skip"
            )
        elif basis is None:
            print(
                "[product-journey] no earlier full PASS of this journey: "
                "nothing backs this skip"
            )
        else:
            print(
                f"[product-journey] relies on PASS run={basis['run_id']} "
                f"code_revision={basis['code_revision']}"
            )
        return 0
    try:
        result = run_from_config(
            args.project_root,
            config_path=args.config,
            run_id=args.run_id,
            measured_at=args.measured_at,
            scenarios=args.scenarios,
        )
    except JourneyConfigError as exc:
        print(f"[product-journey] contract error: {exc}", file=sys.stderr)
        return 2
    print(result.receipt_path)
    # History is advisory: whatever goes wrong while reading old records, the
    # exit code stays the verdict of the run that just finished.
    try:
        history = journey_history(args.project_root, result.receipt["journey_id"])
        lines = _history_lines(result.receipt, history)
    except Exception as exc:  # noqa: BLE001
        print(f"[product-journey] history unavailable: {exc}", file=sys.stderr)
        lines = []
    for line in lines:
        print(f"[product-journey] {line}")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run a project-local non-UI product journey and emit a verifiable receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
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


CONFIG_REL = Path(".dcness/product-journey.json")
EVIDENCE_ROOT_REL = Path(".dcness-work/product-journey")
SCHEMA_VERSION = 1
RECEIPT_TYPE = "dcness.product-journey"
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_BOUNDARIES = {"api", "cli", "integration", "mock"}
_ASSERTION_SOURCES = {"journey_exit", "none"}
_PHASES = ("start", "health", "journey", "cleanup")


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


def _command_spec(commands: dict[str, Any], phase: str) -> dict[str, Any]:
    raw = commands.get(phase)
    if not isinstance(raw, dict):
        raise JourneyConfigError(f"commands.{phase} must be an object")
    argv = raw.get("argv")
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(item, str) or not item for item in argv)
    ):
        raise JourneyConfigError(f"commands.{phase}.argv must be non-empty strings")
    timeout = raw.get("timeout_sec", 60)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
        raise JourneyConfigError(f"commands.{phase}.timeout_sec must be numeric")
    if timeout <= 0 or timeout > 600:
        raise JourneyConfigError(f"commands.{phase}.timeout_sec must be in (0, 600]")
    return raw


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
    for phase in _PHASES:
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
        "log_path": _relative(log_path, project_root),
    }


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


def run_from_config(
    project_root: Path | str,
    *,
    config_path: Path | str = CONFIG_REL,
    run_id: Optional[str] = None,
    measured_at: Optional[str] = None,
) -> JourneyRunResult:
    """Execute start/health/journey/cleanup and return the generated receipt."""
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
    selected_run_id = run_id or f"run-{int(time.time())}"
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
    env = os.environ.copy()
    env.update(config.get("env", {}))
    commands = config["commands"]
    command_results: dict[str, dict[str, Any]] = {}
    log_paths = {phase: run_dir / f"{phase}.log" for phase in _PHASES}
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

    outcome = (
        "PASS"
        if not failures
        and app_started
        and journey_executed
        and assertion_evaluated
        and assertion_passed
        else "FAIL"
    )
    target_ac = [str(item).strip() for item in config["target_ac"]]
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
        "outcome": outcome,
        "boundary": config["boundary"],
        "target_ac": target_ac,
        "product_ac": {
            "passed": len(target_ac) if outcome == "PASS" else 0,
            "total": len(target_ac),
        },
        "human_intervention_count": config.get("human_intervention_count", 0),
        "evidence_types": sorted({"command", config["boundary"], "log"}),
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
    }
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
        if not _is_valid_receipt(payload, root, path):
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
    if _parse_ts(payload.get("measured_at")) is None:
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
    if payload["outcome"] == "FAIL" and (passed != 0 or not failure_reasons):
        return False
    return _evidence_matches_receipt(payload, project_root, receipt_path)


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
    if payload["outcome"] == "PASS" and set(commands) != set(_PHASES):
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
        for phase in ("health", "journey", "cleanup"):
            if commands[phase].get("exit_code") != 0:
                return False
    return True


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="project-local non-UI product journey runner"
    )
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--config", default=CONFIG_REL.as_posix())
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--measured-at", default=None)
    args = parser.parse_args(argv)
    try:
        result = run_from_config(
            args.project_root,
            config_path=args.config,
            run_id=args.run_id,
            measured_at=args.measured_at,
        )
    except JourneyConfigError as exc:
        print(f"[product-journey] contract error: {exc}", file=sys.stderr)
        return 2
    print(result.receipt_path)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())

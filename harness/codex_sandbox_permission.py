"""Codex workspace-write sandbox permission recovery receipts.

The build-worker keeps prose as its output contract.  This helper reads that
prose together with the raw provider log and records only narrowly recognised
sandbox denials.  It also owns the user-approved, single Codex retry so the
provider chain cannot silently widen permissions or fall through elsewhere.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess  # nosec B404
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence


RECEIPT_TYPE = "dcness.codex-sandbox-permission"
RECEIPT_VERSION = 1
NETWORK_ENV = "DCNESS_CODEX_NETWORK_ACCESS"
WRITABLE_ROOTS_ENV = "DCNESS_CODEX_WRITABLE_ROOTS"
RETRY_RECEIPT_ENV = "DCNESS_CODEX_PERMISSION_RECEIPT"

_NETWORK_SIGNATURES = (
    re.compile(r"java\.net\.SocketException:\s*Operation not permitted", re.I),
    re.compile(r"(?:bind|listen|loopback|socket).{0,120}Operation not permitted", re.I),
)
_WRITABLE_SIGNATURE = re.compile(
    r"(?:Codex\s+)?sandbox denied write to\s+(?P<path>/[^\r\n]+)", re.I
)
_INFRA_FAILURES = (
    re.compile(r"codex CLI not found", re.I),
    re.compile(r"\b(?:401|403)\b.{0,80}(?:unauthorized|authentication|auth\b)", re.I),
    re.compile(r"\b(?:authentication|auth) (?:failed|required)\b", re.I),
    re.compile(r"(?:idle|total) timeout after", re.I),
    re.compile(r"codex exec failed before workspace mutation", re.I),
)
_GRADLE_HOME = re.compile(r"^\s*GRADLE_USER_HOME\s*[=:]\s*(?P<path>.+?)\s*$", re.I)
_FINAL_PROSE_MARKER = "----- CODEX OUTPUT-LAST-MESSAGE / FINAL PROSE -----"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    from harness.session_state import atomic_write

    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_write(path, data.encode("utf-8"))


def _load_receipt(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"permission receipt를 읽을 수 없습니다: {path}: {exc}") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("receipt_type") != RECEIPT_TYPE
        or payload.get("receipt_version") != RECEIPT_VERSION
    ):
        raise ValueError(f"지원하지 않는 permission receipt입니다: {path}")
    return payload


def _conclusion_is_validation_blocked(prose: str) -> bool:
    from harness.run_review import _extract_conclusion_enum

    return _extract_conclusion_enum(prose) == "VALIDATION_BLOCKED"


def _evidence_line(text: str, pattern: re.Pattern[str]) -> Optional[str]:
    for line in text.splitlines():
        if pattern.search(line):
            return line.strip()[:500]
    return None


def _clean_path_token(raw: str) -> str:
    value = raw.strip().strip("'\"")
    for marker in (" (", " [", ": "):
        if marker in value:
            value = value.split(marker, 1)[0]
    return value.rstrip(".,;:")


def _normalise_gradle_root(path: Path) -> Path:
    parts = path.parts
    if ".gradle" in parts:
        index = parts.index(".gradle")
        return Path(*parts[: index + 1])
    return path


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _root_is_safe(path: Path, project_root: Path) -> bool:
    if not path.is_absolute():
        return False
    resolved = path.resolve(strict=False)
    project = project_root.resolve(strict=False)
    home = Path.home().resolve(strict=False)
    if resolved in {Path("/"), home, project.parent}:
        return False
    if resolved.name.lower() in {"home", "private", "tmp", "users", "var"}:
        return False
    if len(resolved.parts) < 4:
        return False
    return not _path_is_within(resolved, project)


def _sandbox_denied_paths(raw_log: str) -> list[Path]:
    paths: list[Path] = []
    for match in _WRITABLE_SIGNATURE.finditer(raw_log):
        token = _clean_path_token(match.group("path"))
        candidate = Path(os.path.expanduser(token))
        if candidate.is_absolute():
            paths.append(candidate.resolve(strict=False))
    return paths


def _suggested_gradle_roots(raw_log: str, project_root: Path) -> list[Path]:
    denied_paths = _sandbox_denied_paths(raw_log)
    explicit_candidates: list[Path] = []
    for line in raw_log.splitlines():
        match = _GRADLE_HOME.match(line)
        if match:
            token = _clean_path_token(match.group("path"))
            candidate = Path(os.path.expanduser(token))
            resolved = candidate.resolve(strict=False)
            if _root_is_safe(candidate, project_root) and any(
                _path_is_within(denied, resolved) for denied in denied_paths
            ):
                explicit_candidates.append(resolved)

    candidates = list(explicit_candidates)
    if not explicit_candidates:
        for denied in denied_paths:
            candidate = _normalise_gradle_root(denied)
            if candidate.name not in {".gradle", ".konan"}:
                continue
            if _root_is_safe(candidate, project_root):
                candidates.append(candidate.resolve(strict=False))

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _writable_evidence_line(raw_log: str, roots: Sequence[Path]) -> Optional[str]:
    for line in raw_log.splitlines():
        match = _WRITABLE_SIGNATURE.search(line)
        if not match:
            continue
        token = _clean_path_token(match.group("path"))
        denied = Path(os.path.expanduser(token))
        if not denied.is_absolute():
            continue
        resolved = denied.resolve(strict=False)
        if any(_path_is_within(resolved, root) for root in roots):
            return line.strip()[:500]
    return None


def _classify(
    *, prose: str, raw_log: str, project_root: Path
) -> Optional[dict[str, Any]]:
    if not _conclusion_is_validation_blocked(prose):
        return None
    if any(pattern.search(raw_log) for pattern in _INFRA_FAILURES):
        return None

    capabilities: list[str] = []
    evidence: list[dict[str, str]] = []

    for signature in _NETWORK_SIGNATURES:
        line = _evidence_line(raw_log, signature)
        if line:
            capabilities.append("network_access")
            evidence.append(
                {
                    "capability": "network_access",
                    "signature": line,
                    "reason": "Codex workspace-write 안의 socket bind/listen 거부",
                }
            )
            break

    roots = _suggested_gradle_roots(raw_log, project_root)
    write_line = _writable_evidence_line(raw_log, roots)
    if write_line and roots:
        capabilities.append("writable_roots")
        evidence.append(
            {
                "capability": "writable_roots",
                "signature": write_line,
                "reason": "로그에서 확인된 Gradle cache root에 대한 sandbox write 거부",
            }
        )

    if not capabilities:
        return None

    return {
        "capabilities": capabilities,
        "suggested_writable_roots": [str(path) for path in roots]
        if "writable_roots" in capabilities
        else [],
        "evidence": evidence,
    }


def _provider_log_evidence(raw_log: str) -> str:
    """Exclude the wrapper-appended final prose from execution evidence."""
    return raw_log.split(_FINAL_PROSE_MARKER, 1)[0]


def _append_ledger_event(
    *,
    sid: Optional[str],
    rid: Optional[str],
    receipt_path: Path,
    receipt: Mapping[str, Any],
) -> None:
    if not sid or not rid:
        return
    try:
        from harness import ledger

        state = str(receipt.get("state", "permission_required"))
        ledger.append_event(
            sid,
            rid,
            "blocked",
            agent="build-worker",
            provider="codex-headless",
            category=(
                "codex_sandbox_permission_retry_blocked"
                if state == "retry_blocked"
                else "codex_sandbox_permission_required"
            ),
            receipt_file=str(receipt_path),
            capabilities=receipt.get("capabilities", []),
            suggested_writable_roots=receipt.get("suggested_writable_roots", []),
            detail=(
                "Codex workspace-write sandbox denial requires explicit user approval"
            ),
        )
    except Exception as exc:  # noqa: BLE001
        print(
            "[dcness-codex-permission] WARN: permission ledger event 기록 실패: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )


def record_permission_required(
    *,
    prose_path: Path,
    raw_log_path: Path,
    project_root: Path,
    receipt_path: Path,
    retry_receipt_path: Optional[Path] = None,
    sid: Optional[str] = None,
    rid: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Classify evidence and atomically create/update a permission receipt."""
    prose = _read_text(prose_path)
    if not _conclusion_is_validation_blocked(prose):
        return None
    raw_log = _read_text(raw_log_path)
    classified = _classify(
        prose=prose,
        raw_log=_provider_log_evidence(raw_log),
        project_root=project_root,
    )
    if classified is None:
        if retry_receipt_path is not None and _conclusion_is_validation_blocked(prose):
            receipt = _load_receipt(retry_receipt_path)
            receipt.update(
                {
                    "state": "retry_blocked",
                    "updated_at": _now_iso(),
                    "repeat_evidence": [],
                    "repeat_reason": (
                        "approved retry still reported VALIDATION_BLOCKED; "
                        "no further permission expansion"
                    ),
                    "raw_log": str(raw_log_path),
                    "prose_file": str(prose_path),
                }
            )
            _atomic_write_json(retry_receipt_path, receipt)
            _append_ledger_event(
                sid=sid,
                rid=rid,
                receipt_path=retry_receipt_path,
                receipt=receipt,
            )
            return receipt
        return None

    target = retry_receipt_path or receipt_path
    if retry_receipt_path is not None:
        receipt = _load_receipt(retry_receipt_path)
        receipt.update(
            {
                "state": "retry_blocked",
                "updated_at": _now_iso(),
                "repeat_evidence": classified["evidence"],
                "raw_log": str(raw_log_path),
                "prose_file": str(prose_path),
            }
        )
    else:
        receipt = {
            "receipt_type": RECEIPT_TYPE,
            "receipt_version": RECEIPT_VERSION,
            "state": "permission_required",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "project_root": str(project_root.resolve(strict=False)),
            "sandbox": "workspace-write",
            "danger_full_access": False,
            "retry_count": 0,
            "prose_file": str(prose_path),
            "raw_log": str(raw_log_path),
            **classified,
        }
    _atomic_write_json(target, receipt)
    _append_ledger_event(sid=sid, rid=rid, receipt_path=target, receipt=receipt)
    return receipt


def _approved_env(receipt: Mapping[str, Any], project_root: Path) -> dict[str, str]:
    capabilities = receipt.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        raise ValueError("permission receipt에 승인할 capability가 없습니다")
    if any(item not in {"network_access", "writable_roots"} for item in capabilities):
        raise ValueError("permission receipt에 지원하지 않는 capability가 있습니다")

    approved: dict[str, str] = {}
    if "network_access" in capabilities:
        approved[NETWORK_ENV] = "1"
    if "writable_roots" in capabilities:
        roots = receipt.get("suggested_writable_roots")
        if not isinstance(roots, list) or not roots:
            raise ValueError("안전하게 추론된 writable root가 없습니다")
        safe_roots: list[str] = []
        for raw in roots:
            if not isinstance(raw, str):
                raise ValueError("writable root는 절대경로 문자열이어야 합니다")
            path = Path(raw)
            if not _root_is_safe(path, project_root):
                raise ValueError(f"안전하지 않은 writable root 제안입니다: {raw}")
            safe_roots.append(str(path.resolve(strict=False)))
        approved[WRITABLE_ROOTS_ENV] = os.pathsep.join(safe_roots)
    return approved


def _merge_project_settings(settings_path: Path, approved: Mapping[str, str]) -> None:
    if settings_path.exists():
        original = settings_path.read_bytes()
        try:
            payload = json.loads(original.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"malformed settings 파일은 덮어쓰지 않습니다: {settings_path}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError(f"settings 최상위 값이 JSON object가 아닙니다: {settings_path}")
    else:
        payload = {}

    existing_env = payload.get("env")
    if existing_env is None:
        existing_env = {}
    if not isinstance(existing_env, dict):
        raise ValueError(f"settings env 값이 JSON object가 아닙니다: {settings_path}")
    merged_env = dict(existing_env)
    merged_env.update(approved)
    payload["env"] = merged_env
    _atomic_write_json(settings_path, payload)


def _update_receipt(path: Path, receipt: dict[str, Any], **fields: Any) -> None:
    receipt.update(fields)
    receipt["updated_at"] = _now_iso()
    _atomic_write_json(path, receipt)


def retry_main(
    *,
    receipt_path: Path,
    decision: str,
    project_root: Path,
    prompt_file: Path,
    worker_path: Path,
    helper_path: Path,
    run: Callable[..., Any] = subprocess.run,
    environ: Optional[Mapping[str, str]] = None,
) -> int:
    """Apply one explicit decision and run the Codex worker at most once."""
    try:
        receipt = _load_receipt(receipt_path)
        project = project_root.resolve(strict=False)
        stored_project = receipt.get("project_root")
        if not isinstance(stored_project, str) or not Path(stored_project).is_absolute():
            raise ValueError("permission receipt에 유효한 project root가 없습니다")
        if Path(stored_project).resolve(strict=False) != project:
            raise ValueError("permission receipt의 project root가 현재 프로젝트와 다릅니다")
        retry_count = receipt.get("retry_count")
        if not isinstance(retry_count, int) or retry_count != 0:
            raise ValueError("승인 후 Codex 자동 재시도는 이미 사용됐거나 상태가 잘못됐습니다")
        if receipt.get("state") != "permission_required":
            raise ValueError(f"재시도할 수 없는 receipt 상태입니다: {receipt.get('state')}")
        if decision == "deny":
            _update_receipt(receipt_path, receipt, state="denied", decision="deny")
            print(
                "[dcness-codex-permission] 사용자가 권한 확대를 거부했습니다; "
                "VALIDATION_BLOCKED를 유지합니다.",
                file=sys.stderr,
            )
            return 3
        if decision not in {"once", "project"}:
            raise ValueError(f"지원하지 않는 승인 선택입니다: {decision}")
        approved = _approved_env(receipt, project)
        if not prompt_file.is_file():
            raise ValueError(f"재시도 prompt 파일이 없습니다: {prompt_file}")
        if decision == "project":
            _merge_project_settings(
                project / ".claude" / "settings.local.json", approved
            )
    except (OSError, ValueError) as exc:
        print(f"[dcness-codex-permission] BLOCKED: {exc}", file=sys.stderr)
        return 2

    _update_receipt(
        receipt_path,
        receipt,
        state="retrying",
        decision=decision,
        retry_count=1,
        approved_env_keys=sorted(approved),
    )
    child_env = dict(environ if environ is not None else os.environ)
    child_env.pop(NETWORK_ENV, None)
    child_env.pop(WRITABLE_ROOTS_ENV, None)
    child_env.update(approved)
    child_env[RETRY_RECEIPT_ENV] = str(receipt_path)

    command = [
        str(worker_path),
        "build-worker",
        "--prompt-file",
        str(prompt_file),
        "--project-root",
        str(project),
        "--helper",
        str(helper_path),
    ]
    try:
        result = run(command, env=child_env, check=False)
    except OSError as exc:
        latest = _load_receipt(receipt_path)
        _update_receipt(
            receipt_path,
            latest,
            state="retry_failed",
            exit_code=127,
            error=f"{type(exc).__name__}: {exc}",
        )
        print(
            f"[dcness-codex-permission] BLOCKED: Codex worker 재시도 시작 실패: {exc}",
            file=sys.stderr,
        )
        return 127
    latest = _load_receipt(receipt_path)
    if latest.get("state") == "retry_blocked":
        print(
            "[dcness-codex-permission] BLOCKED: 승인 후 동일 sandbox 거부가 반복되어 "
            "추가 권한 확대 없이 중단합니다.",
            file=sys.stderr,
        )
        return 1
    returncode = int(getattr(result, "returncode", 1))
    if returncode == 0:
        _update_receipt(receipt_path, latest, state="completed")
        return 0
    _update_receipt(receipt_path, latest, state="retry_failed", exit_code=returncode)
    return returncode


def _status(receipt_path: Path) -> int:
    try:
        receipt = _load_receipt(receipt_path)
    except ValueError as exc:
        print(f"[dcness-codex-permission] {exc}", file=sys.stderr)
        return 2
    print(f"receipt: {receipt_path}")
    print(f"state: {receipt.get('state', 'unknown')}")
    print("capabilities: " + ", ".join(receipt.get("capabilities", [])))
    roots = receipt.get("suggested_writable_roots", [])
    print("suggested writable roots: " + (os.pathsep.join(roots) if roots else "none"))
    for item in receipt.get("evidence", []):
        if isinstance(item, dict):
            print(f"evidence: {item.get('signature', '')}")
    print("sandbox: workspace-write (danger-full-access is unavailable)")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect and apply user-approved Codex sandbox recovery"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    detect = sub.add_parser("detect")
    detect.add_argument("--prose-file", type=Path, required=True)
    detect.add_argument("--raw-log", type=Path, required=True)
    detect.add_argument("--project-root", type=Path, required=True)
    detect.add_argument("--receipt", type=Path, required=True)
    detect.add_argument("--retry-receipt", type=Path)
    detect.add_argument("--sid")
    detect.add_argument("--run-id")

    status = sub.add_parser("status")
    status.add_argument("--receipt", type=Path, required=True)

    retry = sub.add_parser("retry")
    retry.add_argument("--receipt", type=Path, required=True)
    retry.add_argument("--decision", choices=("once", "project", "deny"), required=True)
    retry.add_argument("--prompt-file", type=Path, required=True)
    retry.add_argument("--project-root", type=Path, required=True)
    retry.add_argument("--helper", type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "detect":
        try:
            receipt = record_permission_required(
                prose_path=args.prose_file,
                raw_log_path=args.raw_log,
                project_root=args.project_root,
                receipt_path=args.receipt,
                retry_receipt_path=args.retry_receipt,
                sid=args.sid,
                rid=args.run_id,
            )
        except (OSError, ValueError) as exc:
            print(f"[dcness-codex-permission] detect 실패: {exc}", file=sys.stderr)
            return 2
        if receipt is None:
            return 4
        print(args.retry_receipt or args.receipt)
        return 0
    if args.command == "status":
        return _status(args.receipt)
    if args.command == "retry":
        script_dir = Path(__file__).resolve().parents[1] / "scripts"
        return retry_main(
            receipt_path=args.receipt,
            decision=args.decision,
            project_root=args.project_root,
            prompt_file=args.prompt_file,
            worker_path=script_dir / "dcness-codex-worker",
            helper_path=args.helper or script_dir / "dcness-helper",
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

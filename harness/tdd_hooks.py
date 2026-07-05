"""Project-local generated TDD hook contract and self-test support (#909)."""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess  # nosec B404
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional


CONFIG_REL = Path(".dcness/tdd-hooks.json")
CC_HOOK_REL = Path(".claude/hooks/dcness-tdd-guard.sh")
CODEX_HOOK_REL = Path(".codex/hooks/dcness-tdd-guard.sh")
CC_SETTINGS_REL = Path(".claude/settings.json")
CODEX_HOOKS_REL = Path(".codex/hooks.json")
CONFIG_VERSION = 1
HOOK_TIMEOUT_SEC = 10
EXCLUDED_SCAN_DIRS = {
    ".git",
    ".claude",
    ".codex",
    ".dcness",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
}
TEST_DIR_SEGMENTS = {
    "__tests__",
    "__test__",
    "__mocks__",
    "test",
    "tests",
    "spec",
    "specs",
    "e2e",
}


@dataclass(frozen=True)
class SelfTestCase:
    name: str
    path: Path
    expected: str


@dataclass(frozen=True)
class SelfTestFailure:
    name: str
    expected: str
    actual: str
    stderr: str


class SelfTestError(RuntimeError):
    def __init__(self, failures: list[SelfTestFailure]) -> None:
        self.failures = failures
        lines = ["TDD hook self-test failed:"]
        for failure in failures:
            lines.append(
                f"- {failure.name}: expected {failure.expected}, got {failure.actual}"
            )
            if failure.stderr:
                lines.append(f"  stderr: {failure.stderr.strip()}")
        super().__init__("\n".join(lines))


class JsonConfigError(RuntimeError):
    """Raised when an existing user-owned JSON file would be overwritten."""


def _read_json(path: Path, *, strict: bool = False) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        if strict:
            raise JsonConfigError(
                f"{path}: invalid JSON; refusing to overwrite existing file"
            ) from exc
        return {}
    except OSError as exc:
        if strict:
            raise JsonConfigError(f"{path}: cannot read JSON file: {exc}") from exc
        return {}
    if strict and not isinstance(data, dict):
        raise JsonConfigError(f"{path}: JSON root must be an object")
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _iter_project_files(root: Path, suffixes: tuple[str, ...]) -> Iterable[Path]:
    for path in root.rglob("*"):
        rel_parts = path.relative_to(root).parts
        if any(part in EXCLUDED_SCAN_DIRS for part in rel_parts):
            continue
        if path.is_file() and path.suffix in suffixes:
            yield path


def _existing_source_roots(root: Path, candidates: tuple[str, ...]) -> list[str]:
    found = [candidate for candidate in candidates if (root / candidate).is_dir()]
    return found or ["."]


def _has_files(root: Path, suffixes: tuple[str, ...]) -> bool:
    return next(iter(_iter_project_files(root, suffixes)), None) is not None


def detect_platform(project_root: Path) -> Optional[str]:
    """Return a broad platform bucket or None for empty/unknown projects."""
    root = project_root.resolve()
    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
        return "python"
    if _has_files(root, (".py",)):
        return "python"
    if (root / "package.json").exists() or _has_files(root, (".ts", ".tsx", ".js", ".jsx")):
        return "web"
    if (root / "go.mod").exists() or _has_files(root, (".go",)):
        return "go"
    if (
        (root / "settings.gradle").exists()
        or (root / "settings.gradle.kts").exists()
        or (root / "build.gradle").exists()
        or (root / "build.gradle.kts").exists()
        or _has_files(root, (".kt", ".java"))
    ):
        return "android"
    if (root / "Package.swift").exists() or _has_files(root, (".swift",)):
        return "ios"
    return None


def build_contract_config(project_root: Path, platform: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Build the project-local TDD contract config used by generated hooks."""
    root = project_root.resolve()
    detected = platform or detect_platform(root)
    if detected is None:
        return None

    if detected == "python":
        source_roots = _existing_source_roots(root, ("src", "app", "apps", "packages"))
        impl_exts = [".py"]
    elif detected == "web":
        source_roots = _existing_source_roots(root, ("src", "app", "apps", "packages"))
        impl_exts = [".ts", ".tsx", ".js", ".jsx"]
    elif detected == "go":
        source_roots = _existing_source_roots(root, (".", "cmd", "pkg", "internal"))
        impl_exts = [".go"]
    elif detected == "android":
        source_roots = _existing_source_roots(
            root,
            ("app/src/main", "src/main", "app", "src"),
        )
        impl_exts = [".kt", ".java"]
    elif detected == "ios":
        source_roots = _existing_source_roots(root, ("Sources", "App", "src"))
        impl_exts = [".swift"]
    else:
        return None

    return {
        "version": CONFIG_VERSION,
        "platform": detected,
        "source_roots": source_roots,
        "impl_exts": impl_exts,
        "registered": {"cc": False, "codex": False},
    }


def _rel_path(path: Path, project_root: Path) -> Optional[Path]:
    candidate = path
    if not candidate.is_absolute():
        candidate = project_root / candidate
    try:
        return candidate.resolve().relative_to(project_root.resolve())
    except (OSError, ValueError):
        return None


def _is_under_source_root(rel: Path, config: dict[str, Any]) -> bool:
    source_roots = config.get("source_roots")
    if not isinstance(source_roots, list):
        return True
    rel_text = rel.as_posix()
    for source_root in source_roots:
        if not isinstance(source_root, str):
            continue
        normalized = source_root.strip("/")
        if normalized in ("", "."):
            return True
        if rel_text == normalized or rel_text.startswith(f"{normalized}/"):
            return True
    return False


def _is_test_file(rel: Path, platform: str) -> bool:
    parts = set(rel.parts[:-1])
    if parts & TEST_DIR_SEGMENTS:
        return True
    name = rel.name
    if ".test." in name or ".spec." in name:
        return True
    if platform == "python":
        return name.startswith("test_") or name.endswith("_test.py")
    if platform == "go":
        return name.endswith("_test.go")
    if platform == "android":
        return name.endswith("Test.kt") or name.endswith("Test.java")
    if platform == "ios":
        return name.endswith("Test.swift") or name.endswith("Tests.swift") or "Tests" in parts
    return False


def _strip_known_suffix(path: Path) -> str:
    return path.name[: -len(path.suffix)] if path.suffix else path.name


def matching_test_candidates(source_rel: Path, config: dict[str, Any]) -> list[Path]:
    platform = str(config.get("platform") or "")
    ext = source_rel.suffix
    base = _strip_known_suffix(source_rel)
    parent = source_rel.parent
    candidates: list[Path] = []

    if platform == "python":
        candidates.extend(
            [
                parent / f"test_{base}.py",
                parent / f"{base}_test.py",
                parent / "tests" / f"test_{base}.py",
                Path("tests") / f"test_{base}.py",
                Path("tests") / f"{base}_test.py",
            ]
        )
    elif platform == "web":
        for test_ext in (".ts", ".tsx", ".js", ".jsx"):
            candidates.extend(
                [
                    parent / f"{base}.test{test_ext}",
                    parent / f"{base}.spec{test_ext}",
                    parent / "__tests__" / f"{base}.test{test_ext}",
                    Path("src") / "__tests__" / f"{base}.test{test_ext}",
                ]
            )
    elif platform == "go":
        candidates.append(parent / f"{base}_test.go")
    elif platform == "android":
        mirrored = _android_test_path(source_rel, base, ext)
        candidates.append(mirrored)
        candidates.append(parent / f"{base}Test{ext}")
    elif platform == "ios":
        candidates.append(Path("Tests") / f"{base}Tests.swift")
        candidates.append(parent / f"{base}Tests.swift")
    else:
        candidates.append(parent / f"{base}.test{ext}")

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.as_posix()
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def _android_test_path(source_rel: Path, base: str, ext: str) -> Path:
    parts = list(source_rel.parts)
    try:
        main_index = parts.index("main")
    except ValueError:
        return Path("app/src/test/java") / f"{base}Test{ext}"
    test_parts = parts[:main_index] + ["test"] + parts[main_index + 1 :]
    test_parts[-1] = f"{base}Test{ext}"
    return Path(*test_parts)


def should_enforce(path: Path, project_root: Path, config: dict[str, Any]) -> bool:
    rel = _rel_path(path, project_root)
    if rel is None:
        return False
    platform = str(config.get("platform") or "")
    impl_exts = config.get("impl_exts")
    if not isinstance(impl_exts, list) or rel.suffix not in impl_exts:
        return False
    if _is_test_file(rel, platform):
        return False
    return _is_under_source_root(rel, config)


def has_matching_test(path: Path, project_root: Path, config: dict[str, Any]) -> bool:
    rel = _rel_path(path, project_root)
    if rel is None:
        return True
    for candidate in matching_test_candidates(rel, config):
        if (project_root / candidate).is_file():
            return True
    return False


def extract_payload_paths(payload: dict[str, Any]) -> list[Path]:
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return []
    if tool_name == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str):
            return []
        try:
            from harness.agent_boundary import extract_bash_paths

            return [Path(path) for path in extract_bash_paths(command)]
        except Exception:
            return []
    if tool_name == "apply_patch":
        return _extract_apply_patch_paths(tool_input)
    for key in ("file_path", "path", "filename", "notebook_path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return [Path(value)]
    return []


def _extract_apply_patch_paths(tool_input: dict[str, Any]) -> list[Path]:
    text_parts: list[str] = []
    for key in ("patch", "input", "command"):
        value = tool_input.get(key)
        if isinstance(value, str):
            text_parts.append(value)
    text = "\n".join(text_parts)
    paths: list[Path] = []
    for line in text.splitlines():
        for prefix in ("*** Add File: ", "*** Update File: "):
            if line.startswith(prefix):
                paths.append(Path(line[len(prefix) :].strip()))
        if line.startswith("+++ b/"):
            paths.append(Path(line[len("+++ b/") :].strip()))
    return paths


def evaluate_payload(
    payload: dict[str, Any],
    project_root: Path,
    config: dict[str, Any],
) -> tuple[str, str]:
    """Return (allow|deny, reason). Missing config/path is intentionally allow."""
    paths = extract_payload_paths(payload)
    for path in paths:
        if not should_enforce(path, project_root, config):
            continue
        if has_matching_test(path, project_root, config):
            continue
        rel = _rel_path(path, project_root) or path
        candidates = matching_test_candidates(rel, config)
        suggested = "\n".join(f"  - {candidate.as_posix()}" for candidate in candidates[:5])
        return (
            "deny",
            "TDD GUARD[generated]: "
            f"'{rel.as_posix()}' 에 대한 매칭 테스트가 없습니다.\n"
            "구현 파일을 쓰기 전에 테스트를 먼저 작성하세요.\n"
            f"권장 위치:\n{suggested}",
        )
    return "allow", ""


def _allow_json() -> str:
    return (
        '{"suppressOutput": true, "hookSpecificOutput": '
        '{"hookEventName": "PreToolUse", "permissionDecision": "allow"}}'
    )


def run_generated_hook(
    *,
    project_root: Path,
    config_path: Path,
    stdin_text: str,
) -> int:
    config = _read_json(config_path)
    if not config:
        print(_allow_json())
        return 0
    try:
        payload = json.loads(stdin_text or "{}")
    except json.JSONDecodeError:
        print(_allow_json())
        return 0
    if not isinstance(payload, dict):
        print(_allow_json())
        return 0
    decision, reason = evaluate_payload(payload, project_root.resolve(), config)
    if decision == "deny":
        print(reason, file=sys.stderr)
        return 2
    print(_allow_json())
    return 0


def _primary_source_root(config: dict[str, Any]) -> str:
    roots = config.get("source_roots")
    if isinstance(roots, list):
        for root in roots:
            if isinstance(root, str) and root not in ("", "."):
                return root
    platform = str(config.get("platform") or "")
    if platform == "ios":
        return "Sources"
    return "src"


def _first_impl_ext(config: dict[str, Any]) -> str:
    exts = config.get("impl_exts")
    if isinstance(exts, list) and exts and isinstance(exts[0], str):
        return exts[0]
    return ".txt"


def _self_test_paths(config: dict[str, Any], token: str) -> tuple[Path, Path, Path]:
    source_root = Path(_primary_source_root(config))
    ext = _first_impl_ext(config)
    no_test = source_root / f"dcness_tdd_contract_no_test_{token}{ext}"
    with_test = source_root / f"dcness_tdd_contract_with_test_{token}{ext}"
    test_file = matching_test_candidates(with_test, config)[0]
    test_self = test_file.parent / f"test_dcness_tdd_contract_self_{token}.py"
    platform = str(config.get("platform") or "")
    if platform == "web":
        test_self = test_file.parent / f"dcness_tdd_contract_self_{token}.test.ts"
    elif platform == "go":
        test_self = test_file.parent / f"dcness_tdd_contract_self_{token}_test.go"
    elif platform == "android":
        test_self = test_file.parent / f"DcnessTddContractSelf{token}Test{ext}"
    elif platform == "ios":
        test_self = test_file.parent / f"DcnessTddContractSelf{token}Tests.swift"
    return no_test, with_test, test_self


def _fixture_content(path: Path) -> str:
    if path.suffix == ".py":
        return "def dcness_contract_subject():\n    return 1\n"
    if path.suffix in {".ts", ".tsx", ".js", ".jsx"}:
        return "export function dcnessContractSubject() { return 1; }\n"
    if path.suffix == ".go":
        return "package dcness\n\nfunc DcnessContractSubject() int { return 1 }\n"
    if path.suffix in {".kt", ".java", ".swift"}:
        return "// dcness contract subject\n"
    return "dcness contract subject\n"


def _write_fixture_file(project_root: Path, rel: Path) -> Path:
    path = project_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_fixture_content(rel), encoding="utf-8")
    return path


def _cleanup_created(paths: list[Path], project_root: Path) -> None:
    dirs: set[Path] = set()
    for path in paths:
        if path.exists():
            path.unlink()
        parent = path.parent
        while parent != project_root and project_root in parent.parents:
            dirs.add(parent)
            parent = parent.parent
    for directory in sorted(dirs, key=lambda item: len(item.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass


def _run_hook_command(
    hook_command: str,
    project_root: Path,
    payload_path: Path,
    *,
    config_path: Path,
    plugin_root: Optional[Path],
) -> tuple[str, str]:
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(payload_path)}}
    env = os.environ.copy()
    env["DCNESS_TDD_CONFIG"] = str(config_path)
    env["DCNESS_TDD_PROJECT_ROOT"] = str(project_root)
    if plugin_root is not None:
        env["DCNESS_TDD_PLUGIN_ROOT"] = str(plugin_root)
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
        env["PYTHONPATH"] = f"{plugin_root}{os.pathsep}{env.get('PYTHONPATH', '')}"
    try:
        proc = subprocess.run(  # nosec B603
            shlex.split(hook_command),
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=HOOK_TIMEOUT_SEC,
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return "error", str(exc)
    if proc.returncode == 0:
        return "allow", proc.stderr
    if proc.returncode == 2:
        return "deny", proc.stderr
    return "error", proc.stderr or proc.stdout


def run_self_test(
    *,
    project_root: Path,
    config: dict[str, Any],
    hook_command: str,
    config_path: Path,
    plugin_root: Optional[Path] = None,
) -> None:
    token = uuid.uuid4().hex[:8]
    no_test_rel, with_test_rel, test_self_rel = _self_test_paths(config, token)
    created = [
        _write_fixture_file(project_root, no_test_rel),
        _write_fixture_file(project_root, with_test_rel),
        _write_fixture_file(project_root, matching_test_candidates(with_test_rel, config)[0]),
        _write_fixture_file(project_root, test_self_rel),
    ]
    cases = [
        SelfTestCase("without_test", created[0], "deny"),
        SelfTestCase("with_test", created[1], "allow"),
        SelfTestCase("test_file_self", created[3], "allow"),
    ]
    failures: list[SelfTestFailure] = []
    try:
        for case in cases:
            actual, stderr = _run_hook_command(
                hook_command,
                project_root,
                case.path,
                config_path=config_path,
                plugin_root=plugin_root,
            )
            if actual != case.expected:
                failures.append(SelfTestFailure(case.name, case.expected, actual, stderr))
    finally:
        _cleanup_created(created, project_root)
    if failures:
        raise SelfTestError(failures)


def _generated_hook_text(target: str) -> str:
    return f"""#!/usr/bin/env bash
# Generated by dcNess for this project. Do not edit by hand.
set -u

allow() {{
  cat >/dev/null || true
  echo '{{"suppressOutput": true, "hookSpecificOutput": {{"hookEventName": "PreToolUse", "permissionDecision": "allow"}}}}'
  exit 0
}}

resolve_plugin_root() {{
  if [ -n "${{DCNESS_TDD_PLUGIN_ROOT:-}}" ] && [ -f "${{DCNESS_TDD_PLUGIN_ROOT}}/scripts/dcness-tdd-hooks" ]; then
    echo "${{DCNESS_TDD_PLUGIN_ROOT}}"; return 0
  fi
  if [ -n "${{CLAUDE_PLUGIN_ROOT:-}}" ] && [ -f "${{CLAUDE_PLUGIN_ROOT}}/scripts/dcness-tdd-hooks" ]; then
    echo "${{CLAUDE_PLUGIN_ROOT}}"; return 0
  fi
  cache_dir="${{HOME}}/.claude/plugins/cache/dcness/dcness"
  if [ -d "$cache_dir" ]; then
    latest=$(ls -1 "$cache_dir" 2>/dev/null | sort -V | tail -1)
    if [ -n "$latest" ] && [ -f "$cache_dir/$latest/scripts/dcness-tdd-hooks" ]; then
      echo "$cache_dir/$latest"; return 0
    fi
  fi
  return 1
}}

PLUGIN_ROOT="$(resolve_plugin_root 2>/dev/null || true)"
[ -n "$PLUGIN_ROOT" ] || allow

PROJECT_ROOT="${{DCNESS_TDD_PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}}"
CONFIG_PATH="${{DCNESS_TDD_CONFIG:-$PROJECT_ROOT/.dcness/tdd-hooks.json}}"

exec bash "$PLUGIN_ROOT/scripts/dcness-tdd-hooks" run \\
  --project-root "$PROJECT_ROOT" \\
  --config "$CONFIG_PATH" \\
  --target "{target}"
"""


def _install_hook_script(project_root: Path, target: str, source: Path) -> Path:
    rel = CC_HOOK_REL if target == "cc" else CODEX_HOOK_REL
    final_path = project_root / rel
    final_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, final_path)
    final_path.chmod(0o755)
    return final_path


def _strip_existing_dcness_tdd_hooks(entries: list[Any]) -> list[Any]:
    kept: list[Any] = []
    for entry in entries:
        if not isinstance(entry, dict):
            kept.append(entry)
            continue
        hooks = entry.get("hooks")
        if not isinstance(hooks, list):
            kept.append(entry)
            continue
        new_hooks = []
        for hook in hooks:
            if not isinstance(hook, dict):
                new_hooks.append(hook)
                continue
            command = hook.get("command")
            if isinstance(command, str) and "dcness-tdd-guard.sh" in command:
                continue
            new_hooks.append(hook)
        if new_hooks:
            cloned = dict(entry)
            cloned["hooks"] = new_hooks
            kept.append(cloned)
    return kept


def _register_hook_json(path: Path, matcher: str, command: str) -> None:
    data = _read_json(path, strict=True)
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks
    pre = hooks.setdefault("PreToolUse", [])
    if not isinstance(pre, list):
        pre = []
        hooks["PreToolUse"] = pre
    pre = _strip_existing_dcness_tdd_hooks(pre)
    pre.append(
        {
            "matcher": matcher,
            "hooks": [{"type": "command", "command": command, "timeout": 10}],
        }
    )
    hooks["PreToolUse"] = pre
    _write_json(path, data)


def _register_cc(project_root: Path) -> None:
    command = (
        'bash "$(git rev-parse --show-toplevel 2>/dev/null || pwd)'
        '/.claude/hooks/dcness-tdd-guard.sh"'
    )
    _register_hook_json(
        project_root / CC_SETTINGS_REL,
        "Edit|Write|NotebookEdit|Bash",
        command,
    )


def _register_codex(project_root: Path) -> None:
    command = (
        'bash "$(git rev-parse --show-toplevel 2>/dev/null || pwd)'
        '/.codex/hooks/dcness-tdd-guard.sh"'
    )
    _register_hook_json(
        project_root / CODEX_HOOKS_REL,
        "Edit|Write|apply_patch",
        command,
    )


def _preflight_registration_json(project_root: Path, targets: Iterable[str]) -> None:
    _read_json(project_root / CONFIG_REL, strict=True)
    target_set = set(targets)
    if "cc" in target_set:
        _read_json(project_root / CC_SETTINGS_REL, strict=True)
    if "codex" in target_set:
        _read_json(project_root / CODEX_HOOKS_REL, strict=True)


def _run_git(project_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603, B607
        ["git", "-C", str(project_root), *args],
        capture_output=True,
        text=True,
        timeout=5,
    )


def _is_git_work_tree(project_root: Path) -> bool:
    try:
        proc = _run_git(project_root, ["rev-parse", "--is-inside-work-tree"])
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def _is_committed_clean(project_root: Path, rel: Path) -> bool:
    rel_text = rel.as_posix()
    try:
        status = _run_git(project_root, ["status", "--porcelain", "--", rel_text])
        tracked = _run_git(project_root, ["ls-files", "--error-unmatch", "--", rel_text])
    except (OSError, subprocess.SubprocessError):
        return False
    return status.returncode == 0 and not status.stdout.strip() and tracked.returncode == 0


def generated_files_git_state(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    existing = _existing_generated_file_rels(root)
    if not existing:
        return {
            "generated_files": [],
            "generated_files_committed": True,
            "uncommitted_generated_files": [],
        }
    if not _is_git_work_tree(root):
        return {
            "generated_files": existing,
            "generated_files_committed": False,
            "uncommitted_generated_files": existing,
        }
    uncommitted = [
        rel for rel in existing if not _is_committed_clean(root, Path(rel))
    ]
    return {
        "generated_files": existing,
        "generated_files_committed": not uncommitted,
        "uncommitted_generated_files": uncommitted,
    }


def _existing_generated_file_rels(root: Path) -> list[str]:
    existing: list[str] = []
    if (root / CONFIG_REL).exists():
        existing.append(CONFIG_REL.as_posix())
    if _hook_json_references(root / CC_SETTINGS_REL, "dcness-tdd-guard.sh"):
        existing.append(CC_SETTINGS_REL.as_posix())
    if (root / CC_HOOK_REL).exists():
        existing.append(CC_HOOK_REL.as_posix())
    if _hook_json_references(root / CODEX_HOOKS_REL, "dcness-tdd-guard.sh"):
        existing.append(CODEX_HOOKS_REL.as_posix())
    if (root / CODEX_HOOK_REL).exists():
        existing.append(CODEX_HOOK_REL.as_posix())
    return existing


def ensure_generated_hooks(
    *,
    project_root: Path,
    targets: tuple[str, ...],
    plugin_root: Path,
) -> list[str]:
    root = project_root.resolve()
    config = build_contract_config(root)
    if config is None:
        return ["skip: empty_or_unknown_project"]

    normalized = list(dict.fromkeys(targets))
    if "codex" in normalized and "cc" not in normalized:
        normalized.insert(0, "cc")
    if "cc" in normalized and "codex" in normalized:
        normalized = ["cc"] + [target for target in normalized if target != "cc"]

    config_path = root / CONFIG_REL
    _preflight_registration_json(root, normalized)
    current = _read_json(config_path, strict=True)
    registered_data = current.get("registered")
    registered: dict[str, Any] = registered_data if isinstance(registered_data, dict) else {}
    registered_config: dict[str, bool] = {
        "cc": bool(registered.get("cc")),
        "codex": bool(registered.get("codex")),
    }
    config["registered"] = registered_config

    tmp_dir = root / ".dcness" / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    messages: list[str] = []
    try:
        for target in normalized:
            if target not in {"cc", "codex"}:
                raise ValueError(f"unknown target: {target}")
            if target == "codex" and not registered_config.get("cc"):
                raise SelfTestError(
                    [SelfTestFailure("cc_before_codex", "cc registered", "missing", "")]
                )
            candidate = tmp_dir / f"dcness-tdd-guard-{target}.sh"
            candidate.write_text(_generated_hook_text(target), encoding="utf-8")
            candidate.chmod(0o755)
            candidate_config = tmp_dir / f"tdd-hooks-{target}.json"
            _write_json(candidate_config, config)
            run_self_test(
                project_root=root,
                config=config,
                hook_command=f"bash {shlex.quote(str(candidate))}",
                config_path=candidate_config,
                plugin_root=plugin_root,
            )
            _install_hook_script(root, target, candidate)
            if target == "cc":
                _register_cc(root)
            else:
                _register_codex(root)
            registered_config[target] = True
            config["registered"] = registered_config
            _write_json(config_path, config)
            if target == "codex":
                messages.append("codex: registered (Codex trust approval may still be required)")
            else:
                messages.append(f"{target}: registered")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    git_state = generated_files_git_state(root)
    uncommitted = git_state["uncommitted_generated_files"]
    if uncommitted:
        joined = ", ".join(uncommitted)
        messages.append(
            "commit-required: generated TDD hook files must be committed for "
            f"worktree/headless reuse: {joined}"
        )
    return messages


def inspect_installation(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    platform = detect_platform(root)
    config = _read_json(root / CONFIG_REL)
    registered_data = config.get("registered")
    registered: dict[str, Any] = registered_data if isinstance(registered_data, dict) else {}
    cc_hook = (root / CC_HOOK_REL).is_file()
    codex_hook = (root / CODEX_HOOK_REL).is_file()
    cc_configured = _hook_json_references(root / CC_SETTINGS_REL, "dcness-tdd-guard.sh")
    codex_configured = _hook_json_references(root / CODEX_HOOKS_REL, "dcness-tdd-guard.sh")
    report = {
        "platform": platform,
        "config": bool(config),
        "cc_hook": cc_hook,
        "codex_hook": codex_hook,
        "cc_registered": bool(registered.get("cc")) and cc_hook and cc_configured,
        "codex_registered": bool(registered.get("codex")) and codex_hook and codex_configured,
    }
    report.update(generated_files_git_state(root))
    return report


def _hook_json_references(path: Path, needle: str) -> bool:
    data = _read_json(path)
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return False
    pre = hooks.get("PreToolUse")
    if not isinstance(pre, list):
        return False
    return any(needle in json.dumps(entry) for entry in pre)


def _cmd_run(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve()
    config_path = Path(args.config).resolve()
    stdin_text = sys.stdin.read()
    return run_generated_hook(
        project_root=project_root,
        config_path=config_path,
        stdin_text=stdin_text,
    )


def _cmd_self_test(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve()
    config: Optional[dict[str, Any]]
    if args.config:
        config_path = Path(args.config).resolve()
        try:
            config = _read_json(config_path, strict=True)
        except JsonConfigError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    else:
        config = build_contract_config(project_root, args.platform)
        config_path = project_root / ".dcness" / ".tmp-self-test-config.json"
        if config is not None:
            _write_json(config_path, config)
    if config is None or not config:
        print("skip: empty_or_unknown_project")
        return 0
    try:
        run_self_test(
            project_root=project_root,
            config=config,
            hook_command=args.hook_command,
            config_path=config_path,
            plugin_root=Path(args.plugin_root).resolve() if args.plugin_root else None,
        )
    except SelfTestError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        if not args.config:
            config_path.unlink(missing_ok=True)
    print("self-test: PASS")
    return 0


def _cmd_ensure(args: argparse.Namespace) -> int:
    try:
        messages = ensure_generated_hooks(
            project_root=Path(args.project_root),
            targets=tuple(part for part in args.targets.split(",") if part),
            plugin_root=Path(args.plugin_root).resolve(),
        )
    except (JsonConfigError, SelfTestError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for message in messages:
        print(message)
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    report = inspect_installation(Path(args.project_root))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    platform = report.get("platform") or "empty_or_unknown_project"
    print(
        "generated TDD hooks: "
        f"platform={platform}, "
        f"cc={report['cc_registered']}, "
        f"codex={report['codex_registered']}, "
        f"generated_files_committed={report['generated_files_committed']}"
    )
    uncommitted = report.get("uncommitted_generated_files")
    if isinstance(uncommitted, list) and uncommitted:
        joined = ", ".join(str(item) for item in uncommitted)
        print(f"commit-required: {joined}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dcness-tdd-hooks",
        description="dcNess generated project-local TDD hook contract helper",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="internal generated hook entrypoint")
    p_run.add_argument("--project-root", required=True)
    p_run.add_argument("--config", required=True)
    p_run.add_argument("--target", choices=("cc", "codex"), default="cc")
    p_run.set_defaults(func=_cmd_run)

    p_self = sub.add_parser("self-test", help="run TDD contract self-test for a hook")
    p_self.add_argument("--project-root", required=True)
    p_self.add_argument("--hook-command", required=True)
    p_self.add_argument("--platform", default=None)
    p_self.add_argument("--config", default="")
    p_self.add_argument("--plugin-root", default="")
    p_self.set_defaults(func=_cmd_self_test)

    p_ensure = sub.add_parser("ensure", help="generate and register CC/Codex hooks")
    p_ensure.add_argument("--project-root", required=True)
    p_ensure.add_argument("--targets", default="cc,codex")
    p_ensure.add_argument("--plugin-root", required=True)
    p_ensure.set_defaults(func=_cmd_ensure)

    p_status = sub.add_parser("status", help="inspect generated hook installation")
    p_status.add_argument("--project-root", default=".")
    p_status.add_argument("--json", action="store_true")
    p_status.set_defaults(func=_cmd_status)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

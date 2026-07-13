#!/usr/bin/env python3
"""Build, measure, compare, and smoke-test the dcNess release artifact."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
# All subprocess calls below use fixed argv and never enable shell execution.
import subprocess  # nosec B404
import sys
import tarfile
import tempfile
import time
from typing import Any


DEFAULT_CONTRACT = Path(__file__).with_name("release_artifact.json")


class ArtifactError(RuntimeError):
    """Raised when the release artifact contract is invalid or violated."""


@dataclass(frozen=True)
class Contract:
    exclude_paths: tuple[str, ...]
    allowed_cache_metadata: tuple[str, ...]
    required_runtime_paths: tuple[str, ...]


def _safe_relative(value: str, *, field: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise ArtifactError(f"{field} must contain safe repo-relative paths: {value!r}")
    return path.as_posix().rstrip("/")


def load_contract(path: Path) -> Contract:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactError(f"cannot read artifact contract {path}: {exc}") from exc
    if payload.get("schema_version") != 1:
        raise ArtifactError("artifact contract schema_version must be 1")

    def paths(field: str) -> tuple[str, ...]:
        values = payload.get(field)
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise ArtifactError(f"artifact contract {field} must be a string array")
        normalized = tuple(_safe_relative(item, field=field) for item in values)
        if len(normalized) != len(set(normalized)):
            raise ArtifactError(f"artifact contract {field} contains duplicates")
        return normalized

    return Contract(
        exclude_paths=paths("exclude_paths"),
        allowed_cache_metadata=paths("allowed_cache_metadata"),
        required_runtime_paths=paths("required_runtime_paths"),
    )


def _is_under(relative: str, roots: tuple[str, ...]) -> bool:
    return any(relative == root or relative.startswith(f"{root}/") for root in roots)


def _archive(repo_root: Path, ref: str) -> bytes:
    result = subprocess.run(  # nosec B603
        [_executable("git"), "-C", str(repo_root), "archive", "--format=tar", ref],
        check=False,
        capture_output=True,
        timeout=60,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ArtifactError(f"git archive failed for {ref}: {detail}")
    return result.stdout


def _extract_archive(data: bytes, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        for member in archive.getmembers():
            member_path = PurePosixPath(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ArtifactError(f"unsafe git archive member: {member.name}")
            if member.issym() or member.islnk():
                raise ArtifactError(f"release artifact does not allow links: {member.name}")
            target = output.joinpath(*member_path.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ArtifactError(f"unsupported git archive member: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise ArtifactError(f"cannot read git archive member: {member.name}")
            with source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            target.chmod(member.mode & 0o777)


def _remove_excluded(output: Path, contract: Contract) -> None:
    for relative in contract.exclude_paths:
        target = output / relative
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists() or target.is_symlink():
            target.unlink()


def build(repo_root: Path, ref: str, output: Path, contract: Contract) -> None:
    if output.exists():
        raise ArtifactError(f"output already exists: {output}")
    _extract_archive(_archive(repo_root, ref), output)
    _remove_excluded(output, contract)


def _content_hashes(root: Path, contract: Contract) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if not _is_under(relative, contract.allowed_cache_metadata):
            hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def snapshot(root: Path, contract: Contract) -> dict[str, Any]:
    if not root.is_dir():
        raise ArtifactError(f"snapshot root is not a directory: {root}")
    files: list[str] = []
    hashes: dict[str, str] = {}
    byte_size = 0
    text_loc = 0
    composition: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "bytes": 0})
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if _is_under(relative, contract.allowed_cache_metadata):
            continue
        data = path.read_bytes()
        size = len(data)
        files.append(relative)
        hashes[relative] = hashlib.sha256(data).hexdigest()
        byte_size += size
        try:
            if b"\0" not in data:
                data.decode("utf-8")
                text_loc += data.count(b"\n")
        except UnicodeDecodeError:
            pass
        top = relative.split("/", 1)[0]
        composition[top]["files"] += 1
        composition[top]["bytes"] += size
    manifest_json = json.dumps(hashes, sort_keys=True, separators=(",", ":"))
    return {
        "root": str(root.resolve()),
        "file_count": len(files),
        "byte_size": byte_size,
        "text_loc": text_loc,
        "manifest_sha256": hashlib.sha256(manifest_json.encode()).hexdigest(),
        "top_level": dict(sorted(composition.items())),
        "files": files,
    }


def compare(expected: Path, actual: Path, contract: Contract) -> tuple[bool, list[str]]:
    if not expected.is_dir() or not actual.is_dir():
        raise ArtifactError("compare roots must both be directories")
    expected_hashes = _content_hashes(expected, contract)
    actual_hashes = _content_hashes(actual, contract)
    missing = sorted(set(expected_hashes) - set(actual_hashes))
    extra = sorted(set(actual_hashes) - set(expected_hashes))
    changed = sorted(
        path
        for path in set(expected_hashes) & set(actual_hashes)
        if expected_hashes[path] != actual_hashes[path]
    )
    details = [*(f"missing: {path}" for path in missing), *(f"extra: {path}" for path in extra)]
    details.extend(f"changed: {path}" for path in changed)
    return not details, details


def _executable(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        raise ArtifactError(f"required executable not found: {name}")
    return resolved


def _run_checked(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(  # nosec B603
        command,
        cwd=cwd,
        env=env,
        check=False,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ArtifactError(f"command failed ({' '.join(command)}): {detail}")
    return result.stdout


def _verify_agent_surface(bundle: Path, public_surface_checker: Path) -> None:
    agents_root = bundle / "agents"
    recursive = sorted(path for path in agents_root.rglob("*.md") if path.is_file())
    top_level = sorted(path for path in agents_root.glob("*.md") if path.is_file())
    nested = [path.relative_to(bundle).as_posix() for path in recursive if path not in top_level]
    if nested:
        raise ArtifactError(f"nested agent entrypoints are not allowed: {', '.join(nested)}")
    for entrypoint in top_level:
        name = entrypoint.stem
        instruction = bundle / "docs" / "plugin" / "agents" / name / f"{name}-agent.md"
        if not instruction.is_file():
            raise ArtifactError(f"agent instruction missing: {instruction.relative_to(bundle)}")
    _run_checked([_executable("node"), str(public_surface_checker)], cwd=bundle)


def _verify_required_paths(bundle: Path, contract: Contract) -> None:
    missing = [relative for relative in contract.required_runtime_paths if not (bundle / relative).exists()]
    if missing:
        raise ArtifactError(f"required runtime paths missing: {', '.join(missing)}")
    leaked = [relative for relative in contract.exclude_paths if (bundle / relative).exists()]
    if leaked:
        raise ArtifactError(f"self-only paths leaked into artifact: {', '.join(leaked)}")


def _deploy_init_core(bundle: Path, project: Path, home: Path, env: dict[str, str]) -> int:
    deployed = 0
    hooks_dir = project / ".git" / "hooks"
    for name in ("pre-commit", "commit-msg", "post-checkout", "pre-push"):
        source = bundle / "scripts" / "hooks" / name
        target = hooks_dir / name
        shutil.copy2(source, target)
        target.chmod(0o755)
        if target.read_bytes() != source.read_bytes():
            raise ArtifactError(f"/init-dcness hook deploy mismatch: {name}")
        deployed += 1

    codex_home = home / ".codex"
    for name in ("dcness-impl-validator", "dcness-architecture-validator"):
        source = bundle / "codex" / "skills" / name / "SKILL.md"
        target = codex_home / "skills" / name / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if target.read_bytes() != source.read_bytes():
            raise ArtifactError(f"/init-dcness Codex skill deploy mismatch: {name}")
        deployed += 1

    helper = str(bundle / "scripts" / "dcness-helper")
    context_docs = str(bundle / "scripts" / "dcness-context-docs")
    _run_checked([helper, "enable"], cwd=project, env=env)
    _run_checked([helper, "is-active"], cwd=project, env=env)
    _run_checked([context_docs, "--ensure", "--repo", str(project)], cwd=project, env=env)
    if not (project / "CLAUDE.md").is_file():
        raise ArtifactError("/init-dcness context seed was not created")
    return deployed + 1


def _verify_agent_reads(bundle: Path, project: Path, env: dict[str, str]) -> int:
    code = """
import sys
from pathlib import Path
from harness.agent_boundary import check_read_allowed

bundle = Path(sys.argv[1])
project = Path(sys.argv[2])
count = 0
for entrypoint in sorted((bundle / 'agents').glob('*.md')):
    name = entrypoint.stem
    instruction = bundle / 'docs' / 'plugin' / 'agents' / name / f'{name}-agent.md'
    reason = check_read_allowed(name, str(instruction), cwd=project, plugin_root=str(bundle))
    if reason:
        raise SystemExit(f'{name}: {reason}')
    if not instruction.read_text(encoding='utf-8').strip():
        raise SystemExit(f'{name}: empty instruction')
    count += 1
print(count)
"""
    output = _run_checked(
        [sys.executable, "-c", code, str(bundle), str(project)], cwd=project, env=env
    )
    return int(output.strip())


def _verify_external_runtime(bundle: Path, temp_root: Path) -> dict[str, int]:
    project = temp_root / "external-project"
    home = temp_root / "home"
    config = temp_root / "config"
    project.mkdir()
    home.mkdir()
    config.mkdir()
    _run_checked([_executable("git"), "init", "-q", str(project)], cwd=temp_root)
    cache_dir = home / ".claude" / "plugins" / "data" / "dcness-dcness"
    cache_dir.mkdir(parents=True)
    version = json.loads(
        (bundle / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )["version"]
    (cache_dir / "last-update-check.txt").write_text(
        f"{int(time.time())} {version}\n", encoding="utf-8"
    )
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "CLAUDE_CONFIG_DIR": str(config),
            "CLAUDE_PLUGIN_ROOT": str(bundle),
            "DCNESS_WHITELIST_PATH": str(temp_root / "whitelist.json"),
            "PYTHONPATH": str(bundle),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    deployed_count = _deploy_init_core(bundle, project, home, env)
    agent_read_count = _verify_agent_reads(bundle, project, env)
    payload = json.dumps({"session_id": "release-artifact-smoke", "cwd": str(project)})
    result = subprocess.run(  # nosec B603
        [_executable("bash"), str(bundle / "hooks" / "session-start.sh")],
        cwd=project,
        env=env,
        input=payload,
        check=False,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise ArtifactError(f"SessionStart failed: {result.stderr.strip()}")
    try:
        hook_output = json.loads(result.stdout)
        context = hook_output["hookSpecificOutput"]["additionalContext"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ArtifactError("SessionStart did not emit additionalContext JSON") from exc
    if "[dcness 활성 환경]" not in context:
        raise ArtifactError("SessionStart additionalContext lacks activation marker")
    return {
        "init_core_deployed_files": deployed_count,
        "agent_instruction_reads": agent_read_count,
        "session_start_additional_context_bytes": len(context.encode("utf-8")),
    }


def smoke(repo_root: Path, ref: str, contract: Contract) -> dict[str, int]:
    with tempfile.TemporaryDirectory(prefix="dcness-release-smoke-") as tmp:
        temp_root = Path(tmp)
        bundle = temp_root / "bundle"
        build(repo_root, ref, bundle, contract)
        _verify_required_paths(bundle, contract)
        _verify_agent_surface(bundle, repo_root / "scripts" / "check_public_surface.mjs")
        runtime = _verify_external_runtime(bundle, temp_root)
        artifact = snapshot(bundle, contract)
        context_bytes = runtime["session_start_additional_context_bytes"]
        return {
            "file_count": artifact["file_count"],
            "byte_size": artifact["byte_size"],
            "text_loc": artifact["text_loc"],
            "session_start_additional_context_bytes": context_bytes,
            "session_start_token_approx": (context_bytes + 3) // 4,
            "agent_instruction_reads": runtime["agent_instruction_reads"],
            "init_core_deployed_files": runtime["init_core_deployed_files"],
        }


def _path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    subparsers = root.add_subparsers(dest="command", required=True)

    def add_contract(command: argparse.ArgumentParser) -> None:
        command.add_argument("--contract", type=_path, default=DEFAULT_CONTRACT)

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--repo-root", type=_path, required=True)
    build_parser.add_argument("--ref", required=True)
    build_parser.add_argument("--output", type=_path, required=True)
    add_contract(build_parser)

    snapshot_parser = subparsers.add_parser("snapshot")
    snapshot_parser.add_argument("--root", type=_path, required=True)
    add_contract(snapshot_parser)

    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--expected", type=_path, required=True)
    compare_parser.add_argument("--actual", type=_path, required=True)
    add_contract(compare_parser)

    excluded_parser = subparsers.add_parser("excluded-paths")
    add_contract(excluded_parser)

    smoke_parser = subparsers.add_parser("smoke")
    smoke_parser.add_argument("--repo-root", type=_path, required=True)
    smoke_parser.add_argument("--ref", required=True)
    add_contract(smoke_parser)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        contract = load_contract(args.contract)
        if args.command == "build":
            build(args.repo_root, args.ref, args.output, contract)
        elif args.command == "snapshot":
            print(json.dumps(snapshot(args.root, contract), ensure_ascii=False, indent=2))
        elif args.command == "compare":
            matched, details = compare(args.expected, args.actual, contract)
            if not matched:
                print("\n".join(details), file=sys.stderr)
                return 1
            print("manifest_match=true")
        elif args.command == "excluded-paths":
            print("\n".join(contract.exclude_paths))
        elif args.command == "smoke":
            result = smoke(args.repo_root, args.ref, contract)
            print("release_artifact_smoke=PASS")
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (ArtifactError, OSError, subprocess.SubprocessError) as exc:
        print(f"release_artifact=FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

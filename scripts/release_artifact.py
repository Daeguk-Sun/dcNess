#!/usr/bin/env python3
"""Build, measure, compare, and smoke-test the dcNess release artifact."""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
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
    include_paths: tuple[str, ...]
    product_python: tuple[tuple[str, str], ...]
    allowed_cache_metadata: tuple[str, ...]
    allowed_cache_metadata_globs: tuple[str, ...]
    required_runtime_paths: tuple[str, ...]
    forbidden_product_imports: tuple[str, ...]


def _safe_relative(value: str, *, field: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise ArtifactError(f"{field} must contain safe repo-relative paths: {value!r}")
    normalized = path.as_posix().rstrip("/")
    if normalized in {"", "."}:
        raise ArtifactError(f"{field} cannot select the repository root: {value!r}")
    return normalized


def load_contract(path: Path) -> Contract:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactError(f"cannot read artifact contract {path}: {exc}") from exc
    if payload.get("schema_version") != 2:
        raise ArtifactError("artifact contract schema_version must be 2")

    def paths(field: str) -> tuple[str, ...]:
        values = payload.get(field)
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise ArtifactError(f"artifact contract {field} must be a string array")
        normalized = tuple(_safe_relative(item, field=field) for item in values)
        if len(normalized) != len(set(normalized)):
            raise ArtifactError(f"artifact contract {field} contains duplicates")
        return normalized

    raw_product_python = payload.get("product_python")
    if not isinstance(raw_product_python, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in raw_product_python.items()
    ):
        raise ArtifactError("artifact contract product_python must be a path-to-contract object")
    product_python: list[tuple[str, str]] = []
    normalized_product_paths: set[str] = set()
    for raw_path, raw_reason in raw_product_python.items():
        normalized = _safe_relative(raw_path, field="product_python")
        reason = raw_reason.strip()
        if not normalized.endswith(".py"):
            raise ArtifactError(f"product_python must name Python files: {raw_path!r}")
        if not reason:
            raise ArtifactError(f"product_python contract must not be empty: {raw_path!r}")
        if normalized in normalized_product_paths:
            raise ArtifactError(f"artifact contract product_python contains duplicates: {normalized}")
        normalized_product_paths.add(normalized)
        product_python.append((normalized, reason))

    include_paths = paths("include_paths")
    outside_allowlist = sorted(
        path for path in normalized_product_paths if not _is_under(path, include_paths)
    )
    if outside_allowlist:
        raise ArtifactError(
            "product_python paths must be selected by include_paths: "
            + ", ".join(outside_allowlist)
        )

    return Contract(
        include_paths=include_paths,
        product_python=tuple(product_python),
        allowed_cache_metadata=paths("allowed_cache_metadata"),
        allowed_cache_metadata_globs=paths("allowed_cache_metadata_globs"),
        required_runtime_paths=paths("required_runtime_paths"),
        forbidden_product_imports=paths("forbidden_product_imports"),
    )


def _is_under(relative: str, roots: tuple[str, ...]) -> bool:
    return any(relative == root or relative.startswith(f"{root}/") for root in roots)


def _is_allowed_cache_metadata(relative: str, contract: Contract) -> bool:
    if _is_under(relative, contract.allowed_cache_metadata):
        return True
    path = PurePosixPath(relative)
    return any(path.match(pattern) for pattern in contract.allowed_cache_metadata_globs)


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


def _extract_archive(
    data: bytes,
    output: Path,
    *,
    include_paths: tuple[str, ...] | None = None,
) -> None:
    output.mkdir(parents=True, exist_ok=False)
    matched_includes: set[str] = set()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        for member in archive.getmembers():
            member_path = PurePosixPath(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ArtifactError(f"unsafe git archive member: {member.name}")
            relative = member_path.as_posix().rstrip("/")
            if include_paths is not None:
                matched = {
                    root
                    for root in include_paths
                    if relative == root or relative.startswith(f"{root}/")
                }
                if not matched:
                    continue
                matched_includes.update(matched)
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
    if include_paths is not None:
        missing = sorted(set(include_paths) - matched_includes)
        if missing:
            raise ArtifactError(f"allowlist paths missing at revision: {', '.join(missing)}")

def build(repo_root: Path, ref: str, output: Path, contract: Contract) -> None:
    if output.exists():
        raise ArtifactError(f"output already exists: {output}")
    _extract_archive(_archive(repo_root, ref), output, include_paths=contract.include_paths)
    _verify_product_python_inventory(output, contract)


def _verify_product_python_inventory(bundle: Path, contract: Contract) -> None:
    expected = {path for path, _reason in contract.product_python}
    actual = {
        path.relative_to(bundle).as_posix()
        for path in bundle.rglob("*.py")
        if path.is_file()
    }
    undeclared = sorted(actual - expected)
    missing = sorted(expected - actual)
    details = [*(f"undeclared product Python: {path}" for path in undeclared)]
    details.extend(f"declared product Python missing: {path}" for path in missing)
    if details:
        raise ArtifactError("product Python inventory violated:\n" + "\n".join(details))


def _content_hashes(root: Path, contract: Contract) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if not _is_allowed_cache_metadata(relative, contract):
            hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def snapshot(root: Path, contract: Contract) -> dict[str, Any]:
    if not root.is_dir():
        raise ArtifactError(f"snapshot root is not a directory: {root}")
    files: list[str] = []
    hashes: dict[str, str] = {}
    byte_size = 0
    text_loc = 0
    python_file_count = 0
    python_loc = 0
    composition: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "bytes": 0})
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if _is_allowed_cache_metadata(relative, contract):
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
                if path.suffix == ".py":
                    python_file_count += 1
                    python_loc += data.count(b"\n")
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
        "python_file_count": python_file_count,
        "python_loc": python_loc,
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


SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
RELEASE_TAG_RE = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def _json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactError(f"cannot read {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ArtifactError(f"{label} must contain a JSON object")
    return payload


def _git_file(repo_root: Path, ref: str, relative: str) -> str:
    result = subprocess.run(  # nosec B603
        [_executable("git"), "-C", str(repo_root), "show", f"{ref}:{relative}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise ArtifactError(
            f"cannot read {relative} at {ref}: {result.stderr.strip()}"
        )
    return result.stdout


def _git_commit(repo_root: Path, ref: str) -> str:
    result = subprocess.run(  # nosec B603
        [_executable("git"), "-C", str(repo_root), "rev-parse", "--verify", f"{ref}^{{commit}}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise ArtifactError(f"cannot resolve commit {ref}: {result.stderr.strip()}")
    return result.stdout.strip()


def _plugin_version(root: Path) -> str:
    payload = _json_object(root / ".claude-plugin" / "plugin.json", label="plugin manifest")
    version = payload.get("version")
    if not isinstance(version, str) or SEMVER_RE.fullmatch(version) is None:
        raise ArtifactError(f"plugin version must be strict semver: {version!r}")
    return version


def _marketplace_version(repo_root: Path, ref: str) -> str:
    try:
        payload = json.loads(_git_file(repo_root, ref, ".claude-plugin/marketplace.json"))
        version = payload["metadata"]["version"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ArtifactError("marketplace metadata.version is missing or invalid") from exc
    if not isinstance(version, str) or SEMVER_RE.fullmatch(version) is None:
        raise ArtifactError(f"marketplace version must be strict semver: {version!r}")
    return version


def _semver_tuple(version: str) -> tuple[int, int, int]:
    match = SEMVER_RE.fullmatch(version)
    if match is None:
        raise ArtifactError(f"version must be strict semver: {version!r}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def _install_payload(bundle: Path, destination: Path, contract: Contract) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    preserved = set(contract.allowed_cache_metadata)
    for child in destination.iterdir():
        if child.name in preserved:
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    shutil.copytree(bundle, destination, dirs_exist_ok=True)


def _install_cohort_report(
    candidate: Path,
    published: Path | None,
    source_sha: str,
    contract: Contract,
    temp_root: Path,
) -> dict[str, Any]:
    candidate_digest = snapshot(candidate, contract)["manifest_sha256"]
    clean_cache = temp_root / "clean-cache"
    _install_payload(candidate, clean_cache, contract)
    clean_digest = snapshot(clean_cache, contract)["manifest_sha256"]
    clean_report = {"source_sha": source_sha, "bundle_digest": clean_digest}
    update_report: dict[str, str] | None = None
    if published is not None:
        update_cache = temp_root / "update-cache"
        _install_payload(published, update_cache, contract)
        _install_payload(candidate, update_cache, contract)
        update_digest = snapshot(update_cache, contract)["manifest_sha256"]
        update_report = {"source_sha": source_sha, "bundle_digest": update_digest}
    if clean_digest != candidate_digest or (
        update_report is not None and update_report["bundle_digest"] != candidate_digest
    ):
        raise ArtifactError("clean install and previous-version update cohort digest mismatch")
    return {
        "bundle_digest": candidate_digest,
        "clean_install": clean_report,
        "previous_version_update": update_report,
    }


def verify_release(
    repo_root: Path,
    tag: str,
    candidate: Path,
    published: Path | None,
    published_source_sha: str | None,
    contract: Contract,
) -> dict[str, Any]:
    tag_match = RELEASE_TAG_RE.fullmatch(tag)
    if tag_match is None:
        raise ArtifactError(f"release tag must match vMAJOR.MINOR.PATCH: {tag!r}")
    version = ".".join(tag_match.groups())
    tag_ref = f"refs/tags/{tag}"
    source_sha = _git_commit(repo_root, tag_ref)
    candidate_version = _plugin_version(candidate)
    marketplace_version = _marketplace_version(repo_root, tag_ref)
    if candidate_version != version or marketplace_version != version:
        raise ArtifactError(
            "tag, plugin, and marketplace versions must match: "
            f"tag={version}, plugin={candidate_version}, marketplace={marketplace_version}"
        )

    with tempfile.TemporaryDirectory(prefix="dcness-release-verify-") as tmp:
        temp_root = Path(tmp)
        expected = temp_root / "tag-candidate"
        build(repo_root, tag_ref, expected, contract)
        matched, details = compare(expected, candidate, contract)
        if not matched:
            raise ArtifactError(
                "candidate bundle does not match immutable tag source:\n" + "\n".join(details)
            )

        candidate_digest = snapshot(candidate, contract)["manifest_sha256"]
        previous_version: str | None = None
        previous_digest: str | None = None
        action = "publish"
        if published is not None:
            if not published_source_sha:
                raise ArtifactError("published source SHA is required with a published bundle")
            resolved_published_source = _git_commit(repo_root, published_source_sha)
            if resolved_published_source != published_source_sha:
                raise ArtifactError("published source SHA must be a full commit SHA")
            previous_version = _plugin_version(published)
            previous_digest = snapshot(published, contract)["manifest_sha256"]
            if candidate_version == previous_version:
                if candidate_digest != previous_digest:
                    raise ArtifactError(
                        f"existing version {candidate_version} has a different bundle digest"
                    )
                if source_sha != published_source_sha:
                    raise ArtifactError(
                        f"existing version {candidate_version} has a different source SHA"
                    )
                action = "already_published"
            elif _semver_tuple(candidate_version) <= _semver_tuple(previous_version):
                raise ArtifactError(
                    f"release version must increase: published={previous_version}, candidate={candidate_version}"
                )

        cohorts = _install_cohort_report(
            candidate, published, source_sha, contract, temp_root
        )

    return {
        "action": action,
        "tag": tag,
        "version": candidate_version,
        "source_sha": source_sha,
        "bundle_digest": candidate_digest,
        "previous_version": previous_version,
        "previous_bundle_digest": previous_digest,
        "clean_install": cohorts["clean_install"],
        "previous_version_update": cohorts["previous_version_update"],
    }


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


def _imported_modules(path: Path, bundle: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        raise ArtifactError(f"cannot parse product Python {path}: {exc}") from exc

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                module = node.module or ""
                if module:
                    imported.add(module)
                if module in {"evals", "harness", "scripts", "tests"}:
                    imported.update(f"{module}.{alias.name}" for alias in node.names)
                continue

            package = list(path.relative_to(bundle).parts[:-1])
            ascend = node.level - 1
            if ascend > len(package):
                continue
            base = package[: len(package) - ascend] if ascend else package
            if node.module:
                base.extend(node.module.split("."))
            module = ".".join(base)
            if module:
                imported.add(module)
            if not node.module:
                imported.update(f"{module}.{alias.name}" for alias in node.names)
    return imported


def _product_module_exists(bundle: Path, module: str) -> bool:
    parts = module.split(".")
    candidate = bundle.joinpath(*parts)
    return candidate.is_dir() or candidate.with_suffix(".py").is_file()


def _verify_product_dependencies(bundle: Path, contract: Contract) -> None:
    _verify_product_python_inventory(bundle, contract)
    violations: list[str] = []
    for path in sorted(bundle.rglob("*.py")):
        relative = path.relative_to(bundle).as_posix()
        for imported in sorted(_imported_modules(path, bundle)):
            if imported.startswith("harness.") and not _product_module_exists(bundle, imported):
                violations.append(f"{relative}: missing product module {imported}")
            forbidden = next(
                (
                    prefix
                    for prefix in contract.forbidden_product_imports
                    if imported == prefix or imported.startswith(f"{prefix}.")
                ),
                None,
            )
            if forbidden is not None:
                violations.append(f"{relative}: forbidden import {imported} ({forbidden})")
    if violations:
        raise ArtifactError("product dependency boundary violated:\n" + "\n".join(violations))


def measure(repo_root: Path, ref: str, contract: Contract) -> dict[str, Any]:
    revision = _run_checked(
        [_executable("git"), "-C", str(repo_root), "rev-parse", ref], cwd=repo_root
    ).strip()
    archive = _archive(repo_root, revision)
    with tempfile.TemporaryDirectory(prefix="dcness-release-measure-") as tmp:
        temp_root = Path(tmp)
        repository = temp_root / "repository"
        bundle = temp_root / "bundle"
        _extract_archive(archive, repository)
        _extract_archive(archive, bundle, include_paths=contract.include_paths)
        tracked_python_loc = sum(
            path.read_bytes().count(b"\n")
            for path in repository.rglob("*.py")
            if path.relative_to(repository).parts[0] != "tests"
        )
        artifact = snapshot(bundle, contract)
    return {
        "revision": revision,
        "tracked_python_loc_excluding_tests": tracked_python_loc,
        "release_artifact_python_loc": artifact["python_loc"],
    }


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


def smoke(
    repo_root: Path, ref: str, contract: Contract, previous_root: Path | None = None
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="dcness-release-smoke-") as tmp:
        temp_root = Path(tmp)
        bundle = temp_root / "bundle"
        build(repo_root, ref, bundle, contract)
        _verify_required_paths(bundle, contract)
        _verify_product_dependencies(bundle, contract)
        _verify_agent_surface(bundle, repo_root / "scripts" / "check_public_surface.mjs")
        runtime = _verify_external_runtime(bundle, temp_root)
        artifact = snapshot(bundle, contract)
        source_sha = _git_commit(repo_root, ref)
        cohorts = _install_cohort_report(
            bundle, previous_root, source_sha, contract, temp_root
        )
        context_bytes = runtime["session_start_additional_context_bytes"]
        return {
            "file_count": artifact["file_count"],
            "byte_size": artifact["byte_size"],
            "text_loc": artifact["text_loc"],
            "source_sha": source_sha,
            "bundle_digest": cohorts["bundle_digest"],
            "clean_install": cohorts["clean_install"],
            "previous_version_update": cohorts["previous_version_update"],
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

    dependencies_parser = subparsers.add_parser("check-dependencies")
    dependencies_parser.add_argument("--root", type=_path, required=True)
    add_contract(dependencies_parser)

    measure_parser = subparsers.add_parser("measure")
    measure_parser.add_argument("--repo-root", type=_path, required=True)
    measure_parser.add_argument("--ref", required=True)
    add_contract(measure_parser)

    smoke_parser = subparsers.add_parser("smoke")
    smoke_parser.add_argument("--repo-root", type=_path, required=True)
    smoke_parser.add_argument("--ref", required=True)
    smoke_parser.add_argument("--previous-root", type=_path)
    add_contract(smoke_parser)

    verify_release_parser = subparsers.add_parser("verify-release")
    verify_release_parser.add_argument("--repo-root", type=_path, required=True)
    verify_release_parser.add_argument("--tag", required=True)
    verify_release_parser.add_argument("--candidate", type=_path, required=True)
    verify_release_parser.add_argument("--published", type=_path)
    verify_release_parser.add_argument("--published-source-sha")
    add_contract(verify_release_parser)
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
        elif args.command == "check-dependencies":
            _verify_product_dependencies(args.root, contract)
            print("product_dependencies=PASS")
        elif args.command == "measure":
            print(
                json.dumps(
                    measure(args.repo_root, args.ref, contract), ensure_ascii=False, indent=2
                )
            )
        elif args.command == "smoke":
            result = smoke(args.repo_root, args.ref, contract, args.previous_root)
            print("release_artifact_smoke=PASS")
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        elif args.command == "verify-release":
            print(
                json.dumps(
                    verify_release(
                        args.repo_root,
                        args.tag,
                        args.candidate,
                        args.published,
                        args.published_source_sha,
                        contract,
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        return 0
    except (ArtifactError, OSError, subprocess.SubprocessError) as exc:
        print(f"release_artifact=FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

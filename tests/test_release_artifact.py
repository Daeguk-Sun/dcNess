"""Release artifact composition and marketplace boundary regressions (#1102)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_artifact.py"
CONTRACT = ROOT / "scripts" / "release_artifact.json"


def _run(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd or ROOT,
        check=check,
        text=True,
        capture_output=True,
        timeout=30,
    )


def _current_candidate_ref() -> str:
    """Return a commit-like ref for the candidate visible to the test gate.

    A pre-commit test must inspect the staged tree rather than combine the new
    working-tree contract with the old HEAD archive. Outside pre-commit, fall
    back to Git's non-mutating stash snapshot for tracked worktree changes.
    The created objects are unreachable and no ref or worktree state changes.
    """
    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=ROOT,
        check=False,
    ).returncode
    if staged == 1:
        tree = subprocess.run(
            ["git", "write-tree"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        parent = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        env = os.environ.copy()
        env.update(
            {
                "GIT_AUTHOR_NAME": "dcness test",
                "GIT_AUTHOR_EMAIL": "test@dcness.local",
                "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
                "GIT_COMMITTER_NAME": "dcness test",
                "GIT_COMMITTER_EMAIL": "test@dcness.local",
                "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
            }
        )
        return subprocess.run(
            ["git", "commit-tree", tree, "-p", parent, "-m", "test candidate"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        ).stdout.strip()

    snapshot = subprocess.run(
        ["git", "stash", "create", "release-artifact-test-candidate"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return snapshot or "HEAD"


class ReleaseArtifactContractTests(unittest.TestCase):
    def test_contract_is_a_positive_product_allowlist(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        included = set(contract["include_paths"])
        product_python = contract["product_python"]
        required = set(contract["required_runtime_paths"])

        self.assertEqual(contract["schema_version"], 2)
        self.assertNotIn("exclude_paths", contract)
        self.assertTrue(
            {
                ".claude-plugin/plugin.json",
                "agents",
                "commands",
                "docs/plugin",
                "hooks",
                "skills",
            }.issubset(included)
        )
        self.assertFalse(
            {
                ".claude",
                ".github",
                "docs/internal",
                "evals",
                "tests",
                "scripts/release_artifact.py",
                "scripts/release_preflight.py",
            }
            & included
        )
        self.assertNotIn("harness/agent_effectiveness.py", included)
        self.assertNotIn("harness/outcome_scorecard.py", included)
        self.assertNotIn("harness/agent_effectiveness.py", product_python)
        self.assertNotIn("harness/outcome_scorecard.py", product_python)
        self.assertTrue(product_python)
        self.assertTrue(all(isinstance(reason, str) and reason.strip() for reason in product_python.values()))

        tracked_python = subprocess.run(
            ["git", "ls-files", "*.py"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        included_python = {
            path
            for path in tracked_python
            if any(path == root or path.startswith(f"{root}/") for root in included)
        }
        self.assertEqual(set(product_python), included_python)
        self.assertEqual(contract["allowed_cache_metadata"], [".git", ".in_use"])
        self.assertNotIn("scripts/loop_diagnose.py", included)
        self.assertNotIn("scripts/loop_diagnose.py", required)
        self.assertNotIn("harness/benchmark_aggregate.py", included)
        self.assertNotIn("scripts/measure_main_turns.py", included)
        self.assertEqual(
            contract["allowed_cache_metadata_globs"],
            ["__pycache__/*.pyc", "**/__pycache__/*.pyc"],
        )
        self.assertEqual(
            set(contract["forbidden_product_imports"]),
            {
                "evals",
                "tests",
                "harness.agent_effectiveness",
                "harness.outcome_scorecard",
                "scripts.release_artifact",
                "scripts.release_preflight",
            },
        )

    def test_build_and_snapshot_share_the_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            bundle = Path(tmp) / "bundle"
            contract_path = Path(tmp) / "contract.json"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", repo], check=True)
            subprocess.run(["git", "-C", repo, "config", "user.name", "test"], check=True)
            subprocess.run(
                ["git", "-C", repo, "config", "user.email", "test@example.com"], check=True
            )
            files = {
                ".claude-plugin/plugin.json": '{"name":"dcness","version":"9.9.9"}\n',
                "agents/example.md": "---\nname: example\n---\n",
                "docs/plugin/user.md": "user docs\n",
                "docs/internal/secret.md": "self only\n",
                ".github/workflows/self.yml": "name: self\n",
                "tests/test_self.py": "raise AssertionError\n",
                "PROGRESS.md": "self only\n",
                "repo-only-fixture.txt": "must not be packaged\n",
            }
            for relative, content in files.items():
                path = repo / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            subprocess.run(["git", "-C", repo, "add", "."], check=True)
            subprocess.run(["git", "-C", repo, "commit", "-qm", "fixture"], check=True)
            contract_path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "include_paths": [
                            ".claude-plugin/plugin.json",
                            "agents",
                            "docs/plugin",
                        ],
                        "product_python": {},
                        "allowed_cache_metadata": [".git", ".in_use"],
                        "allowed_cache_metadata_globs": [
                            "__pycache__/*.pyc",
                            "**/__pycache__/*.pyc",
                        ],
                        "required_runtime_paths": [
                            ".claude-plugin/plugin.json",
                            "agents",
                            "docs/plugin",
                        ],
                        "forbidden_product_imports": ["evals", "tests"],
                    }
                ),
                encoding="utf-8",
            )

            _run(
                "build",
                "--repo-root",
                str(repo),
                "--ref",
                "HEAD",
                "--output",
                str(bundle),
                "--contract",
                str(contract_path),
            )

            self.assertTrue((bundle / "agents/example.md").is_file())
            self.assertTrue((bundle / "docs/plugin/user.md").is_file())
            self.assertFalse((bundle / "docs/internal").exists())
            self.assertFalse((bundle / ".github").exists())
            self.assertFalse((bundle / "tests").exists())
            self.assertFalse((bundle / "PROGRESS.md").exists())
            self.assertFalse((bundle / "repo-only-fixture.txt").exists())

            snapshot = json.loads(
                _run(
                    "snapshot",
                    "--root",
                    str(bundle),
                    "--contract",
                    str(contract_path),
                ).stdout
            )
            self.assertEqual(snapshot["file_count"], 3)
            self.assertEqual(snapshot["files"], sorted(snapshot["files"]))
            self.assertGreater(snapshot["byte_size"], 0)
            self.assertGreater(snapshot["text_loc"], 0)

    def test_build_fails_when_an_allowlist_entry_is_missing_at_the_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            contract_path = root / "contract.json"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", repo], check=True)
            subprocess.run(["git", "-C", repo, "config", "user.name", "test"], check=True)
            subprocess.run(
                ["git", "-C", repo, "config", "user.email", "test@example.com"], check=True
            )
            (repo / "product.py").write_text("VALUE = 1\n", encoding="utf-8")
            subprocess.run(["git", "-C", repo, "add", "."], check=True)
            subprocess.run(["git", "-C", repo, "commit", "-qm", "fixture"], check=True)
            contract_path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "include_paths": ["product.py", "missing-runtime.py"],
                        "product_python": {"product.py": "public fixture runtime"},
                        "allowed_cache_metadata": [".git", ".in_use"],
                        "allowed_cache_metadata_globs": [],
                        "required_runtime_paths": ["product.py"],
                        "forbidden_product_imports": ["evals", "tests"],
                    }
                ),
                encoding="utf-8",
            )

            failed = _run(
                "build",
                "--repo-root",
                str(repo),
                "--ref",
                "HEAD",
                "--output",
                str(root / "bundle"),
                "--contract",
                str(contract_path),
                check=False,
            )

            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("allowlist paths missing at revision: missing-runtime.py", failed.stderr)

    def test_build_rejects_undeclared_python_inside_an_included_product_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            contract_path = root / "contract.json"
            (repo / "product").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", repo], check=True)
            subprocess.run(["git", "-C", repo, "config", "user.name", "test"], check=True)
            subprocess.run(
                ["git", "-C", repo, "config", "user.email", "test@example.com"], check=True
            )
            (repo / "product/runtime.py").write_text("VALUE = 1\n", encoding="utf-8")
            (repo / "product/dev_only.py").write_text("VALUE = 2\n", encoding="utf-8")
            subprocess.run(["git", "-C", repo, "add", "."], check=True)
            subprocess.run(["git", "-C", repo, "commit", "-qm", "fixture"], check=True)
            contract_path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "include_paths": ["product"],
                        "product_python": {
                            "product/runtime.py": "public hook runtime",
                        },
                        "allowed_cache_metadata": [".git", ".in_use"],
                        "allowed_cache_metadata_globs": [],
                        "required_runtime_paths": ["product/runtime.py"],
                        "forbidden_product_imports": ["evals", "tests"],
                    }
                ),
                encoding="utf-8",
            )

            failed = _run(
                "build",
                "--repo-root",
                str(repo),
                "--ref",
                "HEAD",
                "--output",
                str(root / "bundle"),
                "--contract",
                str(contract_path),
                check=False,
            )

            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("undeclared product Python: product/dev_only.py", failed.stderr)

    def test_product_dependency_check_rejects_repository_imports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / "bundle"
            contract_path = root / "contract.json"
            bundle.mkdir()
            (bundle / "harness").mkdir()
            (bundle / "product.py").write_text(
                (
                    "from tests import fixture\n"
                    "from harness import missing_runtime\n"
                    "from harness import outcome_scorecard\n"
                ),
                encoding="utf-8",
            )
            (bundle / "harness/relative_product.py").write_text(
                "from . import outcome_scorecard\n", encoding="utf-8"
            )
            contract_path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "include_paths": ["product.py", "harness/relative_product.py"],
                        "product_python": {
                            "product.py": "public fixture runtime",
                            "harness/relative_product.py": "public fixture runtime",
                        },
                        "allowed_cache_metadata": [".git", ".in_use"],
                        "allowed_cache_metadata_globs": [],
                        "required_runtime_paths": ["product.py"],
                        "forbidden_product_imports": [
                            "evals",
                            "tests",
                            "harness.outcome_scorecard",
                        ],
                    }
                ),
                encoding="utf-8",
            )

            failed = _run(
                "check-dependencies",
                "--root",
                str(bundle),
                "--contract",
                str(contract_path),
                check=False,
            )

            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("product.py", failed.stderr)
            self.assertIn("tests", failed.stderr)
            self.assertIn("missing product module harness.missing_runtime", failed.stderr)
            self.assertIn("harness.outcome_scorecard", failed.stderr)
            self.assertIn("harness/relative_product.py", failed.stderr)

    def test_measure_separates_tracked_and_artifact_python_at_one_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            contract_path = root / "contract.json"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", repo], check=True)
            subprocess.run(["git", "-C", repo, "config", "user.name", "test"], check=True)
            subprocess.run(
                ["git", "-C", repo, "config", "user.email", "test@example.com"], check=True
            )
            (repo / "product.py").write_text("VALUE = 1\nVALUE += 1\n", encoding="utf-8")
            (repo / "repo_only.py").write_text("VALUE = 2\n", encoding="utf-8")
            (repo / "tests").mkdir()
            (repo / "tests/test_product.py").write_text("assert True\n", encoding="utf-8")
            contract_path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "include_paths": ["product.py"],
                        "product_python": {"product.py": "public fixture runtime"},
                        "allowed_cache_metadata": [".git", ".in_use"],
                        "allowed_cache_metadata_globs": [
                            "__pycache__/*.pyc",
                            "**/__pycache__/*.pyc",
                        ],
                        "required_runtime_paths": ["product.py"],
                        "forbidden_product_imports": ["evals", "tests"],
                    }
                ),
                encoding="utf-8",
            )
            subprocess.run(["git", "-C", repo, "add", "."], check=True)
            subprocess.run(["git", "-C", repo, "commit", "-qm", "fixture"], check=True)

            measured = json.loads(
                _run(
                    "measure",
                    "--repo-root",
                    str(repo),
                    "--ref",
                    "HEAD",
                    "--contract",
                    str(contract_path),
                ).stdout
            )

            self.assertEqual(measured["revision"], subprocess.run(
                ["git", "-C", repo, "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip())
            self.assertEqual(measured["tracked_python_loc_excluding_tests"], 3)
            self.assertEqual(measured["release_artifact_python_loc"], 2)

    def test_compare_allows_only_declared_cache_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / "candidate"
            cache = Path(tmp) / "cache"
            candidate.mkdir()
            cache.mkdir()
            (candidate / "runtime.txt").write_text("same\n", encoding="utf-8")
            (cache / "runtime.txt").write_text("same\n", encoding="utf-8")
            (cache / ".in_use").write_text("metadata\n", encoding="utf-8")
            for root in (candidate, cache):
                package = root / "harness"
                package.mkdir()
                (package / "__init__.py").write_text("", encoding="utf-8")
                (package / "runtime.py").write_text("VALUE = 1\n", encoding="utf-8")

            runtime_env = {**os.environ, "PYTHONPATH": str(cache)}
            runtime_env.pop("PYTHONDONTWRITEBYTECODE", None)
            subprocess.run(
                [sys.executable, "-c", "import harness.runtime"],
                cwd=tmp,
                env=runtime_env,
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertTrue(list(cache.rglob("__pycache__/*.pyc")))

            passed = _run(
                "compare",
                "--expected",
                str(candidate),
                "--actual",
                str(cache),
                "--contract",
                str(CONTRACT),
            )
            self.assertIn("manifest_match=true", passed.stdout)

            snapshot = json.loads(
                _run("snapshot", "--root", str(cache), "--contract", str(CONTRACT)).stdout
            )
            self.assertFalse(any("__pycache__" in path for path in snapshot["files"]))

            unexpected = cache / "harness" / "__pycache__" / "unexpected.txt"
            unexpected.write_text("drift\n", encoding="utf-8")
            failed = _run(
                "compare",
                "--expected",
                str(candidate),
                "--actual",
                str(cache),
                "--contract",
                str(CONTRACT),
                check=False,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("harness/__pycache__/unexpected.txt", failed.stderr)

    def test_marketplace_installs_the_release_ref_at_a_new_version(self) -> None:
        marketplace = json.loads(
            (ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8")
        )
        plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
        source = marketplace["plugins"][0]["source"]

        self.assertEqual(
            source,
            {
                "source": "github",
                "repo": "Daeguk-Sun/dcNess",
                "ref": "release",
            },
        )
        self.assertEqual(marketplace["metadata"]["version"], plugin["version"])
        baseline = json.loads(
            (ROOT / "docs/internal/marketplace-artifact-baseline.json").read_text(
                encoding="utf-8"
            )
        )

        def semver(value: str) -> tuple[int, int, int]:
            match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value)
            self.assertIsNotNone(match, f"invalid semver: {value}")
            assert match is not None
            major, minor, patch = match.groups()
            return int(major), int(minor), int(patch)

        self.assertGreater(semver(plugin["version"]), semver(baseline["plugin_version"]))

    def test_release_workflow_is_tag_only_and_tests_the_exact_source_before_publish(self) -> None:
        workflow = (ROOT / ".github/workflows/release-sync.yml").read_text(encoding="utf-8")

        self.assertIn("tags:", workflow)
        self.assertIn("'v*.*.*'", workflow)
        self.assertNotIn("branches: [main]", workflow)
        self.assertIn("python3 -m unittest discover -s tests -v", workflow)
        self.assertIn('bash scripts/sync_release.sh --tag "$GITHUB_REF_NAME" --yes', workflow)
        self.assertLess(
            workflow.index("python3 -m unittest discover -s tests -v"),
            workflow.index("bash scripts/sync_release.sh"),
        )

    def test_sync_release_has_no_second_exclude_list_tag_mutation_or_hook_bypass(self) -> None:
        script = (ROOT / "scripts/sync_release.sh").read_text(encoding="utf-8")

        self.assertIn("scripts/release_artifact.py", script)
        self.assertIn('"$ARTIFACT_BUILDER" build', script)
        self.assertIn("verify-release", script)
        self.assertIn('"$ARTIFACT_BUILDER" "${VERIFY_ARGS[@]}"', script)
        self.assertIn("--previous-root", script)
        self.assertIn('"$ARTIFACT_BUILDER" "${SMOKE_ARGS[@]}"', script)
        self.assertIn("--tag", script)
        self.assertNotIn("git tag", script)
        self.assertNotIn("EXCLUDE_PATHS=(", script)
        self.assertNotIn("excluded-paths", script)
        self.assertNotIn("--no-verify", script)

        pre_push = (ROOT / "scripts/hooks/pre-push").read_text(encoding="utf-8")
        git_spec = (ROOT / "docs/plugin/git-spec.md").read_text(encoding="utf-8")
        self.assertIn("is_dcness_release_remote", pre_push)
        self.assertNotIn("scripts/sync_release.sh", git_spec)
        subprocess.run(
            [
                "node",
                str(ROOT / "scripts/check_git_naming.mjs"),
                "--title",
                "[docs] release 1.2.3 from v1.2.3@abcdef0",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        push_input = f"refs/heads/release {'a' * 40} refs/heads/release {'b' * 40}\n"
        external_release_push = subprocess.run(
            [
                "sh",
                str(ROOT / "scripts/hooks/pre-push"),
                "origin",
                "https://github.com/example/project.git",
            ],
            cwd=ROOT,
            input=push_input,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotEqual(external_release_push.returncode, 0)
        self.assertIn("브랜치명 형식 위반", external_release_push.stderr)

        for remote in (
            "https://github.com/Daeguk-Sun/dcNess",
            "https://github.com/Daeguk-Sun/dcNess.git",
            "git@github.com:Daeguk-Sun/dcNess",
            "git@github.com:Daeguk-Sun/dcNess.git",
            "ssh://git@github.com/Daeguk-Sun/dcNess",
            "ssh://git@github.com/Daeguk-Sun/dcNess.git",
            "https://github.com/alruminum/dcNess.git",
        ):
            with self.subTest(remote=remote):
                dcness_release_push = subprocess.run(
                    ["sh", str(ROOT / "scripts/hooks/pre-push"), "origin", remote],
                    cwd=ROOT,
                    input=push_input,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(dcness_release_push.returncode, 0, dcness_release_push.stderr)

    def test_sync_release_fails_closed_when_contract_command_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = tmp_path / "repo"
            remote = tmp_path / "remote.git"
            fake_bin = tmp_path / "bin"
            (repo / "scripts").mkdir(parents=True)
            fake_bin.mkdir()
            shutil.copy2(ROOT / "scripts/sync_release.sh", repo / "scripts/sync_release.sh")
            (repo / "runtime.txt").write_text("runtime\n", encoding="utf-8")
            fake_python = fake_bin / "python3"
            fake_python.write_text("#!/bin/sh\nexit 17\n", encoding="utf-8")
            fake_python.chmod(0o755)

            subprocess.run(["git", "init", "-q", "--bare", remote], check=True)
            subprocess.run(["git", "init", "-q", "-b", "main", repo], check=True)
            subprocess.run(["git", "-C", repo, "config", "user.name", "test"], check=True)
            subprocess.run(
                ["git", "-C", repo, "config", "user.email", "test@example.com"],
                check=True,
            )
            subprocess.run(["git", "-C", repo, "add", "."], check=True)
            subprocess.run(["git", "-C", repo, "commit", "-qm", "fixture"], check=True)
            subprocess.run(["git", "-C", repo, "tag", "v1.0.0"], check=True)
            subprocess.run(["git", "-C", repo, "remote", "add", "origin", str(remote)], check=True)
            subprocess.run(["git", "-C", repo, "push", "-q", "-u", "origin", "main"], check=True)
            subprocess.run(["git", "-C", repo, "push", "-q", "origin", "v1.0.0"], check=True)

            result = subprocess.run(
                ["bash", "scripts/sync_release.sh", "--tag", "v1.0.0", "--yes"],
                cwd=repo,
                env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "positive allowlist artifact 생성에 실패해 release publish를 중단합니다",
                result.stderr,
            )
            remote_release = subprocess.run(
                ["git", "--git-dir", str(remote), "show-ref", "--verify", "refs/heads/release"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(remote_release.returncode, 0)

    def test_main_push_style_sync_invocation_leaves_release_ref_and_tree_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            (repo / "scripts").mkdir(parents=True)
            shutil.copy2(ROOT / "scripts/sync_release.sh", repo / "scripts/sync_release.sh")
            (repo / "product.txt").write_text("published\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", "-b", "main", repo], check=True)
            subprocess.run(["git", "-C", repo, "config", "user.name", "test"], check=True)
            subprocess.run(
                ["git", "-C", repo, "config", "user.email", "test@example.com"], check=True
            )
            subprocess.run(["git", "-C", repo, "add", "."], check=True)
            subprocess.run(["git", "-C", repo, "commit", "-qm", "published"], check=True)
            subprocess.run(["git", "-C", repo, "branch", "release"], check=True)
            refs_before = subprocess.run(
                ["git", "-C", repo, "show-ref"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            tree_before = subprocess.run(
                ["git", "-C", repo, "rev-parse", "release^{tree}"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            result = subprocess.run(
                ["bash", "scripts/sync_release.sh", "--yes"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("release publish requires --tag", result.stderr)
            refs_after = subprocess.run(
                ["git", "-C", repo, "show-ref"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            tree_after = subprocess.run(
                ["git", "-C", repo, "rev-parse", "release^{tree}"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(refs_after, refs_before)
            self.assertEqual(tree_after, tree_before)

    def test_sync_release_publishes_only_the_positive_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            remote = root / "remote.git"
            (repo / "scripts").mkdir(parents=True)
            shutil.copy2(ROOT / "scripts/sync_release.sh", repo / "scripts/sync_release.sh")
            shutil.copy2(ROOT / "scripts/release_artifact.py", repo / "scripts/release_artifact.py")
            (repo / "scripts/release_artifact.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "include_paths": [".claude-plugin/plugin.json", "product.txt"],
                        "product_python": {},
                        "allowed_cache_metadata": [".git", ".in_use"],
                        "allowed_cache_metadata_globs": [],
                        "required_runtime_paths": [".claude-plugin/plugin.json", "product.txt"],
                        "forbidden_product_imports": ["evals", "tests"],
                    }
                ),
                encoding="utf-8",
            )
            (repo / ".claude-plugin").mkdir()
            (repo / ".claude-plugin/plugin.json").write_text(
                json.dumps({"name": "dcness", "version": "1.0.0"}) + "\n",
                encoding="utf-8",
            )
            (repo / ".claude-plugin/marketplace.json").write_text(
                json.dumps({"metadata": {"version": "1.0.0"}}) + "\n",
                encoding="utf-8",
            )
            (repo / "product.txt").write_text("product\n", encoding="utf-8")
            (repo / "repo-only.txt").write_text("self\n", encoding="utf-8")

            subprocess.run(["git", "init", "-q", "--bare", remote], check=True)
            subprocess.run(["git", "init", "-q", "-b", "main", repo], check=True)
            subprocess.run(["git", "-C", repo, "config", "user.name", "test"], check=True)
            subprocess.run(
                ["git", "-C", repo, "config", "user.email", "test@example.com"], check=True
            )
            subprocess.run(["git", "-C", repo, "add", "."], check=True)
            subprocess.run(["git", "-C", repo, "commit", "-qm", "fixture"], check=True)
            source_sha = subprocess.run(
                ["git", "-C", repo, "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(["git", "-C", repo, "tag", "v1.0.0"], check=True)
            subprocess.run(["git", "-C", repo, "remote", "add", "origin", str(remote)], check=True)
            subprocess.run(["git", "-C", repo, "push", "-q", "-u", "origin", "main"], check=True)
            subprocess.run(["git", "-C", repo, "push", "-q", "origin", "v1.0.0"], check=True)

            result = subprocess.run(
                ["bash", "scripts/sync_release.sh", "--tag", "v1.0.0", "--yes"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            released = subprocess.run(
                ["git", "--git-dir", str(remote), "ls-tree", "-r", "--name-only", "release"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()
            self.assertEqual(released, [".claude-plugin/plugin.json", "product.txt"])
            released_parent = subprocess.run(
                ["git", "--git-dir", str(remote), "rev-parse", "release^"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(released_parent, source_sha)
            remote_tag = subprocess.run(
                ["git", "--git-dir", str(remote), "rev-parse", "v1.0.0^{}"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(remote_tag, source_sha)
            self.assertEqual(
                subprocess.run(
                    ["git", "-C", repo, "branch", "--show-current"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                "main",
            )

    def test_verify_release_rejects_same_version_digest_drift_without_mutating_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            contract_path = root / "contract.json"
            published = root / "published"
            candidate = root / "candidate"
            (repo / ".claude-plugin").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", "-b", "main", repo], check=True)
            subprocess.run(["git", "-C", repo, "config", "user.name", "test"], check=True)
            subprocess.run(
                ["git", "-C", repo, "config", "user.email", "test@example.com"], check=True
            )
            contract_path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "include_paths": [".claude-plugin/plugin.json", "product.txt"],
                        "product_python": {},
                        "allowed_cache_metadata": [".git", ".in_use"],
                        "allowed_cache_metadata_globs": [],
                        "required_runtime_paths": [".claude-plugin/plugin.json", "product.txt"],
                        "forbidden_product_imports": ["evals", "tests"],
                    }
                ),
                encoding="utf-8",
            )
            (repo / ".claude-plugin/plugin.json").write_text(
                json.dumps({"name": "dcness", "version": "1.0.0"}) + "\n",
                encoding="utf-8",
            )
            (repo / ".claude-plugin/marketplace.json").write_text(
                json.dumps({"metadata": {"version": "1.0.0"}}) + "\n",
                encoding="utf-8",
            )
            (repo / "product.txt").write_text("published\n", encoding="utf-8")
            subprocess.run(["git", "-C", repo, "add", "."], check=True)
            subprocess.run(["git", "-C", repo, "commit", "-qm", "published"], check=True)
            published_source = subprocess.run(
                ["git", "-C", repo, "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(["git", "-C", repo, "tag", "v1.0.0"], check=True)
            subprocess.run(["git", "-C", repo, "branch", "release"], check=True)
            _run(
                "build",
                "--repo-root",
                str(repo),
                "--ref",
                "HEAD",
                "--output",
                str(published),
                "--contract",
                str(contract_path),
            )

            (repo / "product.txt").write_text("drifted\n", encoding="utf-8")
            subprocess.run(["git", "-C", repo, "add", "."], check=True)
            subprocess.run(["git", "-C", repo, "commit", "-qm", "drift"], check=True)
            subprocess.run(["git", "-C", repo, "tag", "-f", "v1.0.0"], check=True)
            _run(
                "build",
                "--repo-root",
                str(repo),
                "--ref",
                "HEAD",
                "--output",
                str(candidate),
                "--contract",
                str(contract_path),
            )
            refs_before = subprocess.run(
                ["git", "-C", repo, "show-ref"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout

            failed = _run(
                "verify-release",
                "--repo-root",
                str(repo),
                "--tag",
                "v1.0.0",
                "--candidate",
                str(candidate),
                "--published",
                str(published),
                "--published-source-sha",
                published_source,
                "--contract",
                str(contract_path),
                check=False,
            )

            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("existing version 1.0.0 has a different bundle digest", failed.stderr)
            refs_after = subprocess.run(
                ["git", "-C", repo, "show-ref"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertEqual(refs_after, refs_before)

    def test_verify_release_reports_new_version_cohorts_and_rejects_version_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            contract_path = root / "contract.json"
            published = root / "published"
            candidate = root / "candidate"
            (repo / ".claude-plugin").mkdir(parents=True)
            (repo / "product").mkdir()
            subprocess.run(["git", "init", "-q", "-b", "main", repo], check=True)
            subprocess.run(["git", "-C", repo, "config", "user.name", "test"], check=True)
            subprocess.run(
                ["git", "-C", repo, "config", "user.email", "test@example.com"], check=True
            )
            contract_path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "include_paths": [".claude-plugin/plugin.json", "product"],
                        "product_python": {},
                        "allowed_cache_metadata": [".git", ".in_use"],
                        "allowed_cache_metadata_globs": [],
                        "required_runtime_paths": [".claude-plugin/plugin.json", "product"],
                        "forbidden_product_imports": ["evals", "tests"],
                    }
                ),
                encoding="utf-8",
            )
            (repo / ".claude-plugin/plugin.json").write_text(
                json.dumps({"name": "dcness", "version": "1.0.0"}) + "\n",
                encoding="utf-8",
            )
            (repo / ".claude-plugin/marketplace.json").write_text(
                json.dumps({"metadata": {"version": "1.0.0"}}) + "\n",
                encoding="utf-8",
            )
            (repo / "product/runtime.txt").write_text("old\n", encoding="utf-8")
            (repo / "product/removed.txt").write_text("remove on update\n", encoding="utf-8")
            subprocess.run(["git", "-C", repo, "add", "."], check=True)
            subprocess.run(["git", "-C", repo, "commit", "-qm", "v1"], check=True)
            published_source = subprocess.run(
                ["git", "-C", repo, "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(["git", "-C", repo, "tag", "v1.0.0"], check=True)
            _run(
                "build",
                "--repo-root",
                str(repo),
                "--ref",
                "HEAD",
                "--output",
                str(published),
                "--contract",
                str(contract_path),
            )

            (repo / ".claude-plugin/plugin.json").write_text(
                json.dumps({"name": "dcness", "version": "1.1.0"}) + "\n",
                encoding="utf-8",
            )
            (repo / ".claude-plugin/marketplace.json").write_text(
                json.dumps({"metadata": {"version": "1.1.0"}}) + "\n",
                encoding="utf-8",
            )
            (repo / "product/runtime.txt").write_text("new\n", encoding="utf-8")
            (repo / "product/removed.txt").unlink()
            subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
            subprocess.run(["git", "-C", repo, "commit", "-qm", "v1.1"], check=True)
            source_sha = subprocess.run(
                ["git", "-C", repo, "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(["git", "-C", repo, "tag", "v1.1.0"], check=True)
            _run(
                "build",
                "--repo-root",
                str(repo),
                "--ref",
                "HEAD",
                "--output",
                str(candidate),
                "--contract",
                str(contract_path),
            )

            result = _run(
                "verify-release",
                "--repo-root",
                str(repo),
                "--tag",
                "v1.1.0",
                "--candidate",
                str(candidate),
                "--published",
                str(published),
                "--published-source-sha",
                published_source,
                "--contract",
                str(contract_path),
            )
            report = json.loads(result.stdout)

            self.assertEqual(report["action"], "publish")
            self.assertEqual(report["source_sha"], source_sha)
            self.assertEqual(report["version"], "1.1.0")
            self.assertEqual(
                report["clean_install"],
                {
                    "source_sha": source_sha,
                    "bundle_digest": report["bundle_digest"],
                },
            )
            self.assertEqual(report["previous_version_update"], report["clean_install"])

            subprocess.run(["git", "-C", repo, "tag", "v1.2.0"], check=True)
            version_mismatch = _run(
                "verify-release",
                "--repo-root",
                str(repo),
                "--tag",
                "v1.2.0",
                "--candidate",
                str(candidate),
                "--published",
                str(published),
                "--published-source-sha",
                published_source,
                "--contract",
                str(contract_path),
                check=False,
            )
            self.assertNotEqual(version_mismatch.returncode, 0)
            self.assertIn(
                "tag, plugin, and marketplace versions must match",
                version_mismatch.stderr,
            )

    def test_distributed_markdown_links_do_not_target_excluded_paths(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        included = tuple(contract["include_paths"])
        tracked = subprocess.run(
            ["git", "ls-files", "*.md"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.splitlines()
        link_pattern = re.compile(r"(?<!!)\[[^]]*\]\(([^)]+)\)")
        broken: list[str] = []

        def is_included(relative: str) -> bool:
            return any(relative == root or relative.startswith(f"{root}/") for root in included)

        for relative in tracked:
            if not is_included(relative):
                continue
            source = ROOT / relative
            if not source.is_file():
                continue
            in_fence = False
            for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("```"):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    continue
                prose = re.sub(r"`[^`]*`", "", line)
                for raw_target in link_pattern.findall(prose):
                    target = raw_target.split("#", 1)[0].strip().strip("<>")
                    if not target or "://" in target or target.startswith(("/", "mailto:")):
                        continue
                    resolved = (source.parent / target).resolve()
                    try:
                        target_relative = resolved.relative_to(ROOT.resolve()).as_posix()
                    except ValueError:
                        broken.append(f"{relative}:{line_number}: {raw_target}")
                        continue
                    if not resolved.exists() or not is_included(target_relative):
                        broken.append(f"{relative}:{line_number}: {raw_target}")

        self.assertEqual(broken, [], "distributed artifact has broken relative links")

    def test_current_candidate_passes_runtime_smoke(self) -> None:
        candidate_ref = _current_candidate_ref()
        result = _run(
            "smoke",
            "--repo-root",
            str(ROOT),
            "--ref",
            candidate_ref,
            "--contract",
            str(CONTRACT),
        )
        self.assertIn("release_artifact_smoke=PASS", result.stdout)
        smoke_metrics = json.loads(result.stdout.splitlines()[-1])
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "bundle"
            _run(
                "build",
                "--repo-root",
                str(ROOT),
                "--ref",
                candidate_ref,
                "--output",
                str(bundle),
                "--contract",
                str(CONTRACT),
            )
            direct = json.loads(
                _run("snapshot", "--root", str(bundle), "--contract", str(CONTRACT)).stdout
            )
        self.assertEqual(smoke_metrics["file_count"], direct["file_count"])
        self.assertEqual(smoke_metrics["byte_size"], direct["byte_size"])
        self.assertEqual(smoke_metrics["bundle_digest"], direct["manifest_sha256"])
        self.assertEqual(
            smoke_metrics["clean_install"],
            {
                "source_sha": smoke_metrics["source_sha"],
                "bundle_digest": smoke_metrics["bundle_digest"],
            },
        )
        self.assertIsNone(smoke_metrics["previous_version_update"])


if __name__ == "__main__":
    unittest.main()

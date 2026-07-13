"""Release artifact composition and marketplace boundary regressions (#1102)."""

from __future__ import annotations

import json
from pathlib import Path
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


class ReleaseArtifactContractTests(unittest.TestCase):
    def test_contract_excludes_self_only_paths_and_names_runtime_metadata(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        excluded = set(contract["exclude_paths"])

        self.assertTrue(
            {
                ".claude",
                ".github",
                "AGENTS.md",
                "CLAUDE.md",
                "PROGRESS.md",
                "docs/archive",
                "docs/internal",
                "evals",
                "harness/CLAUDE.md",
                "tests",
                "pyproject.toml",
                "requirements-eval.txt",
                "requirements-quality.txt",
                "scripts/CLAUDE.md",
                "scripts/check_cross_refs.mjs",
                "scripts/check_doc_path_integrity.mjs",
                "scripts/check_python_tests.sh",
                "scripts/check_plugin_manifest.mjs",
                "scripts/check_public_evidence.mjs",
                "scripts/check_public_surface.mjs",
                "scripts/hooks/cc-pre-commit.sh",
                "scripts/launchd",
                "scripts/release_artifact.json",
                "scripts/release_artifact.py",
                "scripts/setup_branch_protection.mjs",
                "scripts/sync_release.sh",
                "templates/CLAUDE.md",
            }.issubset(excluded)
        )
        self.assertEqual(contract["allowed_cache_metadata"], [".git", ".in_use"])

        runtime_checkers = {
            "scripts/check_design_artifact_structure.mjs",
            "scripts/check_git_naming.mjs",
            "scripts/check_issue_body.mjs",
            "scripts/check_pr_body.mjs",
        }
        all_checkers = {
            path.relative_to(ROOT).as_posix() for path in (ROOT / "scripts").glob("check_*")
        }
        self.assertEqual(all_checkers - excluded, runtime_checkers)

    def test_build_and_snapshot_share_the_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            bundle = Path(tmp) / "bundle"
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
            }
            for relative, content in files.items():
                path = repo / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            subprocess.run(["git", "-C", repo, "add", "."], check=True)
            subprocess.run(["git", "-C", repo, "commit", "-qm", "fixture"], check=True)

            _run(
                "build",
                "--repo-root",
                str(repo),
                "--ref",
                "HEAD",
                "--output",
                str(bundle),
                "--contract",
                str(CONTRACT),
            )

            self.assertTrue((bundle / "agents/example.md").is_file())
            self.assertTrue((bundle / "docs/plugin/user.md").is_file())
            self.assertFalse((bundle / "docs/internal").exists())
            self.assertFalse((bundle / ".github").exists())
            self.assertFalse((bundle / "tests").exists())
            self.assertFalse((bundle / "PROGRESS.md").exists())

            snapshot = json.loads(
                _run(
                    "snapshot",
                    "--root",
                    str(bundle),
                    "--contract",
                    str(CONTRACT),
                ).stdout
            )
            self.assertEqual(snapshot["file_count"], 3)
            self.assertEqual(snapshot["files"], sorted(snapshot["files"]))
            self.assertGreater(snapshot["byte_size"], 0)
            self.assertGreater(snapshot["text_loc"], 0)

    def test_compare_allows_only_declared_cache_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / "candidate"
            cache = Path(tmp) / "cache"
            candidate.mkdir()
            cache.mkdir()
            (candidate / "runtime.txt").write_text("same\n", encoding="utf-8")
            (cache / "runtime.txt").write_text("same\n", encoding="utf-8")
            (cache / ".in_use").write_text("metadata\n", encoding="utf-8")

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

            (cache / "unexpected.txt").write_text("drift\n", encoding="utf-8")
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
            self.assertIn("unexpected.txt", failed.stderr)

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
        self.assertEqual(plugin["version"], "0.22.1")
        self.assertEqual(marketplace["metadata"]["version"], plugin["version"])

    def test_sync_release_has_no_second_exclude_list_or_hook_bypass(self) -> None:
        script = (ROOT / "scripts/sync_release.sh").read_text(encoding="utf-8")

        self.assertIn("scripts/release_artifact.py", script)
        self.assertIn("excluded-paths", script)
        self.assertIn('git commit -m "[docs] release sync from main@', script)
        self.assertNotIn("EXCLUDE_PATHS=(", script)
        self.assertNotIn("--no-verify", script)

        pre_push = (ROOT / "scripts/hooks/pre-push").read_text(encoding="utf-8")
        git_spec = (ROOT / "docs/plugin/git-spec.md").read_text(encoding="utf-8")
        self.assertIn("main|master|HEAD|develop|release", pre_push)
        self.assertIn("`release`", git_spec)
        subprocess.run(
            [
                "node",
                str(ROOT / "scripts/check_git_naming.mjs"),
                "--title",
                "[docs] release sync from main@abcdef0",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        release_push = subprocess.run(
            ["sh", str(ROOT / "scripts/hooks/pre-push")],
            cwd=ROOT,
            input=f"refs/heads/release {'a' * 40} refs/heads/release {'b' * 40}\n",
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(release_push.returncode, 0, release_push.stderr)

    def test_current_candidate_passes_runtime_smoke(self) -> None:
        result = _run(
            "smoke",
            "--repo-root",
            str(ROOT),
            "--ref",
            "HEAD",
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
                "HEAD",
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


if __name__ == "__main__":
    unittest.main()

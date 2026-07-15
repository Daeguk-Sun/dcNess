"""Public file/read/Bash/MCP boundary contracts."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from harness import agent_boundary as boundary
from harness.agent_boundary import (
    ALLOW_MATRIX,
    check_bash_mutation,
    check_github_mcp_mutation,
    check_read_allowed,
    check_write_allowed,
    extract_bash_paths,
    is_infra_project,
    load_project_boundary_overrides,
)


@contextmanager
def external_boundary():
    with (
        patch("harness.agent_boundary.is_infra_project", return_value=False),
        patch("harness.agent_boundary.is_opt_out", return_value=False),
    ):
        yield


class ActivationBoundaryTests(unittest.TestCase):
    def test_infra_project_uses_only_explicit_marker_signals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            home = Path(directory) / "home"
            root.mkdir()
            home.mkdir()
            self.assertFalse(is_infra_project(root, env={}, home=home))
            self.assertTrue(is_infra_project(root, env={"DCNESS_INFRA": "1"}, home=home))

            marker = home / ".claude/.dcness-infra"
            marker.parent.mkdir()
            marker.touch()
            self.assertTrue(is_infra_project(root, env={}, home=home))

            marker.unlink()
            manifest = root / ".claude-plugin/plugin.json"
            manifest.parent.mkdir()
            manifest.write_text('{"name":"dcness"}', encoding="utf-8")
            self.assertTrue(is_infra_project(root / "child", env={}, home=home))

    def test_plugin_root_environment_is_not_an_infra_bypass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            home.mkdir()
            env = {"CLAUDE_PLUGIN_ROOT": "/tmp/dcness"}
            self.assertFalse(is_infra_project(root, env=env, home=home))


class WriteBoundaryTests(unittest.TestCase):
    def test_allow_matrix_has_current_agents_and_no_retired_aliases(self) -> None:
        self.assertEqual(
            set(ALLOW_MATRIX),
            {
                "build-worker",
                "module-architect",
                "system-architect",
                "designer",
                "ux-architect",
                "tech-reviewer",
                "impl-validator",
                "architecture-validator",
                "product-acceptance",
            },
        )

    def test_main_unknown_and_opt_out_preserve_fail_open_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertIsNone(check_write_allowed(None, "CLAUDE.md", cwd=root))
            with external_boundary():
                self.assertIsNone(check_write_allowed("future-agent", "anywhere.txt", cwd=root))
            (root / ".no-dcness-guard").touch()
            with patch("harness.agent_boundary.is_infra_project", return_value=False):
                self.assertIsNone(check_write_allowed("build-worker", "CLAUDE.md", cwd=root))

    def test_role_matrix_is_table_driven(self) -> None:
        cases = [
            ("build-worker", "src/service.ts", True),
            ("build-worker", "apps/api/alembic/001.py", True),
            ("build-worker", "tests/test_service.py", True),
            ("build-worker", "app.py", True),
            ("build-worker", "docs/src/example.py", False),
            ("build-worker", "jest.config.ts", False),
            ("module-architect", "docs/architecture.md", True),
            ("system-architect", "docs/epics/42/architecture.md", True),
            ("module-architect", "docs/stories.md", False),
            ("designer", "docs/design-variants/drafts/a.html", True),
            ("designer", "docs/design-variants/canvas/a.html", False),
            ("ux-architect", "docs/epics/42/ux-flow.md", True),
            ("ux-architect", "docs/ux-flow.md", False),
            ("tech-reviewer", "docs/tech-review.md", True),
            ("tech-reviewer", ".dcness-work/reviews/42.md", True),
        ]
        with tempfile.TemporaryDirectory() as directory, external_boundary():
            root = Path(directory)
            for agent, path, allowed in cases:
                with self.subTest(agent=agent, path=path):
                    reason = check_write_allowed(agent, path, cwd=root)
                    self.assertEqual(reason is None, allowed, reason)

    def test_write_zero_and_protected_paths_cannot_be_opened(self) -> None:
        protected = (
            "CLAUDE.md",
            "hooks/file-guard.sh",
            "harness/hooks.py",
            ".dcness/boundary.json",
            ".no-dcness-guard",
            ".claude-plugin/plugin.json",
        )
        with tempfile.TemporaryDirectory() as directory, external_boundary():
            root = Path(directory)
            for agent in ("impl-validator", "architecture-validator", "product-acceptance"):
                self.assertIsNotNone(check_write_allowed(agent, "docs/report.md", cwd=root))
            for path in protected:
                with self.subTest(path=path):
                    self.assertIsNotNone(check_write_allowed("build-worker", path, cwd=root))

    def test_external_and_shell_expansion_paths_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory, external_boundary():
            root = Path(directory)
            for path in ("../outside.ts", "/tmp/outside.ts", "~/secret.ts"):
                self.assertIsNotNone(check_write_allowed("build-worker", path, cwd=root))
            self.assertIsNotNone(
                check_write_allowed("build-worker", "$PWD/../src/x.ts", cwd=root, shell_context=True)
            )
            self.assertIsNone(
                check_write_allowed("build-worker", "src/users.$id.ts", cwd=root)
            )

    def test_run_prose_carveout_is_narrow(self) -> None:
        run = ".claude/harness-state/.sessions/s/runs/run-1/"
        with tempfile.TemporaryDirectory() as directory, external_boundary():
            root = Path(directory)
            self.assertIsNone(check_write_allowed("build-worker", run + "build-impl.md", cwd=root))
            self.assertIsNotNone(check_write_allowed("build-worker", run + "impl-validator.md", cwd=root))
            self.assertIsNotNone(check_write_allowed("module-architect", run + "build-impl.md", cwd=root))


class ProjectOverrideTests(unittest.TestCase):
    def _repo(self, directory: str, payload: object) -> Path:
        root = Path(directory)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        config = root / ".dcness/boundary.json"
        config.parent.mkdir()
        config.write_text(json.dumps(payload), encoding="utf-8")
        boundary._BOUNDARY_ROOT_CACHE.clear()
        return root

    def test_add_remove_and_immutable_boundaries(self) -> None:
        payload = {
            "build-worker": {"add": [r"^custom/"], "remove": [r"^src/locked/"]},
            "impl-validator": {"add": [r".*"]},
        }
        with tempfile.TemporaryDirectory() as directory, external_boundary():
            root = self._repo(directory, payload)
            self.assertIsNone(check_write_allowed("build-worker", "custom/x.kt", cwd=root))
            self.assertIsNotNone(check_write_allowed("build-worker", "src/locked/x.ts", cwd=root))
            self.assertIsNotNone(check_write_allowed("build-worker", ".dcness/override", cwd=root))
            self.assertIsNotNone(check_write_allowed("impl-validator", "custom/report.md", cwd=root))

    def test_malformed_fragments_degrade_safely_and_retired_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(directory, {"build-worker": {"add": ["[bad", 1]}})
            self.assertEqual(load_project_boundary_overrides(root), {})

        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(directory, {"engineer": {"add": [r"^src/"]}})
            with self.assertRaises(ValueError):
                load_project_boundary_overrides(root)


class ReadBoundaryTests(unittest.TestCase):
    def test_read_policy_and_active_plugin_carveout(self) -> None:
        with tempfile.TemporaryDirectory() as directory, external_boundary():
            base = Path(directory)
            project = base / "project"
            plugin = base / ".claude/plugins/cache/dcness/dcness/1.0.0"
            project.mkdir()
            plugin.mkdir(parents=True)
            cases = [
                ("designer", "src/App.tsx", False),
                ("designer", "docs/ux.md", True),
                ("module-architect", str(plugin / "agents/module-architect/SKILL.md"), True),
                ("module-architect", str(plugin / "docs/plugin/terms.md"), True),
                ("module-architect", str(plugin / "docs/plugin/loop-procedure.md"), False),
                ("module-architect", str(plugin / "hooks/file-guard.sh"), False),
                ("module-architect", ".claude/harness-state/live.json", False),
            ]
            for agent, path, allowed in cases:
                with self.subTest(path=path):
                    reason = check_read_allowed(agent, path, cwd=project, plugin_root=str(plugin))
                    self.assertEqual(reason is None, allowed, reason)

    def test_stale_plugin_and_nested_infra_do_not_use_carveout(self) -> None:
        with tempfile.TemporaryDirectory() as directory, external_boundary():
            base = Path(directory)
            project = base / "project"
            active = base / ".claude/plugins/cache/dcness/dcness/2"
            stale = base / ".claude/plugins/cache/dcness/dcness/1"
            project.mkdir()
            active.mkdir(parents=True)
            stale.mkdir(parents=True)
            self.assertIsNotNone(
                check_read_allowed(
                    "module-architect", str(stale / "agents/a.md"), cwd=project, plugin_root=str(active)
                )
            )
            self.assertIsNotNone(
                check_read_allowed(
                    "module-architect",
                    str(active / "agents/a/.claude/history.jsonl"),
                    cwd=project,
                    plugin_root=str(active),
                )
            )


class BashPathContractTests(unittest.TestCase):
    def test_write_target_extraction_is_table_driven(self) -> None:
        cases = [
            ("printf x > src/x.ts", ["src/x.ts"]),
            ("cat a | tee src/y.ts /dev/null", ["src/y.ts"]),
            ("cp source.ts src/copy.ts", ["src/copy.ts"]),
            ("rm -f src/a.ts src/b.ts", ["src/a.ts", "src/b.ts"]),
            ("sed -i '' s/x/y/ src/a.ts", ["src/a.ts"]),
            ("git status && cat README.md", []),
            ("printf x > /dev/null", []),
        ]
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(extract_bash_paths(command), expected)

    def test_multiple_segments_are_deduplicated(self) -> None:
        self.assertEqual(
            extract_bash_paths("printf x > src/x.ts; tee src/x.ts < input"),
            ["src/x.ts"],
        )


class ExternalMutationContractTests(unittest.TestCase):
    def test_bash_mutation_matrix(self) -> None:
        cases = [
            ("git push origin main", True),
            ("sudo -E git push", True),
            ("bash -lc 'gh pr merge 12'", True),
            ("gh pr create --title x", True),
            ("gh issue comment 12 --body x", True),
            ("gh api repos/o/r/issues -f title=x", True),
            ("gh api repos/o/r -X POST", True),
            ("dcness-helper end-run", True),
            ("bash scripts/pr-finalize.sh 12", True),
            ("git commit -m ok", False),
            ("gh pr view 12", False),
            ("gh issue list", False),
            ("gh api repos/o/r -X GET", False),
            ("dcness-helper run-dir", False),
            ("echo dcness-helper end-run", False),
        ]
        for command, blocked in cases:
            with self.subTest(command=command):
                reason = check_bash_mutation(command)
                self.assertEqual(reason is not None, blocked, reason)

    def test_github_mcp_matrix(self) -> None:
        cases = [
            ("mcp__github__merge_pull_request", True),
            ("mcp__github__push_files", True),
            ("mcp__github__get_pull_request", False),
            ("mcp__github__list_issues", False),
            ("mcp__github__update_issue", False),
            ("mcp__other__mutate", False),
        ]
        for tool, blocked in cases:
            with self.subTest(tool=tool):
                self.assertEqual(check_github_mcp_mutation(tool) is not None, blocked)


if __name__ == "__main__":
    unittest.main()

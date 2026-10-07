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
    unresolved_bash_python_writes,
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

    def test_impl_task_scope_opens_nonstandard_path_but_not_hard_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory, external_boundary():
            root = Path(directory)
            scope = ("gradlew", "gradle/libs.versions.toml", "custom/**/*.kt")

            self.assertIsNotNone(
                check_write_allowed("build-worker", "gradlew", cwd=root)
            )
            self.assertIsNone(
                check_write_allowed(
                    "build-worker",
                    "gradlew",
                    cwd=root,
                    task_scope_paths=scope,
                )
            )
            self.assertIsNone(
                check_write_allowed(
                    "build-worker",
                    "custom/app/Main.kt",
                    cwd=root,
                    task_scope_paths=scope,
                )
            )
            self.assertIsNotNone(
                check_write_allowed(
                    "build-worker",
                    "custom/app/Nested.kt",
                    cwd=root,
                    task_scope_paths=("custom/*.kt",),
                )
            )
            for protected in ("hooks/file-guard.sh", ".dcness/boundary.json", "../outside.kt"):
                with self.subTest(protected=protected):
                    self.assertIsNotNone(
                        check_write_allowed(
                            "build-worker",
                            protected,
                            cwd=root,
                            task_scope_paths=scope + (protected,),
                        )
                    )

    def test_impl_task_scope_cannot_open_write_zero_agent(self) -> None:
        with tempfile.TemporaryDirectory() as directory, external_boundary():
            root = Path(directory)
            reason = check_write_allowed(
                "impl-validator",
                "custom/report.md",
                cwd=root,
                task_scope_paths=("custom/report.md",),
            )

            self.assertIsNotNone(reason)
            self.assertIn("write-zero", reason or "")


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

    def test_linked_worktree_uses_its_local_boundary_from_a_subdirectory(self) -> None:
        git_identity = (
            "-c",
            "user.name=dcness-test",
            "-c",
            "user.email=dcness-test@example.invalid",
        )
        with tempfile.TemporaryDirectory() as main_dir, tempfile.TemporaryDirectory() as worktree_dir:
            main = Path(main_dir)
            subprocess.run(["git", "init", "-q"], cwd=main, check=True)
            subprocess.run(
                ["git", *git_identity, "commit", "--allow-empty", "-q", "-m", "init"],
                cwd=main,
                check=True,
            )
            worktree = Path(worktree_dir) / "linked"
            subprocess.run(
                ["git", "worktree", "add", "-q", "-b", "boundary-fixture", str(worktree)],
                cwd=main,
                check=True,
            )
            config = worktree / ".dcness/boundary.json"
            config.parent.mkdir()
            config.write_text(
                json.dumps({"build-worker": {"add": [r"(^|/)custom-pkg/"]}}),
                encoding="utf-8",
            )
            boundary._BOUNDARY_ROOT_CACHE.clear()
            nested = worktree / "services/api"
            nested.mkdir(parents=True)
            with external_boundary():
                self.assertIsNone(
                    check_write_allowed("build-worker", "custom-pkg/x.go", cwd=nested)
                )


class ReadBoundaryTests(unittest.TestCase):
    def test_read_is_limited_only_by_agent_specific_deny(self) -> None:
        with tempfile.TemporaryDirectory() as directory, external_boundary():
            base = Path(directory)
            project = base / "project"
            plugin = base / ".claude/plugins/cache/dcness/dcness/1.0.0"
            stale = base / ".claude/plugins/cache/dcness/dcness/0.9.0"
            project.mkdir()
            plugin.mkdir(parents=True)
            cases = [
                ("designer", "src/App.tsx", False),
                ("designer", "docs/ux.md", True),
                ("module-architect", str(plugin / "agents/module-architect/SKILL.md"), True),
                ("module-architect", str(plugin / "docs/plugin/terms.md"), True),
                ("module-architect", str(plugin / "docs/plugin/loop-procedure.md"), True),
                ("module-architect", str(plugin / "hooks/file-guard.sh"), True),
                ("module-architect", str(stale / "agents/a.md"), True),
                ("module-architect", str(base / ".claude/history.jsonl"), True),
                ("module-architect", ".claude/harness-state/live.json", True),
                ("impl-validator", ".claude/worktrees/task/acceptance-result.json", True),
                ("impl-validator", "harness/agent_boundary.py", True),
                ("impl-validator", "skills/impl/impl-routing.md", True),
                ("impl-validator", "CLAUDE.md", True),
                ("impl-validator", ".dcness/boundary.json", True),
            ]
            for agent, path, allowed in cases:
                with self.subTest(path=path):
                    reason = check_read_allowed(agent, path, cwd=project, plugin_root=str(plugin))
                    self.assertEqual(reason is None, allowed, reason)

    def test_dot_claude_is_readable_but_still_not_writable(self) -> None:
        paths = (
            ".claude/settings.json",
            ".claude/harness-state/live.json",
            ".claude/worktrees/task/acceptance-result.json",
        )
        with tempfile.TemporaryDirectory() as directory, external_boundary():
            root = Path(directory)
            for agent in ("build-worker", "impl-validator", "module-architect"):
                for path in paths:
                    with self.subTest(agent=agent, path=path):
                        self.assertIsNone(check_read_allowed(agent, path, cwd=root))
                        self.assertIsNotNone(check_write_allowed(agent, path, cwd=root))

    def test_agent_deny_uses_plugin_relative_path_for_plugin_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as directory, external_boundary():
            base = Path(directory)
            project = base / "project"
            plugin = base / "src/dcness"
            project.mkdir()
            plugin.mkdir(parents=True)
            instruction = plugin / "docs/plugin/agents/designer/designer-agent.md"
            self.assertIsNone(
                check_read_allowed("designer", str(instruction), cwd=project, plugin_root=str(plugin))
            )
            self.assertIsNotNone(
                check_read_allowed(
                    "designer", str(plugin / "agents/designer/src/a.ts"), cwd=project, plugin_root=str(plugin)
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
            ("pytest tests/ 2>&1 | tail -20", []),
            ("echo warn >&2", []),
            ("echo x > 1", ["1"]),
            ("cmd >& out.log", ["out.log"]),
            ("cmd 2> err.log", ["err.log"]),
            # `\` 줄 연속은 명령 경계가 아니다.
            ("sed -i '' \\\n  's/x/y/' \\\n  hooks/evil.sh", ["hooks/evil.sh"]),
            ("printf x \\\n  > src/x.ts", ["src/x.ts"]),
        ]
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(extract_bash_paths(command), expected)

    def test_multiple_segments_are_deduplicated(self) -> None:
        self.assertEqual(
            extract_bash_paths("printf x > src/x.ts; tee src/x.ts < input"),
            ["src/x.ts"],
        )

    def test_python_file_writes_are_write_targets(self) -> None:
        cases = [
            (
                "python3 - <<'EOF'\np='src/a.kt'\ns=open(p).read()\n"
                "open(p,'w').write(s.replace('a','b'))\nEOF",
                ["src/a.kt"],
            ),
            ("python3 -c \"open('src/a.kt','w').write('x')\"", ["src/a.kt"]),
            (
                "python3 - <<'EOF'\nfrom pathlib import Path\n"
                "Path('src/a.kt').write_text('x')\nEOF",
                ["src/a.kt"],
            ),
            (
                "cd /repo && python3 <<'EOF'\nimport pathlib\n"
                "root = pathlib.Path('src')\n(root / 'b.kt').write_bytes(b'x')\n"
                "with open('src/c.kt', mode='a') as f:\n    f.write('x')\nEOF",
                ["src/b.kt", "src/c.kt"],
            ),
            ("python3 -c \"import os; open(os.path.join('src', 'd.kt'), 'w')\"", ["src/d.kt"]),
            ("python3 -c \"from pathlib import Path; Path('src/e.kt').open('w')\"", ["src/e.kt"]),
            ("cat <<'EOF' | python3 -\nopen('src/f.kt','w')\nEOF", ["src/f.kt"]),
            ("python3 -u - <<'EOF'\nopen('src/g.kt','w')\nEOF", ["src/g.kt"]),
        ]
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(extract_bash_paths(command), expected)
                self.assertEqual(unresolved_bash_python_writes(command), [])

    def test_shell_variable_write_target_resolves_same_command_assignment(self) -> None:
        cases = [
            ("T=src/a.kt; sed -i '' -e 's/x/y/' \"$T\"", ["src/a.kt"]),
            ("export D=src && sed -i '' 's/x/y/' \"${D}/b.kt\"", ["src/b.kt"]),
            ("printf x > \"$UNSET\"", ["$UNSET"]),
            ("for T in a b; do sed -i '' s/x/y/ \"$T\"; done", ["$T"]),
            ("T=\"$HOME/a.kt\"; sed -i '' s/x/y/ \"$T\"", ["$T"]),
            ("T=src/a.kt; T=src/b.kt; sed -i '' s/x/y/ \"$T\"", ["src/b.kt"]),
            ("T=src/a.kt\nsed -i '' s/x/y/ \"$T\"", ["src/a.kt"]),
            ("T=$(mktemp); sed -i '' s/x/y/ \"$T\"", ["$T"]),
            # 실행 여부가 확정되지 않는 대입은 값으로 쓰지 않는다 — 원형 유지.
            ("T=hooks/evil.sh; false && T=src/a.ts; printf x > \"$T\"", ["$T"]),
            ("T=hooks/evil.sh; true || T=src/a.ts; printf x > \"$T\"", ["$T"]),
            ("T=hooks/evil.sh; (T=src/a.ts); printf x > \"$T\"", ["$T"]),
            ("T=hooks/evil.sh; if x; then T=src/a.ts; fi; printf x > \"$T\"", ["$T"]),
            ("T=hooks/evil.sh; T=src/a.ts | cat; printf x > \"$T\"", ["$T"]),
            # 백그라운드 대입은 부모 셸에 반영되지 않는다 — 붙은 연산자 토큰(`&\n`)도 같다.
            ("T=hooks/evil.sh; T=src/a.ts &\nprintf x > \"$T\"", ["$T"]),
            ("T=hooks/evil.sh; T=src/a.ts & printf x > \"$T\"", ["$T"]),
            ("T=src/a.ts &&\nprintf x > \"$T\"", ["src/a.ts"]),
            # 같은 segment 의 리다이렉션은 대입 전 값으로 확장된다.
            ("T=hooks/evil.sh; T=src/a.ts > \"$T\"", ["hooks/evil.sh"]),
            # 단어 분리·glob 결과가 하나로 확정되지 않는 값은 원형 유지.
            ("T='src/a.ts hooks/evil.sh'; rm $T", ["$T"]),
            ("T='src/*.ts'; rm $T", ["$T"]),
            ("T='~/a.ts'; rm $T", ["$T"]),
            # 인식하지 못한 형태로 다시 대입하면 이전 값을 쓰지 않는다.
            ("T=src/a.ts; declare -x T=hooks/evil.sh; printf x > \"$T\"", ["$T"]),
            ("T=src/a.ts; printf -v T hooks/evil.sh; printf x > \"$T\"", ["$T"]),
            ("T=src/a.ts; T+=.bak; printf x > \"$T\"", ["$T"]),
            ("T=src/a.ts; read T; printf x > \"$T\"", ["$T"]),
            ("T=src/a.ts; eval \"$CMD\"; printf x > \"$T\"", ["$T"]),
            # 작은따옴표·`\$` 안의 `$T` 는 확장되지 않는 글자다 — 값으로 바꾸지 않는다.
            ("T=src/a.ts; printf x > '$T'", ["$T"]),
            ("T=src/a.ts; printf x > \\$T", ["$T"]),
            ("T=src/a.ts; printf x > \"$T\"", ["src/a.ts"]),
        ]
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(extract_bash_paths(command), expected)

    def test_python_without_project_write_has_no_target(self) -> None:
        commands = [
            "python3 - <<'EOF'\np='src/a.kt'\nprint(open(p).read())\nEOF",
            "python3 -c \"print(open('src/a.kt', 'r').read())\"",
            "python3 -c \"open('/tmp/x.txt','w').write('src/send.py')\"",
            "python3 - <<'EOF'\nfrom pathlib import Path\nPath('/private/tmp/x/y.json').write_text('{}')\nEOF",
            "cat > notes.md <<'EOF'\nopen('src/a.kt','w')\nEOF",
            # python 이 표준입력을 프로그램이 아니라 데이터로 읽는 경우.
            "python3 -c 'import sys; print(sys.stdin.read())' <<'EOF'\nopen('src/a.kt','w')\nEOF",
            "python3 -m json.tool <<'EOF'\nopen('src/a.kt','w')\nEOF",
            "python3 tools/x.py <<'EOF'\nopen('src/a.kt','w')\nEOF",
            "cat <<'EOF' | python3 tools/x.py\nopen('src/a.kt','w')\nEOF",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertNotIn("src/a.kt", extract_bash_paths(command))
                self.assertFalse(
                    any(p.startswith(("/tmp", "/private/tmp")) for p in extract_bash_paths(command))
                )
                self.assertEqual(unresolved_bash_python_writes(command), [])

    def test_unresolvable_python_write_is_reported_not_guessed(self) -> None:
        cases = [
            "python3 -c \"import sys; open(sys.argv[1], 'w').write('x')\" src/a.kt",
            "python3 - <<'EOF'\nfor p in ['src/a.kt']:\n    open(p, 'w').write('x')\nEOF",
            "python3 - <<'EOF'\nopen(f'src/{name}.kt', 'w')\nEOF",
            "python3 - <<'EOF'\nopen('src/a.kt', 'w'\nEOF",
        ]
        for command in cases:
            with self.subTest(command=command):
                self.assertEqual(extract_bash_paths(command), [])
                self.assertNotEqual(unresolved_bash_python_writes(command), [])


class ExternalMutationContractTests(unittest.TestCase):
    def test_bash_mutation_matrix(self) -> None:
        cases = [
            ("git push origin main", True),
            ("sudo -E git push", True),
            ("bash -lc 'gh pr merge 12'", True),
            ("env -i GH_TOKEN=x gh issue create --title x", True),
            ("(git push origin main)", True),
            ("if true; then git push origin main; fi", True),
            ("nohup gh pr create --title x", True),
            ("command -- gh pr create --title x", True),
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
            ("sudo git status", False),
            ("(gh issue list)", False),
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

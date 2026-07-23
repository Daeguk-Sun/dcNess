"""Generated project-local TDD hook contract tests (#909)."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from harness.tdd_hooks import inspect_installation


ROOT = Path(__file__).resolve().parents[1]
TDD_HOOKS = ROOT / "scripts" / "dcness-tdd-hooks"
CENTRAL_TDD_GUARD = ROOT / "hooks" / "tdd-guard.sh"


def _run_hook(hook: Path, project: Path, file_path: Path) -> subprocess.CompletedProcess[str]:
    payload = {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(file_path)},
    }
    return subprocess.run(
        ["bash", str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=project,
        timeout=10,
        env={
            **os.environ,
            "CLAUDE_PLUGIN_ROOT": str(ROOT),
            "DCNESS_TDD_PLUGIN_ROOT": str(ROOT),
            "PYTHONPATH": str(ROOT),
        },
    )


def _run_hook_payload(
    hook: Path,
    project: Path,
    payload: dict,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=project,
        timeout=10,
        env={
            **os.environ,
            "CLAUDE_PLUGIN_ROOT": str(ROOT),
            "DCNESS_TDD_PLUGIN_ROOT": str(ROOT),
            "PYTHONPATH": str(ROOT),
        },
    )


def _run_central_guard(
    project: Path,
    file_path: Path,
    *,
    headless: bool = False,
) -> subprocess.CompletedProcess[str]:
    payload = {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(file_path)},
    }
    env = {
        **os.environ,
        "CLAUDE_PLUGIN_ROOT": str(ROOT),
        "DCNESS_FORCE_ENABLE": "1",
        "PYTHONPATH": str(ROOT),
    }
    if headless:
        env["DCNESS_HEADLESS_TDD_CHECK"] = "1"
    return subprocess.run(
        ["bash", str(CENTRAL_TDD_GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=project,
        timeout=10,
        env=env,
    )


class GeneratedTddHookContractTests(unittest.TestCase):
    def test_self_test_rejects_allow_all_hook_before_generation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            (project / "pyproject.toml").write_text("[project]\nname='demo'\n")
            (project / "src").mkdir()
            (project / "src" / "existing.py").write_text("def existing():\n    return 1\n")

            bad_hook = Path(td) / "allow-all.sh"
            bad_hook.write_text("#!/bin/sh\ncat >/dev/null\nexit 0\n", encoding="utf-8")
            bad_hook.chmod(0o755)

            result = subprocess.run(
                [
                    str(TDD_HOOKS),
                    "self-test",
                    "--project-root",
                    str(project),
                    "--platform",
                    "python",
                    "--hook-command",
                    f"bash {bad_hook}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("without_test", result.stderr)

    def test_ensure_generates_cc_then_codex_hooks_after_self_test(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "project with space"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            (project / "pyproject.toml").write_text("[project]\nname='demo'\n")
            (project / "src").mkdir()
            (project / "src" / "existing.py").write_text("def existing():\n    return 1\n")

            result = subprocess.run(
                [
                    str(TDD_HOOKS),
                    "ensure",
                    "--project-root",
                    str(project),
                    "--targets",
                    "cc,codex",
                    "--plugin-root",
                    str(ROOT),
                ],
                capture_output=True,
                text=True,
                timeout=20,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("cc: registered", result.stdout)
            self.assertIn("codex: registered", result.stdout)
            self.assertIn("commit-advisory:", result.stdout)

            config = json.loads(
                (project / ".dcness" / "tdd-hooks.json").read_text(encoding="utf-8")
            )
            self.assertEqual(config["platform"], "python")
            self.assertIn("test_candidate_templates", config)
            self.assertTrue(config["registered"]["cc"])
            self.assertTrue(config["registered"]["codex"])

            cc_settings = json.loads(
                (project / ".claude" / "settings.json").read_text(encoding="utf-8")
            )
            cc_hooks = cc_settings["hooks"]["PreToolUse"]
            self.assertTrue(any("dcness-tdd-guard.sh" in json.dumps(e) for e in cc_hooks))

            codex_hooks = json.loads(
                (project / ".codex" / "hooks.json").read_text(encoding="utf-8")
            )
            codex_pre = codex_hooks["hooks"]["PreToolUse"]
            self.assertTrue(
                any("apply_patch" in e.get("matcher", "") for e in codex_pre),
                codex_hooks,
            )

    def test_status_reports_generated_files_until_committed_to_git(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            (project / "pyproject.toml").write_text("[project]\nname='demo'\n")
            (project / "src").mkdir()
            (project / "src" / "existing.py").write_text("def existing():\n    return 1\n")

            subprocess.run(
                [
                    str(TDD_HOOKS),
                    "ensure",
                    "--project-root",
                    str(project),
                    "--targets",
                    "cc,codex",
                    "--plugin-root",
                    str(ROOT),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
            )

            report = inspect_installation(project)
            self.assertFalse(report["generated_files_committed"])
            self.assertFalse(report["linked_worktree"])
            self.assertFalse(report["generated_files_commit_required"])
            self.assertIn(".dcness/tdd-hooks.json", report["uncommitted_generated_files"])
            self.assertIn(".claude/settings.json", report["uncommitted_generated_files"])
            self.assertIn(".codex/hooks.json", report["uncommitted_generated_files"])

            subprocess.run(["git", "add", "."], cwd=project, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=dcness-test",
                    "-c",
                    "user.email=dcness@example.invalid",
                    "commit",
                    "-q",
                    "-m",
                    "bootstrap generated hooks",
                ],
                cwd=project,
                check=True,
            )

            committed_report = inspect_installation(project)
            self.assertTrue(committed_report["generated_files_committed"])
            self.assertFalse(committed_report["linked_worktree"])
            self.assertFalse(committed_report["generated_files_commit_required"])
            self.assertEqual(committed_report["uncommitted_generated_files"], [])

    def test_status_ignores_unrelated_user_settings_without_tdd_reference(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            (project / "pyproject.toml").write_text("[project]\nname='demo'\n")
            settings = project / ".claude" / "settings.json"
            settings.parent.mkdir()
            settings.write_text(
                json.dumps({"permissions": {"allow": ["Read(docs/**)"]}}),
                encoding="utf-8",
            )
            codex_hooks = project / ".codex" / "hooks.json"
            codex_hooks.parent.mkdir()
            codex_hooks.write_text(json.dumps({"hooks": {}}), encoding="utf-8")

            report = inspect_installation(project)

            self.assertEqual(report["generated_files"], [])
            self.assertTrue(report["generated_files_committed"])
            self.assertEqual(report["uncommitted_generated_files"], [])

    def test_ensure_refuses_malformed_cc_settings_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            (project / "pyproject.toml").write_text("[project]\nname='demo'\n")
            (project / "src").mkdir()
            (project / "src" / "existing.py").write_text("def existing():\n    return 1\n")
            settings = project / ".claude" / "settings.json"
            settings.parent.mkdir()
            original = '{"permissions": '
            settings.write_text(original, encoding="utf-8")

            result = subprocess.run(
                [
                    str(TDD_HOOKS),
                    "ensure",
                    "--project-root",
                    str(project),
                    "--targets",
                    "cc",
                    "--plugin-root",
                    str(ROOT),
                ],
                capture_output=True,
                text=True,
                timeout=20,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid JSON", result.stderr)
            self.assertEqual(settings.read_text(encoding="utf-8"), original)
            self.assertFalse((project / ".claude" / "hooks" / "dcness-tdd-guard.sh").exists())
            self.assertFalse((project / ".dcness" / "tdd-hooks.json").exists())

    def test_generated_python_hook_enforces_flat_project_without_source_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            (project / "pyproject.toml").write_text("[project]\nname='demo'\n")
            (project / "existing.py").write_text("def existing():\n    return 1\n")

            subprocess.run(
                [
                    str(TDD_HOOKS),
                    "ensure",
                    "--project-root",
                    str(project),
                    "--targets",
                    "cc",
                    "--plugin-root",
                    str(ROOT),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
            )

            hook = project / ".claude" / "hooks" / "dcness-tdd-guard.sh"
            no_test = project / "price.py"
            no_test.write_text("def price():\n    return 1\n", encoding="utf-8")
            denied = _run_hook(hook, project, no_test)
            self.assertEqual(denied.returncode, 2, denied.stderr)
            self.assertIn("price.py", denied.stderr)

    def test_ensure_uses_project_owned_config_for_unknown_platform(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            (project / "Cargo.toml").write_text("[package]\nname='demo'\nversion='0.1.0'\n")
            (project / "src").mkdir()
            (project / "src" / "lib.rs").write_text("pub fn existing() -> i32 { 1 }\n")
            (project / ".dcness").mkdir()
            (project / ".dcness" / "tdd-hooks.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "platform": "rust",
                        "source_roots": ["src"],
                        "impl_exts": [".rs"],
                        "test_candidate_templates": [
                            "tests/{stem}_test{ext}",
                            "{parent}/{stem}_test{ext}",
                        ],
                        "test_file_globs": [
                            "tests/**/*{ext}",
                            "**/*_test{ext}",
                        ],
                        "registered": {"cc": False, "codex": False},
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    str(TDD_HOOKS),
                    "ensure",
                    "--project-root",
                    str(project),
                    "--targets",
                    "cc",
                    "--plugin-root",
                    str(ROOT),
                ],
                capture_output=True,
                text=True,
                timeout=20,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("cc: registered", result.stdout)

            report = inspect_installation(project)
            self.assertEqual(report["platform"], "rust")
            self.assertTrue(report["cc_registered"])

            hook = project / ".claude" / "hooks" / "dcness-tdd-guard.sh"
            no_test = project / "src" / "price.rs"
            no_test.write_text("pub fn price() -> i32 { 1 }\n", encoding="utf-8")
            denied = _run_hook(hook, project, no_test)
            self.assertEqual(denied.returncode, 2, denied.stderr)
            self.assertIn("price.rs", denied.stderr)
            self.assertIn("tests/price_test.rs", denied.stderr)

            (project / "src" / "price.test.rs").write_text(
                "#[test]\nfn generic_name_only() { assert_eq!(1, 1); }\n",
                encoding="utf-8",
            )
            still_denied = _run_hook(hook, project, no_test)
            self.assertEqual(still_denied.returncode, 2, still_denied.stderr)

            (project / "tests").mkdir()
            (project / "tests" / "price_test.rs").write_text(
                "#[test]\nfn price_contract() { assert_eq!(1, 1); }\n",
                encoding="utf-8",
            )
            allowed = _run_hook(hook, project, no_test)
            self.assertEqual(allowed.returncode, 0, allowed.stderr)

    def test_status_does_not_trust_stale_registered_flags_without_hook_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            (project / "pyproject.toml").write_text("[project]\nname='demo'\n")
            (project / ".dcness").mkdir()
            (project / ".dcness" / "tdd-hooks.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "platform": "python",
                        "source_roots": ["."],
                        "impl_exts": [".py"],
                        "registered": {"cc": True, "codex": True},
                    }
                ),
                encoding="utf-8",
            )

            report = inspect_installation(project)
            self.assertFalse(report["cc_registered"])
            self.assertFalse(report["codex_registered"])

    def test_generated_python_hook_enforces_contract_cases(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            (project / "pyproject.toml").write_text("[project]\nname='demo'\n")
            (project / "src").mkdir()
            (project / "src" / "existing.py").write_text("def existing():\n    return 1\n")

            subprocess.run(
                [
                    str(TDD_HOOKS),
                    "ensure",
                    "--project-root",
                    str(project),
                    "--targets",
                    "cc",
                    "--plugin-root",
                    str(ROOT),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
            )

            hook = project / ".claude" / "hooks" / "dcness-tdd-guard.sh"
            no_test = project / "src" / "price.py"
            no_test.write_text("def price():\n    return 1\n", encoding="utf-8")
            denied = _run_hook(hook, project, no_test)
            self.assertEqual(denied.returncode, 2, denied.stderr)
            self.assertIn("TDD GUARD", denied.stderr)
            self.assertIn("tdd-exempt: <사유>", denied.stderr)

            (project / "tests").mkdir()
            (project / "tests" / "test_price.py").write_text(
                "from src.price import price\n\n\ndef test_price():\n    assert price() == 1\n",
                encoding="utf-8",
            )
            allowed = _run_hook(hook, project, no_test)
            self.assertEqual(allowed.returncode, 0, allowed.stderr)

            test_file = project / "tests" / "test_new_contract.py"
            test_file.write_text("def test_new_contract():\n    assert True\n", encoding="utf-8")
            test_allowed = _run_hook(hook, project, test_file)
            self.assertEqual(test_allowed.returncode, 0, test_allowed.stderr)

    def test_generated_hook_allows_existing_file_with_tdd_exempt_reason(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            (project / "pyproject.toml").write_text("[project]\nname='demo'\n")
            (project / "src").mkdir()
            (project / "src" / "existing.py").write_text("def existing():\n    return 1\n")

            subprocess.run(
                [
                    str(TDD_HOOKS),
                    "ensure",
                    "--project-root",
                    str(project),
                    "--targets",
                    "cc",
                    "--plugin-root",
                    str(ROOT),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
            )

            hook = project / ".claude" / "hooks" / "dcness-tdd-guard.sh"
            exempt = project / "src" / "dto.py"
            exempt.write_text(
                "# tdd-exempt: dataclass shape only\n"
                "class Dto:\n"
                "    pass\n",
                encoding="utf-8",
            )

            allowed = _run_hook(hook, project, exempt)

            self.assertEqual(allowed.returncode, 0, allowed.stderr)

    def test_generated_hook_rejects_empty_tdd_exempt_reason(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            (project / "pyproject.toml").write_text("[project]\nname='demo'\n")
            (project / "src").mkdir()
            (project / "src" / "existing.py").write_text("def existing():\n    return 1\n")

            subprocess.run(
                [
                    str(TDD_HOOKS),
                    "ensure",
                    "--project-root",
                    str(project),
                    "--targets",
                    "cc",
                    "--plugin-root",
                    str(ROOT),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
            )

            hook = project / ".claude" / "hooks" / "dcness-tdd-guard.sh"
            empty_reason = project / "src" / "dto.py"
            empty_reason.write_text(
                "# tdd-exempt:   \n"
                "class Dto:\n"
                "    pass\n",
                encoding="utf-8",
            )

            denied = _run_hook(hook, project, empty_reason)

            self.assertEqual(denied.returncode, 2, denied.stderr)

    def test_generated_hook_allows_write_payload_with_tdd_exempt_reason(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            (project / "pyproject.toml").write_text("[project]\nname='demo'\n")
            (project / "src").mkdir()
            (project / "src" / "existing.py").write_text("def existing():\n    return 1\n")

            subprocess.run(
                [
                    str(TDD_HOOKS),
                    "ensure",
                    "--project-root",
                    str(project),
                    "--targets",
                    "cc",
                    "--plugin-root",
                    str(ROOT),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
            )

            hook = project / ".claude" / "hooks" / "dcness-tdd-guard.sh"
            target = project / "src" / "payload_dto.py"
            payload = {
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(target),
                    "content": (
                        "# tdd-exempt: generated dataclass only\n"
                        "class PayloadDto:\n"
                        "    pass\n"
                    ),
                },
            }

            allowed = _run_hook_payload(hook, project, payload)

            self.assertEqual(allowed.returncode, 0, allowed.stderr)

    def test_generated_hook_allows_apply_patch_add_file_with_tdd_exempt_reason(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            (project / "pyproject.toml").write_text("[project]\nname='demo'\n")
            (project / "src").mkdir()
            (project / "src" / "existing.py").write_text("def existing():\n    return 1\n")

            subprocess.run(
                [
                    str(TDD_HOOKS),
                    "ensure",
                    "--project-root",
                    str(project),
                    "--targets",
                    "codex",
                    "--plugin-root",
                    str(ROOT),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
            )

            hook = project / ".codex" / "hooks" / "dcness-tdd-guard.sh"
            payload = {
                "tool_name": "apply_patch",
                "tool_input": {
                    "patch": (
                        "*** Begin Patch\n"
                        "*** Add File: src/codex_dto.py\n"
                        "+# tdd-exempt: generated DTO only\n"
                        "+class CodexDto:\n"
                        "+    pass\n"
                        "*** End Patch\n"
                    )
                },
            }

            allowed = _run_hook_payload(hook, project, payload)

            self.assertEqual(allowed.returncode, 0, allowed.stderr)

    def test_central_tdd_guard_delegates_to_generated_hook_for_headless_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            (project / "pyproject.toml").write_text("[project]\nname='demo'\n")
            (project / "src").mkdir()
            (project / "src" / "existing.py").write_text("def existing():\n    return 1\n")

            subprocess.run(
                [
                    str(TDD_HOOKS),
                    "ensure",
                    "--project-root",
                    str(project),
                    "--targets",
                    "cc",
                    "--plugin-root",
                    str(ROOT),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
            )

            target = project / "src" / "headless_contract.py"
            target.write_text("def headless_contract():\n    return 1\n", encoding="utf-8")

            result = _run_central_guard(project, target, headless=True)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("headless_contract", result.stderr)

    def test_central_tdd_guard_skips_project_hook_during_interactive_cc_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            (project / "pyproject.toml").write_text("[project]\nname='demo'\n")
            (project / "src").mkdir()
            (project / "src" / "existing.py").write_text("def existing():\n    return 1\n")

            subprocess.run(
                [
                    str(TDD_HOOKS),
                    "ensure",
                    "--project-root",
                    str(project),
                    "--targets",
                    "cc",
                    "--plugin-root",
                    str(ROOT),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
            )

            target = project / "src" / "interactive_contract.py"
            target.write_text("def interactive_contract():\n    return 1\n", encoding="utf-8")

            central = _run_central_guard(project, target)
            self.assertEqual(central.returncode, 0, central.stderr)
            self.assertNotIn("TDD GUARD", central.stderr)

            project_hook = project / ".claude" / "hooks" / "dcness-tdd-guard.sh"
            generated = _run_hook(project_hook, project, target)
            self.assertEqual(generated.returncode, 2, generated.stderr)
            self.assertIn("interactive_contract", generated.stderr)

    def test_ensure_skips_empty_project_without_registering_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            result = subprocess.run(
                [
                    str(TDD_HOOKS),
                    "ensure",
                    "--project-root",
                    str(project),
                    "--targets",
                    "cc,codex",
                    "--plugin-root",
                    str(ROOT),
                ],
                capture_output=True,
                text=True,
                timeout=10,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("skip: empty_or_unknown_project", result.stdout)
            self.assertFalse((project / ".claude" / "settings.json").exists())
            self.assertFalse((project / ".codex" / "hooks.json").exists())


class GeneratedTddHookDocsTests(unittest.TestCase):
    def test_public_docs_keep_contract_before_generation_order(self) -> None:
        init_skill = (ROOT / "commands" / "init-dcness.md").read_text(encoding="utf-8")
        hooks_doc = (ROOT / "docs" / "plugin" / "hooks.md").read_text(encoding="utf-8")
        impl_skill = (ROOT / "skills" / "impl" / "SKILL.md").read_text(encoding="utf-8")

        for text in (init_skill, hooks_doc):
            with self.subTest(text=text[:20]):
                self.assertIn("TDD 계약", text)
                self.assertIn("self-test", text)
                self.assertIn("test_candidate_templates", text)
        self.assertNotIn("test_candidate_templates", impl_skill)
        self.assertIn("TDD 게이트는 삭제하지 않는다", impl_skill)

        ordered = [
            "TDD 계약",
            "CC",
            "Codex",
        ]
        cursor = -1
        for needle in ordered:
            next_pos = init_skill.find(needle, cursor + 1)
            self.assertGreater(next_pos, cursor, textwrap.shorten(init_skill, width=200))
            cursor = next_pos

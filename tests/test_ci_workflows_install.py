"""/init-dcness CI workflow copy install (#1243) + lint-build-test workflow (#1244).

설치된 workflow 가 외부 저장소 action 없이 사용자 저장소 체크아웃만으로 도는지,
중립 명명 설치 산출물에 하네스 이름이 남지 않는지, 플랫폼별 lint-build-test
workflow 가 판정 결과에 따라 설치·skip 되는지 검증한다.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from harness import ci_workflows, tdd_hooks
from tests.test_design_variants_generator import _screen, _ux_flow

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates" / "github-workflows"
WRAPPER = ROOT / "scripts" / "dcness-ci-workflows"
NODE = shutil.which("node")
ACTIONLINT = shutil.which("actionlint")
PR_CHECKS = (
    "git-naming-validation",
    "pr-body-validation",
    "doc-path-integrity",
    "doc-sync",
)
ALL_CHECKS = PR_CHECKS + ("github-project-lifecycle", "lint-build-test")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")


def _seed_android(root: Path) -> None:
    _write(root / "settings.gradle.kts", 'include(":app")\n')
    _write(root / "gradlew", "#!/bin/sh\n")
    _write(root / "app" / "build.gradle.kts", "plugins {}\n")


def _run_wrapper(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(WRAPPER), *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


class TemplateContractTests(unittest.TestCase):
    def test_templates_use_only_official_actions(self) -> None:
        templates = sorted(TEMPLATES.rglob("*.yml"))
        self.assertTrue(templates)
        for template in templates:
            text = template.read_text(encoding="utf-8")
            with self.subTest(template=template.name):
                self.assertNotIn("Daeguk-Sun", text)
                for ref in re.findall(r"uses:\s*([^\s#]+)", text):
                    self.assertTrue(ref.startswith("actions/"), ref)

    def test_every_check_has_template_and_copied_scripts(self) -> None:
        for check in ALL_CHECKS:
            spec = ci_workflows.CHECKS[check]
            with self.subTest(check=check):
                for rel in spec.template_sources():
                    self.assertTrue((ROOT / rel).is_file(), rel)
                for rel in spec.support_files:
                    self.assertTrue((ROOT / rel).is_file(), rel)
                if spec.support_files:
                    # workflow 는 복사된 사본만 실행한다.
                    self.assertIn(f"{ci_workflows.INSTALL_ROOT}/scripts/", _workflow_texts(check))

    def test_copied_scripts_have_closed_runtime_dependencies(self) -> None:
        """복사본이 plugin 원본 경로를 런타임에 읽으면 사용자 repo CI 에서 ENOENT 로 깨진다."""
        for check, spec in ci_workflows.CHECKS.items():
            copied = set(spec.support_files)
            with self.subTest(check=check):
                for rel in spec.support_files:
                    for dep in _runtime_dependencies(rel):
                        self.assertIn(dep, copied, f"{rel} -> {dep}")

    def test_neutral_templates_and_scripts_have_no_harness_name(self) -> None:
        for check, spec in ci_workflows.CHECKS.items():
            if not spec.neutral_ok:
                continue
            with self.subTest(check=check):
                self.assertNotRegex(_workflow_texts(check), re.compile("dcness", re.I))
                for rel in spec.support_files:
                    text = (ROOT / rel).read_text(encoding="utf-8")
                    self.assertNotRegex(text, re.compile("dcness", re.I), rel)


class DocContractTests(unittest.TestCase):
    def test_docs_describe_copy_install_and_update_path(self) -> None:
        reference = (ROOT / "docs" / "plugin" / "init-dcness.md").read_text(encoding="utf-8")
        runbook = (ROOT / "commands" / "init-dcness.md").read_text(encoding="utf-8")
        hooks = (ROOT / "docs" / "plugin" / "hooks.md").read_text(encoding="utf-8")
        snippets = reference.split("## CI Workflow Snippets", 1)[1].split("\n## ", 1)[0]

        for text in (reference, runbook, hooks):
            self.assertNotIn("composite action 을 호출", text)
        self.assertIn(".github/ci-checks/", snippets)
        self.assertIn("/init-dcness` 를 재실행", snippets)
        self.assertIn("--neutral-naming", snippets)
        self.assertIn("### lint-build-test.yml", snippets)
        self.assertIn("skip lint-build-test", snippets)
        self.assertIn("dcness-ci-workflows\" install", runbook)
        self.assertNotIn('cp "$PLUGIN_ROOT/templates/github-workflows', runbook)
        self.assertIn("lint-build-test", runbook)


_JS_RELATIVE = re.compile(
    r"""(?:from\s+|import\s*\(\s*|new URL\(\s*)['"](\.{1,2}/[^'"]+)['"]"""
)
_JS_PLUGIN_ROOT_JOIN = re.compile(r"join\(\s*PLUGIN_ROOT\s*,((?:\s*'[^']+'\s*,?)+)\)")
_PY_HARNESS_IMPORT = re.compile(r"^(?:from|import)\s+harness\.(\w+)", re.M)
_SH_PY_MODULE = re.compile(r"python3?\s+-m\s+harness\.(\w+)")


def _runtime_dependencies(rel: str) -> set[str]:
    """plugin 안의 다른 파일을 가리키는 import·런타임 경로 참조 (plugin 상대 경로)."""
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    deps: set[str] = set()
    if path.suffix == ".mjs":
        for spec in _JS_RELATIVE.findall(text):
            deps.add((path.parent / spec).resolve().relative_to(ROOT).as_posix())
        for group in _JS_PLUGIN_ROOT_JOIN.findall(text):
            target = ROOT.joinpath(*re.findall(r"'([^']+)'", group))
            # 디렉터리를 가리키면 그 안의 파일을 런타임에 읽으므로 전부 필요하다.
            files = sorted(target.rglob("*")) if target.is_dir() else [target]
            deps.update(f.relative_to(ROOT).as_posix() for f in files if f.is_file())
    elif path.suffix == ".py":
        # 함수 안 lazy import 는 CI 가 쓰지 않는 명령 경로라 module 수준 import 만 본다.
        deps.update(f"harness/{name}.py" for name in _PY_HARNESS_IMPORT.findall(text))
    else:
        deps.update(f"harness/{name}.py" for name in _SH_PY_MODULE.findall(text))
    return deps


def _workflow_texts(check: str) -> str:
    spec = ci_workflows.CHECKS[check]
    return "\n".join(
        (ROOT / rel).read_text(encoding="utf-8") for rel in spec.template_sources()
    )


class InstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _install(self, checks=PR_CHECKS, **kwargs):
        return ci_workflows.install(self.root, list(checks), **kwargs)

    def test_installs_workflows_and_scripts_without_external_uses(self) -> None:
        result = self._install()

        self.assertEqual(result.skipped, [])
        for check in PR_CHECKS:
            wf = self.root / ".github" / "workflows" / f"{check}.yml"
            self.assertTrue(wf.is_file(), wf)
            self.assertIn(f".github/workflows/{check}.yml", result.written)
            for ref in re.findall(r"uses:\s*([^\s#]+)", wf.read_text(encoding="utf-8")):
                self.assertTrue(ref.startswith("actions/"), ref)
        for rel in ci_workflows.CHECKS["doc-sync"].support_files:
            self.assertTrue((self.root / ci_workflows.INSTALL_ROOT / rel).is_file(), rel)
        runner = self.root / ci_workflows.INSTALL_ROOT / "scripts" / "dcness-story-runner"
        self.assertTrue(os.access(runner, os.X_OK))

    def test_reinstall_is_idempotent_overwrite(self) -> None:
        self._install()
        wf = self.root / ".github" / "workflows" / "git-naming-validation.yml"
        wf.write_text("stale\n", encoding="utf-8")
        self._install()
        self.assertEqual(
            wf.read_text(encoding="utf-8"),
            (TEMPLATES / "git-naming-validation.yml").read_text(encoding="utf-8"),
        )

    @unittest.skipUnless(NODE, "node not installed")
    def test_installed_scripts_run_offline_from_user_repo(self) -> None:
        self._install()
        scripts = self.root / ci_workflows.INSTALL_ROOT / "scripts"

        def node(*args: str, stdin: str | None = None) -> int:
            return subprocess.run(
                [NODE, *args],
                cwd=self.root,
                input=stdin,
                capture_output=True,
                text=True,
            ).returncode

        naming = str(scripts / "check_git_naming.mjs")
        self.assertEqual(node(naming, "--branch", "feature/add_login"), 0)
        self.assertEqual(node(naming, "--branch", "my-random-branch"), 1)
        self.assertEqual(node(naming, "--title", "[feature] 로그인 추가"), 0)
        self.assertEqual(node(naming, "--title", "add login"), 1)

        body = str(scripts / "check_pr_body.mjs")
        self.assertEqual(node(body, "--stdin", stdin="Closes #12\n"), 0)
        self.assertEqual(node(body, "--stdin", stdin="no trailer\n"), 1)

        _write(self.root / "CLAUDE.md", "Read `docs/missing.md`.\n")
        doc_path = str(scripts / "check_doc_path_integrity.mjs")
        self.assertEqual(node(doc_path), 1)
        _write(self.root / "docs" / "missing.md", "# now present\n")
        self.assertEqual(node(doc_path), 0)

        self.assertEqual(node(str(scripts / "aggregate_index_map.mjs"), "--check"), 0)

    @unittest.skipUnless(NODE, "node not installed")
    def test_installed_design_audit_runs_copied_story_runner(self) -> None:
        self._install()
        _write(self.root / "docs" / "index.md", "# Index\n")
        _write(self.root / "docs" / "epics" / "epic-01-alpha" / "stories.md", "# Stories\n")
        _write(self.root / "docs" / "epics" / "epic-01-alpha" / "architecture.md", "# Arch\n")
        impl = self.root / "docs" / "epics" / "epic-01-alpha" / "impl"
        for name, story, index, deps in (
            ("01-auth", 1, "1/2", "[]"),
            ("02-story-two", 2, "1/1", "[01-auth]"),
            ("03-story-one", 1, "2/2", "[02-story-two]"),
        ):
            _write(
                impl / f"{name}.md",
                f"---\nstory: {story}\ntask_index: {index}\ndepends_on: {deps}\n---\n# task\n",
            )
        audit = self.root / ci_workflows.INSTALL_ROOT / "scripts" / "check_design_artifact_structure.mjs"
        proc = subprocess.run(
            [NODE, str(audit), "--json"],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        # 순서 위반을 copied story runner 가 실제로 판정해야 한다 (import 실패 진단이 아님).
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertNotIn("ModuleNotFoundError", proc.stdout + proc.stderr)
        self.assertIn("impl-story-non-contiguous", proc.stdout)

    @unittest.skipUnless(NODE, "node not installed")
    def test_installed_design_variant_checks_run_without_plugin(self) -> None:
        """doc-sync workflow 의 design-variants 단계를 복사본으로 재현한다."""
        self._install(["doc-sync"])
        design = self.root / "docs" / "design-variants"
        shutil.copytree(ROOT / "templates" / "design-variants", design)
        _write(self.root / "CLAUDE.md", "# Project\n")
        _write(self.root / "docs" / "index.md", "# Documentation\n")
        _write(self.root / "docs" / "epics" / "epic-ui" / "ux-flow.md", _ux_flow())
        for screen_id in ("home", "review", "detail"):
            _write(
                design / "screens" / f"{screen_id}.html",
                _screen(screen_id, [("default", "state=default")]),
            )
        generators = ("build-journey-boards.mjs", "build-screen-states.mjs", "build-design-index.mjs")
        for name in generators:
            # 사용자가 로컬에서 plugin 원본으로 파생 보드를 만든 상태.
            subprocess.run(
                [NODE, str(ROOT / "scripts" / "design" / name), "--project-root", "."],
                cwd=self.root,
                check=True,
                capture_output=True,
            )
        copied = self.root / ci_workflows.INSTALL_ROOT / "scripts" / "design"
        for name in generators:
            proc = subprocess.run(
                [NODE, str(copied / name), "--project-root", ".", "--check"],
                cwd=self.root,
                capture_output=True,
                text=True,
            )
            with self.subTest(generator=name):
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertNotIn("ENOENT", proc.stderr)
                self.assertNotIn("ENGINE WARNING", proc.stderr)

    def test_neutral_naming_install_has_no_harness_name(self) -> None:
        _seed_android(self.root)
        result = self._install(ALL_CHECKS, neutral_naming=True)

        skipped = dict(result.skipped)
        self.assertIn("doc-sync", skipped)
        self.assertIn("github-project-lifecycle", skipped)
        self.assertTrue(result.written)
        for rel in result.written:
            with self.subTest(path=rel):
                self.assertNotRegex(rel, re.compile("dcness", re.I))
                text = (self.root / rel).read_text(encoding="utf-8")
                self.assertNotRegex(text, re.compile("dcness", re.I))
        grep = subprocess.run(
            ["grep", "-ril", "dcness", ".github"],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        self.assertEqual(grep.stdout, "")

    def test_lint_build_test_android_installs_platform_commands(self) -> None:
        _seed_android(self.root)
        result = self._install(["lint-build-test"])

        self.assertEqual(result.skipped, [])
        wf = self.root / ".github" / "workflows" / "lint-build-test.yml"
        self.assertEqual(result.written, [".github/workflows/lint-build-test.yml"])
        text = wf.read_text(encoding="utf-8")
        self.assertIn("pull_request:", text)
        for task in (":app:lintDebug", ":app:assembleDebug", ":app:testDebugUnitTest"):
            self.assertIn(task, text)
        self.assertLess(text.index("lintDebug"), text.index("assembleDebug"))
        self.assertLess(text.index("assembleDebug"), text.index("testDebugUnitTest"))
        self.assertIn("cache: gradle", text)
        self.assertNotRegex(text, re.compile("dcness", re.I))

    def test_copied_check_scripts_do_not_change_platform_detection(self) -> None:
        _seed_android(self.root)
        self._install(["doc-sync"])

        self.assertEqual(tdd_hooks.detect_platform(self.root), "android")
        result = self._install(["lint-build-test"])
        self.assertEqual(result.written, [".github/workflows/lint-build-test.yml"])

    @unittest.skipUnless(ACTIONLINT, "actionlint not installed")
    def test_installed_workflows_pass_actionlint(self) -> None:
        _seed_android(self.root)
        self._install(ALL_CHECKS)
        workflows = sorted((self.root / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(len(workflows), len(ALL_CHECKS))
        proc = subprocess.run(
            [ACTIONLINT, "-shellcheck=", *map(str, workflows)],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_lint_build_test_skips_when_platform_undetected(self) -> None:
        result = self._install(["lint-build-test"])

        self.assertEqual(result.written, [])
        self.assertEqual([check for check, _ in result.skipped], ["lint-build-test"])
        self.assertIn("플랫폼", result.skipped[0][1])
        self.assertFalse((self.root / ".github" / "workflows" / "lint-build-test.yml").exists())

    def test_lint_build_test_skips_platform_without_template(self) -> None:
        _write(self.root / "pyproject.toml", "[project]\nname = 'x'\n")
        result = self._install(["lint-build-test"])

        self.assertEqual(result.written, [])
        self.assertIn("python", result.skipped[0][1])

    def test_lint_build_test_skips_android_without_app_module(self) -> None:
        _write(self.root / "settings.gradle.kts", "\n")
        _write(self.root / "gradlew", "#!/bin/sh\n")
        result = self._install(["lint-build-test"])

        self.assertEqual(result.written, [])
        self.assertIn("app/build.gradle", result.skipped[0][1])

    def test_explicit_platform_overrides_detection(self) -> None:
        _write(self.root / "pyproject.toml", "[project]\nname = 'x'\n")
        _write(self.root / "gradlew", "#!/bin/sh\n")
        _write(self.root / "app" / "build.gradle", "\n")
        result = self._install(["lint-build-test"], platform="android")

        self.assertEqual(result.written, [".github/workflows/lint-build-test.yml"])

    def test_unknown_check_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._install(["nope"])

    def test_cli_prints_written_paths_and_skip_reasons(self) -> None:
        proc = _run_wrapper(
            "install",
            "--project-root",
            str(self.root),
            "--checks",
            "git-naming-validation,lint-build-test",
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            proc.stdout.split(),
            [
                ".github/workflows/git-naming-validation.yml",
                f"{ci_workflows.INSTALL_ROOT}/scripts/check_git_naming.mjs",
            ],
        )
        self.assertIn("skip lint-build-test:", proc.stderr)

    def test_cli_rejects_unknown_check(self) -> None:
        proc = _run_wrapper("install", "--project-root", str(self.root), "--checks", "nope")
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()

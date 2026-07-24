"""Epic-boundary Codebase Sanity contracts for issue #1062."""

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import unittest

from harness.chain_view import ChainTask, substeps_for
from harness.hooks import _maybe_emit_continuation_signal


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class CodebaseSanityWorkflowTests(unittest.TestCase):
    def test_epic_close_progress_folds_sanity_into_validation_sequence(self) -> None:
        task = ChainTask(name="final", engine="build-worker", closes="epic")

        self.assertEqual(
            substeps_for(task),
            [
                "build-worker",
                "validation-sequence:EPIC",
            ],
        )

    def test_sanity_pass_continues_to_merge_review_not_acceptance(self) -> None:
        with TemporaryDirectory() as td:
            run_dir = Path(td)
            (run_dir / "impl-validator-CODEBASE_SANITY.md").write_text(
                "Epic semantic scope clean.\n\nPASS\n", encoding="utf-8"
            )
            slot = {
                "run_id": "run-1062abcd",
                "run_dir": str(run_dir),
                "acceptance_required": True,
            }
            active = {"run-1062abcd": slot}

            from contextlib import redirect_stdout
            from io import StringIO

            stdout = StringIO()
            with redirect_stdout(stdout):
                blocked = _maybe_emit_continuation_signal(
                    sid="sid-1062",
                    rid="run-1062abcd",
                    slot=slot,
                    active=active,
                    last_agent="impl-validator",
                    last_mode="CODEBASE_SANITY",
                    base_dir=run_dir,
                )

        self.assertTrue(blocked)
        reason = json.loads(stdout.getvalue())["reason"]
        self.assertIn("impl-validator", reason)
        self.assertIn("lifecycle hook", reason)
        self.assertIn("merge review", reason)
        self.assertNotIn("begin-step product-acceptance", reason)

    def test_design_sanity_pass_continues_to_cartography_preflight(self) -> None:
        with TemporaryDirectory() as td:
            run_dir = Path(td)
            (run_dir / "impl-validator-CODEBASE_SANITY.md").write_text(
                "Affected scope clean.\n\nPASS\n", encoding="utf-8"
            )
            slot = {
                "run_id": "run-1062dcba",
                "run_dir": str(run_dir),
                "entry_point": "design",
            }
            active = {"run-1062dcba": slot}

            from contextlib import redirect_stdout
            from io import StringIO

            stdout = StringIO()
            with redirect_stdout(stdout):
                blocked = _maybe_emit_continuation_signal(
                    sid="sid-1062-design",
                    rid="run-1062dcba",
                    slot=slot,
                    active=active,
                    last_agent="impl-validator",
                    last_mode="CODEBASE_SANITY",
                    base_dir=run_dir,
                )

        self.assertTrue(blocked)
        reason = json.loads(stdout.getvalue())["reason"]
        self.assertIn("Cartography freshness preflight", reason)
        self.assertNotIn("merge review", reason)

    def test_impl_loop_folds_epic_sanity_into_holistic_review(self) -> None:
        skill = read("skills/impl-loop/impl-loop-finish.md")

        for text in (skill,):
            self.assertIn("CODEBASE_SANITY", text)
            self.assertIn("Epic", text)
            self.assertIn("holistic invocation", text)
            self.assertIn("별도 Sanity reviewer를 선행 호출하지 않는다", text)
            self.assertIn("coverage", text)
            self.assertIn("UNKNOWN", text)
            self.assertIn("code revision", text)
            self.assertIn("product-acceptance", text)

        self.assertIn("fixed task/commit fan-out", skill)
        self.assertIn("validation sequence", skill)

    def test_validator_modes_preserve_default_scope_and_read_only_boundary(self) -> None:
        validators = (
            read("docs/plugin/agents/impl-validator/impl-validator-agent.md"),
            read("codex/skills/dcness-impl-validator/SKILL.md"),
        )

        for validator in validators:
            self.assertIn("CODEBASE_SANITY", validator)
            self.assertIn("기본 merge-review mode", validator)
            self.assertIn("affected dependency cone", validator)
            self.assertIn("framework-reachable", validator)
            self.assertIn("intentional stub", validator)
            self.assertIn("planned seam", validator)
            self.assertIn("coverage", validator)
            self.assertIn("UNKNOWN", validator)
            self.assertIn("example/scaffold", validator)
            self.assertIn("[quality-gap]", validator)
            self.assertIn("Bash", validator)
            self.assertIn("읽기 전용", validator)

    def test_replacement_hygiene_is_owned_across_design_build_and_review(self) -> None:
        architect = read(
            "docs/plugin/agents/module-architect/module-architect-agent.md"
        )
        worker = read("docs/plugin/agents/build-worker/build-worker-agent.md")
        validator = read(
            "docs/plugin/agents/impl-validator/impl-validator-agent.md"
        )

        self.assertIn("replacement/refactor/migration", architect)
        self.assertIn("제거 후보", architect)
        self.assertIn("의도적으로 보존", architect)

        for surface in (
            "call site",
            "DI binding/provider",
            "route/deep link",
            "manifest/framework registration",
            "resource",
            "test/fake/fixture",
            "suppression/deprecation",
        ):
            self.assertIn(surface, worker)
        self.assertIn("이유와 owner", worker)
        self.assertIn("구현자 보고", validator)
        self.assertIn("obsolete test/resource", validator)
        self.assertIn("stale registration", validator)

    def test_next_design_reuses_only_a_current_sanity_receipt(self) -> None:
        for path in ("skills/design/SKILL.md", "skills/design-system/SKILL.md"):
            text = read(path)
            self.assertIn("Codebase Sanity receipt", text)
            self.assertIn("code tree", text)
            self.assertIn("affected scope", text)
            self.assertIn("impl-validator:CODEBASE_SANITY", text)
            self.assertIn("canonical Root refresh", text)
            self.assertIn("대신하지", text)
            self.assertIn("local-only/ignored", text)

    def test_sanity_receipt_dir_survives_linked_worktree_cleanup(self) -> None:
        with TemporaryDirectory() as td:
            main_root = Path(td) / "main"
            linked_root = Path(td) / "linked"
            main_root.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=main_root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=main_root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=main_root,
                check=True,
            )
            (main_root / "seed.txt").write_text("seed\n", encoding="utf-8")
            subprocess.run(["git", "add", "seed.txt"], cwd=main_root, check=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", "seed"],
                cwd=main_root,
                check=True,
            )
            subprocess.run(
                ["git", "worktree", "add", "-q", "-b", "feature/test", str(linked_root)],
                cwd=main_root,
                check=True,
            )

            result = subprocess.run(
                [
                    str(ROOT / "scripts" / "dcness-helper"),
                    "sanity-receipt-dir",
                    "--project-root",
                    str(linked_root),
                ],
                cwd=linked_root,
                text=True,
                capture_output=True,
                check=True,
            )

        self.assertEqual(
            Path(result.stdout.strip()),
            main_root.resolve() / ".dcness-work" / "codebase-sanity",
        )

        for path in (
            "skills/design/SKILL.md",
            "skills/design-system/SKILL.md",
        ):
            text = read(path)
            self.assertIn("sanity-receipt-dir", text)
            self.assertIn("ExitWorktree", text)

    def test_eval_suite_contains_all_sanity_scenarios(self) -> None:
        cases = {
            "sanity-lint-green-with-warning": ("exit 0", "warning-free"),
            "sanity-coverage-unknown": ("UNKNOWN", "test count"),
            "sanity-example-test-scaffold": ("example/scaffold", "meaningful coverage"),
            "sanity-framework-entrypoint": ("framework-reachable", "registration"),
            "sanity-planned-stub": ("planned seam", "자동 삭제"),
            "sanity-stale-old-path": ("quality-gap", "old path"),
            "sanity-clean-refactor": ("clean", "PASS"),
            "sanity-next-design-stale-receipt": ("stale", "affected scope"),
            "sanity-lifecycle-smoke": (
                "JOURNEY_CONVERGENCE → final mutation owner Cartography sync",
                "fail-fast 순차 검증",
            ),
        }

        for case, needles in cases.items():
            case_dir = ROOT / "evals" / "cases" / case
            with self.subTest(case=case):
                self.assertTrue((case_dir / "prompt.md").is_file())
                expected = (case_dir / "expected.md").read_text(encoding="utf-8")
                for needle in needles:
                    self.assertIn(needle, expected)


if __name__ == "__main__":
    unittest.main()

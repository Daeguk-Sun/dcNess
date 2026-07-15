"""Public impl-task parsing and parallel-wave planning contracts."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness.parallel_wave import (
    ImplTask,
    _glob_match,
    compute_waves,
    normalize_scope_file,
    normalize_scope_text,
    parse_impl_task,
    scopes_disjoint,
    wave_plan_from_paths,
)


def task(
    slug: str,
    depends_on: tuple[str, ...] | None,
    scope: set[str],
    *,
    ambiguous: bool = False,
    serial: bool = False,
) -> ImplTask:
    return ImplTask(slug, f"{slug}.md", depends_on, frozenset(scope), ambiguous, serial)


def write_task(root: Path, name: str, frontmatter: str, scope: str) -> Path:
    path = root / name
    path.write_text(
        f"---\n{frontmatter}\n---\n\n## Scope\n\n### 수정 허용\n\n{scope}\n"
        "### 수정 금지\n\n-\n",
        encoding="utf-8",
    )
    return path


class ParseContractTests(unittest.TestCase):
    def test_depends_on_three_state_and_comments(self) -> None:
        cases = [
            ("story: 1", None),
            ("depends_on:             # placeholder", None),
            ("depends_on: [<NN-slug>]", None),
            ("depends_on: [] # independent", ()),
            ("depends_on: [01-a, 02-b] # deps", ("01-a", "02-b")),
            ("depends_on:\n  - 01-a # first\n  # note\n  - 02-b", ("01-a", "02-b")),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, (frontmatter, expected) in enumerate(cases):
                with self.subTest(frontmatter=frontmatter):
                    parsed = parse_impl_task(
                        write_task(root, f"{index:02}-task.md", frontmatter, "- src/a.py")
                    )
                    self.assertEqual(parsed.depends_on, expected)

    def test_scope_paths_and_ambiguity_are_table_driven(self) -> None:
        cases = [
            ("- src/a.py\n- `harness/b.py` # note", {"src/a.py", "harness/b.py"}, False),
            ("> note\n- .github/workflows/ci.yml\n- ./src/a.py", {".github/workflows/ci.yml", "src/a.py"}, False),
            ("- docs/plugin/parallel-policy.md\n- package-lock.json", {"docs/plugin/parallel-policy.md", "package-lock.json"}, False),
            ("- src/a.py\n- 사용자 입력 파서 전반", {"src/a.py"}, True),
            ("핵심 파서 전반\n- src/a.py", {"src/a.py"}, True),
            ("-", set(), True),
            ("- .", set(), True),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, (scope, paths, ambiguous) in enumerate(cases):
                with self.subTest(scope=scope):
                    parsed = parse_impl_task(
                        write_task(root, f"{index:02}-task.md", "depends_on: []", scope)
                    )
                    self.assertEqual(parsed.scope_paths, frozenset(paths))
                    self.assertEqual(parsed.scope_ambiguous, ambiguous)

    def test_explicit_and_inherent_high_risk_force_serial(self) -> None:
        scopes = (
            "- migrations/001.py",
            "- alembic/versions/001.py",
            "- config/.env.local",
            "- app/secrets/key.json",
            "- src/credentials.py",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            explicit = parse_impl_task(
                write_task(root, "00-explicit.md", "depends_on: []\nparallel: serial", "- src/a.py")
            )
            self.assertTrue(explicit.force_serial)
            for index, scope in enumerate(scopes, start=1):
                self.assertTrue(
                    parse_impl_task(
                        write_task(root, f"{index:02}-risk.md", "depends_on: []", scope)
                    ).force_serial
                )
            self.assertFalse(
                parse_impl_task(
                    write_task(root, "99-safe.md", "depends_on: []\nrisk: high", "- src/env_utils.py")
                ).force_serial
            )

    def test_scope_normalization_is_narrow_and_convergent(self) -> None:
        text = (
            "## Scope\n\n### 수정 허용\n\n"
            "- **API**: src/api.py\n- `src/model.py` (domain model)\n"
            "- src/a.py src/b.py\n"
        )
        normalized, changes = normalize_scope_text(text)
        self.assertIn("- src/api.py", normalized)
        self.assertIn("- src/model.py", normalized)
        self.assertIn("- src/a.py src/b.py", normalized)
        self.assertEqual(len(changes), 2)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = write_task(
                root,
                "01-task.md",
                "depends_on: []",
                "- **API**: src/api.py\n- src/model.py (domain)",
            )
            self.assertTrue(parse_impl_task(path).scope_ambiguous)
            receipt = normalize_scope_file(path)
            self.assertTrue(receipt["changed"])
            self.assertFalse(receipt["unresolved"])


class ScopeCollisionTests(unittest.TestCase):
    def test_scope_collision_matrix(self) -> None:
        cases = [
            ({"a.py"}, {"b.py"}, True),
            ({"a.py"}, {"a.py"}, False),
            ({"src/"}, {"src/a.py"}, False),
            ({"src/a/"}, {"src/b/"}, True),
            ({"src/*.py"}, {"src/a.py"}, False),
            ({"src/*.py"}, {"src/sub/a.py"}, True),
            ({"src/*.py"}, {"src/a*"}, False),
            ({"src/**/*.py"}, {"src/a.py"}, False),
        ]
        for left, right, expected in cases:
            with self.subTest(left=left, right=right):
                self.assertEqual(scopes_disjoint(left, right), expected)

    def test_glob_matching_is_segment_aware(self) -> None:
        cases = [
            ("src/a.py", "src/[ab].py", True),
            ("src/c.py", "src/[ab].py", False),
            ("src/sub/a.py", "src/*.py", False),
            ("src/a.py", "src/**/*.py", True),
            ("src/x/y/a.py", "src/**/*.py", True),
            ("src/[x.py", "src/[x.py", True),
        ]
        for path, pattern, expected in cases:
            self.assertEqual(_glob_match(path, pattern), expected)


class WavePlanContractTests(unittest.TestCase):
    def test_parallel_dependency_overlap_and_cap_scenarios(self) -> None:
        scenarios = [
            (
                [task("01-a", (), {"a.py"}), task("02-b", (), {"b.py"})],
                2,
                [("parallel", ("01-a", "02-b"))],
            ),
            (
                [task("01-a", (), {"same.py"}), task("02-b", (), {"same.py"})],
                2,
                [("serial", ("01-a",)), ("serial", ("02-b",))],
            ),
            (
                [task("01-a", (), {"a.py"}), task("02-b", ("01-a",), {"b.py"})],
                2,
                [("serial", ("01-a",)), ("serial", ("02-b",))],
            ),
            (
                [
                    task("01-a", (), {"a.py"}),
                    task("02-b", (), {"b.py"}),
                    task("03-c", (), {"c.py"}),
                ],
                2,
                [("parallel", ("01-a", "02-b")), ("serial", ("03-c",))],
            ),
        ]
        for tasks, cap, expected in scenarios:
            plan = compute_waves(tasks, max_parallel_workers=cap)
            actual = [(step.mode, tuple(t.slug for t in step.tasks)) for step in plan.steps]
            self.assertEqual(actual, expected)

    def test_serial_causes_and_public_diagnostics(self) -> None:
        tasks = [
            task("01-unknown", None, {"a.py"}),
            task("02-format", (), set(), ambiguous=True),
            task("03-forced", (), {"c.py"}, serial=True),
            task("04-high", (), {"d.py"}),
        ]
        plan = compute_waves(tasks, high_risk_slugs={"04-high"})
        payload = plan.to_dict()
        causes = {row["slug"]: row["cause"] for row in payload["serial_demotions"]}
        self.assertEqual(
            causes,
            {
                "01-unknown": "unknown_deps",
                "02-format": "scope_unnormalized",
                "03-forced": "forced",
                "04-high": "high_risk",
            },
        )
        self.assertEqual(payload["format_unnormalized_slugs"], ["02-format"])

    def test_blocked_intervening_task_is_an_order_barrier(self) -> None:
        tasks = [
            task("01-a", (), {"a.py"}),
            task("02-blocked", ("01-a",), {"b.py"}),
            task("03-c", (), {"c.py"}),
        ]
        plan = compute_waves(tasks)
        order = [t.slug for step in plan.steps for t in step.tasks]
        self.assertEqual(order, ["01-a", "02-blocked", "03-c"])
        self.assertEqual([t.slug for t in plan.steps[0].tasks], ["01-a"])

    def test_cycle_falls_back_to_deterministic_serial_order(self) -> None:
        plan = compute_waves(
            [task("01-a", ("02-b",), {"a.py"}), task("02-b", ("01-a",), {"b.py"})]
        )
        self.assertEqual([step.cause for step in plan.steps], ["dep_unresolved", "no_disjoint_pair"])
        self.assertEqual([step.tasks[0].slug for step in plan.steps], ["01-a", "02-b"])

    def test_directory_glob_and_explicit_paths_share_one_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = write_task(root, "01-a.md", "depends_on: []", "- src/a.py")
            second = write_task(root, "02-b.md", "depends_on: []", "- src/b.py")
            for paths in (
                [str(root)],
                [str(root / "*.md")],
                [str(second), str(first), str(first)],
            ):
                with self.subTest(paths=paths):
                    plan = wave_plan_from_paths(paths)
                    self.assertTrue(plan.has_parallel)
                    self.assertEqual(
                        [task.slug for task in plan.steps[0].tasks], ["01-a", "02-b"]
                    )


if __name__ == "__main__":
    unittest.main()

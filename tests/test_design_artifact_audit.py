"""Regression tests for design artifact structure audit (#832)."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_design_artifact_structure.mjs"
NODE = shutil.which("node")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [NODE, str(SCRIPT), "--root", str(root), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def _seed_project(root: Path, *, impl_body: str, architecture_extra: str = "") -> None:
    _write(
        root / "docs/index.md",
        """
        # Project Index

        ## 에픽

        | 에픽 | 마일스톤 | Stories | Architecture | Domain Model | UX Flow | Tech Review |
        |---|---|---|---|---|---|---|
        | [epic-01-alpha](epics/epic-01-alpha/) | v01 | [stories.md](epics/epic-01-alpha/stories.md) | [architecture.md](epics/epic-01-alpha/architecture.md) | [domain-model.md](epics/epic-01-alpha/domain-model.md) | — | — |
        """,
    )
    _write(root / "docs/architecture.md", "# Root Architecture\n")
    _write(root / "docs/epics/epic-01-alpha/stories.md", "# Stories\n")
    _write(root / "docs/epics/epic-01-alpha/domain-model.md", "# Domain\n")
    _write(
        root / "docs/epics/epic-01-alpha/architecture.md",
        f"""
        # Epic Architecture

        ## Contract Ledger

        | contract | owner | producer | consumer | invariant | ordering | error mode | config | forbidden alternative | refs |
        |---|---|---|---|---|---|---|---|---|---|
        | AuthSession | AuthCore | LoginForm | AuthCore | session id stable | login before refresh | reject | env | global mutable session | [ADR-0001](../../decisions/0001-auth.md) |
        {architecture_extra}
        """,
    )
    _write(root / "docs/epics/epic-01-alpha/impl/01-auth.md", impl_body)


@unittest.skipUnless(NODE, "node not installed - design artifact audit is a node script")
class DesignArtifactAuditTests(unittest.TestCase):
    def test_pointer_artifacts_pass_and_recover_contract_from_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_project(
                root,
                impl_body="""
                ---
                contract:
                  produces: [AuthSession]
                  consumes: []
                ---

                # Auth task

                ## Contract References

                | kind | Ledger row key | action | note |
                |---|---|---|---|
                | produces | AuthSession | new | Ledger updated |
                """,
            )

            proc = _run(root, "--json", "--contract", "AuthSession")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["violations"], [])
        self.assertEqual(payload["recovery"]["contract"], "AuthSession")
        self.assertEqual(
            payload["recovery"]["ledger_path"],
            "docs/epics/epic-01-alpha/architecture.md",
        )
        self.assertIn(
            "docs/epics/epic-01-alpha/impl/01-auth.md",
            payload["recovery"]["referencing_impl"],
        )

    def test_new_pointer_artifact_fails_when_contract_detail_is_copied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_project(
                root,
                impl_body="""
                ---
                contract:
                  produces: [AuthSession]
                  consumes: []
                ---

                # Auth task

                ## Contract References

                | kind | Ledger row key | action | note |
                |---|---|---|---|
                | produces | AuthSession | new | Ledger updated |

                ## Contract

                | contract | owner | producer | consumer | invariant | ordering | error mode | config | forbidden alternative |
                |---|---|---|---|---|---|---|---|---|
                | AuthSession | AuthCore | LoginForm | AuthCore | duplicated | duplicated | duplicated | duplicated | duplicated |
                """,
            )

            proc = _run(root)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("contract-detail-copy", proc.stderr)
        self.assertIn("01-auth.md", proc.stderr)

    def test_unknown_ledger_row_key_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_project(
                root,
                impl_body="""
                ---
                contract:
                  produces: [MissingContract]
                  consumes: []
                ---

                # Auth task

                ## Contract References

                | kind | Ledger row key | action | note |
                |---|---|---|---|
                | produces | MissingContract | new | wrong key |
                """,
            )

            proc = _run(root)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("unknown-ledger-row-key", proc.stderr)
        self.assertIn("MissingContract", proc.stderr)

    def test_legacy_contract_table_warns_but_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_project(
                root,
                impl_body="""
                # Legacy task

                ## Contract

                | contract | owner | producer | consumer | invariant | ordering | error mode | config | forbidden alternative |
                |---|---|---|---|---|---|---|---|---|
                | AuthSession | AuthCore | LoginForm | AuthCore | old | old | old | old | old |
                """,
            )

            proc = _run(root, "--json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["violations"], [])
        self.assertEqual(payload["warnings"][0]["code"], "legacy-contract-table")

    def test_budget_warning_reports_full_pack_over_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_project(
                root,
                impl_body="# Auth task\n\n## Contract References\n\n- none\n",
            )
            noisy_lines = "\n".join(f"- line {i}" for i in range(1510))
            _write(root / "docs/epics/epic-01-alpha/stories.md", f"# Stories\n{noisy_lines}\n")

            proc = _run(root, "--json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertTrue(
            any(w["code"] == "design-pack-over-target" for w in payload["warnings"])
        )

    def test_contract_recovery_requires_index_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_project(
                root,
                impl_body="# Auth task\n\n## Contract References\n\n- none\n",
            )
            (root / "docs/index.md").unlink()

            proc = _run(root, "--contract", "AuthSession")

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("cold-session-index-missing", proc.stderr)


if __name__ == "__main__":
    unittest.main()

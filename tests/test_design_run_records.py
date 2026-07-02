"""Design run durable record tests (#833)."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from harness import ledger
from harness.design_run_records import (
    DESIGN_RUN_RECORD_REL,
    build_design_record,
    load_records,
    render_records,
    design_record_path,
    write_design_record,
)


def _make_run_dir(tmp: Path, sid: str, rid: str, events: list[dict], prose: dict) -> Path:
    run_dir = tmp / ".claude" / "harness-state" / ".sessions" / sid / "runs" / rid
    run_dir.mkdir(parents=True, exist_ok=True)
    prose_paths: dict[str, tuple[Path, str]] = {}
    for name, text in prose.items():
        p = run_dir / name
        p.write_text(text, encoding="utf-8")
        prose_paths[name] = (p, text)
    with (run_dir / "ledger.jsonl").open("w", encoding="utf-8") as f:
        for event in events:
            rec = dict(event)
            pf = rec.get("prose_file")
            if isinstance(pf, str) and pf in prose_paths:
                p, text = prose_paths[pf]
                rec["prose_file"] = str(p)
                rec.setdefault("sha256", ledger.sha256_text(text))
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return run_dir


def _step(agent: str, filename: str, ts: str) -> dict:
    return {
        "event": "step_completed",
        "ts": ts,
        "agent": agent,
        "mode": None,
        "enum": "PROSE_LOGGED",
        "prose_file": filename,
        "prose_excerpt": "",
    }


class DesignRunRecordTests(unittest.TestCase):
    def _init_git_repo(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        for cmd in (
            ["git", "init", "-q"],
            ["git", "config", "user.email", "test@example.com"],
            ["git", "config", "user.name", "test"],
            ["git", "commit", "-q", "--allow-empty", "-m", "init"],
        ):
            subprocess.run(cmd, cwd=path, check=True, capture_output=True)

    def test_builds_design_record_with_units_findings_and_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            run_dir = _make_run_dir(
                tmp,
                "sid1",
                "run-design01",
                [
                    {
                        "event": "run_started",
                        "entry_point": "design",
                        "ts": "2026-07-01T00:00:00+00:00",
                    },
                    _step(
                        "architecture-validator",
                        "av1.md",
                        "2026-07-01T00:01:00+00:00",
                    ),
                    _step(
                        "module-architect",
                        "ma.md",
                        "2026-07-01T00:04:00+00:00",
                    ),
                    _step(
                        "architecture-validator",
                        "av2.md",
                        "2026-07-01T00:08:00+00:00",
                    ),
                    {
                        "event": "run_finished",
                        "ts": "2026-07-01T00:10:00+00:00",
                    },
                ],
                {
                    "av1.md": (
                        "Must finding: TASK_LOCAL at docs/x.md:1\n"
                        "Still failing\nFAIL\n"
                    ),
                    "ma.md": "보강 완료\nPASS\n",
                    "av2.md": (
                        "Resolved TASK_LOCAL. CONTRACT_PROPAGATION 없음.\n"
                        "PASS\n"
                    ),
                },
            )
            record = build_design_record(run_dir, repo_path=tmp)

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record["entry_point"], "design")
        self.assertEqual(record["duration_s"], 600)
        self.assertEqual(record["step_count"], 3)
        self.assertEqual(record["final_verdict"], "PASS")
        self.assertEqual(record["finding_classes"]["TASK_LOCAL"], 1)
        self.assertNotIn("CONTRACT_PROPAGATION", record["finding_classes"])
        self.assertEqual(record["revalidation_cycles"], {"architecture-validator": 1})
        self.assertEqual(record["units"][0]["verdict"], "FAIL")
        self.assertEqual(record["units"][2]["cycle"], 1)

    def test_non_design_run_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            run_dir = _make_run_dir(
                tmp,
                "sid1",
                "run-impl001",
                [
                    {
                        "event": "run_started",
                        "entry_point": "impl",
                        "ts": "2026-07-01T00:00:00+00:00",
                    },
                    _step("engineer", "e.md", "2026-07-01T00:01:00+00:00"),
                    {"event": "run_finished", "ts": "2026-07-01T00:02:00+00:00"},
                ],
                {"e.md": "구현\nIMPL_DONE\n"},
            )
            self.assertIsNone(build_design_record(run_dir, repo_path=tmp))

    def test_write_replaces_same_run_id_and_render_reads_without_run_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            run_dir = _make_run_dir(
                tmp,
                "sid1",
                "run-design02",
                [
                    {
                        "event": "run_started",
                        "entry_point": "design",
                        "ts": "2026-07-01T00:00:00+00:00",
                    },
                    _step("architecture-validator", "av.md", "2026-07-01T00:01:00+00:00"),
                    {"event": "run_finished", "ts": "2026-07-01T00:02:00+00:00"},
                ],
                {"av.md": "문제 없음\nPASS\n"},
            )

            first = write_design_record(run_dir, repo_path=tmp)
            second = write_design_record(run_dir, repo_path=tmp)
            records = load_records(tmp)
            rendered = render_records(records)
            record_path_exists = (tmp / DESIGN_RUN_RECORD_REL).is_file()

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(len(records), 1)
        self.assertTrue(record_path_exists)
        self.assertIn("run-design02", rendered)
        self.assertIn("| run_id | started_at | verdict |", rendered)

    def test_worktree_record_path_is_design_artifact_root(self) -> None:
        """Worktree `/design` writes the PR artifact, not main checkout state.

        The commit owner is the design branch PR: `/design` must run `end-run`
        before PR creation so this worktree-local docs file is staged with the
        rest of the design artifacts.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            main_repo = tmp / "main"
            self._init_git_repo(main_repo)
            worktree = tmp / "wt-design"
            subprocess.run(
                ["git", "worktree", "add", "-q", str(worktree), "-b", "docs-design"],
                cwd=main_repo,
                check=True,
                capture_output=True,
            )
            try:
                run_dir = _make_run_dir(
                    main_repo,
                    "sid1",
                    "run-design03",
                    [
                        {
                            "event": "run_started",
                            "entry_point": "design",
                            "ts": "2026-07-01T00:00:00+00:00",
                        },
                        _step(
                            "architecture-validator",
                            "av.md",
                            "2026-07-01T00:01:00+00:00",
                        ),
                        {
                            "event": "run_finished",
                            "ts": "2026-07-01T00:02:00+00:00",
                        },
                    ],
                    {"av.md": "문제 없음\nPASS\n"},
                )

                record = write_design_record(run_dir, repo_path=worktree)
                wt_record_path = design_record_path(worktree)
                main_record_path = main_repo / DESIGN_RUN_RECORD_REL

                self.assertIsNotNone(record)
                self.assertEqual(
                    wt_record_path.resolve(),
                    (worktree / DESIGN_RUN_RECORD_REL).resolve(),
                )
                self.assertTrue(wt_record_path.is_file())
                self.assertFalse(main_record_path.exists())
            finally:
                subprocess.run(
                    ["git", "worktree", "remove", str(worktree), "--force"],
                    cwd=main_repo,
                    check=False,
                    capture_output=True,
                )


if __name__ == "__main__":
    unittest.main()

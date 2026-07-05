"""loop_lessons — recurrent waste lesson storage and injection tests (#917)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness import ledger
from harness.loop_lessons import (
    archive_removed_patterns,
    lessons_path,
    list_active_lessons,
    read,
    sync_from_run,
    upsert_entry,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _ghost_run(tmp: Path, rid: str) -> Path:
    run_dir = (
        tmp
        / ".claude"
        / "harness-state"
        / ".sessions"
        / "sid-lessons"
        / "runs"
        / rid
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    reviewer = run_dir / "pr-reviewer.md"
    reviewer.write_text("MUST FIX: blocker remains\n\nPASS\n", encoding="utf-8")
    engineer = run_dir / "engineer-IMPL.md"
    engineer.write_text("follow-up step\n\nIMPL_DONE\n", encoding="utf-8")
    _write_jsonl(
        run_dir / "ledger.jsonl",
        [
            {"event": "run_started", "ts": "2026-07-05T00:00:00Z", "entry_point": "impl"},
            {
                "event": "step_completed",
                "ts": "2026-07-05T00:01:00Z",
                "agent": "pr-reviewer",
                "mode": None,
                "enum": "PROSE_LOGGED",
                "must_fix": True,
                "prose_excerpt": "MUST FIX: blocker remains\n\nPASS",
                "prose_file": str(reviewer),
                "sha256": ledger.sha256_text(reviewer.read_text(encoding="utf-8")),
            },
            {
                "event": "step_completed",
                "ts": "2026-07-05T00:02:00Z",
                "agent": "engineer",
                "mode": "IMPL",
                "enum": "PROSE_LOGGED",
                "must_fix": False,
                "prose_excerpt": "follow-up step\n\nIMPL_DONE",
                "prose_file": str(engineer),
                "sha256": ledger.sha256_text(engineer.read_text(encoding="utf-8")),
            },
            {"event": "run_finished", "ts": "2026-07-05T00:03:00Z"},
        ],
    )
    return run_dir


class LoopLessonsPathTests(unittest.TestCase):
    def test_path_shape_matches_loop_insights(self) -> None:
        p = lessons_path("engineer", "IMPL", cwd=Path("/tmp"))

        self.assertEqual(p.name, "engineer-IMPL.md")
        self.assertIn(".claude/loop-lessons", str(p))

    def test_worktree_cwd_normalizes_to_main_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            main = Path(td) / "main"
            worktree = main / ".claude" / "worktrees" / "wt1"
            worktree.mkdir(parents=True)

            with patch("harness.loop_lessons._resolve_project_root", return_value=main):
                p = lessons_path("pr-reviewer", None, cwd=worktree)

            self.assertEqual(
                p,
                main.resolve() / ".claude" / "loop-lessons" / "pr-reviewer.md",
            )


class LoopLessonsSyncTests(unittest.TestCase):
    def test_sync_creates_lesson_when_agent_pattern_reaches_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            runs = [_ghost_run(tmp, f"run-ghost{i}") for i in range(3)]

            changed = sync_from_run(runs[-1], repo_path=tmp, recurrence_threshold=3)

            p = tmp.resolve() / ".claude" / "loop-lessons" / "pr-reviewer.md"
            self.assertEqual(changed, [p])
            content = p.read_text(encoding="utf-8")
            self.assertIn("### MUST_FIX_GHOST", content)
            self.assertIn("- status: active", content)
            self.assertIn("- hits: 3", content)
            self.assertIn("run_id=run-ghost2", content)
            self.assertIn("pr-reviewer.md", content)

            injected = read("pr-reviewer", cwd=tmp)
            self.assertIn("MUST_FIX_GHOST", injected)
            self.assertIn("hits=3", injected)

    def test_sync_skips_below_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            run = _ghost_run(tmp, "run-ghost0")

            changed = sync_from_run(run, repo_path=tmp, recurrence_threshold=2)

            self.assertEqual(changed, [])
            self.assertFalse((tmp / ".claude" / "loop-lessons").exists())

    def test_existing_entry_is_updated_not_duplicated(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            p = upsert_entry(
                "pr-reviewer",
                None,
                "MUST_FIX_GHOST",
                hits=3,
                last="2026-07-05T00:03:00Z",
                evidence=["run_id=run-a path=/tmp/a.md"],
                cwd=tmp,
            )
            upsert_entry(
                "pr-reviewer",
                None,
                "MUST_FIX_GHOST",
                hits=4,
                last="2026-07-05T00:04:00Z",
                evidence=["run_id=run-b path=/tmp/b.md"],
                cwd=tmp,
            )

            content = p.read_text(encoding="utf-8")
            self.assertEqual(content.count("### MUST_FIX_GHOST"), 1)
            self.assertIn("- hits: 4", content)
            self.assertIn("run_id=run-a", content)
            self.assertIn("run_id=run-b", content)
            self.assertIn("# Loop Lessons: pr-reviewer", content)
            self.assertNotIn("# Loop Lessons: pr / reviewer", content)

            active = list_active_lessons(tmp)
            self.assertEqual(active[0]["agent"], "pr-reviewer")
            self.assertIsNone(active[0]["mode"])

    def test_archive_removed_patterns_excludes_from_read(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            p = upsert_entry(
                "engineer",
                "IMPL",
                "OLD_REMOVED_PATTERN",
                hits=3,
                last="2026-07-05T00:03:00Z",
                evidence=["run_id=run-old path=/tmp/old.md"],
                cwd=tmp,
            )

            archive_removed_patterns(p, active_patterns={"MUST_FIX_GHOST"})

            content = p.read_text(encoding="utf-8")
            self.assertIn("### OLD_REMOVED_PATTERN", content)
            self.assertIn("- status: archived", content)
            self.assertEqual(read("engineer", "IMPL", cwd=tmp, active_patterns={"MUST_FIX_GHOST"}), "")

    def test_explicit_empty_active_patterns_archives_without_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            p = upsert_entry(
                "pr-reviewer",
                None,
                "MUST_FIX_GHOST",
                hits=3,
                last="2026-07-05T00:03:00Z",
                evidence=["run_id=run-a path=/tmp/a.md"],
                cwd=tmp,
            )

            self.assertEqual(read("pr-reviewer", cwd=tmp, active_patterns=set()), "")
            content = p.read_text(encoding="utf-8")
            self.assertIn("- status: archived", content)
            self.assertEqual(list_active_lessons(tmp, active_patterns=set()), [])


if __name__ == "__main__":
    unittest.main()

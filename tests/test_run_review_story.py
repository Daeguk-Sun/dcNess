"""`/run-review` story(chain) 단위 집계 계약 테스트 (#1204)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from harness import run_review  # noqa: E402
from harness.run_review import (  # noqa: E402
    build_story_report,
    find_story_runs,
    render_story_report,
    run_story_id,
)
from tests.run_fixtures import make_ledger_run_dir  # noqa: E402


def _write_task(root: Path, epic: str, filename: str, story: str) -> Path:
    directory = root / "docs" / "epics" / epic / "impl"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_text(
        f"---\ntitle: {filename}\nstory: {story}\ntask_index: 1\n---\n\n본문\n",
        encoding="utf-8",
    )
    return path


def _run(
    root: Path,
    sid: str,
    rid: str,
    *,
    design_doc: Path | None,
    started: str,
    agent: str = "build-worker",
    enum: str = "PASS",
    must_fix: bool = False,
    prose: str = "## 결론\nPASS",
) -> Path:
    started_event: dict[str, object] = {
        "event": "run_started",
        "ts": started,
        "entry_point": "impl",
    }
    if design_doc is not None:
        started_event["design_doc"] = str(design_doc)
    return make_ledger_run_dir(
        root,
        sid,
        rid,
        [
            started_event,
            {
                "event": "step_completed",
                "ts": started,
                "agent": agent,
                "mode": None,
                "enum": enum,
                "must_fix": must_fix,
                "prose_excerpt": prose,
                "prose_file": f"{agent}.md",
                "evidence_paths": [],
                "next_action": "",
            },
            {"event": "run_finished", "ts": started},
        ],
        prose_files={f"{agent}.md": prose},
    )


def _sessions_root(root: Path) -> Path:
    return root / ".claude" / "harness-state" / ".sessions"


class RunStoryResolutionTests(unittest.TestCase):
    """AC3 — 새 상태 파일 없이 기존 run 기록과 impl task frontmatter 로 story 를 확인한다."""

    def test_story_comes_from_recorded_design_doc_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = _write_task(root, "epic-01-messaging", "02-send.md", "story-02-send")
            run_dir = _run(root, "sid", "run-a", design_doc=task, started="2026-09-01T10:00:00")
            self.assertEqual("story-02-send", run_story_id(run_dir, root))

    def test_run_without_design_doc_belongs_to_no_story(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = _run(root, "sid", "run-a", design_doc=None, started="2026-09-01T10:00:00")
            self.assertIsNone(run_story_id(run_dir, root))

    def test_unknown_story_frontmatter_is_not_treated_as_a_story(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = _write_task(root, "epic-01-messaging", "02-send.md", "unknown")
            run_dir = _run(root, "sid", "run-a", design_doc=task, started="2026-09-01T10:00:00")
            self.assertIsNone(run_story_id(run_dir, root))

    def test_missing_worktree_path_is_recovered_under_the_current_repo(self) -> None:
        """begin-run 이 기록한 worktree 절대경로가 사라져도 같은 설계 경로로 다시 찾는다."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_task(root, "epic-01-messaging", "02-send.md", "story-02-send")
            stale = Path("/tmp/gone-worktree/docs/epics/epic-01-messaging/impl/02-send.md")
            run_dir = _run(root, "sid", "run-a", design_doc=stale, started="2026-09-01T10:00:00")
            self.assertEqual("story-02-send", run_story_id(run_dir, root))

    def test_path_outside_the_design_artifact_convention_is_not_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stale = Path("/tmp/gone/notes/02-send.md")
            run_dir = _run(root, "sid", "run-a", design_doc=stale, started="2026-09-01T10:00:00")
            self.assertIsNone(run_story_id(run_dir, root))


class StoryRunCollectionTests(unittest.TestCase):
    """AC1 — 여러 run 으로 나뉜 story 하나가 한 번의 명령으로 전부 포함된다."""

    def _fixture(self, root: Path) -> None:
        epic = "epic-01-messaging"
        first = _write_task(root, epic, "01-list.md", "story-02-send")
        second = _write_task(root, epic, "02-compose.md", "story-02-send")
        third = _write_task(root, epic, "03-status.md", "story-02-send")
        other = _write_task(root, epic, "04-notify.md", "story-03-notify")
        _run(root, "sid", "run-c", design_doc=third, started="2026-09-01T12:00:00")
        _run(root, "sid", "run-a", design_doc=first, started="2026-09-01T10:00:00")
        _run(root, "sid", "run-b", design_doc=second, started="2026-09-01T11:00:00")
        _run(root, "sid", "run-z", design_doc=other, started="2026-09-01T13:00:00")
        _run(root, "sid", "run-none", design_doc=None, started="2026-09-01T14:00:00")

    def test_all_runs_of_one_story_are_collected_in_start_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            found = find_story_runs(_sessions_root(root), "story-02-send", root)
            self.assertEqual(["run-a", "run-b", "run-c"], [p.name for p in found])

    def test_other_stories_and_storyless_runs_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            report = build_story_report(_sessions_root(root), "story-02-send", root)
            self.assertEqual(["run-a", "run-b", "run-c"], [e.run_id for e in report.runs])
            other = build_story_report(_sessions_root(root), "story-03-notify", root)
            self.assertEqual(["run-z"], [e.run_id for e in other.runs])

    def test_each_run_entry_keeps_its_impl_task_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            report = build_story_report(_sessions_root(root), "story-02-send", root)
            self.assertEqual(
                [
                    "docs/epics/epic-01-messaging/impl/01-list.md",
                    "docs/epics/epic-01-messaging/impl/02-compose.md",
                    "docs/epics/epic-01-messaging/impl/03-status.md",
                ],
                [entry.task_path for entry in report.runs],
            )

    def test_unknown_story_reports_no_runs_and_a_nonzero_exit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            report = build_story_report(_sessions_root(root), "story-99-absent", root)
            self.assertEqual([], report.runs)
            self.assertIn("속한 완료 run 이 없다", render_story_report(report))
            self.assertEqual(
                1,
                run_review.main(["--story", "story-99-absent", "--repo", str(root)]),
            )


class StoryTotalsTests(unittest.TestCase):
    """AC2 — run 별 내역과 story 총계가 함께 표기된다."""

    def test_totals_sum_steps_elapsed_tokens_and_cost_across_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            epic = "epic-01-messaging"
            first = _write_task(root, epic, "01-list.md", "story-02-send")
            second = _write_task(root, epic, "02-compose.md", "story-02-send")
            _run(root, "sid", "run-a", design_doc=first, started="2026-09-01T10:00:00")
            _run(root, "sid", "run-b", design_doc=second, started="2026-09-01T11:00:00")
            report = build_story_report(_sessions_root(root), "story-02-send", root)
            self.assertEqual(2, len(report.runs))
            self.assertEqual(
                sum(len(entry.report.steps) for entry in report.runs), report.total_steps
            )
            self.assertEqual(
                sum(entry.report.elapsed_s for entry in report.runs),
                report.total_elapsed_s,
            )
            self.assertEqual(
                sum(entry.report.total_cost_usd for entry in report.runs),
                report.total_cost_usd,
            )
            self.assertEqual(
                sum(entry.report.total_input_tokens for entry in report.runs),
                report.total_input_tokens,
            )

    def test_report_shows_per_run_rows_and_story_totals_together(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            epic = "epic-01-messaging"
            first = _write_task(root, epic, "01-list.md", "story-02-send")
            second = _write_task(root, epic, "02-compose.md", "story-02-send")
            _run(root, "sid", "run-a", design_doc=first, started="2026-09-01T10:00:00")
            _run(root, "sid", "run-b", design_doc=second, started="2026-09-01T11:00:00")
            text = render_story_report(
                build_story_report(_sessions_root(root), "story-02-send", root)
            )
            self.assertIn("# Story Review: story-02-send", text)
            self.assertIn("| run 수 | 2 |", text)
            self.assertIn("## run 내역", text)
            self.assertIn("`run-a`", text)
            self.assertIn("`run-b`", text)
            self.assertIn("소요 합계", text)
            self.assertIn("비용 합계", text)
            self.assertIn("## 호출 흐름 (story 순서)", text)
            self.assertIn("docs/epics/epic-01-messaging/impl/01-list.md", text)


class StoryFindingDedupTests(unittest.TestCase):
    """AC2 — finding 을 story 전체에서 중복 제거해 집계한다."""

    def test_same_finding_in_two_runs_becomes_one_row_with_both_run_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            epic = "epic-01-messaging"
            first = _write_task(root, epic, "01-list.md", "story-02-send")
            second = _write_task(root, epic, "02-compose.md", "story-02-send")
            prose = "## 결론\nMUST FIX: 같은 경계 위반\nFAIL"
            _run(
                root,
                "sid",
                "run-a",
                design_doc=first,
                started="2026-09-01T10:00:00",
                agent="impl-validator",
                enum="FAIL",
                must_fix=True,
                prose=prose,
            )
            _run(
                root,
                "sid",
                "run-b",
                design_doc=second,
                started="2026-09-01T11:00:00",
                agent="impl-validator",
                enum="FAIL",
                must_fix=True,
                prose=prose,
            )
            report = build_story_report(_sessions_root(root), "story-02-send", root)
            self.assertTrue(report.wastes, "두 run 의 미해결 MUST FIX 가 집계돼야 한다")
            merged = [item for item in report.wastes if item.occurrences == 2]
            self.assertTrue(merged, f"중복 제거 결과가 없다: {report.wastes}")
            self.assertEqual(["run-a", "run-b"], merged[0].run_ids)
            text = render_story_report(report)
            self.assertIn("중복 제거", text)

    def test_story_report_does_not_create_any_new_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = _write_task(root, "epic-01-messaging", "01-list.md", "story-02-send")
            _run(root, "sid", "run-a", design_doc=task, started="2026-09-01T10:00:00")
            before = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
            build_story_report(_sessions_root(root), "story-02-send", root)
            after = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()

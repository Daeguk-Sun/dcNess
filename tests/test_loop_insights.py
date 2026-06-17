"""test_loop_insights — loop_insights 모듈 단위 테스트 (DCN-CHG-20260502-02).

Coverage:
    insights_path:
        - mode 있음 / 없음 파일명 규칙

    read:
        - 파일 없음 → ""
        - 파일 있음 → 전체 내용 반환

    append_findings:
        - 신규 파일 생성 + 헤더 + 섹션 구조
        - 기존 파일에 bads append
        - 기존 파일에 goods append
        - 중복 항목 스킵
        - bads/goods 모두 빈 리스트 → 파일 미생성

    append_from_run:
        - redo-log REDO_* 항목 → bads 누적
        - PASS 항목 스킵
        - redo reason 없는 항목 스킵
        - 빈 redo-log + 빈 steps → 수정 파일 없음
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness.loop_insights import (
    insights_path,
    read,
    append_findings,
    append_insight,
    INSIGHT_FIFO_CAP,
)
# issue #392 — append_from_run 폐기
# issue #396 — append_insight 신규 (FIFO 10 cap, 메인 자율 평가)


class TestInsightsPath(unittest.TestCase):
    def test_no_mode(self):
        p = insights_path("engineer", cwd=Path("/tmp"))
        self.assertEqual(p.name, "engineer.md")

    def test_with_mode(self):
        p = insights_path("engineer", "IMPL", cwd=Path("/tmp"))
        self.assertEqual(p.name, "engineer-IMPL.md")

    def test_dir_structure(self):
        p = insights_path("validator", "CODE_VALIDATION", cwd=Path("/tmp"))
        self.assertIn(".claude/loop-insights", str(p))


class TestRead(unittest.TestCase):
    def test_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            result = read("engineer", "IMPL", cwd=Path(td))
            self.assertEqual(result, "")

    def test_existing_file_returns_content(self):
        with tempfile.TemporaryDirectory() as td:
            p = insights_path("engineer", "IMPL", cwd=Path(td))
            p.parent.mkdir(parents=True)
            p.write_text("# Loop Insights\ncontent", encoding="utf-8")
            result = read("engineer", "IMPL", cwd=Path(td))
            self.assertIn("content", result)


class TestAppendFindings(unittest.TestCase):
    def test_creates_new_file_with_header(self):
        with tempfile.TemporaryDirectory() as td:
            append_findings("engineer", "IMPL", ["bad thing"], [], cwd=Path(td))
            p = insights_path("engineer", "IMPL", cwd=Path(td))
            self.assertTrue(p.exists())
            content = p.read_text()
            self.assertIn("# Loop Insights: engineer / IMPL", content)
            self.assertIn("bad thing", content)
            self.assertIn("하지 말 것", content)

    def test_creates_new_file_no_mode(self):
        with tempfile.TemporaryDirectory() as td:
            append_findings("test-engineer", None, ["bad"], [], cwd=Path(td))
            p = insights_path("test-engineer", None, cwd=Path(td))
            content = p.read_text()
            self.assertIn("# Loop Insights: test-engineer", content)
            self.assertNotIn("# Loop Insights: test-engineer /", content)

    def test_appends_to_existing(self):
        with tempfile.TemporaryDirectory() as td:
            append_findings("engineer", "IMPL", ["first bad"], [], cwd=Path(td))
            append_findings("engineer", "IMPL", ["second bad"], [], cwd=Path(td))
            content = insights_path("engineer", "IMPL", cwd=Path(td)).read_text()
            self.assertIn("first bad", content)
            self.assertIn("second bad", content)

    def test_appends_goods(self):
        with tempfile.TemporaryDirectory() as td:
            append_findings("engineer", "IMPL", [], ["good thing"], cwd=Path(td))
            content = insights_path("engineer", "IMPL", cwd=Path(td)).read_text()
            self.assertIn("잘 됐던 것", content)
            self.assertIn("good thing", content)

    def test_skips_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            append_findings("engineer", "IMPL", ["same bad"], [], cwd=Path(td))
            append_findings("engineer", "IMPL", ["same bad"], [], cwd=Path(td))
            content = insights_path("engineer", "IMPL", cwd=Path(td)).read_text()
            self.assertEqual(content.count("same bad"), 1)

    def test_noop_when_empty(self):
        with tempfile.TemporaryDirectory() as td:
            append_findings("engineer", "IMPL", [], [], cwd=Path(td))
            p = insights_path("engineer", "IMPL", cwd=Path(td))
            self.assertFalse(p.exists())


# issue #392 — TestAppendFromRun 클래스 전체 폐기 (append_from_run 폐기 정합).


class TestAppendInsight(unittest.TestCase):
    """issue #396 — append_insight (FIFO 10 cap, 메인 자율 평가)."""

    def test_creates_file_with_first_entry(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            p = append_insight("engineer", "IMPL", "🚨 첫 인사이트", cwd=td_path)
            self.assertTrue(p.exists())
            content = p.read_text()
            self.assertIn("# Loop Insights: engineer / IMPL", content)
            self.assertIn("🚨 첫 인사이트", content)

    def test_no_mode_path(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            p = append_insight("pr-reviewer", None, "LGTM 정합", cwd=td_path)
            self.assertEqual(p.name, "pr-reviewer.md")

    def test_empty_text_is_noop(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            p = append_insight("engineer", "IMPL", "", cwd=td_path)
            self.assertFalse(p.exists())

    def test_multiline_takes_first_line(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            p = append_insight("engineer", "IMPL", "한 줄\n무시될 두 번째 줄", cwd=td_path)
            content = p.read_text()
            self.assertIn("한 줄", content)
            self.assertNotIn("무시될 두 번째 줄", content)

    def test_fifo_cap_drops_oldest(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            for i in range(INSIGHT_FIFO_CAP + 3):
                append_insight("engineer", "IMPL", f"item{i:03d}", cwd=td_path)
            content = insights_path("engineer", "IMPL", cwd=td_path).read_text()
            entries = [line for line in content.splitlines() if line.startswith("- ")]
            self.assertEqual(len(entries), INSIGHT_FIFO_CAP)
            # 가장 오래된 item000/001/002 제거됨 (3자리 zero-padded 정확 매칭)
            self.assertNotIn("item000", content)
            self.assertNotIn("item001", content)
            self.assertNotIn("item002", content)
            # 최신 entry 보존
            self.assertIn(f"item{INSIGHT_FIFO_CAP + 2:03d}", content)

    def test_agent_mode_separated_files(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            append_insight("engineer", "IMPL", "IMPL 전용", cwd=td_path)
            append_insight("engineer", "POLISH", "POLISH 전용", cwd=td_path)
            impl_content = insights_path("engineer", "IMPL", cwd=td_path).read_text()
            polish_content = insights_path("engineer", "POLISH", cwd=td_path).read_text()
            self.assertIn("IMPL 전용", impl_content)
            self.assertNotIn("POLISH 전용", impl_content)
            self.assertIn("POLISH 전용", polish_content)
            self.assertNotIn("IMPL 전용", polish_content)


class TestWorktreeNormalization(unittest.TestCase):
    """worktree 안 cwd → main repo root 정규화 (#306 개선점 5).

    worktree 진입 후에도 loop-insights 가 main repo root 에 저장돼야 함.
    ExitWorktree(remove) 시 누적분 손실 회피.
    """

    def test_insights_path_normalizes_worktree_to_main_root(self):
        with tempfile.TemporaryDirectory() as td:
            main_root = Path(td) / "main"
            worktree = main_root / ".claude" / "worktrees" / "wt1"
            main_root.mkdir(parents=True)
            worktree.mkdir(parents=True)

            with patch(
                "harness.loop_insights._resolve_project_root",
                return_value=main_root,
            ):
                p = insights_path("engineer", "IMPL", cwd=worktree)

            self.assertTrue(
                str(p).startswith(str(main_root.resolve()) + os.sep),
                f"insights_path={p} 가 main_root={main_root} 안이 아님",
            )
            self.assertIn(".claude/loop-insights", str(p))
            self.assertNotIn("worktrees/wt1", str(p))

    def test_append_findings_writes_to_main_root_not_worktree(self):
        """append_findings 가 worktree cwd 받아도 main repo root 에 저장."""
        with tempfile.TemporaryDirectory() as td:
            main_root = Path(td) / "main"
            worktree = main_root / ".claude" / "worktrees" / "wt1"
            main_root.mkdir(parents=True)
            worktree.mkdir(parents=True)

            with patch(
                "harness.loop_insights._resolve_project_root",
                return_value=main_root,
            ):
                append_findings(
                    "engineer", "IMPL",
                    ["worktree path leak detected"], [],
                    cwd=worktree,
                )

            worktree_path = worktree / ".claude" / "loop-insights" / "engineer-IMPL.md"
            self.assertFalse(worktree_path.exists())

            main_path = main_root / ".claude" / "loop-insights" / "engineer-IMPL.md"
            self.assertTrue(main_path.exists())
            self.assertIn("worktree path leak detected", main_path.read_text())

    def test_read_resolves_from_main_root_after_worktree_remove(self):
        """worktree 안에서 호출돼도 main_root 에서 read — ExitWorktree(remove) 후 영속성."""
        with tempfile.TemporaryDirectory() as td:
            main_root = Path(td) / "main"
            worktree = main_root / ".claude" / "worktrees" / "wt1"
            main_root.mkdir(parents=True)
            worktree.mkdir(parents=True)

            main_path = main_root / ".claude" / "loop-insights" / "architect.md"
            main_path.parent.mkdir(parents=True)
            main_path.write_text("# Loop Insights\ncontent X", encoding="utf-8")

            with patch(
                "harness.loop_insights._resolve_project_root",
                return_value=main_root,
            ):
                result = read("architect", cwd=worktree)

            self.assertIn("content X", result)


if __name__ == "__main__":
    unittest.main()

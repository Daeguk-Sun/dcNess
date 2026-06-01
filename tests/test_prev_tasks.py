"""test_prev_tasks — prev_tasks 모듈 단위 테스트 (#525).

Coverage:
    prev_tasks_path:
        - .claude/loop-insights/.prev-tasks.md 경로 규칙

    read:
        - 파일 없음 → ""
        - 파일 있음 → 내용 반환

    append:
        - 신규 파일 생성 + 한 줄 형식 (- slug: summary)
        - 누적 (순서 보존)
        - 같은 slug 재append → 직전 제거 + 최신 끝으로 이동 (재시도 중복 회피)
        - 빈 slug / 빈 summary → noop (파일 미생성)
        - multiline summary → 첫 줄만
        - FIFO cap 초과 → 가장 오래된 항목 제거

    reset:
        - 파일 삭제
        - 파일 없을 때 reset → 에러 없음

    worktree root 해석:
        - 하위 디렉토리 cwd 여도 같은 파일 (git 리포 환경)
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

from harness.prev_tasks import (
    prev_tasks_path,
    read,
    append,
    reset,
    PREV_TASKS_FIFO_CAP,
)


class TestPrevTasksPath(unittest.TestCase):
    def test_path_rule(self):
        p = prev_tasks_path(cwd=Path("/tmp"))
        self.assertEqual(p.name, ".prev-tasks.md")
        self.assertIn(".claude/loop-insights", str(p))


class TestRead(unittest.TestCase):
    def test_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(read(cwd=Path(td)), "")

    def test_existing_file_returns_content(self):
        with tempfile.TemporaryDirectory() as td:
            append("01-foo", "도메인 모델 추가", cwd=Path(td))
            self.assertIn("01-foo", read(cwd=Path(td)))


class TestAppend(unittest.TestCase):
    def test_creates_new_file_line_format(self):
        with tempfile.TemporaryDirectory() as td:
            append("01-domain", "pydantic 도메인 모델 추가", cwd=Path(td))
            p = prev_tasks_path(cwd=Path(td))
            self.assertTrue(p.exists())
            self.assertEqual(
                p.read_text(encoding="utf-8").strip(),
                "- 01-domain: pydantic 도메인 모델 추가",
            )

    def test_accumulates_in_order(self):
        with tempfile.TemporaryDirectory() as td:
            append("01-a", "first", cwd=Path(td))
            append("02-b", "second", cwd=Path(td))
            lines = read(cwd=Path(td)).splitlines()
            self.assertEqual(lines, ["- 01-a: first", "- 02-b: second"])

    def test_same_slug_reappend_moves_latest_to_end(self):
        with tempfile.TemporaryDirectory() as td:
            append("01-a", "first", cwd=Path(td))
            append("02-b", "second", cwd=Path(td))
            append("01-a", "retried", cwd=Path(td))  # 재시도
            lines = read(cwd=Path(td)).splitlines()
            # 01-a 직전 항목 제거 + 최신만, 끝으로 이동
            self.assertEqual(lines, ["- 02-b: second", "- 01-a: retried"])

    def test_empty_slug_noop(self):
        with tempfile.TemporaryDirectory() as td:
            append("", "summary", cwd=Path(td))
            self.assertFalse(prev_tasks_path(cwd=Path(td)).exists())

    def test_empty_summary_noop(self):
        with tempfile.TemporaryDirectory() as td:
            append("01-a", "   ", cwd=Path(td))
            self.assertFalse(prev_tasks_path(cwd=Path(td)).exists())

    def test_multiline_summary_first_line_only(self):
        with tempfile.TemporaryDirectory() as td:
            append("01-a", "first line\nsecond line\nthird", cwd=Path(td))
            self.assertEqual(read(cwd=Path(td)).strip(), "- 01-a: first line")

    def test_fifo_cap_drops_oldest(self):
        with tempfile.TemporaryDirectory() as td:
            for i in range(PREV_TASKS_FIFO_CAP + 5):
                append(f"{i:02d}-task", f"summary {i}", cwd=Path(td))
            lines = read(cwd=Path(td)).splitlines()
            self.assertEqual(len(lines), PREV_TASKS_FIFO_CAP)
            # 가장 오래된 5개 (00~04) 제거됨 → 05 부터 시작
            self.assertEqual(lines[0], "- 05-task: summary 5")
            self.assertEqual(lines[-1], f"- {PREV_TASKS_FIFO_CAP + 4:02d}-task: summary {PREV_TASKS_FIFO_CAP + 4}")


class TestReset(unittest.TestCase):
    def test_reset_removes_file(self):
        with tempfile.TemporaryDirectory() as td:
            append("01-a", "x", cwd=Path(td))
            self.assertTrue(prev_tasks_path(cwd=Path(td)).exists())
            reset(cwd=Path(td))
            self.assertFalse(prev_tasks_path(cwd=Path(td)).exists())

    def test_reset_missing_file_no_error(self):
        with tempfile.TemporaryDirectory() as td:
            reset(cwd=Path(td))  # 에러 안 나야


class TestWorktreeRootResolution(unittest.TestCase):
    """worktree / 하위 디렉토리 cwd 여도 main repo root 기준 저장 (#306 패턴 정합)."""

    def test_subdir_cwd_resolves_to_repo_root(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subdir = root / "src" / "deep"
            subdir.mkdir(parents=True)

            append("01-a", "from root", cwd=root)
            # 하위 디렉토리에서 read → 같은 파일 (γ-resolution)
            self.assertIn("01-a", read(cwd=subdir))
            # 경로가 repo root 기준인지
            self.assertEqual(
                prev_tasks_path(cwd=subdir), prev_tasks_path(cwd=root)
            )


if __name__ == "__main__":
    unittest.main()

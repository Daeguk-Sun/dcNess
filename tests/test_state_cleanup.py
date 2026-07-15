"""상태 위생 청소 테스트 — run 디렉토리 7d TTL + SessionStart 와이어링.

cleanup_stale_pid_files / cleanup_stale_runs 는 정의만 있고 호출처가 없었고,
run 디렉토리(prose/ledger)는 삭제 로직 자체가 없어 무한 누적이었다.
본 테스트는 (1) 신규 cleanup_stale_run_dirs 의 mtime 기준 판정과
(2) handle_session_start 가 청소 3종을 fail-open 으로 수행하는지 검증한다.
"""
from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from harness.hooks import handle_session_start
from harness.session_state import (
    DEFAULT_RUN_DIR_TTL_SEC,
    cleanup_stale_run_dirs,
    read_live,
    transition,
)

SID = "11111111-2222-4333-8444-555555555555"


def _set_old_mtime(path: Path, age_sec: float) -> None:
    old = time.time() - age_sec
    os.utime(path, (old, old))


class CleanupStaleRunDirsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name) / ".claude" / "harness-state"

    def tearDown(self) -> None:
        self._td.cleanup()

    def _make_run_dir(self, sid: str, rid: str) -> Path:
        rdir = self.base / ".sessions" / sid / "runs" / rid
        rdir.mkdir(parents=True)
        (rdir / "engineer.md").write_text("prose\n", encoding="utf-8")
        return rdir

    def _age_run_dir(self, rdir: Path, age_sec: float) -> None:
        for child in rdir.iterdir():
            _set_old_mtime(child, age_sec)
        _set_old_mtime(rdir, age_sec)

    def test_removes_only_expired_run_dirs(self) -> None:
        old = self._make_run_dir(SID, "run-aaaaaaaa")
        recent = self._make_run_dir(SID, "run-bbbbbbbb")
        self._age_run_dir(old, DEFAULT_RUN_DIR_TTL_SEC + 3600)

        removed = cleanup_stale_run_dirs(base_dir=self.base)

        self.assertEqual(removed, 1)
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())

    def test_recent_child_write_preserves_old_dir(self) -> None:
        # 디렉토리 mtime 은 오래됐어도 직계 파일에 7일 내 쓰기가 있으면 보존.
        rdir = self._make_run_dir(SID, "run-cccccccc")
        self._age_run_dir(rdir, DEFAULT_RUN_DIR_TTL_SEC + 3600)
        (rdir / "impl-validator.md").write_text("late prose\n", encoding="utf-8")

        removed = cleanup_stale_run_dirs(base_dir=self.base)

        self.assertEqual(removed, 0)
        self.assertTrue(rdir.exists())

    def test_spans_all_sessions(self) -> None:
        other_sid = "99999999-8888-4777-8666-555555555555"
        old_a = self._make_run_dir(SID, "run-dddddddd")
        old_b = self._make_run_dir(other_sid, "run-eeeeeeee")
        self._age_run_dir(old_a, DEFAULT_RUN_DIR_TTL_SEC + 3600)
        self._age_run_dir(old_b, DEFAULT_RUN_DIR_TTL_SEC + 3600)

        removed = cleanup_stale_run_dirs(base_dir=self.base)

        self.assertEqual(removed, 2)

    def test_missing_sessions_dir_returns_zero(self) -> None:
        self.assertEqual(cleanup_stale_run_dirs(base_dir=self.base), 0)


class SessionStartCleanupWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name) / ".claude" / "harness-state"

    def tearDown(self) -> None:
        self._td.cleanup()

    def _start(self) -> int:
        return handle_session_start(
            {"session_id": SID}, cc_pid=12345, base_dir=self.base
        )

    def test_session_start_removes_stale_pid_and_run_dir(self) -> None:
        stale_pid = self.base / ".by-pid" / "777"
        stale_pid.parent.mkdir(parents=True)
        stale_pid.write_text(SID, encoding="utf-8")
        _set_old_mtime(stale_pid, 25 * 3600)

        stale_run = self.base / ".sessions" / SID / "runs" / "run-ffffffff"
        stale_run.mkdir(parents=True)
        (stale_run / "engineer.md").write_text("old\n", encoding="utf-8")
        for p in (stale_run / "engineer.md", stale_run):
            _set_old_mtime(p, DEFAULT_RUN_DIR_TTL_SEC + 3600)

        rc = self._start()

        self.assertEqual(rc, 0)
        self.assertFalse(stale_pid.exists())
        self.assertFalse(stale_run.exists())
        # 본 세션의 by-pid 파일(방금 작성)은 살아 있어야 한다.
        self.assertTrue((self.base / ".by-pid" / "12345").exists())

    def test_session_start_removes_expired_tombstone_slot(self) -> None:
        with mock.patch(
            "harness.session_state._now_iso",
            return_value="2020-01-01T00:00:00+00:00",
        ):
            transition(
                SID,
                "run_started",
                run_id="run-abcd1234",
                entry_point="impl",
                base_dir=self.base,
            )

        rc = self._start()

        self.assertEqual(rc, 0)
        live_after = read_live(SID, base_dir=self.base)
        self.assertNotIn("run-abcd1234", live_after.get("active_runs", {}))

    def test_cleanup_failure_does_not_block_session_start(self) -> None:
        with mock.patch(
            "harness.hooks.cleanup_stale_run_dirs",
            side_effect=RuntimeError("simulated cleanup bug"),
        ):
            rc = self._start()
        self.assertEqual(rc, 0)
        self.assertTrue((self.base / ".by-pid" / "12345").exists())


if __name__ == "__main__":
    unittest.main()

"""run 요약 기록 보존 계약 (#1331).

run 폴더(prose/ledger)는 7일 뒤 삭제되지만, 프로젝트 단위 요약 기록은 남아
cross-project outcome scorecard 가 과거 run 을 계속 집계한다.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from harness import session_state as state
from harness.outcome_scorecard import build_scorecard

SID = "11111111-2222-4333-8444-555555555555"
RID = "run-aaaa0001"


class RunSummaryRetentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.project = self.root / "project"
        self.base = self.project / ".claude" / "harness-state"
        self.projects_file = self.root / "projects.json"
        self.projects_file.write_text(
            json.dumps({"version": 1, "projects": [str(self.project)]}), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self._td.cleanup()

    def _run(self, rid: str = RID, *, pr_number: int = 7) -> Path:
        state.transition(SID, "run_started", run_id=rid, base_dir=self.base, entry_point="impl")
        run_dir = state.run_dir(SID, rid, base_dir=self.base, create=True)
        prose = "독립 검토 결과\nFAIL\n"
        prose_path = run_dir / "impl-validator.md"
        prose_path.write_text(prose, encoding="utf-8")
        state.transition(
            SID,
            "step_completed",
            run_id=rid,
            base_dir=self.base,
            agent="impl-validator",
            mode=None,
            enum="PROSE_LOGGED",
            prose=prose,
            prose_path=prose_path,
        )
        url = f"https://example.invalid/repo/pull/{pr_number}"
        for event in ("pr_created", "pr_merged"):
            state.transition(
                SID,
                "ledger_checkpoint",
                run_id=rid,
                base_dir=self.base,
                event=event,
                pr_number=pr_number,
                url=url,
            )
        state.transition(SID, "run_completed", run_id=rid, base_dir=self.base)
        return run_dir

    def _expire(self, run_dir: Path) -> None:
        old = time.time() - state.DEFAULT_RUN_DIR_TTL_SEC - 3600
        for child in run_dir.iterdir():
            os.utime(child, (old, old))
        os.utime(run_dir, (old, old))

    def _process(self) -> dict:
        return build_scorecard(self.projects_file, redact_paths=True)["process_evidence"]

    def _summaries(self) -> list[dict]:
        path = self.base / "run-summaries.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def test_deleted_run_dir_stays_in_scorecard_through_summary(self) -> None:
        run_dir = self._run()
        self._expire(run_dir)
        self.assertEqual(state.cleanup_stale_run_dirs(base_dir=self.base), 1)
        self.assertFalse(run_dir.exists())

        process = self._process()
        self.assertEqual(process["finished_runs"]["numerator"], 1)
        self.assertEqual(process["finished_runs"]["denominator"], 1)
        self.assertEqual(process["pr_merge_success"]["numerator"], 1)
        self.assertEqual(process["pr_merge_success"]["denominator"], 1)
        self.assertEqual(process["impl_validator_rework"]["numerator"], 1)

        serialized = json.dumps(self._summaries(), ensure_ascii=False)
        self.assertNotIn(str(self.project), serialized)
        self.assertNotIn("독립 검토 결과", serialized)

    def test_run_in_both_run_dir_and_summary_is_counted_once(self) -> None:
        self._run()
        self.assertTrue(self._summaries())

        process = self._process()
        self.assertEqual(process["finished_runs"]["numerator"], 1)
        self.assertEqual(process["finished_runs"]["denominator"], 1)
        self.assertEqual(process["pr_merge_success"]["denominator"], 1)

    def test_summary_write_failure_does_not_block_run_completion(self) -> None:
        (self.base / "run-summaries.jsonl").mkdir(parents=True)
        run_dir = self._run()

        events = [json.loads(line) for line in (run_dir / "ledger.jsonl").read_text().splitlines()]
        self.assertEqual(events[-1]["event"], "run_finished")


if __name__ == "__main__":
    unittest.main()

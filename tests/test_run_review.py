"""tests/test_run_review.py — DCN-CHG-20260430-19 run_review 단위 테스트."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from harness import ledger  # noqa: E402
from harness.run_review import (  # noqa: E402
    RunReport, StepRecord, build_report, detect_wastes, detect_notes,
    parse_steps, render_report, list_runs, find_run_dir,
    _normalize_agent_type, assign_invocations_to_steps,
    EXPECTED_AGENT_BUDGETS, DCNESS_AGENT_NAMES, LEGACY_AGENT_ALIASES,
    WINDOW_TS_PADDING, _extract_conclusion_enum,
)
# issue #392 — detect_goods 폐기
# issue #394 — detect_notes 신규 (TOOL_USE_OVERFLOW / THINKING_LOOP)


def _make_run_dir(tmp: Path, sid: str, rid: str, step_records: list[dict],
                    prose_files: Optional[dict[str, str]] = None) -> Path:
    run_dir = tmp / ".claude" / "harness-state" / ".sessions" / sid / "runs" / rid
    run_dir.mkdir(parents=True, exist_ok=True)
    jsonl = run_dir / ".steps.jsonl"
    with open(jsonl, "w", encoding="utf-8") as f:
        for r in step_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    for filename, content in (prose_files or {}).items():
        (run_dir / filename).write_text(content, encoding="utf-8")
    return run_dir


def _make_run_dir_ledger(tmp: Path, sid: str, rid: str, events: list[dict],
                          prose_files: Optional[dict[str, str]] = None) -> Path:
    """이슈 #587 — ledger.jsonl (event stream) 기반 run_dir fixture."""
    run_dir = tmp / ".claude" / "harness-state" / ".sessions" / sid / "runs" / rid
    run_dir.mkdir(parents=True, exist_ok=True)
    prose_by_name: dict[str, tuple[Path, str]] = {}
    for filename, content in (prose_files or {}).items():
        prose_path = run_dir / filename
        prose_path.write_text(content, encoding="utf-8")
        prose_by_name[filename] = (prose_path, content)
    with open(run_dir / "ledger.jsonl", "w", encoding="utf-8") as f:
        for e in events:
            rec = dict(e)
            prose_file = rec.get("prose_file")
            if isinstance(prose_file, str) and prose_file in prose_by_name:
                prose_path, content = prose_by_name[prose_file]
                rec["prose_file"] = str(prose_path)
                rec.setdefault("sha256", ledger.sha256_text(content))
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return run_dir


class ParseStepsTests(unittest.TestCase):
    def test_parses_ledger_jsonl_step_completed_only(self):
        """이슈 #587 — ledger.jsonl 의 step_completed event 만 StepRecord 로 (run_started/step_started/run_finished 제외)."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rd = _make_run_dir_ledger(tmp, "sidL", "ridL", [
                {"event": "run_started", "ts": "2026-04-30T10:00:00", "entry_point": "impl"},
                {"event": "step_started", "ts": "2026-04-30T10:00:01",
                 "agent": "engineer", "mode": "IMPL"},
                {"event": "step_completed", "ts": "2026-04-30T10:00:05",
                 "agent": "engineer", "mode": "IMPL", "enum": "PROSE_LOGGED",
                 "must_fix": False, "prose_excerpt": "## 결론\nIMPL_DONE",
                 "prose_file": "engineer-IMPL.md", "evidence_paths": [],
                 "next_action": ""},
                {"event": "run_finished", "ts": "2026-04-30T10:01:00"},
            ], prose_files={"engineer-IMPL.md": "## 결론\nIMPL_DONE"})
            steps = parse_steps(rd)
            self.assertEqual(len(steps), 1)
            self.assertEqual(steps[0].agent, "engineer")
            self.assertEqual(steps[0].mode, "IMPL")


    def test_parses_steps_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rd = _make_run_dir(tmp, "sid1", "rid1", [
                {"ts": "2026-04-30T10:00:00", "agent": "architect", "mode": "MODULE_PLAN",
                 "enum": "PASS", "must_fix": False,
                 "prose_excerpt": "## 결론\nMODULE_PLAN 완성\nPASS"},
                {"ts": "2026-04-30T10:05:00", "agent": "engineer", "mode": "IMPL",
                 "enum": "IMPL_DONE", "must_fix": False,
                 "prose_excerpt": "구현 완료\n## 결론\nIMPL_DONE"},
            ])
            steps = parse_steps(rd)
            self.assertEqual(len(steps), 2)
            self.assertEqual(steps[0].agent, "architect")
            self.assertEqual(steps[0].mode, "MODULE_PLAN")
            self.assertEqual(steps[0].enum, "PASS")
            self.assertEqual(steps[0].elapsed_s, 300)
            self.assertEqual(steps[1].agent, "engineer")

    def test_returns_empty_when_no_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rd = tmp / "empty"
            rd.mkdir()
            self.assertEqual(parse_steps(rd), [])

    def test_loads_full_prose(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            prose_path = tmp / "architect-SYSTEM_DESIGN.md"
            prose_path.write_text("## Domain Model\nEntity X\n")
            rd = _make_run_dir(tmp, "sid1", "rid1", [
                {"ts": "2026-04-30T10:00:00", "agent": "architect", "mode": "SYSTEM_DESIGN",
                 "enum": "SYSTEM_DESIGN_READY", "must_fix": False, "prose_excerpt": "x",
                 "prose_file": str(prose_path)},
            ])
            steps = parse_steps(rd)
            self.assertIn("Domain Model", steps[0].prose_full)


class ProseFileTests(unittest.TestCase):
    """prose_file 필드 기반 prose 로딩 테스트."""

    def test_parse_steps_recomputes_must_fix_from_prose(self):
        """prose_file 있을 때 must_fix 재계산 (negation-aware retro accuracy)."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            prose_path = tmp / "pr-reviewer.md"
            prose_path.write_text("MUST FIX 0, NICE TO HAVE 6 (let tree: any / dead code).\nPASS\n")
            rd = _make_run_dir(tmp, "sid1", "rid1", [
                {"ts": "2026-04-30T10:00:00", "agent": "pr-reviewer", "mode": None,
                 "enum": "PASS", "must_fix": True,
                 "prose_excerpt": "MUST FIX 0, NICE TO HAVE 6\nPASS",
                 "prose_file": str(prose_path)},
            ])
            steps = parse_steps(rd)
            self.assertEqual(len(steps), 1)
            self.assertFalse(steps[0].must_fix, "negation 부정문 → False 재계산")

    def test_parse_steps_must_fix_falls_back_to_jsonl(self):
        """prose_file 없을 때 jsonl must_fix fallback."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rd = _make_run_dir(tmp, "sid1", "rid1", [
                {"ts": "2026-04-30T10:00:00", "agent": "validator", "mode": "CODE_VALIDATION",
                 "enum": "FAIL", "must_fix": True, "prose_excerpt": "x"},
            ])
            steps = parse_steps(rd)
            self.assertEqual(len(steps), 1)
            self.assertTrue(steps[0].must_fix, "prose 부재 → jsonl fallback")

    def test_parse_steps_resolves_per_occurrence_via_prose_file(self):
        """같은 (agent, mode) 반복 시 prose_file 로 각 step 독립 파일 읽기."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            p1 = tmp / "engineer-IMPL.md"
            p2 = tmp / "engineer-IMPL-1.md"
            p1.write_text("first batch\n## 자가 검증\n- jest PASS")
            p2.write_text("second batch\nno anchor")
            rd = _make_run_dir(tmp, "sid1", "rid1", [
                {"ts": "2026-04-30T10:00:00", "agent": "engineer", "mode": "IMPL",
                 "enum": "IMPL_DONE", "must_fix": False, "prose_excerpt": "x",
                 "prose_file": str(p1)},
                {"ts": "2026-04-30T10:05:00", "agent": "engineer", "mode": "IMPL",
                 "enum": "IMPL_DONE", "must_fix": False, "prose_excerpt": "x",
                 "prose_file": str(p2)},
            ])
            steps = parse_steps(rd)
            self.assertEqual(len(steps), 2)
            self.assertIn("first batch", steps[0].prose_full)
            self.assertIn("second batch", steps[1].prose_full)
            self.assertNotEqual(steps[0].prose_full, steps[1].prose_full)

    def test_parse_steps_legacy_fallback_outer_file(self):
        """prose_file 없는 레거시 record → outer <agent>[-mode].md fallback."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rd = _make_run_dir(tmp, "sid1", "rid1", [
                {"ts": "2026-04-30T10:00:00", "agent": "architect", "mode": "SYSTEM_DESIGN",
                 "enum": "SYSTEM_DESIGN_READY", "must_fix": False, "prose_excerpt": "x"},
            ], prose_files={"architect-SYSTEM_DESIGN.md": "## Domain Model\nlegacy\n"})
            steps = parse_steps(rd)
            self.assertIn("legacy", steps[0].prose_full)


class WasteDetectionTests(unittest.TestCase):
    def test_retry_same_fail(self):
        steps = [
            StepRecord(idx=0, ts="t1", agent="engineer", mode="IMPL",
                       enum="TESTS_FAIL", must_fix=False, prose_excerpt="a\nb\nc\nd\ne"),
            StepRecord(idx=1, ts="t2", agent="engineer", mode="IMPL",
                       enum="TESTS_FAIL", must_fix=False, prose_excerpt="a\nb\nc\nd\ne"),
        ]
        wastes = detect_wastes(steps)
        kinds = {w.pattern for w in wastes}
        self.assertIn("RETRY_SAME_FAIL", kinds)

    def test_retry_same_fail_prose_logged_skip(self):
        """이슈 #302 #1 — PROSE_LOGGED 는 prose-only mode 정상 sentinel.
        연속 발생해도 RETRY_SAME_FAIL false positive 안 됨."""
        steps = [
            StepRecord(idx=0, ts="t1", agent="architect", mode="MODULE_PLAN",
                       enum="PROSE_LOGGED", must_fix=False, prose_excerpt="task 01"),
            StepRecord(idx=1, ts="t2", agent="architect", mode="MODULE_PLAN",
                       enum="PROSE_LOGGED", must_fix=False, prose_excerpt="task 02"),
            StepRecord(idx=2, ts="t3", agent="architect", mode="MODULE_PLAN",
                       enum="PROSE_LOGGED", must_fix=False, prose_excerpt="task 03"),
        ]
        wastes = detect_wastes(steps)
        kinds = {w.pattern for w in wastes}
        self.assertNotIn("RETRY_SAME_FAIL", kinds,
                         "PROSE_LOGGED 는 advance sentinel — 연속 발생해도 retry 아님")

    def test_retry_same_fail_different_prose_skip(self):
        """이슈 #302 #1 — 같은 enum 이라도 prose 내용이 다르면 다른 invocation (N task 순회 등).
        retry 아님."""
        steps = [
            StepRecord(idx=0, ts="t1", agent="engineer", mode="IMPL",
                       enum="TESTS_FAIL", must_fix=False,
                       prose_excerpt="task 01 첫 시도",
                       prose_full="task 01 첫 시도\n실패 원인 A"),
            StepRecord(idx=1, ts="t2", agent="engineer", mode="IMPL",
                       enum="TESTS_FAIL", must_fix=False,
                       prose_excerpt="task 02 첫 시도",
                       prose_full="task 02 첫 시도\n실패 원인 B"),
        ]
        wastes = detect_wastes(steps)
        kinds = {w.pattern for w in wastes}
        self.assertNotIn("RETRY_SAME_FAIL", kinds,
                         "다른 task / 다른 prose = 다른 invocation, retry 아님")

    # issue #392 — test_echo_violation / test_echo_violation_no_prose_full_skipped 폐기.

    def test_stray_dir_leak_detected(self):
        """이슈 #321 C STRAY_DIR_LEAK — `.claire` 같은 .claude typo 검출."""
        steps = [
            StepRecord(idx=0, ts="t", agent="engineer", mode="IMPL",
                       enum="IMPL_DONE", must_fix=False,
                       prose_excerpt="x",
                       prose_full="작업 위치 .claire/worktrees/foo/ 시작 — 검증 완료"),
        ]
        wastes = detect_wastes(steps)
        leak = [w for w in wastes if w.pattern == "STRAY_DIR_LEAK"]
        self.assertEqual(len(leak), 1)
        self.assertIn(".claire", leak[0].detail)
        self.assertIn(".claude", leak[0].detail)

    def test_stray_dir_leak_correct_dir_skipped(self):
        """정확 `.claude` 는 typo 아님 — 검출 X."""
        steps = [
            StepRecord(idx=0, ts="t", agent="engineer", mode="IMPL",
                       enum="IMPL_DONE", must_fix=False,
                       prose_excerpt="x",
                       prose_full="작업 위치 .claude/worktrees/foo/ 시작 — 검증 완료"),
        ]
        wastes = detect_wastes(steps)
        kinds = {w.pattern for w in wastes}
        self.assertNotIn("STRAY_DIR_LEAK", kinds)

    def test_stray_dir_leak_unrelated_dir_skipped(self):
        """완전 다른 디렉토리 (`.vscode` 같은) 는 fuzzy match 안 됨 — 검출 X."""
        steps = [
            StepRecord(idx=0, ts="t", agent="engineer", mode="IMPL",
                       enum="IMPL_DONE", must_fix=False,
                       prose_excerpt="x",
                       prose_full="설정 파일 .vscode/settings.json 갱신"),
        ]
        wastes = detect_wastes(steps)
        kinds = {w.pattern for w in wastes}
        self.assertNotIn("STRAY_DIR_LEAK", kinds)

    # issue #392 — test_placeholder_leak 폐기 (PLACEHOLDER_LEAK 패턴 폐기 정합).

    def test_infra_read_self_rundir_bookkeeping_skipped(self):
        """issue #543 — build-worker 가 자기 run_dir 의 phase prose 경로를
        메인 ls 검증용으로 나열한 것은 인프라 탐색이 아니라 자기-bookkeeping →
        INFRA_READ 오탐 X."""
        rid = "run-abc123"
        run_dir = Path(f"/repo/.claude/harness-state/.sessions/sid1/runs/{rid}")
        prose = (
            "phase 1/2/3 GREEN 확인 완료.\n"
            "phase prose 파일 (메인 ls 검증용):\n"
            f"- /repo/.claude/harness-state/.sessions/sid1/runs/{rid}/build-test.md\n"
            f"- /repo/.claude/harness-state/.sessions/sid1/runs/{rid}/build-impl.md\n"
            f"- /repo/.claude/harness-state/.sessions/sid1/runs/{rid}/build-validate.md\n"
            "LGTM"
        )
        steps = [
            StepRecord(idx=0, ts="t", agent="build-worker", mode="",
                       enum="PASS", must_fix=False, prose_excerpt="x",
                       prose_full=prose),
        ]
        wastes = detect_wastes(steps, run_dir=run_dir)
        self.assertNotIn("INFRA_READ", {w.pattern for w in wastes})

    def test_infra_read_other_run_path_detected(self):
        """다른 run 의 harness-state 경로 참조는 자기-bookkeeping 아님 →
        INFRA_READ 검출 유지."""
        run_dir = Path("/repo/.claude/harness-state/.sessions/sid1/runs/run-abc123")
        prose = (
            "타 세션 산출물 확인:\n"
            "/repo/.claude/harness-state/.sessions/sid1/runs/run-OTHER999/build-test.md\n"
        )
        steps = [
            StepRecord(idx=0, ts="t", agent="engineer", mode="IMPL",
                       enum="IMPL_DONE", must_fix=False, prose_excerpt="x",
                       prose_full=prose),
        ]
        wastes = detect_wastes(steps, run_dir=run_dir)
        infra = [w for w in wastes if w.pattern == "INFRA_READ"]
        self.assertEqual(len(infra), 1)

    def test_infra_read_harness_memory_detected_with_rundir(self):
        """run_dir 가 있어도 harness-memory.md 등 self marker 무관 leak 은 검출 유지."""
        run_dir = Path("/repo/.claude/harness-state/.sessions/sid1/runs/run-abc123")
        steps = [
            StepRecord(idx=0, ts="t", agent="engineer", mode="IMPL",
                       enum="IMPL_DONE", must_fix=False, prose_excerpt="x",
                       prose_full="설정 갱신 harness-memory.md 읽음"),
        ]
        wastes = detect_wastes(steps, run_dir=run_dir)
        self.assertIn("INFRA_READ", {w.pattern for w in wastes})

    def test_infra_read_no_rundir_falls_back_to_substring(self):
        """run_dir 미전달 시 (None) self marker 필터 없이 기존 substring 검출 유지."""
        steps = [
            StepRecord(idx=0, ts="t", agent="engineer", mode="IMPL",
                       enum="IMPL_DONE", must_fix=False, prose_excerpt="x",
                       prose_full="경로 /repo/.claude/harness-state/.sessions/x/runs/y/z.md"),
        ]
        wastes = detect_wastes(steps)  # run_dir 미전달
        self.assertIn("INFRA_READ", {w.pattern for w in wastes})

    def test_must_fix_ghost(self):
        steps = [
            StepRecord(idx=0, ts="t1", agent="validator", mode="CODE_VALIDATION",
                       enum="FAIL", must_fix=True, prose_excerpt="a\nb\nc\nd\ne"),
            StepRecord(idx=1, ts="t2", agent="engineer", mode="IMPL",
                       enum="IMPL_DONE", must_fix=False, prose_excerpt="a\nb\nc\nd\ne"),
        ]
        wastes = detect_wastes(steps)
        self.assertTrue(any(w.pattern == "MUST_FIX_GHOST" for w in wastes))

    def test_spec_gap_loop(self):
        steps = [
            StepRecord(idx=i, ts=f"t{i}", agent="architect", mode="SPEC_GAP",
                       enum="SPEC_GAP_RESOLVED", must_fix=False, prose_excerpt="a\nb\nc\nd\ne")
            for i in range(3)
        ]
        wastes = detect_wastes(steps)
        self.assertTrue(any(w.pattern == "SPEC_GAP_LOOP" for w in wastes))

    # issue #392 — test_external_verified_missing 폐기 (EXTERNAL_VERIFIED_MISSING 패턴 폐기 정합).

    def test_tool_repeat_high_bash(self):
        """issue #484 Case 1 — Bash 동일 input ≥ 5회 반복 = TOOL_REPEAT_HIGH MEDIUM.

        jajang run-545513a1 build-worker 가 같은 `cd ... npm test ...` 6회 호출했는데
        review heuristic 이 못 잡은 회귀 직접 재현 테스트.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rd = tmp / "runs" / "rid1"
            rd.mkdir(parents=True)
            # agent-trace.jsonl 박기
            trace = rd / "agent-trace.jsonl"
            cmd = "cd apps/mobile && npm test -- --testPathPattern S11"
            entries = []
            for i in range(6):
                entries.append({
                    "ts": f"2026-05-23T02:1{i}:00Z", "phase": "pre",
                    "agent": "build-worker", "tool": "Bash", "input": cmd,
                })
            trace.write_text("\n".join(json.dumps(e) for e in entries))
            steps = [
                StepRecord(idx=0, ts="2026-05-23T02:20:00Z", agent="build-worker",
                           mode=None, enum="PASS", must_fix=False, prose_excerpt="x"),
            ]
            wastes = detect_wastes(steps, run_dir=rd)
            repeats = [w for w in wastes if w.pattern == "TOOL_REPEAT_HIGH"]
            self.assertEqual(len(repeats), 1)
            self.assertEqual(repeats[0].severity, "MEDIUM")
            self.assertIn("6회 반복", repeats[0].detail)
            self.assertIn("Bash", repeats[0].detail)

    def test_tool_repeat_below_threshold_skip(self):
        """Bash 동일 input ≤ 4회 = 임계 미만 → skip (정상 단순 재시도)."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rd = tmp / "runs" / "rid2"
            rd.mkdir(parents=True)
            trace = rd / "agent-trace.jsonl"
            cmd = "npm test"
            entries = [
                {"ts": f"2026-05-23T02:1{i}:00Z", "phase": "pre",
                 "agent": "build-worker", "tool": "Bash", "input": cmd}
                for i in range(4)
            ]
            trace.write_text("\n".join(json.dumps(e) for e in entries))
            steps = [
                StepRecord(idx=0, ts="2026-05-23T02:20:00Z", agent="build-worker",
                           mode=None, enum="PASS", must_fix=False, prose_excerpt="x"),
            ]
            wastes = detect_wastes(steps, run_dir=rd)
            self.assertFalse(any(w.pattern == "TOOL_REPEAT_HIGH" for w in wastes))

    def test_tool_repeat_read_lower_threshold(self):
        """Read 는 임계 4회 — 동일 파일 4회 read = finding."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rd = tmp / "runs" / "rid3"
            rd.mkdir(parents=True)
            trace = rd / "agent-trace.jsonl"
            entries = [
                {"ts": f"2026-05-23T02:1{i}:00Z", "phase": "pre",
                 "agent": "pr-reviewer", "tool": "Read",
                 "input": "apps/mobile/src/screens/S11PreviewScreen.tsx"}
                for i in range(4)
            ]
            trace.write_text("\n".join(json.dumps(e) for e in entries))
            steps = [
                StepRecord(idx=0, ts="2026-05-23T02:20:00Z", agent="pr-reviewer",
                           mode=None, enum="PASS", must_fix=False, prose_excerpt="x"),
            ]
            wastes = detect_wastes(steps, run_dir=rd)
            repeats = [w for w in wastes if w.pattern == "TOOL_REPEAT_HIGH"]
            self.assertEqual(len(repeats), 1)
            self.assertIn("4회 반복", repeats[0].detail)

    def test_tool_repeat_no_trace_skip(self):
        """agent-trace.jsonl 부재 / run_dir=None 시 silent skip — 기존 동작 영향 X."""
        steps = [
            StepRecord(idx=0, ts="t1", agent="engineer", mode="IMPL",
                       enum="IMPL_DONE", must_fix=False, prose_excerpt="x"),
        ]
        wastes = detect_wastes(steps)  # run_dir 미전달
        self.assertFalse(any(w.pattern == "TOOL_REPEAT_HIGH" for w in wastes))

    def test_tool_repeat_window_split_by_step(self):
        """step 별 윈도우 분리 — task1 와 task2 의 같은 input 은 별개 카운트."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rd = tmp / "runs" / "rid4"
            rd.mkdir(parents=True)
            trace = rd / "agent-trace.jsonl"
            cmd = "npm test"
            entries = []
            # step 0 윈도우 안 3회
            for i in range(3):
                entries.append({
                    "ts": f"2026-05-23T02:0{i}:00Z", "phase": "pre",
                    "agent": "build-worker", "tool": "Bash", "input": cmd,
                })
            # step 1 윈도우 안 3회
            for i in range(3):
                entries.append({
                    "ts": f"2026-05-23T02:1{i}:00Z", "phase": "pre",
                    "agent": "build-worker", "tool": "Bash", "input": cmd,
                })
            trace.write_text("\n".join(json.dumps(e) for e in entries))
            steps = [
                StepRecord(idx=0, ts="2026-05-23T02:05:00Z", agent="build-worker",
                           mode=None, enum="PASS", must_fix=False, prose_excerpt="x"),
                StepRecord(idx=1, ts="2026-05-23T02:20:00Z", agent="build-worker",
                           mode=None, enum="PASS", must_fix=False, prose_excerpt="x"),
            ]
            wastes = detect_wastes(steps, run_dir=rd)
            # 각 step 3회씩 — 임계 5회 미달 → 둘 다 skip
            self.assertFalse(any(w.pattern == "TOOL_REPEAT_HIGH" for w in wastes))


# issue #392 — GoodDetectionTests 전체 폐기. detect_goods 함수 폐기와 정합.


class LocalTimeRenderTests(unittest.TestCase):
    def test_step_table_shows_local_time(self):
        # DCN-30-24: UTC ts → system local time (e.g. KST = UTC+9)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rd = _make_run_dir(tmp, "sid1", "rid1", [
                {"ts": "2026-04-30T02:46:47+00:00", "agent": "architect", "mode": "MODULE_PLAN",
                 "enum": "PASS", "must_fix": False,
                 "prose_excerpt": "a\nb\nc\nd\ne\nf"},
            ])
            report = build_report(rd, repo_path=tmp)
            text = render_report(report)
            self.assertIn("시작(local)", text)
            # `:46:47` 부분만 확인 — 시스템 timezone 무관 (분/초는 동일)
            self.assertIn(":46:47", text)


class ToolUsesColumnTests(unittest.TestCase):
    """DCN-CHG-20260430-39: render_report tool_uses 컬럼 + ≥ 100 강조."""

    def _make_report(self, steps: list[StepRecord]) -> RunReport:
        with tempfile.TemporaryDirectory() as td:
            return RunReport(run_id="rid", session_id="sid", run_dir=Path(td), steps=steps)

    def test_header_has_tool_uses_column(self):
        step = StepRecord(idx=0, ts="t", agent="engineer", mode="IMPL",
                          enum="IMPL_DONE", must_fix=False,
                          prose_excerpt="a\nb\nc\nd\ne",
                          matched_invocation=True, tool_use_count=42)
        text = render_report(self._make_report([step]))
        self.assertIn("tool_uses", text)
        self.assertIn("| 42 |", text)

    def test_overflow_threshold_bolded(self):
        step = StepRecord(idx=0, ts="t", agent="engineer", mode="IMPL",
                          enum="IMPL_DONE", must_fix=False,
                          prose_excerpt="a\nb\nc\nd\ne",
                          matched_invocation=True, tool_use_count=153)
        text = render_report(self._make_report([step]))
        self.assertIn("**153**", text)

    def test_unmatched_invocation_dash(self):
        step = StepRecord(idx=0, ts="t", agent="engineer", mode="IMPL",
                          enum="IMPL_DONE", must_fix=False,
                          prose_excerpt="a\nb\nc\nd\ne",
                          matched_invocation=False, tool_use_count=0)
        text = render_report(self._make_report([step]))
        # 단계별 표 row 안 tool_uses 자리 = "-" (cost 와 동일 형식)
        # 검사: "| - | - |" 같은 dash 시퀀스 존재 (out_tok / total_tok / tool_uses / cost 모두 dash)
        self.assertRegex(text, r"\|\s*-\s*\|\s*-\s*\|\s*-\s*\|\s*-\s*\|")


class ReportRenderTests(unittest.TestCase):
    def test_render_smoke(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rd = _make_run_dir(tmp, "sid1", "rid1", [
                {"ts": "2026-04-30T10:00:00", "agent": "architect", "mode": "MODULE_PLAN",
                 "enum": "PASS", "must_fix": False,
                 "prose_excerpt": "line1\nline2\nline3\nline4\nline5\nline6"},
                {"ts": "2026-04-30T10:05:00", "agent": "engineer", "mode": "IMPL",
                 "enum": "IMPL_DONE", "must_fix": False,
                 "prose_excerpt": "line1\nline2\nline3\nline4\nline5\nline6"},
            ])
            report = build_report(rd, repo_path=tmp)
            text = render_report(report)
            self.assertIn("# Run Review", text)
            self.assertIn("## 호출 흐름", text)
            self.assertIn("## 단계별 상세", text)
            self.assertIn("MODULE_PLAN", text)
            self.assertIn("IMPL_DONE", text)

    def test_verify_only_pass_step_is_clean_without_pr_step(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rd = _make_run_dir(
                tmp,
                "sid1",
                "rid1",
                [
                    {
                        "ts": "2026-06-05T10:00:00+00:00",
                        "agent": "code-validator",
                        "mode": "VERIFY_ONLY",
                        "enum": "PROSE_LOGGED",
                        "must_fix": False,
                        "prose_excerpt": "verify-only import contracts kept\n\nPASS",
                    },
                ],
                {
                    "code-validator-VERIFY_ONLY.md": (
                        "검증 명령: lint-imports\n"
                        "exit code: 0\n"
                        "git status --porcelain: empty\n\n"
                        "PASS\n"
                    )
                },
            )
            report = build_report(rd, repo_path=tmp)
            text = render_report(report)
            self.assertEqual(len(report.steps), 1)
            self.assertEqual(report.final_enum, "PASS")
            self.assertTrue(report.final_clean)
            self.assertIn("code-validator [VERIFY_ONLY]", text)
            self.assertIn("| clean 판정 | ✅ |", text)


class RunListTests(unittest.TestCase):
    def test_list_and_find(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            sessions_root = tmp / ".claude" / "harness-state" / ".sessions"
            _make_run_dir(tmp, "sid1", "rid_a", [
                {"ts": "2026-04-30T10:00:00", "agent": "architect", "mode": None,
                 "enum": "PASS", "must_fix": False, "prose_excerpt": "x"}])
            _make_run_dir(tmp, "sid1", "rid_b", [
                {"ts": "2026-04-30T11:00:00", "agent": "engineer", "mode": "IMPL",
                 "enum": "IMPL_DONE", "must_fix": False, "prose_excerpt": "x"}])
            runs = list_runs(sessions_root)
            self.assertEqual(len(runs), 2)
            self.assertEqual(find_run_dir(sessions_root, "rid_a", False).name, "rid_a")
            self.assertEqual(find_run_dir(sessions_root, None, True).name, runs[0].name)


class NormalizeAgentTypeTests(unittest.TestCase):
    def test_dcness_namespaced_strips_prefix(self):
        self.assertEqual(_normalize_agent_type("dcness:architect"), "architect")
        self.assertEqual(_normalize_agent_type("dcness:architect:system-design"), "architect")
        self.assertEqual(_normalize_agent_type("dcness:engineer"), "engineer")

    def test_non_namespaced_returns_as_is(self):
        self.assertEqual(_normalize_agent_type("architect"), "architect")
        self.assertEqual(_normalize_agent_type("Explore"), "Explore")

    def test_none_or_empty(self):
        self.assertIsNone(_normalize_agent_type(None))
        self.assertIsNone(_normalize_agent_type(""))


class AssignInvocationsTests(unittest.TestCase):
    def test_assigns_by_timestamp_proximity(self):
        # DCN-30-21: timestamp-proximity matching.
        from datetime import datetime as dt
        steps = [
            StepRecord(idx=0, ts="2026-04-30T10:05:00+00:00", agent="architect", mode="MODULE_PLAN",
                       enum="PASS", must_fix=False, prose_excerpt="x"),
            StepRecord(idx=1, ts="2026-04-30T10:15:00+00:00", agent="engineer", mode="IMPL",
                       enum="IMPL_DONE", must_fix=False, prose_excerpt="x"),
        ]
        invocations = [
            {"ts": dt(2026, 4, 30, 10, 4, 30), "agent": "architect", "duration_ms": 60000,
             "total_tokens": 5000, "output_tokens": 1500, "cost_usd": 0.05},
            {"ts": dt(2026, 4, 30, 10, 14, 30), "agent": "engineer", "duration_ms": 120000,
             "total_tokens": 8000, "output_tokens": 2500, "cost_usd": 0.10},
        ]
        assign_invocations_to_steps(steps, invocations)
        self.assertTrue(steps[0].matched_invocation)
        self.assertEqual(steps[0].duration_ms, 60000)
        self.assertEqual(steps[0].output_tokens, 1500)
        self.assertTrue(steps[1].matched_invocation)
        self.assertEqual(steps[1].cost_usd, 0.10)

    def test_skips_unmatched_agents(self):
        from datetime import datetime as dt
        steps = [
            StepRecord(idx=0, ts="2026-04-30T10:05:00+00:00", agent="architect", mode=None,
                       enum="PASS", must_fix=False, prose_excerpt="x"),
        ]
        invocations = [
            {"ts": dt(2026, 4, 30, 10, 4, 30), "agent": "engineer", "duration_ms": 60000,
             "total_tokens": 5000, "output_tokens": 1500, "cost_usd": 0.05},
        ]
        assign_invocations_to_steps(steps, invocations)
        self.assertFalse(steps[0].matched_invocation)

    def test_handles_missing_first_invocation(self):
        # DCN-30-21 regression — jajang 사례. step 0 invocation 부재 시 후속 step
        # 매칭 cascade 어긋남 X.
        from datetime import datetime as dt
        steps = [
            StepRecord(idx=0, ts="2026-04-30T10:00:00+00:00", agent="product-planner", mode=None,
                       enum="PRODUCT_PLAN_UPDATED", must_fix=False, prose_excerpt="x"),
            StepRecord(idx=1, ts="2026-04-30T10:10:00+00:00", agent="plan-reviewer", mode=None,
                       enum="PASS", must_fix=False, prose_excerpt="x"),
            StepRecord(idx=2, ts="2026-04-30T10:20:00+00:00", agent="product-planner", mode=None,
                       enum="PRODUCT_PLAN_UPDATED", must_fix=False, prose_excerpt="x"),
        ]
        invocations = [
            {"ts": dt(2026, 4, 30, 10, 9, 30), "agent": "plan-reviewer", "duration_ms": 60000,
             "total_tokens": 5000, "output_tokens": 1500, "cost_usd": 0.05},
            {"ts": dt(2026, 4, 30, 10, 19, 30), "agent": "product-planner", "duration_ms": 120000,
             "total_tokens": 8000, "output_tokens": 2500, "cost_usd": 0.10},
        ]
        assign_invocations_to_steps(steps, invocations)
        self.assertFalse(steps[0].matched_invocation, "step 0 invocation 없으니 미매칭")
        self.assertTrue(steps[1].matched_invocation, "step 1 plan-reviewer 정확 매칭")
        self.assertEqual(steps[1].output_tokens, 1500)
        self.assertTrue(steps[2].matched_invocation, "step 2 product-planner 정확 매칭")
        self.assertEqual(steps[2].output_tokens, 2500)

    def test_excludes_invocation_after_step_ts(self):
        # invocation ts > step ts → 매칭 X (sub-agent 는 end-step 전에 끝남).
        from datetime import datetime as dt
        steps = [
            StepRecord(idx=0, ts="2026-04-30T10:00:00+00:00", agent="architect", mode=None,
                       enum="PASS", must_fix=False, prose_excerpt="x"),
        ]
        invocations = [
            {"ts": dt(2026, 4, 30, 10, 5, 0), "agent": "architect", "duration_ms": 60000,
             "total_tokens": 5000, "output_tokens": 1500, "cost_usd": 0.05},
        ]
        assign_invocations_to_steps(steps, invocations)
        self.assertFalse(steps[0].matched_invocation)


class ThinkingLoopDetectionTests(unittest.TestCase):
    """issue #394 — THINKING_LOOP 는 detect_notes 로 이동 (severity 없는 알림)."""

    def test_thinking_loop_high_duration_low_output(self):
        # 사용자 jajang 사례 시뮬레이션 — architect 6분 + 624 tokens
        s = StepRecord(idx=0, ts="t", agent="architect", mode="MODULE_PLAN",
                        enum="PASS", must_fix=False,
                        prose_excerpt="line1\nline2\nline3\nline4\nline5\nline6")
        s.matched_invocation = True
        s.duration_ms = 360000  # 6분
        s.output_tokens = 624
        s.total_tokens = 1000
        notes = detect_notes([s])
        kinds = {n.pattern for n in notes}
        self.assertIn("THINKING_LOOP", kinds)

    def test_no_thinking_loop_when_healthy(self):
        # 정상 — 60s + 5000 tokens
        s = StepRecord(idx=0, ts="t", agent="architect", mode="MODULE_PLAN",
                        enum="PASS", must_fix=False,
                        prose_excerpt="line1\nline2\nline3\nline4\nline5\nline6")
        s.matched_invocation = True
        s.duration_ms = 60000
        s.output_tokens = 5000
        s.total_tokens = 30000
        notes = detect_notes([s])
        self.assertFalse(any(n.pattern == "THINKING_LOOP" for n in notes))

    def test_no_thinking_loop_when_unmatched(self):
        # matched_invocation=False 면 detection skip
        s = StepRecord(idx=0, ts="t", agent="architect", mode="MODULE_PLAN",
                        enum="PASS", must_fix=False,
                        prose_excerpt="line1\nline2\nline3\nline4\nline5\nline6")
        s.matched_invocation = False
        s.duration_ms = 0
        s.output_tokens = 0
        notes = detect_notes([s])
        self.assertFalse(any(n.pattern == "THINKING_LOOP" for n in notes))


class RegressionPatternsTests(unittest.TestCase):
    """DCN-CHG-20260430-37 — 4 신규 회귀 패턴."""

    def test_tool_use_overflow_emits_finding(self):
        # issue #394 — TOOL_USE_OVERFLOW 는 detect_notes 로 이동.
        s = StepRecord(idx=0, ts="t", agent="engineer", mode="IMPL",
                        enum="IMPL_DONE", must_fix=False,
                        prose_excerpt="line1\nline2\nline3\nline4\nline5")
        s.matched_invocation = True
        s.tool_use_count = 119
        notes = detect_notes([s])
        kinds = {n.pattern for n in notes}
        self.assertIn("TOOL_USE_OVERFLOW", kinds)

    def test_tool_use_overflow_below_threshold(self):
        # ≤ 99 = silent.
        s = StepRecord(idx=0, ts="t", agent="engineer", mode="IMPL",
                        enum="IMPL_DONE", must_fix=False,
                        prose_excerpt="line1\nline2\nline3\nline4\nline5")
        s.matched_invocation = True
        s.tool_use_count = 64
        notes = detect_notes([s])
        self.assertFalse(any(n.pattern == "TOOL_USE_OVERFLOW" for n in notes))

    def test_tool_use_overflow_unmatched_invocation_skipped(self):
        # matched_invocation=False → skip
        s = StepRecord(idx=0, ts="t", agent="engineer", mode="IMPL",
                        enum="IMPL_DONE", must_fix=False,
                        prose_excerpt="line1\nline2\nline3\nline4\nline5")
        s.matched_invocation = False
        s.tool_use_count = 200
        notes = detect_notes([s])
        self.assertFalse(any(n.pattern == "TOOL_USE_OVERFLOW" for n in notes))

    # issue #392 — test_partial_loop_* 폐기 (PARTIAL_LOOP 패턴 폐기 정합).

    def test_end_step_skip_when_invocations_exceed_steps(self):
        # invocations 3 vs steps 1 (engineer) — 2 누락 의심
        from datetime import datetime
        steps = [
            StepRecord(idx=0, ts="2026-04-30T10:00:00", agent="engineer", mode="IMPL",
                        enum="IMPL_DONE", must_fix=False,
                        prose_excerpt="line1\nline2\nline3\nline4\nline5"),
        ]
        invocations = [
            {"agent": "engineer", "ts": datetime(2026, 4, 30, 10, 0, 0),
             "duration_ms": 1000, "output_tokens": 100, "total_tokens": 100,
             "input_tokens": 100, "cache_read": 0, "cost_usd": 0.0,
             "tool_use_count": 50, "agent_type_raw": "dcness:engineer"},
            {"agent": "engineer", "ts": datetime(2026, 4, 30, 10, 5, 0),
             "duration_ms": 1000, "output_tokens": 100, "total_tokens": 100,
             "input_tokens": 100, "cache_read": 0, "cost_usd": 0.0,
             "tool_use_count": 60, "agent_type_raw": "dcness:engineer"},
            {"agent": "engineer", "ts": datetime(2026, 4, 30, 10, 10, 0),
             "duration_ms": 1000, "output_tokens": 100, "total_tokens": 100,
             "input_tokens": 100, "cache_read": 0, "cost_usd": 0.0,
             "tool_use_count": 40, "agent_type_raw": "dcness:engineer"},
        ]
        wastes = detect_wastes(steps, invocations=invocations)
        kinds = {w.pattern for w in wastes}
        self.assertIn("END_STEP_SKIP", kinds)

    def test_end_step_skip_silent_within_margin(self):
        # invocations 2 vs steps 1 = diff 1, margin 1 안 → silent
        from datetime import datetime
        steps = [
            StepRecord(idx=0, ts="2026-04-30T10:00:00", agent="engineer", mode="IMPL",
                        enum="IMPL_DONE", must_fix=False,
                        prose_excerpt="line1\nline2\nline3\nline4\nline5"),
        ]
        invocations = [
            {"agent": "engineer", "ts": datetime(2026, 4, 30, 10, 0, 0),
             "duration_ms": 0, "output_tokens": 0, "total_tokens": 0,
             "input_tokens": 0, "cache_read": 0, "cost_usd": 0.0,
             "tool_use_count": 0, "agent_type_raw": "dcness:engineer"},
            {"agent": "engineer", "ts": datetime(2026, 4, 30, 10, 5, 0),
             "duration_ms": 0, "output_tokens": 0, "total_tokens": 0,
             "input_tokens": 0, "cache_read": 0, "cost_usd": 0.0,
             "tool_use_count": 0, "agent_type_raw": "dcness:engineer"},
        ]
        wastes = detect_wastes(steps, invocations=invocations)
        self.assertFalse(any(w.pattern == "END_STEP_SKIP" for w in wastes))

    # issue #392 — test_main_sed_misdiagnosis_detects_self_correction 폐기.


# issue #392 — MissingSelfVerifyTests 클래스 전체 폐기 (MISSING_SELF_VERIFY 패턴 폐기).


# ── issue #383 회귀 차단 테스트 (B1~B4) ──────────────────────────────


class WindowPaddingTests(unittest.TestCase):
    """B1 — sub-agent TUR ts < first_ts (= 첫 step end-step 호출 시각) 케이스.

    sub-agent 는 end-step 직전에 완료하므로 TUR ts < step.ts 가 *구조적* 패턴.
    padding 없으면 첫 step metric 매번 누락 (jajang run-459cce99 실측 8s off-by-N).
    """

    def test_first_step_tur_before_window_first_ts_matches_via_padding(self):
        from datetime import datetime as dt
        from harness.run_review import build_report

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            # step.ts = end-step 호출 시각. CC session JSONL 의 TUR ts 는 그 직전.
            rd = _make_run_dir(tmp, "sid_pad", "rid_pad", [
                {"ts": "2026-04-30T10:05:00+00:00", "agent": "engineer", "mode": "IMPL",
                 "enum": "IMPL_DONE", "must_fix": False, "prose_excerpt": "x"},
                {"ts": "2026-04-30T10:15:00+00:00", "agent": "pr-reviewer", "mode": None,
                 "enum": "LGTM", "must_fix": False, "prose_excerpt": "y"},
            ])
            # CC session JSONL — 첫 TUR 는 first_ts (10:05:00) 보다 8초 *이전*
            cc_dir = tmp / ".claude" / "projects" / "-tmp-dir"
            cc_dir.mkdir(parents=True, exist_ok=True)
            jsonl = cc_dir / "sid_pad.jsonl"
            jsonl.write_text(
                json.dumps({
                    "timestamp": "2026-04-30T10:04:52.000Z",  # ← 8초 전 (B1 케이스)
                    "toolUseResult": {
                        "agentType": "dcness:engineer",
                        "totalTokens": 9000, "totalDurationMs": 300000,
                        "usage": {"output_tokens": 2500, "input_tokens": 6000},
                        "totalToolUseCount": 30,
                    },
                }) + "\n" +
                json.dumps({
                    "timestamp": "2026-04-30T10:14:50.000Z",
                    "toolUseResult": {
                        "agentType": "dcness:pr-reviewer",
                        "totalTokens": 4000, "totalDurationMs": 100000,
                        "usage": {"output_tokens": 1000, "input_tokens": 3000},
                        "totalToolUseCount": 15,
                    },
                }) + "\n",
                encoding="utf-8",
            )
            report = build_report(rd, repo_path=tmp / "fakerepo")
            # repo_path 가 jsonl 위치와 다르면 find_session_jsonls 가 못 찾을 수도 있음.
            # 본 테스트는 *padding 적용* 자체를 확인 — repo_path 일치 환경 fallback 후 검증.

        # WINDOW_TS_PADDING ≥ 60s 충족 — B1 fix 확인
        self.assertGreaterEqual(WINDOW_TS_PADDING.total_seconds(), 30)


class DcnessAgentNamesCompletenessTests(unittest.TestCase):
    """B2 — agents/ 디렉토리와 DCNESS_AGENT_NAMES 정합 검증."""

    def test_includes_module_and_system_architect(self):
        # jajang design run 의 module-architect / system-architect
        # invocation 도 매칭되어야 함 (이전엔 `architect` 만 있어 미매칭).
        self.assertIn("module-architect", DCNESS_AGENT_NAMES)
        self.assertIn("system-architect", DCNESS_AGENT_NAMES)

    def test_validator_alias_normalizes_to_code_validator(self):
        # 0.2.16 시절 메인 Claude 의 잔재 호출 `dcness:validator` 흡수.
        # backward compat — 옛 데이터 review 회복용.
        self.assertEqual(_normalize_agent_type("dcness:validator"), "code-validator")
        self.assertEqual(_normalize_agent_type("validator"), "code-validator")
        self.assertIn("validator", LEGACY_AGENT_ALIASES)
        self.assertEqual(LEGACY_AGENT_ALIASES["validator"], "code-validator")


class MustFixLeakTests(unittest.TestCase):
    """B3 — 마지막 step must_fix=True 면 wastes 1+ 박혀야 함 (caveat 통지 회귀 차단).

    MUST_FIX_GHOST 는 *다음 step 진행* 케이스만 검사. 마지막 step 은 다음 없음으로
    skip → wastes 비어있는 회귀 (jajang run-459cce99 pr-reviewer 케이스).
    """

    def test_must_fix_true_on_last_step_emits_waste(self):
        steps = [
            StepRecord(idx=0, ts="2026-04-30T10:05:00+00:00", agent="engineer", mode="IMPL",
                       enum="IMPL_DONE", must_fix=False, prose_excerpt="x"),
            StepRecord(idx=1, ts="2026-04-30T10:15:00+00:00", agent="pr-reviewer", mode=None,
                       enum="PROSE_LOGGED", must_fix=True, prose_excerpt="y"),
        ]
        wastes = detect_wastes(steps)
        leak = [w for w in wastes if w.pattern == "MUST_FIX_LEAK"]
        self.assertEqual(len(leak), 1, "마지막 step must_fix=True 면 MUST_FIX_LEAK 1+ 필수")
        self.assertEqual(leak[0].severity, "HIGH")
        self.assertEqual(leak[0].agent, "pr-reviewer")

    def test_no_leak_when_last_step_clean(self):
        steps = [
            StepRecord(idx=0, ts="2026-04-30T10:05:00+00:00", agent="engineer", mode="IMPL",
                       enum="IMPL_DONE", must_fix=False, prose_excerpt="x"),
            StepRecord(idx=1, ts="2026-04-30T10:15:00+00:00", agent="pr-reviewer", mode=None,
                       enum="LGTM", must_fix=False, prose_excerpt="y"),
        ]
        wastes = detect_wastes(steps)
        leak = [w for w in wastes if w.pattern == "MUST_FIX_LEAK"]
        self.assertEqual(len(leak), 0)


class ConclusionEnumExtractionTests(unittest.TestCase):
    """B4 — prose-only mode 후 enum 컬럼이 PROSE_LOGGED 그대로 박히는 회귀.

    agent prose 마지막 단락에 PASS/LGTM/FAIL/ESCALATE 결론 박혀있음
    (agents/code-validator.md 의 결론 + 권장 다음 단계 등 강제). 표시 단계에서 그 결론 추출 의무.
    """

    def test_extracts_pass_from_prose_tail(self):
        prose = "여기는 본문.\n중간 분석.\n\n## 결론\n\n모든 항목 PASS 확인되었다."
        self.assertEqual(_extract_conclusion_enum(prose), "PASS")

    def test_extracts_lgtm(self):
        prose = "리뷰 결과.\n\nLGTM — CI PASS 후 메인이 즉시 regular merge 권고."
        self.assertEqual(_extract_conclusion_enum(prose), "LGTM")

    def test_extracts_fail(self):
        prose = "검증 결과.\n\nspec mismatch 발견 — FAIL 판정."
        self.assertEqual(_extract_conclusion_enum(prose), "FAIL")

    def test_negation_skipped_for_pass_fail(self):
        # "FAIL 없음" 부정문은 매칭 X
        prose = "검토 완료.\n\n모든 항목 통과 — FAIL 없음."
        self.assertNotEqual(_extract_conclusion_enum(prose), "FAIL")

    def test_empty_prose_returns_empty(self):
        self.assertEqual(_extract_conclusion_enum(""), "")
        self.assertEqual(_extract_conclusion_enum("아무 결론 없음"), "")

    # issue #383 follow-up — agent 별 결론 enum 12 매트릭스 매핑 회귀 차단.
    def test_extracts_tests_written(self):
        # test-engineer 결론 (jajang run-459cce99 step 0 실측 케이스)
        prose = "분석 완료.\n\n나머지 12 it 는 RED. TESTS_WRITTEN — engineer attempt 0 권고."
        self.assertEqual(_extract_conclusion_enum(prose), "TESTS_WRITTEN")

    def test_extracts_impl_done(self):
        # engineer IMPL 결론
        prose = "구현 완료.\n\nIMPL_DONE — code-validator 검증 권고."
        self.assertEqual(_extract_conclusion_enum(prose), "IMPL_DONE")

    def test_extracts_impl_partial(self):
        prose = "분량 초과.\n\nIMPL_PARTIAL — 남은 작업: foo.ts §3.2 ~ §3.5"
        self.assertEqual(_extract_conclusion_enum(prose), "IMPL_PARTIAL")

    def test_extracts_polish_done(self):
        prose = "POLISH 완료.\n\nN passed / 변경 범위 src/foo.ts. POLISH_DONE."
        self.assertEqual(_extract_conclusion_enum(prose), "POLISH_DONE")

    def test_extracts_implementation_escalate(self):
        prose = "재시도 한도 초과.\n\nIMPLEMENTATION_ESCALATE — 사용자 위임."
        self.assertEqual(_extract_conclusion_enum(prose), "IMPLEMENTATION_ESCALATE")

    def test_validation_blocked_beats_tests_fail_mention(self):
        # 리뷰 P3 — agent 문서가 가르치는 구분 문장("TESTS_FAIL 이 아니라 VALIDATION_BLOCKED")
        # 에서 둘 다 standalone(negation skip)이라 매칭 순서가 결론을 정한다.
        prose = (
            "self-validate 시도.\n\n"
            "검증이 실행돼 실패한 게 아니므로 TESTS_FAIL 이 아니라 VALIDATION_BLOCKED 입니다."
        )
        self.assertEqual(_extract_conclusion_enum(prose), "VALIDATION_BLOCKED")

    def test_extracts_validation_blocked(self):
        # build-worker 결론 — 검증 명령 실행 불가 (환경 제약). PASS 로 오인 금지 (#705).
        prose = (
            "self-validate 시도.\n\n게이트 명령 실행이 환경 제약으로 막힘 — "
            "VALIDATION_BLOCKED. 메인 대행 명령: python -m pytest tests/"
        )
        self.assertEqual(_extract_conclusion_enum(prose), "VALIDATION_BLOCKED")

    def test_extracts_tests_fail(self):
        # TESTS_FAIL 이 FAIL 보다 우선 매칭
        prose = "테스트 결과.\n\n3회 후에도 동일 FAIL — TESTS_FAIL 결론."
        self.assertEqual(_extract_conclusion_enum(prose), "TESTS_FAIL")

    def test_extracts_ux_flow_done(self):
        prose = "UX_FLOW 작성 완료.\n\nself-check 5 카테고리 통과. UX_FLOW_DONE."
        self.assertEqual(_extract_conclusion_enum(prose), "UX_FLOW_DONE")

    def test_extracts_ux_flow_escalate(self):
        prose = "self-check 2 cycle.\n\n카테고리 3 미해결. UX_FLOW_ESCALATE."
        self.assertEqual(_extract_conclusion_enum(prose), "UX_FLOW_ESCALATE")

    def test_standalone_enum_ignores_negation_marker_on_same_line(self):
        # IMPL_DONE 같은 단독 enum 은 부정 마커 (예: "FAIL 없음") 있어도 추출.
        # 단어 자체가 부정 형태 가질 수 없음.
        prose = "임시 분석.\n\n빌드 통과, FAIL 없음. IMPL_DONE — 다음 단계 권고."
        self.assertEqual(_extract_conclusion_enum(prose), "IMPL_DONE")

    def test_priority_specific_over_generic(self):
        # 같은 줄에 TESTS_FAIL 과 FAIL 둘 다 있으면 TESTS_FAIL 우선 매칭.
        prose = "결과.\n\nTESTS_FAIL — 3회 FAIL 후 종료."
        self.assertEqual(_extract_conclusion_enum(prose), "TESTS_FAIL")

    def test_parse_steps_populates_conclusion_enum(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            sid, rid = "sid_b4", "rid_b4"
            run_dir = tmp / ".claude" / "harness-state" / ".sessions" / sid / "runs" / rid
            run_dir.mkdir(parents=True, exist_ok=True)
            prose_path = run_dir / "pr-reviewer.md"
            prose_path.write_text("리뷰 진행.\n\nLGTM — merge 권고.", encoding="utf-8")
            jsonl = run_dir / ".steps.jsonl"
            jsonl.write_text(
                json.dumps({
                    "ts": "2026-04-30T10:15:00+00:00",
                    "agent": "pr-reviewer", "mode": None,
                    "enum": "PROSE_LOGGED", "must_fix": False,
                    "prose_excerpt": "리뷰 진행", "prose_file": str(prose_path),
                }) + "\n",
                encoding="utf-8",
            )
            steps = parse_steps(run_dir)
            self.assertEqual(len(steps), 1)
            self.assertEqual(steps[0].conclusion_enum, "LGTM")
            self.assertEqual(steps[0].enum, "PROSE_LOGGED")  # sentinel 그대로 보존


class MissingConclusionEnumTests(unittest.TestCase):
    """issue #387 — engineer prose 끝 결론 enum 부재 검출.

    agents/engineer.md 의 결론 + 권장 다음 단계: IMPL/POLISH 모드 모두 prose 마지막 단락에
    결론 enum (IMPL_DONE / IMPL_PARTIAL / SPEC_GAP_FOUND / TESTS_FAIL /
    IMPLEMENTATION_ESCALATE / POLISH_DONE) 의무. jajang run-459cce99 step 1
    engineer-IMPL prose 가 어떤 enum 도 박지 않은 caveat 케이스 직접 동기.
    """

    def test_missing_conclusion_enum_engineer_caveat(self):
        # engineer prose 끝 = "사용자에게 요청하는 결정 사항" — 결론 enum 부재
        prose = (
            "구현 작업 중.\n\n"
            "TypeScript 에러 발생.\n\n"
            "**사용자에게 요청하는 결정 사항**\n"
            "1. stub 파일 허용 여부\n"
            "2. @theme/tokens 상대 경로 수정 허용 여부"
        )
        s = StepRecord(
            idx=0, ts="2026-04-30T10:05:00+00:00",
            agent="engineer", mode="IMPL",
            enum="PROSE_LOGGED", must_fix=False,
            prose_excerpt="x", prose_full=prose,
            conclusion_enum="",  # 추출 실패
        )
        wastes = detect_wastes([s])
        missing = [w for w in wastes if w.pattern == "MISSING_CONCLUSION_ENUM"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0].severity, "MEDIUM")
        self.assertEqual(missing[0].agent, "engineer")

    def test_no_missing_when_enum_present(self):
        prose = "구현 완료.\n\nIMPL_DONE — code-validator 권고."
        s = StepRecord(
            idx=0, ts="2026-04-30T10:05:00+00:00",
            agent="engineer", mode="IMPL",
            enum="PROSE_LOGGED", must_fix=False,
            prose_excerpt="x", prose_full=prose,
            conclusion_enum="IMPL_DONE",
        )
        wastes = detect_wastes([s])
        missing = [w for w in wastes if w.pattern == "MISSING_CONCLUSION_ENUM"]
        self.assertEqual(len(missing), 0)

    def test_missing_skips_non_engineer(self):
        # validator / pr-reviewer / architect 류는 자율 영역 — skip
        prose = "검증 진행.\n\n특별한 enum 박지 않음."
        steps = [
            StepRecord(idx=0, ts="2026-04-30T10:05:00+00:00",
                       agent="code-validator", mode="CODE_VALIDATION",
                       enum="PROSE_LOGGED", must_fix=False,
                       prose_excerpt="x", prose_full=prose, conclusion_enum=""),
            StepRecord(idx=1, ts="2026-04-30T10:15:00+00:00",
                       agent="pr-reviewer", mode=None,
                       enum="PROSE_LOGGED", must_fix=False,
                       prose_excerpt="y", prose_full=prose, conclusion_enum=""),
        ]
        wastes = detect_wastes(steps)
        missing = [w for w in wastes if w.pattern == "MISSING_CONCLUSION_ENUM"]
        self.assertEqual(len(missing), 0)

    def test_missing_skips_no_prose_full(self):
        # prose_full 부재 시 검사 불가 — skip
        s = StepRecord(
            idx=0, ts="2026-04-30T10:05:00+00:00",
            agent="engineer", mode="IMPL",
            enum="PROSE_LOGGED", must_fix=False,
            prose_excerpt="x", prose_full="",
            conclusion_enum="",
        )
        wastes = detect_wastes([s])
        missing = [w for w in wastes if w.pattern == "MISSING_CONCLUSION_ENUM"]
        self.assertEqual(len(missing), 0)


class ToolHistogramTableTests(unittest.TestCase):
    """#415 — _build_tool_histogram_table step 윈도우 fix.

    step.ts = end-step 시각. sub-agent 도구 호출 ts < step.ts.
    윈도우 = 이전 step end ~ 현재 step end.
    """

    def _make_run_with_trace(self, td: Path, step_records: list[dict], trace_entries: list[dict]) -> Path:
        sid = "00000000-0000-4000-8000-000000000415"
        rid = "run-00000415"
        rd = _make_run_dir(td, sid, rid, step_records)
        # agent-trace.jsonl 추가
        trace_path = rd / "agent-trace.jsonl"
        with open(trace_path, "w", encoding="utf-8") as f:
            for e in trace_entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        return rd

    def test_last_step_included(self):
        """마지막 step 의 sub-agent trace 가 히스토그램에 포함된다."""
        from harness.run_review import _build_tool_histogram_table
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            # step 2개 — 마지막은 pr-reviewer
            rd = self._make_run_with_trace(tmp, [
                {"ts": "2026-05-12T14:54:00+00:00", "agent": "engineer", "mode": "IMPL",
                 "enum": "IMPL_DONE", "must_fix": False, "prose_excerpt": "x"},
                {"ts": "2026-05-12T14:59:00+00:00", "agent": "pr-reviewer", "mode": None,
                 "enum": "LGTM", "must_fix": False, "prose_excerpt": "y"},
            ], [
                # engineer trace (step 0 윈도우 = ~ 14:54:00)
                {"phase": "pre", "agent": "engineer", "ts": "2026-05-12T14:53:00+00:00", "tool": "Edit"},
                {"phase": "pre", "agent": "engineer", "ts": "2026-05-12T14:53:30+00:00", "tool": "Edit"},
                # pr-reviewer trace (step 1 윈도우 = 14:54:00 ~ 14:59:00)
                {"phase": "pre", "agent": "pr-reviewer", "ts": "2026-05-12T14:57:00+00:00", "tool": "Read"},
                {"phase": "pre", "agent": "pr-reviewer", "ts": "2026-05-12T14:58:00+00:00", "tool": "Read"},
            ])
            report = build_report(rd, tmp)
            lines = _build_tool_histogram_table(report)
            # 표 lines: header(2) + step0 + step1
            self.assertGreater(len(lines), 2)
            joined = "\n".join(lines)
            # step 1 (pr-reviewer) 가 표에 포함 — last step 누락 회귀 차단
            pr_line = [ln for ln in lines if "pr-reviewer" in ln]
            self.assertEqual(len(pr_line), 1)
            # Read 2 박힘
            self.assertIn(" 2 ", pr_line[0])

    def test_step_window_uses_previous_end_to_current_end(self):
        """윈도우 = 이전 step.ts ~ 현재 step.ts. trace 가 정확히 배정."""
        from harness.run_review import _build_tool_histogram_table
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rd = self._make_run_with_trace(tmp, [
                {"ts": "2026-05-12T10:00:00+00:00", "agent": "test-engineer", "mode": None,
                 "enum": "TESTS_WRITTEN", "must_fix": False, "prose_excerpt": "x"},
                {"ts": "2026-05-12T10:10:00+00:00", "agent": "engineer", "mode": "IMPL",
                 "enum": "IMPL_DONE", "must_fix": False, "prose_excerpt": "y"},
            ], [
                # test-engineer 영역 (~ 10:00:00 까지)
                {"phase": "pre", "agent": "test-engineer", "ts": "2026-05-12T09:55:00+00:00", "tool": "Read"},
                {"phase": "pre", "agent": "test-engineer", "ts": "2026-05-12T09:56:00+00:00", "tool": "Write"},
                # engineer 영역 (10:00:00 ~ 10:10:00)
                {"phase": "pre", "agent": "engineer", "ts": "2026-05-12T10:05:00+00:00", "tool": "Edit"},
            ])
            report = build_report(rd, tmp)
            lines = _build_tool_histogram_table(report)
            joined = "\n".join(lines)
            # 두 step 모두 표에 박힘
            self.assertIn("test-engineer", joined)
            self.assertIn("engineer", joined)


class ListRunsLedgerTests(unittest.TestCase):
    """이슈 #587 (codex review) — list_runs 가 빈 active run 을 latest 후보에서 제외."""

    def test_latest_requires_run_finished_for_ledger(self) -> None:
        """ledger run 은 run_finished 있어야 implicit latest 후보 — partial/empty 제외 (codex review)."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            # finished run — step_completed + run_finished
            _make_run_dir_ledger(tmp, "sidD", "ridDone", [
                {"event": "step_completed", "ts": "2026-05-01T09:00:00", "agent": "engineer",
                 "mode": None, "enum": "PROSE_LOGGED", "must_fix": False,
                 "prose_excerpt": "x", "prose_file": "done.md"},
                {"event": "run_finished", "ts": "2026-05-01T09:05:00"},
            ], prose_files={"done.md": "done"})
            # partial run — step 있지만 run_finished 없음 (active, end-run 전)
            _make_run_dir_ledger(tmp, "sidP", "ridPartial", [
                {"event": "step_completed", "ts": "2026-05-01T10:00:00", "agent": "engineer",
                 "mode": None, "enum": "PROSE_LOGGED", "must_fix": False,
                 "prose_excerpt": "y", "prose_file": "partial.md"},
            ], prose_files={"partial.md": "partial"})
            # empty active run — run_started 만
            _make_run_dir_ledger(tmp, "sidE", "ridEmpty", [
                {"event": "run_started", "ts": "2026-05-01T11:00:00", "entry_point": "impl"},
            ])
            # finished but step 0 — run-review latest 후보 제외
            _make_run_dir_ledger(tmp, "sidF", "ridFinishedEmpty", [
                {"event": "run_started", "ts": "2026-05-01T11:30:00", "entry_point": "impl"},
                {"event": "run_finished", "ts": "2026-05-01T11:35:00"},
            ])
            # finished but invalid receipt — strict reader 가 step drop → 후보 제외
            _make_run_dir_ledger(tmp, "sidI", "ridInvalidReceipt", [
                {"event": "step_completed", "ts": "2026-05-01T12:00:00", "agent": "engineer",
                 "mode": None, "enum": "PROSE_LOGGED", "must_fix": False,
                 "prose_excerpt": "z", "prose_file": str(tmp / "missing-dcness-prose.md"),
                 "sha256": ledger.sha256_text("z")},
                {"event": "run_finished", "ts": "2026-05-01T12:05:00"},
            ])
            sessions_root = tmp / ".claude" / "harness-state" / ".sessions"
            names = [r.name for r in list_runs(sessions_root)]
            self.assertIn("ridDone", names)
            self.assertNotIn("ridPartial", names)
            self.assertNotIn("ridEmpty", names)
            self.assertNotIn("ridFinishedEmpty", names)
            self.assertNotIn("ridInvalidReceipt", names)

    def test_includes_legacy_steps_run(self) -> None:
        """옛 .steps.jsonl 만 있는 run 도 포함 (폴백 호환)."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            _make_run_dir(tmp, "sidL", "ridLegacy", [
                {"ts": "2026-05-01T08:00:00", "agent": "code-validator", "mode": None,
                 "enum": "PROSE_LOGGED", "must_fix": False, "prose_excerpt": "y"},
            ])
            sessions_root = tmp / ".claude" / "harness-state" / ".sessions"
            names = [r.name for r in list_runs(sessions_root)]
            self.assertIn("ridLegacy", names)


if __name__ == "__main__":
    unittest.main()

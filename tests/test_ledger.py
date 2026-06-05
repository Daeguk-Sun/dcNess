"""test_ledger — run 단위 append-only event 장부 + receipt 검증 (이슈 #587).

Coverage matrix:
    EVENT_TYPES:
        - 이슈 카탈로그 10종 전부 포함
    ledger_path / legacy_steps_path:
        - run_dir 안 ledger.jsonl / .steps.jsonl
    append_event:
        - 유효 event append + ts 자동
        - 잘못된 event type → ValueError
        - 임의 필드 보존
    read_events:
        - 전체 읽기 / 빈 파일 / ledger 없으면 .steps.jsonl 폴백
    read_step_completed:
        - step_completed 만 필터
        - .steps.jsonl 폴백 시 옛 row 를 step_completed 로 normalize
    count_step_completed:
        - (agent, mode) 카운트 (occurrence 계산)
    sha256_text:
        - 결정적 해시
    extract_evidence_paths:
        - prose 에서 파일 경로 / PR 참조 best-effort 추출
    infer_next_action:
        - validator must_fix → retry hint / advance → 빈 문자열
    build_receipt:
        - sha256 / prose_excerpt / evidence_paths / prose_file 포함
        - agent 출력 형식 강제 안 함 (임의 prose 입력)
    append_step_completed:
        - step_completed event 가 receipt superset (옛 row 필드명 호환)
    render_status:
        - 현재 run 의 phase / last event / evidence pointer 출력 (resume)
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from harness import ledger
from harness.session_state import run_dir, start_run, update_live

_SID = "test-ledger-sid"
_RID = "run-deadbeef"


def _seed_run(base: Path) -> None:
    """live.json + run_dir 슬롯 1개 생성 (entry_point=impl, issue 587)."""
    start_run(_SID, _RID, "impl", base_dir=base, issue_num=587)


def _write_prose_file(base: Path, filename: str, content: str) -> Path:
    target = run_dir(_SID, _RID, base_dir=base) / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def _receipt_fields(base: Path, filename: str, content: str) -> dict:
    prose_path = _write_prose_file(base, filename, content)
    return {"prose_file": str(prose_path), "sha256": ledger.sha256_text(content)}


class EventTypesTests(unittest.TestCase):
    def test_issue_catalog_present(self) -> None:
        expected = {
            "run_started", "step_started", "step_completed",
            "validator_passed", "validator_failed",
            "pr_created", "pr_merged", "task_completed",
            "blocked", "run_finished",
        }
        self.assertTrue(expected.issubset(ledger.EVENT_TYPES))

    def test_manual_excludes_lifecycle(self) -> None:
        """수동 CLI 허용 집합은 helper-owned lifecycle 을 제외 (codex review)."""
        self.assertEqual(
            ledger.MANUAL_EVENT_TYPES,
            ledger.EVENT_TYPES - ledger.LIFECYCLE_EVENT_TYPES,
        )
        for ev in ("run_started", "step_started", "step_completed", "run_finished"):
            self.assertNotIn(ev, ledger.MANUAL_EVENT_TYPES)
        for ev in ("pr_merged", "blocked", "task_completed", "validator_failed"):
            self.assertIn(ev, ledger.MANUAL_EVENT_TYPES)


class PathTests(unittest.TestCase):
    def test_ledger_path_under_run_dir(self) -> None:
        with TemporaryDirectory() as d:
            base = Path(d)
            p = ledger.ledger_path(_SID, _RID, base_dir=base)
            self.assertEqual(p, run_dir(_SID, _RID, base_dir=base) / "ledger.jsonl")

    def test_legacy_steps_path(self) -> None:
        with TemporaryDirectory() as d:
            base = Path(d)
            p = ledger.legacy_steps_path(_SID, _RID, base_dir=base)
            self.assertEqual(p, run_dir(_SID, _RID, base_dir=base) / ".steps.jsonl")


class AppendEventTests(unittest.TestCase):
    def test_append_and_read(self) -> None:
        with TemporaryDirectory() as d:
            base = Path(d)
            _seed_run(base)
            rec = ledger.append_event(
                _SID, _RID, "run_started",
                base_dir=base, entry_point="impl", issue_num=587,
            )
            self.assertEqual(rec["event"], "run_started")
            self.assertEqual(rec["entry_point"], "impl")
            self.assertEqual(rec["issue_num"], 587)
            self.assertIn("ts", rec)
            # 디스크 반영
            events = ledger.read_events(_SID, _RID, base_dir=base)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event"], "run_started")

    def test_invalid_event_type_raises(self) -> None:
        with TemporaryDirectory() as d:
            base = Path(d)
            _seed_run(base)
            with self.assertRaises(ValueError):
                ledger.append_event(_SID, _RID, "not_a_real_event", base_dir=base)

    def test_append_event_rejects_step_completed(self) -> None:
        """public append_event 는 step_completed 위조 거부 — append_step_completed 전용 (codex review)."""
        with TemporaryDirectory() as d:
            base = Path(d)
            _seed_run(base)
            with self.assertRaises(ValueError):
                ledger.append_event(_SID, _RID, "step_completed", base_dir=base, agent="fake")
            # 디스크에 위조 step_completed 가 안 남음
            self.assertEqual(ledger.read_step_completed(_SID, _RID, base_dir=base), [])
            # 정당 경로(append_step_completed)는 receipt 동반으로 생성
            prose_path = _write_prose_file(base, "r.md", "p")
            rec = ledger.append_step_completed(
                _SID, _RID, "real", None, "PROSE_LOGGED", "p", prose_path, base_dir=base)
            self.assertEqual(rec["event"], "step_completed")
            self.assertIn("sha256", rec)
            self.assertEqual(len(ledger.read_step_completed(_SID, _RID, base_dir=base)), 1)

    def test_append_order_preserved(self) -> None:
        with TemporaryDirectory() as d:
            base = Path(d)
            _seed_run(base)
            ledger.append_event(_SID, _RID, "run_started", base_dir=base)
            ledger.append_event(_SID, _RID, "step_started", base_dir=base, agent="engineer")
            ledger.append_event(_SID, _RID, "run_finished", base_dir=base)
            events = ledger.read_events(_SID, _RID, base_dir=base)
            self.assertEqual(
                [e["event"] for e in events],
                ["run_started", "step_started", "run_finished"],
            )


class ReadEventsFallbackTests(unittest.TestCase):
    def test_empty_when_nothing(self) -> None:
        with TemporaryDirectory() as d:
            base = Path(d)
            _seed_run(base)
            self.assertEqual(ledger.read_events(_SID, _RID, base_dir=base), [])

    def test_fallback_to_legacy_steps(self) -> None:
        """ledger.jsonl 없고 .steps.jsonl 만 있으면 옛 row 를 step_completed 로 반환."""
        with TemporaryDirectory() as d:
            base = Path(d)
            _seed_run(base)
            legacy = ledger.legacy_steps_path(_SID, _RID, base_dir=base)
            legacy.parent.mkdir(parents=True, exist_ok=True)
            old_row = {
                "ts": "2026-05-24T19:01:07+00:00",
                "agent": "build-test",
                "mode": None,
                "enum": "PROSE_LOGGED",
                "prose_excerpt": "요약",
                "must_fix": False,
                "prose_file": "/tmp/build-test.md",
            }
            legacy.write_text(json.dumps(old_row) + "\n", encoding="utf-8")
            events = ledger.read_events(_SID, _RID, base_dir=base)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event"], "step_completed")
            self.assertEqual(events[0]["agent"], "build-test")
            self.assertEqual(events[0]["prose_file"], "/tmp/build-test.md")

    def test_mixed_merges_legacy_and_ledger(self) -> None:
        """plugin 업데이트가 진행 중 run 에 걸침 — legacy step + 새 ledger event 둘 다 보존 (codex high).

        ledger.jsonl 만 읽으면 옛 .steps.jsonl step 이 사라져 occurrence count 리셋 →
        prose 덮어쓰기. legacy (시간상 먼저) 를 앞에 두고 merge 해야 한다.
        """
        with TemporaryDirectory() as d:
            base = Path(d)
            _seed_run(base)
            # 옛 코드 구간 — .steps.jsonl 에 step row
            legacy = ledger.legacy_steps_path(_SID, _RID, base_dir=base)
            legacy.write_text(
                json.dumps({"agent": "old-step", "mode": None, "enum": "PROSE_LOGGED",
                            "prose_excerpt": "old", "must_fix": False,
                            "prose_file": "/tmp/old.md"}) + "\n",
                encoding="utf-8")
            # plugin 업데이트 후 — 새 코드가 ledger.jsonl 에 event 생성
            ledger.append_event(_SID, _RID, "step_started", base_dir=base, agent="new-step")
            prose_path = _write_prose_file(base, "new.md", "new")
            ledger.append_step_completed(
                _SID, _RID, "new-step", None, "PROSE_LOGGED", "new", prose_path, base_dir=base)
            # legacy step 이 사라지지 않고 시간상 먼저로 merge
            events = ledger.read_events(_SID, _RID, base_dir=base)
            self.assertEqual(events[0]["event"], "step_completed")
            self.assertEqual(events[0]["agent"], "old-step")
            steps = ledger.read_step_completed(_SID, _RID, base_dir=base)
            self.assertEqual([s["agent"] for s in steps], ["old-step", "new-step"])
            # occurrence count 가 legacy 포함 (prose 덮어쓰기 방지)
            self.assertEqual(
                ledger.count_step_completed(_SID, _RID, "old-step", None, base_dir=base), 1)

    def test_mixed_merge_sorts_by_ts(self) -> None:
        """legacy ts 가 ledger event 사이에 끼면 ts 정렬로 시간순 복원 (codex review non-monotonic)."""
        with TemporaryDirectory() as d:
            base = Path(d)
            _seed_run(base)
            lp = ledger.ledger_path(_SID, _RID, base_dir=base)
            early = _receipt_fields(base, "a.md", "early")
            late = _receipt_fields(base, "c.md", "late")
            lp.write_text(
                json.dumps({"event": "step_completed", "ts": "2026-05-01T10:00:00+00:00",
                            "agent": "early", "mode": None, **early}) + "\n"
                + json.dumps({"event": "step_completed", "ts": "2026-05-01T12:00:00+00:00",
                              "agent": "late", "mode": None, **late}) + "\n",
                encoding="utf-8")
            legacy = ledger.legacy_steps_path(_SID, _RID, base_dir=base)
            legacy.write_text(
                json.dumps({"ts": "2026-05-01T11:00:00+00:00", "agent": "middle", "mode": None,
                            "enum": "PROSE_LOGGED", "prose_excerpt": "m", "must_fix": False,
                            "prose_file": "/tmp/b.md"}) + "\n",
                encoding="utf-8")
            steps = ledger.read_step_completed(_SID, _RID, base_dir=base)
            self.assertEqual([s["agent"] for s in steps], ["early", "middle", "late"])

    def test_mixed_merge_dedupes_step_completed(self) -> None:
        """동일 (agent,mode,ts,prose_file) step_completed 중복 제거 (codex review)."""
        with TemporaryDirectory() as d:
            base = Path(d)
            _seed_run(base)
            dup = _receipt_fields(base, "d.md", "dup")
            ident = {"ts": "2026-05-01T10:00:00+00:00", "agent": "dup",
                     "mode": None, **dup}
            lp = ledger.ledger_path(_SID, _RID, base_dir=base)
            lp.write_text(json.dumps({"event": "step_completed", **ident}) + "\n", encoding="utf-8")
            legacy = ledger.legacy_steps_path(_SID, _RID, base_dir=base)
            legacy.write_text(
                json.dumps({**ident, "enum": "PROSE_LOGGED", "prose_excerpt": "d",
                            "must_fix": False}) + "\n",
                encoding="utf-8")
            steps = ledger.read_step_completed(_SID, _RID, base_dir=base)
            self.assertEqual(len(steps), 1)
            self.assertEqual(steps[0]["agent"], "dup")

    def test_primary_step_with_invalid_receipt_dropped(self) -> None:
        """ledger.jsonl 의 invalid receipt step_completed 는 drop+warn (codex review)."""
        import contextlib
        import io
        with TemporaryDirectory() as d:
            base = Path(d)
            _seed_run(base)
            lp = ledger.ledger_path(_SID, _RID, base_dir=base)
            valid = _receipt_fields(base, "valid.md", "valid")
            mismatch_path = _write_prose_file(base, "mismatch.md", "actual")
            missing_path = run_dir(_SID, _RID, base_dir=base) / "missing.md"
            lp.write_text(
                json.dumps({"event": "step_completed", "ts": "2026-05-01T10:00:00+00:00",
                            "agent": "valid", "mode": None, **valid}) + "\n"
                # prose_file 없음 → drop
                + json.dumps({"event": "step_completed", "ts": "2026-05-01T10:01:00+00:00",
                              "agent": "forged", "mode": None}) + "\n"
                # prose_file 있지만 sha256 없음 → drop (receipt 불완전)
                + json.dumps({"event": "step_completed", "ts": "2026-05-01T10:02:00+00:00",
                              "agent": "no_sha", "mode": None, "prose_file": str(missing_path)}) + "\n"
                # prose_file 이 가리키는 파일 없음 → drop (파일 실존 strict)
                + json.dumps({"event": "step_completed", "ts": "2026-05-01T10:03:00+00:00",
                              "agent": "missing_file", "mode": None,
                              "prose_file": str(missing_path), "sha256": ledger.sha256_text("missing")}) + "\n"
                # digest mismatch → drop
                + json.dumps({"event": "step_completed", "ts": "2026-05-01T10:04:00+00:00",
                              "agent": "bad_hash", "mode": None,
                              "prose_file": str(mismatch_path), "sha256": ledger.sha256_text("expected")}) + "\n",
                encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                steps = ledger.read_step_completed(_SID, _RID, base_dir=base)
            self.assertEqual([s["agent"] for s in steps], ["valid"])
            self.assertIn("receipt", buf.getvalue())
            self.assertIn("missing_file", buf.getvalue())
            self.assertIn("sha256_mismatch", buf.getvalue())

    def test_legacy_step_without_prose_file_preserved(self) -> None:
        """옛 .steps.jsonl 의 prose_file 없는 row 는 호환 보존 (primary 검증과 분리 — codex review)."""
        with TemporaryDirectory() as d:
            base = Path(d)
            _seed_run(base)
            legacy = ledger.legacy_steps_path(_SID, _RID, base_dir=base)
            legacy.write_text(
                json.dumps({"ts": "2026-05-01T10:00:00+00:00", "agent": "old", "mode": None,
                            "enum": "PROSE_LOGGED", "must_fix": False,
                            "prose_excerpt": "o"}) + "\n",
                encoding="utf-8")
            steps = ledger.read_step_completed(_SID, _RID, base_dir=base)
            self.assertEqual(len(steps), 1)
            self.assertEqual(steps[0]["agent"], "old")

    def test_malformed_line_warns(self) -> None:
        """손상 레코드 가시화 — malformed 줄 skip + stderr WARN (codex medium)."""
        import contextlib
        import io
        with TemporaryDirectory() as d:
            base = Path(d)
            _seed_run(base)
            lp = ledger.ledger_path(_SID, _RID, base_dir=base)
            lp.write_text(
                '{"event": "run_started", "ts": "t"}\n{truncated broken json...\n',
                encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                events = ledger.read_events(_SID, _RID, base_dir=base)
            self.assertEqual(len(events), 1)
            self.assertIn("malformed", buf.getvalue().lower())


class ReadStepCompletedTests(unittest.TestCase):
    def test_filters_step_completed(self) -> None:
        with TemporaryDirectory() as d:
            base = Path(d)
            _seed_run(base)
            ledger.append_event(_SID, _RID, "run_started", base_dir=base)
            ledger.append_event(_SID, _RID, "step_started", base_dir=base, agent="engineer")
            prose_path = _write_prose_file(base, "engineer.md", "## 결론\n구현 완료")
            ledger.append_step_completed(
                _SID, _RID, "engineer", None, "PROSE_LOGGED",
                "## 결론\n구현 완료", prose_path, base_dir=base,
            )
            steps = ledger.read_step_completed(_SID, _RID, base_dir=base)
            self.assertEqual(len(steps), 1)
            self.assertEqual(steps[0]["agent"], "engineer")

    def test_legacy_steps_as_step_completed(self) -> None:
        with TemporaryDirectory() as d:
            base = Path(d)
            _seed_run(base)
            legacy = ledger.legacy_steps_path(_SID, _RID, base_dir=base)
            legacy.parent.mkdir(parents=True, exist_ok=True)
            rows = [
                {"agent": "engineer", "mode": "IMPL", "enum": "PROSE_LOGGED",
                 "prose_excerpt": "a", "must_fix": False, "prose_file": "/tmp/e.md"},
                {"agent": "code-validator", "mode": None, "enum": "PROSE_LOGGED",
                 "prose_excerpt": "b", "must_fix": True, "prose_file": "/tmp/cv.md"},
            ]
            legacy.write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
            )
            steps = ledger.read_step_completed(_SID, _RID, base_dir=base)
            self.assertEqual([s["agent"] for s in steps], ["engineer", "code-validator"])
            self.assertTrue(steps[1]["must_fix"])


class CountStepCompletedTests(unittest.TestCase):
    def test_count_by_agent_mode(self) -> None:
        with TemporaryDirectory() as d:
            base = Path(d)
            _seed_run(base)
            p0 = _write_prose_file(base, "e.md", "x")
            p1 = _write_prose_file(base, "e1.md", "y")
            p2 = _write_prose_file(base, "ep.md", "z")
            ledger.append_step_completed(
                _SID, _RID, "engineer", "IMPL", "PROSE_LOGGED", "x", p0, base_dir=base)
            ledger.append_step_completed(
                _SID, _RID, "engineer", "IMPL", "PROSE_LOGGED", "y", p1, base_dir=base)
            ledger.append_step_completed(
                _SID, _RID, "engineer", "POLISH", "PROSE_LOGGED", "z", p2, base_dir=base)
            self.assertEqual(
                ledger.count_step_completed(_SID, _RID, "engineer", "IMPL", base_dir=base), 2)
            self.assertEqual(
                ledger.count_step_completed(_SID, _RID, "engineer", "POLISH", base_dir=base), 1)
            self.assertEqual(
                ledger.count_step_completed(_SID, _RID, "code-validator", None, base_dir=base), 0)

    def test_count_includes_legacy_fallback(self) -> None:
        with TemporaryDirectory() as d:
            base = Path(d)
            _seed_run(base)
            legacy = ledger.legacy_steps_path(_SID, _RID, base_dir=base)
            legacy.parent.mkdir(parents=True, exist_ok=True)
            legacy.write_text(
                json.dumps({"agent": "engineer", "mode": "IMPL"}) + "\n", encoding="utf-8")
            self.assertEqual(
                ledger.count_step_completed(_SID, _RID, "engineer", "IMPL", base_dir=base), 1)


class Sha256Tests(unittest.TestCase):
    def test_deterministic(self) -> None:
        h1 = ledger.sha256_text("hello world")
        h2 = ledger.sha256_text("hello world")
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)  # full sha256 hex
        self.assertNotEqual(h1, ledger.sha256_text("hello world!"))


class ExtractEvidenceTests(unittest.TestCase):
    def test_extracts_backticked_paths(self) -> None:
        prose = (
            "구현 완료. `harness/ledger.py` 신규 + `tests/test_ledger.py` 추가.\n"
            "관련 없는 텍스트."
        )
        paths = ledger.extract_evidence_paths(prose)
        self.assertIn("harness/ledger.py", paths)
        self.assertIn("tests/test_ledger.py", paths)

    def test_extracts_pr_reference(self) -> None:
        prose = "PR https://github.com/alruminum/dcNess/pull/588 생성"
        paths = ledger.extract_evidence_paths(prose)
        self.assertTrue(
            any("pull/588" in p for p in paths),
            f"PR URL 추출 실패: {paths}",
        )

    def test_no_false_positive_on_prose(self) -> None:
        prose = "그냥 설명문. 파일 경로 없음. 정상 동작 확인."
        paths = ledger.extract_evidence_paths(prose)
        self.assertEqual(paths, [])


class InferNextActionTests(unittest.TestCase):
    def test_validator_must_fix_hint(self) -> None:
        hint = ledger.infer_next_action("code-validator", None, must_fix=True, enum="PROSE_LOGGED")
        self.assertTrue(hint)  # 비어있지 않음
        self.assertIn("engineer", hint.lower())

    def test_advance_empty(self) -> None:
        hint = ledger.infer_next_action("engineer", "IMPL", must_fix=False, enum="PROSE_LOGGED")
        self.assertEqual(hint, "")


class BuildReceiptTests(unittest.TestCase):
    def test_receipt_fields(self) -> None:
        prose = "## 결론\ncode-validator PASS. MUST FIX 없음.\n수용 기준 충족."
        prose_path = "/tmp/code-validator.md"
        r = ledger.build_receipt("code-validator", None, "PROSE_LOGGED", prose, prose_path)
        self.assertEqual(r["agent"], "code-validator")
        self.assertEqual(r["prose_file"], prose_path)
        self.assertEqual(r["sha256"], ledger.sha256_text(prose))
        self.assertIn("prose_excerpt", r)
        self.assertIn("evidence_paths", r)
        self.assertIn("must_fix", r)
        self.assertFalse(r["must_fix"])  # "MUST FIX 없음"

    def test_no_format_enforcement(self) -> None:
        """agent prose 형식 강제 안 함 — 임의 텍스트도 receipt 생성."""
        r = ledger.build_receipt("engineer", "IMPL", "PROSE_LOGGED", "아무 자유 텍스트", "/tmp/x.md")
        self.assertEqual(r["sha256"], ledger.sha256_text("아무 자유 텍스트"))
        self.assertIsInstance(r["evidence_paths"], list)


class AppendStepCompletedTests(unittest.TestCase):
    def test_step_completed_is_receipt_superset(self) -> None:
        with TemporaryDirectory() as d:
            base = Path(d)
            _seed_run(base)
            prose = "## 결론\n구현 완료. `harness/ledger.py` 작성."
            prose_path = _write_prose_file(base, "engineer-IMPL.md", prose)
            rec = ledger.append_step_completed(
                _SID, _RID, "engineer", "IMPL", "PROSE_LOGGED",
                prose, prose_path, base_dir=base,
            )
            # 옛 .steps.jsonl row 필드명 호환
            for k in ("ts", "agent", "mode", "enum", "prose_excerpt", "must_fix", "prose_file"):
                self.assertIn(k, rec, f"호환 필드 누락: {k}")
            # 신규 receipt 필드
            for k in ("sha256", "evidence_paths"):
                self.assertIn(k, rec, f"receipt 필드 누락: {k}")
            self.assertEqual(rec["event"], "step_completed")
            self.assertEqual(rec["sha256"], ledger.sha256_text(prose))


class ReadAtPathTests(unittest.TestCase):
    """run_dir Path 기반 read (run_review 사후 분석용 — sid/rid 없이 디렉토리 스캔)."""

    def test_read_events_at_ledger(self) -> None:
        with TemporaryDirectory() as d:
            base = Path(d)
            _seed_run(base)
            ledger.append_event(_SID, _RID, "run_started", base_dir=base)
            prose_path = _write_prose_file(base, "e.md", "x")
            ledger.append_step_completed(
                _SID, _RID, "engineer", None, "PROSE_LOGGED", "x", prose_path, base_dir=base)
            rd = run_dir(_SID, _RID, base_dir=base)
            events = ledger.read_events_at(rd)
            self.assertEqual([e["event"] for e in events], ["run_started", "step_completed"])
            steps = ledger.read_step_completed_at(rd)
            self.assertEqual(len(steps), 1)
            self.assertEqual(steps[0]["agent"], "engineer")

    def test_read_at_legacy_fallback(self) -> None:
        with TemporaryDirectory() as d:
            base = Path(d)
            _seed_run(base)
            rd = run_dir(_SID, _RID, base_dir=base)
            (rd / ".steps.jsonl").write_text(
                json.dumps({"agent": "qa", "mode": None, "enum": "PROSE_LOGGED",
                            "prose_excerpt": "z", "must_fix": False, "prose_file": "/tmp/q.md"})
                + "\n",
                encoding="utf-8",
            )
            steps = ledger.read_step_completed_at(rd)
            self.assertEqual(len(steps), 1)
            self.assertEqual(steps[0]["agent"], "qa")
            self.assertEqual(steps[0]["event"], "step_completed")


class RenderStatusTests(unittest.TestCase):
    def test_status_shows_phase_and_evidence(self) -> None:
        with TemporaryDirectory() as d:
            base = Path(d)
            _seed_run(base)
            ledger.append_event(_SID, _RID, "run_started", base_dir=base, entry_point="impl", issue_num=587)
            prose_path = _write_prose_file(base, "code-validator.md", "## 결론\nPASS")
            ledger.append_step_completed(
                _SID, _RID, "code-validator", None, "PROSE_LOGGED",
                "## 결론\nPASS", prose_path, base_dir=base,
            )
            out = ledger.render_status(_SID, _RID, base_dir=base)
            self.assertIn(_RID, out)
            self.assertIn("code-validator", out)
            # phase 또는 last event 정보 포함
            self.assertTrue(len(out.strip()) > 0)

    def test_status_empty_run(self) -> None:
        with TemporaryDirectory() as d:
            base = Path(d)
            _seed_run(base)
            out = ledger.render_status(_SID, _RID, base_dir=base)
            self.assertIsInstance(out, str)


if __name__ == "__main__":
    unittest.main()

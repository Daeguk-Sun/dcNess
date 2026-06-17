"""test_session_state — 세션/run 격리 상태 API 검증.

Coverage matrix:
    valid_session_id:
        - valid (영숫자 / 하이픈 / 언더스코어 with leading alphanumeric)
        - invalid (empty / leading underscore / space / dot / non-str / 256+ chars)

    session_id_from_stdin:
        - 3 변형 (sessionId / session_id / sessionid)
        - 빈 dict / 잘못된 타입 / 잘못된 sid 형식
        - data= 전달 시 stdin read 스킵

    current_session_id (env > pointer):
        - env 있음 → env
        - env 빈 + pointer 있음 → pointer
        - 둘 다 빈 → ""
        - env 잘못된 → pointer

    read_session_pointer:
        - 정상 / 미존재 / 잘못된 sid

    write_session_pointer:
        - 작성 + 0o600 권한
        - 잘못된 sid → ValueError

    generate_run_id:
        - 형식 (run-{8 hex})
        - 충돌 없음 (1000회)

    atomic_write:
        - 파일 생성 + 권한 + 내용
        - tmp residue 없음
        - bytes 외 타입 → TypeError

    session_dir / run_dir / live_path:
        - 정상 경로
        - path traversal 차단
        - run_id 형식 검증

    read_live:
        - envelope 자기참조 일치 → 데이터 반환
        - sessionId 불일치 → 빈 dict (leftover 방어)
        - 미존재 / 잘못된 JSON → 빈 dict

    update_live:
        - _meta 항상 갱신
        - session_id 자기참조 박힘
        - 필드 None 시 삭제
        - active_runs 디폴트 빈 dict

    start_run / update_current_step / complete_run:
        - 슬롯 lifecycle
        - 중복 run_id → ValueError
        - 미활성 run_id update → ValueError
        - complete idempotent

    cleanup_stale_runs:
        - completed+ttl 초과 삭제
        - heartbeat ttl 초과 삭제
        - 신선 슬롯 보존
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from harness.session_state import (
    LIVE_JSON_VERSION,
    atomic_write,
    cleanup_stale_runs,
    complete_run,
    current_session_id,
    generate_run_id,
    live_path,
    read_live,
    read_session_pointer,
    run_dir,
    session_dir,
    session_id_from_stdin,
    start_run,
    update_current_step,
    update_live,
    valid_session_id,
    write_session_pointer,
)


# ---------------------------------------------------------------------------
# valid_session_id
# ---------------------------------------------------------------------------


class ValidSessionIdTests(unittest.TestCase):
    def test_valid_examples(self) -> None:
        for sid in ["abc-def-123", "A1", "x", "abcDEF_123-xyz", "z" * 256]:
            self.assertTrue(valid_session_id(sid), f"should accept: {sid!r}")

    def test_invalid_examples(self) -> None:
        invalids = [
            "",
            "_starts_underscore",
            "-starts-hyphen",
            "with space",
            "with.dot",
            "../path",
            "x" * 257,
            None,
            42,
            ["list"],
        ]
        for sid in invalids:
            self.assertFalse(valid_session_id(sid), f"should reject: {sid!r}")


# ---------------------------------------------------------------------------
# session_id_from_stdin (data= 인자만 — stdin read 는 별도)
# ---------------------------------------------------------------------------


class SessionIdFromStdinTests(unittest.TestCase):
    def test_session_id_variant(self) -> None:
        self.assertEqual(
            session_id_from_stdin(data={"session_id": "abc-123"}),
            "abc-123",
        )

    def test_sessionId_variant(self) -> None:
        self.assertEqual(
            session_id_from_stdin(data={"sessionId": "abc-123"}),
            "abc-123",
        )

    def test_sessionid_variant(self) -> None:
        self.assertEqual(
            session_id_from_stdin(data={"sessionid": "abc-123"}),
            "abc-123",
        )

    def test_priority_session_id_over_sessionId(self) -> None:
        # session_id 가 첫 우선
        result = session_id_from_stdin(
            data={"session_id": "first", "sessionId": "second"}
        )
        self.assertEqual(result, "first")

    def test_invalid_sid_returns_empty(self) -> None:
        self.assertEqual(
            session_id_from_stdin(data={"session_id": "../bad"}), ""
        )

    def test_empty_dict_returns_empty(self) -> None:
        self.assertEqual(session_id_from_stdin(data={}), "")

    def test_non_dict_data_returns_empty(self) -> None:
        self.assertEqual(session_id_from_stdin(data="string"), "")
        self.assertEqual(session_id_from_stdin(data=[]), "")


# ---------------------------------------------------------------------------
# current_session_id (env > pointer)
# ---------------------------------------------------------------------------


class CurrentSessionIdTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.base = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()
        os.environ.pop("DCNESS_SESSION_ID", None)

    def test_env_var_takes_priority(self) -> None:
        os.environ["DCNESS_SESSION_ID"] = "env-sid"
        write_session_pointer("pointer-sid", base_dir=self.base)
        self.assertEqual(
            current_session_id(base_dir=self.base), "env-sid"
        )

    def test_pointer_used_when_env_empty(self) -> None:
        write_session_pointer("pointer-sid", base_dir=self.base)
        self.assertEqual(
            current_session_id(base_dir=self.base), "pointer-sid"
        )

    def test_returns_empty_when_both_missing(self) -> None:
        self.assertEqual(current_session_id(base_dir=self.base), "")

    def test_invalid_env_falls_to_pointer(self) -> None:
        os.environ["DCNESS_SESSION_ID"] = "../bad"
        write_session_pointer("pointer-sid", base_dir=self.base)
        self.assertEqual(
            current_session_id(base_dir=self.base), "pointer-sid"
        )


# ---------------------------------------------------------------------------
# session pointer read/write
# ---------------------------------------------------------------------------


class SessionPointerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.base = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_write_then_read(self) -> None:
        write_session_pointer("abc-sid", base_dir=self.base)
        self.assertEqual(read_session_pointer(base_dir=self.base), "abc-sid")

    def test_read_missing_returns_empty(self) -> None:
        self.assertEqual(read_session_pointer(base_dir=self.base), "")

    def test_write_invalid_raises(self) -> None:
        with self.assertRaises(ValueError):
            write_session_pointer("../bad", base_dir=self.base)

    def test_pointer_file_permissions(self) -> None:
        write_session_pointer("abc-sid", base_dir=self.base)
        path = self.base / ".session-id"
        # POSIX 만 — Windows 는 0o600 매핑이 다름
        if os.name == "posix":
            mode = path.stat().st_mode & 0o777
            self.assertEqual(mode, 0o600)


# ---------------------------------------------------------------------------
# generate_run_id
# ---------------------------------------------------------------------------


class GenerateRunIdTests(unittest.TestCase):
    def test_format(self) -> None:
        rid = generate_run_id()
        self.assertTrue(rid.startswith("run-"))
        suffix = rid[4:]
        self.assertEqual(len(suffix), 8)
        # all lowercase hex
        int(suffix, 16)  # would raise if not valid hex
        self.assertEqual(suffix, suffix.lower())

    def test_uniqueness_in_1000_calls(self) -> None:
        ids = {generate_run_id() for _ in range(1000)}
        self.assertEqual(len(ids), 1000)


# ---------------------------------------------------------------------------
# atomic_write
# ---------------------------------------------------------------------------


class AtomicWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.base = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_creates_file_with_content(self) -> None:
        target = self.base / "x.json"
        atomic_write(target, b'{"a": 1}')
        self.assertEqual(target.read_bytes(), b'{"a": 1}')

    def test_no_tmp_residue(self) -> None:
        target = self.base / "x.json"
        atomic_write(target, b"data")
        residue = list(self.base.glob("*.tmp.*"))
        self.assertEqual(residue, [])

    def test_overwrites_existing(self) -> None:
        target = self.base / "x.json"
        atomic_write(target, b"v1")
        atomic_write(target, b"v2")
        self.assertEqual(target.read_bytes(), b"v2")

    def test_default_permissions_0o600(self) -> None:
        if os.name != "posix":
            self.skipTest("0o600 검증은 POSIX 만")
        target = self.base / "x.json"
        atomic_write(target, b"data")
        mode = target.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_rejects_non_bytes(self) -> None:
        target = self.base / "x.json"
        with self.assertRaises(TypeError):
            atomic_write(target, "string")  # type: ignore[arg-type]

    def test_creates_parent_dir(self) -> None:
        target = self.base / "deep" / "nested" / "x.json"
        atomic_write(target, b"data")
        self.assertTrue(target.exists())


# ---------------------------------------------------------------------------
# session_dir / run_dir / live_path
# ---------------------------------------------------------------------------


class PathHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.base = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_session_dir_format(self) -> None:
        path = session_dir("abc-sid", base_dir=self.base)
        self.assertEqual(path, (self.base / ".sessions" / "abc-sid").resolve())

    def test_run_dir_format(self) -> None:
        rid = "run-a3f81b29"
        path = run_dir("abc", rid, base_dir=self.base)
        self.assertEqual(
            path,
            (self.base / ".sessions" / "abc" / "runs" / rid).resolve(),
        )

    def test_run_dir_create(self) -> None:
        path = run_dir("abc", "run-12345678", base_dir=self.base, create=True)
        self.assertTrue(path.exists())

    def test_session_dir_invalid_sid_raises(self) -> None:
        with self.assertRaises(ValueError):
            session_dir("../bad", base_dir=self.base)

    def test_run_dir_invalid_run_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            run_dir("abc", "not-a-run-id", base_dir=self.base)

    def test_live_path(self) -> None:
        path = live_path("abc", base_dir=self.base)
        self.assertEqual(path.name, "live.json")
        self.assertEqual(path.parent.name, "abc")


# ---------------------------------------------------------------------------
# read_live / update_live (envelope)
# ---------------------------------------------------------------------------


class LiveJsonTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.base = Path(self._td.name)
        self.sid = "abc-sid"

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_read_missing_returns_empty(self) -> None:
        self.assertEqual(read_live(self.sid, base_dir=self.base), {})

    def test_update_then_read_roundtrip(self) -> None:
        update_live(self.sid, base_dir=self.base, custom_field="hello")
        data = read_live(self.sid, base_dir=self.base)
        self.assertEqual(data["custom_field"], "hello")
        self.assertEqual(data["_meta"]["sessionId"], self.sid)
        self.assertEqual(data["_meta"]["version"], LIVE_JSON_VERSION)
        self.assertIn("writtenAt", data["_meta"])

    def test_active_runs_default_empty_dict(self) -> None:
        update_live(self.sid, base_dir=self.base, foo="bar")
        data = read_live(self.sid, base_dir=self.base)
        self.assertEqual(data["active_runs"], {})

    def test_field_none_deletes(self) -> None:
        update_live(self.sid, base_dir=self.base, x=1, y=2)
        update_live(self.sid, base_dir=self.base, x=None)
        data = read_live(self.sid, base_dir=self.base)
        self.assertNotIn("x", data)
        self.assertEqual(data["y"], 2)

    def test_cross_session_envelope_rejected(self) -> None:
        # 다른 세션이 같은 경로에 leftover 남긴 상황 시뮬
        path = live_path(self.sid, base_dir=self.base)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({
                "_meta": {"sessionId": "OTHER-SID", "writtenAt": "x", "version": 1},
                "session_id": "OTHER-SID",
                "active_runs": {"run-aaaaaaaa": {"foo": 1}},
            }),
            encoding="utf-8",
        )
        # read_live 가 다른 sid 의 데이터 거부
        self.assertEqual(read_live(self.sid, base_dir=self.base), {})

    def test_invalid_json_returns_empty(self) -> None:
        path = live_path(self.sid, base_dir=self.base)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not valid json", encoding="utf-8")
        self.assertEqual(read_live(self.sid, base_dir=self.base), {})

    def test_session_id_self_reference(self) -> None:
        update_live(self.sid, base_dir=self.base, x=1)
        data = read_live(self.sid, base_dir=self.base)
        self.assertEqual(data["session_id"], self.sid)


# ---------------------------------------------------------------------------
# active_runs operations
# ---------------------------------------------------------------------------


class ActiveRunsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.base = Path(self._td.name)
        self.sid = "abc-sid"
        self.run_id = "run-12345678"

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_start_run_adds_slot(self) -> None:
        start_run(
            self.sid, self.run_id, "impl",
            base_dir=self.base, issue_num=42,
        )
        data = read_live(self.sid, base_dir=self.base)
        slot = data["active_runs"][self.run_id]
        self.assertEqual(slot["run_id"], self.run_id)
        self.assertEqual(slot["entry_point"], "impl")
        self.assertEqual(slot["issue_num"], 42)
        self.assertIsNone(slot["completed_at"])
        self.assertIsNone(slot["current_step"])
        self.assertIn("started_at", slot)
        self.assertIn("last_confirmed_at", slot)
        self.assertIn("run_dir", slot)
        self.assertFalse(slot["acceptance_required"])

    def test_start_run_creates_dir(self) -> None:
        start_run(self.sid, self.run_id, "impl", base_dir=self.base)
        rd = run_dir(self.sid, self.run_id, base_dir=self.base)
        self.assertTrue(rd.exists())

    def test_start_run_duplicate_raises(self) -> None:
        start_run(self.sid, self.run_id, "impl", base_dir=self.base)
        with self.assertRaises(ValueError):
            start_run(self.sid, self.run_id, "impl", base_dir=self.base)

    # -- design_doc 기록 — engineer 게이트 사전 조건 증거 --

    def _chdir_base(self) -> None:
        # design_doc 검증은 repo root(= helper 호출 cwd) 기준 — base 를 root 로 모사.
        old = os.getcwd()
        os.chdir(self.base)
        self.addCleanup(os.chdir, old)

    def _write_design_doc(self, rel: str = "docs/compact-plans/foo.md") -> Path:
        doc = self.base / rel
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text("# design artifact\n", encoding="utf-8")
        return doc

    def test_start_run_records_design_doc_resolved(self) -> None:
        # 기록값 = resolve 된 절대경로 — hook 프로세스 cwd 와 무관하게 실존 확인 가능.
        self._chdir_base()
        doc = self._write_design_doc()
        start_run(
            self.sid, self.run_id, "impl",
            base_dir=self.base, design_doc="docs/compact-plans/foo.md",
        )
        slot = read_live(self.sid, base_dir=self.base)["active_runs"][self.run_id]
        self.assertEqual(slot["design_doc"], str(doc.resolve()))
        self.assertTrue(Path(slot["design_doc"]).is_absolute())

    def test_start_run_without_design_doc_records_none(self) -> None:
        start_run(self.sid, self.run_id, "impl", base_dir=self.base)
        slot = read_live(self.sid, base_dir=self.base)["active_runs"][self.run_id]
        self.assertIsNone(slot["design_doc"])

    def test_start_run_design_doc_missing_file_raises(self) -> None:
        # 기록 시점 fail-fast — 실존하지 않는 경로는 게이트에서 막히기 전에 거부.
        self._chdir_base()
        with self.assertRaises(ValueError):
            start_run(
                self.sid, self.run_id, "impl",
                base_dir=self.base,
                design_doc="docs/compact-plans/nope.md",
            )

    def test_start_run_design_doc_non_design_path_raises(self) -> None:
        # 설계 산출물 경로 규약(docs/milestones|compact-plans|bugfix) 밖 파일은
        # 사전 조건 증거가 될 수 없다 — 임의 파일로 게이트 무력화 방지.
        self._chdir_base()
        readme = self.base / "README.md"
        readme.write_text("x\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            start_run(
                self.sid, self.run_id, "impl",
                base_dir=self.base, design_doc="README.md",
            )

    def test_start_run_design_doc_non_md_raises(self) -> None:
        doc = self.base / "docs" / "compact-plans" / "foo.txt"
        doc.parent.mkdir(parents=True)
        doc.write_text("x\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            start_run(
                self.sid, self.run_id, "impl",
                base_dir=self.base, design_doc=str(doc),
            )

    def test_start_run_design_doc_traversal_rejected(self) -> None:
        # 경로 규약은 resolve *후* prefix 앵커 비교 — `..` 로 규약 디렉토리를
        # 경유만 하고 빠져나가는 우회 차단.
        self._chdir_base()
        (self.base / "README.md").write_text("x\n", encoding="utf-8")
        (self.base / "docs" / "milestones").mkdir(parents=True)
        with self.assertRaises(ValueError):
            start_run(
                self.sid, self.run_id, "impl",
                base_dir=self.base,
                design_doc="docs/milestones/../../README.md",
            )

    def test_start_run_design_doc_outside_repo_rejected(self) -> None:
        # repo 밖 절대경로는 marker 문자열을 포함해도 거부 (substring 매치 아님).
        self._chdir_base()
        with TemporaryDirectory() as td2:
            outside = Path(td2) / "docs" / "compact-plans" / "fake.md"
            outside.parent.mkdir(parents=True)
            outside.write_text("x\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                start_run(
                    self.sid, self.run_id, "impl",
                    base_dir=self.base, design_doc=str(outside),
                )

    def test_start_run_design_doc_symlink_outside_rejected(self) -> None:
        # 규약 디렉토리 안 symlink 가 규약 밖 파일을 가리키면 resolve 후 거부.
        self._chdir_base()
        target = self.base / "secret.md"
        target.write_text("x\n", encoding="utf-8")
        link_dir = self.base / "docs" / "compact-plans"
        link_dir.mkdir(parents=True)
        (link_dir / "link.md").symlink_to(target)
        with self.assertRaises(ValueError):
            start_run(
                self.sid, self.run_id, "impl",
                base_dir=self.base, design_doc="docs/compact-plans/link.md",
            )

    def test_start_run_design_doc_non_impl_entry_rejected(self) -> None:
        # design_doc 은 impl 구현 run 전용 — design run 의 engineer ←
        # module-architect PASS 강제가 코드 보장으로 유지.
        self._chdir_base()
        self._write_design_doc()
        with self.assertRaises(ValueError):
            start_run(
                self.sid, self.run_id, "design",
                base_dir=self.base, design_doc="docs/compact-plans/foo.md",
            )

    def test_start_run_design_doc_milestones_impl_path_ok(self) -> None:
        self._chdir_base()
        doc = self._write_design_doc(
            "docs/milestones/v01/epics/epic-01-x/impl/03-foo.md"
        )
        start_run(
            self.sid, self.run_id, "impl",
            base_dir=self.base,
            design_doc="docs/milestones/v01/epics/epic-01-x/impl/03-foo.md",
        )
        slot = read_live(self.sid, base_dir=self.base)["active_runs"][self.run_id]
        self.assertEqual(slot["design_doc"], str(doc.resolve()))

    # -- #714 — lane 기록 (engineer 게이트 lane-aware 사전 조건) --

    def test_start_run_records_lane(self) -> None:
        start_run(self.sid, self.run_id, "impl", base_dir=self.base, lane="lite")
        slot = read_live(self.sid, base_dir=self.base)["active_runs"][self.run_id]
        self.assertEqual(slot["lane"], "lite")

    def test_start_run_records_lane_standard(self) -> None:
        start_run(self.sid, self.run_id, "impl", base_dir=self.base, lane="standard")
        slot = read_live(self.sid, base_dir=self.base)["active_runs"][self.run_id]
        self.assertEqual(slot["lane"], "standard")

    def test_start_run_without_lane_records_none(self) -> None:
        start_run(self.sid, self.run_id, "impl", base_dir=self.base)
        slot = read_live(self.sid, base_dir=self.base)["active_runs"][self.run_id]
        self.assertIsNone(slot["lane"])

    def test_start_run_lane_invalid_value_raises(self) -> None:
        # lane 은 닫힌 enum(lite/standard) — 임의 값으로 게이트 면제를 유발하지 못한다.
        with self.assertRaises(ValueError):
            start_run(self.sid, self.run_id, "impl", base_dir=self.base, lane="deep")

    def test_start_run_lane_non_impl_entry_rejected(self) -> None:
        # lane 은 impl 구현 run 전용 — design/architect-loop run 의 engineer ←
        # module-architect PASS 강제가 코드 보장으로 유지되도록 다른 entry_point
        # 의 lane 기록 자체를 거부한다 (lite 면제가 설계 루프로 새는 것 차단).
        with self.assertRaises(ValueError):
            start_run(self.sid, self.run_id, "design", base_dir=self.base, lane="lite")

    # -- #722 — 마감 acceptance 대상 run marker --

    def test_start_run_records_acceptance_required(self) -> None:
        start_run(
            self.sid, self.run_id, "impl",
            base_dir=self.base, acceptance_required=True,
        )
        slot = read_live(self.sid, base_dir=self.base)["active_runs"][self.run_id]
        self.assertTrue(slot["acceptance_required"])

    def test_start_run_acceptance_required_non_impl_entry_rejected(self) -> None:
        # inline product-acceptance 는 impl-loop/impl run 의 마감 PR 전 게이트다.
        with self.assertRaises(ValueError):
            start_run(
                self.sid, self.run_id, "design",
                base_dir=self.base, acceptance_required=True,
            )

    def test_update_current_step(self) -> None:
        start_run(self.sid, self.run_id, "impl", base_dir=self.base)
        update_current_step(
            self.sid, self.run_id, "engineer", "IMPL",
            base_dir=self.base,
        )
        slot = read_live(self.sid, base_dir=self.base)["active_runs"][self.run_id]
        self.assertEqual(slot["current_step"]["agent"], "engineer")
        self.assertEqual(slot["current_step"]["mode"], "IMPL")

    def test_update_step_unknown_run_raises(self) -> None:
        with self.assertRaises(ValueError):
            update_current_step(
                self.sid, self.run_id, "engineer", "IMPL",
                base_dir=self.base,
            )

    def test_update_step_warn_when_prev_stale(self) -> None:
        # DCN-30-30: begin-step 호출 시 기존 current_step 의 last_confirmed_at 가
        # STALE_STEP_TTL_SEC (30min) 초과 → stderr STALE STEP WARN.
        # I4 사례 — engineer step 후 end-step 누락 시 다음 begin-step 이 잡음.
        from io import StringIO
        from contextlib import redirect_stderr

        start_run(self.sid, self.run_id, "impl", base_dir=self.base)
        # 첫 begin-step (engineer)
        update_current_step(
            self.sid, self.run_id, "engineer", "IMPL", base_dir=self.base,
        )

        # last_confirmed_at 를 31분 전으로 강제 — stale 시뮬레이션
        # update_live 는 last_confirmed_at 자체를 덮지 않으니 raw json write.
        from datetime import datetime, timedelta, timezone
        from harness.session_state import live_path
        live = read_live(self.sid, base_dir=self.base)
        slot = live["active_runs"][self.run_id]
        old_iso = (datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat()
        slot["last_confirmed_at"] = old_iso
        live["active_runs"][self.run_id] = slot
        live_path(self.sid, base_dir=self.base).write_text(
            json.dumps(live, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        # 두번째 begin-step (validator) — stale WARN 기대
        err = StringIO()
        with redirect_stderr(err):
            update_current_step(
                self.sid, self.run_id, "validator", "CODE_VALIDATION",
                base_dir=self.base,
            )
        self.assertIn("STALE STEP WARN", err.getvalue())
        self.assertIn("engineer", err.getvalue())
        # 새 current_step 박힘 (동작 정상)
        slot = read_live(self.sid, base_dir=self.base)["active_runs"][self.run_id]
        self.assertEqual(slot["current_step"]["agent"], "code-validator")

    def test_update_step_no_warn_when_prev_fresh(self) -> None:
        # last_confirmed_at 가 30min 이내면 WARN 없음 (정상 워크플로우 — 빠른 step 전환).
        from io import StringIO
        from contextlib import redirect_stderr

        start_run(self.sid, self.run_id, "impl", base_dir=self.base)
        update_current_step(
            self.sid, self.run_id, "engineer", "IMPL", base_dir=self.base,
        )
        # 즉시 다음 begin-step
        err = StringIO()
        with redirect_stderr(err):
            update_current_step(
                self.sid, self.run_id, "validator", "CODE_VALIDATION",
                base_dir=self.base,
            )
        self.assertNotIn("STALE STEP WARN", err.getvalue())

    def test_complete_run(self) -> None:
        start_run(self.sid, self.run_id, "impl", base_dir=self.base)
        complete_run(self.sid, self.run_id, base_dir=self.base)
        slot = read_live(self.sid, base_dir=self.base)["active_runs"][self.run_id]
        self.assertIsNotNone(slot["completed_at"])
        self.assertIsNone(slot["current_step"])

    def test_complete_run_idempotent_on_missing(self) -> None:
        # raise 안 함 — noop
        complete_run(self.sid, self.run_id, base_dir=self.base)

    def test_multiple_active_runs(self) -> None:
        # 동시 다중 run 지원 검증 (OMC 차용 핵심)
        start_run(self.sid, "run-aaaaaaaa", "impl", base_dir=self.base)
        start_run(self.sid, "run-bbbbbbbb", "spec", base_dir=self.base)
        data = read_live(self.sid, base_dir=self.base)
        self.assertEqual(len(data["active_runs"]), 2)


# ---------------------------------------------------------------------------
# cleanup_stale_runs
# ---------------------------------------------------------------------------


class CleanupStaleRunsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.base = Path(self._td.name)
        self.sid = "abc-sid"

    def tearDown(self) -> None:
        self._td.cleanup()

    def _set_slot(self, run_id: str, **overrides) -> None:
        # DCN-30-40 fix: hardcoded ts (2026-04-29) → now() — time bomb 회피.
        # 24h TTL 기준이라 hardcoded ts 가 시간 흐름에 따라 stale 판정 됨.
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        live = read_live(self.sid, base_dir=self.base) or {}
        active = live.get("active_runs", {}) or {}
        active[run_id] = {
            "run_id": run_id,
            "entry_point": "impl",
            "started_at": now_iso,
            "last_confirmed_at": now_iso,
            "completed_at": None,
            "run_dir": "x",
            "current_step": None,
            "issue_num": None,
        }
        active[run_id].update(overrides)
        update_live(self.sid, base_dir=self.base, active_runs=active)

    def test_removes_completed_old_slot(self) -> None:
        # 25h 전 완료된 슬롯
        old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(timespec="seconds")
        self._set_slot("run-aaaaaaaa", completed_at=old, last_confirmed_at=old)
        self._set_slot("run-bbbbbbbb")  # 신선
        removed = cleanup_stale_runs(self.sid, base_dir=self.base)
        self.assertEqual(removed, 1)
        active = read_live(self.sid, base_dir=self.base)["active_runs"]
        self.assertNotIn("run-aaaaaaaa", active)
        self.assertIn("run-bbbbbbbb", active)

    def test_removes_heartbeat_dead_slot(self) -> None:
        # 25h heartbeat 안 갱신된 슬롯 (completed 아닌데 stale)
        old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(timespec="seconds")
        self._set_slot("run-cccccccc", last_confirmed_at=old)
        removed = cleanup_stale_runs(self.sid, base_dir=self.base)
        self.assertEqual(removed, 1)

    def test_keeps_fresh_slot(self) -> None:
        self._set_slot("run-dddddddd")
        removed = cleanup_stale_runs(self.sid, base_dir=self.base)
        self.assertEqual(removed, 0)
        active = read_live(self.sid, base_dir=self.base)["active_runs"]
        self.assertIn("run-dddddddd", active)


# ---------------------------------------------------------------------------
# by-pid 레지스트리 (멀티세션 정합)
# ---------------------------------------------------------------------------


class ByPidRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        from harness.session_state import (
            valid_cc_pid, pid_session_path, pid_run_path,
            write_pid_session, read_pid_session,
            write_pid_current_run, read_pid_current_run,
            clear_pid_current_run,
        )
        self.valid_cc_pid = valid_cc_pid
        self.pid_session_path = pid_session_path
        self.pid_run_path = pid_run_path
        self.write_pid_session = write_pid_session
        self.read_pid_session = read_pid_session
        self.write_pid_current_run = write_pid_current_run
        self.read_pid_current_run = read_pid_current_run
        self.clear_pid_current_run = clear_pid_current_run
        self._td = TemporaryDirectory()
        self.base = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_valid_cc_pid(self) -> None:
        self.assertTrue(self.valid_cc_pid(12345))
        self.assertFalse(self.valid_cc_pid(0))
        self.assertFalse(self.valid_cc_pid(-1))
        self.assertFalse(self.valid_cc_pid("12345"))
        self.assertFalse(self.valid_cc_pid(None))

    def test_pid_session_path_format(self) -> None:
        path = self.pid_session_path(12345, base_dir=self.base)
        self.assertEqual(path, (self.base / ".by-pid" / "12345").resolve())

    def test_pid_run_path_format(self) -> None:
        path = self.pid_run_path(12345, base_dir=self.base)
        self.assertEqual(
            path,
            (self.base / ".by-pid-current-run" / "12345").resolve(),
        )

    def test_write_then_read_pid_session(self) -> None:
        self.write_pid_session(12345, "abc-sid", base_dir=self.base)
        self.assertEqual(
            self.read_pid_session(12345, base_dir=self.base), "abc-sid"
        )

    def test_read_pid_session_missing(self) -> None:
        self.assertEqual(self.read_pid_session(99999, base_dir=self.base), "")

    def test_read_pid_session_invalid_returns_empty(self) -> None:
        # Force write invalid sid bypassing validator
        path = self.pid_session_path(12345, base_dir=self.base)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("../bad", encoding="utf-8")
        self.assertEqual(self.read_pid_session(12345, base_dir=self.base), "")

    def test_write_then_read_pid_current_run(self) -> None:
        self.write_pid_current_run(12345, "run-12345678", base_dir=self.base)
        self.assertEqual(
            self.read_pid_current_run(12345, base_dir=self.base),
            "run-12345678",
        )

    def test_clear_pid_current_run(self) -> None:
        self.write_pid_current_run(12345, "run-12345678", base_dir=self.base)
        ok = self.clear_pid_current_run(12345, base_dir=self.base)
        self.assertTrue(ok)
        self.assertEqual(self.read_pid_current_run(12345, base_dir=self.base), "")

    def test_clear_pid_current_run_idempotent(self) -> None:
        self.assertFalse(self.clear_pid_current_run(99999, base_dir=self.base))

    def test_invalid_sid_write_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.write_pid_session(12345, "../bad", base_dir=self.base)

    def test_invalid_run_id_write_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.write_pid_current_run(12345, "not-a-run", base_dir=self.base)

    def test_invalid_cc_pid_path_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.pid_session_path(-1, base_dir=self.base)

    def test_multi_session_isolation(self) -> None:
        # 두 세션 동시 by-pid 작성 — 서로 영향 0
        self.write_pid_session(12345, "ses-A", base_dir=self.base)
        self.write_pid_session(23456, "ses-B", base_dir=self.base)
        self.write_pid_current_run(12345, "run-aaaaaaaa", base_dir=self.base)
        self.write_pid_current_run(23456, "run-bbbbbbbb", base_dir=self.base)
        self.assertEqual(
            self.read_pid_session(12345, base_dir=self.base), "ses-A"
        )
        self.assertEqual(
            self.read_pid_session(23456, base_dir=self.base), "ses-B"
        )
        self.assertEqual(
            self.read_pid_current_run(12345, base_dir=self.base), "run-aaaaaaaa"
        )
        self.assertEqual(
            self.read_pid_current_run(23456, base_dir=self.base), "run-bbbbbbbb"
        )


class CleanupStalePidTests(unittest.TestCase):
    def setUp(self) -> None:
        from harness.session_state import (
            cleanup_stale_pid_files, write_pid_session, write_pid_current_run,
        )
        self.cleanup_stale_pid_files = cleanup_stale_pid_files
        self.write_pid_session = write_pid_session
        self.write_pid_current_run = write_pid_current_run
        self._td = TemporaryDirectory()
        self.base = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_removes_old_pid_files(self) -> None:
        import time
        self.write_pid_session(12345, "old-sid", base_dir=self.base)
        # mtime 25h 전으로 조작
        path = self.base / ".by-pid" / "12345"
        old = time.time() - (25 * 3600)
        os.utime(path, (old, old))

        # 신선한 파일
        self.write_pid_session(23456, "fresh-sid", base_dir=self.base)

        removed = self.cleanup_stale_pid_files(base_dir=self.base)
        self.assertEqual(removed, 1)
        self.assertFalse((self.base / ".by-pid" / "12345").exists())
        self.assertTrue((self.base / ".by-pid" / "23456").exists())


# ---------------------------------------------------------------------------
# CLI subcommands (subprocess 통해 호출 — 회귀 검증)
# ---------------------------------------------------------------------------


class CliInitSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        from harness.session_state import _cli_init_session, read_pid_session, read_live
        self._cli_init_session = _cli_init_session
        self.read_pid_session = read_pid_session
        self.read_live = read_live
        self._td = TemporaryDirectory()
        self.base = Path(self._td.name)
        self._cwd = os.getcwd()
        os.chdir(self.base)

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        self._td.cleanup()

    def test_init_session_writes_by_pid_and_live(self) -> None:
        from types import SimpleNamespace
        rc = self._cli_init_session(
            SimpleNamespace(sid="abc-sid", cc_pid=12345)
        )
        self.assertEqual(rc, 0)
        self.assertEqual(self.read_pid_session(12345), "abc-sid")
        live = self.read_live("abc-sid")
        self.assertEqual(live["session_id"], "abc-sid")
        self.assertEqual(live["active_runs"], {})

    def test_init_session_invalid_sid(self) -> None:
        from types import SimpleNamespace
        rc = self._cli_init_session(
            SimpleNamespace(sid="../bad", cc_pid=12345)
        )
        self.assertEqual(rc, 1)

    def test_init_session_invalid_cc_pid(self) -> None:
        from types import SimpleNamespace
        rc = self._cli_init_session(
            SimpleNamespace(sid="abc-sid", cc_pid=0)
        )
        self.assertEqual(rc, 1)


class CliBeginStepEndStepTests(unittest.TestCase):
    """auto_detect_* 를 mock 하고 CLI subcommand 동작 검증."""

    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.base = Path(self._td.name)
        self._cwd = os.getcwd()
        os.chdir(self.base)
        # init session
        from harness.session_state import (
            write_pid_session, write_pid_current_run,
            start_run,
        )
        self.sid = "test-sid"
        self.rid = "run-12345678"
        self.cc_pid = 99999  # 임의
        write_pid_session(self.cc_pid, self.sid)
        from harness.session_state import update_live
        update_live(self.sid)
        start_run(self.sid, self.rid, "test-entry")
        write_pid_current_run(self.cc_pid, self.rid)
        # auto_detect 가 self.cc_pid 반환하도록 mock
        from unittest.mock import patch
        self._patcher = patch(
            "harness.session_state.get_cc_pid_via_ppid_chain",
            return_value=self.cc_pid,
        )
        self._patcher.start()
        # interpret 텔레메트리 off
        self._prev_telemetry = os.environ.get("DCNESS_LLM_TELEMETRY")
        os.environ["DCNESS_LLM_TELEMETRY"] = "0"

    def tearDown(self) -> None:
        self._patcher.stop()
        os.chdir(self._cwd)
        self._td.cleanup()
        if self._prev_telemetry is None:
            os.environ.pop("DCNESS_LLM_TELEMETRY", None)
        else:
            os.environ["DCNESS_LLM_TELEMETRY"] = self._prev_telemetry

    def test_begin_step_updates_current_step(self) -> None:
        from harness.session_state import _cli_begin_step, read_live
        from types import SimpleNamespace
        rc = _cli_begin_step(SimpleNamespace(agent="validator", mode="PLAN_VALIDATION"))
        self.assertEqual(rc, 0)
        live = read_live(self.sid)
        slot = live["active_runs"][self.rid]
        self.assertEqual(slot["current_step"]["agent"], "code-validator")
        self.assertEqual(slot["current_step"]["mode"], "PLAN_VALIDATION")

    def test_run_dir_cli_outputs_absolute_path(self) -> None:
        # DCN-30-21: run-dir subcommand for prose-staging path 격리.
        from harness.session_state import _cli_run_dir, run_dir
        from types import SimpleNamespace
        from io import StringIO
        from contextlib import redirect_stdout
        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_run_dir(SimpleNamespace())
        self.assertEqual(rc, 0)
        printed = out.getvalue().strip()
        expected = str(run_dir(self.sid, self.rid))
        self.assertEqual(printed, expected)
        # path 가 .sessions/{sid}/runs/{rid} 끝남
        self.assertTrue(printed.endswith(f".sessions/{self.sid}/runs/{self.rid}"))

    def test_cli_resolves_active_run_when_pid_current_run_pointer_missing(self) -> None:
        """issue #684 — escape hatch 없이 helper CLI 가 sid-scoped active_runs 로 복구."""
        from harness.session_state import (
            _cli_begin_step,
            _cli_end_step,
            _cli_run_dir,
            _cli_run_status,
            clear_pid_current_run,
            read_live,
            run_dir,
        )
        from types import SimpleNamespace
        from io import StringIO
        from contextlib import redirect_stdout

        clear_pid_current_run(self.cc_pid)

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_begin_step(SimpleNamespace(agent="validator", mode="CODE_VALIDATION"))
        self.assertEqual(rc, 0)
        self.assertIn("ok", out.getvalue())
        live = read_live(self.sid)
        slot = live["active_runs"][self.rid]
        self.assertEqual(slot["current_step"]["agent"], "code-validator")
        self.assertEqual(slot["current_step"]["mode"], "CODE_VALIDATION")

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_run_dir(SimpleNamespace())
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), str(run_dir(self.sid, self.rid)))

        prose_path = self.base / "validator_prose.md"
        prose_path.write_text("검증 결과 정상\n\nPASS\n", encoding="utf-8")
        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_end_step(SimpleNamespace(
                agent="validator",
                mode="CODE_VALIDATION",
                prose_file=str(prose_path),
            ))
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), "PROSE_LOGGED")

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_run_status(SimpleNamespace(run_id=None))
        self.assertEqual(rc, 0)
        self.assertIn(self.rid, out.getvalue())

    def test_step_reentry_after_finalize_resolves_same_run_without_pointer(self) -> None:
        """issue #730 — pr-reviewer FAIL 후 fix round begin-step 재진입 회귀."""
        from harness.session_state import (
            _cli_begin_step,
            _cli_end_step,
            _cli_finalize_run,
            clear_pid_current_run,
            read_live,
        )
        from types import SimpleNamespace
        from io import StringIO
        from contextlib import redirect_stdout, redirect_stderr

        clear_pid_current_run(self.cc_pid)

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_begin_step(SimpleNamespace(agent="build-worker", mode=None))
        self.assertEqual(rc, 0, out.getvalue())

        build_prose = self.base / "build_prose.md"
        build_prose.write_text("구현 라운드 완료\n\nPASS\n", encoding="utf-8")
        with redirect_stdout(StringIO()):
            rc = _cli_end_step(SimpleNamespace(
                agent="build-worker",
                mode=None,
                prose_file=str(build_prose),
            ))
        self.assertEqual(rc, 0)

        with redirect_stdout(StringIO()):
            rc = _cli_begin_step(SimpleNamespace(agent="pr-reviewer", mode=None))
        self.assertEqual(rc, 0)

        review_prose = self.base / "review_prose.md"
        review_prose.write_text("MUST FIX: 보강 필요\n\nFAIL\n", encoding="utf-8")
        with redirect_stdout(StringIO()):
            rc = _cli_end_step(SimpleNamespace(
                agent="pr-reviewer",
                mode=None,
                prose_file=str(review_prose),
            ))
        self.assertEqual(rc, 0)

        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            rc = _cli_finalize_run(SimpleNamespace(
                expected_steps=2,
                auto_review=False,
            ))
        self.assertEqual(rc, 0)
        slot = read_live(self.sid)["active_runs"][self.rid]
        self.assertIsNotNone(slot.get("finalized_at"))
        self.assertIsNone(slot.get("completed_at"))

        out = StringIO()
        err = StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = _cli_begin_step(SimpleNamespace(agent="build-worker", mode=None))
        self.assertEqual(rc, 0, err.getvalue())
        self.assertIn("ok", out.getvalue())
        slot = read_live(self.sid)["active_runs"][self.rid]
        self.assertEqual(slot["current_step"]["agent"], "build-worker")

    def test_step_reentry_after_finalize_resolves_when_pid_mapping_missing(self) -> None:
        """#625 + #730 — PPID mapping 단절 후 finalized 미완료 run 전역 fallback."""
        from harness.session_state import (
            _cli_begin_step,
            _cli_end_step,
            _cli_finalize_run,
            clear_pid_current_run,
            pid_session_path,
            read_live,
        )
        from types import SimpleNamespace
        from io import StringIO
        from contextlib import redirect_stdout, redirect_stderr

        clear_pid_current_run(self.cc_pid)
        pid_session_path(self.cc_pid).unlink()

        with redirect_stdout(StringIO()):
            rc = _cli_begin_step(SimpleNamespace(agent="build-worker", mode=None))
        self.assertEqual(rc, 0)

        build_prose = self.base / "build_prose_global.md"
        build_prose.write_text("구현 라운드 완료\n\nPASS\n", encoding="utf-8")
        with redirect_stdout(StringIO()):
            rc = _cli_end_step(SimpleNamespace(
                agent="build-worker",
                mode=None,
                prose_file=str(build_prose),
            ))
        self.assertEqual(rc, 0)

        with redirect_stdout(StringIO()):
            rc = _cli_begin_step(SimpleNamespace(agent="pr-reviewer", mode=None))
        self.assertEqual(rc, 0)

        review_prose = self.base / "review_prose_global.md"
        review_prose.write_text("MUST FIX: 보강 필요\n\nFAIL\n", encoding="utf-8")
        with redirect_stdout(StringIO()):
            rc = _cli_end_step(SimpleNamespace(
                agent="pr-reviewer",
                mode=None,
                prose_file=str(review_prose),
            ))
        self.assertEqual(rc, 0)

        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            rc = _cli_finalize_run(SimpleNamespace(
                expected_steps=2,
                auto_review=False,
            ))
        self.assertEqual(rc, 0)
        slot = read_live(self.sid)["active_runs"][self.rid]
        self.assertIsNotNone(slot.get("finalized_at"))
        self.assertIsNone(slot.get("completed_at"))

        out = StringIO()
        err = StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = _cli_begin_step(SimpleNamespace(agent="build-worker", mode=None))
        self.assertEqual(rc, 0, err.getvalue())
        self.assertIn("ok", out.getvalue())
        slot = read_live(self.sid)["active_runs"][self.rid]
        self.assertEqual(slot["current_step"]["agent"], "build-worker")

    def test_end_step_drift_warn_on_agent_mismatch(self) -> None:
        # DCN-30-25: end-step 호출 시 current_step 의 agent 와 args.agent 불일치
        # → stderr DRIFT WARN. 자동 보정 X (동작은 정상 진행).
        from harness.session_state import _cli_begin_step, _cli_end_step
        from types import SimpleNamespace
        from io import StringIO
        from contextlib import redirect_stderr, redirect_stdout

        # begin-step "validator" 박은 후 end-step "engineer" 호출
        _cli_begin_step(SimpleNamespace(agent="validator", mode="CODE_VALIDATION"))

        prose_path = self.base / "drift_prose.md"
        prose_path.write_text("## 결론\nIMPL_DONE\n", encoding="utf-8")

        err = StringIO()
        out = StringIO()
        with redirect_stderr(err), redirect_stdout(out):
            rc = _cli_end_step(SimpleNamespace(
                agent="engineer", mode="IMPL",
                prose_file=str(prose_path),
            ))
        self.assertEqual(rc, 0)
        # stdout = PROSE_LOGGED (자유서술 방식 정상 동작)
        self.assertEqual(out.getvalue().strip(), "PROSE_LOGGED")
        # stderr 에 DRIFT WARN
        self.assertIn("DRIFT WARN", err.getvalue())
        self.assertIn("validator", err.getvalue())
        self.assertIn("engineer", err.getvalue())

    def test_end_step_drift_warn_when_no_current_step(self) -> None:
        # DCN-30-25: begin-step 안 부르고 end-step 호출 → stderr WARN.
        from harness.session_state import _cli_end_step
        from types import SimpleNamespace
        from io import StringIO
        from contextlib import redirect_stderr, redirect_stdout

        prose_path = self.base / "no_begin_prose.md"
        prose_path.write_text("## 결론\nIMPL_DONE\n", encoding="utf-8")

        err = StringIO()
        out = StringIO()
        with redirect_stderr(err), redirect_stdout(out):
            rc = _cli_end_step(SimpleNamespace(
                agent="engineer", mode="IMPL",
                prose_file=str(prose_path),
            ))
        self.assertEqual(rc, 0)
        self.assertIn("DRIFT WARN", err.getvalue())
        self.assertIn("current_step 부재", err.getvalue())

    def test_finalize_run_step_count_warn(self) -> None:
        # DCN-30-25: --expected-steps 미달 시 stderr WARN.
        from harness.session_state import _cli_finalize_run
        from types import SimpleNamespace
        from io import StringIO
        from contextlib import redirect_stderr, redirect_stdout

        # .steps.jsonl 비어있음 (0 steps)
        err = StringIO()
        out = StringIO()
        with redirect_stderr(err), redirect_stdout(out):
            rc = _cli_finalize_run(SimpleNamespace(expected_steps=5))
        self.assertEqual(rc, 0)
        self.assertIn("STEP COUNT WARN", err.getvalue())
        self.assertIn("step_completed=0", err.getvalue())
        self.assertIn("expected=5", err.getvalue())

    def test_finalize_run_no_warn_when_expected_none(self) -> None:
        # --expected-steps 미명시 시 WARN 없음 (기존 호출자 backward compat).
        from harness.session_state import _cli_finalize_run
        from types import SimpleNamespace
        from io import StringIO
        from contextlib import redirect_stderr, redirect_stdout

        err = StringIO()
        out = StringIO()
        with redirect_stderr(err), redirect_stdout(out):
            rc = _cli_finalize_run(SimpleNamespace(expected_steps=None))
        self.assertEqual(rc, 0)
        self.assertNotIn("STEP COUNT WARN", err.getvalue())

    def test_finalize_run_auto_review_chains_report(self) -> None:
        # DCN-30-29: --auto-review 시 STATUS JSON 뒤에 run-review 호출 chained.
        from harness import session_state as ss
        from types import SimpleNamespace
        from io import StringIO
        from contextlib import redirect_stderr, redirect_stdout
        from unittest.mock import patch

        called = {"argv": None}

        def fake_main(argv):
            called["argv"] = list(argv)
            print("[fake-review] OK")
            return 0

        err = StringIO()
        out = StringIO()
        with patch("harness.run_review.main", side_effect=fake_main):
            with redirect_stderr(err), redirect_stdout(out):
                rc = ss._cli_finalize_run(SimpleNamespace(
                    expected_steps=None, auto_review=True,
                ))
        self.assertEqual(rc, 0)
        stdout_val = out.getvalue()
        self.assertIn("\"run_id\"", stdout_val)  # STATUS JSON 정상
        self.assertIn("--- /run-review (auto) ---", stdout_val)
        self.assertIn("[fake-review] OK", stdout_val)
        self.assertEqual(called["argv"][:2], ["--run-id", self.rid])

    def test_finalize_run_auto_review_skip_on_failure(self) -> None:
        # DCN-30-29: review_main 예외 시 STATUS 정상 + stderr WARN, exit 0.
        from harness import session_state as ss
        from types import SimpleNamespace
        from io import StringIO
        from contextlib import redirect_stderr, redirect_stdout
        from unittest.mock import patch

        def boom(argv):
            raise RuntimeError("boom")

        err = StringIO()
        out = StringIO()
        with patch("harness.run_review.main", side_effect=boom):
            with redirect_stderr(err), redirect_stdout(out):
                rc = ss._cli_finalize_run(SimpleNamespace(
                    expected_steps=None, auto_review=True,
                ))
        self.assertEqual(rc, 0)
        self.assertIn("\"run_id\"", out.getvalue())  # STATUS JSON 정상
        self.assertIn("AUTO_REVIEW_FAIL", err.getvalue())
        self.assertIn("RuntimeError", err.getvalue())

    def test_finalize_run_auto_review_off_no_chain(self) -> None:
        # --auto-review 미지정 시 review 호출 안 함 (기존 동작 보존).
        from harness import session_state as ss
        from types import SimpleNamespace
        from io import StringIO
        from contextlib import redirect_stderr, redirect_stdout
        from unittest.mock import patch

        called = {"hit": False}

        def should_not(argv):
            called["hit"] = True
            return 0

        err = StringIO()
        out = StringIO()
        with patch("harness.run_review.main", side_effect=should_not):
            with redirect_stderr(err), redirect_stdout(out):
                rc = ss._cli_finalize_run(SimpleNamespace(
                    expected_steps=None, auto_review=False,
                ))
        self.assertEqual(rc, 0)
        self.assertFalse(called["hit"])
        self.assertNotIn("/run-review (auto)", out.getvalue())

    # issue #392 — auto accumulate 매커니즘 폐기로 관련 3 tests 삭제:
    #   - test_finalize_run_auto_review_triggers_accumulate
    #   - test_finalize_run_no_accumulate_opt_out
    #   - test_finalize_run_explicit_accumulate_without_auto_review

    def _setup_fake_cc_jsonl(self, sid: str, engineer_counts: list) -> Path:
        """CC session JSONL fake — engineer toolUseResult 행 N개 박음. ts 오름차순."""
        from harness.run_review import encode_repo_path_dcness
        encoded = encode_repo_path_dcness(str(Path.cwd()))
        proj_dir = Path.home() / ".claude" / "projects" / encoded
        proj_dir.mkdir(parents=True, exist_ok=True)
        jsonl = proj_dir / f"{sid}.jsonl"
        lines = []
        for i, cnt in enumerate(engineer_counts):
            lines.append(json.dumps({
                "timestamp": f"2026-04-30T0{i}:00:00.000Z",
                "toolUseResult": {
                    "agentType": "dcness:engineer",
                    "totalToolUseCount": cnt,
                    "totalDurationMs": 1000,
                    "totalTokens": 100,
                },
            }))
        jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return jsonl

    def test_begin_step_engineer_emits_tool_use_hint(self) -> None:
        """DCN-30-36: agent='engineer' 시 직전 invocation count stderr hint."""
        from harness.session_state import _cli_begin_step
        from types import SimpleNamespace
        from io import StringIO
        from contextlib import redirect_stderr

        jsonl = self._setup_fake_cc_jsonl(self.sid, [50, 87])  # 직전 = 87
        try:
            err = StringIO()
            with redirect_stderr(err):
                rc = _cli_begin_step(SimpleNamespace(agent="engineer", mode="IMPL"))
            self.assertEqual(rc, 0)
            stderr = err.getvalue()
            self.assertIn("[hint]", stderr)
            self.assertIn("tool_use_count=87", stderr)
            self.assertIn("IMPL_PARTIAL", stderr)
        finally:
            jsonl.unlink(missing_ok=True)

    def test_begin_step_engineer_no_hint_when_no_prior(self) -> None:
        """JSONL 없거나 engineer invocation 없으면 silent."""
        from harness.session_state import _cli_begin_step
        from types import SimpleNamespace
        from io import StringIO
        from contextlib import redirect_stderr

        err = StringIO()
        with redirect_stderr(err):
            rc = _cli_begin_step(SimpleNamespace(agent="engineer", mode="IMPL"))
        self.assertEqual(rc, 0)
        self.assertNotIn("[hint]", err.getvalue())

    def test_begin_step_non_engineer_no_hint(self) -> None:
        """agent != 'engineer' 면 hint 없음 (다른 agent 도 jsonl 있어도 무관)."""
        from harness.session_state import _cli_begin_step
        from types import SimpleNamespace
        from io import StringIO
        from contextlib import redirect_stderr

        jsonl = self._setup_fake_cc_jsonl(self.sid, [200])  # 큰 값 박혀도
        try:
            err = StringIO()
            with redirect_stderr(err):
                rc = _cli_begin_step(SimpleNamespace(agent="validator", mode="CODE_VALIDATION"))
            self.assertEqual(rc, 0)
            self.assertNotIn("[hint]", err.getvalue())
        finally:
            jsonl.unlink(missing_ok=True)

    def test_end_step_prose_only_writes_prose(self) -> None:
        """자유서술 방식: --allowed-enums 없이 PROSE_LOGGED + prose 파일 저장."""
        from harness.session_state import _cli_end_step, session_dir
        from types import SimpleNamespace
        prose_path = self.base / "tmp_prose.md"
        prose_path.write_text("## 결과\n검증.\n## 결론\nPASS\n", encoding="utf-8")

        # capture stdout
        from io import StringIO
        from contextlib import redirect_stdout
        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_end_step(SimpleNamespace(
                agent="validator",
                mode="PLAN_VALIDATION",
                prose_file=str(prose_path),
            ))
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), "PROSE_LOGGED")

        # prose 저장 확인 (메인이 직접 읽고 분기 판단)
        prose_md = (
            session_dir(self.sid) / "runs" / self.rid /
            "code-validator-PLAN_VALIDATION.md"
        )
        self.assertTrue(prose_md.exists())

    def test_end_step_prose_only_mode_no_allowed_enums(self) -> None:
        """자유서술 방식 (이슈 #280/#284) — PROSE_LOGGED + prose 저장 + .steps.jsonl + stderr 요약."""
        from harness.session_state import (
            _cli_end_step, session_dir, _read_steps_jsonl,
        )
        from types import SimpleNamespace
        prose_path = self.base / "tmp_prose.md"
        prose_path.write_text(
            "## 결론\n\n자유로운 자연어 prose. enum 없음. 메인이 직접 분기 판단.\n",
            encoding="utf-8",
        )

        from io import StringIO
        from contextlib import redirect_stdout, redirect_stderr
        out = StringIO()
        err = StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = _cli_end_step(SimpleNamespace(
                agent="code-validator",
                mode="",
                prose_file=str(prose_path),
            ))
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), "PROSE_LOGGED")
        # prose 자체는 저장됨 (메인이 직접 읽고 분기 판단)
        prose_md = session_dir(self.sid) / "runs" / self.rid / "code-validator.md"
        self.assertTrue(prose_md.exists())
        self.assertIn("자연어", prose_md.read_text(encoding="utf-8"))
        # stderr 에 [code-validator = PROSE_LOGGED] 헤더 (모든 skill 자동 요약 수혜)
        self.assertIn("[code-validator = PROSE_LOGGED]", err.getvalue())
        # .steps.jsonl 에 PROSE_LOGGED row append (finalize-run / run-review 입력)
        steps = _read_steps_jsonl(self.sid, self.rid)
        self.assertTrue(steps)
        self.assertEqual(steps[-1]["agent"], "code-validator")
        self.assertEqual(steps[-1]["enum"], "PROSE_LOGGED")

    def test_end_step_prose_only_does_not_extract_enum_word(self) -> None:
        """어휘 보존 ≠ 기계추출: prose 에 PASS 단어가 있어도 추출 안 하고 PROSE_LOGGED."""
        from harness.session_state import _cli_end_step
        from types import SimpleNamespace
        prose_path = self.base / "enum_word_prose.md"
        prose_path.write_text("## 결론\n\nPASS — pr-reviewer 권고\n", encoding="utf-8")

        from io import StringIO
        from contextlib import redirect_stdout
        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_end_step(SimpleNamespace(
                agent="code-validator",
                mode="",
                prose_file=str(prose_path),
            ))
        self.assertEqual(rc, 0)
        # PASS 단어가 prose 에 있어도 기계 추출 안 함 — 항상 PROSE_LOGGED
        self.assertEqual(out.getvalue().strip(), "PROSE_LOGGED")

    def test_end_step_prose_only_mode_attribute_missing(self) -> None:
        """`--allowed-enums` attribute 자체 부재 SimpleNamespace 도 정상 (코드 미참조)."""
        from harness.session_state import _cli_end_step
        from types import SimpleNamespace
        prose_path = self.base / "tmp_prose.md"
        prose_path.write_text("any text\n", encoding="utf-8")

        from io import StringIO
        from contextlib import redirect_stdout
        out = StringIO()
        with redirect_stdout(out):
            ns = SimpleNamespace(
                agent="engineer",
                mode="IMPL",
                prose_file=str(prose_path),
            )  # allowed_enums attribute 부재 — 코드가 더 이상 참조 안 함
            rc = _cli_end_step(ns)
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), "PROSE_LOGGED")

    def test_end_step_no_prose_file_uses_hook_staged(self) -> None:
        # DCN-CHG-20260501-15: --prose-file 미제공 시 live.json.current_step.prose_file 사용
        from harness.session_state import (
            _cli_end_step, _cli_begin_step, session_dir, read_live, update_live,
        )
        from types import SimpleNamespace
        from io import StringIO
        from contextlib import redirect_stdout, redirect_stderr

        # begin-step 으로 current_step 설정
        _cli_begin_step(SimpleNamespace(agent="code-validator", mode=""))

        # hook 이 staged 한 것처럼 prose_file 을 live.json.current_step 에 삽입
        prose_text = "## 결론\nPASS\n"
        staged_path = session_dir(self.sid) / "runs" / self.rid / "code-validator.md"
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        staged_path.write_text(prose_text, encoding="utf-8")

        live = read_live(self.sid) or {}
        active = live.get("active_runs", {}) or {}
        slot = dict(active.get(self.rid, {}))
        cur_step = dict(slot.get("current_step") or {})
        cur_step["prose_file"] = str(staged_path)
        slot["current_step"] = cur_step
        active[self.rid] = slot
        update_live(self.sid, active_runs=active)

        out = StringIO()
        err = StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = _cli_end_step(SimpleNamespace(
                agent="code-validator",
                mode="",
                prose_file=None,
            ))
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), "PROSE_LOGGED")
        live_after = read_live(self.sid) or {}
        slot_after = live_after.get("active_runs", {}).get(self.rid, {})
        self.assertIsNone(slot_after.get("current_step"))

    def test_end_step_no_prose_file_no_staging_returns_1(self) -> None:
        # DCN-CHG-20260501-15: --prose-file 없고 hook staging 도 없으면 rc=1
        from harness.session_state import _cli_end_step, _cli_begin_step
        from types import SimpleNamespace
        from io import StringIO
        from contextlib import redirect_stdout, redirect_stderr

        _cli_begin_step(SimpleNamespace(agent="code-validator", mode=""))
        out = StringIO()
        err = StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = _cli_end_step(SimpleNamespace(
                agent="code-validator",
                mode="",
                prose_file=None,
            ))
        self.assertEqual(rc, 1)
        self.assertIn("hook staging 없음", err.getvalue())

    def test_end_step_argparse_accepts_prose_file_only(self) -> None:
        """argparse 회귀: end-step 은 --prose-file 만 받고 정상 파싱 (--allowed-enums 폐기)."""
        from harness.session_state import _build_arg_parser
        parser = _build_arg_parser()
        ns = parser.parse_args(
            ["end-step", "code-validator", "--prose-file", "/tmp/x.md"]
        )
        self.assertEqual(ns.cmd, "end-step")
        self.assertEqual(ns.agent, "code-validator")
        self.assertEqual(ns.prose_file, "/tmp/x.md")
        self.assertFalse(hasattr(ns, "allowed_enums"))

    def test_end_step_argparse_rejects_removed_allowed_enums_flag(self) -> None:
        """argparse 회귀: 폐기된 --allowed-enums 플래그는 거부 (SystemExit)."""
        from harness.session_state import _build_arg_parser
        from io import StringIO
        from contextlib import redirect_stderr
        parser = _build_arg_parser()
        err = StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit):
            parser.parse_args(
                ["end-step", "code-validator", "--allowed-enums", "PASS,FAIL"]
            )


class DefaultBaseWorktreeTests(unittest.TestCase):
    """`_default_base()` γ 설계 — main repo `.claude/harness-state/` 단일 source 검증.

    옵션 C (worktree keyword 트리거) 도입 시:
      - Skill Step 0 에서 EnterWorktree → cwd = `.claude/worktrees/{name}/`
      - SessionStart 훅은 main repo cwd 에서 발화 → main repo 의 .by-pid 작성
      - worktree 안 helper 가 by-pid 못 찾으면 catastrophic 미동작

    γ 해법: `_default_base()` 가 git rev-parse --git-common-dir 으로 main repo
    `.git` 추출 → parent = main repo root → state root 단일 source.
    """

    def setUp(self) -> None:
        from harness.session_state import _clear_default_base_cache
        self._orig_cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(lambda: os.chdir(self._orig_cwd))
        _clear_default_base_cache()
        self.addCleanup(_clear_default_base_cache)

    def _init_git_repo(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        for cmd in (
            ["git", "init", "-q"],
            ["git", "config", "user.email", "test@example.com"],
            ["git", "config", "user.name", "test"],
            ["git", "commit", "-q", "--allow-empty", "-m", "init"],
        ):
            subprocess.run(cmd, cwd=path, check=True, capture_output=True)

    def test_resolves_to_main_repo_in_plain_repo(self) -> None:
        """일반 repo cwd 에서 _default_base() = repo/.claude/harness-state."""
        from harness.session_state import _default_base
        repo = Path(self._tmp.name) / "repo"
        self._init_git_repo(repo)
        os.chdir(repo)
        base = _default_base()
        self.assertEqual(
            base.resolve(),
            (repo / ".claude" / "harness-state").resolve(),
        )

    def test_resolves_to_main_repo_from_worktree(self) -> None:
        """worktree 안에서 _default_base() = main repo 의 harness-state.

        γ 핵심 — worktree 안 helper 가 main repo state 를 단일 source 로 본다.
        """
        from harness.session_state import _default_base
        repo = Path(self._tmp.name) / "main"
        self._init_git_repo(repo)
        wt_path = Path(self._tmp.name) / "wt-test"
        subprocess.run(
            ["git", "worktree", "add", "-q", str(wt_path), "-b", "wt-branch"],
            cwd=repo, check=True, capture_output=True,
        )
        try:
            os.chdir(wt_path)
            base = _default_base()
            self.assertEqual(
                base.resolve(),
                (repo / ".claude" / "harness-state").resolve(),
            )
        finally:
            os.chdir(self._orig_cwd)
            subprocess.run(
                ["git", "worktree", "remove", str(wt_path), "--force"],
                cwd=repo, check=False, capture_output=True,
            )

    def test_falls_back_to_cwd_outside_git(self) -> None:
        """git 리포 아닌 cwd → cwd/.claude/harness-state 폴백."""
        from harness.session_state import _default_base
        non_git = Path(self._tmp.name) / "no-git"
        non_git.mkdir()
        os.chdir(non_git)
        base = _default_base()
        self.assertEqual(
            base.resolve(),
            (non_git / ".claude" / "harness-state").resolve(),
        )

    def test_cache_returns_same_path_for_same_cwd(self) -> None:
        """동일 cwd 두 번 호출 → 같은 Path."""
        from harness.session_state import _default_base
        repo = Path(self._tmp.name) / "repo"
        self._init_git_repo(repo)
        os.chdir(repo)
        b1 = _default_base()
        b2 = _default_base()
        self.assertEqual(b1, b2)

    def test_pid_session_consistent_main_and_worktree(self) -> None:
        """main repo 에서 write 한 by-pid 를 worktree cwd 에서도 read — γ 정합 핵심."""
        from harness.session_state import (
            write_pid_session,
            read_pid_session,
            _clear_default_base_cache,
        )
        repo = Path(self._tmp.name) / "main"
        self._init_git_repo(repo)
        wt_path = Path(self._tmp.name) / "wt"
        subprocess.run(
            ["git", "worktree", "add", "-q", str(wt_path), "-b", "wt"],
            cwd=repo, check=True, capture_output=True,
        )
        cc_pid = 12345
        try:
            os.chdir(repo)
            _clear_default_base_cache()
            write_pid_session(cc_pid, "test-sid")
            self.assertTrue(
                (repo / ".claude" / "harness-state" / ".by-pid" / str(cc_pid)).exists()
            )
            os.chdir(wt_path)
            _clear_default_base_cache()
            sid_from_wt = read_pid_session(cc_pid)
            self.assertEqual(sid_from_wt, "test-sid")
        finally:
            os.chdir(self._orig_cwd)
            subprocess.run(
                ["git", "worktree", "remove", str(wt_path), "--force"],
                cwd=repo, check=False, capture_output=True,
            )


class ProjectActivationTests(unittest.TestCase):
    """프로젝트 활성화 (whitelist) — `is_project_active` / `enable_project` / `disable_project`.

    plugin-scoped whitelist 경로는 `~/.claude/plugins/data/dcness-dcness/projects.json`.
    테스트는 `DCNESS_WHITELIST_PATH` env 로 임시 경로 override.
    """

    def setUp(self) -> None:
        from harness.session_state import _clear_default_base_cache
        self._orig_cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(lambda: os.chdir(self._orig_cwd))
        # DCNESS_WHITELIST_PATH override
        self._whitelist_file = Path(self._tmp.name) / "projects.json"
        self._env_patch = patch.dict(
            os.environ,
            {"DCNESS_WHITELIST_PATH": str(self._whitelist_file)},
            clear=False,
        )
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)
        # DCNESS_FORCE_ENABLE env 가 외부에서 1로 set 되면 테스트 깨짐 — 보호
        if "DCNESS_FORCE_ENABLE" in os.environ:
            self._force_patch = patch.dict(
                os.environ, {"DCNESS_FORCE_ENABLE": ""}, clear=False
            )
            self._force_patch.start()
            self.addCleanup(self._force_patch.stop)
        _clear_default_base_cache()
        self.addCleanup(_clear_default_base_cache)

    def _init_git_repo(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        for cmd in (
            ["git", "init", "-q"],
            ["git", "config", "user.email", "test@example.com"],
            ["git", "config", "user.name", "test"],
            ["git", "commit", "-q", "--allow-empty", "-m", "init"],
        ):
            subprocess.run(cmd, cwd=path, check=True, capture_output=True)

    def test_inactive_when_whitelist_empty(self) -> None:
        from harness.session_state import is_project_active
        repo = Path(self._tmp.name) / "repo"
        self._init_git_repo(repo)
        os.chdir(repo)
        self.assertFalse(is_project_active())

    def test_enable_then_active(self) -> None:
        from harness.session_state import is_project_active, enable_project
        repo = Path(self._tmp.name) / "repo"
        self._init_git_repo(repo)
        os.chdir(repo)
        root = enable_project()
        self.assertEqual(root, repo.resolve())
        self.assertTrue(is_project_active())
        # 파일이 작성됐는지
        self.assertTrue(self._whitelist_file.exists())

    def test_disable_then_inactive(self) -> None:
        from harness.session_state import (
            is_project_active, enable_project, disable_project
        )
        repo = Path(self._tmp.name) / "repo"
        self._init_git_repo(repo)
        os.chdir(repo)
        enable_project()
        self.assertTrue(is_project_active())
        disable_project()
        self.assertFalse(is_project_active())

    def test_enable_idempotent(self) -> None:
        from harness.session_state import enable_project, list_active_projects
        repo = Path(self._tmp.name) / "repo"
        self._init_git_repo(repo)
        os.chdir(repo)
        enable_project()
        enable_project()
        enable_project()
        self.assertEqual(len(list_active_projects()), 1)

    def test_subdirectory_inherits_active(self) -> None:
        """activated 프로젝트의 subdir 도 active 로 판정."""
        from harness.session_state import is_project_active, enable_project
        repo = Path(self._tmp.name) / "repo"
        self._init_git_repo(repo)
        sub = repo / "subdir" / "deep"
        sub.mkdir(parents=True)
        os.chdir(repo)
        enable_project()
        os.chdir(sub)
        self.assertTrue(is_project_active())

    def test_worktree_inherits_active_via_gamma(self) -> None:
        """worktree cwd 에서 is_project_active = True (γ resolution → main repo whitelist hit)."""
        from harness.session_state import (
            is_project_active, enable_project, _clear_default_base_cache,
        )
        repo = Path(self._tmp.name) / "main"
        self._init_git_repo(repo)
        wt = Path(self._tmp.name) / "wt"
        subprocess.run(
            ["git", "worktree", "add", "-q", str(wt), "-b", "wt"],
            cwd=repo, check=True, capture_output=True,
        )
        try:
            os.chdir(repo)
            _clear_default_base_cache()
            enable_project()
            os.chdir(wt)
            _clear_default_base_cache()
            self.assertTrue(is_project_active())
        finally:
            os.chdir(self._orig_cwd)
            subprocess.run(
                ["git", "worktree", "remove", str(wt), "--force"],
                cwd=repo, check=False, capture_output=True,
            )

    def test_force_enable_env_override(self) -> None:
        """DCNESS_FORCE_ENABLE=1 → whitelist 무시 + 무조건 active."""
        from harness.session_state import is_project_active
        repo = Path(self._tmp.name) / "repo"
        self._init_git_repo(repo)
        os.chdir(repo)
        with patch.dict(os.environ, {"DCNESS_FORCE_ENABLE": "1"}, clear=False):
            self.assertTrue(is_project_active())

    def test_other_project_remains_inactive(self) -> None:
        """A 만 enable 했을 때 B 는 inactive."""
        from harness.session_state import is_project_active, enable_project
        repo_a = Path(self._tmp.name) / "a"
        repo_b = Path(self._tmp.name) / "b"
        self._init_git_repo(repo_a)
        self._init_git_repo(repo_b)
        os.chdir(repo_a)
        enable_project()
        os.chdir(repo_b)
        self.assertFalse(is_project_active())

    def test_whitelist_corrupt_returns_empty(self) -> None:
        """projects.json 파일 깨졌을 때 빈 리스트 반환 (silent)."""
        from harness.session_state import list_active_projects
        self._whitelist_file.parent.mkdir(parents=True, exist_ok=True)
        self._whitelist_file.write_text("not valid json", encoding="utf-8")
        self.assertEqual(list_active_projects(), [])

    def test_cli_is_active_exit_code(self) -> None:
        """`is-active` subcommand exit 0=active, 1=inactive."""
        from harness.session_state import _cli_is_active, enable_project
        from types import SimpleNamespace
        repo = Path(self._tmp.name) / "repo"
        self._init_git_repo(repo)
        os.chdir(repo)
        # 비활성
        self.assertEqual(_cli_is_active(SimpleNamespace()), 1)
        # 활성화 후
        enable_project()
        self.assertEqual(_cli_is_active(SimpleNamespace()), 0)


class HelperAutomationTests(unittest.TestCase):
    """Option A foundation — end-step prose 요약 / finalize-run / auto-resolve.

    DCN-CHG-20260430-XX. helper-side 자동화로 skill prompt 슬림화 + 사용자 가시성 ↑.
    """

    def setUp(self) -> None:
        from harness.session_state import _clear_default_base_cache
        self._orig_cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        self._prose_occurrences: dict = {}
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(lambda: os.chdir(self._orig_cwd))
        _clear_default_base_cache()
        self.addCleanup(_clear_default_base_cache)

    def _append_step_status_with_prose(
        self,
        sid: str,
        rid: str,
        agent: str,
        mode: str | None,
        enum: str,
        prose: str,
    ) -> None:
        from harness.session_state import _append_step_status, run_dir

        key = (sid, rid, agent, mode)
        occurrence = self._prose_occurrences.get(key, 0)
        self._prose_occurrences[key] = occurrence + 1
        stem = f"{agent}-{mode}" if mode else agent
        suffix = f"-{occurrence}" if occurrence else ""
        prose_path = run_dir(sid, rid) / f"{stem}{suffix}.md"
        prose_path.write_text(prose, encoding="utf-8")
        _append_step_status(sid, rid, agent, mode, enum, prose, prose_path)

    def test_extract_prose_summary_prefers_conclusion_section(self) -> None:
        """`## 결론` 섹션이 있으면 그 본문 우선 (DCN-CHG-30-11)."""
        from harness.session_state import _extract_prose_summary
        prose = """## 변경 분석
복잡한 분석 줄1.
복잡한 분석 줄2.

## 결론
PASS — 빈 문자열 가드 추가.
- src/greet.py:4 ValueError raise
- 테스트 추가
"""
        out = _extract_prose_summary(prose)
        self.assertIn("PASS", out)
        self.assertIn("ValueError raise", out)
        # `## 변경 분석` 섹션 본문은 안 들어와야 (결론 우선)
        self.assertNotIn("복잡한 분석", out)

    def test_extract_prose_summary_summary_section_alias(self) -> None:
        """`## Summary` (영어) 도 동일 동작."""
        from harness.session_state import _extract_prose_summary
        prose = (
            "## Background\nUNIQUE_BG_LINE_xyz\n"
            "## Summary\nIMPL_DONE — 5 files modified.\n- src/foo.py:10\n"
        )
        out = _extract_prose_summary(prose)
        self.assertIn("IMPL_DONE", out)
        self.assertIn("src/foo.py", out)  # Summary 섹션 본문이라 포함
        self.assertNotIn("UNIQUE_BG_LINE_xyz", out)  # Background 섹션은 제외

    def test_extract_prose_summary_change_summary_korean(self) -> None:
        """`## 변경 요약` 도 우선 추출."""
        from harness.session_state import _extract_prose_summary
        prose = "## 배경\nbg\n## 변경 요약\n핵심 변경 1\n핵심 변경 2\n"
        out = _extract_prose_summary(prose)
        self.assertIn("핵심 변경 1", out)
        self.assertNotIn("bg", out)

    def test_extract_prose_summary_fallback_when_no_section(self) -> None:
        """결론/요약 헤더 부재 → 첫 N 줄 fallback."""
        from harness.session_state import _extract_prose_summary
        prose = "no headers\nPASS\nbody\n"
        out = _extract_prose_summary(prose)
        self.assertIn("PASS", out)

    def test_extract_prose_summary_change_only_word_not_match(self) -> None:
        """`## 변경` 단독은 매칭 X (`## 변경 분석` 등 generic 헤더 회피)."""
        from harness.session_state import _CONCLUSION_HEADER_RE
        # 매칭 안 되어야
        self.assertFalse(_CONCLUSION_HEADER_RE.match("## 변경 분석"))
        # 매칭 되어야
        self.assertTrue(_CONCLUSION_HEADER_RE.match("## 변경 요약"))
        self.assertTrue(_CONCLUSION_HEADER_RE.match("## 변경 사항"))
        self.assertTrue(_CONCLUSION_HEADER_RE.match("## 결론"))

    def test_extract_prose_summary_respects_line_limit(self) -> None:
        from harness.session_state import _extract_prose_summary
        prose = "\n".join([f"line {i}" for i in range(20)])
        out = _extract_prose_summary(prose, max_lines=3)
        self.assertEqual(len(out.splitlines()), 3)

    def test_extract_prose_summary_respects_char_cap(self) -> None:
        """char cap 1200 (DCN-CHG-30-11 — 600 → 1200 확장)."""
        from harness.session_state import _extract_prose_summary
        prose = "a" * 1000 + "\n" + "b" * 1000
        out = _extract_prose_summary(prose)
        # 2개 라인 뒤 cap 도달 — 정확한 길이는 구현체 결정. 너무 크지 않으면 OK.
        self.assertLess(len(out), 2500)

    def test_append_step_status_creates_jsonl(self) -> None:
        from harness.session_state import (
            _read_steps_jsonl,
            run_dir,
            _clear_default_base_cache,
        )
        repo = Path(self._tmp.name) / "repo"
        repo.mkdir()
        # 가짜 git repo 흉내 — 비-git 폴백으로 동작
        os.chdir(repo)
        _clear_default_base_cache()

        sid = "test-sid"
        rid = "run-deadbeef"
        run_dir(sid, rid, create=True)
        self._append_step_status_with_prose(
            sid, rid, "code-validator", None, "PASS", "code-validator prose body"
        )
        self._append_step_status_with_prose(
            sid, rid, "module-architect", None, "PASS",
            "## 결론\nPASS\n## 변경\n무언가",
        )
        records = _read_steps_jsonl(sid, rid)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["agent"], "code-validator")
        self.assertEqual(records[0]["enum"], "PASS")
        self.assertIsNone(records[1]["mode"])
        self.assertFalse(records[0]["must_fix"])

    def test_append_step_status_detects_must_fix(self) -> None:
        from harness.session_state import (
            _read_steps_jsonl, run_dir,
            _clear_default_base_cache,
        )
        repo = Path(self._tmp.name) / "repo"
        repo.mkdir()
        os.chdir(repo)
        _clear_default_base_cache()
        run_dir("sid", "run-aaaa1111", create=True)
        self._append_step_status_with_prose(
            "sid", "run-aaaa1111", "pr-reviewer", None, "CHANGES_REQUESTED",
            "## 결론\nCHANGES_REQUESTED\n## MUST FIX\n- src/foo.py:10 race condition\n",
        )
        records = _read_steps_jsonl("sid", "run-aaaa1111")
        self.assertTrue(records[0]["must_fix"])

    def test_must_fix_negation_no_false_positive(self) -> None:
        """DCN-CHG-20260501-09 — pr-reviewer 의 'MUST FIX 0' / 'MUST FIX 없음' 부정문은 must_fix=False.

        자장 run-ef6c2c00 회귀 — 6 pr-reviewer step 모두 'MUST FIX 0, NICE TO HAVE 6' 패턴 →
        단순 단어경계 regex 가 매칭 → MUST_FIX_GHOST 6건 false positive.
        """
        from harness.session_state import (
            _read_steps_jsonl, run_dir,
            _clear_default_base_cache,
        )
        repo = Path(self._tmp.name) / "repo"
        repo.mkdir()
        os.chdir(repo)
        _clear_default_base_cache()
        run_dir("sid", "run-bbbb2222", create=True)
        # 자장 실 케이스 그대로
        self._append_step_status_with_prose(
            "sid", "run-bbbb2222", "pr-reviewer", None, "LGTM",
            "MUST FIX 0, NICE TO HAVE 6 (let tree: any / dead code).\nLGTM\n",
        )
        self._append_step_status_with_prose(
            "sid", "run-bbbb2222", "pr-reviewer", None, "LGTM",
            "MUST FIX: 0\n결론: LGTM\n",
        )
        self._append_step_status_with_prose(
            "sid", "run-bbbb2222", "pr-reviewer", None, "LGTM",
            "검토 결과: MUST FIX 없음. NICE TO HAVE 3.\nLGTM\n",
        )
        records = _read_steps_jsonl("sid", "run-bbbb2222")
        for r in records:
            self.assertFalse(r["must_fix"], f"false positive: {r['prose_excerpt'][:60]}")

    def test_must_fix_negation_kr_label_form(self) -> None:
        """DCN-CHG-20260523 (#484 Case 2) — `**MUST FIX 항목**: 없음` 한국어 라벨 형태 부정 인식.

        jajang run-e630af3a pr-reviewer 회귀 — `**MUST FIX 항목**: 없음`
        라인이 `[\\s:=]*` between 영역에 `**`, `항목`, `:` 가 끼어 못 매치 →
        `_has_positive_must_fix` 가 True 반환 → MUST_FIX_LEAK false positive.
        """
        from harness.session_state import (
            _read_steps_jsonl, run_dir,
            _clear_default_base_cache,
        )
        repo = Path(self._tmp.name) / "repo"
        repo.mkdir()
        os.chdir(repo)
        _clear_default_base_cache()
        run_dir("sid", "run-dddd4444", create=True)
        # 자장 task2 pr-reviewer 실 prose 형태
        self._append_step_status_with_prose(
            "sid", "run-dddd4444", "pr-reviewer", None, "LGTM",
            "**MUST FIX 항목**: 없음\n**NICE TO HAVE 항목**:\n- D 데드코드\n",
        )
        # 변형 — 라벨 + 콜론 + 부정
        self._append_step_status_with_prose(
            "sid", "run-dddd4444", "pr-reviewer", None, "LGTM",
            "MUST FIX 항목: 없음\nNICE TO HAVE: 3건\n",
        )
        # 변형 — 해당 없음
        self._append_step_status_with_prose(
            "sid", "run-dddd4444", "pr-reviewer", None, "LGTM",
            "MUST FIX: 해당 없음\n",
        )
        # 변형 — bold + `:` 없이 직접 부정
        self._append_step_status_with_prose(
            "sid", "run-dddd4444", "pr-reviewer", None, "LGTM",
            "**MUST FIX** 없음\n",
        )
        records = _read_steps_jsonl("sid", "run-dddd4444")
        for r in records:
            self.assertFalse(
                r["must_fix"],
                f"false positive (kr label form): {r['prose_excerpt'][:80]}",
            )

    def test_must_fix_positive_still_detected(self) -> None:
        """negation regex 가 *진짜* MUST FIX 케이스는 정확히 검출."""
        from harness.session_state import (
            _read_steps_jsonl, run_dir,
            _clear_default_base_cache,
        )
        repo = Path(self._tmp.name) / "repo"
        repo.mkdir()
        os.chdir(repo)
        _clear_default_base_cache()
        run_dir("sid", "run-cccc3333", create=True)
        self._append_step_status_with_prose(
            "sid", "run-cccc3333", "pr-reviewer", None, "CHANGES_REQUESTED",
            "## MUST FIX\n- audio buffer underflow on iOS\n",
        )
        self._append_step_status_with_prose(
            "sid", "run-cccc3333", "pr-reviewer", None, "CHANGES_REQUESTED",
            "MUST FIX: storage 키 충돌 가능\nLGTM 후보 X\n",
        )
        # mixed — 부정 라인 + positive 라인 → True (positive 우선)
        self._append_step_status_with_prose(
            "sid", "run-cccc3333", "pr-reviewer", None, "CHANGES_REQUESTED",
            "MUST FIX 0\nMUST FIX: 실제 이슈 발견\n",
        )
        records = _read_steps_jsonl("sid", "run-cccc3333")
        self.assertEqual(len(records), 3)
        for r in records:
            self.assertTrue(r["must_fix"], f"missed positive: {r['prose_excerpt'][:60]}")

    def test_finalize_run_outputs_status_json(self) -> None:
        from harness.session_state import (
            _cli_finalize_run,
            run_dir, _clear_default_base_cache, write_pid_session,
            write_pid_current_run, get_cc_pid_via_ppid_chain,
        )
        from io import StringIO
        from contextlib import redirect_stdout
        from types import SimpleNamespace

        repo = Path(self._tmp.name) / "repo"
        repo.mkdir()
        os.chdir(repo)
        _clear_default_base_cache()

        # by-pid 인프라 흉내 — auto_detect 가 sid/rid 찾을 수 있도록
        cc_pid = get_cc_pid_via_ppid_chain()
        if cc_pid is None:
            self.skipTest("cc_pid 추출 불가 — CI 환경 의존")
        sid = "smoke-fin-sid"
        rid = "run-finalize"
        write_pid_session(cc_pid, sid)
        run_dir(sid, rid, create=True)
        write_pid_current_run(cc_pid, rid)

        self._append_step_status_with_prose(
            sid, rid, "code-validator", None, "PASS", "ok"
        )
        self._append_step_status_with_prose(
            sid, rid, "module-architect", None, "PASS", "ok"
        )
        self._append_step_status_with_prose(
            sid, rid, "engineer", "IMPL", "IMPL_DONE", "fix done"
        )
        self._append_step_status_with_prose(
            sid, rid, "validator", "BUGFIX_VALIDATION", "PASS", "verified"
        )
        self._append_step_status_with_prose(
            sid, rid, "pr-reviewer", None, "LGTM", "looks good"
        )

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_finalize_run(SimpleNamespace())
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["run_id"], rid)
        self.assertEqual(payload["session_id"], sid)
        self.assertEqual(payload["step_count"], 5)
        self.assertFalse(payload["has_ambiguous"])
        self.assertFalse(payload["has_must_fix"])
        self.assertEqual(len(payload["steps"]), 5)

    def test_finalize_run_must_fix_resolved_by_polish_lgtm(self) -> None:
        """#272 W4 — pr-reviewer CHANGES_REQUESTED → POLISH → pr-reviewer LGTM 시
        has_must_fix=False (sticky 미발생). latest-per-role 평가 회귀."""
        from harness.session_state import (
            _cli_finalize_run,
            run_dir, _clear_default_base_cache, write_pid_session,
            write_pid_current_run, get_cc_pid_via_ppid_chain,
        )
        from io import StringIO
        from contextlib import redirect_stdout
        from types import SimpleNamespace

        repo = Path(self._tmp.name) / "repo-mustfix"
        repo.mkdir()
        os.chdir(repo)
        _clear_default_base_cache()

        cc_pid = get_cc_pid_via_ppid_chain()
        if cc_pid is None:
            self.skipTest("cc_pid 추출 불가 — CI 환경 의존")
        sid = "smoke-mustfix-sid"
        rid = "run-abcd1234"
        write_pid_session(cc_pid, sid)
        run_dir(sid, rid, create=True)
        write_pid_current_run(cc_pid, rid)

        # impl-task-loop fallback 전형 시퀀스 — pr-reviewer CHANGES_REQUESTED →
        # engineer POLISH → pr-reviewer LGTM. 첫 pr-reviewer prose 에 MUST FIX 포함.
        self._append_step_status_with_prose(
            sid, rid, "code-validator", None, "PASS", "ok"
        )
        self._append_step_status_with_prose(
            sid, rid, "module-architect", None, "PASS", "ok"
        )
        self._append_step_status_with_prose(
            sid, rid, "engineer", "IMPL", "IMPL_DONE", "first attempt"
        )
        self._append_step_status_with_prose(
            sid, rid, "validator", "BUGFIX_VALIDATION", "PASS", "verified",
        )
        self._append_step_status_with_prose(
            sid, rid, "pr-reviewer", None, "CHANGES_REQUESTED",
            "## MUST FIX\n- 1번 항목 고치자\n",
        )
        self._append_step_status_with_prose(
            sid, rid, "engineer", "POLISH", "POLISH_DONE", "fixed",
        )
        self._append_step_status_with_prose(
            sid, rid, "pr-reviewer", None, "LGTM",
            "## 결론\nLGTM\nMUST FIX 없음\n",
        )

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_finalize_run(SimpleNamespace())
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["step_count"], 7)
        # latest pr-reviewer = LGTM (must_fix=False) → has_must_fix False 여야 함
        self.assertFalse(
            payload["has_must_fix"],
            msg="POLISH 후 LGTM 으로 해소된 must_fix 가 sticky 됨 (#272 W4 회귀)",
        )
        self.assertFalse(payload["has_ambiguous"])

    def test_finalize_run_must_fix_unresolved_still_sticky(self) -> None:
        """final pr-reviewer 가 여전히 CHANGES_REQUESTED 면 has_must_fix True."""
        from harness.session_state import (
            _cli_finalize_run,
            run_dir, _clear_default_base_cache, write_pid_session,
            write_pid_current_run, get_cc_pid_via_ppid_chain,
        )
        from io import StringIO
        from contextlib import redirect_stdout
        from types import SimpleNamespace

        repo = Path(self._tmp.name) / "repo-mustfix-unres"
        repo.mkdir()
        os.chdir(repo)
        _clear_default_base_cache()

        cc_pid = get_cc_pid_via_ppid_chain()
        if cc_pid is None:
            self.skipTest("cc_pid 추출 불가 — CI 환경 의존")
        sid = "smoke-mustfix2-sid"
        rid = "run-abcd5678"
        write_pid_session(cc_pid, sid)
        run_dir(sid, rid, create=True)
        write_pid_current_run(cc_pid, rid)

        self._append_step_status_with_prose(
            sid, rid, "code-validator", None, "PASS", "ok"
        )
        self._append_step_status_with_prose(
            sid, rid, "engineer", "IMPL", "IMPL_DONE", "ok"
        )
        self._append_step_status_with_prose(
            sid, rid, "pr-reviewer", None, "CHANGES_REQUESTED",
            "## MUST FIX\n- 미해소 항목\n",
        )

        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_finalize_run(SimpleNamespace())
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        # 후속 LGTM 이 없으니 latest pr-reviewer = CHANGES_REQUESTED → must_fix True
        self.assertTrue(payload["has_must_fix"])

    def test_latest_step_per_role(self) -> None:
        """_latest_step_per_role — 같은 (agent, mode) 의 마지막 발생만 반환 (#272 W4)."""
        from harness.session_state import _latest_step_per_role
        steps = [
            {"agent": "engineer", "mode": "IMPL", "must_fix": False},
            {"agent": "pr-reviewer", "mode": None, "must_fix": True, "enum": "CHANGES_REQUESTED"},
            {"agent": "engineer", "mode": "POLISH", "must_fix": False},
            {"agent": "pr-reviewer", "mode": None, "must_fix": False, "enum": "LGTM"},
        ]
        latest = _latest_step_per_role(steps)
        # engineer:IMPL, engineer:POLISH 는 다른 mode → 둘 다 살아남음.
        # pr-reviewer:None 은 마지막 (LGTM, must_fix=False) 만.
        self.assertEqual(len(latest), 3)
        pr = next(s for s in latest if s["agent"] == "pr-reviewer")
        self.assertEqual(pr["enum"], "LGTM")
        self.assertFalse(pr["must_fix"])

    def test_auto_resolve_ux_escalate(self) -> None:
        from harness.session_state import _cli_auto_resolve
        from io import StringIO
        from contextlib import redirect_stdout
        from types import SimpleNamespace
        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_auto_resolve(
                SimpleNamespace(agent_mode="ux-architect:UX_FLOW_ESCALATE")
            )
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["next_enum"], "UX_FLOW_PATCHED")
        self.assertIn("hint", payload)

    def test_auto_resolve_ambiguous_wildcard(self) -> None:
        from harness.session_state import _cli_auto_resolve
        from io import StringIO
        from contextlib import redirect_stdout
        from types import SimpleNamespace
        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_auto_resolve(
                SimpleNamespace(agent_mode="random-agent:AMBIGUOUS")
            )
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["action"], "user-delegate")

    def test_auto_resolve_unmapped_returns_exit_1(self) -> None:
        from harness.session_state import _cli_auto_resolve
        from io import StringIO
        from contextlib import redirect_stdout
        from types import SimpleNamespace
        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_auto_resolve(SimpleNamespace(agent_mode="unknown:MYSTERY"))
        self.assertEqual(rc, 1)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["action"], "unmapped")

    def test_auto_resolve_architecture_validator_fail_routes_by_classification(self) -> None:
        # issue #612 — validator FAIL 은 finding 분류 의존 분기.
        # read-only validator 재호출(re-invoke) / 직전 step 고정(re-invoke-prev) 둘 다
        # 오분기 — action 은 route-by-classification, 실제 target 은 hint 의 분류가 진본.
        from harness.session_state import _cli_auto_resolve
        from io import StringIO
        from contextlib import redirect_stdout
        from types import SimpleNamespace
        out = StringIO()
        with redirect_stdout(out):
            rc = _cli_auto_resolve(
                SimpleNamespace(agent_mode="architecture-validator:FAIL")
            )
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["action"], "route-by-classification")
        # mechanical 재호출 action 이 아니어야 함 (read-only validator 재실행 = 같은 FAIL)
        self.assertNotIn(payload["action"], ("re-invoke", "re-invoke-prev"))
        # hint 에 3 분류 토큰이 모두 있어야 메인이 분류로 분기 가능
        self.assertIn("SYSTEM_BOUNDARY", payload["hint"])
        self.assertIn("CONTRACT_PROPAGATION", payload["hint"])
        self.assertIn("TASK_LOCAL", payload["hint"])


# ---------------------------------------------------------------------------
# auto_detect_session_id / auto_detect_run_id 폴백 — issue #469 결함 B
# ---------------------------------------------------------------------------


class AutoDetectFallbackTests(unittest.TestCase):
    """issue #469 결함 B — helper sid/rid 폴백 (env var + active_runs scan).

    PPID chain mismatch (bash subprocess 재시작 / fork) 시 sid/rid 미해결
    회귀 차단. env > PPID > pointer > active_runs scan 폴백 우선순위.

    회귀 계보:
      - #469: impl-loop/helper 직접 호출의 PPID mismatch fallback
      - #483: sid/rid 미해결 진단 출력
      - #684: by-pid sid 는 있으나 current-run pointer 유실 + 전역 scan miss
      - #730: finalize-run 후 같은 run fix round begin-step 재진입 scan miss
    """

    SID_A = "11111111-2222-4333-8444-555555555555"
    SID_B = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    RID_A = "run-aaaaaaaa"
    RID_B = "run-bbbbbbbb"

    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.base = Path(self._td.name)
        # env var 영향 회피 — 각 테스트마다 clean
        os.environ.pop("DCNESS_SESSION_ID", None)
        os.environ.pop("DCNESS_RUN_ID", None)

    def tearDown(self) -> None:
        self._td.cleanup()
        os.environ.pop("DCNESS_SESSION_ID", None)
        os.environ.pop("DCNESS_RUN_ID", None)

    def _write_live(
        self,
        sid: str,
        *,
        runs: dict,
        root: str = "sessions",
    ) -> Path:
        """sessions/<sid>/live.json 작성 helper."""
        sess_dir = self.base / root / sid
        sess_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "_meta": {"sessionId": sid, "version": 1, "writtenAt": "2026-05-22T00:00:00+00:00"},
            "session_id": sid,
            "active_runs": runs,
        }
        live_file = sess_dir / "live.json"
        live_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return live_file

    def test_env_var_takes_priority_for_session_id(self) -> None:
        from harness.session_state import auto_detect_session_id
        # env var = SID_A, 다른 active_runs = SID_B (env 가 우선)
        os.environ["DCNESS_SESSION_ID"] = self.SID_A
        self._write_live(
            self.SID_B,
            runs={self.RID_B: {"run_id": self.RID_B, "started_at": "2026-05-22T01:00:00+00:00"}},
        )
        sid = auto_detect_session_id(base_dir=self.base)
        self.assertEqual(sid, self.SID_A)

    def test_env_var_takes_priority_for_run_id(self) -> None:
        from harness.session_state import auto_detect_run_id
        os.environ["DCNESS_RUN_ID"] = self.RID_A
        sid = auto_detect_run_id(base_dir=self.base)
        self.assertEqual(sid, self.RID_A)

    def test_invalid_env_sid_falls_through(self) -> None:
        from harness.session_state import auto_detect_session_id
        # path-traversal 문자 (valid_session_id regex fail) → 폴백 = active_runs scan
        os.environ["DCNESS_SESSION_ID"] = "../escape"
        self._write_live(
            self.SID_B,
            runs={self.RID_B: {"run_id": self.RID_B, "started_at": "2026-05-22T01:00:00+00:00"}},
        )
        sid = auto_detect_session_id(base_dir=self.base)
        # env 무시 + PPID chain (실 환경 X) + pointer 부재 → active_runs scan 박힘
        self.assertEqual(sid, self.SID_B)

    def test_scan_picks_recent_uncompleted_run(self) -> None:
        from harness.session_state import _scan_recent_active_run_slot
        # session A 의 run A = 미완료 (오래된), session B 의 run B = 미완료 (최신)
        self._write_live(
            self.SID_A,
            runs={self.RID_A: {"run_id": self.RID_A, "started_at": "2026-05-22T00:00:00+00:00"}},
        )
        self._write_live(
            self.SID_B,
            runs={self.RID_B: {"run_id": self.RID_B, "started_at": "2026-05-22T02:00:00+00:00"}},
        )
        result = _scan_recent_active_run_slot(base_dir=self.base)
        self.assertEqual(result, (self.SID_B, self.RID_B))

    def test_global_scan_includes_finalized_uncompleted_run(self) -> None:
        from harness.session_state import _scan_recent_active_run_slot

        self._write_live(
            self.SID_A,
            runs={self.RID_A: {
                "run_id": self.RID_A,
                "started_at": "2026-06-11T01:00:00+00:00",
                "completed_at": None,
                "finalized_at": "2026-06-11T01:30:00+00:00",
            }},
        )
        result = _scan_recent_active_run_slot(base_dir=self.base)
        self.assertEqual(result, (self.SID_A, self.RID_A))

    def test_session_scoped_scan_includes_finalized_uncompleted_run(self) -> None:
        """issue #730 — finalized_at 은 review snapshot 이지 run close 가 아니다."""
        from harness.session_state import _scan_recent_active_run_slot

        self._write_live(
            self.SID_A,
            root=".sessions",
            runs={self.RID_A: {
                "run_id": self.RID_A,
                "started_at": "2026-06-11T01:00:00+00:00",
                "completed_at": None,
                "finalized_at": "2026-06-11T01:30:00+00:00",
            }},
        )
        result = _scan_recent_active_run_slot(
            base_dir=self.base,
            session_id=self.SID_A,
        )
        self.assertEqual(result, (self.SID_A, self.RID_A))

    def test_scan_skips_completed_runs_without_finalized_at(self) -> None:
        """completed_at tombstone 만 있는 end-run 완료 슬롯도 fallback 후보에서 제외."""
        from harness.session_state import _scan_recent_active_run_slot

        self._write_live(
            self.SID_A,
            runs={self.RID_A: {
                "run_id": self.RID_A,
                "started_at": "2026-05-22T02:00:00+00:00",
                "completed_at": "2026-05-22T02:30:00+00:00",
            }},
        )
        self._write_live(
            self.SID_B,
            runs={self.RID_B: {
                "run_id": self.RID_B,
                "started_at": "2026-05-22T01:00:00+00:00",
                "completed_at": None,
            }},
        )
        result = _scan_recent_active_run_slot(base_dir=self.base)
        self.assertEqual(result, (self.SID_B, self.RID_B))

    def test_scan_no_sessions_returns_none(self) -> None:
        from harness.session_state import _scan_recent_active_run_slot
        # sessions/ 디렉토리 자체 부재
        result = _scan_recent_active_run_slot(base_dir=self.base)
        self.assertIsNone(result)

    def test_scan_all_completed_returns_none(self) -> None:
        from harness.session_state import _scan_recent_active_run_slot
        # 모든 run completed → None
        self._write_live(
            self.SID_A,
            runs={self.RID_A: {
                "run_id": self.RID_A,
                "started_at": "2026-05-22T00:00:00+00:00",
                "completed_at": "2026-05-22T00:31:00+00:00",
                "finalized_at": "2026-05-22T00:30:00+00:00",
            }},
        )
        result = _scan_recent_active_run_slot(base_dir=self.base)
        self.assertIsNone(result)

    def test_auto_detect_run_id_uses_scan_when_no_env_no_ppid(self) -> None:
        from harness.session_state import auto_detect_run_id
        # env 없음, PPID chain 실 환경 X (테스트 환경에서는 None 반환 또는 unrelated PID)
        # → active_runs scan 폴백 박힘
        self._write_live(
            self.SID_A,
            runs={self.RID_A: {"run_id": self.RID_A, "started_at": "2026-05-22T01:00:00+00:00"}},
        )
        rid = auto_detect_run_id(base_dir=self.base)
        self.assertEqual(rid, self.RID_A)

    def test_auto_detect_run_id_uses_pid_sid_scoped_scan_when_current_run_pointer_missing(self) -> None:
        """issue #684 — sid 는 by-pid 에 있으나 by-pid-current-run 만 유실된 장시간 run."""
        from harness.session_state import (
            auto_detect_run_id,
            diagnose_sid_rid_resolution,
            write_pid_session,
        )

        cc_pid = 12345
        write_pid_session(cc_pid, self.SID_A, base_dir=self.base)
        target_live = self._write_live(
            self.SID_A,
            root=".sessions",
            runs={self.RID_A: {
                "run_id": self.RID_A,
                "started_at": "2026-05-22T01:00:00+00:00",
                "completed_at": None,
                "current_step": {"agent": "module-architect", "mode": None},
            }},
        )
        os.utime(target_live, (1000, 1000))

        # 전역 scan 의 최신 후보가 다른 session 의 finalized-only noise 여도,
        # by-pid 로 sid 가 특정되면 target sid active_runs 를 직접 봐야 한다.
        for idx in range(6):
            sid = f"noise-sid-{idx}"
            rid = f"run-abc0000{idx}"
            live_file = self._write_live(
                sid,
                root=".sessions",
                runs={rid: {
                    "run_id": rid,
                    "started_at": "2026-05-22T02:00:00+00:00",
                    "completed_at": None,
                    "finalized_at": "2026-05-22T02:30:00+00:00",
                }},
            )
            os.utime(live_file, (2000 + idx, 2000 + idx))

        with patch("harness.session_state.get_cc_pid_via_ppid_chain", return_value=cc_pid):
            rid = auto_detect_run_id(base_dir=self.base)
            msg = diagnose_sid_rid_resolution(base_dir=self.base, mode="rid")
        self.assertEqual(rid, self.RID_A)
        self.assertIn("active_runs scan best-guess", msg)
        self.assertIn(self.SID_A, msg)
        self.assertIn(self.RID_A, msg)

    # ── issue #483 — diagnose_sid_rid_resolution 진단성 강화 ────────────

    def test_diagnose_all_layers_unresolved(self) -> None:
        """env / PPID / scan 전 layer 미해결 → 모든 layer 상태 + escape hatch 출력."""
        from harness.session_state import diagnose_sid_rid_resolution
        msg = diagnose_sid_rid_resolution(base_dir=self.base, mode="both")
        self.assertIn("env DCNESS_SESSION_ID: 미설정", msg)
        self.assertIn("env DCNESS_RUN_ID: 미설정", msg)
        self.assertIn("PPID chain", msg)
        self.assertIn("active_runs scan: 매치 없음", msg)
        # escape hatch 안내 의무
        self.assertIn("export DCNESS_SESSION_ID=", msg)
        self.assertIn("export DCNESS_RUN_ID=", msg)
        self.assertIn("dcness#483", msg)

    def test_diagnose_env_var_present(self) -> None:
        """env var 설정 시 진단 메시지에 '있음' 표시."""
        from harness.session_state import diagnose_sid_rid_resolution
        os.environ["DCNESS_SESSION_ID"] = self.SID_A
        os.environ["DCNESS_RUN_ID"] = self.RID_A
        msg = diagnose_sid_rid_resolution(base_dir=self.base, mode="both")
        self.assertIn("env DCNESS_SESSION_ID: 있음", msg)
        self.assertIn("env DCNESS_RUN_ID: 있음", msg)

    def test_diagnose_active_runs_scan_best_guess(self) -> None:
        """active_runs scan 매치 시 best-guess sid/rid 노출 — 사용자 우회 hint."""
        from harness.session_state import diagnose_sid_rid_resolution
        self._write_live(
            self.SID_A,
            runs={self.RID_A: {"run_id": self.RID_A, "started_at": "2026-05-22T01:00:00+00:00"}},
        )
        msg = diagnose_sid_rid_resolution(base_dir=self.base, mode="both")
        self.assertIn("active_runs scan best-guess", msg)
        self.assertIn(self.SID_A, msg)
        self.assertIn(self.RID_A, msg)

    def test_diagnose_mode_sid_only(self) -> None:
        """mode='sid' → sid 영역만 진단 (rid 영역 미출력)."""
        from harness.session_state import diagnose_sid_rid_resolution
        msg = diagnose_sid_rid_resolution(base_dir=self.base, mode="sid")
        self.assertIn("env DCNESS_SESSION_ID", msg)
        self.assertNotIn("env DCNESS_RUN_ID", msg)
        self.assertIn("export DCNESS_SESSION_ID=", msg)
        self.assertNotIn("export DCNESS_RUN_ID=", msg)


# ---------------------------------------------------------------------------
# _cli_next_task subcommand — issue #471
# ---------------------------------------------------------------------------


class NextTaskTransitionTests(unittest.TestCase):
    """issue #471 — `next-task` subcommand 단위 검증.

    `_cli_next_task` 의 분기 검증만 — review.md 본문 / end-run finalize 통합 흐름은
    jajang round-trip 측정 영역.
    """

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self._old_cwd = os.getcwd()
        os.chdir(self.base)
        from harness.session_state import _clear_default_base_cache
        _clear_default_base_cache()
        os.environ.pop("DCNESS_SESSION_ID", None)
        os.environ.pop("DCNESS_RUN_ID", None)

    def tearDown(self) -> None:
        os.chdir(self._old_cwd)
        from harness.session_state import _clear_default_base_cache
        _clear_default_base_cache()
        os.environ.pop("DCNESS_SESSION_ID", None)
        os.environ.pop("DCNESS_RUN_ID", None)
        self._tmp.cleanup()

    def test_sid_unresolved_returns_exit_1(self) -> None:
        from harness.session_state import _cli_next_task
        from types import SimpleNamespace
        rc = _cli_next_task(SimpleNamespace(entry_point="impl"))
        self.assertEqual(rc, 1)

    def test_transition_prints_previous_and_new(self) -> None:
        from harness.session_state import _cli_next_task, start_run
        from io import StringIO
        from contextlib import redirect_stdout
        from types import SimpleNamespace
        sid = "11111111-2222-4333-8444-555555555555"
        prev_rid = "run-prev1234"
        os.environ["DCNESS_SESSION_ID"] = sid
        os.environ["DCNESS_RUN_ID"] = prev_rid

        # 이전 run 사전 등록 — end-run 의 finalize-run --auto-review 가 review.md
        # 자동 생성 (사전 박은 본문은 덮어써짐. 정상 동작 — run_review 가 ground truth).
        start_run(sid, prev_rid, "impl", issue_num=None)

        buf = StringIO()
        with redirect_stdout(buf):
            rc = _cli_next_task(SimpleNamespace(entry_point="impl"))

        self.assertEqual(rc, 0)
        out = buf.getvalue()
        # transition header + previous run_id stdout
        self.assertIn("next-task transition", out)
        self.assertIn(prev_rid, out)
        # previous review.md 본문 stdout 노출 (run_review 자동 생성 본문)
        self.assertIn("[previous review.md (review.md)]", out)
        self.assertIn("Run Review", out)  # auto-review header
        # 새 rid 발급 + run_dir stdout
        self.assertIn("[new] run_id: run-", out)
        self.assertIn("[new] run_dir:", out)
        # 새 rid != 이전 rid (begin-run 정상 동작)
        self.assertNotIn(f"[new] run_id: {prev_rid}", out)

    def test_transition_records_design_doc(self) -> None:
        # chain task — 다음 task 의 머지된 설계 문서를 새 run 에 기록 (engineer
        # 게이트 사전 조건 증거 승계). 기록값 = resolve 절대경로.
        from harness.session_state import _cli_next_task, read_live
        from io import StringIO
        from contextlib import redirect_stdout
        from types import SimpleNamespace
        sid = "11111111-2222-4333-8444-555555555555"
        os.environ["DCNESS_SESSION_ID"] = sid

        doc = Path("docs/compact-plans/foo.md")
        doc.parent.mkdir(parents=True)
        doc.write_text("# compact plan\n", encoding="utf-8")
        resolved = str(doc.resolve())

        buf = StringIO()
        with redirect_stdout(buf):
            rc = _cli_next_task(SimpleNamespace(
                entry_point="impl", design_doc=str(doc),
            ))
        self.assertEqual(rc, 0)
        active = read_live(sid)["active_runs"]
        recorded = [s.get("design_doc") for s in active.values()]
        self.assertIn(resolved, recorded)
        self.assertIn(f"[new] design_doc: {resolved}", buf.getvalue())

    def test_transition_records_acceptance_required(self) -> None:
        # chain task — 다음 task 가 story/epic 마감이면 새 run 에 acceptance marker 를 기록.
        from harness.session_state import _cli_next_task, read_live
        from io import StringIO
        from contextlib import redirect_stdout
        from types import SimpleNamespace
        sid = "11111111-2222-4333-8444-555555555555"
        os.environ["DCNESS_SESSION_ID"] = sid

        buf = StringIO()
        with redirect_stdout(buf):
            rc = _cli_next_task(SimpleNamespace(
                entry_point="impl", acceptance_required=True,
            ))
        self.assertEqual(rc, 0)
        active = read_live(sid)["active_runs"]
        self.assertIn(True, [s.get("acceptance_required") for s in active.values()])
        self.assertIn("[new] acceptance_required: true", buf.getvalue())

    def test_transition_invalid_design_doc_fails_before_end_run(self) -> None:
        # 실존하지 않는 design_doc — begin-run FAIL fail-fast (exit 1). 검증은
        # 이전 run end-run *전* 이라 이전 run 이 닫히지 않고 보존돼야 한다
        # (오타 한 번에 prev review echo 영구 소실 방지).
        from harness.session_state import _cli_next_task, read_live, start_run
        from io import StringIO
        from contextlib import redirect_stdout, redirect_stderr
        from types import SimpleNamespace
        sid = "11111111-2222-4333-8444-555555555555"
        prev_rid = "run-prev1234"
        os.environ["DCNESS_SESSION_ID"] = sid
        os.environ["DCNESS_RUN_ID"] = prev_rid
        start_run(sid, prev_rid, "impl", issue_num=None)

        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = _cli_next_task(SimpleNamespace(
                entry_point="impl",
                design_doc="docs/compact-plans/nope.md",
            ))
        self.assertEqual(rc, 1)
        self.assertIn("begin-run FAIL", err.getvalue())
        prev_slot = read_live(sid)["active_runs"][prev_rid]
        self.assertIsNone(prev_slot["completed_at"])

    def test_transition_invalid_acceptance_marker_fails_before_end_run(self) -> None:
        # acceptance_required 는 impl run 전용 — 잘못된 entry_point 면 이전 run 닫기 전 실패.
        from harness.session_state import _cli_next_task, read_live, start_run
        from io import StringIO
        from contextlib import redirect_stdout, redirect_stderr
        from types import SimpleNamespace
        sid = "11111111-2222-4333-8444-555555555555"
        prev_rid = "run-prev1234"
        os.environ["DCNESS_SESSION_ID"] = sid
        os.environ["DCNESS_RUN_ID"] = prev_rid
        start_run(sid, prev_rid, "impl", issue_num=None)

        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = _cli_next_task(SimpleNamespace(
                entry_point="design",
                acceptance_required=True,
            ))
        self.assertEqual(rc, 1)
        self.assertIn("acceptance_required is only valid", err.getvalue())
        prev_slot = read_live(sid)["active_runs"][prev_rid]
        self.assertIsNone(prev_slot["completed_at"])


class DesignDocArgparseTests(unittest.TestCase):
    """begin-run / next-task 의 --design-doc 플래그 파싱 회귀."""

    def test_begin_run_accepts_design_doc(self) -> None:
        from harness.session_state import _build_arg_parser
        ns = _build_arg_parser().parse_args(
            ["begin-run", "impl", "--design-doc", "docs/compact-plans/x.md"]
        )
        self.assertEqual(ns.cmd, "begin-run")
        self.assertEqual(ns.design_doc, "docs/compact-plans/x.md")

    def test_begin_run_design_doc_defaults_none(self) -> None:
        from harness.session_state import _build_arg_parser
        ns = _build_arg_parser().parse_args(["begin-run", "impl"])
        self.assertIsNone(ns.design_doc)

    def test_begin_run_accepts_acceptance_required(self) -> None:
        from harness.session_state import _build_arg_parser
        ns = _build_arg_parser().parse_args(
            ["begin-run", "impl", "--acceptance-required"]
        )
        self.assertEqual(ns.cmd, "begin-run")
        self.assertTrue(ns.acceptance_required)

    def test_begin_run_acceptance_required_defaults_false(self) -> None:
        from harness.session_state import _build_arg_parser
        ns = _build_arg_parser().parse_args(["begin-run", "impl"])
        self.assertFalse(ns.acceptance_required)

    def test_next_task_accepts_design_doc(self) -> None:
        from harness.session_state import _build_arg_parser
        ns = _build_arg_parser().parse_args(
            ["next-task", "--design-doc",
             "docs/milestones/v01/epics/epic-01-x/impl/01-x.md"]
        )
        self.assertEqual(ns.cmd, "next-task")
        self.assertEqual(
            ns.design_doc,
            "docs/milestones/v01/epics/epic-01-x/impl/01-x.md",
        )

    def test_next_task_accepts_acceptance_required(self) -> None:
        from harness.session_state import _build_arg_parser
        ns = _build_arg_parser().parse_args(["next-task", "--acceptance-required"])
        self.assertEqual(ns.cmd, "next-task")
        self.assertTrue(ns.acceptance_required)

    # -- #714 — begin-run --lane 플래그 파싱 --

    def test_begin_run_accepts_lane(self) -> None:
        from harness.session_state import _build_arg_parser
        ns = _build_arg_parser().parse_args(
            ["begin-run", "impl", "--lane", "lite"]
        )
        self.assertEqual(ns.cmd, "begin-run")
        self.assertEqual(ns.lane, "lite")

    def test_begin_run_lane_defaults_none(self) -> None:
        from harness.session_state import _build_arg_parser
        ns = _build_arg_parser().parse_args(["begin-run", "impl"])
        self.assertIsNone(ns.lane)


# ---------------------------------------------------------------------------
# _cli_post_task_begin — issue #472
# ---------------------------------------------------------------------------


class PostTaskBeginMarkerTests(unittest.TestCase):
    """issue #472 — `post-task-begin` subcommand 단위 검증.

    /impl-loop 종료 후 메인 자율 작업 영역 진입 marker. live.json 의
    `post_task_markers` list 에 timestamp + reason 박힘. FIFO cap 20.
    """

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self._old_cwd = os.getcwd()
        os.chdir(self.base)
        from harness.session_state import _clear_default_base_cache
        _clear_default_base_cache()
        os.environ.pop("DCNESS_SESSION_ID", None)

    def tearDown(self) -> None:
        os.chdir(self._old_cwd)
        from harness.session_state import _clear_default_base_cache
        _clear_default_base_cache()
        os.environ.pop("DCNESS_SESSION_ID", None)
        self._tmp.cleanup()

    def test_sid_unresolved_silent_skip(self) -> None:
        from harness.session_state import _cli_post_task_begin
        from types import SimpleNamespace
        rc = _cli_post_task_begin(SimpleNamespace(reason=""))
        self.assertEqual(rc, 0)

    def test_marker_appended_to_live(self) -> None:
        from harness.session_state import _cli_post_task_begin, read_live
        from io import StringIO
        from contextlib import redirect_stdout
        from types import SimpleNamespace
        sid = "11111111-2222-4333-8444-555555555555"
        os.environ["DCNESS_SESSION_ID"] = sid

        buf = StringIO()
        with redirect_stdout(buf):
            rc = _cli_post_task_begin(SimpleNamespace(reason="이슈 등록"))

        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("post-task area begin", out)
        self.assertIn("이슈 등록", out)
        self.assertIn("marker count: 1", out)

        live = read_live(sid)
        self.assertIsNotNone(live)
        markers = live.get("post_task_markers")
        self.assertIsInstance(markers, list)
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["reason"], "이슈 등록")
        self.assertIn("at", markers[0])

    def test_multiple_markers_appended(self) -> None:
        from harness.session_state import _cli_post_task_begin, read_live
        from io import StringIO
        from contextlib import redirect_stdout
        from types import SimpleNamespace
        sid = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        os.environ["DCNESS_SESSION_ID"] = sid

        for reason in ("이슈 등록", "cleanup", "분석"):
            with redirect_stdout(StringIO()):
                _cli_post_task_begin(SimpleNamespace(reason=reason))

        live = read_live(sid)
        markers = live.get("post_task_markers")
        self.assertEqual(len(markers), 3)
        self.assertEqual([m["reason"] for m in markers], ["이슈 등록", "cleanup", "분석"])

    def test_marker_fifo_cap_20(self) -> None:
        from harness.session_state import _cli_post_task_begin, read_live
        from io import StringIO
        from contextlib import redirect_stdout
        from types import SimpleNamespace
        sid = "cccccccc-dddd-4eee-8fff-aaaaaaaaaaaa"
        os.environ["DCNESS_SESSION_ID"] = sid

        for i in range(25):
            with redirect_stdout(StringIO()):
                _cli_post_task_begin(SimpleNamespace(reason=f"reason-{i}"))

        live = read_live(sid)
        markers = live.get("post_task_markers")
        self.assertEqual(len(markers), 20)
        # 오래된 5개 (reason-0 ~ reason-4) trim, reason-5 ~ reason-24 남음
        self.assertEqual(markers[0]["reason"], "reason-5")
        self.assertEqual(markers[-1]["reason"], "reason-24")


class NextTaskLedgerTests(unittest.TestCase):
    """이슈 #587 (codex review) — next-task 가 chain 새 run 에 run_started 를 남겨야."""

    def setUp(self) -> None:
        self._cwd = os.getcwd()
        self._td = TemporaryDirectory()
        os.environ.pop("DCNESS_SESSION_ID", None)
        os.environ.pop("DCNESS_RUN_ID", None)

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        self._td.cleanup()
        os.environ.pop("DCNESS_SESSION_ID", None)
        os.environ.pop("DCNESS_RUN_ID", None)

    def test_next_task_appends_run_started(self) -> None:
        import contextlib
        import io
        import re as _re
        from types import SimpleNamespace

        from harness import ledger
        from harness.session_state import _cli_next_task, _clear_default_base_cache

        repo = Path(self._td.name) / "repo"
        repo.mkdir()
        os.chdir(repo)
        _clear_default_base_cache()
        sid = "11111111-2222-4333-8444-555555555555"
        os.environ["DCNESS_SESSION_ID"] = sid

        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = _cli_next_task(SimpleNamespace(entry_point="impl"))
        self.assertEqual(rc, 0)
        m = _re.search(r"\[new\] run_id: (run-[0-9a-f]+)", out.getvalue())
        self.assertIsNotNone(m, out.getvalue())
        new_rid = m.group(1)
        events = ledger.read_events(sid, new_rid)
        self.assertTrue(
            any(
                e.get("event") == "run_started" and e.get("entry_point") == "impl"
                for e in events
            ),
            f"next-task 새 run 에 run_started 누락: {events}",
        )

    def test_ledger_event_rejects_lifecycle(self) -> None:
        """ledger-event CLI 가 helper-owned lifecycle event 위조를 거부 (codex review)."""
        import contextlib
        import io
        from types import SimpleNamespace

        from harness.session_state import _cli_ledger_event, _clear_default_base_cache

        repo = Path(self._td.name) / "le-repo"
        repo.mkdir()
        os.chdir(repo)
        _clear_default_base_cache()
        os.environ["DCNESS_SESSION_ID"] = "11111111-2222-4333-8444-555555555555"
        os.environ["DCNESS_RUN_ID"] = "run-deadbeef"

        def _ns(event_type: str) -> SimpleNamespace:
            return SimpleNamespace(
                event_type=event_type, agent=None, mode=None,
                pr_number=None, url=None, issue_num=None, reason=None,
            )

        # lifecycle event 위조 거부
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = _cli_ledger_event(_ns("step_completed"))
        self.assertEqual(rc, 1)
        self.assertIn("lifecycle", err.getvalue().lower())

        # 수동 event 는 허용
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc2 = _cli_ledger_event(
                SimpleNamespace(event_type="pr_merged", agent=None, mode=None,
                                pr_number=588, url=None, issue_num=None, reason=None)
            )
        self.assertEqual(rc2, 0)
        self.assertIn("pr_merged", out.getvalue())


if __name__ == "__main__":
    unittest.main()

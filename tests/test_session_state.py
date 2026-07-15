from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from harness import session_state as state
from harness import session_state_activation as activation
from harness import session_state_fail_open as fail_open
from harness.session_state_cli import _build_arg_parser


SID = "state-contract-session"
RID = "run-1234abcd"


class SessionStateContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = self.root / "state"

    def start(self, rid: str = RID, **fields: object) -> None:
        state.transition(
            SID,
            "run_started",
            run_id=rid,
            base_dir=self.base,
            entry_point=str(fields.pop("entry_point", "impl")),
            **fields,
        )

    def test_identity_and_paths_reject_traversal(self) -> None:
        for valid in ("a", "session-1", "ABC_123"):
            with self.subTest(valid=valid):
                self.assertTrue(state.valid_session_id(valid))
        for invalid in ("", "../x", "/tmp/x", "has space", None):
            with self.subTest(invalid=invalid):
                self.assertFalse(state.valid_session_id(invalid))
        self.assertRegex(state.generate_run_id(), r"^run-[a-f0-9]{8}$")
        self.assertEqual(
            state.run_dir(SID, RID, base_dir=self.base),
            (self.base / ".sessions" / SID / "runs" / RID).resolve(),
        )
        with self.assertRaises(ValueError):
            state.run_dir(SID, "../escape", base_dir=self.base)

    def test_atomic_write_round_trip_and_permissions(self) -> None:
        target = self.root / "nested" / "state.bin"
        state.atomic_write(target, b"one")
        state.atomic_write(target, b"two")
        self.assertEqual(target.read_bytes(), b"two")
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(target.parent.glob("*.tmp.*")), [])

    def test_start_contract_validates_lane_stage_and_design_doc(self) -> None:
        cases = (
            ({"entry_point": "impl", "lane": "unknown"}, "lane"),
            ({"entry_point": "design", "lane": "lite"}, "lane"),
            ({"entry_point": "impl", "stage": "design-ux"}, "stage"),
            ({"entry_point": "design", "acceptance_required": True}, "acceptance"),
        )
        for index, (fields, message) in enumerate(cases):
            with self.subTest(fields=fields):
                with self.assertRaisesRegex(ValueError, message):
                    self.start(f"run-a000000{index}", **fields)

        docs = self.root / "docs" / "epics" / "01" / "impl"
        docs.mkdir(parents=True)
        design = docs / "01-plan.md"
        design.write_text("plan", encoding="utf-8")
        with mock.patch("pathlib.Path.cwd", return_value=self.root):
            self.start(design_doc=str(design), lane="standard")
        slot = state.read_live(SID, base_dir=self.base)["active_runs"][RID]
        self.assertEqual(slot["design_doc"], str(design.resolve()))

    def test_pid_registry_and_environment_resolution(self) -> None:
        state.write_pid_session(123, SID, base_dir=self.base)
        state.write_pid_current_run(123, RID, base_dir=self.base)
        self.assertEqual(state.read_pid_session(123, base_dir=self.base), SID)
        self.assertEqual(state.read_pid_current_run(123, base_dir=self.base), RID)
        with mock.patch.dict(
            os.environ,
            {"DCNESS_SESSION_ID": SID, "DCNESS_RUN_ID": RID},
            clear=True,
        ):
            self.assertEqual(state.auto_detect_session_id(base_dir=self.base), SID)
            self.assertEqual(state.auto_detect_run_id(base_dir=self.base), RID)
        self.assertTrue(state.clear_pid_current_run(123, base_dir=self.base))
        self.assertFalse(state.clear_pid_current_run(123, base_dir=self.base))

    def test_active_run_scan_uses_latest_open_slot(self) -> None:
        self.start("run-aaaaaaaa", lane="lite")
        with mock.patch.object(
            state, "_now_iso", return_value="2099-01-01T00:00:00+00:00"
        ):
            state.transition(
                SID,
                "run_started",
                run_id="run-bbbbbbbb",
                base_dir=self.base,
                entry_point="impl",
                lane="lite",
            )
        with mock.patch.object(state, "get_cc_pid_via_ppid_chain", return_value=None), mock.patch.dict(
            os.environ, {}, clear=True
        ):
            self.assertEqual(state.auto_detect_run_id(base_dir=self.base), "run-bbbbbbbb")
        state.transition(SID, "run_completed", run_id="run-bbbbbbbb", base_dir=self.base)
        with mock.patch.object(state, "get_cc_pid_via_ppid_chain", return_value=None), mock.patch.dict(
            os.environ, {}, clear=True
        ):
            self.assertEqual(state.auto_detect_run_id(base_dir=self.base), "run-aaaaaaaa")

    def test_order_gate_preserves_lite_design_and_blocked_meaning(self) -> None:
        self.start(lane="standard")
        message = state.evaluate_order_gate_for_step(
            SID, RID, "build-worker", base_dir=self.base
        )
        self.assertIn("implementation gate", message or "")
        run_path = state.run_dir(SID, RID, base_dir=self.base)
        (run_path / "module-architect.md").write_text("PASS", encoding="utf-8")
        self.assertIsNone(
            state.evaluate_order_gate_for_step(
                SID, RID, "build-worker", base_dir=self.base
            )
        )
        state.transition(
            SID,
            "run_blocked",
            run_id=RID,
            base_dir=self.base,
            category="worker_boundary",
            reason="scope escaped",
        )
        blocked = state.evaluate_order_gate_for_step(
            SID, RID, "build-worker", base_dir=self.base
        )
        self.assertIn("boundary BLOCK", blocked or "")

    def test_prose_lookup_accepts_current_occurrence_and_mode_names(self) -> None:
        self.start(lane="lite")
        run_path = state.run_dir(SID, RID, base_dir=self.base)
        for name in (
            "module-architect-1.md",
            "module-architect-CODE_VALIDATION.md",
            "module-architect-epic-batch-2.md",
        ):
            with self.subTest(name=name):
                for existing in run_path.glob("module-architect*.md"):
                    existing.unlink()
                (run_path / name).write_text("PASS", encoding="utf-8")
                self.assertTrue(state.run_prose_has_pass(run_path, "module-architect"))

    def test_receipt_summary_and_must_fix_detection_are_prose_based(self) -> None:
        prose = "서론\n\n## 결론\n변경 완료\n검증 PASS\n"
        self.assertEqual(state._extract_prose_summary(prose), "변경 완료\n검증 PASS")
        cases = {
            "MUST FIX: 경로 검증 필요": True,
            "MUST FIX 없음": False,
            "## MUST FIX\n없음": False,
            "all good": False,
        }
        for prose, expected in cases.items():
            with self.subTest(prose=prose):
                self.assertEqual(state._has_positive_must_fix(prose), expected)

    def test_activation_is_idempotent_and_project_scoped(self) -> None:
        whitelist = self.root / "projects.json"
        project = self.root / "project"
        project.mkdir()
        with mock.patch.object(activation, "_DEFAULT_WHITELIST_PATH", whitelist):
            self.assertFalse(activation.is_project_active(project))
            self.assertEqual(activation.enable_project(project), project.resolve())
            self.assertTrue(activation.is_project_active(project))
            self.assertEqual(activation.list_active_projects(), [str(project.resolve())])
            self.assertEqual(activation.disable_project(project), project.resolve())
            self.assertFalse(activation.is_project_active(project))

    def test_fail_open_events_round_trip_without_becoming_state(self) -> None:
        fail_open.record_fail_open_event(
            hook="file-guard",
            category="handler_nonzero",
            detail="allowed after failure",
            cwd=self.root,
            base_dir=self.base,
        )
        events = fail_open.read_fail_open_events(cwd=self.root, base_dir=self.base)
        self.assertEqual(events[-1]["hook"], "file-guard")
        self.assertEqual(fail_open.collect_fail_open_summary(cwd=self.root, base_dir=self.base)["total"], 1)
        self.assertEqual(state.read_live(SID, base_dir=self.base), {})

    def test_cli_parser_preserves_public_state_and_hook_commands(self) -> None:
        parser = _build_arg_parser()
        commands = (
            ["begin-run", "impl", "--lane", "lite"],
            ["begin-step", "build-worker"],
            ["end-step", "build-worker", "--prose-file", "result.md"],
            ["finalize-run"],
            ["run-status"],
            ["ledger-event", "blocked", "--reason", "why"],
            ["hook-fail-open", "--hook", "file-guard", "--category", "x"],
        )
        for argv in commands:
            with self.subTest(argv=argv):
                self.assertTrue(callable(parser.parse_args(argv).func))


if __name__ == "__main__":
    unittest.main()

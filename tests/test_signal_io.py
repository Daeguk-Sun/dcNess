"""test_signal_io — prose-only pattern foundation 검증.

Coverage matrix:
    write_prose       : happy / atomic / unicode / mode 분기 / type error
    read_prose        : happy / not_found / empty
    signal_path       : path traversal / agent/mode 화이트리스트
    clear_run_state   : 다중 파일 제거 / run_id 화이트리스트 / 미존재 디렉토리
    MissingSignal     : reason enum 강제

대 원칙 정합:
    - 형식 강제 0: schema/required 키 검증 안 함 (prose 자유)
    - 작업 순서 / 접근 영역만: path 화이트리스트 + traversal 차단 (catastrophic-prevention)
"""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from harness.signal_io import (
    MissingSignal,
    clear_run_state,
    read_prose,
    signal_path,
    write_prose,
)


class WriteReadProseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.base = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_write_then_read_round_trip(self) -> None:
        prose = "## 검증 결과\n\n전체 통과.\n\n## 결론\n\nPASS\n"
        path = write_prose(
            "code-validator", "run_001", prose, mode=None, base_dir=self.base
        )
        self.assertTrue(path.exists())
        self.assertEqual(path.suffix, ".md")
        self.assertIn("code-validator.md", path.name)

        result = read_prose(
            "code-validator", "run_001", mode=None, base_dir=self.base
        )
        self.assertEqual(result, prose)

    def test_write_creates_parent_dir(self) -> None:
        write_prose(
            "architect", "deep-run", "stub", mode=None, base_dir=self.base
        )
        self.assertTrue((self.base / "deep-run" / "architect.md").exists())

    def test_write_unicode(self) -> None:
        prose = "한글 결론\n\nPASS\n"
        write_prose(
            "architecture-validator", "r", prose, mode=None, base_dir=self.base
        )
        out = read_prose(
            "architecture-validator", "r", mode=None, base_dir=self.base
        )
        self.assertEqual(out, prose)

    def test_write_rejects_non_string(self) -> None:
        with self.assertRaises(TypeError):
            write_prose("code-validator", "r", 123, base_dir=self.base)  # type: ignore[arg-type]

    def test_read_not_found(self) -> None:
        with self.assertRaises(MissingSignal) as cm:
            read_prose("validator", "missing", base_dir=self.base)
        self.assertEqual(cm.exception.reason, "not_found")

    def test_read_empty_file(self) -> None:
        path = write_prose(
            "validator", "r", "    \n\t\n", base_dir=self.base
        )
        with self.assertRaises(MissingSignal) as cm:
            read_prose("validator", "r", base_dir=self.base)
        self.assertEqual(cm.exception.reason, "empty")
        self.assertIn(str(path), cm.exception.detail)

    def test_atomic_write_no_tmp_residue(self) -> None:
        write_prose("validator", "r", "x", base_dir=self.base)
        # tmp 잔여물 없어야 함
        residue = list((self.base / "r").glob("*.tmp"))
        self.assertEqual(residue, [])

    def test_overwrite(self) -> None:
        write_prose("validator", "r", "first", base_dir=self.base)
        write_prose("validator", "r", "second", base_dir=self.base)
        out = read_prose("validator", "r", base_dir=self.base)
        self.assertEqual(out, "second")


class SignalPathValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.base = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_invalid_agent_name(self) -> None:
        for bad in ["Validator", "vali_dator", "../etc", "", "1abc"]:
            with self.assertRaises(ValueError, msg=f"agent={bad!r}"):
                signal_path(bad, "run", base_dir=self.base)

    def test_invalid_mode_name(self) -> None:
        for bad in ["plan", "Plan", "PLAN-A", "1MODE"]:
            with self.assertRaises(ValueError, msg=f"mode={bad!r}"):
                signal_path("validator", "run", mode=bad, base_dir=self.base)

    def test_invalid_run_id_traversal(self) -> None:
        with self.assertRaises(ValueError):
            signal_path("validator", "../escape", base_dir=self.base)

    def test_invalid_run_id_slash(self) -> None:
        with self.assertRaises(ValueError):
            signal_path("validator", "a/b", base_dir=self.base)

    def test_path_format(self) -> None:
        path = signal_path("validator", "r1", mode="CODE_VALIDATION", base_dir=self.base)
        self.assertEqual(path.name, "validator-CODE_VALIDATION.md")

    def test_no_mode_path(self) -> None:
        path = signal_path("architect", "r1", base_dir=self.base)
        self.assertEqual(path.name, "architect.md")


class ClearRunStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.base = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_clear_removes_md_files(self) -> None:
        write_prose("validator", "r", "x", base_dir=self.base)
        write_prose("architect", "r", "y", base_dir=self.base)
        count = clear_run_state("r", base_dir=self.base)
        self.assertEqual(count, 2)

    def test_clear_missing_dir_returns_zero(self) -> None:
        self.assertEqual(clear_run_state("absent-run", base_dir=self.base), 0)

    def test_clear_rejects_traversal(self) -> None:
        with self.assertRaises(ValueError):
            clear_run_state("../escape", base_dir=self.base)


class MissingSignalEnumTests(unittest.TestCase):
    def test_known_reasons_accepted(self) -> None:
        for reason in ("not_found", "empty"):
            err = MissingSignal(reason, "x")
            self.assertEqual(err.reason, reason)

    def test_unknown_reason_rejected(self) -> None:
        # "ambiguous" 는 옛 interpret_signal 전용 reason — enum 추출 폐기와 함께 제거.
        for reason in ("schema_violation", "ambiguous"):
            with self.assertRaises(ValueError):
                MissingSignal(reason, "x")


if __name__ == "__main__":
    unittest.main()

"""docs/index.md next-work pointer backfill helper tests."""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ensure_docs_index_next_section.mjs"
SECTION_TITLE = "## 진행 상태 · 다음 작업"


class DocsIndexNextSectionTests(unittest.TestCase):
    def run_helper(self, root: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["node", str(SCRIPT), str(root)],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_missing_index_is_noop(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            result = self.run_helper(root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("docs/index.md 없음", result.stdout)
            self.assertFalse((root / "docs" / "index.md").exists())

    def test_existing_index_gets_section_appended_without_overwrite(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            docs = root / "docs"
            docs.mkdir()
            index = docs / "index.md"
            index.write_text("# 기존 인덱스\n\n- 유지할 내용\n", encoding="utf-8")

            result = self.run_helper(root)

            self.assertEqual(result.returncode, 0, result.stderr)
            text = index.read_text(encoding="utf-8")
            self.assertIn("# 기존 인덱스\n\n- 유지할 내용", text)
            self.assertIn(SECTION_TITLE, text)
            self.assertIn("- 콜드스타트 다음 작업 확인: `/next`", text)
            self.assertIn("진행 상태 섹션 추가", result.stdout)

    def test_existing_section_is_not_duplicated(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            docs = root / "docs"
            docs.mkdir()
            index = docs / "index.md"
            index.write_text(
                "# 프로젝트 문서 인덱스\n\n"
                f"{SECTION_TITLE}\n\n"
                "- 콜드스타트 다음 작업 확인: `/next`\n",
                encoding="utf-8",
            )

            result = self.run_helper(root)

            self.assertEqual(result.returncode, 0, result.stderr)
            text = index.read_text(encoding="utf-8")
            self.assertEqual(text.count(SECTION_TITLE), 1)
            self.assertIn("이미 존재 - skip", result.stdout)


if __name__ == "__main__":
    unittest.main()

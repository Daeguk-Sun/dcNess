"""Story AC -> task REQ contract regression tests (#1047)."""
from __future__ import annotations

import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTER = ROOT / "scripts" / "report_ac_coverage.mjs"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def _run_report(stories: str, impl_files: dict[str, str]) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        stories_path = root / "docs/epics/epic-01-demo/stories.md"
        impl_dir = stories_path.parent / "impl"
        _write(stories_path, stories)
        for name, content in impl_files.items():
            _write(impl_dir / name, content)
        return subprocess.run(
            [
                "node",
                str(REPORTER),
                "--stories",
                str(stories_path),
                "--impl-dir",
                str(impl_dir),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )


STORIES = """
---
epic: epic-01-demo
milestone: v01
---

# Story Backlog

## Epic — Demo

### Story 1 — Create a report

**As a** user,
**I want** a report,
**So that** I can inspect results.

**Acceptance criteria:**
- AC-001 [command]: Given valid input, When generation runs, Then a report file exists.
- AC-002 [agent-read]: Given the report, When its metadata is read, Then the source is recorded.
"""


FINAL_TASK = """
---
story: 1
task_index: 2/2
depends_on: [01-build]
---

# 02-verify

## 수용 기준

| REQ | 유형 | 내용 | 출처 | 검증 명령 | 통과 조건 |
|---|---|---|---|---|---|
| REQ-003 | Story AC | report 생성 검증 | `(from AC-001)` | `(TEST) test -f report.md` | exit 0 |
| REQ-004 | Story AC | source 기록 관찰 | `(from AC-002)` | `(AGENT READ) rg source report.md` | source 존재 |
| REQ-TECH-001 | 기술 REQ | schema shape 검증 | `(technical: public schema 계약)` | `(TEST) npm test` | exit 0 |
"""


class AcceptanceHierarchySurfaceTests(unittest.TestCase):
    def test_prd_stops_before_acceptance_criteria(self) -> None:
        template = (ROOT / "skills/spec/templates/prd.md").read_text(encoding="utf-8")
        reference = (ROOT / "skills/spec/spec-prd-reference.md").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("AC-001", template)
        self.assertNotIn("- 수용 기준:", template)
        self.assertIn("기능 나열", reference)
        self.assertIn("유저 시나리오", reference)
        self.assertIn("PRD 에 Story 수용 기준을 두지 않는다", reference)

    def test_story_owns_stable_acceptance_criteria(self) -> None:
        stories = (ROOT / "skills/spec/spec-stories-reference.md").read_text(
            encoding="utf-8"
        )
        git_spec = (ROOT / "docs/plugin/git-spec.md").read_text(encoding="utf-8")

        for needle in (
            "Story AC",
            "AC-001",
            "Given <상황>, When <행동>, Then <검증 가능한 결과>",
            "프로젝트 전역 순번",
            "한번 부여하면 불변",
            "사람 확인 안내",
        ):
            self.assertIn(needle, stories)

        self.assertIn("Story AC", git_spec)
        self.assertIn("AC-NNN", git_spec)

    def test_req_template_distinguishes_story_and_technical_requirements(self) -> None:
        template = (
            ROOT
            / "docs/plugin/agents/module-architect/templates/impl-task.md"
        ).read_text(encoding="utf-8")

        for needle in (
            "| REQ | 유형 | 내용 | 출처 | 검증 명령 | 통과 조건 |",
            "(from AC-001)",
            "REQ-TECH-001",
            "(technical:",
            "Story 마지막 task",
            "Story AC 전항목",
        ):
            self.assertIn(needle, template)

        impl_loop = (ROOT / "skills/impl-loop/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Story 마지막 task", impl_loop)
        self.assertIn("Story AC 전항목", impl_loop)
        self.assertIn("SPEC_GAP_FOUND", impl_loop)

    def test_validators_and_acceptance_use_story_ac_as_origin(self) -> None:
        paths = (
            ROOT / "docs/plugin/agents/architecture-validator/architecture-validator-agent.md",
            ROOT / "codex/skills/dcness-architecture-validator/SKILL.md",
            ROOT / "docs/plugin/agents/product-acceptance/product-acceptance-agent.md",
        )
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Story AC", text, path)

        for path in paths[:2]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("미커버 AC", text, path)
            self.assertIn("무출처 REQ", text, path)
            self.assertIn("report_ac_coverage.mjs", text, path)

    def test_terms_define_acceptance_hierarchy(self) -> None:
        terms = (ROOT / "docs/plugin/terms.md").read_text(encoding="utf-8")
        for needle in (
            "수용 기준 계층",
            "PRD 유저 시나리오",
            "Epic 완료 기준",
            "Story AC",
            "task REQ",
        ):
            self.assertIn(needle, terms)


class AcceptanceCoverageReporterTests(unittest.TestCase):
    def test_complete_mapping_reports_full_coverage_and_final_task(self) -> None:
        result = _run_report(STORIES, {"02-verify.md": FINAL_TASK})

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("| AC | Has REQ? | REQ IDs |", result.stdout)
        self.assertIn("AC-001", result.stdout)
        self.assertIn("AC-002", result.stdout)
        self.assertIn("Coverage: 2/2 (100.0%)", result.stdout)
        self.assertIn("Final task coverage: 2/2 (100.0%)", result.stdout)
        self.assertIn("Source-less REQ: none", result.stdout)
        self.assertIn("Unknown AC references: none", result.stdout)
        self.assertIn("Technical REQ: REQ-TECH-001", result.stdout)

    def test_gaps_are_reported_without_turning_advisory_into_a_blocking_gate(self) -> None:
        incomplete = FINAL_TASK.replace(
            "| REQ-004 | Story AC | source 기록 관찰 | `(from AC-002)` | "
            "`(AGENT READ) rg source report.md` | source 존재 |\n",
            "| REQ-004 | Story AC | 출처 누락 | - | `(TEST) npm test` | exit 0 |\n"
            "| REQ-005 | Story AC | 잘못된 출처 | `(from AC-999)` | `(TEST) npm test` | exit 0 |\n",
        )

        result = _run_report(STORIES, {"02-verify.md": incomplete})

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Coverage: 1/2 (50.0%)", result.stdout)
        self.assertIn("Uncovered AC: AC-002", result.stdout)
        self.assertIn("Source-less REQ: REQ-004", result.stdout)
        self.assertIn("Unknown AC references: AC-999", result.stdout)
        self.assertIn("Final task missing AC: AC-002", result.stdout)
        self.assertIn("advisory report", result.stdout)

    def test_legacy_stories_without_story_ac_are_accepted_without_rewrite(self) -> None:
        legacy = """
        # Story Backlog

        ### Story 1 — Legacy
        **As a** user,
        **I want** the old format,
        **So that** existing projects keep working.
        """

        result = _run_report(legacy, {})

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Legacy stories format", result.stdout)
        self.assertIn("no retroactive conversion", result.stdout)

    def test_duplicate_ac_declaration_inside_one_story_is_reported(self) -> None:
        duplicate = STORIES.replace(
            "- AC-002 [agent-read]: Given the report, When its metadata is read, Then the source is recorded.",
            "- AC-001 [agent-read]: Given the report, When its metadata is read, Then the source is recorded.",
        )

        result = _run_report(duplicate, {"02-verify.md": FINAL_TASK})

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Duplicate AC IDs: AC-001", result.stdout)

    def test_req_mentions_outside_the_id_column_are_not_parsed_as_rows(self) -> None:
        mentioning_other_req = FINAL_TASK.replace(
            "report 생성 검증",
            "report 생성 검증 (REQ-999 참고)",
        )

        result = _run_report(STORIES, {"02-verify.md": mentioning_other_req})

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("REQ-999", result.stdout)


if __name__ == "__main__":
    unittest.main()

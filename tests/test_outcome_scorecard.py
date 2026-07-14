"""Cross-project outcome scorecard contract and aggregation tests."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from harness import ledger
from harness.outcome_scorecard import (
    SourceDataUnavailable,
    build_scorecard,
    main,
    render_markdown,
)


ROOT = Path(__file__).resolve().parents[1]


def _write_run(
    project: Path,
    run_id: str,
    *,
    verdict: str,
    finished: bool = True,
    pr_number: int | None = None,
    date: str = "2026-07-01",
    blocked: bool = False,
    future_pr_number: int | None = None,
    future_verdict: str | None = None,
) -> None:
    run_dir = (
        project
        / ".claude"
        / "harness-state"
        / ".sessions"
        / "session-1"
        / "runs"
        / run_id
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    prose = f"독립 검토 결과\n{verdict}\n"
    prose_path = run_dir / "impl-validator.md"
    prose_path.write_text(prose, encoding="utf-8")
    events = [
        {
            "event": "run_started",
            "entry_point": "impl",
            "ts": f"{date}T00:00:00Z",
        },
        {
            "event": "step_completed",
            "agent": "impl-validator",
            "enum": "PROSE_LOGGED",
            "prose_file": str(prose_path),
            "sha256": ledger.sha256_text(prose),
            "ts": f"{date}T00:01:00Z",
        },
    ]
    if pr_number is not None:
        url = f"https://example.invalid/repo/pull/{pr_number}"
        events.extend(
            [
                {
                    "event": "pr_created",
                    "pr_number": pr_number,
                    "url": url,
                    "ts": f"{date}T00:02:00Z",
                },
                {
                    "event": "pr_merged",
                    "pr_number": pr_number,
                    "url": url,
                    "ts": f"{date}T00:03:00Z",
                },
            ]
        )
    if blocked:
        events.append(
            {"event": "blocked", "reason": "fixture", "ts": f"{date}T00:03:30Z"}
        )
    if finished:
        events.append({"event": "run_finished", "ts": f"{date}T00:04:00Z"})
    if future_pr_number is not None:
        future_url = f"https://example.invalid/repo/pull/{future_pr_number}"
        events.extend(
            [
                {
                    "event": "pr_created",
                    "pr_number": future_pr_number,
                    "url": future_url,
                    "ts": "2026-07-12T00:02:00Z",
                },
                {
                    "event": "pr_merged",
                    "pr_number": future_pr_number,
                    "url": future_url,
                    "ts": "2026-07-12T00:03:00Z",
                },
            ]
        )
    if future_verdict is not None:
        future_prose = f"cutoff 이후 독립 검토\n{future_verdict}\n"
        future_prose_path = run_dir / "impl-validator-future.md"
        future_prose_path.write_text(future_prose, encoding="utf-8")
        events.append(
            {
                "event": "step_completed",
                "agent": "impl-validator",
                "enum": "PROSE_LOGGED",
                "prose_file": str(future_prose_path),
                "sha256": ledger.sha256_text(future_prose),
                "ts": "2026-07-12T00:05:00Z",
            }
        )
    with (run_dir / "ledger.jsonl").open("w", encoding="utf-8") as stream:
        for event in events:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")


def _write_product_journey_receipt(
    project: Path,
    run_id: str,
    *,
    outcome: str,
    measured_at: str = "2026-07-10T00:00:00Z",
) -> None:
    receipt_dir = project / ".dcness-work" / "product-journey" / run_id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    passed = 1 if outcome == "PASS" else 0
    evidence_paths = {
        "receipt": f".dcness-work/product-journey/{run_id}/receipt.json"
    }
    evidence_sha256: dict[str, str] = {}
    commands: dict[str, dict[str, object]] = {}
    for phase in ("start", "health", "journey", "cleanup"):
        content = f"{phase} fixture log\n"
        log_path = receipt_dir / f"{phase}.log"
        log_path.write_text(content, encoding="utf-8")
        relative = f".dcness-work/product-journey/{run_id}/{phase}.log"
        evidence_paths[phase] = relative
        evidence_sha256[phase] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        commands[phase] = {
            "argv": ["fixture", phase],
            "exit_code": 0,
            "timed_out": False,
            "duration_ms": 1,
            "log_path": relative,
        }
    (receipt_dir / "receipt.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "receipt_type": "dcness.product-journey",
                "run_id": run_id,
                "journey_id": "fixture-non-ui",
                "measured_at": measured_at,
                "outcome": outcome,
                "boundary": "cli",
                "target_ac": ["AC-FIXTURE-1"],
                "product_ac": {"passed": passed, "total": 1},
                "human_intervention_count": 0,
                "evidence_types": ["command", "cli", "log"],
                "evidence_paths": evidence_paths,
                "evidence_sha256": evidence_sha256,
                "commands": commands,
                "app_started": True,
                "journey_executed": True,
                "assertion": {
                    "description": "fixture assertion",
                    "source": "journey_exit",
                    "evaluated": True,
                    "passed": outcome == "PASS",
                },
                "failure_reasons": [] if outcome == "PASS" else ["journey_failed"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class OutcomeScorecardAggregationTests(unittest.TestCase):
    def _fixture(self, root: Path) -> Path:
        project_a = root / "private-project-a"
        project_b = root / "private-project-b"
        empty = root / "empty-project"
        for project in (project_a, project_b, empty):
            project.mkdir()
        _write_run(
            project_a,
            "run-a0000001",
            verdict="FAIL",
            blocked=True,
            future_pr_number=9,
            future_verdict="PASS",
        )
        _write_run(project_a, "run-a0000002", verdict="PASS", finished=False)
        _write_run(project_b, "run-b0000001", verdict="PASS", pr_number=7)
        _write_run(
            project_b,
            "run-future01",
            verdict="FAIL",
            pr_number=8,
            date="2026-07-12",
        )
        projects_file = root / "projects.json"
        projects_file.write_text(
            json.dumps(
                {"version": 1, "projects": [str(project_a), str(project_b), str(empty)]}
            ),
            encoding="utf-8",
        )
        return projects_file

    def test_cross_project_report_preserves_denominators_and_unmeasured_axes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            projects_file = self._fixture(Path(directory))
            report = build_scorecard(
                projects_file,
                measured_at="2026-07-11T00:00:00Z",
                as_of="2026-07-11T00:00:00Z",
                redact_paths=True,
            )

        self.assertEqual(report["source_project_count"], 2)
        self.assertEqual(report["configured_project_count"], 3)
        process = report["process_evidence"]
        self.assertEqual(process["finished_runs"]["numerator"], 2)
        self.assertEqual(process["finished_runs"]["denominator"], 3)
        self.assertEqual(process["pr_merge_success"]["numerator"], 1)
        self.assertEqual(process["pr_merge_success"]["denominator"], 1)
        self.assertEqual(process["impl_validator_rework"]["numerator"], 1)
        self.assertEqual(process["impl_validator_rework"]["denominator"], 2)
        self.assertEqual(process["blocked_events"]["numerator"], 1)
        self.assertEqual(process["blocked_events"]["denominator"], 2)
        self.assertEqual(process["guard_results"]["status"], "측정 불가")
        self.assertEqual(process["regressions"]["status"], "측정 불가")
        for metric in process.values():
            self.assertEqual(metric["source_project_count"], 2)
            self.assertEqual(metric["measured_at"], "2026-07-11T00:00:00Z")

        self.assertEqual(report["agent_effectiveness"]["status"], "측정 불가")
        self.assertEqual(report["product_outcome"]["status"], "측정 불가")
        self.assertEqual(report["trial_metadata"]["status"], "측정 불가")
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("private-project-a", serialized)
        self.assertNotIn("private-project-b", serialized)

    def test_product_journey_receipts_fill_outcome_without_process_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            projects_file = self._fixture(root)
            project_a = root / "private-project-a"
            _write_product_journey_receipt(project_a, "journey-pass", outcome="PASS")
            _write_product_journey_receipt(project_a, "journey-fail", outcome="FAIL")

            report = build_scorecard(
                projects_file,
                measured_at="2026-07-11T00:00:00Z",
                as_of="2026-07-11T00:00:00Z",
                redact_paths=True,
            )

        outcome = report["product_outcome"]
        self.assertEqual(outcome["status"], "관측")
        self.assertEqual(outcome["numerator"], 1)
        self.assertEqual(outcome["denominator"], 2)
        self.assertEqual(outcome["product_ac"], {"passed": 1, "total": 2})
        self.assertEqual(outcome["source_project_count"], 1)
        self.assertEqual(outcome["human_intervention_count"], 0)
        self.assertEqual(outcome["evidence_types"], ["cli", "command", "log"])
        self.assertEqual(len(outcome["journeys"]), 2)
        serialized = json.dumps(outcome, ensure_ascii=False)
        self.assertNotIn("private-project-a", serialized)
        self.assertEqual(
            report["process_evidence"]["pr_merge_success"]["denominator"], 1
        )

    def test_pinned_source_refs_ignore_registry_reordering_and_new_projects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            projects_file = self._fixture(root)
            first = build_scorecard(
                projects_file,
                measured_at="2026-07-11T00:00:00Z",
                as_of="2026-07-11T00:00:00Z",
                redact_paths=True,
            )
            pinned = [source["source_ref"] for source in first["sources"]]
            registry = json.loads(projects_file.read_text(encoding="utf-8"))
            new_project = root / "new-project"
            new_project.mkdir()
            _write_run(new_project, "run-new00001", verdict="FAIL", pr_number=10)
            registry["projects"] = [
                str(new_project),
                registry["projects"][1],
                registry["projects"][0],
                registry["projects"][2],
            ]
            projects_file.write_text(json.dumps(registry), encoding="utf-8")

            replay = build_scorecard(
                projects_file,
                measured_at="2026-07-11T00:00:00Z",
                as_of="2026-07-11T00:00:00Z",
                source_refs=pinned,
                redact_paths=True,
            )

        self.assertEqual(replay["source_project_count"], 2)
        self.assertEqual(
            replay["process_evidence"]["pr_merge_success"]["numerator"], 1
        )
        self.assertEqual(
            {source["source_ref"] for source in replay["sources"]}, set(pinned)
        )

    def test_pinned_source_fails_closed_when_registered_runtime_data_disappears(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            projects_file = self._fixture(root)
            first = build_scorecard(
                projects_file,
                measured_at="2026-07-11T00:00:00Z",
                as_of="2026-07-11T00:00:00Z",
                redact_paths=True,
            )
            pinned = [source["source_ref"] for source in first["sources"]]
            shutil.rmtree(
                root
                / "private-project-a"
                / ".claude"
                / "harness-state"
                / ".sessions"
            )

            with self.assertRaises(SourceDataUnavailable) as raised:
                build_scorecard(
                    projects_file,
                    measured_at="2026-07-11T00:00:00Z",
                    as_of="2026-07-11T00:00:00Z",
                    source_refs=pinned,
                    redact_paths=True,
                )

        self.assertEqual(raised.exception.unavailable, [pinned[0]])

    def test_product_receipt_only_source_can_be_pinned_without_run_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "product-only-project"
            project.mkdir()
            _write_product_journey_receipt(
                project,
                "product-only-journey",
                outcome="PASS",
            )
            projects_file = root / "projects.json"
            projects_file.write_text(
                json.dumps({"version": 1, "projects": [str(project)]}),
                encoding="utf-8",
            )
            source_ref = "source-" + hashlib.sha256(
                str(project.resolve()).encode("utf-8")
            ).hexdigest()[:10]

            report = build_scorecard(
                projects_file,
                measured_at="2026-07-11T00:00:00Z",
                as_of="2026-07-11T00:00:00Z",
                source_refs=[source_ref],
                redact_paths=True,
            )

        self.assertEqual(report["product_outcome"]["numerator"], 1)
        self.assertEqual(report["product_outcome"]["denominator"], 1)
        self.assertEqual(report["product_outcome"]["source_project_count"], 1)
        self.assertEqual(report["process_evidence"]["finished_runs"]["status"], "측정 불가")

    def test_markdown_separates_process_effectiveness_and_product_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = build_scorecard(
                self._fixture(Path(directory)),
                measured_at="2026-07-11T00:00:00Z",
                as_of="2026-07-11T00:00:00Z",
                redact_paths=True,
            )
        markdown = render_markdown(report)
        for heading in (
            "## 과정·merge 지표",
            "## Agent effectiveness",
            "## 실제 제품 outcome",
            "## 주장 가능 범위",
        ):
            self.assertIn(heading, markdown)
        self.assertIn("1/1", markdown)
        self.assertIn("측정 불가", markdown)
        self.assertIn("source 프로젝트: 2", markdown)
        self.assertIn("2026-07-11T00:00:00Z", markdown)

    def test_cli_emits_json_without_synthetic_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            projects_file = self._fixture(Path(directory))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(
                    [
                        "--projects-file",
                        str(projects_file),
                        "--measured-at",
                        "2026-07-11T00:00:00Z",
                        "--as-of",
                        "2026-07-11T00:00:00Z",
                        "--source-ref",
                        "source-placeholder",
                        "--redact-paths",
                        "--json",
                    ]
                )
        self.assertEqual(result, 2)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["error"], "source_ref_not_found")


class OutcomeScorecardDocumentTests(unittest.TestCase):
    def test_scorecard_contract_defines_required_axes_and_fields(self) -> None:
        contract = (ROOT / "docs" / "plugin" / "outcome-scorecard.md").read_text(
            encoding="utf-8"
        )
        for axis in ("과정·merge", "Agent effectiveness", "실제 제품 outcome"):
            self.assertIn(axis, contract)
        for field in (
            "task 유형",
            "repo 유형",
            "model",
            "provider",
            "harness variant",
            "trial",
            "denominator",
            "token",
            "wall-clock",
            "사람 개입",
            "실행 증거 종류",
        ):
            self.assertIn(field, contract)
        for effectiveness in (
            "SSOT",
            "runtime entrypoint",
            "capability owner",
            "첫 올바른 변경 대상",
            "불필요한 파일 읽기",
            "오경로",
            "영향 범위 누락",
            "context 기인 재작업",
            "cross-session 복구",
        ):
            self.assertIn(effectiveness, contract)
        self.assertIn("기능이 존재", contract)
        self.assertIn("측정 불가", contract)
        self.assertIn("1+1", contract)
        self.assertIn("공개 우위", contract)

    def test_baseline_records_reproduction_source_counts_and_limits(self) -> None:
        baseline = (ROOT / "docs" / "internal" / "outcome-baseline.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("harness/outcome_scorecard.py", baseline)
        self.assertIn("source 프로젝트 2", baseline)
        self.assertIn("26/28", baseline)
        self.assertIn("7/7", baseline)
        self.assertIn("TOOL_REPEAT_HIGH", baseline)
        self.assertIn("측정 불가", baseline)
        self.assertNotIn("제품 성공률 100%", baseline)

    def test_baseline_records_non_ui_product_journey_pilot(self) -> None:
        baseline = (ROOT / "docs" / "internal" / "outcome-baseline.md").read_text(
            encoding="utf-8"
        )
        for evidence in (
            "yt-make-intake-cli",
            "source-d640b1b95d",
            "journey PASS 1/1",
            "제품 AC 1/1",
            "사람 개입 0",
            "cli, command, log",
            "2026-07-12T07:36:43Z",
        ):
            self.assertIn(evidence, baseline)
        self.assertNotIn("/Users/dc.kim/project/youTubeGenerator", baseline)

    def test_baseline_records_ui_product_journey_pilot(self) -> None:
        baseline = (ROOT / "docs" / "internal" / "outcome-baseline.md").read_text(
            encoding="utf-8"
        )
        for evidence in (
            "UI 제품 journey pilot",
            "source-5509daf5ed",
            "finsight-underage-ui",
            "AC-001",
            "journey PASS 1/1",
            "제품 AC 1/1",
            "ui, screenshot, command, log",
            "실행 중 사람 개입 0",
            "2026-07-13T03:00:00Z",
        ):
            self.assertIn(evidence, baseline)
        self.assertNotIn("/Users/dc.kim/project/finsight", baseline)


if __name__ == "__main__":
    unittest.main()

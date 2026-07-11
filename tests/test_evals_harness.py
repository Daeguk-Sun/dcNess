"""행동 eval 하네스 구조 계약 테스트.

evals/ 의 러너·케이스·정답표가 구조 계약(계약 수준 정답표 — agent 이름/지침 문구
미포함, 블라인드 prompt, placeholder)을 지키는지 회귀로 보존한다.
실제 LLM 실행은 하지 않는다 — 그건 `bash evals/run.sh` 의 영역이다.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "evals"


class EvalsHarnessContractTests(unittest.TestCase):
    def test_runner_exists_and_parses(self) -> None:
        for name in ("run.sh", "run-core.sh"):
            run_sh = EVALS / name
            self.assertTrue(run_sh.is_file())
            result = subprocess.run(
                ["bash", "-n", str(run_sh)], capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        core = (EVALS / "run-core.sh").read_text(encoding="utf-8")
        self.assertIn("core-incident-subset.json", core)
        self.assertIn("EVAL_CASES", core)

    def test_runner_rejects_unknown_case_filter_without_llm_call(self) -> None:
        for case_filter in ("does-not-exist", ".", "..", "   "):
            with self.subTest(case_filter=case_filter), TemporaryDirectory() as td:
                tmp = Path(td)
                bin_dir = tmp / "bin"
                bin_dir.mkdir()
                marker = tmp / "claude-called"
                fake_claude = bin_dir / "claude"
                fake_claude.write_text(
                    "#!/usr/bin/env bash\n"
                    f"touch {marker}\n"
                    "exit 0\n",
                    encoding="utf-8",
                )
                fake_claude.chmod(fake_claude.stat().st_mode | stat.S_IEXEC)
                env = os.environ.copy()
                env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
                env["EVAL_CASES"] = case_filter
                env["EVAL_OUTPUT_DIR"] = str(tmp / "output")

                result = subprocess.run(
                    ["bash", str(EVALS / "run.sh")],
                    cwd=str(ROOT),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                self.assertEqual(
                    result.returncode, 2, result.stderr + result.stdout
                )
                self.assertIn("선택 케이스", result.stderr)
                self.assertFalse(marker.exists())

    def test_runner_executes_report_from_blind_instruction_snapshot(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            bin_dir = tmp / "bin"
            out_dir = tmp / "output"
            bin_dir.mkdir()
            fake_claude = bin_dir / "claude"
            fake_claude.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "set -euo pipefail",
                        "prompt=''",
                        "while [ \"$#\" -gt 0 ]; do",
                        "  case \"$1\" in -p) shift; prompt=\"$1\" ;; esac",
                        "  shift || true",
                        "done",
                        "if printf '%s' \"$prompt\" | grep -q '\\[정답표\\]'; then",
                        "  printf 'RESULT: PASS\\n'",
                        "else",
                        "  printf 'PWD=%s\\n' \"$PWD\"",
                        "  [ -d \"$PWD/docs\" ] && printf 'docs=yes\\n'",
                        "  [ ! -e \"$PWD/evals\" ] && printf 'evals=no\\n'",
                        "fi",
                    ]
                ),
                encoding="utf-8",
            )
            fake_claude.chmod(fake_claude.stat().st_mode | stat.S_IEXEC)
            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
            env["EVAL_CASES"] = "headless-prose-quality"
            env["EVAL_OUTPUT_DIR"] = str(out_dir)

            result = subprocess.run(
                ["bash", str(EVALS / "run.sh")],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            report = (
                out_dir / "headless-prose-quality" / "run-1-report.md"
            ).read_text(encoding="utf-8")
            self.assertIn("dcness-eval-instructions-", report)
            self.assertIn("docs=yes", report)
            self.assertIn("evals=no", report)
            self.assertNotIn(f"PWD={ROOT}", report)

    def test_judge_calibration_tool_is_documented(self) -> None:
        calibrate = EVALS / "calibrate_judge.py"
        self.assertTrue(calibrate.is_file())
        result = subprocess.run(
            ["python3.11", "-m", "py_compile", str(calibrate)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        example = EVALS / "judge-golden.example.json"
        self.assertTrue(example.is_file())
        self.assertIn('"labels"', example.read_text(encoding="utf-8"))

        readme = (EVALS / "README.md").read_text(encoding="utf-8")
        for needle in (
            "python3 evals/calibrate_judge.py",
            "judge-golden.json",
            "judge_review_candidate",
            "--min-agreement",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, readme)
        runner = (EVALS / "run.sh").read_text(encoding="utf-8")
        self.assertNotIn("judge-golden", runner)
        self.assertNotIn("core-incidents-v1.json", runner)
        self.assertIn('cp -R "$ROOT/docs" "$ROOT/skills"', runner)
        self.assertNotIn('s|{{REPO_ROOT}}|$ROOT|g', runner)

    def test_core_incident_subset_and_versioned_golden_candidate_exist(self) -> None:
        manifest = json.loads(
            (EVALS / "core-incident-subset.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["subset_version"], "core-incidents-v1")
        selected = {item["case"]: item for item in manifest["selected_cases"]}
        self.assertEqual(
            set(selected), {"shorts-real-spec", "headless-prose-quality"}
        )
        for item in selected.values():
            self.assertTrue(item["incident_risk"])
            self.assertTrue(item["regression_value"])
        self.assertIn("exclusion_policy", manifest)

        golden = json.loads(
            (EVALS / "golden" / "core-incidents-v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(golden["schema_version"], 2)
        self.assertEqual(golden["golden_version"], "core-incidents-v1-human-v1")
        self.assertEqual(golden["subset_version"], manifest["subset_version"])
        self.assertEqual(
            golden["verification_status"], "pending_owner_confirmation"
        )
        self.assertEqual(len(golden["labels"]), 2)
        for label in golden["labels"]:
            self.assertRegex(label["report_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(set(label["expectations"]), set(label["reasons"]))

    def test_every_case_has_required_files(self) -> None:
        case_dirs = sorted((EVALS / "cases").iterdir())
        self.assertGreaterEqual(len(case_dirs), 2)
        for case_dir in case_dirs:
            for name in ("prompt.md", "expected.md"):
                with self.subTest(case=case_dir.name, file=name):
                    self.assertTrue((case_dir / name).is_file())

    def test_prompts_use_placeholders_and_do_not_leak_expectations(self) -> None:
        for case_dir in sorted((EVALS / "cases").iterdir()):
            prompt = (case_dir / "prompt.md").read_text(encoding="utf-8")
            with self.subTest(case=case_dir.name):
                self.assertIn("{{REPO_ROOT}}", prompt)
                self.assertIn("{{CASE_DIR}}", prompt)
                # 블라인드 — 기대 결과(정답표 어휘)를 prompt 에 누설하지 않는다.
                for leak in ("MUST", "정답", "기대", "expected"):
                    self.assertNotIn(leak, prompt)

    def test_expected_files_stay_at_contract_level(self) -> None:
        """정답표는 계약 수준만 — agent 이름/지침 고유 문구에 묶이면 역할 개편 때 깨진다."""
        forbidden = (
            "product-acceptance",
            "architecture-validator",
            "module-architect",
            "system-architect",
            "SPEC_ACCEPTANCE",
            "SYSTEM_BOUNDARY",
            "TASK_LOCAL",
            "agents/",
            "skills/",
        )
        for case_dir in sorted((EVALS / "cases").iterdir()):
            expected = (case_dir / "expected.md").read_text(encoding="utf-8")
            with self.subTest(case=case_dir.name):
                self.assertRegex(expected, r"\[(MUST|MUST_NOT)\]")
                for token in forbidden:
                    self.assertNotIn(token, expected)

    def test_story_slice_case_pair_exists(self) -> None:
        partfirst = EVALS / "cases" / "story-slice-partfirst"
        skeleton = EVALS / "cases" / "story-slice-skeleton"
        for case_dir in (partfirst, skeleton):
            for name in ("prd.md", "stories.md"):
                with self.subTest(case=case_dir.name, file=name):
                    self.assertTrue((case_dir / name).is_file())
        self.assertIn(
            "[MUST]", (partfirst / "expected.md").read_text(encoding="utf-8")
        )
        self.assertIn(
            "[MUST_NOT]", (skeleton / "expected.md").read_text(encoding="utf-8")
        )

    def test_readme_documents_when_to_run_and_case_addition(self) -> None:
        readme = (EVALS / "README.md").read_text(encoding="utf-8")
        for needle in (
            "머지 전 1회",
            "플러그인 릴리즈 직전 1회",
            "CI 차단 게이트가 아니다",
            "계약 수준",
            "사고 1건 = 케이스 1개",
            "bash evals/run.sh",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, readme)

    def test_claude_md_recommends_eval_before_merge(self) -> None:
        claude_md = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("bash evals/run.sh", claude_md)
        self.assertIn("행동 eval (권고 — CI 차단 아님)", claude_md)

    def test_runner_persists_blind_report_and_judge_output(self) -> None:
        """#893 — run.sh must leave artifacts for missed-case and judge calibration review."""
        with TemporaryDirectory() as td:
            tmp = Path(td)
            bin_dir = tmp / "bin"
            out_dir = tmp / "eval-output"
            bin_dir.mkdir()
            fake_claude = bin_dir / "claude"
            fake_claude.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "set -euo pipefail",
                        "prompt=''",
                        "while [ \"$#\" -gt 0 ]; do",
                        "  case \"$1\" in",
                        "    -p) shift; prompt=\"$1\" ;;",
                        "  esac",
                        "  shift || true",
                        "done",
                        "if printf '%s' \"$prompt\" | grep -q '\\[정답표\\]'; then",
                        "  printf 'OK FAKE\\nRESULT: PASS\\n'",
                        "else",
                        "  printf 'blind report with concrete evidence\\n'",
                        "fi",
                    ]
                ),
                encoding="utf-8",
            )
            fake_claude.chmod(fake_claude.stat().st_mode | stat.S_IEXEC)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
            env["EVAL_OUTPUT_DIR"] = str(out_dir)
            env["EVAL_RUNS"] = "1"
            env["EVAL_RELEASE_CHECK"] = "1"
            result = subprocess.run(
                ["bash", str(EVALS / "run.sh")],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn(str(out_dir), result.stdout)
            report_files = sorted(out_dir.glob("*/run-1-report.md"))
            judge_files = sorted(out_dir.glob("*/run-1-judge.md"))
            self.assertGreaterEqual(len(report_files), 1)
            self.assertEqual(len(report_files), len(judge_files))
            self.assertIn("blind report", report_files[0].read_text(encoding="utf-8"))
            self.assertIn("RESULT: PASS", judge_files[0].read_text(encoding="utf-8"))
            telemetry = sorted(out_dir.glob("guard-telemetry.jsonl"))
            self.assertEqual(len(telemetry), 1)
            self.assertIn(
                '"kind":"eval_case_result"',
                telemetry[0].read_text(encoding="utf-8"),
            )
            telemetry_text = telemetry[0].read_text(encoding="utf-8")
            self.assertIn('"llm_turns":2', telemetry_text)
            self.assertIn('"estimated_output_tokens"', telemetry_text)

    def test_runner_persists_miss_report_and_judge_output_before_failing(self) -> None:
        """#893 — MISS runs must leave files for human/judge comparison."""
        with TemporaryDirectory() as td:
            tmp = Path(td)
            bin_dir = tmp / "bin"
            out_dir = tmp / "eval-output"
            bin_dir.mkdir()
            fake_claude = bin_dir / "claude"
            fake_claude.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "set -euo pipefail",
                        "prompt=''",
                        "while [ \"$#\" -gt 0 ]; do",
                        "  case \"$1\" in",
                        "    -p) shift; prompt=\"$1\" ;;",
                        "  esac",
                        "  shift || true",
                        "done",
                        "if printf '%s' \"$prompt\" | grep -q '\\[정답표\\]'; then",
                        "  printf 'MISS FAKE\\nRESULT: FAIL\\n'",
                        "else",
                        "  printf 'blind miss report with concrete evidence\\n'",
                        "fi",
                    ]
                ),
                encoding="utf-8",
            )
            fake_claude.chmod(fake_claude.stat().st_mode | stat.S_IEXEC)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
            env["EVAL_OUTPUT_DIR"] = str(out_dir)
            env["EVAL_RUNS"] = "1"
            result = subprocess.run(
                ["bash", str(EVALS / "run.sh")],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            report_files = sorted(out_dir.glob("*/run-1-report.md"))
            judge_files = sorted(out_dir.glob("*/run-1-judge.md"))
            self.assertGreaterEqual(len(report_files), 1)
            self.assertEqual(len(report_files), len(judge_files))
            self.assertIn("blind miss report", report_files[0].read_text(encoding="utf-8"))
            self.assertIn("RESULT: FAIL", judge_files[0].read_text(encoding="utf-8"))
            telemetry = sorted(out_dir.glob("guard-telemetry.jsonl"))
            self.assertEqual(len(telemetry), 1)
            text = telemetry[0].read_text(encoding="utf-8")
            self.assertIn('"kind":"eval_case_result"', text)
            self.assertIn('"passed":false', text)
            self.assertIn('"llm_turns":2', text)
            self.assertIn('"estimated_output_tokens"', text)

    def test_runner_records_report_execution_failure(self) -> None:
        """#904 — failed report LLM calls still count in eval telemetry."""
        with TemporaryDirectory() as td:
            tmp = Path(td)
            bin_dir = tmp / "bin"
            out_dir = tmp / "eval-output"
            bin_dir.mkdir()
            fake_claude = bin_dir / "claude"
            fake_claude.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "set -euo pipefail",
                        "exit 42",
                    ]
                ),
                encoding="utf-8",
            )
            fake_claude.chmod(fake_claude.stat().st_mode | stat.S_IEXEC)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
            env["EVAL_OUTPUT_DIR"] = str(out_dir)
            env["EVAL_RUNS"] = "1"
            result = subprocess.run(
                ["bash", str(EVALS / "run.sh")],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            telemetry = sorted(out_dir.glob("guard-telemetry.jsonl"))
            self.assertEqual(len(telemetry), 1)
            text = telemetry[0].read_text(encoding="utf-8")
            self.assertIn('"kind":"eval_case_result"', text)
            self.assertIn('"passed":false', text)
            self.assertIn('"failure_stage":"report"', text)
            self.assertIn('"llm_turns":1', text)

    def test_runner_records_judge_execution_failure(self) -> None:
        """#904 — failed judge LLM calls leave report artifact and failed attempt."""
        with TemporaryDirectory() as td:
            tmp = Path(td)
            bin_dir = tmp / "bin"
            out_dir = tmp / "eval-output"
            bin_dir.mkdir()
            fake_claude = bin_dir / "claude"
            fake_claude.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "set -euo pipefail",
                        "prompt=''",
                        "while [ \"$#\" -gt 0 ]; do",
                        "  case \"$1\" in",
                        "    -p) shift; prompt=\"$1\" ;;",
                        "  esac",
                        "  shift || true",
                        "done",
                        "if printf '%s' \"$prompt\" | grep -q '\\[정답표\\]'; then",
                        "  exit 43",
                        "else",
                        "  printf '한글 검수 보고\\n'",
                        "fi",
                    ]
                ),
                encoding="utf-8",
            )
            fake_claude.chmod(fake_claude.stat().st_mode | stat.S_IEXEC)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
            env["EVAL_OUTPUT_DIR"] = str(out_dir)
            env["EVAL_RUNS"] = "1"
            result = subprocess.run(
                ["bash", str(EVALS / "run.sh")],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertGreaterEqual(len(sorted(out_dir.glob("*/run-1-report.md"))), 1)
            telemetry = sorted(out_dir.glob("guard-telemetry.jsonl"))
            self.assertEqual(len(telemetry), 1)
            text = telemetry[0].read_text(encoding="utf-8")
            self.assertIn('"failure_stage":"judge"', text)
            self.assertIn('"llm_turns":2', text)
            self.assertIn('"token_estimate_basis":"utf8_bytes/4_lower_bound"', text)

    def test_judge_prompt_distinguishes_minimum_enum_from_rigid_schema(self) -> None:
        """#906 — HPQ-5 must not mistake branch conclusion enum for schema demand."""
        run_sh = (EVALS / "run.sh").read_text(encoding="utf-8")

        for needle in (
            "PASS / FAIL / ESCALATE 같은 최소 결론 enum 요구는 rigid schema 요구가 아니다",
            "status JSON, marker, fixed table, fixed schema, exact template",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, run_sh)


if __name__ == "__main__":
    unittest.main()

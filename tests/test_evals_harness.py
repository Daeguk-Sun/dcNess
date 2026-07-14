"""행동 eval 하네스 구조 계약 테스트.

evals/ 의 러너·케이스·정답표가 구조 계약(계약 수준 정답표 — agent 이름/지침 문구
미포함, 블라인드 prompt, placeholder)을 지키는지 회귀로 보존한다.
실제 LLM 실행은 하지 않는다 — 그건 `bash evals/run.sh` 의 영역이다.
"""
from __future__ import annotations

import json
import os
import re
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

    def test_core_incident_subset_and_verified_human_golden_exist(self) -> None:
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
        self.assertEqual(golden["verification_status"], "verified")
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

    # ------------------------------------------------------------------
    # #1120 — (case, run) 셀 단위 병렬 실행. 셀 내부 report→judge 순서만 유지.
    # ------------------------------------------------------------------

    @staticmethod
    def _write_fake_claude(bin_dir: Path, body_lines: list[str]) -> Path:
        fake_claude = bin_dir / "claude"
        fake_claude.write_text("\n".join(body_lines), encoding="utf-8")
        fake_claude.chmod(fake_claude.stat().st_mode | stat.S_IEXEC)
        return fake_claude

    @staticmethod
    def _verdict_fake(verdict: str) -> list[str]:
        """검수는 report, 채점은 고정 verdict 를 돌려주는 deterministic fake."""
        return [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "prompt=''",
            'while [ "$#" -gt 0 ]; do',
            '  case "$1" in -p) shift; prompt="$1" ;; esac',
            "  shift || true",
            "done",
            "if printf '%s' \"$prompt\" | grep -q '\\[정답표\\]'; then",
            f"  printf 'OK FAKE\\nRESULT: {verdict}\\n'",
            "else",
            "  printf 'blind report with concrete evidence\\n'",
            "fi",
        ]

    def _run_eval(self, env_overrides: dict, timeout: int = 90):
        env = os.environ.copy()
        env.update({k: str(v) for k, v in env_overrides.items()})
        return subprocess.run(
            ["bash", str(EVALS / "run.sh")],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def test_runner_runs_cells_in_parallel_but_serial_valve_stays_serial(self) -> None:
        """EVAL_PARALLEL>1 이면 셀이 실제로 겹쳐 돌고, EVAL_PARALLEL=1 은 겹치지 않는다."""
        with TemporaryDirectory() as td:
            tmp = Path(td)
            bin_dir = tmp / "bin"
            conc_dir = tmp / "conc"
            bin_dir.mkdir()
            conc_dir.mkdir()
            # 셀마다 진입 시 동시 실행 수를 원자적으로(mkdir 락) 세고 최대치를 기록한다.
            self._write_fake_claude(
                bin_dir,
                [
                    "#!/usr/bin/env bash",
                    "prompt=''",
                    'while [ "$#" -gt 0 ]; do',
                    '  case "$1" in -p) shift; prompt="$1" ;; esac',
                    "  shift || true",
                    "done",
                    'LOCK="$CONC_DIR/lock"',
                    'COUNT="$CONC_DIR/count"',
                    'MAXC="$CONC_DIR/max"',
                    'while ! mkdir "$LOCK" 2>/dev/null; do :; done',
                    'n=$(( $(cat "$COUNT" 2>/dev/null || echo 0) + 1 ))',
                    'echo "$n" > "$COUNT"',
                    'm=$(cat "$MAXC" 2>/dev/null || echo 0)',
                    'if [ "$n" -gt "$m" ]; then echo "$n" > "$MAXC"; fi',
                    'rmdir "$LOCK"',
                    "sleep 0.3",
                    'while ! mkdir "$LOCK" 2>/dev/null; do :; done',
                    'echo "$(( $(cat "$COUNT" 2>/dev/null || echo 1) - 1 ))" > "$COUNT"',
                    'rmdir "$LOCK"',
                    "if printf '%s' \"$prompt\" | grep -q '\\[정답표\\]'; then",
                    "  printf 'RESULT: PASS\\n'",
                    "else",
                    "  printf 'blind report\\n'",
                    "fi",
                ],
            )

            def run_and_measure(parallel: int) -> int:
                (conc_dir / "count").write_text("0", encoding="utf-8")
                (conc_dir / "max").write_text("0", encoding="utf-8")
                env = os.environ.copy()
                env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
                env["CONC_DIR"] = str(conc_dir)
                env["EVAL_CASES"] = "headless-prose-quality"
                env["EVAL_RUNS"] = "4"
                env["EVAL_PARALLEL"] = str(parallel)
                env["EVAL_OUTPUT_DIR"] = str(tmp / f"out-{parallel}")
                result = subprocess.run(
                    ["bash", str(EVALS / "run.sh")],
                    cwd=str(ROOT),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=90,
                )
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                return int((conc_dir / "max").read_text(encoding="utf-8").strip())

            parallel_max = run_and_measure(4)
            serial_max = run_and_measure(1)
            self.assertGreaterEqual(
                parallel_max, 2, f"EVAL_PARALLEL=4 인데 셀이 겹치지 않음 (max={parallel_max})"
            )
            self.assertEqual(
                serial_max, 1, f"EVAL_PARALLEL=1 인데 셀이 겹침 (max={serial_max})"
            )

    def test_parallel_and_serial_agree_on_pass_fail(self) -> None:
        """병렬/직렬 pass·fail 집계 동일 + EVAL_RELEASE_CHECK strict N/N 판정 불변 (#1120 MUST)."""
        cases = "headless-prose-quality shorts-real-spec story-slice-skeleton"

        def summary(stdout: str) -> list[str]:
            return sorted(
                line
                for line in stdout.splitlines()
                if re.search(r"— 정답 \d+/\d+", line) or "릴리즈 체크 실패" in line
            )

        for verdict, expected_rc in (("PASS", 0), ("FAIL", 1)):
            with self.subTest(verdict=verdict), TemporaryDirectory() as td:
                tmp = Path(td)
                bin_dir = tmp / "bin"
                bin_dir.mkdir()
                self._write_fake_claude(bin_dir, self._verdict_fake(verdict))
                # RELEASE_CHECK=1 + 선택 케이스를 전부 strict 로 둬 N/N 판정 경로까지 태운다.
                base_env = {
                    "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                    "EVAL_CASES": cases,
                    "EVAL_STRICT_CASES": cases,
                    "EVAL_RELEASE_CHECK": "1",
                    "EVAL_RUNS": "2",
                }
                serial = self._run_eval(
                    {**base_env, "EVAL_PARALLEL": "1", "EVAL_OUTPUT_DIR": str(tmp / "s")}
                )
                parallel = self._run_eval(
                    {**base_env, "EVAL_PARALLEL": "8", "EVAL_OUTPUT_DIR": str(tmp / "p")}
                )
                self.assertEqual(serial.returncode, expected_rc, serial.stdout + serial.stderr)
                self.assertEqual(parallel.returncode, expected_rc, parallel.stdout + parallel.stderr)
                self.assertEqual(
                    summary(serial.stdout),
                    summary(parallel.stdout),
                    f"serial vs parallel 집계 불일치\nS:{serial.stdout}\nP:{parallel.stdout}",
                )

    def test_parallel_telemetry_lines_all_valid_json(self) -> None:
        """병렬 실행 후 guard-telemetry.jsonl 전 라인이 valid JSON 이어야 한다 (#1120 MUST)."""
        with TemporaryDirectory() as td:
            tmp = Path(td)
            bin_dir = tmp / "bin"
            out_dir = tmp / "out"
            bin_dir.mkdir()
            self._write_fake_claude(bin_dir, self._verdict_fake("PASS"))
            result = self._run_eval(
                {
                    "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                    "EVAL_RUNS": "2",
                    "EVAL_PARALLEL": "8",
                    "EVAL_OUTPUT_DIR": str(out_dir),
                }
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            telemetry = out_dir / "guard-telemetry.jsonl"
            self.assertTrue(telemetry.is_file())
            epoch_count = 0
            for line in telemetry.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                obj = json.loads(line)  # 깨진 라인이면 여기서 실패
                if obj.get("kind") == "telemetry_epoch":
                    epoch_count += 1
            # epoch 중복은 무해 — 존재만 확인하고 깨진 라인이 없음을 위에서 강제한다.
            self.assertGreaterEqual(epoch_count, 1)

    def test_runner_rejects_invalid_parallel_without_llm_call(self) -> None:
        for value in ("0", "abc", "-1", "  "):
            with self.subTest(value=value), TemporaryDirectory() as td:
                tmp = Path(td)
                bin_dir = tmp / "bin"
                bin_dir.mkdir()
                marker = tmp / "claude-called"
                self._write_fake_claude(
                    bin_dir,
                    ["#!/usr/bin/env bash", f"touch {marker}", "exit 0"],
                )
                result = self._run_eval(
                    {
                        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                        "EVAL_PARALLEL": value,
                        "EVAL_OUTPUT_DIR": str(tmp / "out"),
                    },
                    timeout=30,
                )
                self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
                self.assertIn("EVAL_PARALLEL", result.stderr)
                self.assertFalse(marker.exists())

    def test_eval_parallel_is_documented(self) -> None:
        run_sh = (EVALS / "run.sh").read_text(encoding="utf-8")
        readme = (EVALS / "README.md").read_text(encoding="utf-8")
        claude_md = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        for label, text in (("run.sh", run_sh), ("README", readme), ("CLAUDE.md", claude_md)):
            with self.subTest(doc=label):
                self.assertIn("EVAL_PARALLEL", text)


if __name__ == "__main__":
    unittest.main()

"""Regression tests for impl-loop scoped provider capability memoization."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from harness.provider_failure_cache import (
    cache_path_for_state,
    check_cached_failure,
    classify_failure,
    emit_failure,
    record_failure,
)


ROOT = Path(__file__).resolve().parents[1]
CHAIN = ROOT / "scripts" / "dcness-implementation-chain"


def _write_executable(path: Path, text: str) -> None:
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    path.chmod(0o755)


def _write_chain_state(path: Path, project: Path, chain_id: str = "chain-a") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "kind": "dcness-story-run",
                "chain_id": chain_id,
                "project_root": str(project.resolve()),
                "tasks": [{"id": 1, "status": "pending"}],
            }
        ),
        encoding="utf-8",
    )


class ProviderFailureCacheStateTests(unittest.TestCase):
    def test_failure_classifier_only_marks_capability_failures_cacheable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            raw_log = Path(td) / "provider.log"
            cases = {
                "Authentication required: not logged in": "auth_unavailable",
                "Failed to load configuration: malformed config": "config_unavailable",
                "Connection reset by peer": "network_transient",
                "unexpected provider failure": "provider_error",
            }
            for text, expected in cases.items():
                with self.subTest(expected=expected):
                    raw_log.write_text(text, encoding="utf-8")
                    self.assertEqual(
                        classify_failure(
                            provider="codex-headless",
                            exit_code=1,
                            raw_log=raw_log,
                        ),
                        expected,
                    )

    def test_scope_is_chain_project_and_active_state_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            other_project = tmp / "other-project"
            project.mkdir()
            other_project.mkdir()
            state = project / ".dcness-work" / "story-run.json"
            _write_chain_state(state, project)
            raw_log = project / "first-provider.log"
            raw_log.write_text("auth unavailable", encoding="utf-8")
            failure = tmp / "failure.json"
            emit_failure(
                failure,
                provider="codex-headless",
                category="auth_unavailable",
                raw_log=raw_log,
            )

            recorded = record_failure(
                state,
                project,
                failure,
                expected_provider="codex-headless",
            )
            self.assertEqual(recorded["category"], "auth_unavailable")
            first_cache = cache_path_for_state(state, project)
            self.assertIsNotNone(first_cache)
            self.assertTrue(first_cache.is_file())
            self.assertEqual(
                check_cached_failure(state, project, "codex-headless")["raw_log"],
                str(raw_log.resolve()),
            )

            # A completed chain cannot consume its old cache.
            completed = json.loads(state.read_text(encoding="utf-8"))
            completed["tasks"][0]["status"] = "completed"
            state.write_text(json.dumps(completed), encoding="utf-8")
            self.assertIsNone(check_cached_failure(state, project, "codex-headless"))

            # Reinitialization receives a new chain id and therefore a new cache path.
            _write_chain_state(state, project, chain_id="chain-b")
            second_cache = cache_path_for_state(state, project)
            self.assertNotEqual(first_cache, second_cache)
            self.assertIsNone(check_cached_failure(state, project, "codex-headless"))

            # A state file cannot be reused from another project/worktree.
            with self.assertRaisesRegex(ValueError, "project_root mismatch"):
                check_cached_failure(state, other_project, "codex-headless")

    def test_concurrent_records_remain_valid_json_and_keep_first_failure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            state = project / ".dcness-work" / "story-run.json"
            _write_chain_state(state, project)

            failures: list[Path] = []
            for index in range(12):
                raw_log = tmp / f"raw-{index}.log"
                raw_log.write_text(f"failure {index}", encoding="utf-8")
                failure = tmp / f"failure-{index}.json"
                emit_failure(
                    failure,
                    provider="codex-headless",
                    category="config_unavailable",
                    raw_log=raw_log,
                )
                failures.append(failure)

            with ThreadPoolExecutor(max_workers=6) as pool:
                list(
                    pool.map(
                        lambda path: record_failure(
                            state,
                            project,
                            path,
                            expected_provider="codex-headless",
                        ),
                        failures,
                    )
                )

            cache_path = cache_path_for_state(state, project)
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["chain_id"], "chain-a")
            self.assertEqual(list(payload["entries"]), ["codex-headless"])
            cached = check_cached_failure(state, project, "codex-headless")
            self.assertEqual(cached["category"], "config_unavailable")
            self.assertIn(Path(cached["raw_log"]).name, {path.name for path in tmp.glob("raw-*.log")})


class ImplementationChainMemoizationTests(unittest.TestCase):
    def _fixture(self, tmp: Path) -> dict[str, Path | dict[str, str]]:
        project = tmp / "project"
        project.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=project, check=True)
        prompt = tmp / "prompt.md"
        prompt.write_text("Implement the frozen task.\n", encoding="utf-8")
        helper = tmp / "dcness-helper"
        _write_executable(helper, "#!/bin/sh\nexit 0\n")
        state = project / ".dcness-work" / "story-run.json"
        _write_chain_state(state, project)
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        codex_calls = tmp / "codex-calls.txt"
        claude_calls = tmp / "claude-calls.txt"
        _write_executable(
            bin_dir / "codex",
            """\
            #!/bin/sh
            if [ "${1:-}" = "--help" ]; then
              echo "Usage: codex"
              exit 0
            fi
            output=""
            while [ "$#" -gt 0 ]; do
              if [ "$1" = "--output-last-message" ]; then
                output="$2"
                shift 2
                continue
              fi
              shift
            done
            printf 'call\\n' >> "$CODEX_CALLS"
            cat >/dev/null
            case "${FAILURE_CASE:-auth}" in
              success)
                printf 'Codex success\\n\\nPASS\\n' > "$output"
                exit 0
                ;;
              auth)
                printf 'Authentication required: not logged in\\n' >&2
                exit 41
                ;;
              config)
                printf 'Failed to load configuration: malformed config\\n' >&2
                exit 42
                ;;
              timeout|idle)
                sleep 3
                ;;
              empty)
                exit 0
                ;;
              interrupt)
                exit 130
                ;;
              network)
                printf 'Connection reset by peer\\n' >&2
                exit 43
                ;;
            esac
            """,
        )
        _write_executable(
            bin_dir / "claude",
            """\
            #!/bin/sh
            printf 'call\\n' >> "$FALLBACK_CALLS"
            cat >/dev/null
            printf 'Claude fallback\\n\\nPASS\\n'
            """,
        )
        env = os.environ.copy()
        env.update(
            {
                "CODEX_CALLS": str(codex_calls),
                "FALLBACK_CALLS": str(claude_calls),
                "DCNESS_RUN_ID": "run-11111111",
                "DCNESS_SESSION_ID": "sid-cache",
                "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
            }
        )
        return {
            "project": project,
            "prompt": prompt,
            "helper": helper,
            "state": state,
            "codex_calls": codex_calls,
            "claude_calls": claude_calls,
            "env": env,
        }

    def _run(
        self,
        fixture: dict[str, Path | dict[str, str]],
        *,
        provenance: str = "routing",
        failure_case: str = "auth",
        run_id: str = "run-11111111",
        permission_retry: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        env = dict(fixture["env"])
        env["FAILURE_CASE"] = failure_case
        env["DCNESS_RUN_ID"] = run_id
        if failure_case == "timeout":
            env.update(DCNESS_CODEX_TIMEOUT="1", DCNESS_CODEX_IDLE_TIMEOUT="5")
        elif failure_case == "idle":
            env.update(DCNESS_CODEX_TIMEOUT="5", DCNESS_CODEX_IDLE_TIMEOUT="1")
        if permission_retry:
            env["DCNESS_CODEX_PERMISSION_RECEIPT"] = str(
                Path(fixture["project"]) / ".dcness-work" / "permission.json"
            )
        return subprocess.run(
            [
                str(CHAIN),
                "build-worker",
                "--provider",
                "headless-chain",
                "--provider-provenance",
                provenance,
                "--chain-state",
                str(fixture["state"]),
                "--prompt-file",
                str(fixture["prompt"]),
                "--project-root",
                str(fixture["project"]),
                "--helper",
                str(fixture["helper"]),
            ],
            capture_output=True,
            env=env,
            text=True,
            timeout=15,
        )

    @staticmethod
    def _count(path: Path) -> int:
        return len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0

    def test_two_task_chain_skips_one_cacheable_provider_execution(self) -> None:
        cases = (("auth", "auth_unavailable"), ("config", "config_unavailable"))
        for failure_case, category in cases:
            with self.subTest(category=category), tempfile.TemporaryDirectory() as td:
                fixture = self._fixture(Path(td))
                first = self._run(
                    fixture,
                    failure_case=failure_case,
                    run_id="run-11111111",
                )
                second = self._run(
                    fixture,
                    failure_case=failure_case,
                    run_id="run-22222222",
                )

                self.assertEqual(first.returncode, 0, first.stderr)
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertEqual(self._count(Path(fixture["codex_calls"])), 1)
                self.assertEqual(self._count(Path(fixture["claude_calls"])), 2)
                self.assertIn("PROVIDER_CACHE_HIT", second.stderr)
                self.assertIn(f"category={category}", second.stderr)
                self.assertIn("first_raw_log=", second.stderr)
                self.assertIn("scope=chain:chain-a", second.stderr)

    def test_missing_cli_is_cached_for_the_rest_of_the_chain(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fixture = self._fixture(Path(td))
            bin_dir = Path(dict(fixture["env"])["PATH"].split(os.pathsep)[0])
            (bin_dir / "codex").unlink()

            first = self._run(fixture, run_id="run-11111111")
            second = self._run(fixture, run_id="run-22222222")

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("category=cli_missing", first.stderr)
            self.assertIn("PROVIDER_CACHE_HIT", second.stderr)
            self.assertIn("category=cli_missing", second.stderr)
            self.assertEqual(self._count(Path(fixture["claude_calls"])), 2)

    def test_non_cacheable_failures_execute_again_on_next_task(self) -> None:
        cases = ("timeout", "idle", "empty", "interrupt", "network")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as td:
                fixture = self._fixture(Path(td))
                first = self._run(fixture, failure_case=case, run_id="run-11111111")
                second = self._run(fixture, failure_case=case, run_id="run-22222222")
                self.assertEqual(first.returncode, 0, first.stderr)
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertEqual(self._count(Path(fixture["codex_calls"])), 2)
                self.assertNotIn("PROVIDER_CACHE_HIT", second.stderr)

    def test_explicit_provider_and_permission_retry_bypass_existing_cache(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fixture = self._fixture(Path(td))
            seeded = self._run(fixture, failure_case="auth")
            explicit = self._run(
                fixture,
                provenance="explicit",
                failure_case="success",
                run_id="run-22222222",
            )
            self.assertEqual(seeded.returncode, 0, seeded.stderr)
            self.assertEqual(explicit.returncode, 0, explicit.stderr)
            self.assertIsNone(
                check_cached_failure(
                    Path(fixture["state"]),
                    Path(fixture["project"]),
                    "codex-headless",
                )
            )
            reseeded = self._run(
                fixture,
                failure_case="auth",
                run_id="run-33333333",
            )
            permission = self._run(
                fixture,
                failure_case="auth",
                run_id="run-44444444",
                permission_retry=True,
            )
            self.assertEqual(reseeded.returncode, 0, reseeded.stderr)
            self.assertEqual(permission.returncode, 0, permission.stderr)
            self.assertEqual(self._count(Path(fixture["codex_calls"])), 4)
            self.assertIn("cache bypass: provenance=explicit", explicit.stderr)
            self.assertIn("cache bypass: permission-retry", permission.stderr)

    def test_workspace_mutation_failure_never_falls_back_or_writes_cache(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fixture = self._fixture(Path(td))
            bin_dir = Path(dict(fixture["env"])["PATH"].split(os.pathsep)[0])
            _write_executable(
                bin_dir / "codex",
                """\
                #!/bin/sh
                if [ "${1:-}" = "--help" ]; then exit 0; fi
                cat >/dev/null
                mkdir -p src
                printf 'partial\\n' > src/partial.py
                printf 'Authentication required: not logged in\\n' >&2
                exit 41
                """,
            )

            result = self._run(fixture)

            self.assertEqual(result.returncode, 1)
            self.assertIn("changed workspace", result.stderr)
            self.assertEqual(self._count(Path(fixture["claude_calls"])), 0)
            cache_path = cache_path_for_state(
                Path(fixture["state"]), Path(fixture["project"])
            )
            self.assertFalse(cache_path.exists())


class ProviderFailureCacheDocsTests(unittest.TestCase):
    def test_impl_loop_docs_publish_scope_categories_bypass_and_diagnostics(self) -> None:
        paths = (
            ROOT / "docs" / "plugin" / "loop-procedure.md",
            ROOT / "skills" / "impl-loop" / "SKILL.md",
        )
        required = (
            "--chain-state",
            "--provider-provenance routing",
            "cli_missing",
            "auth_unavailable",
            "config_unavailable",
            "timeout",
            "idle_timeout",
            "empty_output",
            "interrupt",
            "network_transient",
            "permission retry",
            "first_raw_log",
            "chain_id",
        )
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for needle in required:
                with self.subTest(path=path.name, needle=needle):
                    self.assertIn(needle, text)
        skill_text = paths[1].read_text(encoding="utf-8")
        procedure_text = paths[0].read_text(encoding="utf-8")
        self.assertIn("task 1개 single `/impl-loop`도", skill_text)
        self.assertIn("single/chain 모드 모두 `--chain-state`", procedure_text)


if __name__ == "__main__":
    unittest.main()

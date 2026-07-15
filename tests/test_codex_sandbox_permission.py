"""Codex workspace-write sandbox permission recovery contract (#1113)."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from harness import codex_sandbox_permission as permission
from harness import ledger
from harness.session_state import run_dir, transition


ROOT = Path(__file__).resolve().parents[1]


class CodexSandboxPermissionClassificationTests(unittest.TestCase):
    def test_codex_worker_records_permission_receipt_and_ledger_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            sid = "sid-sandbox-permission"
            rid = "run-a11ce111"
            state_base = project / ".claude" / "harness-state"
            transition(sid, "run_started", run_id=rid, base_dir=state_base, entry_point="impl", lane="lite")
            transition(sid, "step_started", run_id=rid, base_dir=state_base, agent="build-worker", mode=None)

            prompt_file = tmp / "prompt.md"
            prompt_file.write_text("Implement and validate.\n", encoding="utf-8")
            gradle_home = tmp / "gradle-home"
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            codex = bin_dir / "codex"
            codex.write_text(
                textwrap.dedent(
                    """\
                    #!/bin/sh
                    if [ "$1" = "--help" ]; then
                      echo "Usage: codex [OPTIONS]"
                      exit 0
                    fi
                    out=""
                    while [ "$#" -gt 0 ]; do
                      case "$1" in
                        --output-last-message)
                          out="$2"
                          shift 2
                          ;;
                        *) shift ;;
                      esac
                    done
                    cat >/dev/null
                    printf 'GRADLE_USER_HOME=%s\\n' "$GRADLE_TEST_HOME"
                    printf 'java.net.SocketException: Operation not permitted\\n'
                    printf 'Codex sandbox denied write to %s/caches/modules.lock\\n' "$GRADLE_TEST_HOME"
                    printf 'Gradle validation blocked.\\n\\nVALIDATION_BLOCKED\\n' > "$out"
                    """
                ),
                encoding="utf-8",
            )
            codex.chmod(0o755)

            env = os.environ.copy()
            for key in (
                permission.NETWORK_ENV,
                permission.WRITABLE_ROOTS_ENV,
                permission.RETRY_RECEIPT_ENV,
            ):
                env.pop(key, None)
            env.update(
                {
                    "DCNESS_RUN_ID": rid,
                    "DCNESS_SESSION_ID": sid,
                    "GRADLE_TEST_HOME": str(gradle_home),
                    "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin:/usr/sbin:/sbin",
                }
            )

            result = subprocess.run(
                [
                    str(ROOT / "scripts" / "dcness-codex-worker"),
                    "build-worker",
                    "--prompt-file",
                    str(prompt_file),
                    "--project-root",
                    str(project),
                    "--helper",
                    str(ROOT / "scripts" / "dcness-helper"),
                ],
                capture_output=True,
                env=env,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt_paths = list(
                run_dir(sid, rid, base_dir=state_base).glob(
                    "codex-sandbox-permission-build-worker-*.json"
                )
            )
            self.assertEqual(len(receipt_paths), 1)
            receipt_path = receipt_paths[0]
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["state"], "permission_required")
            self.assertEqual(
                receipt["capabilities"], ["network_access", "writable_roots"]
            )
            self.assertIn("permission_required receipt", result.stderr)
            events = ledger.read_events(sid, rid, base_dir=state_base)
            permission_events = [
                event
                for event in events
                if event.get("event") == "blocked"
                and event.get("category")
                == "codex_sandbox_permission_required"
            ]
            self.assertEqual(len(permission_events), 1)
            self.assertEqual(
                permission_events[0].get("receipt_file"), str(receipt_path)
            )

    def test_socket_denial_and_gradle_cache_evidence_create_permission_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            gradle_home = tmp / "gradle-home"
            prose = tmp / "build-worker.md"
            raw_log = tmp / "codex.log"
            receipt_path = tmp / "codex-sandbox-permission.json"
            prose.write_text(
                "Gradle 검증 프로세스를 시작하지 못했습니다.\n\nVALIDATION_BLOCKED\n",
                encoding="utf-8",
            )
            raw_log.write_text(
                "GRADLE_USER_HOME=" + str(gradle_home) + "\n"
                "java.net.SocketException: Operation not permitted\n"
                "Codex sandbox denied write to "
                + str(tmp / "unrelated-cache" / "state.bin")
                + "\n"
                "Codex sandbox denied write to "
                + str(gradle_home / "caches" / "modules.lock")
                + "\n",
                encoding="utf-8",
            )

            receipt = permission.record_permission_required(
                prose_path=prose,
                raw_log_path=raw_log,
                project_root=project,
                receipt_path=receipt_path,
            )

            self.assertIsNotNone(receipt)
            assert receipt is not None
            self.assertEqual(receipt["state"], "permission_required")
            self.assertEqual(
                receipt["capabilities"], ["network_access", "writable_roots"]
            )
            self.assertEqual(
                receipt["suggested_writable_roots"],
                [str(gradle_home.resolve())],
            )
            self.assertEqual(receipt["retry_count"], 0)
            self.assertEqual(receipt["sandbox"], "workspace-write")
            self.assertFalse(receipt["danger_full_access"])
            self.assertTrue(receipt_path.is_file())
            self.assertIn("SocketException", json.dumps(receipt["evidence"]))
            self.assertIn(
                str(gradle_home),
                receipt["evidence"][-1]["signature"],
            )
            self.assertNotIn("unrelated-cache", receipt["evidence"][-1]["signature"])

    def test_pass_does_not_require_reading_raw_log(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            prose = tmp / "build-worker.md"
            prose.write_text("All gates passed\n\nPASS\n", encoding="utf-8")

            receipt = permission.record_permission_required(
                prose_path=prose,
                raw_log_path=tmp / "missing.log",
                project_root=tmp,
                receipt_path=tmp / "receipt.json",
            )

            self.assertIsNone(receipt)

    def test_non_sandbox_failures_do_not_create_permission_receipt(self) -> None:
        cases = {
            "assertion": "AssertionError: expected 2 but was 3",
            "compile": "Compilation failed: unresolved reference",
            "test": "Tests failed: 2 failures",
            "generic-permission": "Permission denied: ./gradlew",
            "cli": "codex CLI not found",
            "auth": "401 Unauthorized: authentication required",
            "timeout": "idle timeout after 180s",
        }
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            for name, raw_text in cases.items():
                with self.subTest(name=name):
                    prose = tmp / f"{name}.md"
                    raw_log = tmp / f"{name}.log"
                    receipt_path = tmp / f"{name}.json"
                    prose.write_text(
                        "검증을 완료하지 못했습니다.\n\nVALIDATION_BLOCKED\n",
                        encoding="utf-8",
                    )
                    raw_log.write_text(raw_text + "\n", encoding="utf-8")

                    receipt = permission.record_permission_required(
                        prose_path=prose,
                        raw_log_path=raw_log,
                        project_root=project,
                        receipt_path=receipt_path,
                    )

                    self.assertIsNone(receipt)
                    self.assertFalse(receipt_path.exists())

    def test_unrelated_write_denial_is_not_attached_to_gradle_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            gradle_home = tmp / "gradle-home"
            prose = tmp / "build-worker.md"
            raw_log = tmp / "codex.log"
            prose.write_text("Blocked\n\nVALIDATION_BLOCKED\n", encoding="utf-8")
            raw_log.write_text(
                "GRADLE_USER_HOME=" + str(gradle_home) + "\n"
                "java.net.SocketException: Operation not permitted\n"
                "Codex sandbox denied write to "
                + str(tmp / "unrelated-cache" / "state.bin")
                + "\n",
                encoding="utf-8",
            )

            receipt = permission.record_permission_required(
                prose_path=prose,
                raw_log_path=raw_log,
                project_root=project,
                receipt_path=tmp / "receipt.json",
            )

            self.assertIsNotNone(receipt)
            assert receipt is not None
            self.assertEqual(receipt["capabilities"], ["network_access"])
            self.assertEqual(receipt["suggested_writable_roots"], [])

    def test_sandbox_signature_without_validation_blocked_is_not_classified(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            prose = tmp / "build-worker.md"
            raw_log = tmp / "codex.log"
            prose.write_text("Tests failed\n\nTESTS_FAIL\n", encoding="utf-8")
            raw_log.write_text(
                "java.net.SocketException: Operation not permitted\n",
                encoding="utf-8",
            )

            receipt = permission.record_permission_required(
                prose_path=prose,
                raw_log_path=raw_log,
                project_root=tmp,
                receipt_path=tmp / "receipt.json",
            )

            self.assertIsNone(receipt)

    def test_signature_quoted_only_in_final_prose_is_not_execution_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            prose = tmp / "build-worker.md"
            raw_log = tmp / "codex.log"
            prose.write_text(
                "java.net.SocketException: Operation not permitted\n\n"
                "VALIDATION_BLOCKED\n",
                encoding="utf-8",
            )
            raw_log.write_text(
                "Codex command output contained no sandbox denial.\n"
                + permission._FINAL_PROSE_MARKER
                + "\n"
                + prose.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            receipt = permission.record_permission_required(
                prose_path=prose,
                raw_log_path=raw_log,
                project_root=tmp,
                receipt_path=tmp / "receipt.json",
            )

            self.assertIsNone(receipt)

    def test_retry_denial_updates_existing_receipt_without_new_request(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            prose = tmp / "build-worker.md"
            raw_log = tmp / "codex.log"
            receipt_path = tmp / "receipt.json"
            prose.write_text("Blocked\n\nVALIDATION_BLOCKED\n", encoding="utf-8")
            raw_log.write_text(
                "java.net.SocketException: Operation not permitted\n",
                encoding="utf-8",
            )
            receipt_path.write_text(
                json.dumps(
                    {
                        "receipt_type": permission.RECEIPT_TYPE,
                        "receipt_version": permission.RECEIPT_VERSION,
                        "state": "retrying",
                        "retry_count": 1,
                        "capabilities": ["network_access"],
                        "suggested_writable_roots": [],
                        "project_root": str(tmp),
                    }
                ),
                encoding="utf-8",
            )

            receipt = permission.record_permission_required(
                prose_path=prose,
                raw_log_path=raw_log,
                project_root=tmp,
                receipt_path=receipt_path,
                retry_receipt_path=receipt_path,
            )

            self.assertIsNotNone(receipt)
            assert receipt is not None
            self.assertEqual(receipt["state"], "retry_blocked")
            self.assertEqual(receipt["retry_count"], 1)

    def test_unclassified_validation_blocked_retry_stops_without_new_request(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            prose = tmp / "build-worker.md"
            raw_log = tmp / "codex.log"
            receipt_path = tmp / "receipt.json"
            prose.write_text("Still blocked\n\nVALIDATION_BLOCKED\n", encoding="utf-8")
            raw_log.write_text("No recognised permission signature\n", encoding="utf-8")
            receipt_path.write_text(
                json.dumps(
                    {
                        "receipt_type": permission.RECEIPT_TYPE,
                        "receipt_version": permission.RECEIPT_VERSION,
                        "state": "retrying",
                        "retry_count": 1,
                        "capabilities": ["network_access"],
                        "suggested_writable_roots": [],
                        "project_root": str(tmp),
                    }
                ),
                encoding="utf-8",
            )

            receipt = permission.record_permission_required(
                prose_path=prose,
                raw_log_path=raw_log,
                project_root=tmp,
                receipt_path=receipt_path,
                retry_receipt_path=receipt_path,
            )

            self.assertIsNotNone(receipt)
            assert receipt is not None
            self.assertEqual(receipt["state"], "retry_blocked")
            self.assertEqual(receipt["repeat_evidence"], [])


def _permission_receipt(project: Path, *, include_root: bool = True) -> dict:
    roots = [str(project.parent / "gradle-home")] if include_root else []
    capabilities = ["network_access"]
    if include_root:
        capabilities.append("writable_roots")
    return {
        "receipt_type": permission.RECEIPT_TYPE,
        "receipt_version": 1,
        "state": "permission_required",
        "project_root": str(project),
        "capabilities": capabilities,
        "suggested_writable_roots": roots,
        "retry_count": 0,
        "sandbox": "workspace-write",
        "danger_full_access": False,
        "evidence": [],
    }


class CodexSandboxPermissionRetryTests(unittest.TestCase):
    def _write_receipt(self, project: Path, *, include_root: bool = True) -> Path:
        receipt_path = project.parent / "receipt.json"
        receipt_path.write_text(
            json.dumps(_permission_receipt(project, include_root=include_root)),
            encoding="utf-8",
        )
        return receipt_path

    def _retry(
        self,
        *,
        receipt_path: Path,
        project: Path,
        decision: str,
    ) -> tuple[int, mock.Mock]:
        runner = mock.Mock(return_value=mock.Mock(returncode=0))
        rc = permission.retry_main(
            receipt_path=receipt_path,
            decision=decision,
            project_root=project,
            prompt_file=project.parent / "prompt.md",
            worker_path=ROOT / "scripts" / "dcness-codex-worker",
            helper_path=ROOT / "scripts" / "dcness-helper",
            run=runner,
            environ={"PATH": os.environ.get("PATH", "")},
        )
        return rc, runner

    def test_once_passes_approved_env_to_one_retry_without_writing_settings(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            project.mkdir()
            (tmp / "prompt.md").write_text("retry", encoding="utf-8")
            receipt_path = self._write_receipt(project)

            rc, runner = self._retry(
                receipt_path=receipt_path, project=project, decision="once"
            )

            self.assertEqual(rc, 0)
            runner.assert_called_once()
            call = runner.call_args
            env = call.kwargs["env"]
            self.assertEqual(env["DCNESS_CODEX_NETWORK_ACCESS"], "1")
            self.assertEqual(
                env["DCNESS_CODEX_WRITABLE_ROOTS"],
                str((tmp / "gradle-home").resolve()),
            )
            self.assertEqual(env["DCNESS_CODEX_PERMISSION_RECEIPT"], str(receipt_path))
            self.assertFalse((project / ".claude" / "settings.local.json").exists())
            args = call.args[0]
            self.assertEqual(args[1], "build-worker")
            self.assertNotIn("danger-full-access", args)

            second_rc, second_runner = self._retry(
                receipt_path=receipt_path, project=project, decision="once"
            )
            self.assertEqual(second_rc, 2)
            second_runner.assert_not_called()

    def test_project_preserves_existing_json_and_passes_same_env_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            settings = project / ".claude" / "settings.local.json"
            settings.parent.mkdir(parents=True)
            settings.write_text(
                json.dumps(
                    {
                        "permissions": {"allow": ["Read"]},
                        "env": {"EXISTING": "keep", "DCNESS_CODEX_MODEL": "gpt"},
                    }
                ),
                encoding="utf-8",
            )
            (tmp / "prompt.md").write_text("retry", encoding="utf-8")
            receipt_path = self._write_receipt(project)

            rc, runner = self._retry(
                receipt_path=receipt_path, project=project, decision="project"
            )

            self.assertEqual(rc, 0)
            saved = json.loads(settings.read_text(encoding="utf-8"))
            self.assertEqual(saved["permissions"], {"allow": ["Read"]})
            self.assertEqual(saved["env"]["EXISTING"], "keep")
            self.assertEqual(saved["env"]["DCNESS_CODEX_MODEL"], "gpt")
            self.assertEqual(saved["env"]["DCNESS_CODEX_NETWORK_ACCESS"], "1")
            self.assertEqual(
                saved["env"]["DCNESS_CODEX_WRITABLE_ROOTS"],
                str((tmp / "gradle-home").resolve()),
            )
            retry_env = runner.call_args.kwargs["env"]
            self.assertEqual(
                retry_env["DCNESS_CODEX_WRITABLE_ROOTS"],
                saved["env"]["DCNESS_CODEX_WRITABLE_ROOTS"],
            )

    def test_malformed_settings_deny_and_unsafe_root_do_not_retry_or_mutate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "project"
            settings = project / ".claude" / "settings.local.json"
            settings.parent.mkdir(parents=True)
            settings.write_text("{ malformed", encoding="utf-8")
            (tmp / "prompt.md").write_text("retry", encoding="utf-8")
            receipt_path = self._write_receipt(project)
            original = settings.read_bytes()

            rc, runner = self._retry(
                receipt_path=receipt_path, project=project, decision="project"
            )

            self.assertEqual(rc, 2)
            runner.assert_not_called()
            self.assertEqual(settings.read_bytes(), original)

            receipt_path.write_text(
                json.dumps(_permission_receipt(project)), encoding="utf-8"
            )
            rc, runner = self._retry(
                receipt_path=receipt_path, project=project, decision="deny"
            )
            self.assertEqual(rc, 3)
            runner.assert_not_called()
            self.assertEqual(settings.read_bytes(), original)

            unsafe = _permission_receipt(project)
            unsafe["suggested_writable_roots"] = ["relative/cache"]
            receipt_path.write_text(json.dumps(unsafe), encoding="utf-8")
            rc, runner = self._retry(
                receipt_path=receipt_path, project=project, decision="once"
            )
            self.assertEqual(rc, 2)
            runner.assert_not_called()
            self.assertEqual(settings.read_bytes(), original)


class CodexSandboxPermissionSurfaceTests(unittest.TestCase):
    def test_impl_loop_and_user_docs_describe_the_approval_journey(self) -> None:
        impl_loop = (ROOT / "skills" / "impl-loop" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        hooks = (ROOT / "docs" / "plugin" / "hooks.md").read_text(encoding="utf-8")

        for text in (impl_loop, hooks):
            self.assertIn("permission_required", text)
            self.assertIn("이번 실행에만 허용", text)
            self.assertIn("이 프로젝트에 저장", text)
            self.assertIn("거부", text)
            self.assertIn("outbound network", text)
            self.assertIn("workspace-write", text)
            self.assertIn("danger-full-access", text)
        self.assertIn("새 세션", hooks)


if __name__ == "__main__":
    unittest.main()

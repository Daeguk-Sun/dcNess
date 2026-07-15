"""Public generated-fallback TDD hook allow/block/fail-open contracts."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from harness.guard_telemetry import read_events
from harness.session_state_fail_open import read_fail_open_events


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks/tdd-guard.sh"


class TddHookContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write(self, relative: str, content: str = "// fixture\n") -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def run_payload(self, payload: dict | str, *, active: bool = True) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PYTHONPATH": str(ROOT), "CLAUDE_PLUGIN_ROOT": str(ROOT)}
        if active:
            env["DCNESS_FORCE_ENABLE"] = "1"
        else:
            env.pop("DCNESS_FORCE_ENABLE", None)
        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run(
            ["bash", str(HOOK)],
            cwd=self.root,
            env=env,
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )

    def edit(self, path: Path | str, *, active: bool = True) -> subprocess.CompletedProcess[str]:
        return self.run_payload(
            {"tool_name": "Edit", "tool_input": {"file_path": str(path)}},
            active=active,
        )

    def bash(self, command: str) -> subprocess.CompletedProcess[str]:
        return self.run_payload({"tool_name": "Bash", "tool_input": {"command": command}})

    def test_entry_config_test_and_non_js_skip_matrix(self) -> None:
        paths = (
            "apps/mobile/App.tsx",
            "apps/mobile/app/(tabs)/_layout.tsx",
            "apps/mobile/index.js",
            "src/main.ts",
            "src/foo.test.ts",
            "src/__tests__/helper.ts",
            "tests/helper.ts",
            "babel.config.js",
            "metro.config.js",
            "app.config.ts",
            "src/types/foo.ts",
            "src/foo.py",
            "docs/design-variants/_lib/show-ids.js",
        )
        for relative in paths:
            with self.subTest(relative=relative):
                path = self.write(relative)
                self.assertEqual(self.edit(path).returncode, 0)

    def test_entry_signature_skip_matrix(self) -> None:
        cases = {
            "src/expo-entry.tsx": "registerRootComponent(App);\n",
            "src/rn-entry.js": "AppRegistry.registerComponent('app', () => App);\n",
        }
        for relative, content in cases.items():
            with self.subTest(relative=relative):
                self.assertEqual(self.edit(self.write(relative, content)).returncode, 0)

    def test_implementation_names_are_not_mistaken_for_tests(self) -> None:
        for relative in (
            "src/contest.ts",
            "src/spectrum.ts",
            "src/latest.ts",
            "src/contest/board.ts",
            "contest.ts",
        ):
            with self.subTest(relative=relative):
                self.assertEqual(self.edit(self.write(relative, "export const x = 1;\n")).returncode, 2)

    def test_matching_test_locations_cover_sibling_grandparent_and_src_root(self) -> None:
        cases = [
            ("src/biz.ts", "src/biz.test.ts"),
            ("src/audio/decoder/X.ts", "src/__tests__/X.spec.ts"),
            (
                "apps/mobile/src/audio/AudioEngine.ts",
                "apps/mobile/src/__tests__/AudioEngine.test.ts",
            ),
            (
                "packages/core/src/utils/format.ts",
                "packages/core/src/__tests__/format.test.ts",
            ),
        ]
        for implementation, test in cases:
            with self.subTest(implementation=implementation):
                target = self.write(implementation, "export const x = 1;\n")
                self.write(test, "test('ok', () => {});\n")
                self.assertEqual(self.edit(target).returncode, 0)

    def test_tdd_exempt_requires_a_nonempty_reason_from_file_or_payload(self) -> None:
        allowed_file = self.write(
            "src/dto.ts",
            "// tdd-exempt: DTO shape only\nexport interface Dto {}\n",
        )
        denied_file = self.write(
            "src/empty.ts",
            "// tdd-exempt:   \nexport const x = 1;\n",
        )
        self.assertEqual(self.edit(allowed_file).returncode, 0)
        self.assertEqual(self.edit(denied_file).returncode, 2)

        write_payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(self.root / "src/generated.ts"),
                "content": "// tdd-exempt: generated barrel\nexport const x = 1;\n",
            },
        }
        self.assertEqual(self.run_payload(write_payload).returncode, 0)
        write_payload["tool_input"]["content"] = "// tdd-exempt:   \nexport const x = 1;\n"
        self.assertEqual(self.run_payload(write_payload).returncode, 2)

    def test_bash_write_targets_share_the_same_policy(self) -> None:
        blocked = (
            "printf 'export const x=1' > src/generated.ts",
            "printf x | tee src/from-tee.ts",
            "cat <<'EOF' > src/from-heredoc.ts\nexport const x=1\nEOF",
        )
        for command in blocked:
            with self.subTest(command=command):
                result = self.bash(command)
                self.assertEqual(result.returncode, 2)
                self.assertIn("TDD GUARD[Bash]", result.stderr)

        self.write("src/generated.test.ts", "test('ok', () => {});\n")
        self.assertEqual(self.bash("printf x > src/generated.ts").returncode, 0)
        self.assertEqual(self.bash("printf x > src/another.test.ts").returncode, 0)
        self.assertEqual(self.bash("npm test 2>&1 | tail -20").returncode, 0)

    def test_public_exit_stderr_and_guard_receipt_contract(self) -> None:
        denied = self.edit(self.write("src/biz.ts", "export const x = 1;\n"))
        self.assertEqual(denied.returncode, 2)
        self.assertIn("TDD GUARD", denied.stderr)
        self.assertNotIn("permissionDecision", denied.stdout)
        self.assertTrue(
            any(
                row.get("kind") == "guard_hit"
                and row.get("guard") == "tdd-guard"
                and row.get("category") == "missing_test"
                for row in read_events(cwd=self.root)
            )
        )

        self.write("src/biz.test.ts", "test('ok', () => {});\n")
        self.assertEqual(self.edit(self.root / "src/biz.ts").returncode, 0)

    def test_active_parse_failure_is_recorded_but_inactive_noop_is_silent(self) -> None:
        self.assertEqual(self.run_payload("", active=True).returncode, 0)
        events = read_fail_open_events(cwd=self.root)
        self.assertEqual([(row["hook"], row["category"]) for row in events], [("tdd-guard", "payload_empty")])

        state = self.root / ".claude/harness-state/fail-open-events.jsonl"
        state.unlink()
        self.assertEqual(self.run_payload("", active=False).returncode, 0)
        self.assertEqual(read_fail_open_events(cwd=self.root), [])

    def test_hook_registration_and_notebook_payload_contract(self) -> None:
        config = json.loads((ROOT / "hooks/hooks.json").read_text(encoding="utf-8"))
        matchers = [
            entry["matcher"]
            for entry in config["hooks"]["PreToolUse"]
            if any("tdd-guard.sh" in hook.get("command", "") for hook in entry.get("hooks", []))
        ]
        self.assertTrue(any("Bash" in matcher.split("|") for matcher in matchers))

        result = self.run_payload(
            {"tool_name": "NotebookEdit", "tool_input": {"notebook_path": "analysis.ipynb"}}
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(read_fail_open_events(cwd=self.root), [])


if __name__ == "__main__":
    unittest.main()

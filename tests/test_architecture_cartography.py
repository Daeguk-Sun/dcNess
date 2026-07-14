"""Contract tests for the bounded root architecture Cartography (#1059)."""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "architecture-cartography"
NODE = shutil.which("node")


def _run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [NODE, str(ROOT / "scripts" / script), "--root", str(FIXTURE), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


class ArchitectureCartographyContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root_map = (FIXTURE / "docs" / "architecture.md").read_text(
            encoding="utf-8"
        )
        self.transition = (FIXTURE / "state-transition.md").read_text(
            encoding="utf-8"
        )

    def test_mms_change_is_routable_from_root_to_code_epic_and_decisions(self) -> None:
        for needle in (
            "app/src/main/kotlin/example/mms/MmsWapPushReceiver.kt",
            "app/src/main/kotlin/example/mms/MmsSender.kt",
            "docs/epics/epic-01-sms/architecture.md",
            "docs/epics/epic-02-mms/architecture.md",
            "docs/decisions/0001-message-routing.md",
            "docs/decisions/0002-mms-transport.md",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.root_map)

    def test_root_is_bounded_to_capability_and_entrypoint_routes(self) -> None:
        self.assertIn("## Runtime entrypoint routes", self.root_map)
        self.assertIn("## Capability routes", self.root_map)
        self.assertNotIn("## Story -> 모듈 매핑", self.root_map)
        self.assertNotIn("## 구현 순서", self.root_map)

    def test_as_built_application_to_data_lifecycle_edge_is_recorded(self) -> None:
        app = (
            FIXTURE / "app" / "src" / "main" / "kotlin" / "example" / "App.kt"
        ).read_text(encoding="utf-8")
        self.assertIn("messageObserver.start()", app)
        self.assertIn("app-root --> data", self.root_map)
        self.assertIn("Application lifecycle이 data observer를 시작", self.root_map)

    def test_landed_transition_requires_code_evidence(self) -> None:
        self.assertIn("Before: `planned`", self.transition)
        self.assertIn("Middle: `stub`", self.transition)
        self.assertIn("After: `landed`", self.transition)
        self.assertIn(
            "app/src/main/kotlin/example/mms/MmsWapPushReceiver.kt", self.transition
        )
        self.assertIn("`landed`로 올리지 않는다", self.transition)
        self.assertIn(
            "app/src/test/kotlin/example/sms/SmsReceiverTest.kt", self.root_map
        )

    @unittest.skipUnless(NODE, "node not installed - cartography gates use node")
    def test_fixture_passes_design_and_repo_relative_path_gates(self) -> None:
        design = _run("check_design_artifact_structure.mjs")
        paths = _run("check_doc_path_integrity.mjs")

        self.assertEqual(design.returncode, 0, design.stderr)
        self.assertEqual(paths.returncode, 0, paths.stderr)
        self.assertNotIn("app/" + "...", self.root_map)


if __name__ == "__main__":
    unittest.main()

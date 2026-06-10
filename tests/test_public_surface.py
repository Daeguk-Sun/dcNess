"""Regression tests for the public workflow surface gate."""
from __future__ import annotations

import shutil
import subprocess
import unittest
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_public_surface.mjs"
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "node not installed — public-surface gate is a node script")
class PublicSurfaceGateTests(unittest.TestCase):
    def test_public_surface_contract_passes(self) -> None:
        proc = subprocess.run(
            [NODE, str(SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"public surface gate failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
        )

    def test_surface_contract_uses_lifecycle_defaults(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        positioning = (ROOT / "docs" / "plugin" / "positioning.md").read_text(
            encoding="utf-8"
        )

        defaults = self._array(script, "defaultSkills")
        advanced = self._array(script, "advancedSkills")
        support = self._array(script, "supportSkills")
        internal_skills = self._array(script, "internalSkills")
        internal_agents = self._array(script, "internalAgents")

        self.assertEqual(["spec", "design", "impl", "acceptance"], defaults)
        self.assertEqual(["impl-loop", "tech-review", "ux"], advanced)
        self.assertEqual(["to-issue"], support)
        self.assertEqual(["compact-design"], internal_skills)
        self.assertNotIn("qa", internal_agents)

        for name in defaults:
            self.assertIn(f"`/{name}`", positioning)
        self.assertIn("계획 / 설계 / 구현 / 검수", positioning)
        self.assertIn("/spec -> /design -> /impl -> /acceptance", positioning)
        self.assertNotIn("Compatibility Entrypoints", positioning)
        self.assertIn("Support Entrypoints", positioning)
        self.assertIn("기본/support/고급/유틸리티/내부 agent", positioning)

    def _array(self, text: str, key: str) -> list[str]:
        match = re.search(rf"{key}:\s*\[([^\]]*)\]", text)
        self.assertIsNotNone(match)
        return re.findall(r"'([^']+)'", match.group(1))


if __name__ == "__main__":
    unittest.main()

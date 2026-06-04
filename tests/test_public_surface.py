"""Regression tests for the public workflow surface gate."""
from __future__ import annotations

import shutil
import subprocess
import unittest
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


if __name__ == "__main__":
    unittest.main()

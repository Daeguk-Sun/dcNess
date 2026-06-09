"""Design public surface contract tests."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DesignSurfaceContractTests(unittest.TestCase):
    def test_design_skill_owns_design_loop_without_architect_loop_alias(self) -> None:
        design_dir = ROOT / "skills" / "design"
        design = (design_dir / "SKILL.md").read_text(encoding="utf-8")
        routing = (design_dir / "design-routing.md").read_text(encoding="utf-8")

        self.assertFalse((ROOT / "skills" / "architect-loop").exists())
        self.assertRegex(design, r"(?m)^name:\s*design$")
        self.assertIn("entry_point**: `design`", design)
        self.assertIn("begin-run design", design)
        self.assertIn("design-routing.md", design)
        self.assertIn("`/spec` 종료 후", design)
        self.assertIn("/spec -> /design -> /impl -> /acceptance", design)
        self.assertIn("`/design` skill **단일 전용**", routing)

        for text in (design, routing):
            self.assertNotIn("/architect-loop", text)
            self.assertNotIn("architect-loop", text)
            self.assertNotIn("호환", text)

    def test_design_is_default_lifecycle_surface(self) -> None:
        script = (ROOT / "scripts" / "check_public_surface.mjs").read_text(
            encoding="utf-8"
        )
        positioning = (ROOT / "docs" / "plugin" / "positioning.md").read_text(
            encoding="utf-8"
        )
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        default_match = re.search(r"defaultSkills:\s*\[([^\]]+)\]", script)
        advanced_match = re.search(r"advancedSkills:\s*\[([^\]]+)\]", script)
        self.assertIsNotNone(default_match)
        self.assertIsNotNone(advanced_match)
        self.assertIn("'design'", default_match.group(1))
        self.assertNotIn("'design'", advanced_match.group(1))

        for text in (positioning, readme):
            self.assertIn("`/design`", text)
            self.assertIn("product/technical design", text)
            self.assertIn("visual design", text)
            self.assertNotIn("`/architect-loop`", text)
            self.assertNotIn("호환 alias", text)


if __name__ == "__main__":
    unittest.main()

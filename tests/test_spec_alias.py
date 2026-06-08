"""Spec alias contract tests."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SpecAliasContractTests(unittest.TestCase):
    def test_spec_skill_alias_exists_without_removing_product_plan(self) -> None:
        spec = (ROOT / "skills" / "spec" / "SKILL.md").read_text(encoding="utf-8")
        self.assertRegex(spec, r"(?m)^name:\s*spec$")
        self.assertIn("/product-plan", spec)
        self.assertIn("호환", spec)
        self.assertIn("SPEC_ACCEPTANCE", spec)
        self.assertIn("/spec -> /design -> /impl -> /acceptance", spec)
        self.assertNotIn("후속 #645", spec)

        product_plan = (
            ROOT / "skills" / "product-plan" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn('"/spec"', product_plan)
        self.assertIn('"/product-plan"', product_plan)

    def test_spec_acceptance_checkpoint_is_documented_in_product_plan(self) -> None:
        skill = (ROOT / "skills" / "product-plan" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        routing = (
            ROOT / "skills" / "product-plan" / "product-plan-routing.md"
        ).read_text(encoding="utf-8")
        for text in (skill, routing):
            self.assertIn("product-acceptance", text)
            self.assertIn("SPEC_ACCEPTANCE", text)
            self.assertIn("full E2E", text)
            self.assertIn("범위 밖", text)

    def test_public_surface_keeps_spec_default_and_hides_product_plan_compat(self) -> None:
        script = (ROOT / "scripts" / "check_public_surface.mjs").read_text(
            encoding="utf-8"
        )
        positioning = (ROOT / "docs" / "plugin" / "positioning.md").read_text(
            encoding="utf-8"
        )
        default_match = re.search(r"defaultSkills:\s*\[([^\]]+)\]", script)
        compat_match = re.search(r"compatSkills:\s*\[([^\]]+)\]", script)
        self.assertIsNotNone(default_match)
        self.assertIsNotNone(compat_match)
        defaults = default_match.group(1)
        compat = compat_match.group(1)
        self.assertIn("'spec'", defaults)
        self.assertNotIn("'product-plan'", defaults)
        self.assertIn("'product-plan'", compat)
        self.assertIn("`/spec`", positioning)
        self.assertNotIn("`/product-plan`", positioning)
        self.assertNotIn("호환 alias", positioning)

    def test_workflow_router_prefers_spec_without_public_product_plan_alias(self) -> None:
        router = (ROOT / "docs" / "plugin" / "workflow-router.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("clarify 또는 `/spec`", router)
        self.assertIn("Deep: /spec", router)
        self.assertNotIn("`/product-plan` 호환", router)
        self.assertIn("/spec` → `/tech-review`", router)


if __name__ == "__main__":
    unittest.main()

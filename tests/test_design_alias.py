"""Design alias contract tests."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DesignAliasContractTests(unittest.TestCase):
    def test_design_skill_alias_exists_without_removing_architect_loop(self) -> None:
        design = (ROOT / "skills" / "design" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertRegex(design, r"(?m)^name:\s*design$")
        self.assertIn("/architect-loop", design)
        self.assertIn("호환", design)
        self.assertIn("product/technical design", design)
        self.assertIn("visual design", design)
        self.assertIn("설계 전체", design)

        architect_loop = (
            ROOT / "skills" / "architect-loop" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertRegex(architect_loop, r"(?m)^name:\s*architect-loop$")
        self.assertIn("/architect-loop", architect_loop)

    def test_design_alias_delegates_to_architect_loop_routing(self) -> None:
        design = (ROOT / "skills" / "design" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        hooks = (ROOT / "harness" / "hooks.py").read_text(encoding="utf-8")
        self.assertIn("../architect-loop/SKILL.md", design)
        self.assertIn("../architect-loop/architect-loop-routing.md", design)
        self.assertIn('entry == "architect-loop"', hooks)
        self.assertIn("begin-run architect-loop", design)
        self.assertIn("entry_point = `architect-loop`", design)
        self.assertIn("`design` 으로 시작하지 않는다", design)

    def test_public_surface_tracks_design_as_advanced_until_flip(self) -> None:
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
        self.assertNotIn("'design'", default_match.group(1))
        self.assertIn("'design'", advanced_match.group(1))

        default_table = re.search(
            r"\| 기본 진입점 \|.*?\n(?P<body>.*?)\n\n사용자는 lane",
            positioning,
            flags=re.S,
        )
        advanced_table = re.search(
            r"## Advanced Entrypoints\n\n.*?\n\n(?P<body>\| 고급 진입점 .*?)\n\n## Utility Surface",
            positioning,
            flags=re.S,
        )
        self.assertIsNotNone(default_table)
        self.assertIsNotNone(advanced_table)
        self.assertNotIn("/design", default_table.group("body"))
        self.assertIn("/design", advanced_table.group("body"))
        self.assertIn("고급 workflow | `/design`", readme)
        self.assertIn("product/technical design", positioning)
        self.assertIn("visual design", positioning)
        self.assertIn("product/technical design", readme)
        self.assertIn("visual design", readme)


if __name__ == "__main__":
    unittest.main()

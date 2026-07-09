"""Agent model tier contract tests."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _agent_model(name: str) -> str:
    text = (ROOT / "agents" / f"{name}.md").read_text(encoding="utf-8")
    match = re.search(r"^model:\s*(\S+)\s*$", text, flags=re.MULTILINE)
    if not match:
        raise AssertionError(f"agents/{name}.md is missing frontmatter model")
    return match.group(1)


class AgentModelTierTests(unittest.TestCase):
    def test_high_leverage_agents_use_opus(self) -> None:
        expected_opus = {
            "module-architect",
            "architecture-validator",
            "engineer",
            "product-acceptance",
            "build-worker",
            "system-architect",
            "tech-reviewer",
        }

        for agent in expected_opus:
            with self.subTest(agent=agent):
                self.assertEqual(_agent_model(agent), "opus")

    def test_remaining_agents_stay_sonnet(self) -> None:
        expected_sonnet = {
            "ux-architect",
            "designer",
            "test-engineer",
            "impl-validator",
        }

        for agent in expected_sonnet:
            with self.subTest(agent=agent):
                self.assertEqual(_agent_model(agent), "sonnet")


if __name__ == "__main__":
    unittest.main()

"""Agent Operability and flow ownership contract tests."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AgentOperabilityContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.shared_principles = (
            ROOT / "docs" / "plugin" / "agents" / "_shared" / "module-design-principles.md"
        ).read_text(encoding="utf-8")
        self.module_architect = (
            ROOT / "docs" / "plugin" / "agents" / "module-architect" / "module-architect-agent.md"
        ).read_text(encoding="utf-8")
        self.impl_template = (
            ROOT / "docs" / "plugin" / "agents" / "module-architect" / "templates" / "impl-task.md"
        ).read_text(encoding="utf-8")
        self.epic_architecture_template = (
            ROOT / "docs" / "plugin" / "agents" / "system-architect" / "templates" / "epic-architecture.md"
        ).read_text(encoding="utf-8")
        self.system_architect = (
            ROOT / "docs" / "plugin" / "agents" / "system-architect" / "system-architect-agent.md"
        ).read_text(encoding="utf-8")
        self.pr_reviewer = (
            ROOT / "docs" / "plugin" / "agents" / "pr-reviewer" / "pr-reviewer-agent.md"
        ).read_text(encoding="utf-8")
        self.pr_review_axes = (
            ROOT / "docs" / "plugin" / "agents" / "pr-reviewer" / "references" / "review-axes.md"
        ).read_text(encoding="utf-8")
        self.codex_pr_reviewer = (
            ROOT / "codex" / "skills" / "dcness-pr-reviewer" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.architecture_validator = (
            ROOT
            / "docs" / "plugin" / "agents"
            / "architecture-validator"
            / "architecture-validator-agent.md"
        ).read_text(encoding="utf-8")
        self.codex_architecture_validator = (
            ROOT
            / "codex"
            / "skills"
            / "dcness-architecture-validator"
            / "SKILL.md"
        ).read_text(encoding="utf-8")

    def test_shared_principles_define_agent_operability_axis(self) -> None:
        for needle in (
            "## Agent Operability",
            "edit target determinism",
            "context locality",
            "searchability",
            "state ownership",
            "extension point",
            "validation locality",
            "compaction survivability",
            "파일 크기 축소가 아니라",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.shared_principles)

        self.assertIn("하드 임계", self.shared_principles)
        self.assertIn("hard gate 가 아니다", self.shared_principles)

    def test_epic_architecture_template_records_operability_in_module_list(self) -> None:
        for needle in (
            "## 모듈 목록",
            "책임",
            "공개 인터페이스",
            "검증 경로",
            "forbidden append",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.epic_architecture_template)

        self.assertNotIn("## Flow Ownership Map", self.epic_architecture_template)

        for needle in ("module responsibility", "owner module", "validation path"):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.system_architect)

    def test_impl_task_template_requires_agent_workability_evidence(self) -> None:
        for needle in (
            "## Agent Workability",
            "owner flow/module",
            "entrypoint role",
            "state owner",
            "allowed touch",
            "forbidden touch",
            "validation path",
            "future change scenario",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.impl_template)

    def test_module_architect_requires_flow_owner_before_entrypoint_append(self) -> None:
        for needle in (
            "Agent Operability",
            "module responsibility",
            "entrypoint",
            "flow owner",
            "seam extraction task",
            "append",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.module_architect)

    def test_pr_reviewers_share_agent_operability_review_axis(self) -> None:
        for text_name, text in (
            ("claude", self.pr_reviewer),
            ("axes", self.pr_review_axes),
            ("codex", self.codex_pr_reviewer),
        ):
            for needle in (
                "Agent Operability",
                "edit target",
                "state owner",
                "validation path",
                "overly broad entrypoint",
                "entrypoint",
                "append",
            ):
                with self.subTest(text=text_name, needle=needle):
                    self.assertIn(needle, text)

    def test_pr_reviewers_promote_owner_less_append_to_must_fix(self) -> None:
        for text_name, text in (
            ("claude", self.pr_reviewer),
            ("axes", self.pr_review_axes),
            ("codex", self.codex_pr_reviewer),
        ):
            for needle in (
                "MUST FIX 로 승격",
                "dispatch-only entrypoint",
                "owner module 없이",
                "render/helper/session/global state",
                "owner 근처 validation path",
                "footprint 밖 기존 누적",
            ):
                with self.subTest(text=text_name, needle=needle):
                    self.assertIn(needle, text)

    def test_pr_reviewers_do_not_accept_entrypoint_file_as_owner(self) -> None:
        for text_name, text in (
            ("claude", self.pr_reviewer),
            ("axes", self.pr_review_axes),
            ("codex", self.codex_pr_reviewer),
        ):
            for needle in (
                "entrypoint 파일 자체는 owner module 로 인정하지 않는다",
                "함수명 prefix",
                "manual-only validation",
            ):
                with self.subTest(text=text_name, needle=needle):
                    self.assertIn(needle, text)

    def test_shared_principles_scope_must_fix_promotion_to_pr_reviewer(self) -> None:
        self.assertIn("MUST FIX 로 승격", self.shared_principles)
        self.assertIn(
            "entrypoint append + render/helper/session/global state 흡수 + owner 근처 validation path 부재",
            self.shared_principles,
        )
        self.assertIn("크기가 아니라 작업성 악화 조합", self.shared_principles)
        for needle in (
            "entrypoint 파일 자체는 owner module 로 인정하지 않는다",
            "함수명 prefix",
            "manual-only validation",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.shared_principles)

    def test_architecture_validators_check_agent_operability_evidence(self) -> None:
        for text_name, text in (
            ("claude", self.architecture_validator),
            ("codex", self.codex_architecture_validator),
        ):
            for needle in (
                "Agent Operability",
                "module responsibility",
                "Agent Workability",
                "edit target",
                "state owner",
                "validation path",
            ):
                with self.subTest(text=text_name, needle=needle):
                    self.assertIn(needle, text)


class AgentOperabilityEvalCaseTests(unittest.TestCase):
    def test_behavior_eval_bad_good_pair_exists(self) -> None:
        bad = ROOT / "evals" / "cases" / "flow-ownership-entrypoint-bad"
        good = ROOT / "evals" / "cases" / "flow-ownership-owner-good"

        for case_dir in (bad, good):
            for name in ("prompt.md", "expected.md", "diff.md", "impl.md"):
                with self.subTest(case=case_dir.name, file=name):
                    self.assertTrue((case_dir / name).is_file())

        bad_expected = (bad / "expected.md").read_text(encoding="utf-8")
        good_expected = (good / "expected.md").read_text(encoding="utf-8")
        self.assertIn("[MUST]", bad_expected)
        self.assertIn("[MUST_NOT]", good_expected)


if __name__ == "__main__":
    unittest.main()

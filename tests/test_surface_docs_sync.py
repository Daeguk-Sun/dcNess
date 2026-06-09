"""Surface documentation sync tests for the current public lifecycle."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE = ("/spec", "/design", "/impl", "/acceptance")
REMOVED_WORKFLOW = ("/product-plan", "/architect-loop")
SUPPORT = ("/to-issue",)
REMOVED = ("/issue-report",)


class SurfaceDocsSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.router = (ROOT / "docs" / "plugin" / "workflow-router.md").read_text(
            encoding="utf-8"
        )
        self.positioning = (ROOT / "docs" / "plugin" / "positioning.md").read_text(
            encoding="utf-8"
        )
        self.init_doc = (ROOT / "commands" / "init-dcness.md").read_text(
            encoding="utf-8"
        )
        self.efficiency_skill = (ROOT / "commands" / "efficiency.md").read_text(
            encoding="utf-8"
        )
        self.run_review_skill = (ROOT / "commands" / "run-review.md").read_text(
            encoding="utf-8"
        )
        self.issue_lifecycle = (
            ROOT / "docs" / "plugin" / "issue-lifecycle.md"
        ).read_text(encoding="utf-8")
        self.spec_skill = (ROOT / "skills" / "spec" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.spec_routing = (ROOT / "skills" / "spec" / "spec-routing.md").read_text(
            encoding="utf-8"
        )
        self.spec_prd_reference = (
            ROOT / "skills" / "spec" / "spec-prd-reference.md"
        ).read_text(encoding="utf-8")
        self.spec_stories_reference = (
            ROOT / "skills" / "spec" / "spec-stories-reference.md"
        ).read_text(encoding="utf-8")
        self.spec_delivery_reference = (
            ROOT / "skills" / "spec" / "spec-delivery-reference.md"
        ).read_text(encoding="utf-8")
        self.design_skill = (ROOT / "skills" / "design" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.design_routing = (
            ROOT / "skills" / "design" / "design-routing.md"
        ).read_text(encoding="utf-8")
        self.impl_skill = (ROOT / "skills" / "impl" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.impl_routing = (
            ROOT / "skills" / "impl" / "impl-routing.md"
        ).read_text(encoding="utf-8")
        self.impl_loop_skill = (
            ROOT / "skills" / "impl-loop" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.tech_review_skill = (
            ROOT / "skills" / "tech-review" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.tech_review_routing = (
            ROOT / "skills" / "tech-review" / "tech-review-routing.md"
        ).read_text(encoding="utf-8")
        self.ux_routing = (ROOT / "skills" / "ux" / "ux-routing.md").read_text(
            encoding="utf-8"
        )
        self.loop_procedure = (
            ROOT / "docs" / "plugin" / "loop-procedure.md"
        ).read_text(encoding="utf-8")
        self.hooks_doc = (ROOT / "docs" / "plugin" / "hooks.md").read_text(
            encoding="utf-8"
        )
        self.cross_ref_script = (ROOT / "scripts" / "check_cross_refs.mjs").read_text(
            encoding="utf-8"
        )

    def test_removed_alias_skill_directories_do_not_exist(self) -> None:
        self.assertFalse((ROOT / "skills" / "product-plan").exists())
        self.assertFalse((ROOT / "skills" / "architect-loop").exists())

    def test_module_design_principles_are_agent_shared_not_plugin_surface(self) -> None:
        plugin_path = ROOT / "docs" / "plugin" / "module-design-principles.md"
        shared_path = ROOT / "agents" / "_shared" / "module-design-principles.md"

        self.assertFalse(plugin_path.exists())
        self.assertTrue(shared_path.exists())

        for rel_path in (
            "agents/system-architect/system-architect-agent.md",
            "agents/module-architect/module-architect-agent.md",
            "agents/engineer/engineer-agent.md",
            "agents/test-engineer/test-engineer-agent.md",
            "agents/build-worker/build-worker-agent.md",
            "agents/architecture-validator/architecture-validator-agent.md",
        ):
            text = (ROOT / rel_path).read_text(encoding="utf-8")
            self.assertIn("../_shared/module-design-principles.md", text)
            self.assertNotIn("../../docs/plugin/module-design-principles.md", text)

    def test_user_facing_docs_use_korean_operating_principle_wording(self) -> None:
        docs = (
            ROOT / "CLAUDE.md",
            ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md",
            ROOT / "docs" / "plugin" / "workflow-router.md",
            ROOT / "docs" / "plugin" / "positioning.md",
            ROOT / "docs" / "plugin" / "parallel-policy.md",
        )
        for path in docs:
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"\b[Dd]octrine\b|독트린")

        self.assertIn("운영 원칙", self.router)
        self.assertIn("운영 원칙", self.positioning)

    def test_readme_uses_lifecycle_defaults_without_compat_aliases(self) -> None:
        basic_table = self._section(self.readme, r"\| 기본 진입점 \|", r"\n`/impl`")
        for name in LIFECYCLE:
            self.assertIn(f"| `{name}` |", basic_table)
        for name in REMOVED_WORKFLOW + SUPPORT:
            self.assertNotIn(f"| `{name}` |", basic_table)

        public_surface = self._section(self.readme, r"## Public Surface", r"\n12개 sub-agent")
        for name in LIFECYCLE:
            self.assertIn(f"| 기본 workflow | `{name}` |", public_surface)
        for name in REMOVED_WORKFLOW:
            self.assertNotIn(f"`{name}`", public_surface)
        for name in SUPPORT:
            self.assertIn(f"| support | `{name}` |", public_surface)
        for name in REMOVED:
            self.assertNotIn(f"`{name}`", public_surface)

        self.assertIn("`/spec -> /design -> /impl -> /acceptance`", self.readme)
        self.assertIn("`/spec -> /design -> /impl -> /acceptance`", self.positioning)
        self.assertIn("기본/support/고급/유틸리티/내부 agent 분류", self.readme)
        self.assertNotIn("호환 workflow", self.readme)
        self.assertNotIn("호환 alias", self.readme)
        self.assertIn("`/impl` 이 내부적으로 Lite / Standard / Deep lane", self.readme)

    def test_init_summary_uses_same_lifecycle_surface(self) -> None:
        default_block = self._section(
            self.init_doc, r"기본 workflow:\n", r"\n\nsupport:"
        )
        support_block = self._section(
            self.init_doc, r"support:\n", r"\n\n고급 workflow:"
        )
        advanced_block = self._section(
            self.init_doc, r"고급 workflow:\n", r"\n\n유틸리티:"
        )

        for name in LIFECYCLE:
            self.assertIn(f"- {name} ", default_block)
        for name in REMOVED_WORKFLOW + SUPPORT:
            self.assertNotIn(f"- {name} ", default_block)
        self.assertIn("- /spec — PRD / Epic / Story / AC", default_block)

        for name in SUPPORT:
            self.assertIn(f"- {name} ", support_block)
        for name in ("/tech-review", "/impl-loop", "/ux"):
            self.assertIn(f"- {name} ", advanced_block)
        for name in REMOVED_WORKFLOW + REMOVED:
            self.assertNotIn(f"- {name} ", self.init_doc)
        self.assertNotIn("호환 workflow", self.init_doc)
        self.assertNotIn("호환 alias", self.init_doc)

    def test_public_wrapper_docs_treat_lifecycle_surface_as_current(self) -> None:
        for text in (self.spec_skill, self.design_skill):
            self.assertIn("/spec -> /design -> /impl -> /acceptance", text)
            self.assertNotIn("후속 #645", text)
            self.assertNotIn("future", text)

        for text in (self.efficiency_skill, self.run_review_skill):
            self.assertIn("/spec", text)
            self.assertNotIn("/product-plan", text)

    def test_cross_ref_gate_agent_count_label_matches_public_surface(self) -> None:
        self.assertIn("현재 12 종", self.cross_ref_script)
        self.assertIn(r"agent\s+1[013]\s*종", self.cross_ref_script)
        self.assertIn(r"1[013]\s*개\s+(?:sub-)?agent", self.cross_ref_script)
        self.assertIn(r"1[013]\s+agents?", self.cross_ref_script)
        self.assertIn("13개 agent/sub-agent", self.cross_ref_script)
        self.assertNotIn(r"agent\s+1[0-2]\s*종", self.cross_ref_script)
        self.assertNotIn("현재 13 종", self.cross_ref_script)

    def test_strict_conveyor_docs_use_current_entrypoints(self) -> None:
        expected = "entry_point=design|impl|ux"
        for text in (self.hooks_doc, self.loop_procedure):
            self.assertIn(expected, text)
            self.assertIn("정상 `/design` 은 `begin-run design`", text)
            self.assertNotIn("entry_point=architect-loop", text)
            self.assertNotIn("entry_point=design|design", text)
            self.assertNotIn("begin-run architect-loop", text)

    def test_hooks_doc_tracks_registered_enforcement_layers(self) -> None:
        hooks_json = json.loads(
            (ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8")
        )
        runtime_hooks: set[str] = set()
        for entries in hooks_json["hooks"].values():
            for entry in entries:
                for hook in entry.get("hooks", []):
                    command = hook.get("command", "")
                    match = re.search(r"/hooks/([A-Za-z0-9_.-]+\.sh)", command)
                    self.assertIsNotNone(match, command)
                    runtime_hooks.add(match.group(1))

        self.assertEqual(8, len(runtime_hooks))
        for hook_name in sorted(runtime_hooks):
            self.assertIn(f"### {hook_name}", self.hooks_doc)
            self.assertRegex(
                self.hooks_doc,
                rf"\| `{re.escape(hook_name)}` \|",
                msg=f"{hook_name} missing from CC hook summary table",
            )

        git_hooks = set(
            re.findall(r'scripts/hooks/([A-Za-z0-9_.-]+)"', self.init_doc)
        )
        self.assertEqual({"commit-msg", "post-checkout", "pre-push"}, git_hooks)
        for hook_name in sorted(git_hooks):
            self.assertIn(f"### .git/hooks/{hook_name}", self.hooks_doc)
            self.assertIn(f"`scripts/hooks/{hook_name}`", self.hooks_doc)

        workflows = set(
            re.findall(
                r"다음 thin yml 을 `\$PROJECT_ROOT/\.github/workflows/"
                r"([A-Za-z0-9_.-]+\.yml)`",
                self.init_doc,
            )
        )
        self.assertEqual(
            {
                "git-naming-validation.yml",
                "github-project-lifecycle.yml",
                "pr-body-validation.yml",
            },
            workflows,
        )
        for workflow_name in sorted(workflows):
            workflow_path = f".github/workflows/{workflow_name}"
            self.assertIn(f"### {workflow_path}", self.hooks_doc)
            self.assertRegex(
                self.hooks_doc,
                rf"\| `{re.escape(workflow_path)}` \|",
                msg=f"{workflow_path} missing from CI/CD summary table",
            )

    def test_workflow_router_uses_design_surface_without_breaking_lite_impl(self) -> None:
        self.assertIn("/spec -> /design -> /impl -> /acceptance", self.router)
        self.assertIn("/spec -> /design -> /impl -> /acceptance", self.positioning)
        for text in (self.router, self.positioning):
            self.assertNotIn("`/design` (`/architect-loop` 호환)", text)
            self.assertNotIn("`/product-plan` 호환", text)
            self.assertNotIn("architect-loop", text)

        self.assertIn(
            "Deep: /spec 내부 tech-review preflight? → /design → /impl → /acceptance",
            self.router,
        )
        self.assertIn(
            "`/spec` 내부 tech-review preflight 필요 시 / `/design` / `/impl` / `/acceptance` 흐름",
            self.positioning,
        )
        self.assertIn("Lite: /impl direct PR", self.router)
        self.assertIn("Lite (`/impl` 직접)", self.router)
        self.assertIn(
            "concrete signal 로 보고 `/impl`, `/design`, `/spec`, `/ux` 등",
            self.router,
        )

    def test_internal_routing_docs_prefer_lifecycle_names(self) -> None:
        self.assertIn("`/spec` / `/design` / `/impl-loop`", self.impl_skill)
        self.assertIn("없으면 `/spec` 또는 `/design` 선행", self.impl_skill)
        self.assertIn('PLAN["/spec 또는 /design"]', self.impl_routing)
        self.assertIn("없으면 `/spec` / `/tech-review` / `/design` 선행", self.impl_routing)
        self.assertIn(
            "spec / design 단계 → `/spec` (PRD) 또는 `/design` (설계)",
            self.impl_loop_skill,
        )

        self.assertIn(
            "기술 검토 필요 영역에 항목이 있으면 `/tech-review` preflight → PRD 최종화 → stories.md → SPEC_ACCEPTANCE → PR 머지 → 이슈 등록 여부 확인 → `/design`",
            self.spec_routing,
        )
        self.assertIn("PR 머지 → 이슈 등록 여부 확인 → `/design`", self.spec_routing)
        self.assertIn("이슈 등록 보류 marker 기록/머지 후 Step 12", self.spec_routing)
        self.assertNotIn("PR 머지 + 이슈 등록", self.spec_routing)
        self.assertIn("spec-prd-reference.md", self.spec_skill)
        self.assertIn("spec-stories-reference.md", self.spec_skill)
        self.assertIn("spec-delivery-reference.md", self.spec_skill)
        self.assertIn("PRD 산출물 의무", self.spec_prd_reference)
        self.assertIn("stories.md 산출물", self.spec_stories_reference)
        self.assertIn("# Story Backlog", self.spec_stories_reference)
        self.assertIn(
            "# preflight 를 실행했다면: git add docs/tech-review.md docs/tech-review/",
            self.spec_delivery_reference,
        )

        self.assertIn("`/spec` 의 후속", self.design_skill)
        self.assertIn("`/spec` 종료 후", self.design_skill)
        self.assertIn("`/spec` Step 10 결과", self.design_skill)
        self.assertIn("미충족 시 → `/spec` 재진입 권고", self.design_skill)
        self.assertIn("PRD 신규 / 변경 → `/spec`", self.design_skill)
        self.assertIn("사용자(`/spec` 재진입)", self.design_routing)
        self.assertIn("`ESCALATE` → `/spec` 재진입", self.design_routing)
        self.assertIn("`/design` 중단 + `/spec` 재진입", self.design_routing)

        self.assertIn("`/spec` 도중 PRD 최종화 전에", self.tech_review_skill)
        self.assertIn("`/design` 진입 후", self.tech_review_skill)
        self.assertIn("OK → `/spec` Step 5 PRD 최종화", self.tech_review_routing)
        self.assertIn("`/design` 진입 *후*", self.tech_review_routing)
        self.assertIn("`/design` 중단 + `/spec` 재진입", self.tech_review_routing)
        self.assertIn("PRD 미작성 / 기술 검토 필요 영역 부재 → `/spec` 먼저", self.tech_review_routing)
        self.assertIn("tech-review 통과 + 사용자 OK → `/spec` Step 5 로 복귀해 PRD 최종화", self.tech_review_routing)

        self.assertIn(
            "PRD 범위 문제면 메인 `/spec` 재진입 권고",
            self.ux_routing,
        )
        self.assertIn("`**GitHub Issue:** 미등록 (사유: …)`", self.issue_lifecycle)

        for text in (
            self.impl_skill,
            self.impl_routing,
            self.impl_loop_skill,
            self.spec_skill,
            self.spec_routing,
            self.design_skill,
            self.design_routing,
            self.tech_review_skill,
            self.tech_review_routing,
            self.ux_routing,
        ):
            self.assertNotIn("`/product-plan`", text)
            self.assertNotIn("`/architect-loop`", text)
            self.assertNotIn("호환 alias", text)

    def _section(self, text: str, start: str, end: str) -> str:
        match = re.search(start + r"(?P<body>.*?)" + end, text, flags=re.S)
        self.assertIsNotNone(match)
        return match.group("body")


if __name__ == "__main__":
    unittest.main()

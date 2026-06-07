"""Surface documentation sync tests for issues #644/#645."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE = ("/spec", "/design", "/impl", "/acceptance")
COMPAT = ("/product-plan", "/architect-loop")
SUPPORT = ("/issue-report",)


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
        self.spec_skill = (ROOT / "skills" / "spec" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.design_skill = (ROOT / "skills" / "design" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.architect_loop_skill = (
            ROOT / "skills" / "architect-loop" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.architect_loop_routing = (
            ROOT / "skills" / "architect-loop" / "architect-loop-routing.md"
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
        self.issue_report_routing = (
            ROOT / "skills" / "issue-report" / "issue-report-routing.md"
        ).read_text(encoding="utf-8")
        self.product_plan_routing = (
            ROOT / "skills" / "product-plan" / "product-plan-routing.md"
        ).read_text(encoding="utf-8")
        self.product_plan_skill = (
            ROOT / "skills" / "product-plan" / "SKILL.md"
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

    def test_readme_uses_lifecycle_defaults_and_separate_legacy_surface(self) -> None:
        basic_table = self._section(self.readme, r"\| 기본 진입점 \|", r"\n`/impl`")
        for name in LIFECYCLE:
            self.assertIn(f"| `{name}` |", basic_table)
        for name in COMPAT + SUPPORT:
            self.assertNotIn(f"| `{name}` |", basic_table)

        public_surface = self._section(self.readme, r"## Public Surface", r"\n13개 sub-agent")
        for name in LIFECYCLE:
            self.assertIn(f"| 기본 workflow | `{name}` |", public_surface)
        for name in COMPAT:
            self.assertIn(f"| 호환 workflow | `{name}` |", public_surface)
        for name in SUPPORT:
            self.assertIn(f"| support/triage | `{name}` |", public_surface)
        self.assertIn("`/spec -> /design -> /impl -> /acceptance`", self.readme)
        self.assertIn("`/spec -> /design -> /impl -> /acceptance`", self.positioning)
        self.assertIn("기본/호환/support/triage/고급/유틸리티/내부 agent 분류", self.readme)
        self.assertIn("Lite", self.readme)
        self.assertIn("`/impl` 이 내부적으로 Lite / Standard / Deep lane", self.readme)

    def test_public_wrapper_docs_treat_lifecycle_surface_as_current(self) -> None:
        for text in (self.spec_skill, self.design_skill):
            self.assertIn("/spec -> /design -> /impl -> /acceptance", text)
            self.assertNotIn("후속 #645", text)
            self.assertNotIn("future", text)

    def test_cross_ref_gate_agent_count_label_matches_public_surface(self) -> None:
        self.assertIn("현재 13 종", self.cross_ref_script)
        self.assertIn(r"agent\s+1[0-2]\s*종", self.cross_ref_script)
        self.assertNotIn(r"agent\s+1[01]\s*종", self.cross_ref_script)
        self.assertNotIn("현재 12 종", self.cross_ref_script)

    def test_strict_conveyor_docs_include_design_alias_guard(self) -> None:
        expected = "entry_point=architect-loop|design|impl|issue-report|ux"
        self.assertIn(expected, self.hooks_doc)
        self.assertIn(expected, self.loop_procedure)
        self.assertIn("정상 `/design` 은 `begin-run architect-loop`", self.hooks_doc)
        self.assertIn("실수로 `begin-run design`", self.hooks_doc)
        self.assertNotIn("entry_point=architect-loop|impl|issue-report|ux", self.hooks_doc)
        self.assertNotIn("entry_point=architect-loop|impl|issue-report|ux", self.loop_procedure)

    def test_init_summary_uses_same_lifecycle_surface(self) -> None:
        default_block = self._section(
            self.init_doc, r"기본 workflow:\n", r"\n\n호환 workflow:"
        )
        compat_block = self._section(
            self.init_doc, r"호환 workflow:\n", r"\n\nsupport/triage:"
        )
        support_block = self._section(
            self.init_doc, r"support/triage:\n", r"\n\n고급 workflow:"
        )
        advanced_block = self._section(
            self.init_doc, r"고급 workflow:\n", r"\n\n유틸리티:"
        )

        for name in LIFECYCLE:
            self.assertIn(f"- {name} ", default_block)
        for name in COMPAT + SUPPORT:
            self.assertNotIn(f"- {name} ", default_block)
        self.assertIn("- /spec — PRD / Epic / Story / AC", default_block)
        self.assertNotIn("- /spec — 새 기능 spec/design", default_block)

        for name in COMPAT:
            self.assertIn(f"- {name} ", compat_block)
        for name in SUPPORT:
            self.assertIn(f"- {name} ", support_block)
        for name in ("/tech-review", "/impl-loop", "/ux"):
            self.assertIn(f"- {name} ", advanced_block)
        self.assertNotIn("- /acceptance ", advanced_block)

    def test_workflow_router_uses_design_surface_without_breaking_lite_impl(self) -> None:
        self.assertIn("/spec -> /design -> /impl -> /acceptance", self.router)
        self.assertIn("/spec -> /design -> /impl -> /acceptance", self.positioning)
        self.assertIn("`/design` (`/architect-loop` 호환)", self.router)
        self.assertIn("Deep: /spec → tech-review? → /design → /impl → /acceptance", self.router)
        self.assertIn(
            "`/spec` / `/tech-review` 필요 시 / `/design` / `/impl` / `/acceptance` 흐름",
            self.positioning,
        )
        self.assertNotIn("기존 PRD / tech-review / architect-loop", self.positioning)
        self.assertIn(
            "`/spec` → `/tech-review` 필요 시 → `/design` → `/impl` → `/acceptance`",
            self.router,
        )
        self.assertIn(
            "`/spec` → `/tech-review` → `/design` → `/impl` → `/acceptance` full chain",
            self.router,
        )
        self.assertIn("Lite: /impl direct PR", self.router)
        self.assertIn("Lite (`/impl` 직접)", self.router)
        self.assertNotIn("Deep `/architect-loop` 승격", self.router)
        self.assertIn(
            "concrete signal 로 보고 `/impl`, `/design`, `/spec`, `/ux` 등",
            self.router,
        )

    def test_internal_routing_docs_prefer_lifecycle_names_with_compat_aliases(self) -> None:
        self.assertIn("`/spec` / `/design` / `/impl-loop`", self.impl_skill)
        self.assertIn("없으면 `/spec` 또는 `/design` 선행", self.impl_skill)
        self.assertNotIn("`/product-plan` / `/architect-loop` / `/impl-loop`", self.impl_skill)

        self.assertIn('PLAN["/spec 또는 /design"]', self.impl_routing)
        self.assertIn("없으면 `/spec` / `/tech-review` / `/design` 선행", self.impl_routing)
        self.assertNotIn("PLAN[\"/product-plan 또는 /architect-loop\"]", self.impl_routing)

        self.assertIn(
            "spec / design 단계 → `/spec` (PRD) 또는 `/design` (설계)",
            self.impl_loop_skill,
        )
        self.assertNotIn(
            "spec / design 단계 → `/product-plan` (PRD) 또는 `/architect-loop` (설계)",
            self.impl_loop_skill,
        )

        self.assertIn("`/spec` 또는 `/design` 재진입 후보", self.issue_report_routing)
        self.assertNotIn("`/product-plan` 또는 `/architect-loop` 재진입 후보", self.issue_report_routing)

        self.assertIn(
            "`/tech-review` → `/design` (`/architect-loop` 호환) → `/impl` → `/acceptance`",
            self.product_plan_routing,
        )
        self.assertIn(
            "`/tech-review` → `/design` (`/architect-loop` 호환) → `/impl` → `/acceptance`",
            self.product_plan_skill,
        )
        self.assertIn(
            "사용자 trigger (`/tech-review` 또는 `/design`; `/architect-loop` 호환)",
            self.product_plan_routing,
        )
        self.assertIn(
            "작업 중단 + `/spec` 재진입 권고 (`/product-plan` 호환)",
            self.product_plan_routing,
        )
        self.assertNotIn("작업 중단 + `/product-plan` 재진입 권고", self.product_plan_routing)
        self.assertNotIn(
            "`/tech-review` → `/architect-loop` → `/impl`",
            self.product_plan_routing,
        )
        self.assertNotIn(
            "`/tech-review` → `/architect-loop` → `/impl`",
            self.product_plan_skill,
        )
        self.assertIn(
            "`docs/milestones/vNN/epics/epic-NN-<slug>/stories.md` — Epic + N Story",
            self.product_plan_skill,
        )
        self.assertIn(
            "`docs/prd.md` + epic 단위 `docs/milestones/vNN/epics/epic-NN-<slug>/stories.md` + `docs/tech-review.md`",
            self.product_plan_skill,
        )
        self.assertIn(
            "docs/prd.md docs/milestones/vNN/epics/epic-NN-<slug>/stories.md docs/tech-review.md",
            self.product_plan_skill,
        )
        self.assertNotIn("`docs/stories.md` — Epic + N Story", self.product_plan_skill)
        self.assertNotIn("`docs/stories.md`", self.product_plan_skill)
        self.assertNotIn("git add docs/prd.md docs/stories.md", self.product_plan_skill)

        self.assertIn(
            "`/design` (`/architect-loop` 호환)",
            self.loop_procedure,
        )
        self.assertIn(
            "`/spec` (`/product-plan` 호환)",
            self.loop_procedure,
        )
        self.assertIn(
            "impl / impl-loop / design(architect-loop)",
            self.loop_procedure,
        )
        self.assertIn(
            "`/design` (`/architect-loop` 호환) 진입 후 tech-reviewer 재호출 비권장",
            self.loop_procedure,
        )

        self.assertIn("`/spec` (`/product-plan` 호환) 의 후속", self.architect_loop_skill)
        self.assertIn("`/spec` (`/product-plan` 호환) 종료 후", self.architect_loop_skill)
        self.assertIn("`/spec` Step 7", self.architect_loop_skill)
        self.assertIn("미충족 시 → `/spec` 재진입 권고", self.architect_loop_skill)
        self.assertIn("PRD 신규 / 변경 → `/spec` (`/product-plan` 호환)", self.architect_loop_skill)
        self.assertNotIn("`/product-plan` 의 후속", self.architect_loop_skill)
        self.assertNotIn("본 스킬 = `/product-plan` 종료 후", self.architect_loop_skill)
        self.assertNotIn("미충족 시 → `/product-plan` 재진입 권고", self.architect_loop_skill)

        self.assertIn("사용자(`/spec` 재진입, `/product-plan` 호환)", self.architect_loop_routing)
        self.assertIn("`ESCALATE` → `/spec` 재진입", self.architect_loop_routing)
        self.assertIn("`/design` (`/architect-loop` 호환) 중단 + `/spec` (`/product-plan` 호환) 재진입", self.architect_loop_routing)
        self.assertIn("`/spec` 재진입 권고 (`/product-plan` 호환)", self.architect_loop_routing)
        self.assertNotIn("사용자(`/product-plan` 재진입)", self.architect_loop_routing)
        self.assertNotIn("`/architect-loop` 중단 + `/product-plan` 재진입", self.architect_loop_routing)
        self.assertNotIn("`/product-plan` 재진입 권고", self.architect_loop_routing)

        self.assertIn("`/spec` (`/product-plan` 호환) 종료 후", self.tech_review_skill)
        self.assertIn("`/design` (`/architect-loop` 호환) 진입 후", self.tech_review_skill)
        self.assertIn("설계 단계 진입 (`/design` 권고, `/architect-loop` 호환)", self.tech_review_skill)
        self.assertIn("Step 5 (종료 + `/design` 권고, `/architect-loop` 호환)", self.tech_review_skill)
        self.assertIn("### Step 5 — `/design` 권고 (`/architect-loop` 호환, 사용자 OK 종료)", self.tech_review_skill)
        self.assertIn("→ `/design <epic-path>` 호출 시", self.tech_review_skill)
        self.assertIn("사용자 Y → `/design` 진입 (`/architect-loop` 호환)", self.tech_review_skill)
        self.assertIn("`/spec` Step 3", self.tech_review_skill)
        self.assertIn("미충족 시 → `/spec` 권고 (`/product-plan` 호환)", self.tech_review_skill)
        self.assertNotIn("본 스킬 = `/product-plan` 종료 후", self.tech_review_skill)
        self.assertNotIn("→ /product-plan 진행 후 재진입하세요.", self.tech_review_skill)
        self.assertNotIn("(/architect-loop 권고)", self.tech_review_skill)
        self.assertNotIn("Step 5 (종료 + `/architect-loop` 권고)", self.tech_review_skill)
        self.assertNotIn("### Step 5 — `/architect-loop` 권고", self.tech_review_skill)
        self.assertNotIn("→ `/architect-loop <epic-path>`", self.tech_review_skill)
        self.assertNotIn("사용자 Y → `/architect-loop` 진입", self.tech_review_skill)
        self.assertNotIn("`/architect-loop` 진입 *후* 본 스킬 재호출", self.tech_review_skill)

        self.assertIn("OK → `/design` (`/architect-loop` 호환)", self.tech_review_routing)
        self.assertIn("`/design` (`/architect-loop` 호환) 진입 *후*", self.tech_review_routing)
        self.assertIn("`/design` (`/architect-loop` 호환) 중단 + `/spec` (`/product-plan` 호환) 재진입", self.tech_review_routing)
        self.assertIn("PRD 미작성 / 스켈레톤 부재 → `/spec` (`/product-plan` 호환) 먼저", self.tech_review_routing)
        self.assertIn("tech-review 통과 + 사용자 OK → `/design` (`/architect-loop` 호환", self.tech_review_routing)
        self.assertIn("기술 자체 폐기", self.tech_review_routing)
        self.assertIn("`/spec` 재진입 (`/product-plan` 호환", self.tech_review_routing)
        self.assertNotIn("`/architect-loop` 중단 + `/product-plan` 재진입", self.tech_review_routing)
        self.assertNotIn("PRD 미작성 / 스켈레톤 부재 → `/product-plan` 먼저", self.tech_review_routing)
        self.assertNotIn("tech-review 통과 + 사용자 OK → `/architect-loop`", self.tech_review_routing)

        self.assertIn(
            "PRD 범위 문제면 메인 `/spec` 재진입 권고 (`/product-plan` 호환)",
            self.ux_routing,
        )
        self.assertNotIn("PRD 범위 문제면 메인 `/product-plan` 재진입 권고", self.ux_routing)

    def _section(self, text: str, start: str, end: str) -> str:
        match = re.search(start + r"(?P<body>.*?)" + end, text, flags=re.S)
        self.assertIsNotNone(match)
        return match.group("body")


if __name__ == "__main__":
    unittest.main()

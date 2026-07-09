"""Canvas design SSOT workflow regression tests (#843)."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CanvasDesignWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.impl = (ROOT / "skills" / "impl" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.impl_routing = (
            ROOT / "skills" / "impl" / "impl-routing.md"
        ).read_text(encoding="utf-8")
        self.impl_loop = (
            ROOT / "skills" / "impl-loop" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.impl_loop_routing = (
            ROOT / "skills" / "impl-loop" / "impl-loop-routing.md"
        ).read_text(encoding="utf-8")
        self.ux = (ROOT / "skills" / "ux" / "SKILL.md").read_text(encoding="utf-8")
        self.ux_routing = (
            ROOT / "skills" / "ux" / "ux-routing.md"
        ).read_text(encoding="utf-8")
        self.design = (
            ROOT / "skills" / "design" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.design_routing = (
            ROOT / "skills" / "design" / "design-routing.md"
        ).read_text(encoding="utf-8")
        self.spec_routing = (
            ROOT / "skills" / "spec" / "spec-routing.md"
        ).read_text(encoding="utf-8")
        self.designer = (
            ROOT / "docs" / "plugin" / "agents" / "designer" / "designer-agent.md"
        ).read_text(encoding="utf-8")
        self.ux_architect = (
            ROOT / "docs" / "plugin" / "agents" / "ux-architect" / "ux-architect-agent.md"
        ).read_text(encoding="utf-8")
        self.ux_flow_template = (
            ROOT / "docs" / "plugin" / "agents" / "ux-architect" / "templates" / "ux-flow.md"
        ).read_text(encoding="utf-8")
        self.engineer = (
            ROOT / "docs" / "plugin" / "agents" / "engineer" / "engineer-agent.md"
        ).read_text(encoding="utf-8")
        self.build_worker = (
            ROOT / "docs" / "plugin" / "agents" / "build-worker" / "build-worker-agent.md"
        ).read_text(encoding="utf-8")
        self.impl_template = (
            ROOT / "docs" / "plugin" / "agents" / "module-architect" / "templates" / "impl-task.md"
        ).read_text(encoding="utf-8")
        self.init_skill = (ROOT / "commands" / "init-dcness.md").read_text(
            encoding="utf-8"
        )
        self.init_ref = (
            ROOT / "docs" / "plugin" / "init-dcness.md"
        ).read_text(encoding="utf-8")
        self.loop_procedure = (
            ROOT / "docs" / "plugin" / "loop-procedure.md"
        ).read_text(encoding="utf-8")
        self.positioning = (
            ROOT / "docs" / "plugin" / "positioning.md"
        ).read_text(encoding="utf-8")
        self.public_surface = (
            ROOT / "scripts" / "check_public_surface.mjs"
        ).read_text(encoding="utf-8")
        self.doc_path_integrity = (
            ROOT / "scripts" / "check_doc_path_integrity.mjs"
        ).read_text(encoding="utf-8")
        self.tdd_guard = (ROOT / "hooks" / "tdd-guard.sh").read_text(
            encoding="utf-8"
        )

    def test_canvas_design_is_internal_skill_and_single_promotion_path(self) -> None:
        skill_path = ROOT / "skills" / "canvas-design" / "SKILL.md"
        self.assertTrue(skill_path.is_file())
        skill = skill_path.read_text(encoding="utf-8")

        for needle in (
            "공개 진입점이 아니다",
            "docs/design-variants/",
            "docs/design-variants/drafts/",
            "seed 보장",
            "templates/design-variants/",
            "부재 시만",
            "canvas.html",
            "<screen-id>.html",
            "사용자 PICK",
            "확정본 승격",
            "canvas frame 등록",
            "PASS",
            "ESCALATE",
            "helper begin/end-step 비대상",
            "begin-step designer",
            "designer 는 drafts",
            "메인",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, skill)

        self.assertIn("canvas-design", self.impl)
        self.assertIn("canvas-design", self.impl_loop)
        self.assertNotIn("/canvas-design", self.positioning)

        defaults = self._array(self.public_surface, "defaultSkills")
        advanced = self._array(self.public_surface, "advancedSkills")
        utility_skills = self._array(self.public_surface, "utilitySkills")
        internal = self._array(self.public_surface, "internalSkills")
        self.assertEqual(["spec", "design", "impl", "acceptance"], defaults)
        self.assertEqual(["impl-loop", "tech-review"], advanced)
        self.assertEqual(["ux"], utility_skills)
        self.assertEqual(
            ["canvas-design", "design-system", "design-ux"],
            sorted(internal),
        )

    def test_ux_is_thin_canvas_design_wrapper_with_confirmed_outputs(self) -> None:
        for needle in (
            "얇은 wrapper",
            "canvas-design",
            "구현 없이 디자인만",
            "drafts 반복",
            "사용자 PICK",
            "확정본 승격",
            "canvas 등록",
            "docs/design-variants/<screen-id>.html",
            "docs/design-variants/canvas.html",
            "후속 `/impl` 은 머지된 확정본만 `기준 있음`",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.ux)

        for stale in ("DESIGN_HANDOFF", "이슈 코멘트", "독자 handoff", "자체 승격 절차"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, self.ux)

    def test_ux_natural_language_routes_design_baseline_requests(self) -> None:
        """#957 — design system/baseline requests route to /ux instead of ad-hoc docs."""
        for needle in ("디자인 시스템", "디자인 토큰", "베이스라인"):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.ux)

    def test_ux_flow_inventory_tracks_mockup_need_and_confirmed_path(self) -> None:
        for text in (self.ux_architect, self.ux_flow_template):
            with self.subTest(text=text[:30]):
                self.assertIn("hi-fi 목업 필요", text)
                self.assertIn("필요/불필요", text)
                self.assertIn("확정 목업 경로", text)

        self.assertIn(
            "| 화면 ID | 화면명 | 역할 | PRD 근거 | hi-fi 목업 필요 | 확정 목업 경로 | 우선순위 |",
            self.ux_flow_template,
        )
        self.assertIn("확정본 없음", self.ux_flow_template)

        for text in (self.ux, self.designer):
            with self.subTest(text=text[:30]):
                self.assertIn("hi-fi 목업 필요", text)
                self.assertIn("필요로 표시된 화면", text)
                self.assertNotIn("필요 로 표시된 화면", text)
                self.assertIn("전 화면 일괄 목업화 금지", text)

        self.assertNotIn("필요 로 표시된 화면", self.ux_architect)

    def test_ux_standalone_run_commits_confirmed_artifacts_via_pr(self) -> None:
        for needle in (
            "`/impl` · `/impl-loop` · `/design` · `/ux`",
            "EnterWorktree(name=\"<skill>-{ts_short}\")",
            "impl / impl-loop / design / ux",
            "`/impl`·`/impl-loop`·`/design`·`/ux` action loop",
            "`/spec` / `/tech-review` / `/to-issue` (commit 없음)",
            "ux = epic `ux-flow.md`, `docs/design.md`, "
            "`docs/design-variants/<screen-id>.html`, "
            "`docs/design-variants/canvas.html`",
            "해당 loop 산출물만 명시 pathspec",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.loop_procedure)

        self.assertNotIn(
            "`/spec` / `/tech-review` / `/ux` / `/to-issue` (commit 없음)",
            self.loop_procedure,
        )

        for needle in (
            "worktree",
            "commit/PR",
            "docs-only branch + PR",
            "후속 `/impl` 은 머지된 확정본만 `기준 있음` 으로 이어받는다",
            "merge",
            "main sync",
            "확정본을 uncommitted 상태로 남긴 채 종료하지 않는다",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.ux)

    def test_canvas_design_bootstraps_seed_and_requires_routing_enum(self) -> None:
        skill = (ROOT / "skills" / "canvas-design" / "SKILL.md").read_text(
            encoding="utf-8"
        )

        for needle in (
            "docs/design-variants/_lib/show-ids.js",
            "docs/design-variants/_lib/canvas.js",
            "docs/design-variants/canvas.html",
            "docs/design-variants/drafts/.gitkeep",
            "templates/design-variants/.gitignore",
            "templates/design-variants/_lib/show-ids.js",
            "templates/design-variants/_lib/canvas.js",
            "templates/design-variants/canvas.html",
            "templates/design-variants/drafts/.gitkeep",
            "덮어쓰지 않는다",
            "마지막 단락",
            "PASS",
            "ESCALATE",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, skill)

        escalate_line = next(
            line for line in skill.splitlines() if line.startswith("- `ESCALATE`")
        )
        self.assertNotIn("사용자 PICK 대기", escalate_line)
        self.assertIn("사용자 PICK 대기 중에는 routed conclusion", skill)

    def test_canvas_design_is_main_owned_not_strict_agent_step(self) -> None:
        for text in (self.impl_loop, self.impl_loop_routing):
            with self.subTest(doc=text[:30]):
                self.assertIn("main-owned", text)
                self.assertIn("helper begin/end-step 비대상", text)
                self.assertIn("begin-step designer", text)
                self.assertNotIn("begin-step canvas-design", text)

    def test_impl_has_three_way_visual_baseline_branch_and_echo(self) -> None:
        for text in (self.impl, self.impl_routing):
            with self.subTest(file=text[:20]):
                self.assertIn("UI 기준 확보 분기", text)
                self.assertIn("기준 있음", text)
                self.assertIn("신규 시각 구조 + 기준 없음", text)
                self.assertIn("시각 구조 불변", text)
                self.assertIn("목업 없이", text)
                self.assertIn("UI 기준:", text)
                self.assertIn("사용자 제공 이미지", text)
                self.assertIn("기존 확정본", text)

    def test_impl_loop_uses_canvas_design_independent_of_engine(self) -> None:
        for needle in (
            "engine 무관",
            "canvas-design",
            "build-worker-deep",
            "docs/design-variants/<screen-id>.html",
            "build-worker",
            "풀 4-agent",
            "확정본 승격",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.impl_loop)
        self.assertNotIn("풀 4-agent 엔진 한정", self.impl_loop)

    def test_design_reference_contract_is_in_impl_template(self) -> None:
        self.assertIn("design: optional|required", self.impl_template)
        self.assertIn("## 디자인 참조", self.impl_template)
        self.assertIn("확정 목업 경로", self.impl_template)
        self.assertIn("data-node-id", self.impl_template)
        self.assertIn("구현 컴포넌트", self.impl_template)

    def test_agents_use_confirmed_mockup_as_design_alignment_axis(self) -> None:
        for text in (self.engineer, self.build_worker):
            with self.subTest(agent=text[:30]):
                self.assertIn("디자인 정합", text)
                self.assertIn("docs/design-variants/<screen-id>.html", text)
                self.assertIn("레이아웃 계층", text)
                self.assertIn("상태", text)
                self.assertIn("토큰", text)
                self.assertIn("의도적 차이", text)

        self.assertIn("docs/design-variants/drafts/", self.designer)
        self.assertNotIn("design-variants/<screen>-v<N>.html", self.designer)

    def test_init_dcness_deploys_docs_design_variants_seed_and_redeploy_notice(
        self,
    ) -> None:
        for text in (self.init_skill, self.init_ref):
            with self.subTest(doc=text[:30]):
                self.assertIn("docs/design-variants/", text)
                self.assertIn("docs/design-variants/drafts/", text)
                self.assertIn("canvas.html", text)
                self.assertIn("기존 활성 프로젝트", text)
        self.assertNotIn('TARGET="$PROJECT_ROOT/design-variants/$FILE"', self.init_skill)
        self.assertTrue((ROOT / "templates" / "design-variants" / ".gitignore").is_file())
        self.assertTrue(
            (ROOT / "templates" / "design-variants" / "drafts" / ".gitkeep").is_file()
        )

    def test_support_gates_treat_docs_design_variants_as_canonical_path(self) -> None:
        self.assertIn("'docs/design-variants/'", self.doc_path_integrity)
        self.assertIn("LEGACY_PATH_PREFIXES", self.doc_path_integrity)
        self.assertIn("'design-variants/'", self.doc_path_integrity)

        self.assertIn("*/docs/design-variants/*", self.tdd_guard)
        self.assertNotIn("*/design-variants/*) allow", self.tdd_guard)

    def test_every_designer_entry_seeds_design_variants_first(self) -> None:
        for needle in (
            "designer 진입 공통 preflight",
            "templates/design-variants/.gitignore",
            "templates/design-variants/canvas.html",
            "templates/design-variants/_lib/show-ids.js",
            "templates/design-variants/_lib/canvas.js",
            "templates/design-variants/drafts/.gitkeep",
            "덮어쓰지 않는다",
            "designer-ROUND",
            "UX_REFINE",
            "docs/design-variants/drafts/<screen-id>-draft<N>.html",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.ux)

        self.assertIn("design-variants seed 보장", self.ux_routing)
        self.assertIn("designer-ROUND", self.ux_routing)
        self.assertIn("UX_REFINE_READY` → design-variants seed 보장 후 designer", self.design_routing)
        self.assertIn("`docs/design-variants/` seed 보장 후 designer", self.design)
        self.assertIn("docs/design-variants/` seed 보장 후 designer", self.spec_routing)

    def test_design_seed_template_keeps_drafts_directory_materialized(self) -> None:
        gitignore = (ROOT / "templates" / "design-variants" / ".gitignore").read_text(
            encoding="utf-8"
        )

        self.assertIn("drafts/*", gitignore)
        self.assertIn("!drafts/.gitkeep", gitignore)
        self.assertTrue(
            (ROOT / "templates" / "design-variants" / "drafts" / ".gitkeep").is_file()
        )

    def test_canvas_seed_uses_confirmed_screen_paths_without_version_suffix(self) -> None:
        canvas = (ROOT / "templates" / "design-variants" / "canvas.html").read_text(
            encoding="utf-8"
        )
        html_variant = (
            ROOT / "docs" / "plugin" / "agents" / "designer" / "templates" / "html-variant.md"
        ).read_text(encoding="utf-8")

        self.assertIn('src="<screen-id>.html"', canvas)
        self.assertNotIn('src="<screen-id>-v<N>.html"', canvas)
        self.assertIn("../_lib/show-ids.js", html_variant)

    def test_canvas_seed_supports_flow_board_screen_nodes(self) -> None:
        canvas_html = (
            ROOT / "templates" / "design-variants" / "canvas.html"
        ).read_text(encoding="utf-8")
        canvas_js = (
            ROOT / "templates" / "design-variants" / "_lib" / "canvas.js"
        ).read_text(encoding="utf-8")

        for needle in (
            'class="screen-node"',
            'data-node-id="<screen-id>"',
            'data-title="',
            'data-desc="',
            'data-states="',
            'data-h="',
        ):
            with self.subTest(template=needle):
                self.assertIn(needle, canvas_html)

        for needle in (
            "querySelectorAll('.screen-node')",
            "dataset.nodeId",
            "dataset.h",
            "node-caption",
            "dataset.label",
            "data-label",
            "data-bend",
            "zoomToFit",
            "focusNode",
        ):
            with self.subTest(renderer=needle):
                self.assertIn(needle, canvas_js)

    def _array(self, text: str, key: str) -> list[str]:
        match = re.search(rf"{key}:\s*\[([^\]]*)\]", text)
        self.assertIsNotNone(match)
        return re.findall(r"'([^']+)'", match.group(1))


if __name__ == "__main__":
    unittest.main()

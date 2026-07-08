"""Documentation sync tests for the current public lifecycle."""
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
        self.init_reference = (
            ROOT / "docs" / "plugin" / "init-dcness.md"
        ).read_text(encoding="utf-8")
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
        self.agent_prompt_template = (
            ROOT / "docs" / "plugin" / "templates" / "agent-prompt-slots.md"
        ).read_text(encoding="utf-8")
        self.hooks_doc = (ROOT / "docs" / "plugin" / "hooks.md").read_text(
            encoding="utf-8"
        )
        self.terms_doc = (ROOT / "docs" / "plugin" / "terms.md").read_text(
            encoding="utf-8"
        )
        self.pr_reviewer = (
            ROOT / "docs" / "plugin" / "agents" / "pr-reviewer" / "pr-reviewer-agent.md"
        ).read_text(encoding="utf-8")
        self.architecture_validator = (
            ROOT / "docs" / "plugin" / "agents" / "architecture-validator" / "architecture-validator-agent.md"
        ).read_text(encoding="utf-8")
        self.ux_architect = (
            ROOT / "docs" / "plugin" / "agents" / "ux-architect" / "ux-architect-agent.md"
        ).read_text(encoding="utf-8")
        self.tech_reviewer = (
            ROOT / "docs" / "plugin" / "agents" / "tech-reviewer" / "tech-reviewer-agent.md"
        ).read_text(encoding="utf-8")
        self.cross_ref_script = (ROOT / "scripts" / "check_cross_refs.mjs").read_text(
            encoding="utf-8"
        )
        self.doc_sync_action = (
            ROOT / ".github" / "actions" / "doc-sync" / "action.yml"
        ).read_text(encoding="utf-8")
        self.deliverables_map = (
            ROOT / "docs" / "plugin" / "deliverables-map.md"
        ).read_text(encoding="utf-8")
        self.claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.github_project = (
            ROOT / "docs" / "plugin" / "github-project.md"
        ).read_text(encoding="utf-8")
        self.design_tokens_doc = (
            ROOT / "docs" / "plugin" / "design.md"
        ).read_text(encoding="utf-8")
        self.smart_compact = (
            ROOT / "commands" / "smart-compact.md"
        ).read_text(encoding="utf-8")
        self.branch_protection_script = (
            ROOT / "scripts" / "setup_branch_protection.mjs"
        ).read_text(encoding="utf-8")

    def test_removed_alias_skill_directories_do_not_exist(self) -> None:
        self.assertFalse((ROOT / "skills" / "product-plan").exists())
        self.assertFalse((ROOT / "skills" / "architect-loop").exists())

    def test_module_design_principles_are_agent_shared_not_plugin_surface(self) -> None:
        plugin_path = ROOT / "docs" / "plugin" / "module-design-principles.md"
        shared_path = ROOT / "docs" / "plugin" / "agents" / "_shared" / "module-design-principles.md"

        self.assertFalse(plugin_path.exists())
        self.assertTrue(shared_path.exists())

        for rel_path in (
            "docs/plugin/agents/system-architect/system-architect-agent.md",
            "docs/plugin/agents/module-architect/module-architect-agent.md",
            "docs/plugin/agents/engineer/engineer-agent.md",
            "docs/plugin/agents/test-engineer/test-engineer-agent.md",
            "docs/plugin/agents/build-worker/build-worker-agent.md",
            "docs/plugin/agents/architecture-validator/architecture-validator-agent.md",
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

    def test_user_surface_and_doc_delta_review_guidance_exists(self) -> None:
        for needle in (
            "사용자-facing 표현 원칙",
            "내부 실행 토큰은 필요할 때만",
            "하네스 내부 배관 설명은 링크나 상세 로그로 내린다",
            "검증·장애 복구·감사 맥락에서는 근거가 우선",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.terms_doc)

        for needle in (
            "문서 영향",
            "PRD / stories / architecture / decisions / module responsibility",
            "이번 diff 가 기존 장기 문서를 무효화했는지",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.pr_reviewer)

    def test_project_registration_mechanics_have_single_owner(self) -> None:
        """#853 — GitHub Project axis doc points to lifecycle mechanics instead of restating them."""
        self.assertIn(
            "node scripts/github_project_lifecycle.mjs register-issue",
            self.issue_lifecycle,
        )
        self.assertIn(
            "GitHub Project v2 보드는 선택적 사람용 파생 뷰",
            self.issue_lifecycle,
        )
        self.assertNotIn(
            "issue-lifecycle.md#github-project-status-lifecycle",
            self.github_project,
        )
        self.assertNotIn(
            "node scripts/github_project_lifecycle.mjs register-issue",
            self.github_project,
        )
        self.assertIn("issue-lifecycle.md#issuelabel-status-lifecycle", self.github_project)
        self.assertNotIn("좌표(owner/number)", self.spec_delivery_reference)
        self.assertIn(
            "issue-lifecycle.md#issuelabel-status-lifecycle",
            self.spec_delivery_reference,
        )

    def test_workflow_router_owns_impl_lane_conditions(self) -> None:
        """#853 — positioning owns public surface; workflow-router owns Lite/Standard conditions."""
        self.assertIn("## 구현 경로 표", self.router)
        self.assertIn("concrete signal", self.router)
        self.assertNotIn("| 내부 구현 경로 | 조건 | 실행 |", self.positioning)
        self.assertIn("workflow-router.md#구현-경로-표", self.positioning)

    def test_claude_doc_map_reaches_current_plugin_docs(self) -> None:
        """#853 — CLAUDE.md doc map reaches every current docs/plugin markdown file."""
        plugin_docs = sorted(
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "docs" / "plugin").rglob("*.md")
            # docs/plugin/agents/ 는 얇은 진입점(agents/<name>.md)이 가리키는 agent 소비용
            # 지침·templates·references·_shared 다 (#963 — agents/ 재귀 등록 오염 해소로 이동).
            # CLAUDE.md 문서 지도는 사람용 SSOT 네비라 agent-internal 콘텐츠는 대상 밖 —
            # reachability 는 진입점 + cross-ref 고아 게이트가 보장한다.
            if not path.relative_to(ROOT).as_posix().startswith("docs/plugin/agents/")
        )
        missing = [path for path in plugin_docs if path not in self.claude]
        self.assertEqual([], missing)
        self.assertNotIn("## 문서 지도\n\n\n\n", self.claude)

    def test_design_token_doc_is_disambiguated_from_design_workflow(self) -> None:
        """#853 — docs/plugin/design.md is token/spec guidance, not the /design workflow."""
        self.assertIn("본 문서는 `/design` workflow skill 이 아니라", self.design_tokens_doc)
        self.assertIn("skills/design/SKILL.md", self.design_tokens_doc)

    def test_external_runtime_docs_do_not_point_at_archive_paths(self) -> None:
        """#853 — deployed command/script guidance should not require release-pruned archive docs."""
        self.assertNotIn("docs/archive/", self.smart_compact)
        self.assertNotIn("docs/archive/branch-protection-setup.md", self.branch_protection_script)
        self.assertNotIn("docs/internal/branch-protection-setup.md", self.branch_protection_script)
        self.assertIn("docs/plugin/hooks.md", self.branch_protection_script)

    def test_spec_skill_wording_matches_step_ownership_split(self) -> None:
        """#857 follow-up — SKILL owns Step-internal branches; routing owns inter-skill movement."""
        self.assertIn("Step 내부 분기는 본 파일이 소유", self.spec_skill)
        self.assertIn("skill 간 이동·재진입은 [`spec-routing.md`](spec-routing.md)", self.spec_skill)
        self.assertNotIn(
            "분기 규칙 SSOT 는 [`spec-routing.md`](spec-routing.md) 다.",
            self.spec_skill,
        )
        self.assertNotIn(
            "분기 판단이 필요하면 [`spec-routing.md`](spec-routing.md)를 확인한다.",
            self.spec_skill,
        )

    def test_readme_uses_lifecycle_defaults_without_compat_aliases(self) -> None:
        basic_table = self._section(self.readme, r"\| 기본 진입점 \|", r"\n`/impl`")
        for name in LIFECYCLE:
            self.assertIn(f"| `{name}` |", basic_table)
        for name in REMOVED_WORKFLOW + SUPPORT:
            self.assertNotIn(f"| `{name}` |", basic_table)

        public_surface = self._section(self.readme, r"## 공개 진입점", r"\n## 거버넌스")
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
        # #711 — impl 내부 구현 경로 = Lite/Standard (설계도 유무), Deep 제거
        self.assertIn(
            "`/impl` 이 내부적으로 구현 경로(설계도 유무 — Lite / Standard)", self.readme
        )
        self.assertNotIn("Lite / Standard / Deep lane", self.readme)

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
        utility_block = self._section(
            self.init_doc, r"유틸리티:\n", r"\n\n비활성화:"
        )

        for name in LIFECYCLE:
            self.assertIn(f"- {name} ", default_block)
        for name in REMOVED_WORKFLOW + SUPPORT:
            self.assertNotIn(f"- {name} ", default_block)
        self.assertIn("- /spec — PRD / Epic / Story / AC", default_block)

        for name in SUPPORT:
            self.assertIn(f"- {name} ", support_block)
        for name in ("/tech-review", "/impl-loop"):
            self.assertIn(f"- {name} ", advanced_block)
        self.assertNotIn("- /ux ", advanced_block)
        self.assertIn("- /ux ", utility_block)
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

    def test_cross_ref_gate_does_not_freeze_component_counts(self) -> None:
        """#877 — component count drift should be avoided at the source, not patched by deny-list."""
        self.assertNotIn("옛 agent 카운트", self.cross_ref_script)
        self.assertNotIn("옛 hook 카운트", self.cross_ref_script)
        self.assertNotIn("옛 loop 카운트", self.cross_ref_script)
        self.assertNotIn("현재 12 종", self.cross_ref_script)
        self.assertNotIn("현재 8 hook", self.cross_ref_script)

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

        self.assertGreater(len(runtime_hooks), 0)
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
        self.assertEqual({"commit-msg", "post-checkout", "pre-push", "pre-commit"}, git_hooks)
        for hook_name in sorted(git_hooks):
            self.assertIn(f"### .git/hooks/{hook_name}", self.hooks_doc)
            self.assertIn(f"`scripts/hooks/{hook_name}`", self.hooks_doc)

        workflow_source = self.init_doc + "\n" + self.init_reference
        workflows = set(
            re.findall(
                r"(?:\$PROJECT_ROOT/)?\.github/workflows/"
                r"([A-Za-z0-9_.-]+\.yml)",
                workflow_source,
            )
        )
        self.assertEqual(
            {
                "git-naming-validation.yml",
                "doc-path-integrity.yml",
                "doc-sync.yml",
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

        # #711 — Deep 는 impl 내부 lane 이 아니라 impl 진입 전 high-risk 설계 선행 분기
        self.assertIn(
            "high-risk → 설계 선행: /spec 내부 tech-review preflight? → /design → /impl → /acceptance",
            self.router,
        )
        self.assertNotIn("Deep: /spec 내부 tech-review", self.router)
        self.assertIn(
            "설계 선행(`/spec` 내부 tech-review preflight 필요 시 / `/design`)",
            self.positioning,
        )
        self.assertIn("Lite: /impl direct PR", self.router)
        self.assertIn("Lite (`/impl` 직접)", self.router)
        self.assertIn(
            "concrete signal 로 보고 `/impl`, `/design`, `/spec`, `/ux` 등",
            self.router,
        )

    def test_internal_routing_docs_prefer_lifecycle_names(self) -> None:
        # #711 — high-risk 선행은 impl 밖. impl 문서가 lifecycle 진입점을 가리킨다.
        self.assertIn("deep impl task 파일이 이미 있다 → `/impl-loop <task>`", self.impl_skill)
        self.assertIn("`/spec` 부터 시작한다", self.impl_skill)
        self.assertIn("`/design` 으로 설계한다", self.impl_skill)
        self.assertIn('OUT["impl 밖 — 설계 선행: /spec 또는 /design"]', self.impl_routing)
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
        self.assertIn("진행 절차와 체크포인트 응답 분기는 [`SKILL.md`](SKILL.md)", self.spec_routing)
        self.assertIn("이슈 등록 보류 marker", self.spec_routing)
        self.assertNotIn("## skill 시퀀스 그래프", self.spec_routing)
        self.assertNotIn("## 체크포인트 → 다음 단계 매핑", self.spec_routing)
        self.assertNotIn("PR 머지 + 이슈 등록", self.spec_routing)
        self.assertIn("spec-prd-reference.md", self.spec_skill)
        self.assertIn("spec-stories-reference.md", self.spec_skill)
        self.assertIn("spec-delivery-reference.md", self.spec_skill)
        self.assertIn("PRD 산출물 의무", self.spec_prd_reference)
        self.assertIn("stories.md 산출물", self.spec_stories_reference)
        self.assertIn("# Story Backlog", self.spec_stories_reference)
        self.assertIn(
            "# preflight 를 실행했다면: git add docs/tech-review.md",
            self.spec_delivery_reference,
        )
        self.assertIn(
            "git add docs/prd.md docs/index.md docs/epics/epic-NN-<slug>/stories.md",
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

    def test_issue_969_architecture_validator_does_not_require_root_append_map(self) -> None:
        """#969 — final validator no longer fails on checked-in root architecture map drift."""
        for stale in (
            "전역 `docs/architecture.md` append 반영",
            "system 단위(1차) 검증이면 전역 architecture append 반영",
            "aggregate_architecture_map.mjs --check",
        ):
            self.assertNotIn(stale, self.architecture_validator)
        self.assertIn("final epic 검증", self.architecture_validator)
        self.assertIn("형식만으로 Must", self.architecture_validator)

    def test_issue_969_architecture_map_is_on_demand_not_doc_sync_gate(self) -> None:
        """#969 — root architecture summary is on-demand, not a checked-in drift gate."""
        script = (ROOT / "scripts" / "aggregate_architecture_map.mjs")
        index_script = ROOT / "scripts" / "aggregate_index_map.mjs"
        root_template = (
            ROOT / "docs" / "plugin" / "agents" / "system-architect" / "templates" / "root-architecture.md"
        ).read_text(encoding="utf-8")
        index_template = (
            ROOT / "skills" / "spec" / "templates" / "index.md"
        ).read_text(encoding="utf-8")
        epic_template = (
            ROOT / "docs" / "plugin" / "agents" / "system-architect" / "templates" / "epic-architecture.md"
        ).read_text(encoding="utf-8")
        system_architect = (
            ROOT / "docs" / "plugin" / "agents" / "system-architect" / "system-architect-agent.md"
        ).read_text(encoding="utf-8")
        script_text = script.read_text(encoding="utf-8")

        self.assertTrue(script.exists())
        self.assertTrue(index_script.exists())
        self.assertIn(".dcness-work/reports/architecture-map.md", script_text)
        self.assertIn("--stdout", script_text)
        self.assertNotIn("--check", script_text)
        self.assertNotIn("## 공유 계약 인덱스", root_template)
        self.assertNotIn("| 결정 | 범위 | 이유 |", root_template)
        self.assertIn("온디맨드", root_template)
        self.assertIn(".dcness-work/reports/architecture-map.md", root_template)
        self.assertIn("dcness-index-map:generated", index_template)
        self.assertNotIn("scripts/aggregate_architecture_map.mjs", epic_template)
        self.assertIn("| 모듈 | 책임 | 의존 모듈 | 공개 인터페이스 | 검증 경로 | 결정 |", epic_template)
        self.assertNotIn("| contract | owner | producer | consumer | invariant |", epic_template)
        self.assertIn("scripts/aggregate_index_map.mjs", self.init_doc)
        self.assertIn("scripts/aggregate_index_map.mjs", self.init_reference)
        self.assertIn("scripts/aggregate_index_map.mjs", self.spec_skill)
        self.assertIn("scripts/aggregate_architecture_map.mjs", self.init_doc)
        self.assertIn("scripts/aggregate_architecture_map.mjs", self.init_reference)
        self.assertIn("scripts/aggregate_index_map.mjs", system_architect)
        self.assertIn("온디맨드", system_architect)
        self.assertNotIn("aggregate_architecture_map.mjs", self.architecture_validator)

    def test_design_records_are_frozen_before_design_pr(self) -> None:
        """#833 follow-up — design metrics are committed with the design PR."""
        end_run_at = self.design_skill.index("end-run + design run 기록 freeze")
        approval_at = self.design_skill.index("사용자 최종 설계 승인 + commit/PR")
        self.assertLess(end_run_at, approval_at)
        for needle in (
            "PR 생성 전에",
            "docs/metrics/design-runs.jsonl",
            "같은 PR 에 포함",
            "PR/merge 뒤에 end-run 을 미루면",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.design_skill)
        self.assertIn("end-run/metrics freeze 후 사용자 최종 설계 승인", self.design_routing)

    def test_issue_852_worktree_remove_requires_clean_worktree(self) -> None:
        """#852 — auto discard requires absorbed commits and no local dirty files."""
        for needle in (
            "커밋 diff 흡수 확인 + working tree clean",
            "git status --porcelain --untracked-files=all",
            "uncommitted/untracked",
            'ExitWorktree(action="remove", discard_changes=true)',
            'ExitWorktree(action="keep")',
            "자동 discard 금지",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.loop_procedure)

        self.assertIn(
            "../../docs/plugin/loop-procedure.md#worktree-분기-action-루프-한정",
            self.impl_skill,
        )
        self.assertIn("ExitWorktree", self.impl_skill)

    def test_issue_832_design_runs_mechanical_artifact_audit(self) -> None:
        """#832 — design loop runs the artifact audit before final validator/PR."""
        for needle in (
            "check_design_artifact_structure.mjs",
            "legacy Contract Ledger / Contract References 경고",
            "final validator 진입을 막지 않는다",
        ):
            self.assertIn(needle, self.design_skill)

        for needle in (
            "형식만으로 FAIL 하지 않는다",
            "Should finding",
            "module responsibility",
        ):
            self.assertIn(needle, self.architecture_validator)

    def test_issue_832_design_artifact_audit_is_wired_to_external_doc_sync_gate(self) -> None:
        """#832 follow-up — installed doc-sync workflow runs the design audit."""
        for needle in (
            "scripts/check_design_artifact_structure.mjs",
            "Validate /design artifact structure",
        ):
            self.assertIn(needle, self.doc_sync_action)

        for text in (
            self.init_doc,
            self.init_reference,
            self.hooks_doc,
            self.deliverables_map,
        ):
            with self.subTest(source=text[:30]):
                self.assertIn("check_design_artifact_structure.mjs", text)

    def test_issue_810_tech_review_skill_supports_epic_option4(self) -> None:
        """#810 AC7 — /tech-review skill must define both root and epic invocation contracts."""
        for needle in (
            "전역 preflight 모드",
            "epic option 4 모드",
            "`docs/epics/<epic>/stories.md`",
            "`docs/epics/<epic>/tech-review.md`",
            "검토 입력: 대상 epic `stories.md` 와 미검증 외부 의존 질문",
        ):
            self.assertIn(needle, self.tech_review_skill)

    def test_issue_810_design_producer_inputs_are_global_min_plus_epic_fixed(self) -> None:
        """#810 AC8 — design producers carry deterministic input sets."""
        for needle in (
            "전역 최소: `docs/index.md`, `docs/prd.md`, `docs/conventions.md`",
            "epic 고정: `docs/epics/<epic>/stories.md`, 대상 `docs/epics/<epic>/ux-flow.md`",
        ):
            self.assertIn(needle, self.ux_architect)

        for needle in (
            "전역 최소: `docs/index.md`, `docs/prd.md`, `docs/conventions.md`",
            "epic option 4 고정: `docs/epics/<epic>/stories.md`",
        ):
            self.assertIn(needle, self.tech_reviewer)

    def test_issue_810_seed_templates_are_korean_and_index_has_overview(self) -> None:
        """#810 minor — cold-start index overview and seed language consistency."""
        index = (ROOT / "skills" / "spec" / "templates" / "index.md").read_text(
            encoding="utf-8"
        )
        conventions = (
            ROOT / "docs" / "plugin" / "agents" / "system-architect" / "templates" / "conventions.md"
        ).read_text(encoding="utf-8")
        decision = (
            ROOT / "docs" / "plugin" / "agents" / "system-architect" / "templates" / "decision.md"
        ).read_text(encoding="utf-8")
        root_architecture = (
            ROOT / "docs" / "plugin" / "agents" / "system-architect" / "templates" / "root-architecture.md"
        ).read_text(encoding="utf-8")

        self.assertIn("# 프로젝트 문서 인덱스", index)
        self.assertIn("## 개요", index)
        self.assertIn("제품 한 줄 요약", index)
        self.assertIn("# 전역 규약", conventions)
        self.assertIn("# 전역 아키텍처 지도", root_architecture)
        self.assertIn("# 결정 NNNN", decision)
        self.assertIn(
            "scope: global  # global | epic-NN | module:<module-id> | module:<module-id>/epic-NN",
            decision,
        )

    def test_init_doc_drops_removed_tdd_gate_references(self) -> None:
        """#681 — /init-dcness 가 폐기된 TDD CI/pre-commit flow 를 더는 언급하지 않는다.

        제거 대상: `tdd-gate.yml` workflow, `.dcness/tdd-gate-enabled` 마커,
        pre-commit TDD 게이트 활성화 문구. (현재 setup/commit 예시에서 stale.)
        """
        for stale in ("tdd-gate.yml", ".dcness/tdd-gate-enabled", "pre-commit TDD", "TDD 게이트"):
            self.assertNotIn(
                stale,
                self.init_doc,
                msg=f"init-dcness.md 에 폐기된 TDD flow 참조 '{stale}' 잔존 (#681)",
            )

    def test_init_doc_is_execution_runbook_not_hook_policy_reference(self) -> None:
        """#690 — /init-dcness 는 실행 절차만 두고 자동 hook 설명은 SSOT 링크로 내린다."""
        self.assertLess(
            len(self.init_doc.splitlines()),
            500,
            msg="/init-dcness public entrypoint 가 다시 장황한 reference 문서가 됨",
        )
        for stale in (
            "Step 2.9",
            "발화 흐름:",
            "자동 skip 룰",
            "이전 v0.2.10",
            "commit-msg TDD chain",
        ):
            self.assertNotIn(
                stale,
                self.init_doc,
                msg=f"init-dcness.md 에 자동 hook 상세/히스토리 '{stale}' 잔존 (#690)",
            )
        self.assertIn("이미 자동 적용되는 것", self.init_doc)
        self.assertIn("../docs/plugin/hooks.md#tdd-guardsh", self.init_doc)
        self.assertIn("docs/plugin/init-dcness.md", self.init_doc)

    def test_init_reference_owns_bootstrap_inventory_and_workflow_templates(self) -> None:
        """#690/#800 — reference 는 bootstrap 상세와 workflow template inventory 를 둔다."""
        self.assertIn("## Bootstrap Inventory", self.init_reference)
        self.assertIn("### Core", self.init_reference)
        self.assertIn("### Optional", self.init_reference)
        self.assertIn("## Recommended Bundle Defaults", self.init_reference)
        self.assertIn("root architecture.md 감지로 docs/architecture.md skip", self.init_reference)
        self.assertIn("## CI Workflow Snippets", self.init_reference)
        self.assertIn("workflow template inventory", self.init_reference)
        self.assertIn("## Re-run Matrix", self.init_reference)
        self.assertIn("hooks.md#tdd-guardsh", self.init_reference)
        for workflow in (
            "git-naming-validation.yml",
            "pr-body-validation.yml",
            "doc-path-integrity.yml",
            "doc-sync.yml",
            "github-project-lifecycle.yml",
        ):
            self.assertIn(workflow, self.init_reference)
            template = ROOT / "templates" / "github-workflows" / workflow
            self.assertTrue(template.exists(), template)
            self.assertIn(f"templates/github-workflows/{workflow}", self.init_doc)
            self.assertIn(f"templates/github-workflows/{workflow}", self.init_reference)

            workflow_name = workflow.removesuffix(".yml")
            self.assertIn(
                f"name: {workflow_name}",
                template.read_text(encoding="utf-8"),
            )
            self.assertNotIn(f"name: {workflow_name}", self.init_doc)
            self.assertNotIn(f"name: {workflow_name}", self.init_reference)

    def test_issue_825_init_backfills_existing_index_next_section(self) -> None:
        """#825 follow-up — existing docs/index.md gets the next-work section without overwrite."""
        helper = "scripts/ensure_docs_index_next_section.mjs"
        self.assertTrue((ROOT / helper).exists())
        self.assertIn(helper, self.init_doc)
        self.assertIn(helper, self.init_reference)
        self.assertIn("진행 상태 섹션", self.init_doc)
        self.assertIn("진행 상태 섹션", self.init_reference)

    def test_issue_903_init_dcness_ignores_runtime_harness_state(self) -> None:
        """#903 — /init-dcness keeps runtime telemetry/state out of git status."""
        for text in (self.init_doc, self.init_reference):
            with self.subTest(source=text[:30]):
                self.assertIn(".dcness-work/", text)
                self.assertIn(".claude/harness-state/", text)
                self.assertIn(".gitignore", text)

    def test_issue_910_boundary_suggestion_trigger_is_documented(self) -> None:
        """#910 — init/impl start suggests boundary override without writing it."""
        for text in (self.init_doc, self.impl_skill, self.init_reference, self.hooks_doc):
            with self.subTest(source=text[:30]):
                self.assertIn("boundary-suggestions", text)
                self.assertIn(".dcness/boundary.json", text)
                self.assertIn("사람 승인", text)
        self.assertIn("read-only", self.init_reference)
        self.assertIn("표준 레이아웃·빈 프로젝트", self.impl_skill)

    def test_issue_885_claude_md_seed_and_audit_stays_inside_existing_surfaces(self) -> None:
        """#885 — CLAUDE.md seed/migration and audit wire into init/run-review only."""
        helper = "scripts/dcness-context-docs"
        self.assertTrue((ROOT / helper).exists())
        self.assertTrue((ROOT / "harness" / "context_docs.py").exists())
        self.assertIn(helper, self.init_doc)
        self.assertIn(helper, self.init_reference)
        self.assertIn("CLAUDE.md seed/migration", self.init_doc)
        self.assertIn("6축 quality audit", self.init_reference)
        self.assertIn("6축 rubric", self.run_review_skill)
        self.assertIn("cold-start 앵커", self.run_review_skill)

    def test_init_dcness_completion_precedes_optional_bundle(self) -> None:
        """#799 — core 활성화 완료를 먼저 선언하고 선택형 확장은 bundle 1질문으로 둔다."""
        for needle in (
            "## Core Activation",
            "## 선택형 확장",
            "Y/n/custom",
            "엔터 = Y",
            "선택형 확장은 core activation 성공 조건이 아니다",
            "[dcness] 활성화 완료",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.init_doc)

        complete_at = self.init_doc.index("[dcness] 활성화 완료")
        optional_at = self.init_doc.index("## 선택형 확장")
        self.assertLess(complete_at, optional_at)
        self.assertEqual(1, self.init_doc.count("적용할까요? (Y/n/custom)"))
        self.assertNotIn("선택형 확장 추천 bundle 을 적용할까요? (Y/n/custom)", self.init_doc)
        self.assertIn("DCNESS_WORKFLOW_CHANGES", self.init_doc)
        self.assertIn("Codex validator skills", self.init_doc)
        self.assertIn("gh auth status", self.init_doc)
        self.assertIn("ORIGIN_URL", self.init_doc)
        self.assertIn("GH_AUTH_OK", self.init_doc)
        self.assertIn("gh auth 미인증/미설치", self.init_doc)
        self.assertNotIn("git status --short .github/workflows/", self.init_doc)

        for stale_heading in (
            "### Step 5 -",
            "### Step 6 -",
            "### Step 7 -",
            "### Step 8 -",
            "### Step 9 -",
        ):
            self.assertNotIn(stale_heading, self.init_doc)
        self.assertNotIn("(Y/n)", self.init_doc)

    def test_issue_920_init_completion_includes_five_minute_onboarding(self) -> None:
        """#920 — /init-dcness 완료 직후 최소 온보딩 3요소를 한 화면에 제공한다."""
        onboarding = self._section(
            self.init_doc,
            r"5분 온보딩",
            r"\n\n기본 workflow:",
        )
        for needle in (
            "5분 독해 상한",
            "강제/자율 경계",
            "작업 순서",
            "접근 영역",
            "첫 작업 진입점",
            "/impl",
            "막힐 때 볼 곳",
            "hook-first recovery",
            '"$HELPER" status',
            "docs/plugin/hooks.md#catastrophic-gatesh",
            "docs/plugin/workflow-router.md#구현-경로-표",
            "docs/plugin/init-dcness.md#re-run-matrix",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, onboarding)

        self.assertLessEqual(
            len([line for line in onboarding.splitlines() if line.strip()]),
            14,
        )
        self.assertNotIn("신규 공개 진입점", onboarding)

    def test_hooks_doc_distinguishes_issue_mutation_paths(self) -> None:
        """#681 AC#4 — hooks.md 가 Bash `gh issue` 차단 vs GitHub MCP issue 통과를 구별한다."""
        self.assertIn(
            "Bash `gh issue create/edit/close/comment`",
            self.hooks_doc,
        )
        self.assertIn("check_github_mcp_mutation", self.hooks_doc)
        self.assertIn("per-agent `tools:` 권한", self.hooks_doc)

    def test_hooks_doc_tdd_guard_scope_is_accurate(self) -> None:
        """#681/#786 — tdd-guard 문서가 존재-검사·entry-file·Bash write target 정책을 명시한다."""
        self.assertIn("test 의 존재만 검사하고, test 를 실행하지는 않는다", self.hooks_doc)
        self.assertIn("registerRootComponent(", self.hooks_doc)
        self.assertIn("Bash write target 정책", self.hooks_doc)
        self.assertIn("TDD GUARD[Bash]", self.hooks_doc)
        self.assertIn("contest.ts", self.hooks_doc)

    def test_backpressure_loop_is_first_class_across_stages(self) -> None:
        """#702 — 단계 간 되돌림(backpressure) 원리가 분기 규칙 SSOT 에 일급으로 명시된다."""
        # 원리 SSOT — workflow-router: 정의 + 최소 경로(design→spec, impl→설계) + 내부 루프 통합 기술
        self.assertIn("## 되돌림(backpressure) 원리", self.router)
        self.assertIn("정상 루프", self.router)
        self.assertIn("`/spec` 재진입", self.router)
        self.assertIn("compact-design", self.router)
        self.assertIn("단계 내부 되돌림", self.router)

        # impl 의 1차 분기 = 설계 문서 유무 + 설계 부족 시 되돌림 경로
        self.assertIn("설계 산출물이 이미 있는가", self.impl_skill)
        self.assertIn("compact-design", self.impl_skill)
        self.assertIn("--design-doc", self.impl_skill)
        self.assertIn("compact-design", self.impl_routing)

        # design → spec 되돌림이 동일 원리로 참조됨
        self.assertIn("되돌림", self.design_skill)

    def test_compact_design_is_internal_skill_not_public_surface(self) -> None:
        """#702 — 경량 모듈 설계는 module-architect:COMPACT_PLAN wrapper 내부 skill 이다."""
        skill_path = ROOT / "skills" / "compact-design" / "SKILL.md"
        self.assertTrue(skill_path.exists())
        compact_design = skill_path.read_text(encoding="utf-8")

        # 설계 산출 주체 = module-architect COMPACT_PLAN, 산출 경로 = docs/compact-plans/
        self.assertIn("COMPACT_PLAN", compact_design)
        self.assertIn("module-architect", compact_design)
        self.assertIn("docs/compact-plans/", compact_design)
        # engineer 게이트 사전 조건 두 경로 (같은-run PASS / --design-doc) 명시
        self.assertIn("--design-doc", compact_design)

        # positioning: internal 분류로만 노출 — 기본/고급 public 진입점 표에 추가되지 않는다
        self.assertIn("## Internal Skills", self.positioning)
        self.assertIn("`compact-design`", self.positioning)
        self.assertNotIn("| `/compact-design` |", self.positioning)
        self.assertNotIn("/compact-design", self.readme)

    def test_action_loop_prompt_slot_template_is_shared(self) -> None:
        """#780 — 3-slot prompt form is a template and action loops surface it."""
        template_path = ROOT / "docs" / "plugin" / "templates" / "agent-prompt-slots.md"
        self.assertTrue(template_path.exists())
        for needle in (
            "**대상 + 읽을 진본:**",
            "**worktree:**",
            "**이 호출 특유:**",
            "방법 처방",
            "main repo 절대경로",
            "확정 목업 존재 UI epic",
            "docs/design.md",
            "node-id 매핑",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.agent_prompt_template)

        self.assertIn("agent-prompt-slots.md", self.loop_procedure)
        self.assertIn("[PROMPT_SLOT_CHECK]", self.loop_procedure)
        self.assertNotIn(
            "**대상 + 읽을 진본:** {{",
            self.loop_procedure,
            msg="loop-procedure.md should link the shared template, not own a copy",
        )

        for label, text in (
            ("impl", self.impl_skill),
            ("impl-loop", self.impl_loop_skill),
            ("design", self.design_skill),
        ):
            with self.subTest(label=label):
                self.assertIn("Sub-agent prompt 작성 checkpoint (#780)", text)
                self.assertIn("agent-prompt-slots.md", text)
                self.assertIn("[PROMPT_SLOT_CHECK]", text)
                self.assertIn("worktree 절대경로", text)
                self.assertIn("방법 처방", text)

    def _section(self, text: str, start: str, end: str) -> str:
        match = re.search(start + r"(?P<body>.*?)" + end, text, flags=re.S)
        self.assertIsNotNone(match)
        return match.group("body")


if __name__ == "__main__":
    unittest.main()

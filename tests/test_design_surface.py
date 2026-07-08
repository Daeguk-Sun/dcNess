"""Design 공개 진입점 contract tests."""
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

    def test_design_uses_epic_batch_module_design_and_final_validation(self) -> None:
        """#831 — /design no longer interleaves module writing and validation per Story."""
        design_dir = ROOT / "skills" / "design"
        design = (design_dir / "SKILL.md").read_text(encoding="utf-8")
        routing = (design_dir / "design-routing.md").read_text(encoding="utf-8")

        self.assertNotIn("module-architect × K → architecture-validator(2차)", design)
        self.assertNotIn("`PASS × K`", design)
        for stale in (
            "module-architect(common) → architecture-validator(공통 단위)",
            "module-architect(Story N) → architecture-validator(Story 단위)",
            "공통 task 선행 검증",
            "Story별 module-architect+architecture-validator",
            "공통 task 없음 → 공통 단위 검증 없이 Story 1",
            "각 Story 마다 **module-architect",
            "AV_COMMON",
            "AV_STORY",
        ):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, design)
                self.assertNotIn(stale, routing)

        self.assertNotIn(
            "다음 단위 module-architect / (마지막이면) architecture-validator 2차",
            routing,
        )

        for stale in (
            "architecture-validator(1차/system freeze)",
            "system freeze",
            "Contract Ledger row-key",
            "contract_sweep",
            "CONTRACT_PROPAGATION",
        ):
            self.assertNotIn(stale, design)
            self.assertNotIn(stale, routing)

        for expected in (
            "system-architect(thin bootstrap)",
            "모듈 topology 부재",
            "module-architect(epic-batch)",
            "epic architecture 최소형과 epic 전체 impl 산출물",
            "Story 단위 작성 주체로 쪼개지 않는다",
            "architecture-validator(final epic 검증)",
            "Step 4 — architecture-validator final epic 검증",
            "모든 Story 에 단위 검증을 기본값으로 복원하지 않는다",
            "check_design_artifact_structure.mjs",
            "SYSTEM_CHECKPOINT_REQUIRED",
        ):
            self.assertIn(expected, design)

        self.assertIn("선택 `docs/epics/.../ux-flow.md`", design)
        self.assertIn("UI epic 이면 `ux-flow.md`", design)

        for expected in (
            "SA_BOOT[system-architect thin bootstrap]",
            "SA_BOOT -->|PASS| MA_BATCH",
            "MA_BATCH -->|PASS| AV_FINAL",
            "`PASS`(final epic 검증)",
            "bootstrap 뒤 architecture-validator 를 끼우지 않고 바로 module-architect",
            "module-architect(epic-batch)",
            "architecture-validator(final epic 검증)",
            "SYSTEM_CHECKPOINT_REQUIRED",
        ):
            self.assertIn(expected, routing)

    def test_design_epic_batch_supports_issue_831_quality_controls(self) -> None:
        design_dir = ROOT / "skills" / "design"
        design = (design_dir / "SKILL.md").read_text(encoding="utf-8")
        routing = (design_dir / "design-routing.md").read_text(encoding="utf-8")
        system_architect = (
            ROOT / "docs" / "plugin" / "agents" / "system-architect" / "system-architect-agent.md"
        ).read_text(encoding="utf-8")
        system_template = (
            ROOT / "docs" / "plugin" / "agents" / "system-architect" / "templates" / "epic-architecture.md"
        ).read_text(encoding="utf-8")
        module_architect = (
            ROOT / "docs" / "plugin" / "agents" / "module-architect" / "module-architect-agent.md"
        ).read_text(encoding="utf-8")
        validator = (
            ROOT
            / "docs" / "plugin" / "agents"
            / "architecture-validator"
            / "architecture-validator-agent.md"
        ).read_text(encoding="utf-8")
        codex_validator = (
            ROOT / "codex" / "skills" / "dcness-architecture-validator" / "SKILL.md"
        ).read_text(encoding="utf-8")
        test_engineer = (
            ROOT / "docs" / "plugin" / "agents" / "test-engineer" / "test-engineer-agent.md"
        ).read_text(encoding="utf-8")

        for needle in (
            "기록된 스택 결정",
            "확인 안내 후 skip",
            "첫 epic 등 미기록 상태",
            "domain-model.md 생략 가능",
            "생략 판단 근거",
            "계약 표면 코드 SSOT 대조",
            "포트, 도메인 타입, 공개 entrypoint",
            "risk / engine / depends_on",
            "수정 허용",
            "규모 preflight",
            "target 1,500줄 / hard warning 2,000줄",
            "epic 분할 또는 예외적 batch 2분할",
            "system checkpoint 승격",
            "THIN_BOOTSTRAP",
            "topology 부재",
        ):
            self.assertIn(needle, design)

        for needle in (
            "final epic 검증 FAIL → 산출 주체 재진입",
            "3 cycle",
            "표의 각 행에 적힌 한도",
            "초과 시 사용자 위임",
        ):
            self.assertIn(needle, routing)

        for text in (system_architect, module_architect, validator):
            with self.subTest(text=text[:60]):
                self.assertIn("계약 표면 코드 SSOT 대조", text)
                self.assertIn("포트, 도메인 타입, 공개 entrypoint", text)

        for needle in (
            "THIN_BOOTSTRAP",
            "큰 모듈 목록(책임 + 공개 인터페이스 한 줄)",
            "도메인 모델 작성/생략 판단, 계약 표면 코드 SSOT 대조, Module Design Check evidence, Agent Operability 상세, impl task 작성으로 확장하지 않는가",
            "bootstrap 뒤에 별도 architecture-validator 를 끼우지 않고 module-architect(epic-batch)로 바로 간다",
            "CHECKPOINT",
        ):
            self.assertIn(needle, system_architect)

        root_template = (
            ROOT / "docs" / "plugin" / "agents" / "system-architect" / "templates" / "root-architecture.md"
        ).read_text(encoding="utf-8")
        self.assertIn("## 큰 모듈 경계", root_template)
        self.assertIn("| 모듈 | 책임 | 공개 인터페이스 | 결정 |", root_template)
        self.assertIn("## 의존 그래프", root_template)

        self.assertIn("## Domain Model", system_template)
        self.assertIn("생략 판단 근거 (생략 시 필수)", system_template)
        self.assertIn("## 모듈 목록", system_template)
        self.assertIn("## 의존 그래프", system_template)
        self.assertIn("## Story -> 모듈 매핑", system_template)
        self.assertNotIn("## Contract Ledger", system_template)
        self.assertNotIn("## Flow Ownership Map", system_template)

        self.assertIn(
            "domain-model.md` 가 있으면 함께 읽고, 없으면 낮은 도메인 복잡도 등 생략 판단 근거",
            module_architect,
        )
        self.assertIn("파일 부재만으로 도메인 모델을 새로 만들거나 ESCALATE 하지 않는다", module_architect)
        self.assertIn("SYSTEM_CHECKPOINT_REQUIRED", module_architect)
        self.assertIn("기존 모듈 경계, 도메인 invariant, storage policy, public API boundary, 기존 전역 decision", module_architect)
        self.assertIn("신규 epic-scope decision 기록은 자율", module_architect)
        self.assertIn("기존 전역 decision 변경은 `SYSTEM_CHECKPOINT_REQUIRED`", module_architect)
        self.assertIn("파일 부재만으로 `SPEC_GAP_FOUND` 하지 않는다", test_engineer)

        for text in (validator, codex_validator):
            with self.subTest(domain_validator=text[:60]):
                self.assertIn("domain-model.md` 작성 또는 생략 판단 근거", text)
                self.assertIn("domain-model 작성/생략 근거가 impl 계약과 모순", text)
                self.assertIn("형식만으로 Must", text)

    def test_design_clean_path_requires_pre_commit_approval(self) -> None:
        """#851/#997 — final PASS 뒤 commit 전에 사용자 최종 설계 승인을 받는다."""
        design_dir = ROOT / "skills" / "design"
        design = (design_dir / "SKILL.md").read_text(encoding="utf-8")
        routing = (design_dir / "design-routing.md").read_text(encoding="utf-8")
        design_ux = (ROOT / "skills" / "design-ux" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        design_system = (ROOT / "skills" / "design-system" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        loop_procedure = (ROOT / "docs" / "plugin" / "loop-procedure.md").read_text(
            encoding="utf-8"
        )

        for needle in (
            "사용자 최종 설계 승인",
            "산출물 요약",
            "diff 규모",
            "승인 응답 전에는 `git add`, `git commit`, `git push`, `gh pr create`, `$PLUGIN_ROOT/scripts/pr-finalize.sh` 를 호출하지 않는다",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, design)

        for text in (routing, design_ux, design_system, loop_procedure):
            with self.subTest(text=text[:60]):
                self.assertIn("사용자 최종 설계 승인", text)

        self.assertIn(
            "| 승인-gated 산출물 최종 승인 (`/design`, `/ux`) | 사용자 승인 | 동일 (yolo 우회 X) |",
            loop_procedure,
        )
        self.assertNotIn("최종 검증 결과 commit", design)
        self.assertNotIn("사용자 확인 없이 자동 진행 (**impl-task-loop 외** 루프)", loop_procedure)

    def test_design_retry_limit_has_single_provider_agnostic_counter(self) -> None:
        """#970 — final validation retry limit must not reset by finding or provider."""
        design_dir = ROOT / "skills" / "design"
        design = (design_dir / "SKILL.md").read_text(encoding="utf-8")
        routing = (design_dir / "design-routing.md").read_text(encoding="utf-8")
        loop_procedure = (ROOT / "docs" / "plugin" / "loop-procedure.md").read_text(
            encoding="utf-8"
        )
        validator = (
            ROOT
            / "docs"
            / "plugin"
            / "agents"
            / "architecture-validator"
            / "architecture-validator-agent.md"
        ).read_text(encoding="utf-8")
        codex_validator = (
            ROOT / "codex" / "skills" / "dcness-architecture-validator" / "SKILL.md"
        ).read_text(encoding="utf-8")

        for needle in (
            "RCA",
            "final epic 검증 FAIL → 산출 주체 재진입 counter 는 하나",
            "`SYSTEM_BOUNDARY` / `TASK_LOCAL`",
            "finding 영역 변경",
            "새 finding 등장",
            "리셋하지 않는다",
            "4번째 자동 재진입",
            "루프 재구성 이후",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, routing)

        for text in (design, routing, loop_procedure):
            with self.subTest(text=text[:60]):
                self.assertIn("Claude Agent 와 Codex wrapper 모두 메인이 집계", text)
                self.assertIn("Codex wrapper 는 end-step 까지 수행하지만 counter 소유자가 아니다", text)

        for text in (validator, codex_validator):
            with self.subTest(provider_doc=text[:60]):
                self.assertIn("retry counter 를 증가·리셋하지 않는다", text)
                self.assertIn("메인이 design-routing.md 의 provider-agnostic counter", text)

    def test_design_dispatches_internal_ux_and_system_stages(self) -> None:
        """#958 — /design remains public while durable artifacts select an internal stage."""
        design_dir = ROOT / "skills" / "design"
        design = (design_dir / "SKILL.md").read_text(encoding="utf-8")
        routing = (design_dir / "design-routing.md").read_text(encoding="utf-8")
        design_ux = (ROOT / "skills" / "design-ux" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        design_system = (ROOT / "skills" / "design-system" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        surface = (ROOT / "scripts" / "check_public_surface.mjs").read_text(
            encoding="utf-8"
        )

        for needle in (
            "얇은 dispatcher",
            "design-ux",
            "design-system",
            "ux 완료 · system 미완",
            "begin-run design --stage design-ux",
            "begin-run design --stage design-system",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, design)

        self.assertIn("DESIGN_UX_PR_MERGED", routing)
        self.assertIn("DESIGN_SYSTEM_PR_MERGED", routing)
        self.assertIn("'design-ux'", surface)
        self.assertIn("'design-system'", surface)
        self.assertIn("공개 진입점이 아니다", design_ux)
        self.assertIn("stage 1 PR", design_ux)
        self.assertIn("stage 2 PR", design_system)
        self.assertIn("기존 설계 pack 계약", design_system)

    def test_completed_design_pack_can_be_revised_surgically(self) -> None:
        """#997 — completed design packs need a first-class amend/re-open path."""
        design = (ROOT / "skills" / "design" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        routing = (
            ROOT / "skills" / "design" / "design-routing.md"
        ).read_text(encoding="utf-8")
        design_ux = (ROOT / "skills" / "design-ux" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        design_system = (ROOT / "skills" / "design-system" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        module_architect = (
            ROOT
            / "docs"
            / "plugin"
            / "agents"
            / "module-architect"
            / "module-architect-agent.md"
        ).read_text(encoding="utf-8")

        for needle in (
            "완료된 pack 개정",
            "`/design <epic> --revise`",
            "대화 맥락의 명시 개정 신호",
            "UX 층 개정",
            "`design-ux` revision mode",
            "`design-system` revision mode",
            "화면 통합",
            "surgical revision",
            "영향 산출물만 개정",
            "미변경 impl task 보존",
            "파생 drift 체크리스트",
            "전역 `architecture.md` 요약",
            "상태 ID prefix",
            "`design-report.html`",
            "ADR supersede-vs-edit",
            "확정 목업 node-id",
            "final validator",
            "전체 설계 pack 정합",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, design)

        for needle in (
            "revision mode",
            "full design pack 이 완료됐더라도",
            "UX 산출물 자체 개정은 `design-ux` revision mode 의 책임",
            "직전 `design-ux` revision",
            "수술적 개정",
            "미변경 impl task 를 재생성하지 않는다",
            "final epic 검증",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, design_system)

        for needle in (
            "UX 층 revision mode",
            "UX 산출물만 수술적으로 개정",
            "stage 1 revision PR",
            "`design-system` revision mode",
            "system/module 산출물은 직접 수정하지 않는다",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, design_ux)

        for needle in (
            "`/design` revision mode",
            "영향 산출물만 수술적으로 개정",
            "미변경 impl task 를 보존",
            "UX revision 전파",
            "파생 drift 체크 결과",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, module_architect)

        self.assertIn("완료된 pack 개정", routing)
        self.assertIn("완료된 pack + UX 층 개정 REVISION", routing)
        self.assertIn("REVISION", routing)

    def test_design_mockup_prefreeze_branch_contracts(self) -> None:
        """#957 — mockup opt-in happens before system design and becomes required input."""
        design = (ROOT / "skills" / "design" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        routing = (
            ROOT / "skills" / "design" / "design-routing.md"
        ).read_text(encoding="utf-8")
        design_ux = (ROOT / "skills" / "design-ux" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        design_system = (ROOT / "skills" / "design-system" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        module_architect = (
            ROOT
            / "docs"
            / "plugin"
            / "agents"
            / "module-architect"
            / "module-architect-agent.md"
        ).read_text(encoding="utf-8")
        validator = (
            ROOT
            / "docs"
            / "plugin"
            / "agents"
            / "architecture-validator"
            / "architecture-validator-agent.md"
        ).read_text(encoding="utf-8")

        for needle in (
            "목업 선행 여부",
            "목업=예",
            "목업 없음",
            "opt-out",
            "yolo 기본값 = 목업 없음",
            "system stage 는 사용자 PICK 확정 이후",
            "디자인 시스템 체크포인트",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, design)
                self.assertIn(needle, design_ux)

        for needle in (
            "docs/design.md 실존+유효",
            "확인-후-skip",
            "ad-hoc 베이스라인 문서",
            "외부 import 1회 변환",
            "참고 디자인 시스템 신호",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, design_ux)

        for needle in (
            "확정 목업 경로",
            "node-id 매핑",
            "docs/design.md 토큰",
            "목업 미참조 설계 금지",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, design_system)
                self.assertIn(needle, module_architect)
                self.assertIn(needle, validator)

        self.assertIn("dcness-helper mockup-node-check", validator)
        self.assertIn("사용자 PICK 확정 이후", routing)
        self.assertIn("목업 미참조", routing)

    def test_design_system_prompts_carry_ux_artifact_pointers(self) -> None:
        """#974 — stage 2 architect prompts include durable UX artifacts for UI epics."""
        design = (ROOT / "skills" / "design" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        design_ux = (ROOT / "skills" / "design-ux" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        design_system = (ROOT / "skills" / "design-system" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        module_architect = (
            ROOT
            / "docs"
            / "plugin"
            / "agents"
            / "module-architect"
            / "module-architect-agent.md"
        ).read_text(encoding="utf-8")
        ux_flow_template = (
            ROOT
            / "docs"
            / "plugin"
            / "agents"
            / "ux-architect"
            / "templates"
            / "ux-flow.md"
        ).read_text(encoding="utf-8")

        for needle in (
            "epic `ux-flow.md`",
            "`docs/design.md`",
            "화면별 확정 목업",
            "`docs/design-variants/canvas.html`",
            "mockup-node-check",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, design)
                self.assertIn(needle, design_system)

        for needle in (
            "UI epic 조건부 필수",
            "대상 epic의 `ux-flow.md`",
            "확정 목업 경로",
            "node-id 매핑",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, module_architect)

        self.assertIn("확정 목업 경로", ux_flow_template)
        self.assertIn("확정본 없음", ux_flow_template)
        self.assertIn("확정본 승격 후", design_ux)
        self.assertIn("ux-flow.md` 화면 인벤토리", design_ux)


if __name__ == "__main__":
    unittest.main()

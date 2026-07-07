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

    def test_design_clean_path_requires_pre_merge_confirmation_unless_yolo(self) -> None:
        """#851 — final PASS 뒤 설계 pack main 머지 전 사용자 확인 checkpoint 보존."""
        design_dir = ROOT / "skills" / "design"
        design = (design_dir / "SKILL.md").read_text(encoding="utf-8")
        routing = (design_dir / "design-routing.md").read_text(encoding="utf-8")

        for needle in (
            "main 머지 직전 사용자 확인",
            "산출물 요약",
            "diff 규모",
            "yolo",
            "확인 응답 전에는 `scripts/pr-finalize.sh` 를 호출하지 않는다",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, design)

        self.assertIn("사용자 확인 checkpoint", routing)


if __name__ == "__main__":
    unittest.main()

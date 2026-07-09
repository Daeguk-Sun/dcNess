"""skills/impl-loop/SKILL.md §사전 read 의무가 cost-aware 룰 (#436) 박혀있는지 검증.

이슈 #436 — `/impl-loop` skill 의 통째 read 강제가 CLAUDE.md (글로벌) cost-aware 행동
(#402) 과 충돌. 본 fix 가 다음 룰 박음:
- 200 line 초과 doc → 부분 read (grep + offset/limit)
- 수정 X 모듈 → grep + 시그니처만
- PR body → --jq '.body' | head -20
- 메인 직접 read = 최소 (진입 분기 판단만)
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_impl_skill() -> str:
    return (ROOT / "skills" / "impl-loop" / "SKILL.md").read_text(encoding="utf-8")


def read_impl_routing() -> str:
    return (ROOT / "skills" / "impl-loop" / "impl-loop-routing.md").read_text(encoding="utf-8")


def read_impl_skill_default() -> str:
    return (ROOT / "skills" / "impl" / "SKILL.md").read_text(encoding="utf-8")


def read_impl_routing_default() -> str:
    return (ROOT / "skills" / "impl" / "impl-routing.md").read_text(encoding="utf-8")


def read_module_architect() -> str:
    return (
        ROOT / "docs" / "plugin" / "agents" / "module-architect" / "module-architect-agent.md"
    ).read_text(encoding="utf-8")


def read_workflow_router() -> str:
    return (ROOT / "docs" / "plugin" / "workflow-router.md").read_text(encoding="utf-8")


def read_build_worker() -> str:
    return (
        ROOT / "docs" / "plugin" / "agents" / "build-worker" / "build-worker-agent.md"
    ).read_text(encoding="utf-8")


class TestPreReadCostAware(unittest.TestCase):
    """#436 — 사전 read 의무가 cost-aware 룰 명시."""

    def test_section_renamed_with_cost_aware_marker(self):
        body = read_impl_skill()
        self.assertIn(
            "## impl 파일 사전 read 의무 (MUST — module-architect 7 원칙 + cost-aware #436)",
            body,
        )

    def test_full_read_prohibition_marker(self):
        """통째 read 금지 + 200 line 초과 시 부분 read 룰."""
        body = read_impl_skill()
        self.assertIn("통째 read 금지", body)
        self.assertIn("200 line 초과", body)
        self.assertIn("grep + offset", body)

    def test_per_file_read_scope_table_present(self):
        """파일별 read 범위 표 박힘 — architecture.md / decisions / prd.md / PR body / 형제 PR / 의존 모듈."""
        body = read_impl_skill()
        # 표 헤더
        self.assertIn("| 항목 | read 범위 |", body)
        # 핵심 항목 6개 매핑
        self.assertIn("`docs/architecture.md`", body)
        self.assertIn("`docs/decisions/`", body)
        self.assertIn("`docs/prd.md`", body)
        self.assertIn("의존 task 머지 PR", body)
        self.assertIn("형제 PR 환기", body)
        self.assertIn("의존 모듈", body)

    def test_signature_only_read_for_unmodified_module(self):
        """수정 X 영역 = grep + 시그니처만 read."""
        body = read_impl_skill()
        self.assertIn("grep + 시그니처만", body)
        self.assertIn('grep "^export"', body)

    def test_pr_body_jq_head_pattern(self):
        """PR body 통째 json 폐기 — --jq '.body' | head -20 패턴."""
        body = read_impl_skill()
        self.assertIn("--jq '.body'", body)
        self.assertIn("head -20", body)

    def test_main_direct_read_is_minimum(self):
        """메인 직접 read 의무 = 진입 분기 판단 최소만."""
        body = read_impl_skill()
        self.assertIn("진입 분기 판단", body)
        self.assertIn("최소", body)
        self.assertIn("메인이 통째 read 하지 말 것", body)

    def test_402_cost_aware_reference(self):
        """CLAUDE.md §cost-aware 행동 (#402) 정합 명시."""
        body = read_impl_skill()
        self.assertIn("#402", body)
        self.assertIn("cost-aware", body)


class TestImplLoopSingleEngine(unittest.TestCase):
    """#1023 — impl-loop uses a single build-worker engine and batch review."""

    def test_impl_loop_declares_single_build_worker_engine(self):
        skill = read_impl_skill()
        routing = read_impl_routing()
        for body in (skill, routing):
            with self.subTest(body=body[:60]):
                self.assertIn("build-worker", body)
                self.assertIn("impl-validator", body)
                self.assertIn("product-acceptance", body)
                self.assertNotIn("test-engineer", body)
                self.assertNotIn("engineer:IMPL", body)
                self.assertNotIn("2agent", body)
                self.assertNotIn("4agent", body)

    def test_batch_review_boundary_replaces_story_pr_stop(self):
        skill = read_impl_skill()
        for needle in (
            "batch-review",
            "ready_for_review",
            "그 전에는 story PR 로 멈추지 않고 다음 task 로 진행",
            "impl-validator review 출력은 merge candidate 경계에서 1회",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, skill)

    def test_impl_task_template_does_not_emit_engine_taxonomy(self):
        template = (
            ROOT / "docs" / "plugin" / "agents" / "module-architect" / "templates" / "impl-task.md"
        ).read_text(encoding="utf-8")
        for stale in ("risk:", "engine:", "risk_reason:", "depth:"):
            self.assertNotIn(stale, template)
        self.assertIn("depends_on:", template)

    def test_module_architect_documents_depends_on_only_metadata(self):
        module_architect = read_module_architect()
        self.assertIn("frontmatter 에는 `depends_on` 만", module_architect)
        self.assertIn("build-worker 하나", module_architect)
        self.assertIn("`risk` / `engine` / `risk_reason` / `depth` 를 새로 쓰지 않는다", module_architect)

    def test_build_worker_self_check_keeps_invariant_drift_warning(self):
        body = read_build_worker()
        self.assertIn("도메인 invariant 변경은 build-worker self-grading drift", body)
        self.assertIn("build-worker 단일 실행", body)
        self.assertIn("decision 으로 합의된 invariant 구현에도 적용", body)
        self.assertNotIn("풀 경로 승격", body)


if __name__ == "__main__":
    unittest.main()

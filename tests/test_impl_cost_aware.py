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


class TestImplLoopRiskPreview(unittest.TestCase):
    """chain dry preview 가 task 별 risk/engine 판정 증거를 남기는지 검증."""

    def test_chain_plan_table_has_risk_engine_reason_columns(self):
        body = read_impl_skill()
        self.assertIn(
            "| # | 모듈 | impl 파일 | task_index | PR 트레일러 | risk | engine | reason | sub-step |",
            body,
        )
        self.assertIn(
            "|---|------|----------|-----------|-----------|------|--------|--------|----------|",
            body,
        )

    def test_risk_reason_is_required_before_task_execution(self):
        body = read_impl_skill()
        self.assertIn("task1 진입 *전* 실행 계획", body)
        # #703 — risk enum = frontmatter canonical 값 (normal/high/low), engine = 2agent/4agent.
        self.assertIn("`risk` ∈ `normal`/`high`/`low`", body)
        self.assertIn("`reason` 은 비워 두지 않는다", body)
        self.assertIn("고위험 trigger 없음", body)

    def test_risk_engine_read_from_frontmatter_first(self):
        # #703 — dry preview / 진입 분기가 frontmatter risk/engine 을 추론보다 우선.
        skill = read_impl_skill()
        routing = read_impl_routing()
        self.assertIn("frontmatter 에 `risk`/`engine`/`risk_reason` 이 유효한 단일 값", skill)
        self.assertIn("frontmatter 우선", skill)
        self.assertIn("`engine: 4agent` → 풀 4-agent", routing)

    def test_placeholder_risk_metadata_treated_as_absent(self):
        # #703 codex P1 — 템플릿 미작성 잔재(normal|high|low)를 부재로 간주, 추론 fallback.
        skill = read_impl_skill()
        routing = read_impl_routing()
        self.assertIn("placeholder 가드", skill)
        # 진입 분기 + dry preview 양쪽 모두 placeholder 가드 명시 (소비 지점 2곳).
        self.assertGreaterEqual(skill.count("placeholder"), 2)
        self.assertIn("placeholder", routing)

    def test_high_risk_routes_to_full_agent_even_when_chain_defaults_worker(self):
        skill = read_impl_skill()
        routing = read_impl_routing()
        for body in (skill, routing):
            self.assertIn("고위험 trigger 는 build-worker 선호보다 우선", body)
            self.assertIn("풀 4-agent", body)
            self.assertIn("reason", body)


if __name__ == "__main__":
    unittest.main()

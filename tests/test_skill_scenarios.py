"""Skill/agent 자연어 룰 회귀 테스트 (이슈 #521).

skill·agent 문서의 catastrophic 자연어 룰이 문서 리팩터링 중 사라지면 FAIL 한다.
LLM 호출 없이, 문서에 핵심 룰 문구(닻)가 존속하는지만 assertIn/정규식으로 검증한다.

설계 원칙 (이슈 #521 AC #4 + CLAUDE.md 안티패턴 3 정합):
- agent 의 *런타임 출력 형식*을 강제하지 않는다. 문서에 룰이 존속하는지만 본다.
  즉 catastrophic *행동*(시퀀스 / false-clean / TaskCreate / phase prose / 5줄 echo)의
  문서적 보존만 검증한다.
- anchor 는 의미 최소 단위로 잡는다. 긴 문장을 통째로 박지 않는다 — 정상 리워딩에는 안 깨지고
  룰의 *의미*가 사라질 때만 FAIL 하도록.

대상 = 필수 3개 skill: /impl · /impl-loop · /init-dcness (시나리오 1~5).
manifest drift(시나리오 6)와 합성 trace fixture 는 본 scope 밖(follow-up).
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SkillScenarioRegressionTests(unittest.TestCase):
    """이슈 #521 시나리오 1~5 — catastrophic 자연어 룰 anchor 존속 검증."""

    def setUp(self) -> None:
        self.impl_skill = (ROOT / "skills" / "impl" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.impl_routing = (ROOT / "skills" / "impl" / "impl-routing.md").read_text(
            encoding="utf-8"
        )
        self.impl_loop_skill = (
            ROOT / "skills" / "impl-loop" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.impl_loop_routing = (
            ROOT / "skills" / "impl-loop" / "impl-loop-routing.md"
        ).read_text(encoding="utf-8")
        self.build_worker = (
            ROOT / "agents" / "build-worker" / "build-worker-agent.md"
        ).read_text(encoding="utf-8")
        self.test_engineer = (
            ROOT / "agents" / "test-engineer" / "test-engineer-agent.md"
        ).read_text(encoding="utf-8")
        self.init_doc = (ROOT / "commands" / "init-dcness.md").read_text(
            encoding="utf-8"
        )

    # ----- 시나리오 1 — /impl default 4-agent 시퀀스 -----
    def test_impl_default_sequence_keeps_four_agent_order(self) -> None:
        """/impl Standard happy path = test-engineer → engineer → code-validator → pr-reviewer 순서 보존.

        4 단계 중 하나라도 빠지거나 순서가 바뀌면 false-clean 회귀(#431)로 직결된다.
        """
        # impl SKILL task_list — 정확한 시퀀스 (화살표 →)
        self.assertIn(
            "test-engineer → engineer:IMPL → code-validator → pr-reviewer",
            self.impl_skill,
        )
        # impl-routing 표 — 정확한 시퀀스 (화살표 ->)
        self.assertIn(
            "test-engineer -> engineer:IMPL -> code-validator -> pr-reviewer",
            self.impl_routing,
        )
        # impl-loop 엔진 A — 4 단계가 이 순서로 + "모두 호출" 의무 키워드 보존.
        self.assertRegex(
            self.impl_loop_skill,
            r"test-engineer.*engineer.*code-validator.*pr-reviewer",
        )
        self.assertIn("모두 호출", self.impl_loop_skill)

    # ----- 시나리오 2a — build-worker phase prose 3개 -----
    def test_build_worker_requires_three_phase_prose_files(self) -> None:
        """build-worker 는 build-test.md / build-impl.md / build-validate.md 3개 phase prose 를 남겨야 한다.

        phase prose 누락은 false-clean 의 대표 회귀 — 누락 시 blocked 강등이 룰이다.
        """
        for name in ("build-test.md", "build-impl.md", "build-validate.md"):
            self.assertIn(name, self.build_worker)
        # phase prose 작성 + 3개 실존 확인 의무.
        self.assertIn("phase prose", self.build_worker)
        self.assertIn("3개 실존", self.build_worker)
        # impl-loop 안티패턴 — phase prose 부재 시 blocked 강등.
        self.assertIn("build-{test,impl,validate}.md", self.impl_loop_skill)

    # ----- 시나리오 2a-2 — build-worker 결론 enum 노출 정합 -----
    def test_build_worker_conclusion_enums_consistent_with_template(self):
        """agent 본문과 report 템플릿의 결론 enum 집합이 갈라지면 worker 가 템플릿 쪽
        구식 enum 으로 보고해 다음 호출 판단이 오분기된다 (리뷰 P2 실측 — VALIDATION_BLOCKED 누락)."""
        template = (
            ROOT / "agents" / "build-worker" / "templates" / "build-worker-report.md"
        ).read_text(encoding="utf-8")
        for enum in (
            "PASS", "SPEC_GAP_FOUND", "TESTS_FAIL",
            "VALIDATION_BLOCKED", "IMPLEMENTATION_ESCALATE",
        ):
            self.assertIn(enum, self.build_worker)
            self.assertIn(enum, template)

    def test_test_agents_do_not_close_core_ac_with_mock_only_green(self) -> None:
        """테스트 생성/경량 구현 단계가 mock-only green 을 핵심 AC 증거로 남기지 않도록 닻을 둔다."""
        for text in (self.test_engineer, self.build_worker):
            self.assertIn("동작 증거", text)
            self.assertIn("mock-only", text)
            self.assertIn("핵심 AC", text)

    # ----- 시나리오 2b — /impl-loop chain review 5줄 echo -----
    def test_impl_loop_chain_review_echo_is_five_line(self) -> None:
        """chain review echo = 5줄 요약, 자유 형식 단축 금지 (#446, F8 실측 #507)."""
        self.assertIn("5줄 요약", self.impl_loop_skill)
        self.assertIn("자유 형식 단축 금지", self.impl_loop_skill)
        # 5줄 템플릿의 핵심 줄 키 보존 (구조가 무너지면 FAIL).
        for key in ("finding:", "PR <#NNN> merged", "next:"):
            self.assertIn(key, self.impl_loop_skill)

    # ----- 시나리오 3 — false-clean 차단 -----
    def test_false_clean_downgrades_to_blocked(self) -> None:
        """worker/validator 흔적 없이 clean 표기 금지 — false-clean → blocked 강등 (#431)."""
        # impl-loop SKILL: false-clean 의심 → blocked 강등 (한 문장 안에 인과).
        self.assertRegex(self.impl_loop_skill, r"false-clean.*blocked")
        # impl-loop routing: clean 판정 게이트에서도 false-clean → blocked.
        self.assertRegex(self.impl_loop_routing, r"false-clean.*blocked")
        # impl Lite 최소 gate 에도 false-clean 방지 명시.
        self.assertIn("false-clean", self.impl_skill)

    # ----- 시나리오 4 — TaskCreate / TaskUpdate 의무 -----
    def test_task_create_update_is_mandatory(self) -> None:
        """impl-loop 모든 step 은 TaskCreate / TaskUpdate 와 한 묶음 — 자율 skip 금지 (사용자 가시성)."""
        self.assertIn("TaskCreate", self.impl_loop_skill)
        self.assertIn("TaskUpdate", self.impl_loop_skill)
        self.assertIn("자율 skip 금지", self.impl_loop_skill)
        # skip 은 중대 차단 안티패턴으로 명시돼야 한다.
        self.assertIn("중대 차단 안티패턴", self.impl_loop_skill)

    # ----- 시나리오 5 — /init-dcness deploy path -----
    def test_init_dcness_deploy_sources_exist(self) -> None:
        """init-dcness 가 cp 하는 모든 $PLUGIN_ROOT source 가 실제 repo 에 존재해야 한다.

        새 배포 파일이 rename/삭제됐는데 init-dcness 가 옛 경로를 cp 하려 하면(dangling deploy)
        외부 활성 프로젝트의 init 이 깨진다 — 그 회귀를 여기서 차단한다.
        """
        sources = re.findall(r'cp "\$PLUGIN_ROOT/([^"]+)"', self.init_doc)
        self.assertTrue(
            sources, 'init-dcness.md 에 cp "$PLUGIN_ROOT/..." deploy 라인이 없음'
        )
        for src in sources:
            # 셸 변수($FILE/$DIR) 포함 경로는 변수 앞 디렉토리 prefix 로 실존 확인.
            if "$" in src:
                prefix = src.split("$", 1)[0].rstrip("/")
                target = ROOT / prefix
            else:
                target = ROOT / src
            self.assertTrue(
                target.exists(),
                f"init-dcness deploy source 부재: {src} → {target.relative_to(ROOT)}",
            )

    def test_init_dcness_core_hooks_listed(self) -> None:
        """핵심 thin-shim hook 3개가 deploy 섹션에 명시돼야 한다 (배포 누락 차단)."""
        for hook in (
            "scripts/hooks/commit-msg",
            "scripts/hooks/post-checkout",
            "scripts/hooks/pre-push",
        ):
            self.assertIn(hook, self.init_doc)

    def test_init_dcness_optional_bundle_uses_one_prompt(self) -> None:
        """#799 — 선택형 확장은 기본 경로에서 bundle 1질문으로만 진입한다."""
        for needle in (
            "추천 bundle",
            "Y/n/custom",
            "빈 입력은 Y",
            "선택형 확장",
            "GitHub Project lifecycle 은 기본 skip",
            "root architecture.md 감지로 docs/architecture.md skip",
            "gh auth status",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.init_doc)


if __name__ == "__main__":
    unittest.main()

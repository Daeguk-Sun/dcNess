"""재실행 범위와 반복 중단을 agent 판단으로 정한다는 지침 계약 테스트."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHARED = "docs/plugin/agents/_shared/rerun-judgment.md"
PRODUCT_ACCEPTANCE = "docs/plugin/agents/product-acceptance/product-acceptance-agent.md"
BUILD_WORKER = "docs/plugin/agents/build-worker/build-worker-agent.md"
ARCH_VALIDATOR = "docs/plugin/agents/architecture-validator/architecture-validator-agent.md"
CODEX_ARCH_VALIDATOR = "codex/skills/dcness-architecture-validator/SKILL.md"
FINISH = "skills/impl-loop/impl-loop-finish.md"
DESIGN_ROUTING = "skills/design/design-routing.md"
TECH_REVIEW_ROUTING = "skills/tech-review/tech-review-routing.md"

# 지침이 다시 실행·재검증 범위를 고르는 구간의 문서. 고정 조건 문장이 돌아오면 안 된다.
GUIDES = (
    PRODUCT_ACCEPTANCE,
    BUILD_WORKER,
    ARCH_VALIDATOR,
    CODEX_ARCH_VALIDATOR,
    FINISH,
    DESIGN_ROUTING,
    TECH_REVIEW_ROUTING,
    "docs/plugin/agents/module-architect/module-architect-agent.md",
    "docs/plugin/agents/module-architect/templates/impl-task.md",
    "docs/plugin/agents/architecture-validator/templates/review-report.md",
    "docs/plugin/agents/tech-reviewer/tech-reviewer-agent.md",
    "docs/plugin/product-journey.md",
    "docs/plugin/loop-procedure.md",
    "skills/design/SKILL.md",
    "skills/design-system/SKILL.md",
    "skills/design-ux/SKILL.md",
    "skills/impl/impl-finish.md",
    "skills/impl/impl-routing.md",
    "skills/impl-loop/impl-loop-routing.md",
    "skills/spec/SKILL.md",
    "skills/tech-review/SKILL.md",
)

FIXED_CONDITION_PHRASES = (
    "기존 receipt 유무와 무관하게",
    "기존 수렴 receipt와 무관하게",
    "항상 전체 시나리오",
    "`--scenario` 없이 전체 시나리오를 실행한다",
    "전체 시나리오를 한 번 실행해",
    "개정분만 보지 않고",
    "개정분만 보는 것이 아니라",
    "전수 실행에서 생략하지 않는다",
    "전수 검증에서 생략하지 않는다",
    "마지막 task 전수 검증",
    "무진행은 3회",
    "전체 iteration은 12회",
    "hotfix 등으로 stale이면",
    "hotfix로 stale이면",
    "최대 3회",
    "재리뷰 한도는 현행 3회",
)
NUMERIC_LIMIT = re.compile(r"(≤\s*\d|\d\s*cycle|cycle\s*≤)")


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class SharedCriteriaTests(unittest.TestCase):
    def test_shared_doc_states_the_four_scope_behaviours(self) -> None:
        text = read(SHARED)
        for needle in (
            "변경분을 읽고 고른다",
            "스스로 전체로 올린다",
            "다시 하지 않은 이유를 적는다",
            "기록이 없으면 전체로 한다",
            "호출자는 범위를 좁혀 처방하지 않고, 전체로 올리는 것도 막지 않는다",
            "가장 최근 결과**일 때만 생략의 근거가 된다",
            "실패하거나 gap 으로 남은 대상은 변경분이 닿는지와 무관하게 생략 후보가 아니다",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)

    def test_shared_doc_states_the_stop_judgment_without_a_numeric_limit(self) -> None:
        text = read(SHARED)
        for needle in (
            "다시 실행하기 전에 답한다",
            "같은 신호가 다시 나오면 신호를 먼저 의심한다",
            "검사 도구의 오판, 실행 환경, 제품 결함 순서",
            "더 싼 관찰을 먼저 쓴다",
            "관찰 수단부터 보강한다",
            "새 정보가 없으면 멈춘다",
            "서로 다른 실패의 순차 노출은 진전이다",
            "분류만 바꿔 계속 재시도하지 않는다",
            "숫자 한도를 중단 조건으로 쓰지 않는다",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        self.assertIsNone(NUMERIC_LIMIT.search(text))

    def test_shared_doc_does_not_force_an_output_format(self) -> None:
        text = read(SHARED)
        self.assertIn("형식이 아니라 의미 요구", text)
        self.assertIn("문장 형식은 자유다", text)

    def test_shared_doc_keeps_the_hook_order_untouched(self) -> None:
        text = read(SHARED)
        self.assertIn("harness 가 강제하는 것은 순서", text)
        self.assertIn("검수 agent 는 새 커밋에서 계속 호출된다", text)


class GuideAdoptionTests(unittest.TestCase):
    def test_fixed_condition_sentences_are_gone(self) -> None:
        for path in GUIDES:
            text = read(path)
            for phrase in FIXED_CONDITION_PHRASES:
                with self.subTest(path=path, phrase=phrase):
                    self.assertNotIn(phrase, text)

    def test_no_numeric_retry_limit_remains_as_a_stop_condition(self) -> None:
        # loop-procedure.md 는 재시도와 무관한 수치(git 안전 가드 등)를 함께 담는다.
        for path in (path for path in GUIDES if path != "docs/plugin/loop-procedure.md"):
            with self.subTest(path=path):
                self.assertIsNone(NUMERIC_LIMIT.search(read(path)))

    def test_agents_that_rerun_or_recheck_read_the_shared_criteria(self) -> None:
        for path in (
            PRODUCT_ACCEPTANCE,
            BUILD_WORKER,
            ARCH_VALIDATOR,
            "docs/plugin/agents/tech-reviewer/tech-reviewer-agent.md",
            FINISH,
            DESIGN_ROUTING,
            "skills/impl/impl-routing.md",
            "skills/impl-loop/impl-loop-routing.md",
            "skills/design-ux/SKILL.md",
            "skills/spec/SKILL.md",
            "skills/tech-review/SKILL.md",
        ):
            with self.subTest(path=path):
                self.assertIn("rerun-judgment.md", read(path))

    def test_product_acceptance_chooses_what_to_rerun_and_records_the_rest(self) -> None:
        text = read(PRODUCT_ACCEPTANCE)
        for needle in (
            "변경분을 읽고",
            "같은 커밋에서 실패한 대상을 변경이 없다는 이유로 건너뛰지 않는다",
            "`skip`이 근거가 없다고 출력하면 생략하지 않고 실행한다",
            "닿지 않는다는 근거를 댈 수 있으면 다시 실행하지 않고",
            "dcness-product-journey skip",
            "변경분을 계산할 수 없으면 전체를 실행한다",
            "스스로 넓힌다",
            "이유 없이 생략한 대상이 있으면 PASS 하지 않는다",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)

    def test_convergence_worker_questions_a_repeated_signal_before_rerunning(self) -> None:
        text = read(BUILD_WORKER)
        for needle in (
            "반복은 횟수로 멈추지 않는다",
            "답이 없으면 다시 실행하지 않는다",
            "신호 자체를 먼저 의심",
            "더 싼 관찰",
            "관찰 수단부터 보강",
            "누적 실행 횟수와 시간",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)

    def test_evidence_invalidation_keeps_the_order_but_not_a_full_rerun(self) -> None:
        text = read(FINISH)
        self.assertIn("이 순서는 종료 게이트가 강제한다", text)
        self.assertIn("각 단계가 실제로 무엇을 다시 실행·검토할지는 변경분을 읽고 정한다", text)
        self.assertIn("문서만 바뀐 변경처럼 실행 경로에 닿지 않는 변경은 journey를 다시 실행할 이유가 아니다", text)


class CommandExampleTests(unittest.TestCase):
    """지침의 명령 예시는 실행 도구의 필수 인자를 빠뜨리지 않는다."""

    def test_journey_command_examples_with_options_name_the_manifest(self) -> None:
        example = re.compile(r"`dcness-product-journey (?:run|skip) --[^`]*`")
        found = 0
        for path in (PRODUCT_ACCEPTANCE, BUILD_WORKER, FINISH, "skills/acceptance/SKILL.md"):
            for match in example.finditer(read(path)):
                found += 1
                with self.subTest(path=path, example=match.group(0)):
                    self.assertIn("--config ", match.group(0))
        self.assertGreaterEqual(found, 5)

    def test_skip_examples_carry_a_reason(self) -> None:
        example = re.compile(r"`dcness-product-journey skip --[^`]*`")
        for path in (PRODUCT_ACCEPTANCE, BUILD_WORKER):
            matches = example.findall(read(path))
            self.assertTrue(matches, path)
            for text in matches:
                with self.subTest(path=path, example=text):
                    self.assertIn("--reason ", text)


class ProviderParityTests(unittest.TestCase):
    """Claude 경로와 Codex 경로의 설계 검증 지침이 같은 내용을 담는다."""

    def _sentence(self, text: str, start: str) -> str:
        begin = text.index(start)
        return text[begin : text.index("만들지 않는다.", begin)]

    def test_revision_scope_sentence_is_identical_for_both_providers(self) -> None:
        start = "revision mode 와 FAIL 뒤 재검증에서는 직전 통과·검증 결과 이후의 변경분을 읽고"
        self.assertEqual(
            self._sentence(read(ARCH_VALIDATOR), start),
            self._sentence(read(CODEX_ARCH_VALIDATOR), start),
        )

    def test_last_task_and_retry_ownership_match_for_both_providers(self) -> None:
        for needle in (
            "Story 마지막 task 의 종합 검증이 Story AC 전항목을 덮는가",
            "어느 task 의 증거로 덮는지와 닿지 않는 이유",
            "재시도를 계속할지 정하지 않는다",
            "새 시도의 근거처럼 표현하지 않는다",
            "다시 검토하지 않은 산출물의 이유",
        ):
            for path in (ARCH_VALIDATOR, CODEX_ARCH_VALIDATOR):
                with self.subTest(path=path, needle=needle):
                    self.assertIn(needle, read(path))


class SingleRetrySourceTests(unittest.TestCase):
    def test_new_dependency_reentry_rule_lives_in_one_document(self) -> None:
        routing = read(DESIGN_ROUTING)
        tech_review = read(TECH_REVIEW_ROUTING)
        self.assertIn("이 경로의 재진입 기준은 본 문서 한 곳이 소유한다", routing)
        self.assertIn("design-routing.md#재시도-판단", tech_review)
        self.assertIn("본 문서는 별도 횟수를 두지 않는다", tech_review)


if __name__ == "__main__":
    unittest.main()

"""Workflow-level Cartography freshness contracts for issue #1057."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class CartographyWorkflowIntegrationTests(unittest.TestCase):
    def test_design_preflight_checks_current_code_without_stealing_bounded_writes(self) -> None:
        skill = read("skills/design/SKILL.md")
        routing = read("skills/design/design-routing.md")
        stage = read("skills/design-system/SKILL.md")

        for text in (skill, routing, stage):
            self.assertIn("affected capability/entrypoint", text)
            self.assertIn("현재 코드", text)
            self.assertIn("system boundary", text)
            self.assertIn("storage policy", text)
            self.assertIn("global decision", text)
            self.assertIn("SYSTEM_CHECKPOINT_REQUIRED", text)

        self.assertIn("module-architect가 bounded하게", skill)
        self.assertNotIn("Cartography 전용 system-architect", skill)
        self.assertNotIn("전역 Cartography의 단일 write owner", skill)

    def test_direct_impl_hands_impact_and_root_coordinates_to_validator(self) -> None:
        skill = read("skills/impl/SKILL.md")
        routing = read("skills/impl/impl-routing.md")

        for text in (skill, routing):
            self.assertIn("Cartography impact", text)
            self.assertIn("affected Root Cartography", text)
            self.assertIn("관련 epic/decision", text)
            self.assertIn("merge candidate diff", text)

        for meaning in (
            "runtime entrypoint",
            "owner",
            "dependency edge",
            "public surface",
            "before/after",
        ):
            self.assertIn(meaning, skill)

    def test_direct_impl_routes_three_freshness_results(self) -> None:
        skill = read("skills/impl/SKILL.md")
        routing = read("skills/impl/impl-routing.md")

        for text in (skill, routing):
            self.assertIn("영향 없음 또는 Root와 일치", text)
            self.assertIn("route/state/as-built edge", text)
            self.assertIn("CARTOGRAPHY_REFRESH", text)
            self.assertIn("재검증", text)
            self.assertIn("/design --revise", text)
            self.assertIn("system checkpoint", text)
            self.assertIn("local-only/ignored", text)
            self.assertIn("durable impact handoff", text)
            self.assertIn("durable impact handoff만으로 freshness가 해소되지는 않", text)

        self.assertIn("module-architect", skill)
        self.assertIn("읽기 전용", skill)

    def test_impl_loop_preserves_impact_through_review_and_acceptance(self) -> None:
        skill = read("skills/impl-loop/SKILL.md")
        routing = read("skills/impl-loop/impl-loop-routing.md")

        for text in (skill, routing):
            self.assertIn("build-worker Cartography impact", text)
            self.assertIn("affected Root Cartography", text)
            self.assertIn("CARTOGRAPHY_REFRESH", text)
            self.assertIn("impl-validator 재검증", text)
            self.assertIn("capability 상태 drift", text)
            self.assertIn("최종 clean", text)
            self.assertIn("/design --revise", text)
            self.assertIn("durable impact handoff만으로 freshness가 해소되지는 않", text)

        self.assertIn("acceptance 재검수", routing)

    def test_validator_does_not_treat_durable_handoff_as_refresh_completion(self) -> None:
        validators = (
            read("docs/plugin/agents/impl-validator/impl-validator-agent.md"),
            read("codex/skills/dcness-impl-validator/SKILL.md"),
        )

        for validator in validators:
            self.assertIn("durable impact handoff는 freshness 해소가 아니다", validator)
            self.assertIn("route-only drift가 남아 있으면 PASS하지 않는다", validator)
            self.assertIn("canonical local Root refresh", validator)

    def test_standalone_acceptance_reports_the_next_freshness_producer(self) -> None:
        skill = read("skills/acceptance/SKILL.md")
        routing = read("skills/acceptance/acceptance-routing.md")

        for text in (skill, routing):
            self.assertIn("affected Root Cartography", text)
            self.assertIn("CARTOGRAPHY_REFRESH", text)
            self.assertIn("module-architect", text)
            self.assertIn("durable impact handoff", text)
            self.assertIn("/design --revise", text)
            self.assertIn("읽기 전용", text)
            self.assertIn("durable impact handoff만으로 freshness가 해소되지는 않", text)

    def test_eval_suite_covers_all_integration_outcomes(self) -> None:
        cases = {
            "cartography-no-impact": ("Root와 일치", "PASS"),
            "cartography-mms-system-impact": ("MMS", "system checkpoint"),
            "cartography-refresh": ("route-only refresh", "local-only"),
            "cartography-validator-drift": ("as-built", "route-only refresh"),
            "cartography-acceptance-stale-state": ("landed", "제품 동작"),
            "cartography-lifecycle-smoke": ("design(planned/stub)", "다음 design"),
        }

        for case, needles in cases.items():
            case_dir = ROOT / "evals" / "cases" / case
            with self.subTest(case=case):
                self.assertTrue((case_dir / "prompt.md").is_file())
                expected = (case_dir / "expected.md").read_text(encoding="utf-8")
                for needle in needles:
                    self.assertIn(needle, expected)

        lifecycle = ROOT / "evals" / "cases" / "cartography-lifecycle-smoke"
        self.assertTrue((lifecycle / "validation-after-refresh.md").is_file())
        lifecycle_expected = (lifecycle / "expected.md").read_text(encoding="utf-8")
        self.assertIn("bounded refresh → code revalidation → acceptance", lifecycle_expected)


if __name__ == "__main__":
    unittest.main()

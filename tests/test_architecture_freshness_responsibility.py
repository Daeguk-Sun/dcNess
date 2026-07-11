"""Implementation-stage Cartography freshness contracts for issue #1058."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class ArchitectureFreshnessResponsibilityTests(unittest.TestCase):
    def test_issue_1059_bounded_root_contract_is_preserved(self) -> None:
        module = read(
            "docs/plugin/agents/module-architect/module-architect-agent.md"
        )
        architecture_validator = read(
            "docs/plugin/agents/architecture-validator/architecture-validator-agent.md"
        )
        system = read(
            "docs/plugin/agents/system-architect/system-architect-agent.md"
        )

        self.assertIn(
            "Root 갱신 조건에 해당하는 `docs/architecture.md` Cartography route",
            module,
        )
        self.assertIn("Root Cartography", architecture_validator)
        self.assertIn("landed/stub/planned/deferred", system)
        self.assertNotIn("전역 Cartography의 단일 write owner", system)
        self.assertNotIn("Root Cartography를 직접 수정하지 않는다", module)

    def test_build_worker_reports_implementation_cartography_impact(self) -> None:
        worker = read("docs/plugin/agents/build-worker/build-worker-agent.md")
        report = read(
            "docs/plugin/agents/build-worker/templates/build-worker-report.md"
        )

        for text in (worker, report):
            for meaning in (
                "runtime entrypoint",
                "owner",
                "dependency edge",
                "public surface",
                "before/after",
                "관련 epic/decision",
            ):
                self.assertIn(meaning, text)
        self.assertIn("자유 prose", worker)
        self.assertIn("`docs/**` 수정", worker)
        self.assertIn("local-only", worker)

    def test_both_impl_validators_detect_as_built_drift_read_only(self) -> None:
        validators = (
            read("docs/plugin/agents/impl-validator/impl-validator-agent.md"),
            read("codex/skills/dcness-impl-validator/SKILL.md"),
        )

        for validator in validators:
            self.assertIn("build-worker impact 보고", validator)
            self.assertIn("affected Root Cartography", validator)
            self.assertIn("as-built drift", validator)
            self.assertIn("dependency edge", validator)
            self.assertIn("landed", validator)
            self.assertIn("route-only refresh", validator)
            self.assertIn("system boundary", validator)
            self.assertIn("읽기 전용", validator)

    def test_epic_acceptance_audits_inherited_capability_states(self) -> None:
        acceptance = read(
            "docs/plugin/agents/product-acceptance/product-acceptance-agent.md"
        )

        self.assertIn("epic이 인수한", acceptance)
        for state in ("planned", "stub", "deferred", "landed"):
            self.assertIn(state, acceptance)
        self.assertIn("제품 동작·검증 증거", acceptance)
        self.assertIn("route-only refresh", acceptance)

    def test_as_built_drift_fixture_has_lifecycle_edge_missing_from_root(self) -> None:
        case = ROOT / "evals/cases/cartography-validator-drift"
        prompt = (case / "prompt.md").read_text(encoding="utf-8")
        expected = (case / "expected.md").read_text(encoding="utf-8")
        diff = (case / "diff.md").read_text(encoding="utf-8")
        root_map = (case / "architecture.md").read_text(encoding="utf-8")

        self.assertIn("impl-validator", prompt)
        self.assertIn("MessageObserver", diff)
        self.assertNotIn("MessageObserver", root_map)
        self.assertIn("route-only refresh", expected)
        self.assertIn("문서 수정 권한", expected)

    def test_eval_suite_covers_refresh_and_system_backpressure(self) -> None:
        route_only = read("evals/cases/cartography-refresh/expected.md")
        system_change = read(
            "evals/cases/cartography-system-checkpoint/expected.md"
        )

        self.assertIn("route-only refresh", route_only)
        self.assertIn("local-only", route_only)
        self.assertIn("system boundary", system_change)
        self.assertIn("/design", system_change)


if __name__ == "__main__":
    unittest.main()

"""Cost-aware fast-start and single build-worker contract tests."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_impl_skill() -> str:
    return (ROOT / "skills" / "impl-loop" / "SKILL.md").read_text(encoding="utf-8")


def read_impl_routing() -> str:
    return (ROOT / "skills" / "impl-loop" / "impl-loop-routing.md").read_text(encoding="utf-8")


def read_impl_finish() -> str:
    return (
        ROOT / "skills" / "impl-loop" / "impl-loop-finish.md"
    ).read_text(encoding="utf-8")


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
    """The front door stays focused without restoring the old read matrix."""

    def test_front_door_keeps_task_local_focused_read(self):
        body = read_impl_skill()
        self.assertIn("focused read", body)
        self.assertIn("200 line 초과", body)
        self.assertIn("메인은 worker 대신 문서를 통째로 읽지 않는다", body)

    def test_front_door_does_not_restore_the_old_pre_read_matrix(self):
        body = read_impl_skill()
        self.assertNotIn("| 항목 | read 범위 |", body)
        self.assertNotIn("--jq '.body' | head -20", body)
        self.assertNotIn("docs/architecture.md", body)
        self.assertNotIn("docs/decisions/", body)


class TestImplLoopSingleEngine(unittest.TestCase):
    """#1023/#1041 — one build-worker, story PRs, one integrated review."""

    def test_impl_loop_declares_single_build_worker_engine(self):
        skill = read_impl_skill() + "\n" + read_impl_finish()
        routing = read_impl_routing()
        self.assertIn("build-worker", skill)
        self.assertIn("impl-validator", skill)
        self.assertIn("product-acceptance", skill)
        self.assertIn("build-worker", routing)
        self.assertIn("impl-loop-finish lazy-load", routing)
        self.assertNotIn("impl-validator", routing)
        self.assertNotIn("product-acceptance story", routing)
        for body in (skill, routing):
            with self.subTest(body=body[:60]):
                self.assertNotIn("test-engineer", body)
                self.assertNotIn("engineer:IMPL", body)
                self.assertNotIn("2agent", body)
                self.assertNotIn("4agent", body)

    def test_story_pr_boundary_keeps_one_integrated_review(self):
        skill = read_impl_skill() + "\n" + read_impl_finish()
        for needle in (
            "action=story-pr",
            "story PR",
            "직전 story 브랜치에서 재분기",
            "stack tip vs main",
            "impl-validator review 출력은 merge candidate 경계에서 1회",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, skill)
        for stale in ("batch-review", "ready_for_review", "mark-story"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, skill)

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
